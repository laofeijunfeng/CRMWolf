from __future__ import annotations

import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = SERVER_ROOT.parent
CLIENT_MANIFEST = REPOSITORY_ROOT / "CRM-Client" / "src" / "components" / "crmwolf" / "listQueryCatalogManifest.json"

if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.core.list_query.catalogs import LIST_QUERY_CATALOGS  # noqa: E402
from app.core.list_query.manifest import write_list_query_manifest  # noqa: E402


def main() -> None:
    write_list_query_manifest(CLIENT_MANIFEST, LIST_QUERY_CATALOGS)
    print(f"Generated {CLIENT_MANIFEST.relative_to(REPOSITORY_ROOT)}")


if __name__ == "__main__":
    main()
