#!/usr/bin/env python3
import subprocess
import time


def run(cmd):
    try:
        output = subprocess.Popen(
            cmd, shell=True, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        (out, err) = output.communicate()
    except Exception as e:
        print("Failed to run %s, error: %s" % (cmd, e))
    return out


i = 0
while i < 100:
    projects_active = run("oc get project | grep 'ingress' | grep -c Active").rstrip()
    if projects_active == "3":
        break
    i += 1
    time.sleep(5)

if projects_active == str(3):
    print("There were 3 projects running properly")
else:
    print("ERROR there were " + str(projects_active) + " projects running instead of 3")
