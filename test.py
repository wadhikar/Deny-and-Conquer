import client 
import server
import sys
import time as time
import reconnect

# Check that the user provided at least one argument, the host address.
if len(sys.argv) < 4:
    print("Usage: python3 test.py serverAddr serverPort isServer")
    exit(1)

# Initialize the server port number to 0, which indicates that the kernel should assign a free port.
serverPort = 0
# If the user provided a second command line argument, then we will use that as the port number. 
if len(sys.argv) > 2:
	# Verify that the second argument (the port number) is a number, and convert it from string to integer.
	if str.isdigit(sys.argv[2]):
	    serverPort = int(sys.argv[2])
	else:
		# Argument invalid. Report and error and quit. 
	    print("Error: The second command line argument must be a valid port.")
	    exit(1)

# Store the server address provided as command line argument.
serverAddress = sys.argv[1]

isServer = sys.argv[3]
if isServer == "1":
	isServer = True
	serverPort2 = serverPort
	print("we are server...")
else:
	isServer = False
	serverPort2 = 0

# Create the server.
server = server.Server(4)
standby = not isServer
# Initialize the server with the provided IP address and port number.
serverAddr2, serverPort2 = server.initServer(serverAddress, serverPort2, standby=standby)
# Start the server so that it can accept connections and process requests.
server.start()

client = client.Client()
con, identifier = client.connect(serverAddress, serverPort)
print(identifier)
if not con:
	print("exiting...")
	server.setShutdown()
	client.setShutdown()
	exit(1)
client.start()
client.setCandidate(serverAddr2, serverPort2)

allTheClients = []
while True:
	time.sleep(0.1)
	if not client.receivingQueue.empty():
		msg = client.receivingQueue.get()
		print("client says:", msg )
		if msg["type"] == "reconnect":
			client.setShutdown()
			print("going into reconnect...", msg["candidates"], identifier)
			client, startOurServer = reconnect.reconnect(msg["candidates"], identifier, [serverAddr2, serverPort2])
			if client == None:
				print("Reconnect failed?")
				server.setShutdown()
				exit(1)
			else:
				if startOurServer:
					print("WEEEEEE START OUR SERVER NOW!??!!")
					print("Lets get these guys INNNN", allTheClients)	
					server.startReplacementServer(msg["candidates"], allTheClients)
		if "identifier" in msg:
			allTheClients.append(msg["identifier"])
	msg = server.getMessage()
	if msg is not None:
		print("server says:", msg)
		if msg["type"] == "disconnect":
			server.removeClient(msg["clientNum"])
		elif msg["type"] == "connect":
			message = {
				"identifier": msg["identifier"]
			}
			server.sendToAll(message)