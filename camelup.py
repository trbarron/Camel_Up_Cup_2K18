import random, copy, math, uuid, hashlib
# NOTE: the engine is bot-agnostic — no bot imports at module scope. The
# __main__ demo below imports a few house bots lazily so a bare checkout (no
# contenders) still runs it.

camels = [0,1,2,3,4]
num_camels = len(camels)
num_players = 4
finish_line = 16
display_updates = False

class GameState:
    def __init__(self, rng=None):
        rng = rng or random
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
                index = rng.randint(0,len(initial_camels)-1)
                distance = rng.randint(0,2)
                self.camel_track[distance].append(initial_camels[index])
                initial_camels.remove(initial_camels[index])

class PlayerInterface():
    """Some description that tells you it's abstract,
    often listing the methods you're expected to supply."""
    def move( self ):
        raise NotImplementedError( "Should have implemented this" )


def player_view(g, player):
    """A deep copy of the game state as seen from one player's seat.

    Opponents' game-level bets are hidden information: their entries keep
    who placed them (public) but the camel choice is redacted to None, so
    bots cannot read or brute-force other players' bets. A player's own
    bets stay intact (hashed; decode them with check_bet)."""
    v = copy.deepcopy(g)
    v.game_winner_bets = [[b[0] if b[1] == player else None, b[1]] for b in g.game_winner_bets]
    v.game_loser_bets = [[b[0] if b[1] == player else None, b[1]] for b in g.game_loser_bets]
    v.player_game_bets = [bets if pl == player else [None] * len(bets)
                          for pl, bets in enumerate(g.player_game_bets)]
    return v


def PlayGame(player0,player1,player2,player3):
    players = [player0.move,player1.move,player2.move,player3.move]

    def action(result,player):
        if display_updates: print("Player Action: " + str(result))
        try:
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
                raise ValueError("action code out of bounds: " + str(result))
        except Exception as err: #Invalid actions fall back to rolling the dice
            if display_updates: print("Player " + str(player) + " made an invalid move (" + str(err) + "), rolling instead")
            MoveCamel(g,player)
        return


    g = GameState()
    g_round = 0
    while g.active_game:
        active_player = (g_round%4)
        try:
            result = players[active_player](active_player,player_view(g,active_player))
        except Exception: #Crashing bots roll the dice
            result = [0]
        action(result,active_player)
        g_round += 1
        if display_updates:
            DisplayGamestate(g)
    if display_updates: print("$ Totals:")
    if display_updates: print("\t" + str(g.player_money_values))
    if display_updates: print("Winner: " + str(g.game_winner))
    return g.game_winner


def MoveCamel(g,player,dice_fn=None):
    if (sum(g.camel_yet_to_move) <= 0):
        print(str(player) + ' tried to move a camel when none could be moved')
        return False
        #raise ValueError(str(player) + ' tried to move a camel when none could be moved')
    if dice_fn is not None: #Scripted dice (evaluate.py common-random-numbers harness)
        camel_index, distance = dice_fn(g)
    else:
        selected_camel = False         #Select camel to move
        while not selected_camel:
            camel_index = random.randint(0,num_camels - 1)
            selected_camel = g.camel_yet_to_move[camel_index]
        distance = random.randint(1,3)
    g.camel_yet_to_move[camel_index] = False #Remove camel from pool
    [curr_pos,found_y_pos] = [(ix,iy) for ix, row in enumerate(g.camel_track) for iy, i in enumerate(row) if i == camel_index][0] #Find distance, check for traps
    stack = len(g.camel_track[curr_pos])-found_y_pos

    stack_from_bottom = False
    if (len(g.trap_track[curr_pos + distance]) > 0):
        if display_updates : print("Player hit a trap!")
        if g.trap_track[curr_pos + distance][0] == -1:
            stack_from_bottom = True
        g.player_money_values[g.trap_track[curr_pos + distance][1]] += 1 #Give the player a coin
        distance += g.trap_track[curr_pos + distance][0] #Change the distance

    moving = g.camel_track[curr_pos][found_y_pos:] #Actually move camel (and any camels riding on top of it)
    del g.camel_track[curr_pos][found_y_pos:]
    if stack_from_bottom: #-1 trap: the moving unit goes UNDER the stack on the destination square
        g.camel_track[curr_pos + distance][:0] = moving
    else: #Stack normally (on top)
        g.camel_track[curr_pos + distance].extend(moving)
    g.player_money_values[player] += 1 #Give the rolling player a coin

    if sum(g.camel_yet_to_move) == 0 : EndOfRound(g) #If round is over, trigger End Of Round effects
    if sum(len(g.camel_track[i]) for i in range(finish_line, len(g.camel_track))) > 0 :
        EndOfRound(g)
        EndOfGame(g) #If game is over, trigger End Of Game and round effects

    return True
    
def PlaceTrap(g,trap_type,trap_place,player):
    if trap_type not in (-1,1): raise ValueError(str(player) + ' tried to place a trap with an invalid type: ' + str(trap_type))
    if trap_place < 1 or trap_place > len(g.trap_track) - 2: raise ValueError(str(player) + ' tried to place a trap out of bounds: ' + str(trap_place)) #Space 0 and the track edges are off limits
    if len(g.camel_track[trap_place]) != 0: raise ValueError(str(player) + ' tried to place a trap on top of camels')
    if (len(g.trap_track[trap_place - 1]) != 0 or len(g.trap_track[trap_place]) != 0 or len(g.trap_track[trap_place + 1]) != 0): raise ValueError(str(player) + ' tried to place a trap in an illegal spot') #No trap on or adjacent to another trap
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
    if camel not in g.camels: raise ValueError(str(player) + ' tried to make a game winner bet on an invalid camel: ' + str(camel))
    #Check to see if they are betting on a camel they've already bet on
    for i in range(0,len(g.player_game_bets[player])):
        if check_bet(g.player_game_bets[player][i],str(camel)):
            raise ValueError(str(player) + ' tried to make a game bet on a camel theyd already bet on')
    g.game_winner_bets.append([hash_bet(str(camel)),player])
    g.player_game_bets[player].append(hash_bet(str(camel)))
    return True

def PlaceGameLoserBet(g,camel,player):
    if camel not in g.camels: raise ValueError(str(player) + ' tried to make a game loser bet on an invalid camel: ' + str(camel))
    #Check to see if they are betting on a camel they've already bet on
    for i in range(0,len(g.player_game_bets[player])):
        if check_bet(g.player_game_bets[player][i],str(camel)):
            raise ValueError(str(player) + ' tried to make a game bet on a camel theyd already bet on')
    g.game_loser_bets.append([hash_bet(str(camel)),player])
    g.player_game_bets[player].append(hash_bet(str(camel)))
    return True

def PlaceRoundWinnerBet(g,camel,player):
    if camel not in g.camels: raise ValueError(str(player) + ' tried to make a round bet on an invalid camel: ' + str(camel))
    g.round_bets.append([camel,player])
    return True

def EndOfRound(g):
    first_place_payout = [5,3,2,0] #Settle round bets
    second_place_payout = [1,1,1,0]

    first_place_payout_index = 0
    second_place_payout_index = 0

    first_place_camel = FindCamelInNthPlace(g.camel_track,1)
    second_place_camel = FindCamelInNthPlace(g.camel_track,2)

    for i in range(0,len(g.round_bets)): #Payout every bet, in the order they were placed
        if g.round_bets[i][0] == first_place_camel :
            payout = (first_place_payout[first_place_payout_index] if first_place_payout_index < len(first_place_payout) else 0)
            g.player_money_values[g.round_bets[i][1]] += payout #handles out of range exceptions by returning 0
            if display_updates : print("Paid Player " + str(g.round_bets[i][1]) + " " + str(payout) + " coins for selecting the round winner")
            first_place_payout_index += 1
        elif g.round_bets[i][0] == second_place_camel :
            payout = (second_place_payout[second_place_payout_index] if second_place_payout_index < len(second_place_payout) else 0)
            g.player_money_values[g.round_bets[i][1]] += payout #handles out of range exceptions by returning 0
            second_place_payout_index += 1
            if display_updates : print("Paid Player " + str(g.round_bets[i][1]) + " " + str(payout) + " coins for selecting the round runner up")
        else : #Every losing round bet costs a coin
            g.player_money_values[g.round_bets[i][1]] -= 1
            if display_updates : print("Paid Player " + str(g.round_bets[i][1]) + " -1 coins for selecting a third place or worse camel")
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

    for i in range(0,len(g.game_winner_bets)):
        if check_bet(g.game_winner_bets[i][0],str(winning_camel)): #if you win, get prize
            payout = (payout_struct[payout_index] if payout_index < len(payout_struct) else 1)
            g.player_money_values[g.game_winner_bets[i][1]] += payout
            if display_updates : print("Paid Player " + str(g.game_winner_bets[i][1]) + " " + str(payout) + " coins for selecting the game winner")
            payout_index += 1 #decrease value of guessing winning camel
        else:
            g.player_money_values[g.game_winner_bets[i][1]] -= 1
            if display_updates : print("Paid Player " + str(g.game_winner_bets[i][1]) + " -1 coins for incorrectly selecting the game winner")

    payout_index = 0 #Settle bets on losing camel
    for i in range(0,len(g.game_loser_bets)):
        if check_bet(g.game_loser_bets[i][0],str(losing_camel)): #if you win, get prize
            payout = (payout_struct[payout_index] if payout_index < len(payout_struct) else 1)
            g.player_money_values[g.game_loser_bets[i][1]] += payout
            if display_updates : print("Paid Player " + str(g.game_loser_bets[i][1]) + " " + str(payout) + " coins for selecting the game loser")
            payout_index += 1 #decrease value of guessing winning camel
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
    # uuid is used to generate a random number
    salt = uuid.uuid4().hex
    return hashlib.sha256(salt.encode() + bet.encode()).hexdigest() + ':' + salt
    
def check_bet(hashed_bet, user_bet):
    bet, salt = hashed_bet.split(':')
    return bet == hashlib.sha256(salt.encode() + user_bet.encode()).hexdigest()


if __name__ == '__main__':
    from bots.test.players import Player0
    from bots.house.HandcodedHenry import HandcodedHenry
    from bots.house.ClaudeCamel import ClaudeCamel
    from bots.house.OpusOmul import OpusOmul
    from bots.house.GeminiGerry import GeminiGerry
    from bots.house.FabelFelix import FabelFelix
    player_pool = [Player0, OpusOmul, HandcodedHenry, ClaudeCamel, GeminiGerry, FabelFelix]
    player_points = [0 for i in range(len(player_pool))]

    for game in range(math.ceil(len(player_pool)/10)*100):
        order = [i for i in range(len(player_pool))]
        random.shuffle(order)
        winner = PlayGame(player_pool[order[0]],player_pool[order[1]],player_pool[order[2]],player_pool[order[3]])
        for num_winners in winner: player_points[order[num_winners]] += 1
        if sum(player_points)%10 == 0:
            print("---")
            for i in range(len(player_pool)):
                print("Player " + str(player_pool[i]) + " has " + str(player_points[i]) + " points.")
