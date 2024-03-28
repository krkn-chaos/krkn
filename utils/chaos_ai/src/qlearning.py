import logging

import numpy as np


class QLearning:
    def __init__(self, gamma=None, alpha=None, faults=None, states=None, rewards=None, urls=None):
        self.gamma = gamma  # Discount factor
        self.alpha = alpha  # Learning rate
        self.faults = faults
        self.states = states
        self.rewards = rewards

        # Initializing Q-Values
        # self.Q = np.array(np.zeros([len(states), len(states)]))
        self.Q = np.array(np.zeros([len(urls), len(states), len(faults)]))
        self.state_matrix = np.array(np.zeros([len(states), len(states)]))

        self.logger = logging.getLogger()

    def update_q_fault(self, fault, episode, start_state, end_state, url_index):
        self.logger.info('[UPDATE_Q] ' + str(url_index) + ' ' + fault + ' ' + str(start_state) + '->' + str(end_state))
        if end_state is None:
            end_state = start_state
        if end_state not in self.states:
            end_state = 'Other'
        # reward is dependent on the error response (eg. '404') and length of episode
        reward = self.rewards[str(end_state)] / len(episode)
        current_state = self.states[str(start_state)]
        next_state = self.states[str(end_state)]
        fault_index = self.faults.index(fault)
        # self.logger.debug('[update_q]' + fault + ' ' + str(fault_index) + ' ' + str(reward))
        # self.logger.debug('reward, gamma: ' + str(reward) + ' ' + str(self.gamma))
        # self.logger.debug(
        #     'gamma*val' + str(self.gamma * self.Q[url_index, next_state, np.argmax(self.Q[url_index, next_state,])]))
        # self.logger.debug('current state val:' + str(self.Q[url_index, current_state, fault_index]))

        TD = reward + \
             self.gamma * self.Q[url_index, next_state, np.argmax(self.Q[url_index, next_state,])] - \
             self.Q[url_index, current_state, fault_index]
        self.Q[url_index, current_state, fault_index] += self.alpha * TD

        # update state matrix
        TD_state = reward + \
                   self.gamma * self.state_matrix[next_state, np.argmax(self.state_matrix[next_state,])] - \
                   self.state_matrix[current_state, next_state]
        self.state_matrix[current_state, next_state] += self.alpha * TD_state
        # self.logger.debug('updated Q' + str(self.Q[url_index, current_state, fault_index]))

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
