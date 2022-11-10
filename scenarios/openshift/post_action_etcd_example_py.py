#!/usr/bin/env python3
import subprocess
import logging
from command_runner import CommandRunner


pods_running = CommandRunner.run("oc get pods -n openshift-etcd | grep -c Running").rstrip()

if pods_running == str(3):
    print("There were 3 pods running properly")
else:
    print("ERROR there were " + str(pods_running) + " pods running instead of 3")
