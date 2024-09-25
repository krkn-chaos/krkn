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
