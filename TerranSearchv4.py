#Naive implementation
# workers don't need to move
# units are bound by population limit

# thrifty algorithm: if there are resources, they are going to be spent
# two timers - vespin and minerals
import copy
import math
from typing import List
from actions import *
from Triggers import *
from ActionStatev0 import Status
import landmarklowerbound as LLB


class Goal:
    def __init__(self, name,count,weight = 1):
        self.name = name
        self.weight = weight
        self.count = count

class Plan:
    def __init__(self,timeline):
        self.plan = []
        for a in timeline:
            z = copy.deepcopy(a)
            z.finished = True
            self.plan += [z]

        if len(self.plan) > 0:
            self.time = timeline[len(timeline)-1].end_time
        else:
            self.time = 0

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        out = "["
        for a in self.plan:
            out += str(a) + ","
        out += "]"
        return out

    def __iter__(self):
        return self.plan.__iter__()


class MockPlan:
    def __init__(self, time: int, distance: int):
        self.distance = distance
        self.time = time

    def __str__(self):
        return "Mock Plan ("+str(self.time)+","+str(self.distance)+")"


class Timeline: #objekt pro držení pořadí akcí podle času ukončení

    def __init__(self, type):
        self.actions = [] #TODO iplementace jako strom
        self.key = Timeline.get_end
        if type == "sf":
            self.key = Timeline.get_start
    @staticmethod
    def get_end(elem):
        return elem.end_time

    @staticmethod
    def get_start(elem):
        return elem.start.time

    def add_action(self, action):
        self.actions += [action]
        self.actions = sorted(self.actions, key=self.key)

    def delete(self, action):
        self.actions.remove(action)
        self.actions = sorted(self.actions, key=self.key)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        out = "["
        for a in self.actions:
            out += str(a) + ","
        out += "]"
        return out

    def __getitem__(self, item):
        if item >= len(self.actions): raise IndexError("Out of bounds")
        return self.actions[item]

    def __len__(self):
        return len(self.actions)


class TimePoint:
    def __init__(self):
        self.current_point = 0


class PlanningWindow: #ukládání plánu v časové souvislosti

    def __init__(self, timeline=Timeline("ef")):
        self.time = 0
        self.last_done = -1
        self.finish_time = 0
        self.time_line = timeline #invariant: akce s menším indexem končí dřív
        self.a_order = [] #ukládá akce v pořadí v němž byly naplánovány. tj. řazení dle času začátku

    def _plan_action(self, act: ScheduledAction):
        self.time_line.add_action(act)
        self.a_order.append(act)

    def plan_action(self, act: ScheduledAction):
        self._plan_action(act)
        self.time = act.start_time
        return act

    def plan_finished_action(self, act: ScheduledAction): #TODO: Je potřeba zavolat finish
        self._plan_action(act)
        self.time = act.end_time
        return act

    def get_potential(self):
        if (len(self.time_line)>1):
            return self.time_line[len(self.time_line)-1].end_time
        else: return 0

    def get_plan(self):

        return Plan(self.time_line)

    def unplan_action(self, action: ScheduledAction):
        self.time_line.delete(action)
        self.a_order.remove(action)
        #self.time = action.start_time

    def last(self):
        if len(self.a_order)<1: return None
        action = self.a_order[len(self.a_order)-1]
        return action

    def __str__(self):
        return str(self.time_line)

    def first2finish(self): #vrací

        if not(self.last_done+1 < len(self.time_line)): return self.time

        return self.time_line[self.last_done+1].end_time

    def rewind_to(self, time):
        opened_actions = []
        self.time = time
        for i in range(len(self.time_line)-1, -1, -1):

            if self.time_line[i].end_time <= time:
                self.last_done = i
                break
            z = self.time_line[i]
            opened_actions += [z]
        return opened_actions

    def finish_everything_prior(self,time):
        finish_list = []
        if time < self.time: raise RuntimeError("Action Finishing: Cannot go back in time!")

        for i in range(len(self.time_line)):
            a=self.time_line[i]
            if a.end_time <= time and not a.finished:
                finish_list += [a]
                a.finished = True
                self.last_done = i

        self.time = time
        return finish_list

class Game:

    def __init__(self, init_state: Status, actions: ActionPool, heuristic_graph, max_bounds = {}):
        self.window = PlanningWindow()
        self.w_calendar = {}
        self.state = init_state
        self.action_pool = actions
        self.action_pool.connect(self.state)
       # self.triggers = a_triggers
        self.max_bounds = max_bounds
        self.h_max = heuristic_graph
        self.node_count = 0
        self.finished_branches = 0
        self.good_branches = 0

    def CT(self):
        return self.window.time

    def is_over_bounds(self):
        for u in self.max_bounds:
            if u not in self.state.unaries:
                continue
            if self.state.unaries[u].shadow > self.max_bounds[u]:
                return True
        return False

    def unplan_last(self):
        action = self.window.unplan_last()
        self.state.unplan_action(action)

    def goal_metrics(self, goals):
        plan_distance = 0
        minerals = 0
        vespin = 0

        for g in goals:
            progress = self.state.check(g)
            # isdone?
            plan_distance += progress
            minerals += self.action_pool.by_name[g.name].minerals * progress
            vespin += self.action_pool.by_name[g.name].vespin * progress
        return plan_distance, minerals, vespin

    def update(self,goals):
        self.action_pool.refresh()
        return self.goal_metrics(goals)

    def planable_actions(self):
        assert self.action_pool.plannable is not None
        return self.action_pool.plannable

    def refresh(self, old_time):
        #print("Timeshift: "+str(old_time)+"/"+str(self.CT()))
        assert old_time <= self.CT()
        self.state.get_to(self.CT())
        #print("Akce: "+ repr(self.window.time_line))
        return self.window.finish_everything_prior(self.CT())

    def finish_actions(self,actions):
        for a in actions:
            a.finish = True
            #self.state.end_action(a)

    def time_shift(self, new_time):
        self.window.time = new_time

    def plan_next_action(self, action: Action):
        sch_a = self.__plan_acton(action)
        self.window.plan_action(sch_a)
        return self.CT() #TODO:

    def __plan_acton(self,action):
        surplus_time = self.state.project(action.minerals, action.vespin)
        sch_a = action.schedule(self.CT())
        sch_a.add_time(surplus_time)
        self.state.plan_action(sch_a)
        return sch_a

    def check_triggers(self,action)->List[Action]:
        response = []
        for t in self.triggers:
            act = self.triggers[t].validate(action)
            if not (act is None): response += [act]

        return response

    def plan_finished_action(self, action: Action):
        sch_a = self.__plan_acton(action)
        self.window.plan_finished_action(sch_a)
        return self.CT()

    def first_finished_time(self):
        return self.window.first2finish()

    def reverse(self,time): #finished action

        self.state.return_to(time)
        actions = self.window.rewind_to(time)
        #print("Dude!"+str(actions))
        last = self.window.last()


        """for a in actions:
            if a.start_time <= time:  # multiple undoing
                pass
            else:
                print(actions)
                print(last)
                raise AssertionError
                self.state.unplan_action(a)
                self.window.unplan_action(a)
        #if last not in actions or last.start_time == time:"""

        self.state.unplan_action(last)
        self.window.unplan_action(last)

    def get_plan(self, distance):
        #print (self.state.unaries)
        return self.window.get_plan()

    def potential_end(self, minerals, vespin, goals):
        one_end = self.window.get_potential() + self.state.project_h(minerals,vespin)
        simple_state = set()
        simple_goals = set()
        for u in self.state.unaries:
            if self.state.unaries[u].shadow > 0: simple_state.add(u)
        for g in goals:
            simple_goals.add(g.name)
        second_end = self.window.get_potential() + self.h_max.h(simple_state,simple_goals)
        return max(second_end,one_end)

def betterplan(planA, planB):
    print("A:"+str(planA.time)+" B:"+str(planB.time))
    return planA.time <= planB.time



def AstarSearch(game: Game, actions: ActionPool, goals:List[Goal]):
    step = actions.max_duration()
    min = actions.min_duration()
    base = 0
    for g in goals:
        base += g.count*step
    ub_time = 70000#1 + base
    base = 7000
    state = game.state
    plan_distance=0
    for g in goals:
        progress = state.check(g)
        if progress <= 0:
            goals.remove(g)
        plan_distance += progress

    bestplan = MockPlan(0,plan_distance)
    stop_signal = False
    while (not stop_signal) and (type(bestplan) is MockPlan):
        print("----------------------------------------------------------------------")
        bestplan,stop_signal = AStarDFS(game, goals, 0, ub_time, 5, plan_distance)
        ub_time += base
    return bestplan


def AStarDFS(game: Game, goals, current_time, ub_time, depth: int, ub_distance):
    #print(game.window)
    #print("Some Word:"+str(game.state))
    game.node_count += 1
    besttime=ub_time
    depth2=depth-1
    goal_distance, minerals_vol, vespin_vol = game.update(goals) #distance of every childnode  <= goal_distance
    bestsignal = True
    best_distance = goal_distance
    bestplan = MockPlan(ub_time, best_distance)



    if game.is_over_bounds():
        print("Dosáhli jsme maximálních hranice")
        game.finished_branches += 1
        return MockPlan(ub_time,goal_distance),True

    #if (depth <= 0 ):
    #   print("Limitní čas...")
    #   return MockPlan(ub_time,goal_distance)#něco co není potenciál
    plan_act = game.action_pool
    if len(plan_act) == 0:
        print("Slepá ulička")
        game.finished_branches += 1
        return MockPlan(ub_time, goal_distance),True

    potential = game.potential_end(minerals_vol,vespin_vol,goals)
    if (potential >= ub_time):
        print("Limitní čas...")
        game.finished_branches += 1
        return MockPlan(potential,goal_distance),False #něco co není potenciál

    if goal_distance <= 0:
        print("Vyhráli jsme!")
        plan = game.get_plan(goal_distance)
        print(plan)
        print(game.state)
        game.finished_branches +=1
        game.good_branches += 1
        return plan, True
    goals2 = goals
    #planovatelné akce od tohoto okamžiku
    for a in plan_act:
        # finished
       # response_actions = game.check_triggers(a)
        new_current_time = game.plan_finished_action(a)
       # for n_a in response_actions:
        #    game.plan_next_action(a)
        finished_actions = game.refresh(current_time)
        game.finish_actions(finished_actions)

        plan,signal = AStarDFS(game, goals2, new_current_time, besttime, depth2,best_distance)
        if besttime > plan.time:
            #print("Changing best plan" + str(depth) + "-" + str(besttime) + str(bestplan) + "/" + str(plan))
            bestplan = plan
            besttime = plan.time
        bestsignal = bestsignal and signal
        game.reverse(current_time)
        #game.unplan_last()

        surplus = game.state.project(a.minerals,a.vespin)
        was_in_range = False
        for b in plan_act:
            # cena b < (stav po zaplacení a) + (minerály získáné po dobu trvání a)
            if (b.minerals < (game.state.minerals - a.minerals) + game.state.wait_minerals(a.duration+surplus ,int(game.state.unaries["Worker"])) and
                b.vespin < (game.state.vespin - a.vespin) + game.state.wait_vespin(a.duration + surplus,
                                                                                           int(game.state.unaries["Worker"]))):
                was_in_range = True
        if was_in_range:
        #unfinished
           # response_actions = game.check_triggers(a)
            new_current_time = game.plan_next_action(a)
            #for n_a in response_actions:
            #    game.plan_next_action(a)
            finished_actions = game.refresh(current_time)
            game.finish_actions(finished_actions)
            #print("Dem dovnitř!")
            plan,signal = AStarDFS(game, goals2, new_current_time, besttime,depth2,best_distance)
            if besttime > plan.time :
                #print("Changing best plan"+str(depth)+"-"+str(besttime)+str(bestplan)+"/"+str(plan))
                bestplan = plan
                besttime = plan.time
            bestsignal = bestsignal and signal
            #print(game.state.unaries)
            #print("Dem ven! - "+str(current_time))

            #game.unplan_last()
            game.reverse(current_time)
            #print(game.state.unaries)

    return bestplan,bestsignal