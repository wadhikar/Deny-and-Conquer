import socket
import sys
import time as time
import json
import queue
import threading
import math
from threading import Thread
MICROSECONDS_IN_SECOND = 1000000

# This class implements the Client object. 
class Client(threading.Thread):
	def __init__(self):
		threading.Thread.__init__(self)

		# Maximum number of bytes to receive at a time from the socket.
		self.maxDataReceived = 1024

		# Client socket that connects to the server.
		self.clientSocket = None

		# Time offset from the server time.		
		self.timeOffsetSec = 0
		self.timeOffsetMicro = 0

		# Candidates list, list of servers to connect to if the current server goes down.
		self.candidatesLock = threading.Lock()
		self.candidates = None
		
		# The client number we are on the server.
		self.clientNum = None

		# The sending queue is processed by the sending thread, which sends messages
		# to the server in order of insertion. It should only contain strings. 
		self.sendingQueue = queue.Queue()

		# The receiving queue is how the user of the client will access
		# messages from the server. It should only contain dictionaries (json objects.)
		self.receivingQueue = queue.Queue()

		# If this is set to true, all threads will be signalled to shutdown gracefully. 
		self.shutdown = False
		self.shutdownLock = threading.Lock()

		# This lock is used to ensure the client socket is not closed while in the middle of sending
		# a message.
		self.sendLock = threading.Lock()

		# This variable stores the address of the server that this client is offering as a 
		# leadership candidate. 
		self.setCandidateLock = threading.Lock()
		self.candidateAddr = None

	# Alert all threads that they should shutdown gracefully. 
	def setShutdown(self):
		self.shutdownLock.acquire()
		self.shutdown = True
		self.shutdownLock.release()

	# Check if threads should shutdown. 
	def getShutdown(self):
		self.shutdownLock.acquire()
		shutdown = self.shutdown
		self.shutdownLock.release()
		return shutdown

	# Attempts to connect to the server specified by serverAddr and serverPort.
	# If originalIp and originalPort are provided, they will be used as the clients "identity", and
	# the client will tell the server that this a "reconnect." If not provided, it is assumed that this
	# is a normal initial connect, and the clients IP address and port will be used as it's identity.
	# candidateAttr is only processed by the server on a reconnect, and is used to reconstruct the candidates
	# list after a server goes down.
	def connect(self, serverAddr, serverPort, originalIp=None, originalPort=None, candidateAddr=None):
		# Create the TCP socket.
		self.clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.clientSocket.settimeout(4)
		try:
			# Connect to the server specified.
			self.clientSocket.connect((serverAddr, serverPort))
		except Exception as e:
			print("Could not connect to specified server, with IP address", serverAddr, "and port", serverPort, ".")
			print(str(e))
			# Return false to indicate failure to connect to the server. 
			return False, None
		

		# If either the original IP or original port number is not provided, then we treat this as a new connection.
		if originalIp is None or originalPort is None:
			connectionType = "connect"
			# Get the connection details to use as a unique identity. 
			self.ipAddr = self.clientSocket.getsockname()[0]
			self.port = self.clientSocket.getsockname()[1]
		else:
			# If an original IP address and port number were provided, this is a reconnect.
			# We use the previous connection details to let the new server know our previous identify.
			connectionType = "reconnect"
			self.ipAddr = originalIp
			self.port = originalPort
		# If the connection was established then we send some initial data to the server.
		# The server needs to know our identity, if this is a reconnect or connect attempt,
		# and if we are currently hosting a server replacement candidate. 
		message = {
			"identifier": (self.ipAddr, self.port),
			"type": connectionType,
			"candidateAddr": candidateAddr
		}
		message = json.dumps(message)
		# The server should respond back with its current system time, which allows us to calculate the offset
		# from our own clock. This allows the client to synchronize its time with the server without having to 
		# change its own system time. 
		beforeTime = time.time()
		self.sendMessageInternal(self.clientSocket, message)
		serverTime = self.getMessageInternal(self.clientSocket)
		afterTime = time.time()

		# Try to convert the server response to a JSON object (dictionary) 
		try:
			serverTime = json.loads(serverTime)
		except:
			print("Expected server to respond with system time, but instead got:", serverTime)
			return False, None

		# Estimate one-way delay between the server and the client, for more accurate time synchronization. 
		secondDelay, usecDelay = self.estimateOneWayDelay(beforeTime, afterTime)
		# Add the one way delay to the time recieved by the server.
		serverSeconds = serverTime["seconds"] + secondDelay
		serverMicroseconds = serverTime["microseconds"] + usecDelay
		# Normalize the time to account for overflow or underflow in the microseconds portion. 
		serverSeconds, serverMicroseconds = self.normalizeTime(serverSeconds, serverMicroseconds)

		# Calculate the offset from the server system time. 
		self.timeOffsetSec = serverSeconds - int(math.floor(afterTime))
		self.timeOffsetMicro = serverMicroseconds - round(MICROSECONDS_IN_SECOND * (afterTime % 1))

		# Get the current candidates list from the server, so we know who to try and connect to if the server
		# goes down. 
		candidates = self.getMessageInternal(self.clientSocket)
		try:
			candidates = json.loads(candidates)
		except:
			print("Expected server to respond with server replacement candidates, but instead got:", candidates)
			return False, None

		# Verify that the message received is a config type message.
		if "type" not in candidates or candidates["type"] != "config":
			print("Expected config type message, but instead got:", candidates)
			return False, None

		# Record the client number that we were assigned by the server. 
		self.clientNum = candidates["clientNum"]
		# Record the server replacement candidates list the server sent over. 
		self.candidates = candidates["candidates"]

		# For debugging purpose:
		print("Initial candidate list:", self.candidates)

		# Successful connection, return True and the unique identity for this connection (IP address and port, as a pair).
		return True, [self.ipAddr, self.port]

	# This is the main entry point for running the client.
	def run(self):
		# Start the sending thread, which stores messages destined for the server. 
		sendThread = Thread(target=self.sendingThread)
		sendThread.start()
		# Start the receiving thread, which stores messages received from the server.
		receivingThread = Thread(target=self.receivingThread)
		receivingThread.start()
 
 		# Loop for the lifetime of the connection.
		while True:
			# Send a heartbeat once a second to prevent the sockets from timing out.
			heartbeat = {
				"type": "heartbeat"
			}
			self.sendMessage(heartbeat)

			# Check if we should end the thread.
			if self.getShutdown():
				break

			# Sleep to prevent flooding the network with heartbeat messages.
			time.sleep(1)

		# Set shutdown to true to make sure all other threads know to shutdown. 
		self.setShutdown()
		
		# Send None to the sending queue since the sending thread blocks if the queue is empty.
		# This will allow it to check the shutdown variable and exit gracefully. 
		self.sendingQueue.put(None)
		
		# Wait for the other threads to end.
		sendThread.join()
		receivingThread.join()
	
		# All client threads are now shutdown. 
		print("Client has now shutdown.")

	# This thread processes messages from the sending queue and sends them to the server. 
	def sendingThread(self):
		while True:
			# Get next message that should be sent. 
			messageToSend = self.sendingQueue.get()
			# Check if the thread should shutdown. 
			if messageToSend == None or self.getShutdown():
				break
			# Acquire the sending lock, preventing the socket from being closed in the middle of 
			# sending. 
			self.sendLock.acquire()
			# Verify that the client socket has not already been closed. 
			if self.clientSocket is not None:
				# Send the message to the server.
				self.sendMessageInternal(self.clientSocket, messageToSend)
			# Release the lock. 
			self.sendLock.release()

	# This thread handles receiving and processing messages from the server. 
	def receivingThread(self):
		while True:
			# Get new message from server.
			message = self.getMessageInternal(self.clientSocket)
			
			# Check if the thread should shutdown gracefully.
			if self.getShutdown():
				# Acquire the send lock so that the socket is not shutdown mid way through sending. 
				self.sendLock.acquire()
				# Close the client socket. 
				self.clientSocket.close()
				self.clientSocket = None
				# Release the send lock. 
				self.sendLock.release()
				# Break out of the loop (and out of the thread)
				break

			# Disconnected from the server. Attempt to reconnect to a new server to continue on the game.
			if message == "" or message == None:
				print("giong to recon: ", message)
				# Acquire the send lock so that the socket is not shutdown mid way through sending. 
				self.sendLock.acquire()
				# Close the client socket. 
				self.clientSocket.close()
				self.clientSocket = None
				# Release the send lock. 
				self.sendLock.release()
				
				# For Debugging.
				print("Server going down, returning list of candidates for reconnection.")

				# Acquire the candidates lock, as candidates is a variable shared between threads.
				self.candidatesLock.acquire()
				# Send a message to the user (game server) that connection was lost and they should attempt to 
				# reconnect to a new server to continue the game. Also provide a list of candidate replacement servers
				# to try and connect to. 
				message = {
					"type": "reconnect",
					"candidates": self.candidates
				}
				# Release the lock.
				self.candidatesLock.release()
				# Add message to the queue.
				self.receivingQueue.put(message)
				# Indicate to all other threads that they should shutdown gracefully. 
				self.setShutdown()
				# Break out of the loop (and out of the thread)
				break
			
			# Convert the message to JSON (dictionary)
			try:
				message = json.loads(message)
			except:
				continue

			# If the message is a heartbeat, just drop it. The only purpose is to 
			# ensure the socket doesnt time out, no processing needs to be done. 
			if message["type"] == "heartbeat":
				continue

			# Handle modifications to the replacement server candidate list. 
			if message["type"] == "addCandidate":
				# If the server reports a new candidate has been registered, add it to the candidates list.
				self.candidatesLock.acquire()
				self.candidates.append((message["address"]))
				self.candidatesLock.release()
				continue
			elif message["type"] == "removeCandidate":
				# If the server indicates that a previous candidate has left, remove them from the candidate list
				# if they are currently part of it. 
				self.candidatesLock.acquire()
				if message["address"] in self.candidates:
					self.candidates.remove(message["address"])
				self.candidatesLock.release()
				continue
			elif message["type"] == "config":
				# Note we should only receive config messages once per reconnection.
				# The config type messages let us know what client number we were assigned on the server, 
				# and the current valid replacement server candidate list. 
				self.candidatesLock.acquire()
				self.candidates = message["candidates"]
				self.clientNum = message["clientNum"]
				# For debugging.
				print("Reconfigured, got assigned the following client number:", self.clientNum)
				print("Got the new candidates list:", self.candidates)
				# This lock is specifically for the self.candidateAddr variable.
				self.setCandidateLock.acquire()
				# If we previously flagged ourselves as a server replacement candidate to the old server, but the 
				# new server does not have record of this, unset our candidacy. We will have to reannounce our candidacy 
				# to the new server so that it can be redistributed amongst all connected clients. 
				if self.candidateAddr not in message["candidates"] and self.candidateAddr is not None:
					self.candidateAddr = None
				# Unlock the locks we acquired.
				self.setCandidateLock.release()
				self.candidatesLock.release()

			# Insert the message into the receiving queue, so it can be processed by the game logic.
			self.receivingQueue.put(message)

	# This is a threadsafe function that allows the client to send a message to the server, indicating that it
	# can become a candidate for server replacement, in the case that the current server goes down.
	def setCandidate(self, serverAddr, serverPort):
		if serverAddr == "localhost" or serverAddr == "0.0.0.0" or serverAddr == "127.0.0.1":
			return
		# Acquire a lock since self.candidateAddr is shared between threads.
		self.setCandidateLock.acquire()
		# If we are already a candidate, no need to tell the server again.
		if self.candidateAddr == None:
			# Set the candidateAddr variable.
			self.candidateAddr = [serverAddr, serverPort]
			# Send a message to the server, offering this client as a server replacement candidate. 
			message = {
				"type": "isCandidate",
				"candidateAddr": self.candidateAddr
			}
			message = json.dumps(message)
			self.sendingQueue.put(message)
		# Release the lock.
		self.setCandidateLock.release()

	# This function takes in a JSON (dictionary) message and adds it to the sending queue.
	# It also handles adding a timestamp, to allow for coordination between the server and client. 
	def sendMessage(self, message):
		# First get the clients current system time.
		systemTime = time.time()
		# Account for the offset compared to the server system time, so that the timestamp represents
		# the current time on the server.
		systemSeconds = int(math.floor(systemTime)) + self.timeOffsetSec
		systemMicroseconds = round(MICROSECONDS_IN_SECOND * (systemTime % 1)) + self.timeOffsetMicro
		systemSeconds, systemMicroseconds = self.normalizeTime(systemSeconds, systemMicroseconds)
		systemMicrosecondsStr = str(systemMicroseconds) 

		# Make sure that the microseconds portion has the correct decimal places
		# in the timestamp string. Add leading zeros if necessary.
		while len(systemMicrosecondsStr) < (len(str(MICROSECONDS_IN_SECOND)) -1):
			systemMicrosecondsStr = "0" + systemMicrosecondsStr
		adjustedTime = str(systemSeconds) + "." + systemMicrosecondsStr

		# Convert the timestamp string to a float, and add it to the message in the timestamp field.
		message["timestamp"] = float(adjustedTime)
		
		# If there is no type for this message, add the type "default".
		if "type" not in message:
			message["type"] = "default"

		# Convert the message into a JSON formatted string.
		message = json.dumps(message)

		# Add the message to the sending queue, to be sent to the server.
		self.sendingQueue.put(message)

	# This function sends a message over clientSocket. It adds a header (the total message size)
	# so that the receiver knows how many bytes to receive. 
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
			#print("Error: Failed to send message to client. Error details:", str(e))
			return False

	# This function waits to receive a message over the clientSocket. It first gets the message header to find out
	# how many bytes the message will be, and then waits to receive that amount of bytes. 
	def getMessageInternal(self, clientSocket):
		# Get size of message.
		messageSize = self.getMessageSize(clientSocket)
		# Invalid size, return None to indicate failure to get message.
		if messageSize == None:
			return None
		else:
			# Keep receiving more bytes until the number of bytes received equals the expected number of bytes. 
			# We store the partial message in a buffer as we receive data. 
			message = b""
			while len(message) < messageSize:
				# Determine how many more bytes we need for this message.
				remainingChars = messageSize - len(message)
				# Receive more data from the socket. 
				receivedData = self.receiveData(clientSocket, remainingChars)
				# If received data is None, an error occured. Return None to indicate an error. 
				if receivedData == None:
					return None
				elif receivedData == b"":
					# If received data is an empty string, it means the server has terminated the connection. 
					# Return an empty string to indicate connection has been terminated.
					return ""
				else:
					# Add the received bytes to the buffer, which will eventually contain the entire message.
					message += receivedData
					
			# Convert the received message to a string, and return it. 
			return str(message, "utf-8")

	def getMessageSize(self, clientSocket):
		messageSizeStrSize = 10
		messageSizeStr = b""
		while len(messageSizeStr) < messageSizeStrSize:
			remainingChars = messageSizeStrSize - len(messageSizeStr)
			receivedData = self.receiveData(clientSocket, remainingChars)
			if receivedData == None:
				return None
			elif receivedData == b"":
				return 0
			else:
				messageSizeStr += receivedData

		messageSizeStr = str(messageSizeStr, "utf-8")
		if str.isdigit(messageSizeStr):
			return int(messageSizeStr)
		else:
			print("error with the message for size!!!", messageSizeStr)
			return 0

	def receiveData(self, clientSocket, dataToReceive):
		try:
			receivedData = clientSocket.recv(min(self.maxDataReceived, dataToReceive))
		except socket.timeout:
			print(">>>>>>>>>>>>>>>>>>TIMEDOUT")
			return b""
		except Exception as e:
			print(">>>>>>>>>>>>>>>>>>erorr with receive...", str(e))
			return None 
		if receivedData == b"":
			print(">>>>>>>>>>>>>>>>>>.The server has disconnected us it seems....")
		return receivedData

	# This function handles overflow in the microseconds portion. 
	# Overflow in this case means that the microseconds value is greater than 1 second.
	def normalizeTime(self, seconds, microseconds):
		# If the microseconds portion of the provided time is greater than a second, add the overflow time to the 
		# seconds portion and reduce the microseconds portion to less than a second. 
		if microseconds >= MICROSECONDS_IN_SECOND:
			seconds = seconds + math.floor(microseconds / MICROSECONDS_IN_SECOND)
			microseconds = microseconds % MICROSECONDS_IN_SECOND
		elif microseconds < 0:
			seconds = seconds - math.ceil(-microseconds / MICROSECONDS_IN_SECOND)
			microseconds = microseconds + (math.ceil(-microseconds / MICROSECONDS_IN_SECOND) * MICROSECONDS_IN_SECOND)

		# Return the new time values.
		return seconds, microseconds


	# Calculates the RTT between the two provided times, and from there, estimates the one-way delay.
	def estimateOneWayDelay(self, timeBefore, timeAfter):
		# This section calculates the RTT time by subtracting the before time from the after time.
		# We handle the seconds portion and microseconds portion separately so that we can do integer subtraction.
		# This prevents any rounding errors that may occur when subtracting two floats. 

		# Subtract the seconds portion and microseconds portions separately to find the difference.
		secRtt = math.floor(timeAfter) - math.floor(timeBefore)
		usecRtt = round(MICROSECONDS_IN_SECOND * (timeAfter % 1)) - \
				  round(MICROSECONDS_IN_SECOND * (timeBefore % 1))
		# If the microseconds portion is now negative, we remove a second from the seconds portion and add
		# the equivilent worth of microseconds to the microsecond portion. 
		if usecRtt < 0:
			usecRtt = usecRtt + MICROSECONDS_IN_SECOND
			secRtt = secRtt - 1

		# This section calculates the one-way delay from the server to the client. 
		# We estimate this as simply half of the RTT.
		secOneWayDelay = math.floor(secRtt / 2)
		usecOneWayDelay = math.floor(usecRtt / 2)
		# If the seconds portion was odd, add half of a second to the microseconds portion of the delay.
		if secRtt % 2 == 1:
			usecOneWayDelay = int(usecOneWayDelay + (MICROSECONDS_IN_SECOND / 2))

		# Move any overflow in the microseconds portion to the seconds portion.
		secOneWayDelay, usecOneWayDelay = self.normalizeTime(secOneWayDelay, usecOneWayDelay)

		# Return the new time values.
		return secOneWayDelay, usecOneWayDelay