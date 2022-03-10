from playerinterface import PlayerInterface

class Sir_Humpfree_Bogart(PlayerInterface):
    def move(player,g):
        from itertools import permutations
        from copy import deepcopy
        from math import floor
        import uuid, hashlib
        import random

        finish_line = 16
        display_updates = False
        
        def MoveCamel(selected_camel,move_dist,hyp_camel_track,g):
            [curr_pos,found_y_pos] = [(ix,iy) for ix, row in enumerate(hyp_camel_track) for iy, i in enumerate(row) if i == selected_camel][0] #Find distance, check for traps
            stack = len(hyp_camel_track[curr_pos])-found_y_pos
            distance = move_dist

            stack_from_bottom = False
            if curr_pos + distance > finish_line:
                distance = finish_line - curr_pos
            if (len(g.trap_track[curr_pos + distance]) > 0):
                if g.trap_track[curr_pos + distance][0] == -1:
                    stack_from_bottom = True
                distance += g.trap_track[curr_pos + distance][0] #Change the distance

            camels_to_move = [] #Actually move camel
            
                #don't move camel if you've already crossed line
            if curr_pos > finish_line:
                    return hyp_camel_track			
                            
                    
            if stack_from_bottom: #stack from bottom if trap was -1
                for c in range(0,stack):
                    camels_to_move.append(hyp_camel_track[curr_pos].pop(stack-c-1))
                    hyp_camel_track[curr_pos + distance].insert(0,camels_to_move[0])
                    camels_to_move.clear()
                    
            else: #Stack normally         
                for c in range(0,stack):
                    camels_to_move.append(hyp_camel_track[curr_pos].pop(found_y_pos))
                    hyp_camel_track[curr_pos + distance].append(camels_to_move[0])
                    camels_to_move.clear()
                    
            return hyp_camel_track
        
        def FindCamelInNthPlace(track,n):
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
                    
        def CheckForGameWinners(camel_track,game_winners):
            winner_flag = False
            for i in range(finish_line,len(camel_track)):
                if len(camel_track[i]) > 0:
                    winning_camel = FindCamelInNthPlace(camel_track,1)
                    game_winners[winning_camel] += 1
                    winner_flag = True
            game_winners[5] += 1
            return [game_winners,winner_flag]

        def CheckForGameLosers(camel_track,game_losers):
            loser_camel = FindCamelInNthPlace(camel_track,5)
            game_losers[loser_camel] +=1
            game_losers[5] += 1
            return game_losers

        def check_bet(hashed_bet, user_bet):
            return hashed_bet == user_bet
            #TODO: Readd the hashing stuff
            bet, salt = hashed_bet.split(':')
            return bet == hashlib.sha256(salt.encode() + user_bet.encode()).hexdigest()

        #Calculate ending pos
        
        list_of_moves = []
        camels_to_move = []
        resulting_place = [[0,0,0] for i in range(5)]
        for i in range(0,len(g.camels)):
            if g.camel_yet_to_move[i] : camels_to_move.append(i)
        num_camels_to_move = len(camels_to_move)
        if display_updates: print("Camels to move : " + str(camels_to_move))
        if display_updates: print("num_camels_to_move : " + str(num_camels_to_move))
        for perm in permutations(camels_to_move,num_camels_to_move):
            for move_combinations in range(0,3**num_camels_to_move):
                hyp_camel_track = deepcopy(g.camel_track)
                for moves in range(0,num_camels_to_move):
                    dist_to_move = (floor(move_combinations/(3**moves))%3)+1
                    hyp_camel_track = MoveCamel(perm[moves],dist_to_move,hyp_camel_track,g)
                first_place_camel = FindCamelInNthPlace(hyp_camel_track,1)
                second_place_camel = FindCamelInNthPlace(hyp_camel_track,2)
                for camel_to_count in range(0,len(g.camels)):
                    if camel_to_count == first_place_camel : resulting_place[camel_to_count][2] += 1
                    elif camel_to_count == second_place_camel : resulting_place[camel_to_count][1] += 1
                    else : resulting_place[camel_to_count][0] += 1
                #[game_winners,game_winner_flag] = CheckForGameWinners(0,hyp_camel_track,game_winners)
        if display_updates: print(resulting_place)
        if display_updates: print(camels_to_move)

        #--------------#
        #-Round Winner-#
        #--------------#

        #Define aggresiveness
        #find nearness to end and dist from first place

        first_cam_weight = 0.9
        second_cam_weight = 0.07
        third_cam_weight = 0.03

        dist_scalar_1 = -0.2
        dist_scalar_2 = 0.0394
        dist_scalar_3 = 0.00288
        
        def dist_to_1st_weighter(delta):
            return (dist_scalar_1 + dist_scalar_2*delta + dist_scalar_3*delta**2)

        #nearness to end:
        #Closer to end, the larger the number gets. Goes from 0 to 1
        
        first_place_cam = FindCamelInNthPlace(g.camel_track,1)
        second_place_cam = FindCamelInNthPlace(g.camel_track,2)
        third_place_cam = FindCamelInNthPlace(g.camel_track,3)

        [first_cam_loc,found_y_pos] = [(ix,iy) for ix, row in enumerate(hyp_camel_track) for iy, i in enumerate(row) if i == first_place_cam][0]
        [second_cam_loc,found_y_pos] = [(ix,iy) for ix, row in enumerate(hyp_camel_track) for iy, i in enumerate(row) if i == second_place_cam][0]
        [third_cam_loc,found_y_pos] = [(ix,iy) for ix, row in enumerate(hyp_camel_track) for iy, i in enumerate(row) if i == third_place_cam][0]

        nearness_to_end = (first_cam_weight*first_cam_loc + second_cam_weight * second_cam_loc + third_cam_weight * third_cam_loc)/finish_line
        
        #dist from first place:
        #larger the delta between first place and yourself the larger the value. Roughly goes from 0 to 1

        max_delta = 0
        for money in g.player_money_values:
            delta = money - g.player_money_values[player]
            if delta > max_delta: max_delta = delta
        dist_to_first = dist_to_1st_weighter(max_delta)

        #if delta is high, nearness is high, bet big as possible
        #if delta is low, nearness is high, bet close to EV's
        #if delta is high, nearness is low, bet a tiny bit risky EV's
        #if delta is low, nearness is low, bet exactly EV

        #When delta is high -- then be riskier
        #When nearness is high -- then be riskier

        riskiness = (dist_to_first * nearness_to_end) #Could be modified. Could also be negative...
        if display_updates: print("riskiness : " + str(riskiness))

        #Find EV's of each move
        
        #Of the form ["syntax",functional EV]
        best_move = [[0],1]
        
        #Find EV's of round_bets:
        first_place_payout = [5,3,2,0]
        second_place_payout = [1,1,1,0]
        third_or_worse_place_payout = [-1,-1,-1,0]
        for i in range(0,len(g.camels)):
            payout_index = 0
            for bets in g.round_bets:
                if i == bets[0]: payout_index += 1
            if payout_index > 3 : payout_index = 3
            possible_moves = sum(resulting_place[0])
            chance_of_first = (resulting_place[i][2]/possible_moves)
            chance_of_second = (resulting_place[i][1]/possible_moves)
            chance_of_third = (resulting_place[i][0]/possible_moves)

            ev = (chance_of_first * first_place_payout[payout_index]) + (chance_of_second * second_place_payout[payout_index]) + (chance_of_third * third_or_worse_place_payout[payout_index])
            upshot = first_place_payout[payout_index]

            fEV = ev+riskiness*(upshot-ev)

            if display_updates: print("ev : " + str(ev))
            if display_updates: print("upshot : " + str(upshot))
            if display_updates: print("fEV : " + str(fEV))
            
            if fEV > best_move[1]:
                best_move[0] = [2,i]
                best_move[1] = fEV
        if display_updates: print(best_move)

        #--------------#
        #--Game Winner-#
        #--------------#
            
        #We are goign to do a maximum of futuresight checks
            
        #We are going to multiply the EV by the nearness_to_end so we have more certainty. Maybe even nearness^2
        #For game winner we are going to use the distance between first and second
        #For game loser we use the dist between last and 2nd to last? This sucks. We want prob that they win the game, not much else

        game_winners = [0 for i in range(6)]
        game_losers = [0 for i in range(6)]
        future_sight = 10000
        future_sight = 200
        depth_cap = 35	
        depth_cap = 4
        for futurecycles in range(0,future_sight):
            winner_flag = False
            track = deepcopy(hyp_camel_track)
            camel_bank = camels_to_move

            depth = 0
            while not winner_flag and (depth < depth_cap):
                if len(camel_bank) == 0:
                    camel_bank = [0,1,2,3,4]
                moving_index = random.randint(0,len(camel_bank)-1)
                moving_boy = camel_bank[moving_index]
                del camel_bank[moving_index]
                boy_distance = random.randint(1,3)
                track = MoveCamel(moving_boy,boy_distance,track,g)

                [game_winners,winner_flag] = CheckForGameWinners(track,game_winners)
                depth += 1          
            game_losers = CheckForGameLosers(track,game_losers)
            
        #Operate on these things i have now... doing little tests to see whats if I should bet or not
            
        #Then do a bit of riskiness stuff in here too... if you are super risky then go for broke
        

        #Remove all that you've already bet on
        for sus_camel in range(0,5):
            for i in range(0,len(g.player_game_bets[player])):
                if check_bet(g.player_game_bets[player][i],str(sus_camel)):
                    game_winners[sus_camel] = 0
                    game_losers[sus_camel] = 0

        
        #GameWinners EV
        runs = game_winners[5]
        del game_winners[5]
        frontrunner = game_winners.index(max(game_winners))
        chance = game_winners[frontrunner] / runs

        #higher the chance to win, the lower the likely payout.

        dim_return = len(g.game_winner_bets)*chance
        x = dim_return + 1
        payout = 0.42857*x**2 - 4.37143*x + 12

        ev = payout * chance - (1-chance)
        upshot = 8

        fEV = ev+riskiness*(upshot-ev)

        if display_updates: print("ev : " + str(ev))
        if display_updates: print("upshot : " + str(upshot))
        if display_updates: print("fEV : " + str(fEV))
        
        if fEV > best_move[1]:
            best_move[0] = [3,frontrunner]
            best_move[1] = fEV
   

        #GameLosers EV
        runs = game_losers[5]
        del game_losers[5]
        backrunner = game_losers.index(max(game_losers))
        chance = game_losers[backrunner] *nearness_to_end / runs
        #higher the chance to win, the lower the likely payout.

        dim_return = len(g.game_loser_bets)*chance
        x = dim_return + 1
        payout = 0.42857*x**2 - 4.37143*x + 12

        ev = payout * chance - (1-chance)
        upshot = 8

        fEV = ev+riskiness*(upshot-ev)

        if display_updates: print("ev : " + str(ev))
        if display_updates: print("upshot : " + str(upshot))
        if display_updates: print("fEV : " + str(fEV))
        
        if fEV > best_move[1]:
            best_move[0] = [4,backrunner]
            best_move[1] = fEV
        
        return best_move[0]