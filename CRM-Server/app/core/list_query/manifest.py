from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.core.list_query.types import FieldType

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from app.core.list_query.catalog import ListQueryCatalog

ListQueryFieldManifest = dict[str, FieldType | bool | list[str]]
ListQueryManifest = dict[str, dict[str, ListQueryFieldManifest]]


def build_list_query_manifest(catalogs: Mapping[str, ListQueryCatalog]) -> ListQueryManifest:
    """Project backend catalogs into the frontend query-key/type contract."""
    return {
        catalog_name: {
            field.key: {
                "type": field.type,
                "filterable": field.supports_filtering(),
                "sortable": field.supports_sorting(),
                "ops": sorted(field.ops()) if field.supports_filtering() else [],
            }
            for field in sorted(catalog.fields, key=lambda item: item.key)
        }
        for catalog_name, catalog in sorted(catalogs.items())
    }


def write_list_query_manifest(
    output_path: Path,
    catalogs: Mapping[str, ListQueryCatalog],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(build_list_query_manifest(catalogs), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
