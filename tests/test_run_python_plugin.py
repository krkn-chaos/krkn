#!/usr/bin/env python
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

import tempfile
import unittest

from krkn.scenario_plugins.native.run_python_plugin import (
    RunPythonFileInput,
    run_python_file,
)


class RunPythonPluginTest(unittest.TestCase):
    def test_success_execution(self):
        tmp_file = tempfile.NamedTemporaryFile()
        tmp_file.write(bytes("print('Hello world!')", "utf-8"))
        tmp_file.flush()
        output_id, output_data = run_python_file(
            params=RunPythonFileInput(tmp_file.name),
            run_id="test-python-plugin-success",
        )
        self.assertEqual("success", output_id)
        self.assertEqual("Hello world!\n", output_data.stdout)

    def test_error_execution(self):
        tmp_file = tempfile.NamedTemporaryFile()
        tmp_file.write(
            bytes("import sys\nprint('Hello world!')\nsys.exit(42)\n", "utf-8")
        )
        tmp_file.flush()
        output_id, output_data = run_python_file(
            params=RunPythonFileInput(tmp_file.name), run_id="test-python-plugin-error"
        )
        self.assertEqual("error", output_id)
        self.assertEqual(42, output_data.exit_code)
        self.assertEqual("Hello world!\n", output_data.stdout)


if __name__ == "__main__":
    unittest.main()
