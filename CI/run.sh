#!/bin/bash
set -x
MAX_RETRIES=60

OC=`which oc 2>/dev/null`
[[ $? != 0 ]] && echo "[ERROR]: oc missing, please install it and try again" && exit 1

wait_cluster_become_ready() {
  COUNT=1
  until `$OC get namespace > /dev/null 2>&1`
  do
    echo "[INF] waiting OpenShift to become ready, after $COUNT check"
    sleep 3
    [[ $COUNT == $MAX_RETRIES ]] && echo "[ERR] max retries exceeded, failing" && exit 1
    ((COUNT++))
  done 
}



ci_tests_loc="CI/tests/my_tests"

echo "running test suit consisting of ${ci_tests}"

rm -rf CI/out

mkdir CI/out

results_file_name="results.markdown"

rm -f CI/$results_file_name

results="CI/$results_file_name"

# Prep the results.markdown file
echo 'Test                   | Result | Duration' >> $results
echo '-----------------------|--------|---------' >> $results

# Run each test
for test_name in `cat CI/tests/my_tests`
do
  wait_cluster_become_ready
  ./CI/run_test.sh $test_name $results
  wait_cluster_become_ready
done
