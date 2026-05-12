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

ERRORED=false

function finish {
    if [ $? != 0 ] && [ $ERRORED != "true" ]
    then
        error
    fi
}

function error {
    exit_code=$?
    if [ $exit_code == 1 ]
    then
      echo "Error caught."
      ERRORED=true
    elif [ $exit_code == 2 ]
    then
      echo "Run with exit code 2 detected, it is expected, wrapping the exit code with 0 to avoid pipeline failure"
      exit 0
    fi
}

function get_node {
  worker_node=$(kubectl get nodes --no-headers | grep worker | head -n 1)
  export WORKER_NODE=$worker_node
}
