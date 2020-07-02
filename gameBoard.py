import math
import gameSquare
import bitmap
import copy

class GameBoard:
	# boardSize is number of squares across on playable area of the board
	# gameArea is number of pixels across on the playable area of the board
	def __init__(self, boardSize, squarePixelWidth):
		print("ayyy",squarePixelWidth)
		self.pause = False
		self.gameBoardMatrix = []
		print("THERE", boardSize)
		for y in range(boardSize):
			row = []
			for x in range(boardSize):
				row.append(gameSquare.GameSquare(squarePixelWidth))
			self.gameBoardMatrix.append(row)
		print(len(self.gameBoardMatrix))
		self.emptyBitmap = bitmap.Bitmap(squarePixelWidth, squarePixelWidth)
		self.filledBitmap = bitmap.Bitmap(squarePixelWidth, squarePixelWidth).setAll()

	def getSquare(self, x, y):
		return self.gameBoardMatrix[y][x]

	def resetPlayerSquares(self, player):
		print("removing from ", player)
		squaresToReset = []
		for row in range(len(self.gameBoardMatrix)):
			for col in range(len(self.gameBoardMatrix[row])):
				print("owned by", self.gameBoardMatrix[row][col].owned)
				if self.gameBoardMatrix[row][col].owned == player:
					self.gameBoardMatrix[row][col].resetSquare(copy.deepcopy(self.emptyBitmap))
					squaresToReset.append((row, col))
		print("reseting:", squaresToReset)
		return squaresToReset

	def checkWinner(self):
		allOwned = True
		players = {}
		for row in self.gameBoardMatrix:
			for square in row:
				if square.owned == None:
					allOwned = False
					return None
				else:
					if square.color in players:
						players[square.color] += 1
					else:
						players[square.color] = 1

		maxSquares = -1
		for player in players.keys():
			if players[player] > maxSquares:
				maxSquares = players[player]

		winners = []
		for player in players.keys():
			if players[player] == maxSquares:
				winners.append(player)
		return winners


	# def pauseGame(self):
	# 	self.pause = True

	# def unpauseGame(self):
	# 	self.pause = False