import math

class Bitmap:
	def __init__(self, x, y):
		self.bitmap = []
		self.x = math.floor(x/5)
		self.y = math.floor(y/5)
		# self.bitmapSize = self.x * self.y
		self.filled = False
		for i in range(self.y):
			row = []
			for j in range(self.x):
				row.append(0)
			self.bitmap.append(row)

	def setBits(self, xPixel, yPixel, penSize):
		y = math.floor(yPixel/5)
		x = math.floor(xPixel/5)

		startX = x - (penSize-1)
		startY = y - (penSize-1)
		somethingSet = False
		for row in range((penSize*2)-1):
			for col in range((penSize*2)-1):
				xBit, yBit = self.setBit(startX+col, startY+row) 
				if xBit is not None:
					somethingSet = True

		if somethingSet:
			return (x*5, y*5)
		else:
			return (None, None)

	def setBit(self, x, y):
		if y < 0 or y >= self.y:
			return (None, None)
		if x < 0 or x >= self.y:
			return (None, None)

		if self.bitmap[y][x] != 1:
			self.bitmap[y][x] = 1
			return (x*5, y*5)
		return (None, None)
		
	def setAll(self):
		for row in range(len(self.bitmap)):
			for index in range(len(self.bitmap[row])):
				self.setBit(row, index)
				# print("Set x:{0} y:{1}".format(index, row))

	def countOnes(self):
		oneCount = 0
		for row in self.bitmap:
			for bit in row:
				if bit == 1:
					oneCount += 1

		return oneCount

	# Resets bitmap to all zeros
	def reset(self):
		for row in self.bitmap:
			for index in range(len(row)):
				row[index] = 0
