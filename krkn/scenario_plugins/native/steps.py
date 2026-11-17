"""Local schema and execution support for native scenario steps.

The native scenarios use YAML and Python functions. This module keeps their
input and output contract while providing local validation and serialization.
"""

import dataclasses
import inspect
import typing
from pathlib import Path
from types import SimpleNamespace, UnionType

import yaml


@dataclasses.dataclass(frozen=True)
class Minimum:
    value: int


@dataclasses.dataclass(frozen=True)
class RequiredIfNot:
    other: str


def _annotation_parts(annotation):
    if typing.get_origin(annotation) is typing.Annotated:
        base, *constraints = typing.get_args(annotation)
        return base, constraints
    return annotation, []


def _check_type(value, annotation, path):
    """Check YAML values against the dataclass's declared Python types."""
    annotation, _ = _annotation_parts(annotation)
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin in (typing.Union, UnionType):
        if value is None and type(None) in args:
            return
        errors = []
        for option in args:
            try:
                _check_type(value, option, path)
                return
            except ValueError as exc:
                errors.append(exc)
        raise ValueError(f"{path}: expected {annotation}, got {type(value).__name__}") from errors[-1]
    if annotation is type(None):
        if value is not None:
            raise ValueError(f"{path}: expected null")
        return
    if annotation is typing.Any:
        return
    if origin in (list, typing.List):
        if not isinstance(value, list):
            raise ValueError(f"{path}: expected list, got {type(value).__name__}")
        for index, item in enumerate(value):
            _check_type(item, args[0], f"{path}[{index}]")
    elif origin in (dict, typing.Dict):
        if not isinstance(value, dict):
            raise ValueError(f"{path}: expected dict, got {type(value).__name__}")
        for key, item in value.items():
            _check_type(key, args[0], f"{path} key")
            _check_type(item, args[1], f"{path}[{key!r}]")
    elif annotation in (str, int, float, bool):
        if type(value) is not annotation and not (
            annotation is float and type(value) is int
        ):
            raise ValueError(f"{path}: expected {annotation.__name__}, got {type(value).__name__}")


class InputSchema:
    def __init__(self, input_type):
        self.input_type = input_type
        self.properties = {field.name: field for field in dataclasses.fields(input_type)}
        self.annotations = typing.get_type_hints(input_type, include_extras=True)

    def unserialize(self, data):
        if not isinstance(data, dict):
            raise ValueError(f"{self.input_type.__name__}: expected an object")
        unknown = data.keys() - self.properties.keys()
        if unknown:
            raise ValueError(
                f"{self.input_type.__name__}: invalid parameter {sorted(unknown)[0]!r}"
            )
        values = {}
        for name, field in self.properties.items():
            if name in data and data[name] is not None:
                value = data[name]
            elif field.default is not dataclasses.MISSING:
                value = field.default
            elif field.default_factory is not dataclasses.MISSING:
                value = field.default_factory()
            elif name in data:
                raise ValueError(f"{self.input_type.__name__} -> {name}: null is not allowed")
            else:
                raise ValueError(f"{self.input_type.__name__} -> {name}: this field is required")
            annotation, constraints = _annotation_parts(self.annotations[name])
            if value is not None:
                _check_type(value, annotation, f"{self.input_type.__name__} -> {name}")
            for constraint in constraints:
                if isinstance(constraint, Minimum) and value is not None:
                    measured = len(value) if isinstance(value, (str, list, dict)) else value
                    if measured < constraint.value:
                        raise ValueError(
                            f"{self.input_type.__name__} -> {name}: must be at least {constraint.value}"
                        )
            values[name] = value
        for name, annotation in self.annotations.items():
            _, constraints = _annotation_parts(annotation)
            for constraint in constraints:
                if isinstance(constraint, RequiredIfNot):
                    if values[name] is None and values[constraint.other] is None:
                        raise ValueError(
                            f"{self.input_type.__name__} -> {name}: required because "
                            f"{constraint.other!r} is not set"
                        )
        return self.input_type(**values)


class OutputSchema:
    def __init__(self, output_type):
        self.output_type = output_type

    def serialize(self, value):
        if not isinstance(value, self.output_type):
            raise ValueError(f"expected {self.output_type.__name__} output")
        return dataclasses.asdict(value)


class StepSchema:
    def __init__(self, step_id, name, description, function, outputs):
        self.id = step_id
        self.name = name
        self.description = description
        self.function = function
        self.input = InputSchema(next(iter(inspect.signature(function).parameters.values())).annotation)
        self.outputs = {key: OutputSchema(value) for key, value in outputs.items()}

    def __call__(self, params, run_id=None):
        # run_id remains part of the public step interface, although the
        # current native functions do not consume it.
        output_id, output = self.function(params)
        if output_id not in self.outputs:
            raise ValueError(f"{self.id}: unknown output {output_id!r}")
        if not isinstance(output, self.outputs[output_id].output_type):
            raise ValueError(f"{self.id}: invalid {output_id!r} output")
        return output_id, output


def step(id, name, description, outputs):
    def decorate(function):
        return StepSchema(id, name, description, function, outputs)
    return decorate


def load_from_file(path):
    with Path(path).open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def _json_type(annotation):
    annotation, constraints = _annotation_parts(annotation)
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin in (typing.Union, UnionType):
        non_null = [arg for arg in args if arg is not type(None)]
        result = _json_type(non_null[0])
        if len(non_null) != len(args):
            result["type"] = [result["type"], "null"]
    elif origin in (list, typing.List):
        result = {"type": "array", "items": _json_type(args[0])}
    elif origin in (dict, typing.Dict):
        result = {"type": "object", "additionalProperties": _json_type(args[1])}
    else:
        result = {"type": {str: "string", int: "integer", float: "number", bool: "boolean"}.get(annotation, "object")}
    for constraint in constraints:
        if isinstance(constraint, Minimum):
            kind = result["type"]
            if isinstance(kind, list):
                kind = next(item for item in kind if item != "null")
            key = {"string": "minLength", "array": "minItems", "object": "minProperties"}.get(kind, "minimum")
            result[key] = constraint.value
    return result


def step_input(step_schema):
    input_schema = step_schema.input
    properties = {}
    required = []
    alternatives = set()
    for name, field in input_schema.properties.items():
        value = _json_type(input_schema.annotations[name])
        if field.default is not dataclasses.MISSING:
            value["default"] = field.default
        elif field.default_factory is not dataclasses.MISSING:
            value["default"] = field.default_factory()
        else:
            required.append(name)
        if field.metadata:
            value.update(field.metadata)
        properties[name] = value
        _, constraints = _annotation_parts(input_schema.annotations[name])
        for constraint in constraints:
            if isinstance(constraint, RequiredIfNot):
                alternatives.add(tuple(sorted((name, constraint.other))))
    result = {
        "$id": step_schema.id,
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"{step_schema.name} input",
        "description": step_schema.description,
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    if alternatives:
        result["allOf"] = [
            {"anyOf": [{"required": [name]} for name in pair]}
            for pair in sorted(alternatives)
        ]
    return result


plugin = SimpleNamespace(step=step)
validation = SimpleNamespace(min=Minimum, required_if_not=RequiredIfNot)
schema = SimpleNamespace(StepSchema=StepSchema)
serialization = SimpleNamespace(load_from_file=load_from_file)
jsonschema = SimpleNamespace(step_input=step_input)
