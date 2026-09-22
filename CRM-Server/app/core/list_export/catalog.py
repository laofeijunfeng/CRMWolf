"""Controlled export catalogs: field whitelist, labels, and cell types."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.core.list_export.errors import ListExportError

ListExportCellType = Literal["text", "number", "date", "datetime", "currency"]
ExportRow = Mapping[str, object]


def is_unsafe_export_key(key: str) -> bool:
    """Internal identifiers must never be exported; public_id forms are safe."""
    return key == "id" or (
        key.endswith("_id")
        and key != "public_id"
        and not key.endswith("_public_id")
    )


@dataclass(frozen=True)
class ListExportField:
    key: str
    label: str
    cell_type: ListExportCellType
    value_getter: Callable[[ExportRow], object] | None = None

    def value_from(self, row: ExportRow) -> object:
        return self.value_getter(row) if self.value_getter is not None else row.get(self.key)


@dataclass(frozen=True)
class ListExportCatalog:
    resource: str
    sheet_name: str
    fields: Sequence[ListExportField]
    _index: Mapping[str, ListExportField] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        index: dict[str, ListExportField] = {}
        for export_field in self.fields:
            key = export_field.key
            if is_unsafe_export_key(key):
                raise ListExportError(f"不安全导出字段: {key}")
            if key in index:
                raise ListExportError(f"重复导出字段: {key}")
            index[key] = export_field
        object.__setattr__(self, "_index", index)

    def select(self, keys: Sequence[str]) -> tuple[ListExportField, ...]:
        if not keys:
            raise ListExportError("至少选择一个导出字段")
        if len(set(keys)) != len(keys):
            raise ListExportError("导出字段不能重复")
        selected: list[ListExportField] = []
        for key in keys:
            export_field = self._index.get(key)
            if export_field is None:
                raise ListExportError(f"未知导出字段: {key}")
            selected.append(export_field)
        return tuple(selected)
