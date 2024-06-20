import json
import os
import time
import logging

import src.utils as utils


class KrakenUtils:
    def __init__(self, namespace='robot-shop', chaos_dir='../config/',
                 chaos_experiment='experiment.json', kubeconfig='~/.kube/config', wait_checks=60, command='podman'):
        self.chaos_dir = chaos_dir
        self.chaos_experiment = chaos_experiment
        self.namespace = namespace
        self.kubeconfig = kubeconfig
        self.logger = logging.getLogger()
        self.engines = []
        self.wait_checks = wait_checks
        self.command = command
        self.ns_pods = utils.get_namespace_pods(namespace, kubeconfig)

    def exp_status(self, engine='engine-cartns3'):
        substring_list = ['Waiting for the specified duration','Waiting for wait_duration', 'Step workload started, waiting for response']
        substr = '|'.join(substring_list)
        # cmd = "docker logs "+engine+" 2>&1 | grep Waiting"
        # cmd = "docker logs "+engine+" 2>&1 | grep -E '"+substr+"'"
        cmd = self.command +" logs "+engine+" 2>&1 | grep -E '"+substr+"'"
        line = os.popen(cmd).read()
        self.logger.debug('[exp_status]'+line)
        # if 'Waiting for the specified duration' in line:
        # if 'Waiting for' in line or 'waiting for' in line:
        # if 'Waiting for the specified duration' in line or 'Waiting for wait_duration' in line or 'Step workload started, waiting for response' in line:
        if any(map(line.__contains__, substring_list)):
            return 'Running'
        return 'Not Running'
 
    # print chaos result, check if litmus showed any error
    def print_result(self, engines):
        # self.logger.debug('')
        for e in engines:
            # cmd = 'kubectl describe chaosresult ' + e + ' -n ' + self.namespace + ' | grep "Fail Step:"'
            # line = os.popen(cmd).read()
            # self.logger.debug('[Chaos Result] '+e+' : '+line)
            self.logger.debug('[KRAKEN][Chaos Result] '+e)

    def wait_engines(self, engines=[]):
        status = 'Completed'
        max_checks = self.wait_checks
        for e in engines:
            self.logger.info('[Wait Engines] ' + e)
            for i in range(max_checks):
                status = self.exp_status(e)
                if status == 'Running':
                    break
                time.sleep(1)
            # return False, if even one engine is not running
            if status != 'Running':
                return False

        self.engines = engines
        # return True if all engines are running
        return True


    def cleanup(self):
        self.logger.debug('Removing previous engines')
        # cmd = "docker rm $(docker ps -q -f 'status=exited')"
        if len(self.engines) > 0:
            cmd = self.command+" stop " + " ".join(self.engines) + " >> temp"
            os.system(cmd)
        self.engines = []

        cmd = self.command+" container prune -f >> temp"
        os.system(cmd)
        self.logger.debug('Engines removed')

    def stop_engines(self, episode=[]):
        self.cleanup()

    def get_name(self):
        return 'kraken'

    def inject_faults(self, fault, pod_name):
        self.logger.debug('[KRAKEN][INJECT_FAULT] ' + fault + ':' + pod_name)
        fault, load = utils.get_load(fault)
        engine = 'engine-' + pod_name.replace('=', '-').replace('/','-') + '-' + fault
        ns = utils.get_ns_from_pod(self.ns_pods, pod_name)
        if fault == 'pod-delete':
            cmd = self.command+' run  -d -e NAMESPACE='+ns+' -e POD_LABEL='+pod_name+' --name='+engine+' --net=host -v '+self.kubeconfig+':/root/.kube/config:Z quay.io/redhat-chaos/krkn-hub:pod-scenarios >> temp'
        elif fault == 'network-chaos':
            # 'docker run -e NODE_NAME=minikube-m03 -e DURATION=10  --name=knetwork --net=host -v /home/chaos/.kube/kube-config-raw:/root/.kube/config:Z -d quay.io/redhat-chaos/krkn-hub:network-chaos >> temp'        
            cmd = self.command+' run -d -e NODE_NAME='+pod_name+' -e DURATION=120  --name='+engine+' --net=host -v '+self.kubeconfig+':/root/.kube/config:Z -d quay.io/redhat-chaos/krkn-hub:network-chaos >> temp'
        elif fault == 'node-memory-hog':
            cmd = self.command+' run -d -e NODE_NAME='+pod_name+' -e DURATION=120 -e NODES_AFFECTED_PERC=100 --name='+engine+' --net=host -v '+self.kubeconfig+':/root/.kube/config:Z -d quay.io/redhat-chaos/krkn-hub:node-memory-hog >> temp'
        elif fault == 'node-cpu-hog':
            cmd = self.command+'  run -e NODE_SELECTORS='+pod_name+' -e NODE_CPU_PERCENTAGE=100 -e NAMESPACE='+ns+' -e TOTAL_CHAOS_DURATION=120 -e NODE_CPU_CORE=100 --name='+engine+' --net=host -env-host=true -v '+self.kubeconfig+':/root/.kube/config:Z -d quay.io/redhat-chaos/krkn-hub:node-cpu-hog'
        else:
            cmd = 'echo'
        self.logger.debug('[KRAKEN][INJECT_FAULT] ' + cmd)
        os.system(cmd)
        return engine
