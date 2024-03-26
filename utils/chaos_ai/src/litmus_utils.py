import json
import os
import time
import logging

import src.utils as utils


class LitmusUtils:
    def __init__(self, namespace='robot-shop', chaos_dir='../config/',
                 chaos_experiment='experiment.json'):
        self.chaos_dir = chaos_dir
        self.chaos_experiment = chaos_experiment
        self.namespace = namespace
        self.logger = logging.getLogger()

    def exp_status(self, engine='engine-cartns3'):
        cmd = 'kubectl describe chaosengine ' + engine + ' -n ' + self.namespace + ' | grep "    Status:"'
        line = os.popen(cmd).read()
        # cmd = 'kubectl describe chaosengine '+engine+' -n robot-shop | grep "    Status:" > temp'
        # os.system(cmd)
        # with open("temp", 'r') as f:
        #    line = f.readline()
        status = line.split(':')
        if len(status) > 1:
            self.logger.debug('[exp_status]' + engine + ':' + status[1].strip())
            return status[1].strip()
        self.logger.debug('[exp_status] Not Running! ' + line)
        return 'Not Running'

    # print chaos result, check if litmus showed any error
    def print_result(self, engines):
        # self.logger.debug('')
        for e in engines:
            cmd = 'kubectl describe chaosresult ' + e + ' -n ' + self.namespace + ' | grep "Fail Step:"'
            line = os.popen(cmd).read()
            self.logger.debug('[Chaos Result] '+e+' : '+line)

    def wait_engines(self, engines=[]):
        status = 'Completed'
        max_checks = 20
        for e in engines:
            self.logger.info('[status] ' + e)
            for i in range(max_checks):
                status = self.exp_status(e)
                if status == 'Running':
                    break
                time.sleep(1)
            # return False, if even one engine is not running
            if status != 'Running':
                return False

        # return True if all engines are running
        return True

    def experiment(self, exp_file):
        cmd = 'kubectl apply -f ' + exp_file + ' -n ' + self.namespace
        os.system(cmd)

    def cleanup(self):
        self.logger.debug('Removing previous engines')
        cmd = 'kubectl delete chaosengine,chaosresults --all -n ' + self.namespace
        os.system(cmd)
        self.logger.debug('Engines removed')

    def stop_engines(self, episode=[]):
        self.cleanup()
        # cmd = "kubectl patch chaosengine engine-cartns3 -n robot-shop --type merge --patch '{"spec":{"engineState":"stop"}}'"
        # for e in engines:
        #    cmd = 'kubectl patch chaosengine ' + e + ' -n robot-shop --type merge --patch \'{"spec":{"engineState":"stop"}}\''
        #    print(cmd)
        #    os.system(cmd)

    def get_name(self):
        return 'litmus'

    def inject_faults(self, fault, pod_name):
        # pod_name = 'service=cart'
        self.logger.debug('[INJECT_FAULT] ' + fault + ':' + pod_name)
        fault, load = utils.get_load(fault)
        f = open(self.chaos_dir + self.chaos_experiment[fault])
        data = json.load(f)
        engine = 'engine-' + pod_name.replace('=', '-') + '-' + fault
        data['metadata']['name'] = engine
        data['spec']['appinfo']['applabel'] = pod_name
        data['spec']['appinfo']['appns'] = self.namespace
        if fault in ['cpu-hog', 'disk-fill']:
            for v in data['spec']['experiments'][0]['spec']['components']['env']:
                if v['name'] == 'CPU_LOAD':
                    v['value'] = str(load)
                elif v['name'] == 'FILL_PERCENTAGE':
                    v['value'] = str(load)

        # exp_file = self.chaos_dir + 'chaos/experiments/' + 'experiment_' + str(random.randint(1, 10)) + '.json'
        exp_file = self.chaos_dir + 'experiments/' + 'experiment_' + fault + '_' + pod_name + '.json'
        with open(exp_file, 'w') as f:
            json.dump(data, f)
        self.logger.debug('[INJECT_FAULT] ' + exp_file)
        # exp_file = self.chaos_dir + 'chaos/experiments/' + 'experiment.json'
        # execute faults
        # cmd = 'cd ' + self.chaos_dir + ';chaos run ' + self.chaos_experiment
        self.experiment(exp_file)
        return engine
