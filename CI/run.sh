#!/bin/bash
set -x

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
  ./CI/run_test.sh $test_name $results
done
