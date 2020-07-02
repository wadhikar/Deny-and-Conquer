import sys
import socket
import threading
import queue
import json
import time as time
from threading import Thread
import math
MICROSECONDS_IN_SECOND = 1000000

class MessageQueue:

	def __init__(self, smoothingDelay):
		self.smoothingDelay = smoothingDelay
		self.lock = threading.Lock()
		self.messageList = []

	def insertMessage(self, message):
		self.lock.acquire()
		self.messageList.append(message)
		self.lock.release()

	def getNextMessage(self):
		currTime = time.time()
		oldestMessage = None
		oldestMessageTime = currTime
		self.lock.acquire()
		for i in range(len(self.messageList)):
			message = self.messageList[i]
			if message["timestamp"] < oldestMessageTime:
				oldestMessage = i
				oldestMessageTime = message["timestamp"]

		if oldestMessage != None and oldestMessageTime < (currTime - self.smoothingDelay*0.001):
			nextMessage = self.messageList[oldestMessage]
			self.messageList.remove(nextMessage)
		else:
			nextMessage = None
		self.lock.release()
		if nextMessage is not None:
			del nextMessage["timestamp"]
		return nextMessage

	def getNumMessages(self):
		self.lock.acquire()
		num = len(self.messageList)
		self.lock.release()
		return num

	def clearSender(self, sender):
		toRemove = []
		self.lock.acquire()
		for message in self.messageList:
			if message["sender"] == sender:
				toRemove.append(message)
		for message in toRemove:
			self.messageList.remove(message)
		self.lock.release()

class StandbyClient:
	def __init__(self, clientSocket, identifier, candidateAddr):
		self.clientSocket = clientSocket
		self.identifier = identifier
		self.candidateAddr = candidateAddr
		self.standbyClientLock = threading.Lock()

class Client:
	def __init__(self, clientSocket, identifier):
		self.sendLock = threading.Lock()
		self.clientSocket = clientSocket
		self.closeSocket = False
		# Look into if we still need this...
		self.identifier = identifier

		# CandidateAddr
		self.candidateAddr = None


	def closeConnection(self):
		self.sendLock.acquire()
		self.closeSocket = True
		self.sendLock.release()

	def connectionActive(self):
		self.sendLock.acquire()
		conActive = not self.closeSocket
		self.sendLock.release()
		return conActive

class Server(threading.Thread):
	def __init__(self, maxNumConnections):
		threading.Thread.__init__(self)
		self.maxDataReceived = 1024
		
		self.shutdown = False
		self.shutdownLock = threading.Lock()
		
		self.connectedClientsLock = threading.Lock()
		self.connectedClients = []
		self.numCurrentConnections = 0

		self.maxNumConnections = maxNumConnections
		for i in range(self.maxNumConnections):
			self.connectedClients.append(None)

		self.sendingQueue = queue.Queue()
		self.receivingQueue = queue.Queue()

		self.messageQueue = MessageQueue(100)

		self.sendFilterLock = threading.Lock()
		self.sendFilter = []

		self.candidatesList = []

		# Variables necessary to handle standby mode
		self.standby = False
		self.standbyLock = threading.Lock()
		self.clientsInStandby = []

	def setShutdown(self):
		self.shutdownLock.acquire()
		self.shutdown = True
		self.shutdownLock.release()

	def getShutdown(self):
		self.shutdownLock.acquire()
		shutdown = self.shutdown
		self.shutdownLock.release()
		return shutdown

	def recordNewClient(self, clientSocket, identifier):
		self.connectedClientsLock.acquire()
		newClientNum = None
		for clientNum in range(len(self.connectedClients)):
			client = self.connectedClients[clientNum]
			if client == None:
				newClient = Client(clientSocket, identifier)
				self.connectedClients[clientNum] = newClient
				newClientNum = clientNum
				self.numCurrentConnections += 1
				break
		# Add a filter so that any left over messages are ignored. 
		self.sendFilterLock.acquire()
		self.sendFilter.append(newClientNum)
		self.sendFilterLock.release()
		# Throw away any message before this flag, as it is left over data.
		self.sendingQueue.put((newClientNum, None))
		
		message = {
			"type": "config",
			"clientNum": newClientNum,
			"candidates": self.candidatesList
		}
		messageStr = json.dumps(message)
		self.sendMessageInternal(clientSocket, messageStr)

		self.connectedClientsLock.release()
		return newClientNum, newClient

	def removeClient(self, oldClientNum):
		self.connectedClientsLock.acquire()
		if self.connectedClients[oldClientNum] != None:
			self.numCurrentConnections -= 1
			removedClient = self.connectedClients[oldClientNum]
			self.connectedClients[oldClientNum] = None 
			# Remove from candidate list, if was a candidate.
			if removedClient.candidateAddr is not None:
				# Remove client from candidate list and alert everyone.
				self.candidatesList.remove(removedClient.candidateAddr)
				response = {
					"type": "removeCandidate",
					"address": removedClient.candidateAddr
				}
				print("REMOVING A CANDIDATE HERE...")
				for clientNumber in range(len(self.connectedClients)):
					client = self.connectedClients[clientNumber]
					if client is not None:
						self.sendMessage(response, clientNumber)

		self.connectedClientsLock.release()

	def getNumConnections(self):
		self.connectedClientsLock.acquire()
		connections = self.numCurrentConnections
		self.connectedClientsLock.release()
		return connections

	def getConnectionsList(self):
		connections = []
		self.connectedClientsLock.acquire()
		for i in range(len(self.connectedClients)):
			connection = self.connectedClients[i]
			if connection is not None:
				connections.append(i)
		self.connectedClientsLock.release()
		return connections

	def getConnection(self, clientNum):
		self.connectedClientsLock.acquire()
		connection = self.connectedClients[clientNum]
		self.connectedClientsLock.release()
		return connection

	def shutdownAllConnections(self):
		self.connectedClientsLock.acquire()
		for i in range(len(self.connectedClients)):
			client = self.connectedClients[i]
			if client is not None:
				client.closeConnection()
				self.numCurrentConnections -= 1
				self.connectedClients[i] = None
		self.connectedClientsLock.release()

	def initServer(self, ipAddr="0.0.0.0", port=0, standby=False):
		# Create a TCP socket for the server.
		self.serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.serverSocket.settimeout(3)

		try:
			self.serverSocket.bind((ipAddr, port))
			serverAddr = self.serverSocket.getsockname()[0]
			serverPort = self.serverSocket.getsockname()[1]
			print("The server is now running. It has the following IP address and port number.\nIP address:", 
				  serverAddr, "\nPort number:", serverPort)
		except:
			print(f"Unable to start the server with IP {ipAddr} and port {port}. Please try providing a (different) valid port number.")
			return None, None

		self.serverSocket.listen(5)
		
		self.standby = standby
		
		return ipAddr, serverPort

	# Handles accepting new connections and creating threads.
	def run(self):
		# Create sendingThread
		sendThread = Thread(target=self.sendingThread)
		sendThread.start()
		# Create custom time queue thread
		receivingThread = Thread(target=self.receivingThread)
		receivingThread.start()

		# Accept new connections until told to shutdown
		shutdown = False
		while shutdown == False:
			newConnection = False
			try:
				clientSocket, address = self.serverSocket.accept()
				clientSocket.settimeout(5)
				newConnection = True
			except socket.timeout:
				pass

			self.standbyLock.acquire()
			if newConnection:
				identifier, candidateAddr = self.initialSetup(clientSocket)
				if identifier is not None and not self.standby:
					# Create a new thread to handle the client
					clientNum, client = self.recordNewClient(clientSocket, identifier)
					print("New connection... just got:", clientNum)
					# Add message to the game queue so it can process the new connection. 
					message = {
						"sender": None,
						"timestamp": time.time(),
						"type": "connect",
						"clientNum": clientNum,
						"identifier": identifier
					}
					messageStr = json.dumps(message)
					self.receivingQueue.put(messageStr)
					Thread(target=self.handleClient, args=(client, clientNum, identifier, )).start()
				elif identifier is not None and self.standby:
					# Throw the client and its meta data into a list to be handled later.
					clientInfo = StandbyClient(clientSocket, identifier, candidateAddr)
					self.clientsInStandby.append(clientInfo)
					Thread(target=self.handleClientStandby, args=(clientInfo, )).start()
				else:
					# Client setup failed. Close connection.
					print("CLOSING HERE.......")  
					clientSocket.close()
			self.standbyLock.release()

			shutdown = self.getShutdown()

		self.setShutdown()

		# Shutdown all client receiving threads.
		self.shutdownAllConnections()

		# Shutdown the sending thread.
		self.sendingQueue.put(None)

		# Shutdown the main receiving thread.
		self.receivingQueue.put(None)

		self.serverSocket.close()

		sendThread.join()

		receivingThread.join()

		print("We are totally done !")

	def startReplacementServer(self, candidates, expectedClients):
		time.sleep(8)
		print("expected:", expectedClients)
		self.standbyLock.acquire()
		self.standby = False
		# Check who is expected and send rejection letters to everyone who needs to be rejected
		candidatesToKeep = []
		clientsWeKept = []
		for client in self.clientsInStandby:
			print("is this guy in?", client.identifier, client.identifier in expectedClients)
			if tuple(client.identifier) in expectedClients:
				candidatesToKeep.append(client.candidateAddr)
				client.standbyClientLock.acquire()
				clientSocket = client.clientSocket
				client.clientSocket = None
				client.standbyClientLock.release()
				clientsWeKept.append((clientSocket, client.identifier))
			else:
				client.standbyClientLock.acquire()
				clientSocket = client.clientSocket
				client.clientSocket = None
				client.standbyClientLock.release()
				# Send a message to the client that they have been rejected. 
				message = {
					"type": "reject"
				}
				messageStr = json.dumps(message)
				self.sendMessageInternal(clientSocket, messageStr)
				clientSocket.close()

		# Update the candidate list. 
		self.connectedClientsLock.acquire()
		self.candidatesList = candidates
		candidatesToRemove = []
		for candidate in self.candidatesList:
			if candidate not in candidatesToKeep:
				candidatesToRemove.append(candidate)
		for candidate in candidatesToRemove:
			self.candidatesList.remove(candidate)
		self.connectedClientsLock.release()

		# Register everyone who needs to be registered
		keptClientsInfo = []
		for keptClient in clientsWeKept:
			clientNum, client = self.recordNewClient(keptClient[0], keptClient[1])
			print("Kept a connection... just got:", clientNum)
			keptClientsInfo.append(tuple(keptClient[1]))
			Thread(target=self.handleClient, args=(client, clientNum, keptClient[1], )).start()

		self.standbyLock.release()

		return keptClientsInfo

	def handleClientStandby(self, clientInfo):
		# Finish the connection handshake...
		message = {
			"type": "config",
			"clientNum": -1,
			"candidates": []
		}
		messageStr = json.dumps(message)
		clientInfo.standbyClientLock.acquire()
		self.sendMessageInternal(clientInfo.clientSocket, messageStr)
		clientInfo.standbyClientLock.release()
		
		while True:
			# Get new message
			clientInfo.standbyClientLock.acquire()
			socket = clientInfo.clientSocket
			if socket is not None:
				message = self.getMessageInternal(clientInfo.clientSocket)
			clientInfo.standbyClientLock.release()

			# Error or client disconnected. Terminate connection.
			if socket == None or message == "" or message == None or self.getShutdown():
				break

			try:
				message = json.loads(message)
			except:
				continue

			if message["type"] == "heartbeat":
				heartbeatResponse = {
					"type": "heartbeat"
				}
				heartbeatResponse = json.dumps(heartbeatResponse)
				clientInfo.standbyClientLock.acquire()
				if clientInfo.clientSocket is not None:
					self.sendMessageInternal(clientInfo.clientSocket, heartbeatResponse)
				clientInfo.standbyClientLock.release()

		# Remove from the standby list unless already processed.
		self.standbyLock.acquire()
		clientInfo.standbyClientLock.acquire()
		if clientInfo.clientSocket is not None:
			clientInfo.clientSocket.close()
			self.clientsInStandby.remove(clientInfo) 
		print("Standby handler died...", self.clientsInStandby)
		clientInfo.standbyClientLock.release()
		self.standbyLock.release()

	def handleClient(self, client, clientNum, identifier):
		while True:
			# Get new message
			message = self.getMessageInternal(client.clientSocket)
			# Error or client disconnected. Terminate connection.
			if message == "" or message == None:
				client.closeConnection()
				print("CLOSING HERE!!!!!!!")  
				client.clientSocket.close()
				# Tell the game core that the client is disconnected.
				message = {
					"sender": None,
					"timestamp": time.time(),
					"type": "disconnect",
					"clientNum": clientNum,
					"identifier": identifier
				}
				messageStr = json.dumps(message)
				self.receivingQueue.put(messageStr)
				# game core must call self.removeClient(clientNum)
				break

			# Check if we should exit or not
			if not client.connectionActive():
				print("CLOSING HERE. because said to")  
				client.clientSocket.close()
				# Tell the game core that the client is disconnected.
				message = {
					"sender": None,
					"timestamp": time.time(),
					"type": "disconnect",
					"clientNum": clientNum,
					"identifier": identifier
				}
				messageStr = json.dumps(message)
				self.receivingQueue.put(messageStr)
				# game core must call self.removeClient(clientNum)
				break

			# Add it to the queue
			try:
				message = json.loads(message)
			except:
				print("bad message,", message)
				continue

			# Handle control messages
			if message["type"] == "heartbeat":
				heartbeatResponse = {
					"type": "heartbeat"
				}
				self.sendMessage(heartbeatResponse, clientNum)
				continue
			# If someone can be a candidate, add it to the candidates list and 
			# alert all connected clients. 
			if message["type"] == "isCandidate":
				self.connectedClientsLock.acquire()
				self.candidatesList.append(message["candidateAddr"])
				response = {
					"type": "addCandidate",
					"address": message["candidateAddr"]
				}
				self.connectedClients[clientNum].candidateAddr = message["candidateAddr"]
				for clientNumber in range(len(self.connectedClients)):
					connectedClient = self.connectedClients[clientNumber]
					if connectedClient is not None:
						self.sendMessage(response, clientNumber)
	
				self.connectedClientsLock.release()
				continue

			# Mark the sender.
			message["sender"] = clientNum
			message["identifier"] = identifier

			message = json.dumps(message)
			self.receivingQueue.put(message)

		print("handler for",clientNum," isdead")

	def sendingThread(self):
		while True:
			messageToSend = self.sendingQueue.get()
			if messageToSend == None:
				break

			clientTarget, message = messageToSend

			skip = False
			self.sendFilterLock.acquire()
			if message is None:
				if clientTarget in self.sendFilter:
					self.sendFilter.remove(clientTarget)
				skip = True
			elif clientTarget in self.sendFilter:
					skip = True
			self.sendFilterLock.release()

			if skip:
				continue

			# Get lock on client target
			client = self.getConnection(clientTarget)
			if client == None:
				print("Client doesnt exist to send anything to.")
				continue

			client.sendLock.acquire()
			# Send if connection is active
			if client.closeSocket == False:
				self.sendMessageInternal(client.clientSocket, message)

			# Release lock on client target
			client.sendLock.release()

	def receivingThread(self):
		while True:
			messageToProcess = self.receivingQueue.get()
			if messageToProcess == None:
				break

			messageToProcess = json.loads(messageToProcess)

			# If message is connection, remove everything from that connection that is currently in the message queue.
			if messageToProcess["type"] == "connect":
				self.messageQueue.clearSender(messageToProcess["clientNum"])

			# Add message to message queue
			self.messageQueue.insertMessage(messageToProcess)

	def sendMessage(self, message, clientNum):
		# Add type if there is not one already
		if "type" not in message:
			message["type"] = "default"
		# Convert the message to JSON string.
		messageStr = json.dumps(message)
		self.sendingQueue.put((clientNum, messageStr))

	def sendToAll(self, message):
		print("sending to all:", message)
		connections = self.getConnectionsList()
		for connection in connections:
			self.sendMessage(message, connection)

	def getMessage(self):
		return self.messageQueue.getNextMessage()

	def getNumMessages(self):
		return self.messageQueue.getNumMessages()

	# This function sends a message to the specified client.
	# It returns True on success and False on failure.
	def sendMessageInternal(self, clientSocket, message):	
		# Convert the message to bytes so it can be sent over the network.	
		messageBytes = message.encode()	
		# Get the length of the message in bytes.
		msgLen = len(messageBytes)
		# Encode the length in bytes as well, to send over the network. 
		msgLenBytes = str(msgLen).encode()
		# If the length is less than 5 bytes long, pad it out to 5 bytes long by adding "0" characters to the front.
		while len(msgLenBytes) < 10:
			msgLenBytes = b"0" + msgLenBytes
		
		# Send the message size and then the message itself to the client.
		try:
			# Send the length of the message to the client, so it knows how many bytes to expect.
			clientSocket.send(msgLenBytes)
			# Send the message itself to the client. 
			clientSocket.send(messageBytes)
			# Return true indicating success.
			return True
		except Exception as e:
			# If an error occured when sending the message to the client, print out an error message with some details
			# and return false to indicate failure. 
			print("Error: Failed to send message to client. Error details:", str(e))
			return False

	def getMessageInternal(self, clientSocket):
		messageSize = self.getMessageSize(clientSocket)
		if messageSize == None:
			return None
		else:
			message = b""
			while len(message) < messageSize:
				remainingChars = messageSize - len(message)
				receivedData = self.receiveData(clientSocket, remainingChars)
				if receivedData == None:
					print("error recieivng.....")
					return None
				elif receivedData == b"":
					return ""
				else:
					message += receivedData
			return str(message, "utf-8")

	def getMessageSize(self, clientSocket):
		messageSizeStrSize = 10
		messageSizeStr = b""
		while len(messageSizeStr) < messageSizeStrSize:
			remainingChars = messageSizeStrSize - len(messageSizeStr)
			receivedData = self.receiveData(clientSocket, remainingChars)
			if receivedData == None:
				print("bad message size.....")
				return None
			elif receivedData == b"":
				return 0
			else:
				messageSizeStr += receivedData

		messageSizeStr = str(messageSizeStr, "utf-8")
		if str.isdigit(messageSizeStr):
			return int(messageSizeStr)
		else:
			print("bad message size.....", messageSizeStr)
			return 0

	def receiveData(self, clientSocket, dataToReceive):
		try:
			receivedData = clientSocket.recv(min(self.maxDataReceived, dataToReceive))
		except socket.timeout:
			return b""
		except Exception as e:
			return None 
		return receivedData


	def closeConnection(self, clientNum):
		connection = self.getConnection(clientNum)
		if connection is not None:
			connection.closeConnection()

	def initialSetup(self, clientSocket):
		standby = self.standby
		currentConnectionCount = self.getNumConnections()
		if currentConnectionCount >= self.maxNumConnections and not standby:
			return None, None
		# Receive the client TCP socket address message
		initStr = self.getMessageInternal(clientSocket)
		try:
			initData = json.loads(initStr)
		except:
			print("Warning: New client failed initial setup.")
			return None, None

		if not (initData["type"] == "connect" and not standby) and not (initData["type"] == "reconnect" and standby):
			return None, None

		# Reply back with the current server time
		systemTime = time.time()
		timeObject = {
			# By flooring the systemTime, we are left with only the seconds portion of the time.
			"seconds": int(math.floor(systemTime)),
			# Convert the decimal portion of the time to microseconds. Round to the nearest microsecond.
			"microseconds": round(MICROSECONDS_IN_SECOND * (systemTime % 1)),
		}
		timeObjectStr = json.dumps(timeObject)
		success = self.sendMessageInternal(clientSocket, timeObjectStr)
		if success == False:
			return None, None

		# Return the address 
		return initData["identifier"], initData["candidateAddr"]		