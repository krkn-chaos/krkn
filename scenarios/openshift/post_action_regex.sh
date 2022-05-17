#!/bin/bash
pods="$(oc get pods -n openshift-etcd | grep -c Running)"
echo "$pods"

if [ "$pods" -eq 3 ]
then
  echo "Pods Pass"
else
  # need capital error for proper error catching in run_kraken
  echo "ERROR pod count $pods doesnt match 3 expected pods"
fi
