#!/usr/bin/env python3
import subprocess
import time
import logging
from kubernetes import client, config
from kubernetes.client.rest import ApiException

i = 0
config.load_kube_config()
cli = client.CoreV1Api()
while i < 100:
    try:
        res=cli.list_namespace()
    except ApiException as e:
        logging.error(
            "Exception when calling CoreV1Api->list_namespace: %s\n" % (e))
    projects_active=0
    for ns in res.items:
        if "ingress" in ns.metadata.name and ns.status.phase == "Active":
            projects_active +=1
    if projects_active == 3:
        break
    i +=1
    time.sleep(5)

if projects_active == 3:
    print("There were 3 projects running properly")
else:
    logging.error("ERROR there were %d projects running instead of 3" % (projects_active))
