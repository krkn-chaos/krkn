#!/usr/bin/env python3
import subprocess
import time
from command_runner import CommandRunner


i = 0
while i < 100:
    projects_active = CommandRunner.run("oc get project | grep 'ingress' | grep -c Active").rstrip()
    if projects_active == "3":
        break
    i += 1
    time.sleep(5)

if projects_active == str(3):
    print("There were 3 projects running properly")
else:
    print("ERROR there were " + str(projects_active) + " projects running instead of 3")
