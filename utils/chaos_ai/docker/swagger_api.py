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

# sys.path.append("..")
from src.aichaos_main import AIChaos
import src.utils as utils

app = Flask(__name__)
Swagger(app)
flaskdir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "logs") + '/'


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
        # kubeconfigfile = params['file']
        os.environ["KUBECONFIG"] = kubeconfigfile
        os.system("export KUBECONFIG="+kubeconfigfile)
        os.system("echo $KUBECONFIG")
        print('setting kubeconfig')
        params['command'] = 'podman'
        params['chaosengine'] = 'kraken'
        params['faults'] = 'pod-delete'
        params['iterations'] = 1
        params['maxfaults'] = 5
        if os.path.isfile('/config/aichaos-config.json'):
            with open('/config/aichaos-config.json') as f:
                config_params = json.load(f)
                params['command'] = config_params['command']
                params['chaosengine'] = config_params['chaosengine']
                params['faults']= config_params['faults']
                params['iterations'] = config_params['iterations']
                params['maxfaults'] = config_params['maxfaults']
        # faults = [f + ':' + p for f in params['faults'].split(',') for p in params['podlabels'].split(',')]
        if params['podlabels'] is None or params['podlabels'] == '':
            params['podlabels'] = ','.join(utils.get_pods(kubeconfigfile))
        faults = []
        for f in params['faults'].split(','):
            if f in ['pod-delete']:
                for p in params['podlabels'].split(','):
                    faults.append(f + ':' + p)
            elif f in ['network-chaos', 'node-memory-hog', 'node-cpu-hog']:
                for p in params['nodelabels'].split(','):
                    faults.append(f + ':' + p)
            else:
                pass

        print('#faults:', len(faults), faults)
        states = {'200': 0, '500': 1, '501': 2, '502': 3, '503': 4, '504': 5,
                  '401': 6,  '403': 7,  '404': 8,  '429': 9,
                  'Timeout': 10, 'Other': 11}
        rewards = {'200': -1, '500': 0.8, '501': 0.8, '502': 0.8, '503': 0.8, '504': 0.8,
                   '401': 1,  '403': 1,  '404': 1,  '429': 1,
                   'Timeout': 1, 'Other': 1}
        logfile = self.flaskdir + 'log_' + str(file_id)
        qfile = self.flaskdir + 'qfile_' + str(file_id) + '.csv'
        efile = self.flaskdir + 'efile_' + str(file_id)
        epfile = self.flaskdir + 'episodes_' + str(file_id) + '.json'
        # probe_url = params['probeurl']
        cexp = {'pod-delete': 'pod-delete.json', 'cpu-hog': 'pod-cpu-hog.json',
                'disk-fill': 'disk-fill.json', 'network-loss': 'network-loss.json',
                'network-corruption': 'network-corruption.json', 'io-stress': 'io-stress.json'}
        aichaos = AIChaos(states=states, faults=faults, rewards=rewards,
                          logfile=logfile, qfile=qfile, efile=efile, epfile=epfile,
                          urls=params['urls'].split(','), namespace=params['namespace'],
                          max_faults=int(params['maxfaults']),
                          num_requests=10, timeout=2,
                          chaos_engine=params['chaosengine'],
                          chaos_dir='config/', kubeconfig=kubeconfigfile,
                          loglevel=logging.DEBUG, chaos_experiment=cexp, iterations=int(params['iterations']),
                          command=params['command'])
        print('checking kubeconfig')
        os.system("echo $KUBECONFIG")
        aichaos.start_chaos()

        file = open(outfile, "w")
        file.write('done')
        file.close()
        os.remove(initfile)
        # os.remove(csvfile)
        # ConstraintsInference().remove_temp_files(dir, file_id)
        return 'WRITE'

    @app.route('/GenerateChaos/', methods=['POST'])
    @swag_from('config/yml/chaosGen.yml')
    def chaos_gen():
        dir = flaskdir
        sw = AIChaosSwagger(flaskdir=dir)
        f = request.files['file']
        list = os.listdir(dir)
        for i in range(10000):
            fname = 'kubeconfig-'+str(i)
            if fname not in list:
                break
        kubeconfigfile = ''.join([dir, 'kubeconfig-', str(i)])
        f.save(kubeconfigfile)
        # creating empty file
        open(kubeconfigfile, 'a').close()
        # print('HEADER:', f.headers)
        print('[GenerateChaos] reqs:', request.form.to_dict())
        # print('[GenerateChaos]', f.filename, datetime.now())
        if utils.is_cluster_accessible(kubeconfigfile):
            print("Cluster is accessible!")
        else:
            return 'Cluster not accessible !!!'
        thread = threading.Thread(target=sw.startchaos, args=(kubeconfigfile, str(i), request.form.to_dict()))
        thread.daemon = True
        print(thread.getName())
        thread.start()
        return 'Chaos ID: ' + str(i)

    @app.route('/GetStatus/<chaosid>', methods=['GET'])
    @swag_from('config/yml/status.yml')
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
    @swag_from('config/yml/qtable.yml')
    def get_qtable(chaosid):
        print('[GetQTable]', chaosid)
        qfile = flaskdir + 'qfile_' + str(chaosid) + '.csv'
        initfile = ''.join([flaskdir, 'init-', chaosid])
        if os.path.exists(qfile):
            f = open(qfile, "r")
            return f.read()
        elif os.path.exists(initfile):
            return 'Running'
        else:
            return 'Invalid Chaos ID: ' + chaosid

    @app.route('/GetEpisodes/<chaosid>', methods=['GET'])
    @swag_from('config/yml/episodes.yml')
    def get_episodes(chaosid):
        print('[GetEpisodes]', chaosid)
        epfile = flaskdir + 'episodes_' + str(chaosid) + '.json'
        initfile = ''.join([flaskdir, 'init-', chaosid])
        if os.path.exists(epfile):
            f = open(epfile, "r")
            return f.read()
        elif os.path.exists(initfile):
            return 'Running'
        else:
            return 'Invalid Chaos ID: ' + chaosid


    @app.route('/GetLog/<chaosid>', methods=['GET'])
    @swag_from('config/yml/log.yml')
    def get_log(chaosid):
        print('[GetLog]', chaosid)
        epfile = flaskdir + 'log_' + str(chaosid)
        initfile = ''.join([flaskdir, 'init-', chaosid])
        if os.path.exists(epfile):
            f = open(epfile, "r")
            return f.read()
        elif os.path.exists(initfile):
            return 'Running'
        else:
            return 'Invalid Chaos ID: ' + chaosid


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port='5001')
