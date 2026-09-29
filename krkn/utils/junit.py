# Copyright 2026 The Krkn Authors
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

import logging
import os
import time

from krkn_lib.utils.functions import get_junit_test_case


def validate_junit_options(junit_testcase, junit_testcase_path):
    """Validate junit CLI options. Returns (junit_error, junit_normalized_path)."""
    junit_error = False
    junit_normalized_path = None

    if junit_testcase_path and not junit_testcase:
        logging.error(
            "please set junit test case description with --junit-testcase [description] option"
        )
        junit_error = True

    if junit_testcase and not junit_testcase_path:
        logging.error(
            "please set junit test case path with --junit-testcase-path [path] option"
        )
        junit_error = True

    if junit_testcase and junit_testcase_path:
        junit_normalized_path = os.path.normpath(junit_testcase_path)

        if not os.path.exists(junit_normalized_path):
            logging.error(
                f"{junit_normalized_path} do not exists, please select a valid path"
            )
            junit_error = True

        if not os.path.isdir(junit_normalized_path):
            logging.error(
                f"{junit_normalized_path} is a file, please select a valid folder path"
            )
            junit_error = True

        if not os.access(junit_normalized_path, os.W_OK):
            logging.error(
                f"{junit_normalized_path} is not writable, please select a valid path"
            )
            junit_error = True

    return junit_error, junit_normalized_path


def write_junit_file(
    junit_normalized_path,
    success,
    elapsed_seconds,
    test_case_description,
    test_stdout,
    test_version=None,
):
    """Write a junit XML testcase file to junit_normalized_path."""
    junit_testcase_xml = get_junit_test_case(
        success=success,
        time=int(elapsed_seconds),
        test_suite_name="chaos-krkn",
        test_case_description=test_case_description,
        test_stdout=test_stdout,
        test_version=test_version,
    )
    junit_testcase_file_path = f"{junit_normalized_path}/junit_krkn_{int(time.time())}.xml"
    logging.info(f"writing junit XML testcase in {junit_testcase_file_path}")
    with open(junit_testcase_file_path, "w") as stream:
        stream.write(junit_testcase_xml)
