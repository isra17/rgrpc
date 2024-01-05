# Copyright 2020 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from extra.codegen.protobuf.python.protoc_plugins import ProtocPlugins
from pants.backend.codegen.protobuf.target_types import (
    ProtobufSourcesGeneratorTarget,
    ProtobufSourceTarget,
)
from pants.backend.python.target_types import InterpreterConstraintsField, PythonResolveField
from pants.engine.target import StringField
from pants.util.strutil import help_text


class ProtobufPythonInterpreterConstraintsField(InterpreterConstraintsField):
    alias = "python_interpreter_constraints"


class ProtobufPythonResolveField(PythonResolveField):
    alias = "python_resolve"


class PythonSourceRootField(StringField):
    alias = "python_source_root"
    help = help_text(
        """
        The source root to generate Python sources under.

        If unspecified, the source root the `protobuf_sources` is under will be used.
        """
    )


class PythonProtocPluginField(StringField):
    alias = "python_protoc_plugin"
    valid_choices = ProtocPlugins
    default = ProtocPlugins.GRPCIO.value


def rules():
    return [
        ProtobufSourceTarget.register_plugin_field(ProtobufPythonInterpreterConstraintsField),
        ProtobufSourcesGeneratorTarget.register_plugin_field(
            ProtobufPythonInterpreterConstraintsField,
            as_moved_field=True,
        ),
        ProtobufSourceTarget.register_plugin_field(ProtobufPythonResolveField),
        ProtobufSourcesGeneratorTarget.register_plugin_field(
            ProtobufPythonResolveField, as_moved_field=True
        ),
        ProtobufSourceTarget.register_plugin_field(PythonSourceRootField),
        ProtobufSourcesGeneratorTarget.register_plugin_field(
            PythonSourceRootField, as_moved_field=True
        ),
        ProtobufSourceTarget.register_plugin_field(PythonProtocPluginField),
        ProtobufSourcesGeneratorTarget.register_plugin_field(
            PythonProtocPluginField, as_moved_field=True
        ),
    ]
