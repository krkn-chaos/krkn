#!/bin/bash
pods="$(oc get pods -n openshift-etcd | grep -c Running)"
echo "$pods"
