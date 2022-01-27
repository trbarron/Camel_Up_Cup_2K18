import random, copy, math, uuid, hashlib
from players import Player0, Player1, Player2
from Sir_Humpfree_Bogart import Sir_Humpfree_Bogart
import sys
import os
import random
import pygame
from pygame.locals import *
from neat import neat

camels = [0,1,2,3,4]
num_camels = len(camels)
num_players = 2
finish_line = 16
display_updates = False

P0_Is_AI = True
P1_Is_AI = False


# Constants
WIDTH, HEIGHT = 640, 480
NETWORK_WIDTH = 480

# Flags
AI = True
DRAW_NETWORK = True

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
YELLOW = (255, 255, 0)


# ----------------- #
def generate_net(current, nodes):
    # Generate the neural network to be displayed
    for i in current.get_nodes():
        if current.is_input(i):
            color = (0, 0, 255)
            x = 50
            y = 140 + i*60
        elif current.is_output(i):
            color = (255, 0, 0)
            x = NETWORK_WIDTH-50
            y = HEIGHT/2
        else:
            color = (0, 0, 0)
            x = random.randint(NETWORK_WIDTH/3, int(NETWORK_WIDTH * (2.0/3)))
            y = random.randint(20, HEIGHT-20)
        nodes[i] = [(int(x), int(y)), color]

def render_net(current, display, nodes):
    # Render the current neural network
    genes = current.get_edges()
    for edge in genes:
        if genes[edge].enabled: # Enabled or disabled edge
            color = (0, 255, 0)
        else:
            color = (255, 0, 0)

        pygame.draw.line(display, color, nodes[edge[0]][0], nodes[edge[1]][0], 3)

    for n in nodes:
        pygame.draw.circle(display, nodes[n][1], nodes[n][0], 7)

def convertGamestateToInputs(g, playerPos):
    '''
        self.camel_track = [[] for i in range(29)]
        self.trap_track = [[] for i in range(29)] #entry of the form [trap_type (-1,1), player]
        self.player_has_placed_trap = [False,False,False,False]
        self.round_bets = []		#of the form [camel,player]
        self.game_winner_bets = []			#of the form [camel,player]
        self.game_loser_bets = []			#of the form [camel,player]
        self.player_game_bets = [[],[],[],[]]
        self.player_money_values = [2,2,2,2]
        self.camel_yet_to_move = [True,True,True,True,True]
        self.active_game = True
        self.game_winner = []
        self.camels = camels


        0	which player you are
        1	Money p1
        2	money p2
        3	orange location
        4	white location
        5	blue location
        6	yellow location
        7	green location
        8	p1 trap
        9	p2 trap
        10	orange has moved
        11	white has moved
        12	blue has moved
        13	yellow has moved
        14	green has moved
        15	game winner/loser slot 1
        16	game winner/loser slot 2
        17	game winner/loser slot 3
        18	game winner/loser slot 4
        19	game winner/loser slot 5
        20	game winner/loser slot 6
        21	game winner/loser slot 7
        22	game winner/loser slot 8
        23	game winner/loser slot 9
        24	game winner/loser slot 10
    '''

    inputMatrix = [0] * 25

    inputMatrix[0] = playerPos
    inputMatrix[1] = g.player_money_values[0]
    inputMatrix[2] = g.player_money_values[1]

    camelPos = parseCamelsPosition(g.camel_track)

    inputMatrix[3] = camelPos[0]
    inputMatrix[4] = camelPos[1]
    inputMatrix[5] = camelPos[2]
    inputMatrix[6] = camelPos[3]
    inputMatrix[7] = camelPos[4]

    trapPos = parseTrapsPosition(g.trap_track)

    inputMatrix[8] = trapPos[0]
    inputMatrix[9] = trapPos[1]

    # Camels yet to move:

    inputMatrix[10] = g.camel_yet_to_move[0]
    inputMatrix[11] = g.camel_yet_to_move[1]
    inputMatrix[12] = g.camel_yet_to_move[2]
    inputMatrix[13] = g.camel_yet_to_move[3]
    inputMatrix[14] = g.camel_yet_to_move[4]

    # Game winner/loser bets

    gameBets = parseGameWinnerLoserBets(g.game_winner_bets, g.game_loser_bets, playerPos)

    inputMatrix[15] = gameBets[0]
    inputMatrix[16] = gameBets[1]
    inputMatrix[17] = gameBets[2]
    inputMatrix[18] = gameBets[3]
    inputMatrix[19] = gameBets[4]
    inputMatrix[20] = gameBets[5]
    inputMatrix[21] = gameBets[6]
    inputMatrix[22] = gameBets[7]
    inputMatrix[23] = gameBets[8]
    inputMatrix[24] = gameBets[9]

    return inputMatrix


def convertOutputToAction(output):
    '''
        Takes one of the 48 outputs and turns it into the action form that the game expects

        Roll the die	
        Make a round winner bet	
            5, 1 for each camel
        Make a game winner / loser bet	
            5 x 2, 1 for each camel, 1 for each option
        Place a trap	
            16 x 2, 1 for each space, 1 for each option

        result[0] == 0: #Player wants to move camel
        result[0] == 1: #Player wants to place trap
            if g.player_has_placed_trap[player]: MoveTrap(g,result[1],result[2],player)
        result[0] == 2: #Player wants to make round winner bet
            PlaceRoundWinnerBet(g,result[1],player)
        result[0] == 3: #Player wants to make game winner bet
            PlaceGameWinnerBet(g,result[1],player)
        result[0] == 4: #Player wants to make game loser bet
            PlaceGameLoserBet(g,result[1],player)
    '''

    thresh = 0.8

    # roll the die
    if output[0] and output[0] > thresh: return [0]

    # Make a round winner bet	
    if output[1] and output[1] > thresh: return [2,0]
    if output[2] and output[2] > thresh: return [2,1]
    if output[3] and output[3] > thresh: return [2,2]
    if output[4] and output[4] > thresh: return [2,3]
    if output[5] and output[5] > thresh: return [2,4]

    # Make a game winner / loser bet	
    if output[6] and output[6] > thresh: return [3,0]
    if output[7] and output[7] > thresh: return [3,1]
    if output[8] and output[8] > thresh: return [3,2]
    if output[9] and output[9] > thresh: return [3,3]
    if output[10] and output[10] > thresh: return [3,4]

    # Place a trap	
    #   forwards
    if output[11] and output[11] > thresh: return [1,1,1]
    if output[12] and output[12] > thresh: return [1,1,2]
    if output[13] and output[13] > thresh: return [1,1,3]
    if output[14] and output[14] > thresh: return [1,1,4]
    if output[15] and output[15] > thresh: return [1,1,5]
    if output[16] and output[16] > thresh: return [1,1,6]
    if output[17] and output[17] > thresh: return [1,1,7]
    if output[18] and output[18] > thresh: return [1,1,8]
    if output[19] and output[19] > thresh: return [1,1,9]
    if output[20] and output[20] > thresh: return [1,1,10]
    if output[21] and output[21] > thresh: return [1,1,11]
    if output[22] and output[22] > thresh: return [1,1,12]
    if output[23] and output[23] > thresh: return [1,1,13]
    if output[24] and output[24] > thresh: return [1,1,14]
    if output[25] and output[25] > thresh: return [1,1,15]

    #   backwards
    if output[26] and output[26] > thresh: return [1,-1,1]
    if output[27] and output[27] > thresh: return [1,-1,2]
    if output[28] and output[28] > thresh: return [1,-1,3]
    if output[29] and output[29] > thresh: return [1,-1,4]
    if output[30] and output[30] > thresh: return [1,-1,5]
    if output[31] and output[31] > thresh: return [1,-1,6]
    if output[32] and output[32] > thresh: return [1,-1,7]
    if output[33] and output[33] > thresh: return [1,-1,8]
    if output[34] and output[34] > thresh: return [1,-1,9]
    if output[35] and output[35] > thresh: return [1,-1,10]
    if output[36] and output[36] > thresh: return [1,-1,11]
    if output[37] and output[37] > thresh: return [1,-1,12]
    if output[38] and output[38] > thresh: return [1,-1,13]
    if output[39] and output[39] > thresh: return [1,-1,14]
    if output[40] and output[40] > thresh: return [1,-1,15]


    # uh oh we failed to do anything, just roll
    return [0]


# ---------------------- #

class GameState:
    def __init__(self):
        self.camel_track = [[] for i in range(29)]
        self.trap_track = [[] for i in range(29)] #entry of the form [trap_type (-1,1), player]
        self.player_has_placed_trap = [False,False,False,False]
        self.round_bets = []		#of the form [camel,player]
        self.game_winner_bets = []			#of the form [camel,player]
        self.game_loser_bets = []			#of the form [camel,player]
        self.player_game_bets = [[],[],[],[]]
        self.player_money_values = [2,2,2,2]
        self.camel_yet_to_move = [True,True,True,True,True]
        self.active_game = True
        self.game_winner = []
        self.camels = camels
        
        initial_camels = copy.deepcopy(camels)
        for _ in range(0,num_camels):
                index = random.randint(0,len(initial_camels)-1)
                distance = random.randint(0,2)
                self.camel_track[distance].append(initial_camels[index])
                initial_camels.remove(initial_camels[index])

class PlayerInterface():
    """Some description that tells you it's abstract,
    often listing the methods you're expected to supply."""
    def move( self ):
        raise NotImplementedError( "Should have implemented this" )


def PlayGame(player0,player1):
    if P0_Is_AI and P1_Is_AI:
        players = [player0, player1]
    elif P0_Is_AI and not P1_Is_AI:
        players = [player0,player1.move]
    else:
        players = [player0.move,player1.move]

    def action(result,player):
        if display_updates: print("Player Action: " + str(result))
        if result[0] == 0: #Player wants to move camel
            MoveCamel(g,player)
            if display_updates: print("Player " + str(player) + " moved camel")
        elif result[0] == 1: #Player wants to place trap
            if g.player_has_placed_trap[player]: MoveTrap(g,result[1],result[2],player)
            else : PlaceTrap(g,result[1],result[2],player)
            if display_updates: print("Player " + str(player) + " placed a trap")
        elif result[0] == 2: #Player wants to make round winner bet
            PlaceRoundWinnerBet(g,result[1],player)
            if display_updates: print("Player " + str(player) + " made a round winner bet")
        elif result[0] == 3: #Player wants to make game winner bet
            PlaceGameWinnerBet(g,result[1],player)
            if display_updates: print("Player " + str(player) + " made a game winner bet")
        elif result[0] == 4: #Player wants to make game loser bet
            PlaceGameLoserBet(g,result[1],player)
            if display_updates: print("Player " + str(player) + " made a game loser bet")
        else:
            print("oh jeez result was out of bounds")
            print("Player commited: " + str(player))
            print("Action attempted: " + str(result))
        return
            

    g = GameState()
    g_round = 0
    while g.active_game:
        active_player = (g_round%2)
        
        if P0_Is_AI and active_player == 0:
            # Set our inputs
            inputs = convertGamestateToInputs(g, active_player)

            # Check our outputs
            output = player0.forward(inputs)

            #call action with that output
            actionValue = convertOutputToAction(output)
            action(actionValue, 0)

        elif P1_Is_AI and active_player == 1:
            # Set our inputs
            # Check our outputs
            output = player1.forward(inputs)[0]

            #call action with that output
        
        else:
            action(players[active_player](active_player,copy.deepcopy(g)),active_player)

        g_round += 1
        if display_updates:
            DisplayGamestate(g)
    if display_updates: print("$ Totals:")
    if display_updates: print("\t" + str(g.player_money_values))
    if display_updates: print("Winner: " + str(g.game_winner))
    return g.game_winner


def MoveCamel(g,player):
    if (sum(g.camel_yet_to_move) < 0):
        print(str(player) + ' tried to move a camel when none could be moved')
        return False
        #raise ValueError(str(player) + ' tried to move a camel when none could be moved')
    selected_camel = False         #Select camel to move
    while not selected_camel:
        camel_index = random.randint(0,num_camels - 1)
        selected_camel = g.camel_yet_to_move[camel_index]
    g.camel_yet_to_move[camel_index] = False #Remove camel from pool
    [curr_pos,found_y_pos] = [(ix,iy) for ix, row in enumerate(g.camel_track) for iy, i in enumerate(row) if i == camel_index][0] #Find distance, check for traps
    stack = len(g.camel_track[curr_pos])-found_y_pos
    distance = random.randint(1,3)

    stack_from_bottom = False
    if (len(g.trap_track[curr_pos + distance]) > 0):
        if display_updates : print("Player hit a trap!")
        if g.trap_track[curr_pos + distance][0] == -1:
            stack_from_bottom = True
        g.player_money_values[g.trap_track[curr_pos + distance][1]] += 1 #Give the player a coin
        distance += g.trap_track[curr_pos + distance][0] #Change the distance

    camels_to_move = [] #Actually move camel
    
    if stack_from_bottom: #stack from bottom if trap was -1
        for c in range(0,stack):
            camels_to_move.append(g.camel_track[curr_pos].pop(stack-c-1))
            g.camel_track[curr_pos + distance].insert(0,camels_to_move[0])
            camels_to_move.clear()
    else: #Stack normally         
        for c in range(0,stack):
            camels_to_move.append(g.camel_track[curr_pos].pop(found_y_pos))
            g.camel_track[curr_pos + distance].append(camels_to_move[0])
            camels_to_move.clear()
    g.player_money_values[player] += 1 #Give the rolling player a coin
    
    if sum(g.camel_yet_to_move) == 0 : EndOfRound(g) #If round is over, trigger End Of Round effects
    if len(g.camel_track[finish_line]) + len(g.camel_track[finish_line + 1]) + len(g.camel_track[finish_line + 2]) > 0 :
        EndOfRound(g)
        EndOfGame(g) #If game is over, trigger End Of Game and round effects

    return True
    
def PlaceTrap(g,trap_type,trap_place,player):
    if ((trap_place > 0 and len(g.trap_track[trap_place - 1]) != 0) or (len(g.trap_track[trap_place]) != 0) or (trap_place < len(g.trap_track) and len(g.trap_track[trap_place + 1]) != 0)): raise ValueError(str(player) + ' tried to place a trap in an illegal spot') #Check to see if track placement is legal
    if g.player_has_placed_trap[player] == True : raise ValueError(str(player) + ' tried to place two traps somehow')
    g.trap_track[trap_place] = [trap_type,player]
    g.player_has_placed_trap[player] = True
    return True

def MoveTrap(g,trap_type,trap_place,player):
        #[curr_pos,stack] = [(ix,iy) for ix, row in enumerate(g.camel_track) for iy, i in enumerate(row) if i == camel_index][0] #Find distance, check for traps
    [curr_pos] = [y for y, row in enumerate(g.trap_track) if (row[1] if 0 < len(row) else None) == player]
    g.trap_track[curr_pos] = []
    g.player_has_placed_trap[player] = False
    PlaceTrap(g,trap_type,trap_place,player)
    return True

def PlaceGameWinnerBet(g,camel,player):
    #Check to see if they are betting on a camel they've already bet on
    for i in range(0,len(g.player_game_bets[player])):
        if check_bet(g.player_game_bets[player][i],str(camel)):
            if display_updates : print(str(player) + ' tried to bet on a camel winning that theyd already bet on!')
            return False
    g.game_winner_bets.append([hash_bet(str(camel)),player])
    g.player_game_bets[player].append(hash_bet(str(camel)))
    return True

def PlaceGameLoserBet(g,camel,player):
    #Check to see if they are betting on a camel they've already bet on
    for i in range(0,len(g.player_game_bets[player])):
        if check_bet(g.player_game_bets[player][i],str(camel)):
            if display_updates : print(str(player) + ' tried to bet on a camel winning that theyd already bet on!')
            return False
    g.game_loser_bets.append([hash_bet(str(camel)),player])
    g.player_game_bets[player].append(hash_bet(str(camel)))
    return True

def PlaceRoundWinnerBet(g,camel,player):
    g.round_bets.append([camel,player])
    return True

def EndOfRound(g):
    first_place_payout = [5,3,2,0] #Settle round bets
    second_place_payout = [1,1,1,0]
    third_or_worse_place_payout = [-1,-1,-1,0]
    
    first_place_payout_index = 0
    second_place_payout_index = 0
    third_or_worse_place_payout_index = 0
    
    first_place_camel = FindCamelInNthPlace(g.camel_track,1)
    second_place_camel = FindCamelInNthPlace(g.camel_track,2)
    
    for i in range(0,len(g.round_bets) - 1): #Payout
        if g.round_bets[i][0] == first_place_camel :
            payout = (first_place_payout[first_place_payout_index] if first_place_payout_index < len(first_place_payout) else 0)
            g.player_money_values[g.round_bets[i][1]] += payout #handles out of range exceptions by returning 0
            if display_updates : print("Paid Player " + str(g.round_bets[i][1]) + " " + str(payout) + " coins for selecting the round winner")
            first_place_payout_index += 1
        elif g.round_bets[i][0] == second_place_camel :
            payout = (second_place_payout[second_place_payout_index] if second_place_payout_index < len(second_place_payout) else 0)
            g.player_money_values[g.round_bets[i][1]] += payout #handles out of range exceptions by returning 0
            second_place_payout_index += 1
            if display_updates : print("Paid Player " + str(g.round_bets[i][1]) + " " + str(second_place_payout) + " coins for selecting the round runner up")
        else :
            payout = (third_or_worse_place_payout[third_or_worse_place_payout_index] if third_or_worse_place_payout_index < len(third_or_worse_place_payout) else 0)
            g.player_money_values[g.round_bets[i][1]] += payout #handles out of range exceptions by returning 0
            third_or_worse_place_payout_index += 1
            if display_updates : print("Paid Player " + str(g.round_bets[i][1]) + " " + str(third_or_worse_place_payout) + " coins for selecting the a third place or worse camel")
    g.camel_bet_values = [5,5,5,5,5] #Reset camel bet values and camels yet to move
    g.camel_yet_to_move = [True,True,True,True,True]
    g.round_bets = [] #clear round bets
    g.trap_track = [[] for i in range(29)] #entry of the form [trap_type (-1,1), player]
    g.player_has_placed_trap = [False,False,False,False]
    return

def EndOfGame(g):
    winning_camel = FindCamelInNthPlace(g.camel_track,1) #Find camel that won
    losing_camel = FindCamelInNthPlace(g.camel_track,num_camels) #Find camel that lost
    
    # Settle game bets
        # game_bets are of the form [camel,player]

        # Selecting correct winner gives 8,5,3,1,1,1,1
        # Selecting wrong gives -1
        #Settle bets on winning camel
    
    payout_index = 0
    payout_struct = [8,5,3,1] #anything out of bounds gives a 1

    for i in range(0,len(g.game_winner_bets)-1):
        if check_bet(g.game_winner_bets[i][0],str(winning_camel)): #if you win, get prize
            payout = (payout_struct[payout_index] if payout_index < len(payout_struct) else 1)
            g.player_money_values[g.game_winner_bets[i][1]] += payout
            if display_updates : print("Paid Player " + str(g.game_winner_bets[i][1]) + " " + str(payout) + " coins for selecting the game winner")
            payout_index += 1 #decrease value of guessing winning camel
        else:
            g.player_money_values[g.game_winner_bets[i][1]] -= 1
            if display_updates : print("Paid Player " + str(g.game_winner_bets[i][1]) + " -1 coins for incorrectly selecting the game winner")

    payout_index = 0 #Settle bets on losing camel
    for i in range(0,len(g.game_loser_bets) - 1):
        if check_bet(g.game_loser_bets[i][0],str(losing_camel)): #if you win, get prize
            payout = str(payout_struct[payout_index] if payout_index < len(payout_struct) else 1)
            g.player_money_values[g.game_loser_bets[i][1]] += payout_struct[payout_index]
            if display_updates : print("Paid Player " + str(g.game_loser_bets[i][1]) + " "  + " coins for selecting the game loser")
            payout_index += 1 #decrease value of guessing losing camel
        else:
            g.player_money_values[g.game_loser_bets[i][1]] -= 1
            if display_updates : print("Paid Player " + str(g.game_loser_bets[i][1]) + " -1 coins for incorrectly selecting the game loser")

    g.active_game = False
    g.game_winner = [i for i, j in enumerate(g.player_money_values) if j == max(g.player_money_values)]
    return True

def FindCamelInNthPlace(track,n):
    if (n > num_camels or n < 1): raise ValueError('Something tried to find a camel in a Nth place, where N is out of bounds')	
    found_camel = False
    camels_counted = 0
    i = 1
    while not found_camel:
        dtg = n - camels_counted
        camels_in_stack = len(track[len(track)-i])
        if camels_in_stack >= dtg: return track[len(track) - i][camels_in_stack - dtg] 
        else :
            camels_counted += camels_in_stack
            i += 1
    return False

def parseCamelsPosition(track):
    '''
    Take in all the whole track and return in a matrix the parsed positions of each camel
    "050" = on square 5 in the zero position
    "051" = on top of 50
    142 is another example
    '''

    camelPos = [0] * num_camels

    trackPos = 0
    for place in track:
        stackPos = 0
        for camel in place:
            camelPos[camel] = trackPos * 10 + stackPos
            stackPos += 1
        trackPos += 1
    return camelPos

def parseTrapsPosition(track):
    '''
    Take in all the whole trap track and return in a matrix the parsed positions of each trap
        if its a speed up or slow down		1 = speed up	2 = slow down
        Where the traps are		2 dig number with it's location	

        #entry of the form [trap_type (-1,1), player]
    '''

    trapPos = [0] * num_players

    trackPos = 0
    for place in track:
        if place:
            trapPos[place[1]] = trackPos
            if place[0] == -1:
                trapPos[place[1]] += 200
            else:
                trapPos[place[1]] += 100
        trackPos += 1
    return trapPos

def parseGameWinnerLoserBets(winnerBets, loserBets, playerNum):
    '''
    Take in winner and loser bets and parses it into a form that the input matrix will like
        5x for each player			
        "each slot says if they voted on a winner/loser
        and who it was OR the opponent voted on a winner/loser"			
        1 = it was you, 2 it wasn't you	1 = winner, 2 = loser	1= orange, 2 = white, 3 = blue, etc, 9 = idk

        self.game_winner_bets = []			#of the form [camel,player]
        self.game_loser_bets = []			#of the form [camel,player]
    '''

    bets = [0] * 10
    
    betPointer = 0
    for gameWinBet in winnerBets:
        if gameWinBet[1] == playerNum:
            bets[betPointer] = 110 + int(gameWinBet[0])
        else:
            bets[betPointer] = 200 + 10 + 9
        
        betPointer += 1
    
    betPointer = 9
    for gameLosebet in loserBets:
        if gameLosebet[1] == playerNum:
            bets[betPointer] = 120 + int(gameLosebet[0])
        else:
            bets[betPointer] = 200 + 20 + 9
        
        betPointer -= 1

    return bets

def DisplayGamestate(g):
    print("Track:")
    DisplayTrackState(g.camel_track)
    print("\n")
    print("Traps:")
    DisplayTrackState(g.trap_track)
    print("\n")
    print("$ Totals:")
    print("\t" + str(g.player_money_values))
    print("\n")

def DisplayTrackState(track):
    max_stack = len(max(track,key=len))

    #Print milestones
    track_label_string = "\t|"
    for _ in range(0,finish_line): track_label_string += ("-" + str(_) + "-|")
    print(track_label_string)

    #Print blank line
    track_label_string = "\t"
    for i in range(0,finish_line): track_label_string += ("---"+"-"*len(str(i)))
    print(track_label_string+"-")

    #Print N/A if there are no objects (camels/traps)
    if max_stack == 0:
        track_label_string = "\t  " #extra spaces because double digit numbers mess things up
        for _ in range(0,finish_line): track_label_string += ("  ")
        print(track_label_string+"NA")

    #otherwise print those objects
    for stack_spot in range(0,max_stack):
        track_string = "\t"
        for track_spot in range(0,finish_line):
            if len(track[track_spot]) >= max_stack-stack_spot:
                str_len = len(str(track[track_spot][max_stack-stack_spot-1]))
                track_string += ("|" + " "*(2-str_len)+ str(track[track_spot][max_stack-stack_spot-1]) + " "*len(str(track_spot)))
            else: track_string += ("|" + " "*(2+len(str(track_spot))))
        print(track_string+"|")

    #Print blank line again
    track_label_string = "\t"
    for i in range(0,finish_line): track_label_string += ("---"+"-"*len(str(i)))
    print(track_label_string+"-")
    #Print milestones again

    track_label_string = "\t|"
    for _ in range(0,finish_line): track_label_string += ("-" + str(_) + "-|")
    print(track_label_string)

def hash_bet(bet):
    return bet # TODO: make this better or something? I'm subverting the hashing
    # uuid is used to generate a random number
    salt = uuid.uuid4().hex
    return hashlib.sha256(salt.encode() + bet.encode()).hexdigest() + ':' + salt
    
def check_bet(hashed_bet, user_bet):
    return hashed_bet == user_bet # TODO: make this better or something? I'm subverting the hashing
    bet, salt = hashed_bet.split(':')
    return bet == hashlib.sha256(salt.encode() + user_bet.encode()).hexdigest()


# games_to_play = 20
# player_pool = [Player0, Player1]
# player_points = [0 for i in range(len(player_pool))]

# for game in range(math.ceil(len(player_pool)/10)*games_to_play):
#     order = [i for i in range(len(player_pool))]
#     random.shuffle(order)
#     winner = PlayGame(player_pool[order[0]],player_pool[order[1]])
#     for num_winners in winner: player_points[order[num_winners]] += 1
#     if sum(player_points)%10 == 0:
#         print("---")
#         for i in range(len(player_pool)):
#             print("Player " + str(player_pool[i]) + " has " + str(player_points[i]) + " points.")



def main():
    # Main game function
    if DRAW_NETWORK:
        pygame.init()
        display = pygame.display.set_mode((NETWORK_WIDTH, HEIGHT), 0, 32)
        network_display = pygame.Surface((NETWORK_WIDTH, HEIGHT))
        clock = pygame.time.Clock()


    # Load the camel's brain
    if os.path.isfile('camelupbrain_0.neat'):
        P0Brain = neat.Brain.load('camelupbrain_0')
    else:
        hyperparams = neat.Hyperparameters()
        hyperparams.delta_threshold = 0.75

        hyperparams.mutation_probabilities['node'] = 0.05
        hyperparams.mutation_probabilities['edge'] = 0.05

        P0Brain = neat.Brain(25, 48, 100, hyperparams)
        P0Brain.generate()
    
    # Load the old camel's brain
    if os.path.isfile('camelupbrain_1.neat'):
        P1Brain = neat.Brain.load('camelupbrain_1')
        P1_Is_AI = True
    else:
        P1_Is_AI = False
        P1Current = Player0

    P0Current = P0Brain.get_current()
    inputs = [0] * 25
    output = [0] * 48
    nodes = {}

    generate_net(P0Current, nodes)

    if P1_Is_AI:
        P1Current = P1Brain.get_current()
        generate_net(P1Current, nodes)


    print("Loaded... starting")

    gamesPlayed = 0
    while True:
        # Main loop
        if DRAW_NETWORK: 
            display.fill(BLACK)
            network_display.fill(WHITE)

        games_to_play = 20
        player_pool = [P0Current, P1Current]
        player_points = [0 for i in range(len(player_pool))]

        for game in range(math.ceil(len(player_pool)/10)*games_to_play):
            order = [i for i in range(len(player_pool))]
            # random.shuffle(order) #TODO: Right now we aren't shuffling the order for my SANITY. We'll change that later
            winner = PlayGame(player_pool[order[0]],player_pool[order[1]])
            for num_winners in winner: player_points[order[num_winners]] += 1
            
        # for i in range(len(player_pool)):
        #     print("Player " + str(player_pool[i]) + " has " + str(player_points[i]) + " points.")

        P0Current.set_fitness(float(player_points[0] / games_to_play))

        if DRAW_NETWORK:
            render_net(P0Current, network_display, nodes)
        if gamesPlayed % 10 == 0:
            print("Fitness: ", float(player_points[0] / games_to_play))
            print("Generation: ", P0Brain.get_generation()+1)
            
            if P1_Is_AI:
                P0Brain.save('camelupbrain_1')
                P0Current.set_fitness(0)
                P1Brain = neat.Brain.load('camelupbrain_1')
                P1Current = P1Brain.get_current()
                generate_net(P1Current, nodes)

        # These happen on a game end

        # Save the bird's brain
        P0Brain.save('camelupbrain_0')
        P0Brain.next_iteration()
        P0Current = P0Brain.get_current()

        # Restart the game
        generate_net(P0Current, nodes)

        # Update display and its caption
        if DRAW_NETWORK:
            display.blit(network_display, (WIDTH, 0))
            pygame.display.set_caption("GNRTN : {0}; SPC : {1}; CRRNT : {2}; FIT : {3}".format(
                                                P0Brain.get_generation()+1, 
                                                P0Brain.get_current_species()+1, 
                                                P0Brain.get_current_genome()+1,
                                                P0Brain.get_fittest().get_fitness(),
                                                # round(output, 48),
                                                # [round(i, 48) for i in inputs]
            ))
            pygame.display.update()
            clock.tick(1)

        gamesPlayed += 1


if __name__ == "__main__":
    main()