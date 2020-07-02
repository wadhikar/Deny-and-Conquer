import client
import socket
import sys
import time as time
import json
import queue
import threading
import math
from threading import Thread

# Returns ClientObject, Bool. Bool is True if this client has become leader. False if not. 
# If this client has become the leader, the game engine must turn on their server.
# listOfCandidates is a queue where each index is clientCandidate == [serverAddr, serverPort]
def reconnect(listOfCandidates, identifier, candidateAddr=None):

    # Attempt to connect to each server replacement candidate in order. 
    for clientCandidate in listOfCandidates:
        potentialClient = client.Client()
        # Debugging
        print("RECONNECT: trying out ", clientCandidate)
        # Attempt to connect to the server.
        con, _ = potentialClient.connect(clientCandidate[0], clientCandidate[1], identifier[0], identifier[1], candidateAddr)
        if not con:
            # If the connection attempt failed, move on to try the next candidate server.
            continue
        else:
            # If connection is successful, wait to see if server responds.
            potentialClient.start()
            if clientCandidate == candidateAddr:
                # If the server connected to is the server local to this client, then return and indicate
                # that the game engine should turn on the local server. 
                return potentialClient, True, clientCandidate

            # Wait for a response from the server for 16 seconds. If there is no response after 16 seconds,
            # we assume that we disconnected but original server did not. In this case we return without
            # restablishing a connection, since we alone disconnected from the game. 
            for sec in range(16):
                # Sleep 1 second.
                time.sleep(1)
                # If there is a message to process, process it. 
                if not potentialClient.receivingQueue.empty():
                    # Get message from server.
                    message = potentialClient.receivingQueue.get()
                    # If the server rejected our connection, we return simply return without restablishing a connection.
                    if message["type"] == "reject":
                        # Debugging
                        print("RECONNECT: Rejected!!!")
                        return None, False, None
                    elif message["type"] == "config":
                        # Debugging
                        print("RECONNECT: we are back up guys")
                        # If we receive a config response, then the server accepted our connection. Return the client obect,
                        # and False indicating we connected to an external server.
                        return potentialClient, False, clientCandidate
                    elif message["type"] == "reconnect":
                        # If we receive a reconnect message, then the server we were trying to connect with went down. Move
                        # on to try and connect to the next candidate. 
                        break
            else:
                # Debugging
                print("Simply timed out...")
                # If the loop ended naturally, then it has been 16 seconds without a rejection or acception message
                # from the server. Assume our own client went down but the original server did not. In this case
                # we return without establishing a new connection. 
                return None, False, None
    # Debugging
    print("RECONNECT: Out of options..")
    # If we have not restablished a connection with any of the candidates in the list, then we are out of options.
    # Return without establishing any new connections. 
    return None, False, None