class Player:
	def __init__(self, playerID, color):
		self.ID = playerID
		# lockedSquare should be an (x,y) tuple corresponding to the square
		self.lockedSquare = None
		self.penDown = False
		self.color = color