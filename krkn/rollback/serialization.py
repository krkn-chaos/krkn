import inspect
import os
import logging
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader

if TYPE_CHECKING:
    from krkn.rollback.config import RollbackCallable, RollbackContent, Version

logger = logging.getLogger(__name__)


class Serializer:
    def __init__(self, scenario_type: str):
        self.scenario_type = scenario_type
        # Set up Jinja2 environment to load templates from the rollback directory
        template_dir = os.path.join(os.path.dirname(__file__))
        env = Environment(loader=FileSystemLoader(template_dir))
        self.template = env.get_template("version_template.j2")

    def _parse_rollback_callable_code(
        self, callable: "RollbackCallable"
    ) -> tuple[str, str]:
        """
        Parse the rollback callable code to extract its implementation.
        :param callable: The callable function to parse (can be staticmethod or regular function).
        :return: A tuple containing (function_name, function_code).
        """
        # Get the implementation code of the rollback_callable
        rollback_callable_code = inspect.getsource(callable)

        # Split into lines for processing
        code_lines = rollback_callable_code.split("\n")
        cleaned_lines = []
        function_name = None

        # Find the function definition line and extract function name
        def_line_index = None
        for i, line in enumerate(code_lines):
            # Skip decorators (including @staticmethod)
            if line.strip().startswith("@"):
                continue

            # Look for function definition
            if line.strip().startswith("def "):
                def_line_index = i
                # Extract function name from the def line
                def_line = line.strip()
                if "(" in def_line:
                    function_name = def_line.split("def ")[1].split("(")[0].strip()
                break

        if def_line_index is None or function_name is None:
            raise ValueError(
                "Could not find function definition in callable source code"
            )

        # Get the base indentation level from the def line
        def_line = code_lines[def_line_index]
        base_indent_level = len(def_line) - len(def_line.lstrip())

        # Process all lines starting from the def line
        for i in range(def_line_index, len(code_lines)):
            line = code_lines[i]

            # Handle empty lines
            if not line.strip():
                cleaned_lines.append("")
                continue

            # Calculate current line's indentation
            current_indent = len(line) - len(line.lstrip())

            # Remove the base indentation to normalize to function level
            if current_indent >= base_indent_level:
                # Remove base indentation
                normalized_line = line[base_indent_level:]
                cleaned_lines.append(normalized_line)
            else:
                # This shouldn't happen in well-formed code, but handle it gracefully
                cleaned_lines.append(line.lstrip())

        # Reconstruct the code and clean up trailing whitespace
        function_code = "\n".join(cleaned_lines).rstrip()

        return function_name, function_code

    def serialize_callable(
        self,
        callable: "RollbackCallable",
        rollback_content: "RollbackContent",
        version: "Version",
    ) -> str:
        """
        Serialize a callable function to a file with its arguments and keyword arguments.
        :param callable: The callable to serialize.
        :param rollback_content: The rollback content for the callable.
        :return: Path to the serialized callable file.
        """

        rollback_callable_name, rollback_callable_code = (
            self._parse_rollback_callable_code(callable)
        )

        # Render the template with the required variables
        file_content = self.template.render(
            rollback_callable_name=rollback_callable_name,
            rollback_callable_code=rollback_callable_code,
            rollback_content=str(rollback_content),
        )

        # Write the file to the version directory
        os.makedirs(os.path.dirname(version.version_file_full_path), exist_ok=True)

        logger.debug("Creating version file at %s", version.version_file_full_path)
        logger.debug("Version file content:\n%s", file_content)
        with open(version.version_file_full_path, "w") as f:
            f.write(file_content)
        logger.info(f"Serialized callable written to {version.version_file_full_path}")

        return version.version_file_full_path
