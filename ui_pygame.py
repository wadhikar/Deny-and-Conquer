from multiprocessing import Process,Queue
import pygame
from pygame.color import Color
import time
import random as rand
import math
import tkinter as tk
import sys
import textwrap


# Define some colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 153, 51)
RED = (255, 0, 0)
BLUE = (51, 102, 255)
ORANGE = (255, 153, 51)
ALERT_COLOR = (153, 0, 204)
#Incoming events will be sent as a FUNCTION CALL
#Outgoing events will be placed into a queue


#queue items
#tuple with 2 items, (command, data)
#Outgoing queue
#'q' -- quit ex: ('q', None)
#'s' -- all setting, 2 cases:
#{
#                "isServer": True,
#                "boardSize": self.user_board_sz,
#                "penSize": self.user_thickness,
#                "squarePixelWidth": self.server_squareSz,
#                "percentage": self.user_percent
#}
#{
#     "isServer": False,
#     "ip": self.user_ip_address,
#     "port": self.user_port
#}
#'m' -- mouse event ('m', (x_square, y_square, x_pixel, y_pixel))
#'l' -- lock event ('l', (x_square, y_square))
#'u' -- unlock event ('u', None)
#'c' -- connect event ('c', "192.168.111.130")
#REMOVED's' -- setting ('s', {"boardSize": n, "penSize": n, "squarePixelWidth, "squarePixelWidth": 44, "percentage": 77})

#incoming queue
#'d' -- draw event ('d', ((Colour, colour, colour), x_square, y_square, x_pixel, y_pixel))
#'c' -- colour square ('c', (COLOUR, (x,y)))
#'l' -- loading ('l', None)
#'u' -- unloading ('u', None)
#'i' -- ip and port ('i', ("ip", "port"))
#'


class GameBoardUI:
    def __init__(self):
        #Create 2 queues
        #Incoming and outgoing are fromthe perspective of this class
        self.incoming_queue = Queue()#Add to this queue only through internal functions
        self.outgoing_queue = Queue()

        self.gameSettings = {"boardSize": 0, "penSize": 0, "squarePixelWidth": 0, "percentage": 0}
        self.size = (825, 600)#Choose a screen resolution for the pygame interface

    def start(self):
        #Use processes rather than threads in order to improve performance
        #when using threads python only uses a maximum of 1 core due to the
        #global interpreter lock
        self.thread = Process(target=self._worker)
        self.thread.start()

    def end(self):
        #must be called from ANOTHER thread (not self.thread, presumably the main thread)
        self.killWindow()#Tell the window to quit
        self.thread.join()#Wait for the thread to terminate and join this (main) thread
        pygame.quit()#end the pygame process

    def killWindow(self):
        #Place an item on the queue to tell the pygame process to quit
        self.incoming_queue.put(('q',None))

    def displaySettings(self, ip, port, penSize, capturePercentage, boardSize, currentPlayers):
        self.incoming_queue.put(('i',(ip, str(port), str(penSize), str(capturePercentage),
                                      str(boardSize), currentPlayers)))

    def displayMessage(self, message):
        #Place a given text message at the bottom corner of the screen
        #Put this event into the queue in order to get pygame to process it
        self.incoming_queue.put(('t',message))

    def displayLoading(self, isLoading):
        #Toggle display of the loading activity
        #Either starting or stopping as given by the isLoading bool
        msg_type = 'l' if isLoading else 'u'
        self.incoming_queue.put((msg_type, None))

    def setSquare(self, square, colour):
        #Set a square to an arbitrary colour
        #Placing an item in the incoming queue for processing
        #by the pygame process
        self.incoming_queue.put(('c', (colour, square)))

    def drawChanges(self, colour, change):
        #Apply delta update to square
        #Place item on queue for processing by pygame
        self.incoming_queue.put(('d', (colour, change[0], change[1], change[2], change[3])))

    #Will return (x_square, y_square, x_pixel, y_pixel)
    #will return (0,0,0,0) if user clicks on a border
    def calculatePixelSquare(self, x_pixel, y_pixel):
        x_square_estimate = math.floor(x_pixel/(self.squareSz + 1))
        y_square_estimate = math.floor(y_pixel/(self.squareSz + 1))

        #Avoid divide by 0 error
        if ((x_square_estimate == 0) or (y_square_estimate == 0)):
            if ((x_pixel == 0) or (y_pixel == 0)):
                #This means we're on a boundary      
                return (-1,-1,-1,-1)
        if x_square_estimate != 0 and ((x_pixel / (x_square_estimate * (self.squareSz + 1)) ).is_integer()):
            #This means we're on a boundary        
            return (-1,-1,-1,-1)
        elif y_square_estimate != 0 and ((y_pixel / (y_square_estimate * (self.squareSz + 1)) ).is_integer()):
            #This means we're on a boundary        
            return (-1,-1,-1,-1)


        if (x_square_estimate >= self.num_of_squares):
            return (-1,-1,-1,-1)
        if (y_square_estimate >= self.num_of_squares):
            return (-1,-1,-1,-1)

        #Now we're not on a boundary
        x_interal_pixel = (x_pixel - (x_square_estimate * (self.squareSz + 1))) - 1
        y_interal_pixel = (y_pixel - (y_square_estimate * (self.squareSz + 1))) - 1

        return (x_square_estimate, y_square_estimate, x_interal_pixel, y_interal_pixel)
        

    def _drawBoxes(self, x_offset, y_offset, n):
        fullSquareSz = min(self.size)
        #fullSquareSz = 22
        self.squareSz = math.floor((fullSquareSz - (n+1)) / n)
        self.squareSz = math.floor(self.squareSz / 5) * 5
        print("Square size ", end='')
        print(self.squareSz)

        realSquareSz = (self.squareSz + 1) * n

        self.num_of_squares = n

        #Draw lines at 0, sz+1, (sz+1)*2, ...
        for i in range(n+1):
            pygame.draw.line(self.screen, (0,0,0), [0, (self.squareSz+1)*i], [realSquareSz, (self.squareSz+1)*i])
            pygame.draw.line(self.screen, (0,0,0), [(self.squareSz+1)*i, 0], [(self.squareSz+1)*i, realSquareSz])
 
    def _sendMouseEvent(self, x_loc, y_loc):
        #Internal function which places updated mouse events on the outgoing queue
        boxAndPixel = self.calculatePixelSquare(x_loc, y_loc)

        #Ignore invalid clicks (where (x_log, y_loc) does not correspond to
        #a non-boundary pixel on the board
        if(boxAndPixel != (-1,-1,-1,-1)):
            self.outgoing_queue.put(('m', boxAndPixel))

    def _get_client_config(self):
        #Run when the user clicks the button to select that they wish to use a client config

        #Place the values of the text input fields into a dict
        settings_to_game = {}
        settings_to_game['isServer'] = False
        settings_to_game['ip'] = self.entry_ip_addr.get()
        settings_to_game['port'] = self.entry_port.get()

        #Do basic input validation
        #Check that fields are filled
        if settings_to_game['ip'] == "" or settings_to_game['port'] == "":
            self.error_label_text.set("Invalid IP Address/Port. Please enter a valid IP Address/Port")
            return
        #Check if IP is a localhost and reject if so
        if settings_to_game['ip'] == "127.0.0.1" or \
           settings_to_game['ip'] == "localhost" or \
           settings_to_game['ip'] == "0.0.0.0":
            self.error_label_text.set("Please connect through the interface IP address")
            return
        try:
        	settings_to_game['port'] = int(settings_to_game['port'])
        except:
        	return

        print(settings_to_game)

        #Place the user chosen settings on the outgoing queue
        self.outgoing_queue.put(('s', settings_to_game))
        #Destroy the TK root
        self.tk_root.destroy()

        #Note that we have got a valid (presumably) config
        self.gotConfig = True
        print("CLIENT CONFIG")

    def ui_set_board_sz(self, boardSz, penSize=1):
        #Configure a certain board size
        self.configured_board_sz = boardSz
        self.penSize = penSize

    def _get_server_config(self):

        try:
            user_board_sz = int(self.entry_boardSz.get())
        except:
            user_board_sz = 5

        # Validate the board size.
        if user_board_sz < 3:
            user_board_sz = 3
        elif user_board_sz > 12:
            user_board_sz = 12

        fullSquareSz = min(self.size)

        server_squareSz = math.floor((fullSquareSz - (user_board_sz+1)) / user_board_sz)

        settings_to_game = {}
        settings_to_game["isServer"] = True
        settings_to_game["boardSize"] = user_board_sz
        settings_to_game["penSize"] = self.entry_thickness.get()
        try:
            settings_to_game["penSize"] = int(settings_to_game["penSize"])
        except:
            pass
        settings_to_game["squarePixelWidth"] = server_squareSz
        settings_to_game["percentage"] = self.entry_percentage.get()
        try:
            settings_to_game["percentage"] = int(settings_to_game["percentage"])
        except:
            pass

        # Validate percentage.
        if settings_to_game["percentage"] == "" or settings_to_game["percentage"] < 1:
            settings_to_game["percentage"] = 1
        elif settings_to_game["percentage"] > 100:
            settings_to_game["percentage"] = 100

        # Validate pen size.
        if settings_to_game["penSize"] == "" or settings_to_game["penSize"] < 1:
            settings_to_game["penSize"] = 1
        elif settings_to_game["penSize"] > 5:
            settings_to_game["penSize"] = 5

        self.outgoing_queue.put(('s', settings_to_game))

        self.tk_root.destroy()
        self.gotConfig = True

    def shutdownModal(self):
        self.outgoing_queue.put(('r', None))
        self.tk_root.destroy()

    def onClose(self):
        self.outgoing_queue.put(("q", None))
        self.incoming_queue.put(("q", None))
        self.tk_root.destroy()

    def _niceFormatNamesList(self, otherWinnersList):
        msg = ""
        numWinners = len(otherWinnersList)
        for i in range(numWinners):
            if i == (numWinners - 1):
                msg += " and "
                msg += otherWinnersList[i]
            elif i == (numWinners - 2):
                msg += " "
                msg += otherWinnersList[i]
            else:
                msg += " "
                msg += otherWinnersList[i]
                msg += ","
        return msg

    #Expecting input like (True/False, 'red', ['green'], {'red':7, 'blue': 3, 'green':7})
    def displayEndScreen(self, userIsWinner, ownColour, otherWinnersList, statisticsDict):
        header_message = ""
        if userIsWinner:
            if len(otherWinnersList) == 0:
                header_message = "You're a winner " + ownColour + "!"
            else:
                header_message = "You,"
                header_message += self._niceFormatNamesList(otherWinnersList)
                header_message += " are winners!"
        else:
            if len(otherWinnersList) == 1:
                header_message = otherWinnersList[0] + " wins!"
            else:
                header_message += self._niceFormatNamesList(otherWinnersList)
                header_message += " are winners!"


        message = ""
        newlineRequired = False
        for item in statisticsDict:
            if newlineRequired:
                message += "\n"
            message += item
            message += "\t"
            message += str(statisticsDict[item])
            newlineRequired = True
        self.ui_alert_user(header_message, message=message, colour=ownColour)
        print("RETURNED")
        self.end()


    def ui_alert_user(self, header, message="", colour="black"):
        print("tryna alert")
        self.tk_root = tk.Tk()
        self.tk_root.protocol("WM_DELETE_WINDOW", self.onClose)
        self.tk_root.title("Deny and Conquer Alert")
        label_font = ("times", 20, "bold")
        inst_lbl = tk.Label(self.tk_root, text=header, fg=colour)
        inst_lbl.grid(row=0, column = 0)
        inst_lbl.config(font=label_font)
        details = tk.Label(self.tk_root, text=message)
        details.grid(row=1, column=0)
        tk.Label(self.tk_root, text="").grid(row=2, column = 0)
        ok_button = tk.Button(self.tk_root, text="Okay", width=25, height=2, command=self.shutdownModal)
        ok_button.grid(row=3, column = 0)
        tk.mainloop()

    def ui_get_config(self):
        #We haven't gotten any input yet
        self.gotConfig = False
        #First, initialize tk in order to get a simple text input
        self.tk_root = tk.Tk()
        self.tk_root.protocol("WM_DELETE_WINDOW", self.onClose)
        self.tk_root.title("Deny and Conquer Configuration")

        self.error_label_text = tk.StringVar()

        inst_lbl = tk.Label(self.tk_root, text="Enter the address of the server that you want to connect to, or configure game settings to start your own server!")
        inst_lbl.grid(row=0, column = 0, columnspan=3)
        tk.Label(self.tk_root, text="").grid(row=1, column = 0, columnspan=3)
        tk.Label(self.tk_root, text="IP Address of server").grid(row=2, column = 0)
        tk.Label(self.tk_root, text="Port of server").grid(row=3, column = 0)
        tk.Label(self.tk_root, text="-"*3).grid(row=4, column = 0)
        tk.Label(self.tk_root, text="Percentage of box to colour (1-100)").grid(row=5, column = 0)
        tk.Label(self.tk_root, text="Thickness of the pen (1-5)").grid(row=6, column = 0)
        tk.Label(self.tk_root, text="Board size (3-12)").grid(row=7, column = 0)
        tk.Label(self.tk_root, text="").grid(row=8, column = 0, columnspan=3)
        tk.Label(self.tk_root, fg="red", textvariable=self.error_label_text).grid(row=9, column = 0, columnspan=3)

        self.entry_ip_addr = tk.Entry(self.tk_root)
        self.entry_port = tk.Entry(self.tk_root)
        self.entry_percentage = tk.Entry(self.tk_root)
        self.entry_thickness = tk.Entry(self.tk_root)
        self.entry_boardSz = tk.Entry(self.tk_root)

        button_client_config = tk.Button(self.tk_root, text="Connect to remote server", command=self._get_client_config)
        button_server_config = tk.Button(self.tk_root, text="Create your own server", command=self._get_server_config)

        self.entry_ip_addr.grid(row=2, column = 1)
        self.entry_port.grid(row=3, column = 1)
        tk.Label(self.tk_root, text="-"*3).grid(row=4, column = 1)
        self.entry_percentage.grid(row=5, column = 1)
        self.entry_thickness.grid(row=6, column = 1)
        self.entry_boardSz.grid(row=7, column = 1)
        #e2.grid(row=1, column = 1)
        button_client_config.grid(row=2, column = 2, rowspan=2)
        tk.Label(self.tk_root, text="-"*3).grid(row=4, column = 2)
        button_server_config.grid(row=5, column = 2, rowspan=3)

        tk.mainloop()

        return self.gotConfig

    def _worker(self):

        # Test -Quintin
        self.lastSentLocation = None

        #self._work_tk_get_config()
        #Now use pygame to get the game onto the screen
        pygame.init()
 
        # Set the width and height of the screen [width, height]
        self.screen = pygame.display.set_mode(self.size)
 
        pygame.display.set_caption("Deny and Conquer")

        # Loop until the user clicks the close button.
        self.done = False
 
        # Used to manage how fast the screen updates
        clock = pygame.time.Clock()

        ip_addr_font = pygame.font.Font('freesansbold.ttf', 16)
        text_font = pygame.font.Font('freesansbold.ttf', 16)

        #Load all images into memory
        clear_image = pygame.transform.scale(pygame.image.load('loading_img/blank.png'), (285,93))
        all_loading_images = []
        for i in range(27):
            all_loading_images.append(pygame.transform.scale(pygame.image.load('loading_img/loading-'+str(i)+'.png'), (285,93)))

        # -------- Main Program Loop -----------
        self.screen.fill(WHITE)
        self._drawBoxes(0,0,self.configured_board_sz)#16
        mouseCurrentlyDown = False
        currentlyLoading = -1 #Contains -1 or the last frame rendered
        while not self.done:
            # --- Main event loop
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    #Signal that it is time for the game to end
                    self.done = True
                    self.outgoing_queue.put(("q",None))
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    #print("Mouse click!!! at: ", end='')
                    #print(event.pos, end=',')
                    #print(self.calculatePixelSquare(event.pos[0], event.pos[1]))
                    x_box_loc, y_box_loc, _, _ = self.calculatePixelSquare(event.pos[0], event.pos[1])
                    if(x_box_loc != -1 and y_box_loc != -1):
                        self.outgoing_queue.put(('l',(x_box_loc, y_box_loc)))
                        print("Lock in box: ", end='')
                        print(('l',(x_box_loc, y_box_loc)))
                    self._sendMouseEvent(event.pos[0], event.pos[1])
                    mouseCurrentlyDown = True
                    self.lastSentLocation = None
                elif event.type == pygame.MOUSEBUTTONUP:
                    #print("Mouse up!")
                    mouseCurrentlyDown = False
                    x_box_loc, y_box_loc, _, _ = self.calculatePixelSquare(event.pos[0], event.pos[1])
                    if(x_box_loc != -1 and y_box_loc != -1):
                        self.outgoing_queue.put(('u', None))
                        print("Unlock in box: ", end='')
                        print(('u',(x_box_loc, y_box_loc)))
                    self.lastSentLocation = None
                elif ((event.type == pygame.MOUSEMOTION)):
                    if mouseCurrentlyDown:
                        #print("Mouse dragged!!! to: ", end='')
                        #print(self.calculatePixelSquare(event.pos[0], event.pos[1]))
                        if (math.floor(event.pos[0] / 5), math.floor(event.pos[1]/5)) == self.lastSentLocation:
                            continue
                        else:
                            self._sendMouseEvent(event.pos[0], event.pos[1])
                            self.lastSentLocation = (math.floor(event.pos[0] / 5), math.floor(event.pos[1] / 5))

            while self.incoming_queue.qsize() > 0:
                msg_type, payload = self.incoming_queue.get()
                if msg_type == 'c':
                    colour, position = payload
                    x_loc, y_loc = position
                    #print("fullcolor", x_loc, y_loc)
                    pygame.draw.rect(self.screen, colour, [x_loc*(self.squareSz+1)+1, y_loc*(self.squareSz+1)+1,self.squareSz, self.squareSz])
                if msg_type == 'd':
                    colour, x_square, y_square, x_pixel, y_pixel = payload
                    #print("fdraw", x_square, y_square)
                    leftMost = x_pixel - (self.penSize-1)*5
                    if leftMost < 0:
                        leftMost = 0
                    topMost = y_pixel - (self.penSize-1)*5
                    if topMost < 0:
                        topMost = 0
                    bottomMost = y_pixel + 5 + ((self.penSize-1)*5)
                    if bottomMost > self.squareSz:
                        bottomMost = self.squareSz
                    rightMost = x_pixel + 5 + (self.penSize-1)*5
                    if rightMost >= self.squareSz:
                        rightMost = self.squareSz

                    width = rightMost - leftMost
                    height = bottomMost - topMost

                    #real_x_pixel = (self.squareSz+1) * x_square + x_pixel + 1
                    #real_y_pixel = (self.squareSz+1) * y_square + y_pixel + 1
                    real_x_pixel = (self.squareSz+1) * x_square + leftMost + 1
                    real_y_pixel = (self.squareSz+1) * y_square + topMost + 1
                    pygame.draw.rect(self.screen, colour, [real_x_pixel, real_y_pixel, width, height])
                if msg_type == 'l':
                    currentlyLoading = 0

                if msg_type == 'u':
                    currentlyLoading = -1
                    self.screen.blit(clear_image, (601,0))
                if msg_type == 'i':
                    self.screen.blit(clear_image, (601,90))
                    self.screen.blit(clear_image, (601,180))
                    self.screen.blit(clear_image, (601,270))
                    print("Got new ip ", end='')
                    print(payload)
                    settingsParagraph = "      --- Game Info ---"
                    settingsParagraph += "\nServer IP: " + payload[0]
                    settingsParagraph += "\nServer Port: " + payload[1]
                    settingsParagraph += "\n"
                    settingsParagraph += "\nPen size: " + payload[2]
                    settingsParagraph += "\nCapture Percent: " + payload[3] + "%"
                    settingsParagraph += "\nBoard size: " + payload[4]
                    settingsParagraph += "\n\n    --- Current Players ---"
                    colors = []
                    for playerIdx in range(len(payload[5])):
                        player = payload[5][playerIdx]
                        if player[0] == 1:
                            payload[5][playerIdx][0] = "Red"
                        elif player[0] == 2:
                            payload[5][playerIdx][0] = "Blue"
                        elif player[0] == 3:
                            payload[5][playerIdx][0] = "Green"
                        elif player[0] == 4:
                            payload[5][playerIdx][0] = "Orange"
     
                    for player in payload[5]:
                        print(player)
                        if player[1]:
                            openIdent = ">>"
                            closeIdent = "<<"
                        else:
                            openIdent = ""
                            closeIdent = ""
                        settingsParagraph += "\n" + openIdent + str(player[0]) + closeIdent
                        if player[0] == "Orange":
                            colors.append(ORANGE)
                        elif player[0] == "Blue":
                            colors.append(BLUE)
                        elif player[0] == "Red":
                            colors.append(RED)
                        else:
                            colors.append(GREEN)
                    messageSegments = settingsParagraph.split("\n")
                    print(messageSegments)
                    offset = 100
                    curLine = 0
                    for segment in messageSegments:
                        curLine+=1
                        if curLine >= 10:
                            print (colors, curLine-10)
                            color = colors[curLine-10]
                        else:
                            color = BLACK
                        text_label = text_font.render(segment, 1, color)
                        self.screen.blit(text_label, (601,offset))
                        offset += 20

                    #ip_label = ip_addr_font.render("IP: "+payload[0], 1, BLACK)
                    #self.screen.blit(ip_label, (601,400))
                    #port_label = ip_addr_font.render("Port: " + payload[1], 1, BLACK)
                    #self.screen.blit(port_label, (601,450))

                if msg_type == 't':
                    #First, clear the current message...
                    self.screen.blit(clear_image, (601,400))
                    self.screen.blit(clear_image, (601,440))
                    self.screen.blit(clear_image, (601,480))
                    print("New text!")
                    wrappedMessage = textwrap.fill(payload, 23)
                    messageSegments = wrappedMessage.split("\n")
                    offset = 410
                    for segment in messageSegments:
                        text_label = text_font.render(segment, 1, ALERT_COLOR)
                        self.screen.blit(text_label, (601,offset))
                        offset += 20

                if msg_type == 'q':
                    self.done = True


            if currentlyLoading >= 27:
                currentlyLoading = 0
            if currentlyLoading >= 0:
                #load img here
                self.screen.blit(all_loading_images[int(currentlyLoading)], (601,0))
                currentlyLoading += 0.25

                
         
            pygame.display.flip()
         
            # --- Limit to 30 frames per second
            clock.tick(30)
 
# Close the window and quit.
# game = GameBoardUI()

# #game.drawBoard()

# #game.worker()
# print(game.ui_get_config())
# game.ui_set_board_sz(16)
# game.start()


#running = True
#while running:
#    msg_type, data = game.outgoing_queue.get(block=True)
#    if msg_type == 'q':
#        game.end()
#        running = False
#    elif msg_type == 'm':
#        print("Got a mouse event!: ", end='')
#        print(data)
#    elif msg_type == 's':
#        print("s: ", end='')
#        print(data)

#time.sleep(10)
#game.end()
