import bitmap

class GameSquare:
	def __init__(self, squarePixelWidth):
		# Should be set to player that has it locked. None if no one.
		self.locked = None
		self.owned = None
		self.color = None
		self.bitmap = bitmap.Bitmap(squarePixelWidth, squarePixelWidth)

	def lockSquare(self, player):
		self.locked = player

	def unlockSquare(self):
		self.locked = None

	# Call upon pen-up
	def canBeCaptured(self, ownershipReq):
		colored = self.bitmap.countOnes()
		if colored < ownershipReq:
			return False
		else:
			return True

	def captureSquare(self, player, color):
		self.bitmap.setAll()
		self.owned = player
		self.color = color

	# def resetSquare(self):
	# 	self.bitmap.reset()
	# 	self.color = None

	def resetSquare(self, bitmap):
		self.bitmap = bitmap
		self.locked = None
		self.owned = None
		self.color = None

	def updateColor(self, color):
		self.color = color