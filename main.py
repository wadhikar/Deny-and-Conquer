import game
import gameBoard
from multiprocessing import Process,Queue
import json
import ui_pygame
import time
import sys
import bitmap
import server
# import queue
import client
import reconnect
import copy
# import quntinNetworking

def parseUpdate(string):
	removedLastChar = string[:-1]
	updates = removedLastChar.split("$")
	#if updates == ['']:
	#	return []
	updates = [tuple(map(int, i.split(","))) for i in updates]
	return updates

def validatePreviousLock(gameObject, sender):
	updatesToSend = ""
	previouslyLocked = gameObject.players[sender].lockedSquare
	if previouslyLocked == None:
		return None
	square = gameObject.gameBoard.getSquare(previouslyLocked[0], previouslyLocked[1])
	if square.locked == sender:
		if square.canBeCaptured(gameObject.threshold):
			square.captureSquare(sender, gameObject.players[sender].color)
			updatesToSend += "{0},{1},{2},{3}$".format(previouslyLocked[0], previouslyLocked[1], -2, -2) # Set all bits to 1
		else:
			square.resetSquare(copy.deepcopy(gameObject.gameBoard.emptyBitmap))
			updatesToSend += "{0},{1},{2},{3}$".format(previouslyLocked[0], previouslyLocked[1], -1, -1) # Set all bits to 0
		square.unlockSquare()

	if len(updatesToSend) != 0:
		return updatesToSend
	else:
		return None

def redrawSquares(gameObject):
	print("IN REDRAW")
	for row in range(len(gameObject.gameBoard.gameBoardMatrix)):
		for col in range(len(gameObject.gameBoard.gameBoardMatrix[row])):
			gameObject.gameUI.setSquare((col, row), (255, 255, 255))

	for row in range(len(gameObject.gameBoard.gameBoardMatrix)):
		for col in range(len(gameObject.gameBoard.gameBoardMatrix[row])):
			if gameObject.gameBoard.gameBoardMatrix[row][col].owned is not None:
				print("should be setting this thing....", gameObject.gameBoard.gameBoardMatrix[row][col].owned,gameObject.gameBoard.gameBoardMatrix[row][col].color,gameObject.gameBoard.gameBoardMatrix[row][col].locked)
				gameObject.gameUI.setSquare((col, row), gameObject.colorDict[gameObject.gameBoard.gameBoardMatrix[row][col].color])

	for row in range(len(gameObject.gameBoard.gameBoardMatrix)):
		for col in range(len(gameObject.gameBoard.gameBoardMatrix[row])):
			if gameObject.gameBoard.gameBoardMatrix[row][col].locked is not None:
				color = gameObject.colorDict[gameObject.gameBoard.gameBoardMatrix[row][col].color]
				print("bitmap here...", gameObject.gameBoard.gameBoardMatrix[row][col].bitmap.bitmap)
				for bitRow in range(len(gameObject.gameBoard.gameBoardMatrix[row][col].bitmap.bitmap)):
					for bitCol in range(len(gameObject.gameBoard.gameBoardMatrix[row][col].bitmap.bitmap[bitRow])):
						print("drawing at", bitRow*5, bitCol*5)
						if gameObject.gameBoard.gameBoardMatrix[row][col].bitmap.bitmap[bitRow][bitCol] == 1:
							gameObject.gameUI.drawChanges(color, (col, row, bitCol*5, bitRow*5))


def convertGameBoard(gameBoardMatrix):
	gameBoardDict = {}
	for row in range(len(gameBoardMatrix)):
		for col in range(len(gameBoardMatrix[row])):
			gameBoardDict["{0},{1}".format(row, col)] = (gameBoardMatrix[row][col].locked, gameBoardMatrix[row][col].owned, gameBoardMatrix[row][col].color, gameBoardMatrix[row][col].bitmap.bitmap)
	return gameBoardDict

def reconvertGameBoard(currentGameObject, gameBoardDict):
	for row in gameBoardDict.keys():
		y, x = row.split(",")
		y = int(y)
		x = int(x)
		# print("RECONVERT, ",gameBoardDict[row][1])
		currentGameObject.gameBoard.gameBoardMatrix[y][x].locked = tuple(gameBoardDict[row][0]) if gameBoardDict[row][0] is not None else None
		print("owned??",x,y, gameBoardDict[row][1])
		currentGameObject.gameBoard.gameBoardMatrix[y][x].owned = tuple(gameBoardDict[row][1]) if gameBoardDict[row][1] is not None else None
		# if gameBoardDict[row][1] is not None:
			# print("x, y, owned by.", x, y, gameBoardDict[row][1])
		currentGameObject.gameBoard.gameBoardMatrix[y][x].color = gameBoardDict[row][2]
		currentGameObject.gameBoard.gameBoardMatrix[y][x].bitmap.bitmap = gameBoardDict[row][3]

def serverProcessor(allGameInfo, clientQueue, serverQueue):
	gameObject = game.Game()
	standbyMode = True
	if allGameInfo["isServer"] == True:
		gameObject.createGameboard(allGameInfo["boardSize"], allGameInfo["penSize"], allGameInfo["squarePixelWidth"], allGameInfo["percentage"])
		standbyMode = False

	networkServer = server.Server(4)
	serverAddr, serverPort = networkServer.initServer(standby=standbyMode)
	networkServer.start()
	serverQueue.put((serverAddr, serverPort))

	started = False

	if not allGameInfo["isServer"]:
		message = clientQueue.get()
		if message is not None and "type" in message and message["type"] == "startServer":
			candidates = message["candidates"]
			expectedClients = message["clients"]
			print("We should be starting our backup serve now with the following:", candidates, expectedClients)
		else:
			networkServer.setShutdown()
			exit(1) 
		reconnectedClients = networkServer.startReplacementServer(candidates, expectedClients)
		allGameInfo = clientQueue.get()
		gameObject.createGameboard(allGameInfo["boardSize"], allGameInfo["penSize"], allGameInfo["squarePixelWidth"], allGameInfo["percentage"])
		newPlayers = []
		for player in allGameInfo["currentPlayersConnected"]:
			newPlayers.append(tuple([tuple(player[0]), player[1]]))
		gameObject.connectedPlayers = newPlayers
		print("CONNECTED PLAYERS ARE TUPLES?", gameObject.connectedPlayers)
		reconvertGameBoard(gameObject, allGameInfo["currentGameBoard"])
		oldPlayers = []
		print("RECONNECTED CLIENTS:", reconnectedClients)
		for player in gameObject.connectedPlayers:
			if tuple(player[0]) not in reconnectedClients:
				oldPlayers.append(tuple(player[0]))
		for playerID in oldPlayers:
			print("removing things by", playerID)
			print(gameObject.gameBoard.resetPlayerSquares(playerID))
			gameObject.removePlayer(playerID)
		started = allGameInfo["started"]
		gameObject.initializePlayers()
		gameObject.checkCurrentLocks()
		updateJson = {
			"type": "settings",
			"boardSize": allGameInfo["boardSize"],
			"penSize": allGameInfo["penSize"],
			"squarePixelWidth": allGameInfo["squarePixelWidth"],
			"percentage": allGameInfo["percentage"],
			"currentGameBoard": convertGameBoard(gameObject.gameBoard.gameBoardMatrix),
			"currentPlayersConnected": gameObject.connectedPlayers, #list of tuples (playerID, color)
			"reconnect": True,
			"started": started
		}
		networkServer.sendToAll(updateJson)

	# penDown = set()
	startTime = time.time()
	while True: # Probably should change to while game not over
		if not clientQueue.empty():
			message = clientQueue.get()
			if message is None or "type" in message and message["type"] == "shutdownServer":
				networkServer.setShutdown()
				print("exit?")
				exit(1) 

		event = networkServer.getMessage()
		if event is not None:
			print("got message on server:", event)
		if (time.time() - startTime > 2) and not started:
			started = True
			startGame = {
				"type": "start",
			}
			gameObject.initializePlayers()
			networkServer.sendToAll(startGame)
			print("Force start")
		winners = gameObject.gameBoard.checkWinner()
		winnersList = []
		if winners is not None:
			for winner in winners:
				if winner == 1:
					winnersList.append("Red")
				if winner == 2:
					winnersList.append("Blue")
				if winner == 3:
					winnersList.append("Green")
				if winner == 4:
					winnersList.append("Orange")
			winnersStr = ", ".join(winnersList)
			message = {
				"type": "won",
				"winner": winnersStr
			}
			networkServer.sendToAll(message)
			time.sleep(3)
			networkServer.setShutdown()
			time.sleep(3)
			exit(1)

		if event == None:
			time.sleep(0.1)
			continue 
		elif event["type"] == "connect":
			updateJson = {
				"type": "settings",
				"boardSize": allGameInfo["boardSize"],
				"penSize": allGameInfo["penSize"],
				"squarePixelWidth": allGameInfo["squarePixelWidth"],
				"percentage": allGameInfo["percentage"],
				"currentGameBoard": convertGameBoard(gameObject.gameBoard.gameBoardMatrix),
				"currentPlayersConnected": gameObject.connectedPlayers,
				"started": started
			}
			networkServer.sendMessage(updateJson, event["clientNum"])
			# Update the game info
			assignedColor = gameObject.assignColor()
			gameObject.addConnectedPlayer(tuple(event["identifier"]), assignedColor)
			gameObject.initializePlayer(tuple(event["identifier"]), assignedColor)
			gameObject.numOfPlayers += 1
			if not started:
				if gameObject.numOfPlayers == 4:
					started = True
					startGame = {
						"type": "start",
					}
					#gameObject.initializePlayers() TODO REMOVE THIS I THINK.....
					networkServer.sendToAll(startGame)
			# Send message to all about new connection including the one who joined.  
			newJoinedPlayer = {
				"type": "joined",
				"playerID": tuple(event["identifier"]),
				"color": assignedColor,
			}
			networkServer.sendToAll(newJoinedPlayer)
		elif event["type"] == "disconnect":
			gameObject.numOfPlayers -= 1
			# Remove all squares they held
			gameObject.gameBoard.resetPlayerSquares(tuple(event["identifier"]))
			gameObject.removePlayer(tuple(event["identifier"]))
			networkServer.removeClient(event["clientNum"])

			# Send to all that they left now. 
			playerLeft = {
				"type": "left",
				"playerID": tuple(event["identifier"])
			}
			networkServer.sendToAll(playerLeft)
		elif event["type"] == "penDown" and started:
			# penDown.add(event["sender"])
			gameObject.players[tuple(event["identifier"])].penDown = True
			clickedSquares = parseUpdate(event["lockAttempt"]) # Make this an (xSquare, ySquare) tuple
			updatesToSend = ""

			for clickedSquare in clickedSquares:
				square = gameObject.gameBoard.getSquare(clickedSquare[0], clickedSquare[1])
				currentlyLocked = gameObject.players[tuple(event["identifier"])].lockedSquare
				if currentlyLocked != None:
					print("currently not None...")
					if currentlyLocked[0] != clickedSquare[0] or currentlyLocked[1] != clickedSquare[1]:
						updatesToSend += validatePreviousLock(gameObject, tuple(event["identifier"]))
						print("We shall unlcok em... ")
						gameObject.players[tuple(event["identifier"])].lockedSquare = None

				if square.owned == None:
					if square.locked == None:
						square.lockSquare(tuple(event["identifier"]))
						square.color = gameObject.players[tuple(event["identifier"])].color
						gameObject.players[tuple(event["identifier"])].lockedSquare = (clickedSquare[0], clickedSquare[1])

				if updatesToSend != "":
					updateJson = {
						"type": "draw",
						"boardUpdates": updatesToSend,
						"color": gameObject.players[tuple(event["identifier"])].color
					}
					networkServer.sendToAll(updateJson)
		elif event["type"] == "penUp" and started:
			# penDown.remove(event["sender"])
			gameObject.players[tuple(event["identifier"])].penDown = False
			updatesToSend = validatePreviousLock(gameObject, tuple(event["identifier"]))
			gameObject.players[tuple(event["identifier"])].lockedSquare = None

			if updatesToSend != None:
				updateJson = {
					"type": "draw",
					"boardUpdates": updatesToSend,
					"color": gameObject.players[tuple(event["identifier"])].color
				}
				networkServer.sendToAll(updateJson)
		elif event["type"] == "draw" and started:
			if gameObject.players[tuple(event["identifier"])].penDown == True:
				updatesToSend = ""
				updates = parseUpdate(event["boardUpdates"])
				for update in updates:
					currentlyLocked = gameObject.players[tuple(event["identifier"])].lockedSquare
					if currentlyLocked != None:
						if update[0] == currentlyLocked[0] and update[1] == currentlyLocked[1]:
							square = gameObject.gameBoard.getSquare(update[0], update[1])				
							if square.locked == tuple(event["identifier"]):
								xPixel, yPixel = gameObject.gameBoard.getSquare(update[0], update[1]).bitmap.setBits(update[2], update[3], gameObject.penSize)
								if xPixel != None:
									updatesToSend += "{0},{1},{2},{3}$".format(update[0], update[1], xPixel, yPixel)
						else:
							updatesToSend += validatePreviousLock(gameObject, tuple(event["identifier"]))
							gameObject.players[tuple(event["identifier"])].lockedSquare = None

				if updatesToSend != "":
					updateJson = {
						"type": "draw",
						"boardUpdates": updatesToSend,
						"color": gameObject.players[tuple(event["identifier"])].color
					}
					networkServer.sendToAll(updateJson)

def createUpdate(inputEvent): # Probably need to include quintin's server object in params too
	# Need some kind of event for settings. Something like ('s', {'boardSize': <value>, 'penSize': <value>, ...}) ?
	updatesToSend = ""
	if inputEvent[0] == 'm':
		updatesToSend += "{0},{1},{2},{3}$".format(inputEvent[1][0], inputEvent[1][1], inputEvent[1][2], inputEvent[1][3])
	elif inputEvent[0] == 'l':
		updatesToSend += "{0},{1}$".format(inputEvent[1][0], inputEvent[1][1])

	return updatesToSend

def getAllFromInputQueue(q):
	sizeOfQueue = q.qsize()
	allInput = []
	for i in range(sizeOfQueue):
		allInput.append(q.get())

	return allInput

def processEvent(clientObject, event, updateToSend, clientQueue):
	if event != 'u' and event != 'q' and updatesToSend == "":
		return

	if event == 'm':
		updateJson = {
			"type": "draw",
			"boardUpdates": updatesToSend
		}
		clientObject.sendMessage(updateJson)
	elif event == 'l':
		updateJson = {
			"type": "penDown",
			"lockAttempt": updatesToSend
		}
		clientObject.sendMessage(updateJson)
	elif event == 'u':
		updateJson = {
			"type": "penUp"
		}
		clientObject.sendMessage(updateJson)
	elif event == 'q':
		print("Killing process....")
		clientObject.setShutdown()
		clientQueue.put(None)
		sys.exit() # Temporary

def interpolateClick(x0_pixel, y0_pixel, x1_pixel, y1_pixel):
	# returns list of (xPixel, yPixel) tuples inclusive of given pixels

	coordinates = []
	deltaX = abs(x1_pixel - x0_pixel)
	deltaY = abs(y1_pixel - y0_pixel)
	slopeX = 1 if (x0_pixel < x1_pixel) else -1
	slopeY = 1 if (y0_pixel < y1_pixel) else -1
	error = deltaX - deltaY

	coordinates.append((x0_pixel, y0_pixel))

	while True:
		if (x0_pixel == x1_pixel) and (y0_pixel == y1_pixel):
			break
		
		error2 = 2 * error
		if error2 > -deltaY:
			error -= deltaY
			x0_pixel += slopeX
		if error2 < deltaX:
			error += deltaX
			y0_pixel += slopeY
		
		coordinates.append((x0_pixel, y0_pixel))

	return coordinates

# Main process for client

# gameLogicServer = Process(target=serverProcessor())
# gameLogicServer.start()

gameObject = game.Game()
gameObject.initializeGameUI()
gameObject.startSettingsPrompt()

boardSetUp = False
startGame = False
connected = False
# testJson = {"type": "draw", "boardUpdates": "2,2,-2,-2$"}
# testJson = json.dumps(testJson)
# qQueue = [testJson]
# gameObject.createGameboard(5, 0, 118, 50) # Debug
# penSize = 1
# gameObject.startGameUI(5, penSize) # Debug
# time.sleep(1) # Necessary for loading the board display
# # gameObject.initializePlayers()

filledBitmap = bitmap.Bitmap(118,118)
filledBitmap.setAll()

serverAddr = None
serverPort = None
currServerAddr = None
currServerPort = None

clientQueue = Queue()
serverQueue = Queue()

clientObject = client.Client()

bufferedSqr = None
while True:
	inputInfo = getAllFromInputQueue(gameObject.gameUI.outgoing_queue)
	if len(inputInfo) != 0:
		# print("IN THIS LOOP")
		currentEvent = inputInfo[0][0]
		updatesToSend = ""
		retry = False
		for inputEvent in inputInfo:
			if inputEvent[0] == 's': # This even should only be received once per user.
				# Start the server and/or connect to server here
				print("all to start", inputEvent[1])
				while not clientQueue.empty():
					clientQueue.get()
				while not serverQueue.empty():
					serverQueue.get()

				gameLogicServer = Process(target=serverProcessor, args=(inputEvent[1], clientQueue, serverQueue))
				gameLogicServer.start()

				serverAddr, serverPort = serverQueue.get()
				
				if inputEvent[1]["isServer"] == False:
					print("trying to connect here: ", inputEvent[1]["ip"], inputEvent[1]["port"])
					conn, identifier = clientObject.connect(inputEvent[1]["ip"], inputEvent[1]["port"])
					currServerAddr = inputEvent[1]["ip"]
					currServerPort = inputEvent[1]["port"]
				else:
					currServerPort = serverPort
					conn, identifier = clientObject.connect(serverAddr, serverPort)
					currServerAddr = identifier[0] if identifier is not None else None

				if not conn:
					print("exiting...")
					clientObject.setShutdown()
					clientQueue.put(None)
					gameObject.gameUI.ui_alert_user("Error: Connection failed...", "Press ok to go back to the configuration menu.")
					restart = gameObject.gameUI.outgoing_queue.get()
					if restart[0] == 'r':
						clientObject = client.Client()
						gameObject.startSettingsPrompt()
						retry = True
					else:
						print("exit from here...")
						exit(1)
				else:
					identifier = tuple(identifier)
					serverAddr = identifier[0]
				if retry == True:
					break
				# gameObject.startGameUI(inputEvent[1]["boardSize"], inputEvent[1]["penSize"])
				clientObject.start()
				print(clientObject)
				connected = True
			if boardSetUp == True and startGame == True:
				if inputEvent[0] != currentEvent:
					processEvent(clientObject, currentEvent, updatesToSend, clientQueue)
					updatesToSend = ""
					currentEvent = inputEvent[0]
				#print(inputEvent) # Debug
				updatesToSend += createUpdate(inputEvent)
				if inputEvent[0] == "m" and bufferedSqr == (inputEvent[1][0], inputEvent[1][1]):
					xPixel, yPixel = gameObject.gameBoard.getSquare(inputEvent[1][0], inputEvent[1][1]).bitmap.setBits(inputEvent[1][2], inputEvent[1][3], gameObject.penSize)
					if xPixel != None:
						gameObject.gameUI.drawChanges(gameObject.colorDict[gameObject.players[tuple(identifier)].color], (inputEvent[1][0], inputEvent[1][1], xPixel, yPixel))
		if retry == True:
			continue
		processEvent(clientObject, currentEvent, updatesToSend, clientQueue)

	if connected == True:
		if not clientObject.receivingQueue.empty():
			serverEvent = clientObject.receivingQueue.get()
			print("got message on client:", serverEvent)
		else:
			time.sleep(0.1)
			continue

		if serverEvent["type"] == "settings":
			gameObject.createGameboard(serverEvent["boardSize"], serverEvent["penSize"], serverEvent["squarePixelWidth"], serverEvent["percentage"])
			print("you must see", serverEvent["squarePixelWidth"])
			reconvertGameBoard(gameObject, serverEvent["currentGameBoard"])
			gameObject.connectedPlayers = serverEvent["currentPlayersConnected"]
			gameObject.players = {}
			clientObject.setCandidate(serverAddr, serverPort)
			# On reconnect, we want to update rather than start. 
			if "reconnect" not in serverEvent:
				gameObject.startGameUI(serverEvent["boardSize"], serverEvent["penSize"]) # Need to include board size
			print("Redrawing these squares!!!")
			redrawSquares(gameObject)
			colorList = []
			for player in gameObject.players.keys():
				colorList.append(list((player[1], player == identifier)))
			gameObject.gameUI.displaySettings(currServerAddr, currServerPort, serverEvent["penSize"], serverEvent["percentage"], serverEvent["boardSize"], colorList) #TODO come and fix this Quintin 
			gameObject.initializePlayers()
			gameObject.checkCurrentLocks()
			gameObject.gameUI.displayLoading(False)
			if serverEvent["started"] == True:
				startGame = True
			else:
				gameObject.gameUI.displayMessage("Welcome to Deny and Conqour! The game will start when 4 players connect, or after 10 seconds have passed. Thanks for waiting!")
			time.sleep(1) # Necessary for loading the board display

			boardSetUp = True
		elif serverEvent["type"] == "joined":
			gameObject.addConnectedPlayer(tuple(serverEvent["playerID"]), serverEvent["color"])
			gameObject.initializePlayer(tuple(serverEvent["playerID"]), serverEvent["color"])
			for player in gameObject.players.keys():
				colorList.append(list((player[1], player == identifier)))
			gameObject.gameUI.displaySettings(currServerAddr, currServerPort, gameObject.penSize, gameObject.percentage, gameObject.boardSize, colorList)
		elif serverEvent["type"] == "left":
			resetSquares = gameObject.gameBoard.resetPlayerSquares(tuple(serverEvent["playerID"]))
			for player in gameObject.players.keys():
				colorList.append(list((player[1], player == identifier)))
			gameObject.gameUI.displaySettings(currServerAddr, currServerPort, gameObject.penSize, gameObject.percentage, gameObject.boardSize, colorList)
			for square in resetSquares:
				print("square to reset", square)
				gameObject.gameUI.setSquare((square[1], square[0]), (255, 255, 255))
			gameObject.removePlayer(tuple(serverEvent["playerID"]))
		elif serverEvent["type"] == "start":
			startGame = True
			gameObject.gameUI.displayMessage("")
		elif serverEvent["type"] == "reconnect":
			clientObject.setShutdown()
			gameObject.gameUI.displayLoading(True)
			clientObject, startOurServer, currServer = reconnect.reconnect(serverEvent["candidates"], tuple(identifier), [serverAddr, serverPort])
			if clientObject == None:
				gameObject.gameUI.killWindow()
				gameObject.gameUI.ui_alert_user("Error: Reconnection failed...", "Press ok to go back to the configuration menu.")
				restart = gameObject.gameUI.outgoing_queue.get()
				if restart[0] == 'r':
					print("trying again...")
					clientObject = client.Client()
					gameObject.startSettingsPrompt()
					continue
				else:
					print("exiting from HERE")
					clientQueue.put(None)
					exit(1)
			else:
				currServerAddr = currServer[0]
				currServerPort = currServer[1]
			if startOurServer == True:
				startServer = {
					"type": "startServer",
					"candidates": serverEvent["candidates"],
					"clients": list(gameObject.players.keys())
				}
				clientQueue.put(startServer)
				currentGameState = {
					"type": "gameState",
					"currentGameBoard": convertGameBoard(gameObject.gameBoard.gameBoardMatrix),
					"currentPlayersConnected": gameObject.connectedPlayers,
					"boardSize": gameObject.boardSize,
					"penSize": gameObject.penSize, 
					"squarePixelWidth": gameObject.squarePixelWidth, 
					"percentage": gameObject.percentage,
					"started": startGame
				}
				clientQueue.put(currentGameState)
		elif serverEvent["type"] == "draw":
			print(serverEvent)
			if boardSetUp == True:
				pixelsToColor = serverEvent["boardUpdates"]
				if pixelsToColor != "":
					pixelsToColor = parseUpdate(pixelsToColor)
					print("..",pixelsToColor)
				else:
					pixelsToColor = []
				for update in pixelsToColor:
					print(update)
					# print(update[0], update[1])
					if update[2] == -1 and update[3] == -1:
						gameObject.gameBoard.getSquare(update[0], update[1]).bitmap.reset()
						gameObject.gameBoard.getSquare(update[0], update[1]).updateColor(None)
						print("setting to white:",(update[0], update[1]) )
						gameObject.gameUI.setSquare((update[0], update[1]), (255, 255, 255))
						gameObject.gameBoard.getSquare(update[0], update[1]).owned = None
						gameObject.gameBoard.getSquare(update[0], update[1]).color = None
						gameObject.gameBoard.getSquare(update[0], update[1]).locked = None
						if bufferedSqr == (update[0], update[1]):
							bufferedSqr = None
					elif update[2] == -2 and update[3] == -2:
						gameObject.gameBoard.getSquare(update[0], update[1]).bitmap = filledBitmap
						gameObject.gameUI.setSquare((update[0], update[1]), gameObject.colorDict[serverEvent["color"]]) # color is temporary
						print("CLIENT DRAW: ", gameObject.playerColor(serverEvent["color"]))
						gameObject.gameBoard.getSquare(update[0], update[1]).owned = gameObject.playerColor(serverEvent["color"])
						gameObject.gameBoard.getSquare(update[0], update[1]).color = serverEvent["color"]
						gameObject.gameBoard.getSquare(update[0], update[1]).locked = None
						# gameObject.gameBoard.getSquare(update[0], update[1]).updateColor(gameObject.players[serverEvent["sender"]].color)
						if bufferedSqr == (update[0], update[1]):
							bufferedSqr = None
					else:
						# for i in range(gameObject.penSize):
						# 	# Set bit
						gameObject.gameBoard.getSquare(update[0], update[1]).color = serverEvent["color"]
						gameObject.gameBoard.getSquare(update[0], update[1]).locked = gameObject.playerColor(serverEvent["color"])
						xPixel, yPixel = gameObject.gameBoard.getSquare(update[0], update[1]).bitmap.setBits(update[2], update[3], gameObject.penSize)
						if serverEvent["color"] == gameObject.players[tuple(identifier)].color:
							bufferedSqr = (update[0], update[1])
						if xPixel != None:
							gameObject.gameUI.drawChanges(gameObject.colorDict[serverEvent["color"]], (update[0], update[1], xPixel, yPixel))
		elif serverEvent["type"] == "won":
			print("we got it.........")
			clientQueue.put(None)
			clientObject.setShutdown()
			gameObject.gameUI.ui_alert_user("The game has now ended!", "The following player(s) have won the game: " + serverEvent["winner"] + ". Congratulations!\n\nPress Okay to go back to the game configuration menu.")
			restart = gameObject.gameUI.outgoing_queue.get()
			if restart[0] == 'r':
				gameObject.gameUI.end()
				clientObject = client.Client()
				gameObject.startSettingsPrompt()
			else:
				exit(1)

			continue









#####################################################################
# gameObject = game.Game()
# gameObject.createGameboard(5, 5, 117, 50)
# gameObject.gameBoard.getSquare(4,4).updateColor("REDDDDDDDDDDDD")
# test = convertGameBoard(gameObject.gameBoard.gameBoardMatrix)
# print(test)
# print('#'*45)

# newGameObject = game.Game()
# newGameObject.createGameboard(5, 5, 117, 50)
# reconvertGameBoard(newGameObject, test)
# test2 = convertGameBoard(newGameObject.gameBoard.gameBoardMatrix)
# print(test2)
