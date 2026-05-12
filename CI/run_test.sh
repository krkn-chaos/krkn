#!/bin/bash
#
# Copyright 2025 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

readonly SECONDS_PER_HOUR=3600
readonly SECONDS_PER_MINUTE=60
function get_time_format() {
  seconds=$1
  hours=$((${seconds} / ${SECONDS_PER_HOUR}))
  seconds=$((${seconds} % ${SECONDS_PER_HOUR}))
  minutes=$((${seconds} / ${SECONDS_PER_MINUTE}))
  seconds=$((${seconds} % ${SECONDS_PER_MINUTE}))
  echo $hours:$minutes:$seconds
}
ci_test=`echo $1`

results_file=$2

echo -e "test: ${ci_test}" >&2

ci_results="CI/out/$ci_test.out"
# Test ci

echo "results $ci_results" >> $ci_results
SECONDS=0
if /bin/bash CI/tests/$ci_test.sh >> $ci_results 2>&1
then
  # if the test passes update the results and complete
  duration=$SECONDS
  duration=$(get_time_format $duration)
  echo -e  "> $ci_test: Successful\n" >&2
  echo "$ci_test | Pass | $duration" >> $results_file
  count=$retries
  # return value for run.sh
  echo 0
else
  duration=$SECONDS
  duration=$(get_time_format $duration)
  echo -e "> $ci_test: Failed\n" >&2
  echo "$ci_test | Fail | $duration" >> $results_file
  # return value for run.sh
  echo 1
fi
