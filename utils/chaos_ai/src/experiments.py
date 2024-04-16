import random


class Experiments:
    def __init__(self):
        self.k = 0

    def monotonic(self, aichaos, num_sets=3):
        for i in range(num_sets):
            faults_pods = random.sample(aichaos.faults, k=2)
            faults_set = [[faults_pods[0]], [faults_pods[1]], [faults_pods[0], faults_pods[1]]]

            resp1, resp2, resp_both = 0, 0, 0
            for fl in faults_set:
                engines = []
                for fp in fl:
                    fault = fp.split(':')[0]
                    pod_name = fp.split(':')[1]
                    engine = aichaos.inject_faults_litmus(fault, pod_name)
                    engines.append(engine)
                aichaos.litmus.wait_engines(engines)

                for index, url in enumerate(aichaos.urls):
                    start_state, next_state = aichaos.test_load(url)
                    print(i, fl, next_state)
                    # self.write(str(fl), next_state)
                    if resp1 == 0:
                        resp1 = next_state
                    elif resp2 == 0:
                        resp2 = next_state
                    else:
                        resp_both = next_state

                aichaos.litmus.stop_engines()
            self.write_resp(str(faults_set[2]), resp1, resp2, resp_both)
        print('Experiment Complete!!!')

    @staticmethod
    def write(fault, next_state):
        with open("experiment", "a") as outfile:
            outfile.write(fault + ',' + str(next_state) + ',' + '\n')


    @staticmethod
    def write_resp(faults, resp1, resp2, resp3):
        monotonic = True
        if resp3 == 200:
            if resp1 != 200 or resp2 != 200:
                monotonic = False
        else:
            if resp1 == 200 and resp2 == 200:
                monotonic = False

        with open("experiment", "a") as outfile:
            # outfile.write(faults + ',' + str(resp1) + ',' + '\n')
            outfile.write(faults + ',' + str(resp1) + ',' + str(resp2) + ',' + str(resp3) + ',' + str(monotonic) + '\n')
