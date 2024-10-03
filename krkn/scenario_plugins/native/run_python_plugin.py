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
