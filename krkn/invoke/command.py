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
import subprocess
import logging
import sys


# Invokes a given command and returns the stdout
def invoke(command, timeout=None):
    output = ""
    try:
        output = subprocess.check_output(command, shell=True, universal_newlines=True, timeout=timeout)
    except Exception as e:
        logging.error("Failed to run %s, error: %s" % (command, e))
        sys.exit(1)
    return output


# Invokes a given command and returns the stdout
def invoke_no_exit(command, timeout=15):
    output = ""
    try:
        output = subprocess.check_output(command, shell=True, universal_newlines=True, timeout=timeout, stderr=subprocess.DEVNULL)
    except Exception as e:
        return str(e)
    return output


def run(command):
    try:
        subprocess.run(command, shell=True, universal_newlines=True, timeout=45)
    except Exception:
        pass
