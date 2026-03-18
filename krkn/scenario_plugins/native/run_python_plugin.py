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

import dataclasses
import subprocess
import sys
import typing

from arcaflow_plugin_sdk import plugin


@dataclasses.dataclass
class RunPythonFileInput:
    filename: str


@dataclasses.dataclass
class RunPythonFileOutput:
    stdout: str
    stderr: str


@dataclasses.dataclass
class RunPythonFileError:
    exit_code: int
    stdout: str
    stderr: str


@plugin.step(
    id="run_python",
    name="Run a Python script",
    description="Run a specified Python script",
    outputs={"success": RunPythonFileOutput, "error": RunPythonFileError}
)
def run_python_file(params: RunPythonFileInput) -> typing.Tuple[
    str,
    typing.Union[RunPythonFileOutput, RunPythonFileError]
]:
    run_results = subprocess.run(
        [sys.executable, params.filename],
        capture_output=True
    )
    if run_results.returncode == 0:
        return "success", RunPythonFileOutput(
            str(run_results.stdout, 'utf-8'),
            str(run_results.stderr, 'utf-8')
        )
    return "error", RunPythonFileError(
        run_results.returncode,
        str(run_results.stdout, 'utf-8'),
        str(run_results.stderr, 'utf-8')
    )
