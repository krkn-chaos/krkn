import ast
import pathlib
import unittest


class TestRunKrakenStartup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_path = pathlib.Path("run_kraken.py")
        cls.source = cls.source_path.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def _get_main_function(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == "main":
                return node
        self.fail("main() not found in run_kraken.py")

    def _get_client_init_try(self):
        main_function = self._get_main_function()
        for node in ast.walk(main_function):
            if not isinstance(node, ast.Try):
                continue
            try_calls = [child for child in ast.walk(node) if isinstance(child, ast.Call)]
            call_names = set()
            for call in try_calls:
                if isinstance(call.func, ast.Name):
                    call_names.add(call.func.id)
                elif isinstance(call.func, ast.Attribute):
                    call_names.add(call.func.attr)
            if {"KrknKubernetes", "KrknOpenshift"}.issubset(call_names):
                return main_function, node
        self.fail("Client initialization try/except block not found in main()")

    def test_client_init_error_log_includes_kubeconfig_path(self):
        _, try_node = self._get_client_init_try()
        handler = try_node.handlers[0]

        found = False
        for node in ast.walk(handler):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if not isinstance(node.func.value, ast.Name):
                continue
            if node.func.value.id != "logging" or node.func.attr != "error":
                continue
            arg_names = {
                arg.id
                for arg in node.args
                if isinstance(arg, ast.Name)
            }
            if "kubeconfig_path" in arg_names:
                found = True
                break

        self.assertTrue(
            found,
            "The client initialization error log must include kubeconfig_path.",
        )

    def test_return_stays_inside_exception_handler(self):
        main_function, try_node = self._get_client_init_try()
        lines = self.source.splitlines()
        next_line = ""
        for line in lines[try_node.end_lineno:]:
            if line.strip():
                next_line = line
                break
        self.assertNotEqual(
            next_line.strip(),
            "return -1",
            "main() still has an unconditional return after the client init try/except.",
        )
        self.assertTrue(
            next_line.lstrip().startswith("distribution = \"kubernetes\""),
            "The statement after the client init try/except should continue normal execution.",
        )


if __name__ == "__main__":
    unittest.main()