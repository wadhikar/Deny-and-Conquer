import math
import gameBoard
import player
import ui_pygame
# import TrevorGUI
# import QuintinServer

GREEN = (0, 153, 51)
RED = (255, 0, 0)
BLUE = (51, 102, 255)
ORANGE = (255, 153, 51)

class Game:
	# boardSize is the number squares across on the playable area of the board
	def __init__(self):
		self.gameBoard = None
		self.players = {}
		self.colorList = [RED, BLUE, GREEN, ORANGE]
		self.connectedPlayers = []
		self.numOfPlayers = 0
		self.threshold = 0
		self.boardSize = 0
		self.penSize = 0
		self.gameUI = None
		self.squarePixelWidth = 0
		self.percentage = 0
		self.colorDict = {
			1: RED,
			2: BLUE,
			3: GREEN,
			4: ORANGE
		}
		self.colorNumber = {
			RED: 1,
			BLUE: 2,
			GREEN: 3,
			ORANGE: 4
		}

	def createGameboard(self, boardSize, penSize, squarePixelWidth, percentage):
		self.boardSize = boardSize
		self.penSize = penSize
		self.squarePixelWidth = squarePixelWidth
		self.percentage = percentage
		self.gameBoard = gameBoard.GameBoard(boardSize, squarePixelWidth)
		self.threshold = math.floor(math.floor(squarePixelWidth/5) * math.floor(squarePixelWidth/5) * (percentage / 100))
		print("THRESH: ", self.threshold)

	def initializeGameUI(self):
		self.gameUI = ui_pygame.GameBoardUI()

	def startSettingsPrompt(self):
		# gameSettings = self.gameUI.ui_get_config() # Print for debug
		self.gameUI.ui_get_config() # Print for debug
		# return gameSettings # (Server/True, Settings Dict) or (Client/False, {ip: , port: })

	def startGameUI(self, boardSize, penSize):
		self.gameUI.ui_set_board_sz(boardSize, penSize)#Function must be run before start so that fork() duplicates this setting
		self.gameUI.start()

	# def initializePlayers(self):
	# 	colors = ["red", "blue", "green", "yellow"]
	# 	for i in range(self.numOfPlayers):
	# 		self.players[i] = Players(i, colors[i])

	def initializePlayers(self):
		for playerConn in self.connectedPlayers:
			print(playerConn)
			self.players[tuple(playerConn[0])] = player.Player(playerConn[0], playerConn[1])

	def initializePlayer(self, identifier, color):
		self.players[identifier] = player.Player(identifier, color)
		print("PLAYERS",self.players)

	def addConnectedPlayer(self, playerID, color):
		self.connectedPlayers.append((playerID, color))

	def removePlayer(self, playerID):
		for playerConn in self.connectedPlayers:
			if tuple(playerConn[0]) == playerID:
				self.connectedPlayers.remove(playerConn)
				if playerID in self.players:
					del self.players[playerID]
					print("deleted....")
				break
		print("remaining players...",self.connectedPlayers, playerID)

	def playerColor(self, color):
		for player in self.players.keys():
			if color == self.players[player].color:
				return player
		return None

	def assignColor(self):
		selectedColor = None
		for color in self.colorDict.keys():
			flagColorFound = True
			for playerConn in self.connectedPlayers:
				if color == playerConn[1]:
					flagColorFound = False
					break
			if flagColorFound == True:
				selectedColor = color
				break

		print("selectedColor!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! ", selectedColor)
		return selectedColor

	def checkCurrentLocks(self):
		for row in range(len(self.gameBoard.gameBoardMatrix)):
			for col in range(len(self.gameBoard.gameBoardMatrix[row])):
				if self.gameBoard.gameBoardMatrix[row][col].locked is not None:
					if self.gameBoard.gameBoardMatrix[row][col].locked in self.connectedPlayers:
						self.players[self.gameBoard.gameBoardMatrix[row][col].locked].lockedSquare = self.gameBoard.gameBoardMatrix[row][col].locked
					else:
						self.gameBoard.gameBoardMatrix[row][col].locked = None

