#!/bin/bash
MAX_RETRIES=60

KUBECTL=`which kubectl 2>/dev/null`
[[ $? != 0 ]] && echo "[ERROR]: kubectl missing, please install it and try again" && exit 1

wait_cluster_become_ready() {
  COUNT=1
  until `$KUBECTL get namespace > /dev/null 2>&1`
  do
    echo "[INF] waiting Kubernetes to become ready, after $COUNT check"
    sleep 3
    [[ $COUNT == $MAX_RETRIES ]] && echo "[ERR] max retries exceeded, failing" && exit 1
    ((COUNT++))
  done 
}



ci_tests_loc="CI/tests/functional_tests"

echo -e "********* Running Functional Tests Suite *********\n\n"

rm -rf CI/out

mkdir CI/out

results_file_name="results.markdown"

rm -f CI/$results_file_name

results="CI/$results_file_name"

# Prep the results.markdown file
echo 'Test                   | Result | Duration' >> $results
echo '-----------------------|--------|---------' >> $results

# Run each test
failed_tests=()
for test_name in `cat CI/tests/functional_tests`
do
  #wait_cluster_become_ready
  return_value=`./CI/run_test.sh $test_name $results`
  if [[ $return_value == 1 ]]
  then
    echo "Failed"
    failed_tests+=("$test_name")
  fi
  wait_cluster_become_ready
done


if (( ${#failed_tests[@]}>0 ))
then
  echo -e "\n\n======================================================================"
  echo -e "\n     FUNCTIONAL TESTS FAILED  ${failed_tests[*]} ABORTING"
  echo -e "\n======================================================================\n\n"

  for test in "${failed_tests[@]}"
  do
    echo -e "\n********** $test KRKN RUN OUTPUT **********\n"
    cat "CI/out/$test.out"
    echo -e "\n********************************************\n\n\n\n"
  done

  exit 1
fi
