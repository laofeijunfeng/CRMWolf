"""Project the backend export catalogs into the frontend contract manifest."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from app.core.list_export.catalog import ListExportCatalog

ListExportManifest = dict[str, dict[str, dict[str, str]]]


def build_list_export_manifest(
    catalogs: Mapping[str, ListExportCatalog],
) -> ListExportManifest:
    return {
        resource: {
            export_field.key: {"label": export_field.label, "type": export_field.cell_type}
            for export_field in catalog.fields
        }
        for resource, catalog in sorted(catalogs.items())
    }


def write_list_export_manifest(
    output_path: Path,
    catalogs: Mapping[str, ListExportCatalog],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(build_list_export_manifest(catalogs), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
