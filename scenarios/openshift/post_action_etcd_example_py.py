#!/usr/bin/env python3
import subprocess
import logging


def run(cmd):
    try:
        output = subprocess.Popen(
            cmd, shell=True, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        (out, err) = output.communicate()
        logging.info("out " + str(out))
    except Exception as e:
        logging.error("Failed to run %s, error: %s" % (cmd, e))
    return out


pods_running = run("oc get pods -n openshift-etcd | grep -c Running").rstrip()

if pods_running == str(3):
    print("There were 3 pods running properly")
else:
    print("ERROR there were " + str(pods_running) + " pods running instead of 3")
