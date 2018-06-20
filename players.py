#Syntax for players is:
#   [0] : Move Camel
#   [1,trap_type,trap_location] : Place Trap
#   [2,projected_round_winner] : Make Round Winner Bet
#   [3,projected_game_winner] : Make Game Winner Bet
#   [4,projected_game_loser] : Make Game Loser Bet

        # self.camel_track = [[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[]]
        # self.trap_track = [[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[]] #entry of the form [trap_type (-1,1), player]
        # self.player_has_placed_trap = [False,False,False,False]
        # self.round_bets = []		#of the form [camel,player]
        # self.game_winner_bets = []			#of the form [camel,player]
        # self.game_loser_bets = []			#of the form [camel,player]
        # self.player_game_bets = [[],[],[],[]]
        # self.player_money_values = [2,2,2,2]
        # self.camel_yet_to_move = [True,True,True,True,True]
        # self.active_game = True

import random
import math
from playerinterface import PlayerInterface



class Player0(PlayerInterface):
    def move(player,g):
        #This dumb player always moves a camel
        return [0]

class Player1(PlayerInterface):
    def move(player,g):
        #This player is less dumb. If they have the least amount of money they'll make a round winner bet
        #If they aren't in last then they'll place a trap on a random square. Still p dumb though
        if min(g.player_money_values) == g.player_money_values[player]:
            return [2,random.randint(0,len(g.camels)-1)]
        return [1,math.floor(2*random.random())*2-1,random.randint(1,10)]

class Player2(PlayerInterface):
    def move(player,g):
        #This dumb player always makes a round winner bet
        return [2,random.randint(0,len(g.camels)-1)]