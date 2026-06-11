"""Schema introspection and Hibernate Envers column classification.

Envers audit tables look like:

    <entity>_AUD ( <pk>, <col1>, <col1>_MOD, <col2>, <col2>_MOD, ...,
                   REV, REVTYPE [, REVEND, REVEND_TSTMP] )

  * REV       -> revision number, FK to the REVINFO table
  * REVTYPE   -> 0 = ADD, 1 = MOD, 2 = DEL
  * <col>_MOD -> boolean "modified flag": 1 when <col> changed in that revision
  * REVINFO   -> ( REV, REVTSTMP[, ...] ) maps a revision to an epoch-millis time

This module reads INFORMATION_SCHEMA (so it is schema-scoped and safe) and
groups the columns into identifier / data / modified-flag / system buckets.
"""
from __future__ import annotations

from .db import Database, DatabaseError

# Envers system columns (compared case-insensitively).
_SYSTEM_NAMES = {"rev", "revtype", "revend", "revend_tstmp"}


def quote_ident(name: str) -> str:
    """Backtick-quote an identifier so it is safe to interpolate into SQL.

    Identifiers cannot be passed as bound parameters, so every name that
    reaches a query is validated against INFORMATION_SCHEMA first and then
    escaped here (backticks doubled per MySQL/MariaDB rules).
    """
    if name is None:
        raise ValueError("identifier must not be None")
    return "`" + str(name).replace("`", "``") + "`"


# ── raw lookups ─────────────────────────────────────────────────────────
def list_tables(db: Database, like: str | None = None) -> list[str]:
    sql = (
        "SELECT TABLE_NAME FROM information_schema.tables "
        "WHERE TABLE_SCHEMA = DATABASE()"
    )
    params: list = []
    if like:
        sql += " AND TABLE_NAME LIKE %s"
        params.append(like)
    sql += " ORDER BY TABLE_NAME"
    return [r["TABLE_NAME"] for r in db.query(sql, params)]


def table_exists(db: Database, table: str) -> bool:
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM information_schema.tables "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
        [table],
    )
    return bool(row and row["n"])


def get_columns(db: Database, table: str) -> list[dict]:
    rows = db.query(
        "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY, "
        "       COLUMN_COMMENT, ORDINAL_POSITION "
        "FROM information_schema.columns "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
        "ORDER BY ORDINAL_POSITION",
        [table],
    )
    return [
        {
            "name": r["COLUMN_NAME"],
            "type": r["COLUMN_TYPE"],
            "nullable": r["IS_NULLABLE"] == "YES",
            "key": r["COLUMN_KEY"],
            "comment": r["COLUMN_COMMENT"] or "",
        }
        for r in rows
    ]


def get_pk_columns(db: Database, table: str) -> list[str]:
    rows = db.query(
        "SELECT COLUMN_NAME FROM information_schema.statistics "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
        "AND INDEX_NAME = 'PRIMARY' ORDER BY SEQ_IN_INDEX",
        [table],
    )
    return [r["COLUMN_NAME"] for r in rows]


# ── REVINFO discovery ───────────────────────────────────────────────────
def find_revinfo(db: Database) -> dict:
    """Locate the revision-info table and its REV / timestamp columns.

    The timestamp may be a BIGINT epoch (default Envers REVTSTMP) or a
    DATETIME/TIMESTAMP column (common with custom revision entities), so we try
    several strategies rather than assuming the default name/type.
    """
    tables = list_tables(db)
    target = next((t for t in tables if t.lower() == "revinfo"), None)
    if not target:
        target = next(
            (t for t in tables if t.lower() in ("revision", "rev_info", "revision_info", "revisions")),
            None,
        )
    if not target:
        return {"found": False}

    cols = get_columns(db, target)
    by_lower = {c["name"].lower(): c for c in cols}

    rev_col = (
        by_lower.get("rev", {}).get("name")
        or (get_pk_columns(db, target) or [None])[0]
        or (cols[0]["name"] if cols else None)
    )

    # Pick the timestamp column — never the REV column itself.
    candidates = [c for c in cols if c["name"] != rev_col]

    def _pick():
        for c in candidates:                       # 1) conventional Envers name
            if c["name"].lower() == "revtstmp":
                return c
        for c in candidates:                       # 2) name hints
            n = c["name"].lower()
            if "tstmp" in n or "timestamp" in n or "time" in n or n in ("created", "created_at", "reg_date", "rev_date"):
                return c
        for c in candidates:                       # 3) DATETIME / TIMESTAMP type
            if any(t in c["type"].lower() for t in ("datetime", "timestamp")):
                return c
        for c in candidates:                       # 4) BIGINT epoch
            if "bigint" in c["type"].lower():
                return c
        return None

    ts = _pick()
    return {
        "found": True,
        "table": target,
        "rev_column": rev_col,
        "ts_column": ts["name"] if ts else None,
        "ts_type": ts["type"] if ts else None,
    }


# ── classification ──────────────────────────────────────────────────────
def classify(columns: list[dict], pk_columns: list[str]) -> dict:
    """Bucket audit-table columns into identifier / data / mod-flag / system."""
    by_lower = {c["name"].lower(): c for c in columns}

    rev_column = by_lower.get("rev", {}).get("name")
    revtype_column = by_lower.get("revtype", {}).get("name")

    system, mod_flags = [], []
    for c in columns:
        low = c["name"].lower()
        if low in _SYSTEM_NAMES:
            system.append(c)
        elif low.endswith("_mod"):
            mod_flags.append(c)
    mod_flag_lower = {c["name"].lower() for c in mod_flags}

    # Identifier = primary-key columns minus the REV column.
    identifier_columns = [c for c in pk_columns if c.lower() != "rev"]
    if not identifier_columns:
        guess = by_lower.get("id")
        if guess:
            identifier_columns = [guess["name"]]
    ident_lower = {c.lower() for c in identifier_columns}

    # Data columns = everything that is not system / mod-flag / identifier,
    # each paired with its <col>_MOD flag when one exists.
    data_columns = []
    for c in columns:
        low = c["name"].lower()
        if low in _SYSTEM_NAMES or low in mod_flag_lower or low in ident_lower:
            continue
        flag = f"{low}_mod"
        mod_flag = by_lower[flag]["name"] if flag in by_lower else None
        data_columns.append(
            {"name": c["name"], "type": c["type"], "mod_flag": mod_flag}
        )

    # _MOD flags with no stored value column (e.g. audited collections /
    # relations) — we can only report THAT they changed, not an old->new value.
    data_lower = {dc["name"].lower() for dc in data_columns}
    orphan_mod_flags = []
    for c in mod_flags:
        base = c["name"][:-4]  # strip the trailing _MOD / _mod
        bl = base.lower()
        if bl and bl not in data_lower and bl not in ident_lower and bl not in _SYSTEM_NAMES:
            orphan_mod_flags.append({"name": c["name"], "label": base})

    identifier_default = identifier_columns[0] if identifier_columns else None
    return {
        "rev_column": rev_column,
        "revtype_column": revtype_column,
        "identifier_columns": identifier_columns,
        "identifier_default": identifier_default,
        "data_columns": data_columns,
        "system_columns": [{"name": c["name"], "type": c["type"]} for c in system],
        "mod_flag_columns": [c["name"] for c in mod_flags],
        "orphan_mod_flags": orphan_mod_flags,
        "has_mod_flags": bool(mod_flags),
    }


def describe_table(db: Database, table: str) -> dict:
    """Full preview payload for screen 2: columns + classification + REVINFO."""
    if not table_exists(db, table):
        raise DatabaseError(
            f"'{table}' 테이블을 현재 스키마({db.database})에서 찾을 수 없습니다."
        )
    columns = get_columns(db, table)
    pk = get_pk_columns(db, table)
    cls = classify(columns, pk)
    cls["revinfo"] = find_revinfo(db)
    cls["table"] = table
    cls["all_columns"] = columns
    return cls
