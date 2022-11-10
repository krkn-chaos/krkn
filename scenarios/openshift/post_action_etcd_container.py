#!/usr/bin/env python3
import subprocess
import logging
import time
from command_runner import CommandRunner


i = 0
while i < 100:
    pods_running = CommandRunner.run("oc get pods -n openshift-etcd -l app=etcd | grep -c '4/4'").rstrip()
    if pods_running == "3":
        break
    time.sleep(5)
    i += 1

if pods_running == str(3):
    print("There were 3 pods running properly")
else:
    print("ERROR there were " + str(pods_running) + " pods running instead of 3")
