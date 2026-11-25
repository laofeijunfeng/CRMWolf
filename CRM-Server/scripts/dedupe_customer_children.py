#!/usr/bin/env python3
"""Merge duplicate contacts / invoice titles / deployments within a customer (CRM-164).

Run after migration 171 and before 172:

    python scripts/dedupe_customer_children.py export --out plan.csv
    # review plan.csv; a group's keep row may be moved, nothing else edited
    python scripts/dedupe_customer_children.py apply --plan plan.csv

``export`` lists every duplicate group (same customer, same dedupe key), the proposed
keep row and the reference count of each record, and prints counts of empty and
unnormalized values. ``apply`` re-reads each group, refuses on any drift, then in one
transaction repoints references to the kept row, hands it the primary/default flag,
deletes the rest and asserts reference counts are unchanged. Snapshot fields are not touched.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import bindparam, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.dedupe_normalizer import normalize_mobile, normalize_server_address, normalize_taxpayer_id

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from sqlalchemy.engine import Connection
    from sqlalchemy.sql.elements import BindParameter


@dataclass(frozen=True)
class EntitySpec:
    table: str
    key_column: str
    value_column: str
    name_column: str
    flag_column: str
    references: tuple[tuple[str, str], ...]
    normalize: Callable[[str | None], str]


ENTITIES: dict[str, EntitySpec] = {
    "contact": EntitySpec(
        "crm_contacts", "mobile_dedupe_key", "mobile", "name", "is_primary",
        (("crm_contracts", "signing_contact_id"), ("crm_contacts", "reports_to")),
        normalize_mobile,
    ),
    "invoice_title": EntitySpec(
        "crm_invoice_titles", "taxpayer_dedupe_key", "taxpayer_id", "title", "is_default",
        (("crm_invoice_applications", "invoice_title_id"),),
        normalize_taxpayer_id,
    ),
    "deployment_info": EntitySpec(
        "crm_deployment_infos", "server_address_dedupe_key", "server_address", "deployment_name", "is_default",
        (("crm_license_applications", "deployment_info_id"),),
        normalize_server_address,
    ),
}

CSV_FIELDS = (
    "entity", "customer_id", "team_id", "dedupe_key", "record_id", "action",
    "name", "value", "flagged", "created_time", "ref_count",
)


class PlanError(RuntimeError):
    """The plan is malformed or no longer matches the database."""


@dataclass(frozen=True)
class PlanRow:
    entity: str
    customer_id: int
    team_id: int
    dedupe_key: str
    record_id: int
    action: str
    name: str
    value: str
    flagged: bool
    created_time: str
    ref_count: int

    def to_csv(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in CSV_FIELDS} | {"flagged": int(self.flagged)}


@dataclass(frozen=True)
class Record:
    id: int
    team_id: int
    name: str
    value: str
    flagged: bool
    created_time: str


@dataclass(frozen=True)
class ApplyReport:
    groups: int
    deleted: int
    self_reports: list[int]


def _ref_counts(conn: Connection, spec: EntitySpec, ids: list[int]) -> dict[int, int]:
    counts = dict.fromkeys(ids, 0)
    for table, column in spec.references:
        rows = conn.execute(
            text(f"SELECT {column}, COUNT(*) FROM {table} WHERE {column} IN :ids GROUP BY {column}")
            .bindparams(bindparam("ids", expanding=True)),
            {"ids": ids},
        ).all()
        for ref_id, count in rows:
            counts[int(ref_id)] += int(count)
    return counts


def _group_records(conn: Connection, spec: EntitySpec, customer_id: int, key: str) -> list[Record]:
    rows = conn.execute(text(
        f"SELECT id, team_id, {spec.name_column}, {spec.value_column}, {spec.flag_column}, created_time "
        f"FROM {spec.table} WHERE customer_id = :customer_id AND {spec.key_column} = :key ORDER BY id"
    ), {"customer_id": customer_id, "key": key}).all()
    return [
        Record(int(row[0]), int(row[1]), str(row[2] or ""), str(row[3] or ""), bool(row[4]), str(row[5]))
        for row in rows
    ]


def _choose_keep(records: list[Record], ref_counts: dict[int, int]) -> int:
    """Referenced first, then earliest created_time, then lowest id."""
    return min(records, key=lambda r: (ref_counts[r.id] == 0, r.created_time, r.id)).id


def export_plan(conn: Connection) -> list[PlanRow]:
    plan: list[PlanRow] = []
    for entity, spec in ENTITIES.items():
        groups = conn.execute(text(
            f"SELECT customer_id, {spec.key_column} FROM {spec.table} WHERE {spec.key_column} IS NOT NULL "
            f"GROUP BY customer_id, {spec.key_column} HAVING COUNT(*) > 1 ORDER BY customer_id, {spec.key_column}"
        )).all()
        for customer_id, key in groups:
            records = _group_records(conn, spec, customer_id, key)
            ref_counts = _ref_counts(conn, spec, [r.id for r in records])
            keep_id = _choose_keep(records, ref_counts)
            plan.extend(
                PlanRow(
                    entity=entity, customer_id=int(customer_id), team_id=r.team_id, dedupe_key=str(key),
                    record_id=r.id, action="keep" if r.id == keep_id else "delete", name=r.name, value=r.value,
                    flagged=r.flagged, created_time=r.created_time, ref_count=ref_counts[r.id],
                )
                for r in records
            )
    return plan


def value_summary(conn: Connection) -> dict[str, dict[str, int]]:
    """Per entity: rows whose value is empty (no key) and rows whose stored value is not normalized."""
    summary: dict[str, dict[str, int]] = {}
    for entity, spec in ENTITIES.items():
        values = conn.execute(text(f"SELECT {spec.value_column} FROM {spec.table}")).scalars().all()
        summary[entity] = {
            "empty": sum(1 for value in values if not spec.normalize(value)),
            "unnormalized": sum(1 for value in values if value and spec.normalize(value) != value),
        }
    return summary


def write_plan(rows: Iterable[PlanRow], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(row.to_csv() for row in rows)


def read_plan(path: str) -> list[PlanRow]:
    with open(path, newline="", encoding="utf-8") as handle:
        return [
            PlanRow(
                entity=row["entity"], customer_id=int(row["customer_id"]), team_id=int(row["team_id"]),
                dedupe_key=row["dedupe_key"], record_id=int(row["record_id"]), action=row["action"].strip(),
                name=row["name"], value=row["value"], flagged=row["flagged"] == "1",
                created_time=row["created_time"], ref_count=int(row["ref_count"]),
            )
            for row in csv.DictReader(handle)
        ]


def _total_refs(conn: Connection, table: str, column: str, ids: list[int], exclude_rows: list[int]) -> int:
    sql = f"SELECT COUNT(*) FROM {table} WHERE {column} IN :ids"
    params: dict[str, object] = {"ids": ids}
    binds: list[BindParameter[list[int]]] = [bindparam("ids", expanding=True)]
    if exclude_rows:
        sql += " AND id NOT IN :exclude"
        params["exclude"] = exclude_rows
        binds.append(bindparam("exclude", expanding=True))
    return int(conn.execute(text(sql).bindparams(*binds), params).scalar_one())


def apply_plan(conn: Connection, plan: list[PlanRow]) -> ApplyReport:
    """Validate every group against the database, then merge. The caller owns the transaction."""
    groups: dict[tuple[str, int, str], list[PlanRow]] = defaultdict(list)
    for row in plan:
        if row.entity not in ENTITIES or row.action not in {"keep", "delete"}:
            raise PlanError(f"invalid row for record {row.record_id}: entity={row.entity!r} action={row.action!r}")
        groups[(row.entity, row.customer_id, row.dedupe_key)].append(row)

    merges: list[tuple[EntitySpec, int, list[int]]] = []
    for (entity, customer_id, key), rows in groups.items():
        spec = ENTITIES[entity]
        keeps = [row.record_id for row in rows if row.action == "keep"]
        if len(keeps) != 1 or len(rows) < 2:
            raise PlanError(f"{entity} customer {customer_id} key {key!r}: need one keep and at least one delete")
        current_ids = [r.id for r in _group_records(conn, spec, customer_id, key)]
        planned_ids = sorted(row.record_id for row in rows)
        if current_ids != planned_ids:
            raise PlanError(
                f"{entity} customer {customer_id} key {key!r} drifted: plan {planned_ids}, database {current_ids}"
            )
        ref_counts = _ref_counts(conn, spec, current_ids)
        drifted = [row.record_id for row in rows if ref_counts[row.record_id] != row.ref_count]
        if drifted:
            raise PlanError(f"{entity} customer {customer_id} key {key!r}: reference counts changed for {drifted}")
        merges.append((spec, keeps[0], [row.record_id for row in rows if row.action == "delete"]))

    deleted_rows: dict[str, list[int]] = defaultdict(list)
    for spec, _keep, deletes in merges:
        deleted_rows[spec.table].extend(deletes)

    def surviving_refs(spec: EntitySpec, ids: list[int]) -> dict[tuple[str, str], int]:
        return {
            (table, column): _total_refs(
                conn, table, column, ids, deleted_rows[table] if table == spec.table else []
            )
            for table, column in spec.references
        }

    before = [surviving_refs(spec, [keep, *deletes]) for spec, keep, deletes in merges]
    self_reports: list[int] = []
    for spec, keep, deletes in merges:
        params = {"keep": keep, "deletes": deletes}
        expanding: BindParameter[list[int]] = bindparam("deletes", expanding=True)
        for table, column in spec.references:
            conn.execute(
                text(f"UPDATE {table} SET {column} = :keep WHERE {column} IN :deletes").bindparams(expanding),
                params,
            )
        if spec.table == "crm_contacts" and conn.execute(
            text("SELECT reports_to FROM crm_contacts WHERE id = :keep"), params
        ).scalar_one() == keep:
            self_reports.append(keep)
        flagged = conn.execute(
            text(f"SELECT COUNT(*) FROM {spec.table} WHERE id IN :deletes AND {spec.flag_column} = 1")
            .bindparams(expanding),
            params,
        ).scalar_one()
        if flagged:
            conn.execute(text(f"UPDATE {spec.table} SET {spec.flag_column} = 1 WHERE id = :keep"), params)
        conn.execute(text(f"DELETE FROM {spec.table} WHERE id IN :deletes").bindparams(expanding), params)

    for (spec, keep, _deletes), expected in zip(merges, before, strict=True):
        after = surviving_refs(spec, [keep])
        if after != expected:
            raise PlanError(f"{spec.table} keep {keep}: reference counts {expected} became {after}; rolled back")
    return ApplyReport(groups=len(merges), deleted=sum(len(d) for _, _, d in merges), self_reports=self_reports)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    export_cmd = commands.add_parser("export", help="write the duplicate plan CSV")
    export_cmd.add_argument("--out", required=True)
    apply_cmd = commands.add_parser("apply", help="apply a reviewed plan CSV in one transaction")
    apply_cmd.add_argument("--plan", required=True)
    args = parser.parse_args(argv)

    from app.core.database import engine

    if args.command == "export":
        with engine.connect() as conn:
            plan = export_plan(conn)
            summary = value_summary(conn)
        write_plan(plan, args.out)
        group_count = len({(r.entity, r.customer_id, r.dedupe_key) for r in plan})
        deletes = sum(r.action == "delete" for r in plan)
        print(f"{group_count} duplicate groups, {deletes} records to delete -> {args.out}")
        for entity, counts in summary.items():
            print(f"{entity}: empty={counts['empty']} unnormalized={counts['unnormalized']}")
        return 0

    plan = read_plan(args.plan)
    try:
        with engine.begin() as conn:
            report = apply_plan(conn, plan)
    except PlanError as exc:
        print(f"refused, nothing changed: {exc}", file=sys.stderr)
        return 1
    print(f"merged {report.groups} groups, deleted {report.deleted} records")
    if report.self_reports:
        print(f"contacts now reporting to themselves (review): {report.self_reports}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
