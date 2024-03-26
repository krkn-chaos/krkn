# import os
import requests
# import time
import logging


class DSTKUtils:
    def __init__(self, probes=None, namespace='robot-shop'):
        self.probes = probes
        self.namespace = namespace
        self.logger = logging.getLogger()

    def exp_status(self, engine='engine-cartns3'):
        return 'Running'

    def wait_engines(self, engines=[]):
        # return True if all engines are running
        return True

    # print chaos result, check if litmus showed any error
    def print_result(self, engines):
        pass

    def inject_faults(self, fault, pod_name):
        self.logger.debug('[DSTK INJECT_FAULT] ' + fault + ':' + pod_name)
        self.inject_probe(fault, pod_name)

    def inject_probe(self, fault, pod_label):
        probe_url = self.probes[fault] + '?namespace=' + self.namespace + '&labelselector=' + pod_label
        # if fault in ['cpu-load', 'disk-fill']:

        try:
            if fault not in ['pod-delete']:
                probe_url = probe_url.replace('labelselector', 'name')
                probe_url += '&load_percent=100&duration_sec=30'
                r = requests.delete(probe_url, verify=False)
            self.logger.info('[DSTKUtils inject_probe] url:' + probe_url)

            # injecting probe through request
            r = requests.get(probe_url, verify=False)
            self.logger.debug('[DSTK inject_probe] response:' + str(r.status_code) + ' ' + r.text)
            if r.status_code != 200:
                return '200', r.status_code
        # except requests.exceptions.Timeout as toe:
        except Exception as toe:
            self.logger.debug('Timeout Exception!')
            return '200', 'Timeout'

    # def experiment(self, exp_file):
    #     cmd = 'kubectl apply -f ' + exp_file + ' -n ' + self.namespace
    #     os.system(cmd)

    def cleanup(self, episode=[]):
        self.logger.info('[Cleanup DSTK]')
        for e in episode:
            fault = e['fault']
            pod_name = e['pod_name']
            if fault in ['pod-delete']:
                continue
            probe_url = self.probes[fault] + '?namespace=' + self.namespace + '&labelselector=' + pod_name
            probe_url = probe_url.replace('labelselector', 'name')
            self.logger.debug('[DSTK cleanup] probe_url:' + probe_url)
            try:
                r = requests.delete(probe_url, verify=False)
                self.logger.debug('[DSTK cleanup] response text:' + str(r.status_code) + ' ' + r.text)
            # except requests.exceptions.Timeout as toe:
            except Exception as toe:
                self.logger.debug('Timeout Exception!')

    def stop_engines(self, episode=[]):
        self.logger.debug('[Stop Engines DSTK]')
        self.cleanup(episode=episode)

    def get_name(self):
        return 'dstk'
