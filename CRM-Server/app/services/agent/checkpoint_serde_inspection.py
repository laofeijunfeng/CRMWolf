"""Inert checkpoint decoding for migration inventory and conversion gates."""

from __future__ import annotations

from dataclasses import dataclass

import ormsgpack
from langchain_core.load.load import ALL_SERIALIZABLE_MAPPINGS
from langgraph.checkpoint.serde import _msgpack as langgraph_msgpack
from langgraph.checkpoint.serde.jsonplus import (
    EXT_CONSTRUCTOR_KW_ARGS,
    EXT_CONSTRUCTOR_POS_ARGS,
    EXT_CONSTRUCTOR_SINGLE_ARG,
    EXT_DELTA_SNAPSHOT,
    EXT_METHOD_SINGLE_ARG,
    EXT_NUMPY_ARRAY,
    EXT_PYDANTIC_V1,
    EXT_PYDANTIC_V2,
    JsonPlusSerializer,
)

_CONSTRUCTOR_EXTENSIONS = frozenset(
    {
        EXT_CONSTRUCTOR_SINGLE_ARG,
        EXT_CONSTRUCTOR_POS_ARGS,
        EXT_CONSTRUCTOR_KW_ARGS,
        EXT_METHOD_SINGLE_ARG,
        EXT_PYDANTIC_V1,
        EXT_PYDANTIC_V2,
    }
)
_PYDANTIC_EXTENSIONS = frozenset({EXT_PYDANTIC_V1, EXT_PYDANTIC_V2})


class CheckpointSerdeInspectionError(ValueError):
    """A serialized checkpoint value cannot be safely classified."""


@dataclass(frozen=True)
class SerializedCheckpointConstructor:
    """Content-preserving constructor envelope that never imports its Python type."""

    module: str
    name: str
    payload: object
    extension_code: int | None
    safe_framework_type: bool

    @property
    def type_key(self) -> tuple[str, str]:
        return self.module, self.name

    @property
    def is_pydantic(self) -> bool:
        return self.extension_code in _PYDANTIC_EXTENSIONS


class CheckpointSerdeInspector(JsonPlusSerializer):
    """Decode structure and identities without executing serialized constructors."""

    def __init__(self) -> None:
        self.custom_type_occurrences: list[tuple[str, str]] = []
        super().__init__(__unpack_ext_hook__=self._unpack_ext)

    def _constructor(
        self,
        *,
        module: str,
        name: str,
        payload: object,
        extension_code: int | None,
        safe_framework_type: bool | None = None,
    ) -> SerializedCheckpointConstructor:
        key = (module, name)
        is_safe_framework_type = (
            key in langgraph_msgpack.SAFE_MSGPACK_TYPES if safe_framework_type is None else safe_framework_type
        )
        if not is_safe_framework_type:
            self.custom_type_occurrences.append(key)
        return SerializedCheckpointConstructor(
            module=module,
            name=name,
            payload=payload,
            extension_code=extension_code,
            safe_framework_type=is_safe_framework_type,
        )

    def _unpack_ext(self, code: int, data: bytes) -> object:
        try:
            unpacked = ormsgpack.unpackb(
                data,
                ext_hook=self._unpack_ext,
                option=ormsgpack.OPT_NON_STR_KEYS,
            )
        except Exception as error:
            raise CheckpointSerdeInspectionError("checkpoint extension payload cannot be decoded") from error

        if code == EXT_DELTA_SNAPSHOT:
            return unpacked
        if code == EXT_NUMPY_ARRAY:
            raise CheckpointSerdeInspectionError("numpy checkpoint extensions are outside the migration contract")
        if code not in _CONSTRUCTOR_EXTENSIONS:
            raise CheckpointSerdeInspectionError("unknown checkpoint extension code")
        if not isinstance(unpacked, (list, tuple)):
            raise CheckpointSerdeInspectionError("invalid checkpoint constructor envelope")
        expected_length = 4 if code in {EXT_METHOD_SINGLE_ARG, EXT_PYDANTIC_V2} else 3
        if len(unpacked) != expected_length:
            raise CheckpointSerdeInspectionError("invalid checkpoint constructor envelope")
        module, name, payload = unpacked[:3]
        if not isinstance(module, str) or not isinstance(name, str):
            raise CheckpointSerdeInspectionError("invalid checkpoint constructor identity")
        if code in _PYDANTIC_EXTENSIONS and not isinstance(payload, dict):
            raise CheckpointSerdeInspectionError("invalid checkpoint Pydantic payload")
        if code == EXT_CONSTRUCTOR_POS_ARGS and not isinstance(payload, (list, tuple)):
            raise CheckpointSerdeInspectionError("invalid positional constructor payload")
        if code == EXT_CONSTRUCTOR_KW_ARGS and not isinstance(payload, dict):
            raise CheckpointSerdeInspectionError("invalid keyword constructor payload")
        if code == EXT_PYDANTIC_V2 and unpacked[3] != "model_validate_json":
            raise CheckpointSerdeInspectionError("invalid checkpoint Pydantic constructor method")
        safe_framework_type: bool | None = None
        if code == EXT_METHOD_SINGLE_ARG:
            method = unpacked[3]
            if not isinstance(method, str):
                raise CheckpointSerdeInspectionError("invalid checkpoint constructor method")
            safe_framework_type = (module, name, method) in langgraph_msgpack.SAFE_MSGPACK_METHODS
        return self._constructor(
            module=module,
            name=name,
            payload=payload,
            extension_code=code,
            safe_framework_type=safe_framework_type,
        )

    def _reviver(self, value: dict[str, object]) -> object:
        if value.get("type") != "constructor":
            return value
        protocol_version = value.get("lc")
        if protocol_version not in {1, 2}:
            raise CheckpointSerdeInspectionError("unsupported JSON constructor protocol")
        allowed_fields = (
            {"lc", "type", "id", "kwargs"}
            if protocol_version == 1
            else {"lc", "type", "id", "args", "kwargs", "method"}
        )
        if not {"lc", "type", "id"}.issubset(value) or not set(value).issubset(allowed_fields):
            raise CheckpointSerdeInspectionError("invalid JSON constructor envelope")
        identity = value.get("id")
        if not isinstance(identity, list) or len(identity) < 2 or not all(isinstance(part, str) for part in identity):
            raise CheckpointSerdeInspectionError("invalid JSON constructor identity")
        identity_key = tuple(identity)
        resolved_identity = ALL_SERIALIZABLE_MAPPINGS.get(identity_key)
        if protocol_version == 1 and resolved_identity is None:
            resolved_type_key = ("", "")
        else:
            resolved_identity = resolved_identity or identity_key
            resolved_type_key = (".".join(resolved_identity[:-1]), resolved_identity[-1])
        if protocol_version == 1:
            payload = value.get("kwargs")
            if not isinstance(payload, dict) or "args" in value:
                raise CheckpointSerdeInspectionError("invalid lc:1 JSON constructor payload")
        else:
            args = value.get("args")
            kwargs = value.get("kwargs")
            if args is not None and not isinstance(args, list):
                raise CheckpointSerdeInspectionError("invalid lc:2 JSON constructor args")
            if kwargs is not None and not isinstance(kwargs, dict):
                raise CheckpointSerdeInspectionError("invalid lc:2 JSON constructor kwargs")
            payload = {"args": args, "kwargs": kwargs}
        module = ".".join(identity[:-1])
        name = identity[-1]
        return self._constructor(
            module=module,
            name=name,
            payload=payload,
            extension_code=None,
            safe_framework_type=resolved_type_key in langgraph_msgpack.SAFE_MSGPACK_TYPES,
        )
