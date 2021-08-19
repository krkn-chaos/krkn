#!/usr/bin/env python3
import subprocess
import logging
import time


def run(cmd):
    try:
        output = subprocess.Popen(
            cmd, shell=True, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        (out, err) = output.communicate()
    except Exception as e:
        logging.error("Failed to run %s, error: %s" % (cmd, e))
    return out


i = 0
while i < 100:
    pods_running = run("oc get pods -n openshift-etcd -l app=etcd | grep -c '4/4'").rstrip()
    if pods_running == "3":
        break
    time.sleep(5)
    i += 1

if pods_running == str(3):
    print("There were 3 pods running properly")
else:
    print("ERROR there were " + str(pods_running) + " pods running instead of 3")
