#Syntax for players is:
#   [0] : Move Camel
#   [1,trap_type,trap_location] : Place Trap
#   [2,projected_round_winner] : Make Round Winner Bet
#   [3,projected_game_winner] : Make Game Winner Bet
#   [4,projected_game_loser] : Make Game Loser Bet

import random
import math

def Player0(player,g):
    #This dumb player always moves a camel
    return [0]

def Player1(player,g):
    #This dumb player always places/moves a trap
    return [1,math.floor(2*random.random())*2-1,random.randint(1,10)]

def Player2(player,g):
    #This dumb player always makes a round winner bet
    return [2,random.randint(0,len(g.camels)-1)]

def Player3(player,g):
    #This dumb player always makes a game winner/loser bet
    return [random.randint(3,4),random.randint(0,len(g.camels)-1)]
