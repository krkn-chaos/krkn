import json
import os
import random
import sys

import numpy as np
import logging


class AIChaos:
    def __init__(self, states=None, faults=None, rewards=None, pod_names=[], chaos_dir=None,
                 chaos_experiment='experiment.json',
                 chaos_journal='journal.json', iterations=1000, static_run=False):
        self.faults = faults
        self.pod_names = pod_names
        self.states = states
        self.rewards = rewards
        self.episodes = []

        self.chaos_dir = chaos_dir
        self.chaos_experiment = chaos_experiment
        self.chaos_journal = chaos_journal

        self.iterations = iterations
        # Initialize parameters
        self.gamma = 0.75  # Discount factor
        self.alpha = 0.9  # Learning rate

        # Initializing Q-Values
        # self.Q = np.array(np.zeros([9, 9]))
        # self.Q = np.array(np.zeros([len(faults), len(faults)]))
        # currently action is a single fault, later on we will do multiple faults together
        # For multiple faults, the no of cols in q-matrix will be all combinations of faults (infinite)
        # eg. {f1,f2},f3,f4,{f4,f5} - f1,f2  in parallel, then f3, then f4,  then f4,f5 in parallel produces end state
        # self.Q = np.array(np.zeros([len(states), len(states)]))
        self.Q = np.array(np.zeros([len(states), len(faults)]))
        self.state_matrix = np.array(np.zeros([len(states), len(states)]))

        # may be Q is a dictionary of dictionaries, for each state there is a dictionary of faults
        # Q = {'500' = {'f1f2f4': 0.3, 'f1':  0.5}, '404' = {'f2': 0.22}}

        self.logger = logging.getLogger()
        # run from old static experiment and journal files
        self.static_run = static_run

    # End state is reached when system is down or return error code like '500','404'
    def get_next_state(self):
        self.logger.info('[GET_NEXT_STATE]')
        with open(self.chaos_dir + self.chaos_journal) as f:
            data = json.load(f)

        # before the experiment (if before steady state is false, after is null?)
        for probe in data['steady_states']['before']['probes']:
            if not probe['tolerance_met']:
                # start_state = probe['activity']['tolerance']
                # end_state = probe['status']
                start_state, end_state = None, None
                return start_state, end_state

        # after the experiment
        for probe in data['steady_states']['after']['probes']:
            # if probe['output']['status'] == probe['activity']['tolerance']:
            if not probe['tolerance_met']:
                # print(probe)
                start_state = probe['activity']['tolerance']
                end_state = probe['output']['status']
                # end_state = probe['status']
                return start_state, end_state
        # if tolerances for all probes are met
        start_state = probe['activity']['tolerance']
        end_state = probe['activity']['tolerance']
        return start_state, end_state

    def inject_faults(self, fault, pod_name):
        self.logger.info('[INJECT_FAULT] ' + fault)
        with open(self.chaos_dir + self.chaos_experiment) as f:
            data = json.load(f)
        for m in data['method']:
            if 'provider' in m:
                if fault == 'kill_microservice':
                    m['name'] = 'kill-microservice'
                    m['provider']['module'] = 'chaosk8s.actions'
                    m['provider']['arguments']['name'] = pod_name
                else:
                    m['provider']['arguments']['name_pattern'] = pod_name
                m['provider']['func'] = fault

                print('[INJECT_FAULT] method:', m)
                # self.logger.info('[INJECT_FAULT] ' + m['provider']['arguments']['name_pattern'])
                # self.logger.info('[INJECT_FAULT] ' + str(m))

        exp_file = self.chaos_dir + 'experiment_' + str(random.randint(1, 10)) + '.json'
        with open(exp_file, 'w') as f:
            json.dump(data, f)
        exp_file = self.chaos_dir + 'experiment.json'
        # execute faults
        # cmd = 'cd ' + self.chaos_dir + ';chaos run ' + self.chaos_experiment
        cmd = 'cd ' + self.chaos_dir + ';chaos run ' + exp_file
        if not self.static_run:
            os.system(cmd)

    def create_episode(self):
        self.logger.info('[CREATE_EPISODE]')
        episode = []
        while True:
            # inject more faults
            # TODO: model - choose faults based on q-learning ...
            fault_pod = random.choice(self.faults)
            fault = fault_pod.split(':')[0]
            pod_name = fault_pod.split(':')[1]
            # fault = random.choice(self.faults)
            # pod_name = random.choice(self.pod_names)
            # fault = lstm_model.get_next_fault(episode)
            # fault = get_max_prob_fault(episode)

            self.inject_faults(fault, pod_name)
            start_state, next_state = self.get_next_state()
            print('[CREATE EPISODE]', start_state, next_state)
            # if before state tolerance is not met
            if start_state is None and next_state is None:
                continue

            episode.append({'fault': fault, 'pod_name': pod_name})
            self.update_q_fault(fault_pod, episode, start_state, next_state)
            # self.update_q_fault(fault, episode, start_state, next_state)
            # if an end_state is reached
            # if next_state is not None:
            if start_state != next_state:
                self.logger.info('[CREATE_EPISODE] EPISODE CREATED:' + str(episode))
                self.logger.info('[CREATE_EPISODE] END STATE:' + str(next_state))
                return episode, start_state, next_state

    def update_q_fault(self, fault, episode, start_state, end_state):
        self.logger.info('[UPDATE_Q]')
        print('[UPDATE_Q] ', str(start_state), str(end_state))
        if end_state is None:
            end_state = start_state

        # reward is dependent on the error response (eg. '404') and length of episode
        reward = self.rewards[str(end_state)] / len(episode)
        current_state = self.states[str(start_state)]
        next_state = self.states[str(end_state)]
        fault_index = self.faults.index(fault)

        TD = reward + \
             self.gamma * self.Q[next_state, np.argmax(self.Q[next_state,])] - \
             self.Q[current_state, fault_index]
        self.Q[current_state, fault_index] += self.alpha * TD

        # update state matrix
        TD_state = reward + \
                   self.gamma * self.state_matrix[next_state, np.argmax(self.state_matrix[next_state,])] - \
                   self.state_matrix[current_state, next_state]
        self.state_matrix[current_state, next_state] += self.alpha * TD_state

    # def update_q(self, episode, start_state, end_state):
    #     self.logger.info('[UPDATE_Q]')
    #     if end_state is None:
    #         end_state = start_state
    #
    #     # reward is dependent on the error response (eg. '404') and length of episode
    #     reward = self.rewards[str(end_state)] / len(episode)
    #     current_state = self.states[str(start_state)]
    #     next_state = self.states[str(end_state)]
    #     TD = reward + \
    #          self.gamma * self.Q[next_state, np.argmax(self.Q[next_state,])] - \
    #          self.Q[current_state, next_state]
    #     self.Q[current_state, next_state] += self.alpha * TD

    def start_chaos(self):
        for i in range(self.iterations):
            episode, start_state, end_state = self.create_episode()
            # update Q matrix
            # will do it with each fault injection
            # self.update_q(episode, start_state, end_state)
            print(self.Q)
            print(self.state_matrix)


def test_chaos():
    svc_list = ['cart', 'catalogue', 'dispatch', 'mongodb', 'mysql', 'payment', 'rabbitmq', 'ratings', 'redis',
                'shipping', 'user', 'web']
    # Define faults
    # faults = ['terminate_pods']
    #     faults = ['terminate_pods:' + x for x in pod_names]
    faults = ['kill_microservice:' + x for x in svc_list]
    # Define the states
    states = {
        '200': 0,
        '500': 1,
        '404': 2
    }
    # Define rewards, currently not used
    rewards = {
        '200': 0,
        '500': 0.8,
        '404': 1
    }

    # cdir = '/Users/sandeephans/Downloads/chaos/chaostoolkit-samples-master/service-down-not-visible-to-users/'
    cdir = '/Users/sandeephans/Downloads/openshift/'
    cexp = 'experiment.json'
    cjournal = 'journal.json'

    aichaos = AIChaos(states=states, faults=faults, rewards=rewards,
                      chaos_dir=cdir, chaos_experiment=cexp, chaos_journal=cjournal,
                      static_run=False)
    aichaos.start_chaos()


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    test_chaos()
