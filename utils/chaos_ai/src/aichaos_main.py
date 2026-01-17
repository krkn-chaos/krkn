import json
import os
import random

import numpy as np
import pandas as pd
import logging

# sys.path.insert(1, os.path.join(sys.path[0], '..'))
import src.utils as utils
from src.kraken_utils import KrakenUtils
from src.qlearning import QLearning
from src.test_application import TestApplication


class AIChaos:
    def __init__(self, namespace='robot-shop', states=None, faults=None, rewards=None, urls=None, max_faults=5,
                 service_weights=None, ctd_subsets=None, pod_names=None, chaos_dir='../config/', kubeconfig='~/.kube/config',
                 chaos_experiment='experiment.json', logfile='log', qfile='qfile.csv', efile='efile', epfile='episodes.json',
                 loglevel=logging.INFO,
                 chaos_journal='journal.json', iterations=10, alpha=0.9, gamma=0.2, epsilon=0.3,
                 num_requests=10, sleep_time=1, timeout=2, chaos_engine='kraken', dstk_probes=None,
                 static_run=False, all_faults=False, command='podman'):
        if urls is None:
            urls = []
        if pod_names is None:
            pod_names = []
        self.namespace = namespace
        self.faults = faults
        self.unused_faults = faults.copy()
        self.all_faults = all_faults
        self.pod_names = pod_names
        self.states = states
        self.rewards = rewards
        self.urls = urls
        self.max_faults = max_faults
        self.episodes = []
        self.service_weights = service_weights
        self.ctd_subsets = ctd_subsets

        self.kubeconfig = kubeconfig
        self.chaos_dir = chaos_dir
        self.chaos_experiment = chaos_experiment
        self.chaos_journal = chaos_journal
        self.command = command

        if chaos_engine == 'kraken':
            self.chaos_engine = KrakenUtils(namespace, kubeconfig=kubeconfig, chaos_dir=chaos_dir, chaos_experiment=chaos_experiment, command=self.command)
        else:
            self.chaos_engine = None

        self.iterations = iterations
        # Initialize RL parameters
        self.epsilon = epsilon  # epsilon decay policy
        # self.epsdecay = 0

        # log files
        self.logfile = logfile
        self.qfile = qfile
        self.efile = efile
        self.epfile = epfile
        open(efile, 'w+').close()
        open(logfile, 'w+').close()
        open(logfile, 'r+').truncate(0)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.basicConfig(filename=logfile, filemode='w+', level=loglevel)
        self.logger = logging.getLogger(logfile.replace('/',''))
        self.logger.addHandler(logging.FileHandler(logfile))

        self.testapp = TestApplication(num_requests, timeout, sleep_time)
        self.ql = QLearning(gamma, alpha, faults, states, rewards, urls)

        # run from old static experiment and journal files
        self.static_run = static_run

    def realistic(self, faults_pods):
        self.logger.debug('[Realistic] ' + str(faults_pods))
        fp = faults_pods.copy()
        for f1 in faults_pods:
            for f2 in faults_pods:
                if f1 == f2:
                    continue
                if f1 in fp and f2 in fp:
                    f1_fault, load_1 = utils.get_load(f1.split(':')[0])
                    f1_pod = f1.split(':')[1]
                    f2_fault, load_2 = utils.get_load(f2.split(':')[0])
                    f2_pod = f2.split(':')[1]
                    if f1_pod == f2_pod:
                        if f1_fault == 'pod-delete':
                            fp.remove(f2)
                        if f1_fault == f2_fault:
                            # if int(load_1) > int(load_2):
                            # randomly remove one fault from same faults with different params
                            fp.remove(f2)
        if self.service_weights is None:
            return fp

        fp_copy = fp.copy()
        for f in fp:
            f_fault = f.split(':')[0]
            f_pod = f.split(':')[1].replace('service=', '')
            self.logger.debug('[ServiceWeights] ' + f + ' ' + str(self.service_weights[f_pod][f_fault]))
            if self.service_weights[f_pod][f_fault] == 0:
                fp_copy.remove(f)

        self.logger.debug('[Realistic] ' + str(fp_copy))
        return fp_copy

    def select_faults(self):
        max_faults = min(self.max_faults, len(self.unused_faults))
        num_faults = random.randint(1, max_faults)
        if self.all_faults:
            num_faults = len(self.unused_faults)
        if random.random() > self.epsilon:
            self.logger.info('[Exploration]')
            # faults_pods = random.sample(self.faults, k=num_faults)
            # using used faults list to avoid starvation
            faults_pods = random.sample(self.unused_faults, k=num_faults)
            faults_pods = self.realistic(faults_pods)
            for f in faults_pods:
                self.unused_faults.remove(f)
            if len(self.unused_faults) == 0:
                self.unused_faults = self.faults.copy()
        else:
            self.logger.info('[Exploitation]')
            first_row = self.ql.Q[:, 0, :][0]
            top_k_indices = np.argpartition(first_row, -num_faults)[-num_faults:]
            faults_pods = [self.faults[i] for i in top_k_indices]
            faults_pods = self.realistic(faults_pods)

        return faults_pods

    def create_episode(self, ctd_subset=None):
        self.logger.debug('[CREATE_EPISODE]')
        episode = []

        if ctd_subset is None:
            faults_pods = self.select_faults()
        else:
            faults_pods = ctd_subset
            self.logger.info('CTD Subset: ' + str(faults_pods))

        # faults_pods = self.realistic(faults_pods)
        if len(faults_pods) == 0:
            return [], 200, 200

        engines = []
        for fp in faults_pods:
            fault = fp.split(':')[0]
            pod_name = fp.split(':')[1]
            engine = self.chaos_engine.inject_faults(fault, pod_name)
            engines.append(engine)
            episode.append({'fault': fault, 'pod_name': pod_name})
        self.logger.info('[create_episode]' + str(faults_pods))
        engines_running = self.chaos_engine.wait_engines(engines)
        self.logger.info('[create_episode] engines_running' + str(engines_running))
        if not engines_running:
            return None, None, None

        # randomly shuffling urls 
        urls = random.sample(self.urls, len(self.urls))
        ep_json = []
        for url in urls:
            start_state, next_state = self.testapp.test_load(url)
            self.logger.info('[CREATE EPISODE]' + str(start_state) + ',' + str(next_state))
            # if before state tolerance is not met
            if start_state is None and next_state is None:
                # self.cleanup()
                self.chaos_engine.stop_engines()
                continue

                ### episode.append({'fault': fault, 'pod_name': pod_name})
                # self.update_q_fault(fault_pod, episode, start_state, next_state)
            url_index = self.urls.index(url)
            self.logger.info('[CREATEEPISODE]' + str(url) + ':' + str(url_index))
            for fp in faults_pods:
                self.ql.update_q_fault(fp, episode, start_state, next_state, self.urls.index(url))
            ep_json.append({'start_state': start_state, 'next_state': next_state, 'url': url, 'faults': episode})

        self.logger.debug('[CREATE_EPISODE] EPISODE CREATED:' + str(episode))
        self.logger.debug('[CREATE_EPISODE] END STATE:' + str(next_state))

        self.chaos_engine.print_result(engines)
        self.chaos_engine.stop_engines(episode=episode)
        # ep_json = {'start_state': start_state, 'next_state': next_state, 'faults': episode}

        return ep_json, start_state, next_state

    def start_chaos(self):
        self.logger.info('[INITIALIZING]')
        self.logger.info('Logfile: '+self.logfile)
        self.logger.info('Loggerfile: '+self.logger.handlers[0].stream.name)
        self.logger.info('Chaos Engine: ' + self.chaos_engine.get_name())
        self.logger.debug('Faults:' + str(self.faults))

        self.chaos_engine.cleanup()
        if self.ctd_subsets is None:
            for i in range(self.iterations):
                episode, start_state, end_state = self.create_episode()
                self.logger.debug('[start_chaos]' + str(i) + ' ' + str(episode))
                if episode is None:
                    continue
                # update Q matrix
                # will do it with each fault injection
                # self.update_q(episode, start_state, end_state)
                # if episode['next_state'] != '200':
                self.episodes.extend(episode)
                self.logger.info(str(i) + ' ' + str(self.ql.Q[:, 0]))
                # print(i, self.state_matrix)
                self.write_q()
                self.write_episode(episode)
        else:
            for i, subset in enumerate(self.ctd_subsets):
                episode, start_state, end_state = self.create_episode(subset)
                self.logger.debug('[start_chaos]' + str(episode))
                if episode is None:
                    continue
                self.episodes.append(episode)
                self.logger.info(str(i) + ' ' + str(self.ql.Q[:, 0]))
                self.write_q()
                self.write_episode(episode)

        self.chaos_engine.cleanup()
        # self.remove_temp_file()
        with open(self.epfile, 'w', encoding='utf-8') as f:
            json.dump(self.episodes, f, ensure_ascii=False, indent=4)
        self.logger.info('COMPLETE!!!')

    def write_q(self):
        df = pd.DataFrame(self.ql.Q[:, 0, :], index=self.urls, columns=self.faults)
        df.to_csv(self.qfile)
        return df

    def write_episode(self, episode):
        for ep in episode:
            with open(self.efile, "a") as outfile:
                x = [e['fault'] + ':' + e['pod_name'] for e in ep['faults']]
                x.append(ep['url'])
                x.append(str(ep['next_state']))
                outfile.write(','.join(x) + '\n')

    def remove_temp_file(self):
        mydir = self.chaos_dir + 'experiments'
        print('Removing temp files from: '+mydir)
        self.logger.debug('Removing temp files: '+mydir)
        if os.path.exists(mydir):
            return
        filelist = [f for f in os.listdir(mydir) if f.endswith(".json")]
        for f in filelist:
            print(f)
            os.remove(os.path.join(mydir, f))
