import json
import logging
import time
import requests


class TestApplication:
    def __init__(self, num_requests=10, timeout=2, sleep_time=1):
        self.num_requests = num_requests
        self.timeout = timeout
        self.sleep_time = sleep_time
        self.logger = logging.getLogger()

    def test_load(self, url=''):
        # url = 'http://192.168.49.2:31902/api/cart/health'
        timeout_count = 0
        avg_lat = 0
        for i in range(self.num_requests):
            try:
                r = requests.get(url, verify=False, timeout=self.timeout)
                avg_lat += r.elapsed.total_seconds()
                self.logger.info(
                    url + ' ' + str(i) + ':' + str(r.status_code) + " {:.2f}".format(r.elapsed.total_seconds())
                    + " {:.2f}".format(avg_lat))
                if r.status_code != 200:
                    return '200', r.status_code
            # except requests.exceptions.Timeout as toe:
            except Exception as toe:
                self.logger.info(url + ' ' + str(i) + ':' + 'Timeout Exception!')
                timeout_count += 1
                if timeout_count > 3:
                    return '200', 'Timeout'
            # except Exception as e:
            #   self.logger.debug('Connection refused!'+str(e))
            time.sleep(self.sleep_time)
        self.logger.info(url + "Avg: {:.2f}".format(avg_lat/self.num_requests))
        return '200', '200'

    # def test_load_hey(self):
    #     cmd = 'hey -c 2 -z 20s http://192.168.49.2:31902/api/cart/health > temp'
    #     os.system(cmd)
    #     with open('temp') as f:
    #         datafile = f.readlines()
    #     found = False
    #     for line in datafile:
    #         if 'Status code distribution:' in line:
    #             found = True
    #         if found:
    #             print('[test_load]', line)
    #             m = re.search(r"\[([A-Za-z0-9_]+)\]", line)
    #             if m is not None:
    #                 resp_code = m.group(1)
    #                 if resp_code != 200:
    #                     return '200', resp_code
    #     return '200', '200'

    # # End state is reached when system is down or return error code like '500','404'
    # def get_next_state(self):
    #     self.logger.info('[GET_NEXT_STATE]')
    #     f = open(self.chaos_dir + self.chaos_journal)
    #     data = json.load(f)
    #
    #     # before the experiment (if before steady state is false, after is null?)
    #     for probe in data['steady_states']['before']['probes']:
    #         if not probe['tolerance_met']:
    #             # start_state = probe['activity']['tolerance']
    #             # end_state = probe['status']
    #             start_state, end_state = None, None
    #             return start_state, end_state
    #
    #     # after the experiment
    #     for probe in data['steady_states']['after']['probes']:
    #         # if probe['output']['status'] == probe['activity']['tolerance']:
    #         if not probe['tolerance_met']:
    #             # print(probe)
    #             start_state = probe['activity']['tolerance']
    #             end_state = probe['output']['status']
    #             # end_state = probe['status']
    #             return start_state, end_state
    #     # if tolerances for all probes are met
    #     start_state = probe['activity']['tolerance']
    #     end_state = probe['activity']['tolerance']
    #     return start_state, end_state
