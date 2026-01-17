import json, os
import logging
# import numpy as np
# import pandas as pd
import threading
from datetime import datetime
from flask import Flask, request
from flasgger import Swagger
from flasgger.utils import swag_from
# import zipfile
import sys

sys.path.append("..")
from aichaos_main import AIChaos

app = Flask(__name__)
Swagger(app)
flaskdir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "experiments",
                        "flask") + '/'


class AIChaosSwagger:
    def __init__(self, flaskdir=''):
        self.flaskdir = flaskdir

    @app.route("/")
    def empty(params=''):
        return "AI Chaos Repository!"

    def startchaos(self, kubeconfigfile, file_id, params):
        print('[StartChaos]', file_id, kubeconfigfile)
        dir = flaskdir
        outfile = ''.join([dir, 'out-', file_id])
        initfile = ''.join([dir, 'init-', file_id])
        with open(initfile, 'w'):
            pass
        if os.path.exists(outfile):
            os.remove(outfile)
        # cons = ConstraintsInference(outdir=dir).get_constraints(csvfile, file_id, params, verbose=False,
        #                                                         write_local=False)
        os.environ["KUBECONFIG"] = kubeconfigfile
        params['command'] = 'podman'
        params['chaos_engine'] = 'kraken'
        params['faults'] = 'pod-delete'
        params['iterations'] = 1
        params['maxfaults'] = 5
        if os.path.isfile('/config/aichaos-config.json'):
            with open('/config/aichaos-config.json') as f:
                config_params = json.load(f)
                params['command'] = config_params['command']
                params['chaos_engine'] = config_params['chaos_engine']
                params['faults']= config_params['faults']
                params['iterations'] = config_params['iterations']
                params['maxfaults'] = config_params['maxfaults']
        faults = [f + ':' + p for f in params['faults'].split(',') for p in params['podlabels'].split(',')]
        print('#faults:', len(faults), faults)
        states = {'200': 0, '500': 1, '502': 2, '503': 3, '404': 4, 'Timeout': 5}
        rewards = {'200': -1, '500': 0.8, '502': 0.8, '503': 0.8, '404': 1, 'Timeout': 1}
        logfile = self.flaskdir + 'log_' + str(file_id)
        qfile = self.flaskdir + 'qfile_' + str(file_id) + '.csv'
        efile = self.flaskdir + 'efile_' + str(file_id)
        epfile = self.flaskdir + 'episodes_' + str(file_id) + '.json'
        probe_url = params['probeurl']
        probes = {'pod-delete': 'executeprobe', 'cpu-hog': 'wolffi/cpu_load', 'disk-fill': 'wolffi/memory_load',
                  'io_load': 'wolffi/io_load', 'http_delay': 'wolffi/http_delay', 'packet_delay': 'wolffi/packet_delay',
                  'packet_duplication': 'wolffi/packet_duplication', 'packet_loss': 'wolffi/packet_loss',
                  'packet_corruption': 'wolffi/packet_corruption',
                  'packet_reordering': 'wolffi/packet_reordering', 'network_load': 'wolffi/network_load',
                  'http_bad_request': 'wolffi/http_bad_request',
                  'http_unauthorized': 'wolffi/http_unauthorized', 'http_forbidden': 'wolffi/http_forbidden',
                  'http_not_found': 'wolffi/http_not_found',
                  'http_method_not_allowed': 'wolffi/http_method_not_allowed',
                  'http_not_acceptable': 'wolffi/http_not_acceptable',
                  'http_request_timeout': 'wolffi/http_request_timeout',
                  'http_unprocessable_entity': 'wolffi/http_unprocessable_entity',
                  'http_internal_server_error': 'wolffi/http_internal_server_error',
                  'http_not_implemented': 'wolffi/http_not_implemented',
                  'http_bad_gateway': 'wolffi/http_bad_gateway',
                  'http_service_unavailable': 'wolffi/http_service_unavailable',
                  'bandwidth_restrict': 'wolffi/bandwidth_restrict',
                  'pod_cpu_load': 'wolffi/pod_cpu_load', 'pod_memory_load': 'wolffi/pod_memory_load',
                  'pod_io_load': 'wolffi/pod_io_load',
                  'pod_network_load': 'wolffi/pod_network_load'
                  }
        dstk_probes = {k: probe_url + v for k, v in probes.items()}
        cexp = {'pod-delete': 'pod-delete.json', 'cpu-hog': 'pod-cpu-hog.json',
                'disk-fill': 'disk-fill.json', 'network-loss': 'network-loss.json',
                'network-corruption': 'network-corruption.json', 'io-stress': 'io-stress.json'}
        aichaos = AIChaos(states=states, faults=faults, rewards=rewards,
                          logfile=logfile, qfile=qfile, efile=efile, epfile=epfile,
                          urls=params['urls'].split(','), namespace=params['namespace'],
                          max_faults=params['maxfaults'],
                          num_requests=10, timeout=2,
                          chaos_engine=params['chaos_engine'], dstk_probes=dstk_probes, command=params['command'],
                          loglevel=logging.DEBUG, chaos_experiment=cexp, iterations=params['iterations'])
        aichaos.start_chaos()

        with open(outfile, "w") as file:
            file.write('done')
        os.remove(initfile)
        # os.remove(csvfile)
        # ConstraintsInference().remove_temp_files(dir, file_id)
        return 'WRITE'

    @app.route('/GenerateChaos/', methods=['POST'])
    @swag_from('../config/yml/chaosGen.yml')
    def chaos_gen():
        dir = flaskdir
        sw = AIChaosSwagger(flaskdir=dir)
        f = request.files['file']
        list = os.listdir(dir)
        for i in range(10000):
            if str(i) not in list:
                break
        kubeconfigfile = ''.join([dir, str(i)])
        f.save(kubeconfigfile)
        print('HEADER:', f.headers)
        print('[GenerateChaos] reqs:', request.form.to_dict())
        print('[GenerateChaos]', f.filename, datetime.now())
        # thread = threading.Thread(target=sw.write_constraints, args=(csvfile, str(i), parameters))
        thread = threading.Thread(target=sw.startchaos, args=(kubeconfigfile, str(i), request.form.to_dict()))
        thread.daemon = True
        print(thread.getName())
        thread.start()
        return 'Chaos ID: ' + str(i)

    @app.route('/GetStatus/<chaosid>', methods=['GET'])
    @swag_from('../config/yml/status.yml')
    def get_status(chaosid):
        print('[GetStatus]', chaosid, flaskdir)
        epfile = flaskdir + 'episodes_' + str(chaosid) + '.json'
        initfile = ''.join([flaskdir, 'init-', chaosid])
        if os.path.exists(epfile):
            return 'Completed'
        elif os.path.exists(initfile):
            return 'Running'
        else:
            return 'Does not exist'

    @app.route('/GetQTable/<chaosid>', methods=['GET'])
    @swag_from('../config/yml/qtable.yml')
    def get_qtable(chaosid):
        print('[GetQTable]', chaosid)
        qfile = flaskdir + 'qfile_' + str(chaosid) + '.csv'
        initfile = ''.join([flaskdir, 'init-', chaosid])
        if os.path.exists(qfile):
            with open(qfile, "r") as f:
                return f.read()
        elif os.path.exists(initfile):
            return 'Running'
        else:
            return 'Invalid Chaos ID: ' + chaosid

    @app.route('/GetEpisodes/<chaosid>', methods=['GET'])
    @swag_from('../config/yml/episodes.yml')
    def get_episodes(chaosid):
        print('[GetEpisodes]', chaosid)
        epfile = flaskdir + 'episodes_' + str(chaosid) + '.json'
        initfile = ''.join([flaskdir, 'init-', chaosid])
        if os.path.exists(epfile):
            with open(epfile, "r") as f:
                return f.read()
        elif os.path.exists(initfile):
            return 'Running'
        else:
            return 'Invalid Chaos ID: ' + chaosid


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port='5001')
