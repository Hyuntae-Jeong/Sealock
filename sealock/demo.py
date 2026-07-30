"""Synthetic Envers data for the "샘플 데이터로 둘러보기" mode (no DB needed).

All values are fabricated (example.com, made-up ids) so they are safe to ship
in a public repo. The rows are shaped exactly like real Envers audit rows, so
they flow through the same history.build_timeline() / build_changeset_timeline()
path as live data.

Each table is generated from a single ordered event log, which keeps the two
조회 모드 consistent: the revisions a 식별자 검색 shows for a record are exactly
the ones the 전체 이력 timeline lists for it. Events that share a timestamp
become one revision (they were one transaction), so batch jobs land several
records in a single revision — the case the all-records view exists for.
REV numbers are handed out across all three tables in time order, the way a
shared REVINFO sequence does it, so they interleave and are not contiguous
within one table.

The three tables each demo a different shape of history:

  * ``member_aud``   — small and mixed: 생성 / 수정 / 삭제, per-record stories
  * ``order_aud``    — high volume: 200+ revisions, so 전체 이력 pages
                       ("이전 리비전 더 보기") and the 사전 집계 is worth reading
  * ``product_aud``  — batch-heavy: single revisions touching a whole category,
                       plus a BIT column to show how non-text values render

Timestamps are laid out relative to *today*, so every 기간 preset
(최근 7일 / 30일 / 3개월 / 1년) lands on data.
"""
from __future__ import annotations

import datetime as _dt
from decimal import Decimal

from .history import format_ts

# Korea Standard Time — the zone history.format_ts renders revisions in.
_KST = _dt.timezone(_dt.timedelta(hours=9))
_TODAY = _dt.datetime.now(_KST).replace(hour=0, minute=0, second=0, microsecond=0)

_ADD, _MOD, _DEL = 0, 1, 2      # REVTYPE values
_REV_BASE = 1000                # first revision number handed out

DEFAULT_TABLE = "member_aud"


def _ago(days: int, clock: str = "00:00") -> int:
    """Epoch millis for ``days`` days before today at HH:MM (KST)."""
    hh, mm = (int(x) for x in clock.split(":"))
    when = _TODAY - _dt.timedelta(days=days) + _dt.timedelta(hours=hh, minutes=mm)
    return int(when.timestamp() * 1000)


# ── table shapes ────────────────────────────────────────────────────────
# One entry per demo table: what introspect.describe_table() would report for
# it, and what the generated audit rows carry.
_SPECS = {
    "member_aud": {
        "ident": ("id", "bigint(20)"),
        "rev_type": "int(11)",
        "columns": (
            ("username", "varchar(50)"),
            ("email", "varchar(120)"),
            ("status", "varchar(20)"),
            ("points", "int(11)"),
            ("grade", "varchar(20)"),
        ),
        "orphans": (),
        "example": "42",
    },
    "order_aud": {
        "ident": ("id", "bigint(20)"),
        "rev_type": "bigint(20)",
        "columns": (
            ("order_no", "varchar(32)"),
            ("status", "varchar(20)"),
            ("total_amount", "decimal(12,2)"),
            ("payment_method", "varchar(20)"),
            ("shipping_no", "varchar(40)"),
        ),
        # An audited @OneToMany collection: Envers stores the "changed" flag but
        # no value column, so the timeline can only report 변경됨.
        "orphans": ("items",),
        "example": "5057",
    },
    "product_aud": {
        "ident": ("id", "bigint(20)"),
        "rev_type": "int(11)",
        "columns": (
            ("name", "varchar(120)"),
            ("price", "int(11)"),
            ("stock", "int(11)"),
            ("category", "varchar(40)"),
            ("on_sale", "bit(1)"),
        ),
        "orphans": (),
        "example": "303",
    },
}

_ON, _OFF = b"\x01", b"\x00"    # bit(1) as the driver hands it over


def _describe(table: str) -> dict:
    """Mirror of introspect.describe_table() for a generated demo table."""
    spec = _SPECS[table]
    ident, ident_type = spec["ident"]
    cols = spec["columns"]
    flags = [f"{c}_MOD" for c, _t in cols] + [f"{o}_MOD" for o in spec["orphans"]]
    all_cols = [{"name": ident, "type": ident_type},
                {"name": "REV", "type": spec["rev_type"]},
                {"name": "REVTYPE", "type": "tinyint(4)"}]
    for name, ctype in cols:
        all_cols.append({"name": name, "type": ctype})
        all_cols.append({"name": f"{name}_MOD", "type": "bit(1)"})
    all_cols += [{"name": f"{o}_MOD", "type": "bit(1)"} for o in spec["orphans"]]
    return {
        "table": table,
        "rev_column": "REV",
        "revtype_column": "REVTYPE",
        "has_mod_flags": True,
        "mod_flag_columns": flags,
        "identifier_columns": [ident],
        "identifier_default": ident,
        "data_columns": [{"name": c, "type": t, "mod_flag": f"{c}_MOD"} for c, t in cols],
        "system_columns": [{"name": "REV", "type": spec["rev_type"]},
                           {"name": "REVTYPE", "type": "tinyint(4)"}],
        "orphan_mod_flags": [{"name": f"{o}_MOD", "label": o} for o in spec["orphans"]],
        "revinfo": {"found": True, "table": "REVINFO", "rev_column": "REV",
                    "ts_column": "REVTSTMP", "ts_type": "bigint(20)"},
        "all_columns": all_cols,
    }


# ── event log: member_aud ───────────────────────────────────────────────
def _member_events() -> list[tuple]:
    """14 signups, point / grade / status changes, two 배치 revisions that touch
    several members at once, and one 탈퇴 (DELETE)."""
    ev: list[tuple] = []

    def at(days, clock, mid, rtype=_MOD, **values):
        ev.append((_ago(days, clock), mid, rtype, values, ()))

    signups = [  # (id, username, 가입 D-일, 가입 시각)
        (17, "bora", 402, "07:41"),
        (23, "chris", 388, "13:02"),
        (42, "alice", 371, "09:12"),
        (47, "dana", 355, "18:26"),
        (58, "eunji", 311, "10:47"),
        (61, "felix", 268, "21:33"),
        (73, "grace", 197, "08:19"),
        (88, "hoon", 142, "15:58"),
        (91, "iris", 96, "11:24"),
        (104, "jaemin", 61, "19:05"),
        (110, "kate", 34, "09:48"),
        (118, "luna", 17, "14:12"),
        (125, "noah", 6, "10:31"),
        (129, "sora", 2, "16:44"),
    ]
    for mid, user, days, clock in signups:
        at(days, clock, mid, _ADD, username=user, email=f"{user}@example.com",
           status="ACTIVE", points=0, grade="BRONZE")

    # id=42 (alice) — the record the 식별자 검색 placeholder points at, so it
    # carries the fullest story: 적립 · 등급 승급 · 이메일 변경 · 휴면과 해제.
    at(300, "16:40", 42, points=100, grade="SILVER")
    at(220, "11:05", 42, email="alice.kim@example.com", status="DORMANT")
    at(150, "20:15", 42, status="ACTIVE", points=250, grade="GOLD")
    at(64, "09:26", 42, points=480)
    at(21, "13:52", 42, points=1250, grade="PLATINUM")
    at(5, "10:07", 42, email="alice@example.com", points=1310)

    # 등급 일괄 재산정 (배치) — one revision, several members.
    for mid, pts, grade in ((17, 320, "SILVER"), (23, 180, "SILVER"), (58, 640, "GOLD")):
        at(180, "03:10", mid, points=pts, grade=grade)
    for mid, pts, grade in ((61, 210, "SILVER"), (73, 90, "BRONZE"),
                            (88, 1120, "PLATINUM"), (91, 470, "GOLD")):
        at(45, "03:10", mid, points=pts, grade=grade)
    # 90일 미접속 휴면 전환 (배치)
    for mid in (23, 61):
        at(90, "02:00", mid, status="DORMANT")

    # 개별 변경
    at(340, "10:22", 17, email="bora.lee@example.com")
    at(291, "15:37", 47, points=80)
    at(240, "12:04", 58, email="eunji.p@example.com")
    at(205, "17:49", 61, points=40)
    at(160, "08:58", 73, email="grace.h@example.com", status="ACTIVE")
    at(133, "19:20", 17, status="DORMANT")
    at(120, "14:03", 47, _DEL)                       # 회원 탈퇴 — 레코드 삭제
    at(102, "09:33", 88, points=760, grade="GOLD")
    at(70, "16:11", 17, status="ACTIVE", points=520, grade="GOLD")
    at(52, "13:27", 91, email="iris.j@example.com")
    at(33, "20:41", 104, points=150, grade="BRONZE")
    at(26, "11:19", 58, points=980, grade="PLATINUM")
    at(12, "18:02", 110, points=60)
    at(9, "10:55", 118, email="luna.s@example.com")

    # 최근 7일 — '최근 7일' 프리셋에도 볼 거리가 남도록.
    at(4, "18:20", 110, points=150, grade="SILVER")
    at(3, "09:05", 104, status="DORMANT")
    at(2, "11:47", 91, points=530)
    at(1, "11:38", 88, points=1260)
    at(1, "20:14", 125, points=30)
    return ev


# ── event log: order_aud ────────────────────────────────────────────────
_ORDER_COUNT = 72
_ORDER_AMOUNTS = (24900, 89000, 259000, 39000, 132000, 68000,
                  415000, 21000, 79000, 187000, 45000, 92000)
_ORDER_METHODS = ("CARD", "CARD", "BANK", "VIRTUAL", "CARD", "POINT")
_BATCH_CANCEL = (5031, 5032, 5034, 5035)   # 결제 없이 남아 일괄 취소된 주문
_PURGE = (5001, 5002, 5003)                # 보관 기간이 지나 일괄 파기된 주문


def _order_events() -> list[tuple]:
    """~72 orders walking CREATED → PAID → SHIPPED → DELIVERED, plus 취소 /
    환불 paths and three batch jobs.

    출고와 배송 완료는 매일 정해진 시각에 도는 배치라, 같은 날 주문들이 한
    리비전에 묶인다 — 전체 이력에서 레코드 여러 건이 든 카드가 그것이다.
    """
    ev: list[tuple] = []
    created: dict[int, int] = {}

    def at(days, clock, oid, rtype=_MOD, flags=(), **values):
        ev.append((_ago(days, clock), oid, rtype, values, flags))

    def clock(i, hour):
        return f"{hour + i % 4:02d}:{(i * 17) % 60:02d}"

    for i in range(_ORDER_COUNT):
        oid = 5001 + i
        # 오래된 주문일수록 듬성듬성, 최근으로 올수록 촘촘하게 — 어느 기간
        # 프리셋을 골라도 볼 거리가 남도록 배치한다. 하루에 두 건씩 들어와야
        # 같은 날 주문이 한 출고 배치에 묶인다.
        day = round(384 * (1 - (i // 2) / (_ORDER_COUNT // 2 - 1)) ** 1.9) + 2
        created[oid] = day
        amount = Decimal(f"{_ORDER_AMOUNTS[i % len(_ORDER_AMOUNTS)] + (i % 5) * 1200}.00")
        placed = _TODAY - _dt.timedelta(days=day)
        at(day, clock(i, 9), oid, _ADD, flags=("items",),
           order_no=f"ORD-{placed:%Y%m%d}-{oid:04d}", status="CREATED",
           total_amount=amount, payment_method=_ORDER_METHODS[i % len(_ORDER_METHODS)],
           shipping_no=None)

        if oid in _BATCH_CANCEL:
            continue                                  # 아래 일괄 취소 배치에서 처리
        if day < 3:
            continue                                  # 방금 들어온 주문 — 아직 결제 전
        if i % 13 == 4:                               # 담을 품목을 바꾼 뒤 결제
            at(day, clock(i, 12), oid, flags=("items",), total_amount=amount + 12000)
            amount += 12000
        at(day, clock(i, 15), oid, status="PAID")
        if day < 6:
            continue                                  # 아직 출고 전
        at(day - 2, "18:30", oid, status="SHIPPED",   # 출고 마감 배치
           shipping_no=f"KR{5_100_000 + oid * 37:09d}")
        if day < 8:
            continue
        at(day - 4, "09:15", oid, status="DELIVERED")  # 배송 완료 반영 배치
        if i % 17 == 5 and day >= 16:                  # 수령 후 환불
            at(day - 9, clock(i, 14), oid, flags=("items",), status="REFUNDED")

    # 미결제 주문 일괄 취소 (배치) — 네 건이 한 리비전에 들어간다.
    cancel_day = min(created[o] for o in _BATCH_CANCEL) - 4
    for oid in _BATCH_CANCEL:
        at(cancel_day, "04:00", oid, status="CANCELLED")

    # 보관 기간 만료 주문 일괄 파기 (배치) — DELETE 세 건이 한 리비전에.
    purge_day = min(45, min(created[o] for o in _PURGE) - 30)
    for oid in _PURGE:
        at(purge_day, "01:00", oid, _DEL)
    return ev


# ── event log: product_aud ──────────────────────────────────────────────
def _product_events() -> list[tuple]:
    """16 products: two catalog loads, seasonal 세일 배치, 재고 실사, and one
    단종 (DELETE). The batch revisions are the wide cards in 전체 이력."""
    ev: list[tuple] = []

    def at(days, clock, pid, rtype=_MOD, **values):
        ev.append((_ago(days, clock), pid, rtype, values, ()))

    catalog = [  # (id, 상품명, 가격, 재고, 분류)
        (301, "무선 마우스 M1", 24900, 120, "주변기기"),
        (302, "기계식 키보드 K2", 89000, 60, "주변기기"),
        (303, "27인치 모니터 U27", 259000, 25, "디스플레이"),
        (304, "USB-C 허브 H7", 39000, 200, "주변기기"),
        (305, "노트북 스탠드 S3", 21000, 150, "액세서리"),
        (306, "블루투스 이어폰 B5", 79000, 80, "음향"),
        (307, "웹캠 W1", 45000, 40, "영상"),
        (308, "모니터암 A2", 68000, 30, "액세서리"),
    ]
    # 초기 카탈로그 적재 — 한 리비전에 8건이 생성된다.
    for pid, name, price, stock, cat in catalog:
        at(382, "10:00", pid, _ADD, name=name, price=price, stock=stock,
           category=cat, on_sale=_OFF)
    # 2차 입점
    for pid, name, price, stock, cat in (
        (309, "외장 SSD 1TB", 119000, 55, "저장장치"),
        (310, "노트북 파우치 13", 18000, 300, "액세서리"),
        (311, "USB 마이크 M9", 92000, 18, "음향"),
        (312, "듀얼 충전 독", 34000, 90, "액세서리"),
    ):
        at(240, "11:20", pid, _ADD, name=name, price=price, stock=stock,
           category=cat, on_sale=_OFF)
    for days, clock, pid, name, price, stock, cat in (
        (75, "14:35", 313, "4K 캡처보드 C4", 178000, 12, "영상"),
        (75, "14:35", 314, "링라이트 R2", 29000, 70, "영상"),
        (20, "16:08", 315, "휴대용 SSD 2TB", 209000, 22, "저장장치"),
        (3, "10:26", 316, "무선 충전 패드 P1", 27000, 140, "액세서리"),
    ):
        at(days, clock, pid, _ADD, name=name, price=price, stock=stock,
           category=cat, on_sale=_OFF)

    # 봄 세일 시작 / 종료 (배치) — 여섯 개 상품이 한 리비전에서 함께 바뀐다.
    sale = ((301, 19900), (302, 71000), (304, 31000),
            (305, 16800), (306, 63000), (310, 14400))
    for pid, price in sale:
        at(100, "00:05", pid, price=price, on_sale=_ON)
    for pid, price in ((301, 24900), (302, 89000), (304, 39000),
                       (305, 21000), (306, 79000), (310, 18000)):
        at(86, "23:50", pid, price=price, on_sale=_OFF)

    # 재고 실사 반영 (배치)
    for pid, stock in ((301, 86), (303, 14), (304, 172), (306, 51),
                       (309, 33), (311, 9), (312, 64)):
        at(30, "02:30", pid, stock=stock)

    # 개별 가격 · 재고 변경
    at(352, "13:12", 303, price=249000)
    at(318, "09:44", 301, stock=240)
    at(295, "17:26", 308, price=72000, stock=18)
    at(266, "11:03", 302, stock=95)
    at(210, "15:50", 306, price=74000)
    at(188, "08:37", 305, stock=64)
    at(171, "19:15", 309, price=109000, stock=120)
    at(154, "10:41", 303, stock=48)
    at(129, "12:58", 311, stock=42)
    at(118, "16:22", 310, stock=180)
    at(88, "10:18", 308, price=65000)
    at(72, "13:44", 305, stock=96)
    at(66, "09:27", 310, price=17500)
    at(64, "09:09", 312, price=31000)
    at(58, "14:47", 302, price=95000, stock=38)
    at(50, "16:05", 306, stock=88)
    at(47, "11:31", 301, stock=310)
    at(41, "11:31", 313, stock=25)
    at(37, "18:53", 309, stock=76)
    at(28, "14:30", 312, price=32500, stock=48)
    at(24, "10:14", 314, price=26500, stock=110)
    at(22, "09:18", 302, price=92000)
    at(19, "15:39", 303, price=239000, stock=31)
    at(16, "17:41", 313, price=169000, stock=17)
    at(12, "13:05", 307, _DEL)                       # 단종 — 레코드 삭제
    at(11, "15:22", 315, price=199000)
    at(8, "12:09", 314, stock=95)

    # 최근 7일
    at(6, "09:52", 315, stock=48)
    at(5, "17:33", 301, price=22900, on_sale=_ON)
    at(4, "11:26", 302, stock=72)
    at(2, "14:18", 311, price=87000, stock=26)
    at(1, "09:40", 303, stock=19)
    return ev


_EVENTS = {
    "member_aud": _member_events,
    "order_aud": _order_events,
    "product_aud": _product_events,
}


# ── event log -> Envers-shaped audit rows ───────────────────────────────
def _commits(events: list[tuple]) -> list[tuple]:
    """Group events that share a timestamp into one revision (one transaction),
    oldest first.

    Touching the same record twice inside one transaction still leaves a single
    audit row, as Envers writes one row per record per revision — so those
    events are merged rather than duplicated.
    """
    by_ts: dict[int, dict] = {}
    for ts, ident, rtype, values, flags in events:
        entries = by_ts.setdefault(ts, {})
        if ident in entries:
            was_type, was_values, was_flags = entries[ident]
            merged = dict(was_values)
            merged.update(values)
            entries[ident] = (was_type if rtype == _MOD else rtype, merged,
                              tuple(dict.fromkeys(was_flags + tuple(flags))))
        else:
            entries[ident] = (rtype, values, tuple(flags))
    return sorted(
        ((ts, [(ident, *entry) for ident, entry in entries.items()])
         for ts, entries in by_ts.items()),
        key=lambda c: c[0],
    )


def _expand(table: str, commits: list[tuple]) -> list[dict]:
    """Turn (rev, ts, entries) commits into audit rows.

    Envers stores the *whole* record on every revision (not just the changed
    columns) plus a <col>_MOD flag per column, and NULLs out the values on a
    DELETE — so the running per-record state below is what makes the generated
    rows indistinguishable from live ones.
    """
    spec = _SPECS[table]
    ident_col = spec["ident"][0]
    names = [c for c, _t in spec["columns"]]
    rows: list[dict] = []
    state: dict = {}

    for rev, ts, entries in commits:
        for ident, rtype, values, flags in entries:
            prev = state.get(ident, {})
            if rtype == _DEL:
                current = {c: None for c in names}
                mods = {f"{c}_MOD": 0 for c in names}
                state.pop(ident, None)
            else:
                current = dict(prev)
                current.update(values)
                mods = {f"{c}_MOD": int(rtype == _ADD or current.get(c) != prev.get(c))
                        for c in names}
                state[ident] = current
            row = {"REV": rev, "REVTYPE": rtype, "__revts": ts, ident_col: ident}
            row.update(current)
            row.update(mods)
            row.update({f"{o}_MOD": int(o in flags) for o in spec["orphans"]})
            rows.append(row)
    return rows


def _build() -> dict[str, list[dict]]:
    """Number every commit across the three tables in time order — one shared
    REVINFO sequence, as a real schema has — then expand them into audit rows."""
    per_table = {name: _commits(build()) for name, build in _EVENTS.items()}
    stream = sorted(
        ((ts, name, entries) for name, commits in per_table.items() for ts, entries in commits),
        key=lambda c: (c[0], c[1]),
    )
    numbered: dict[str, list] = {name: [] for name in per_table}
    for i, (ts, name, entries) in enumerate(stream):
        numbered[name].append((_REV_BASE + i + 1, ts, entries))
    return {name: _expand(name, commits) for name, commits in numbered.items()}


_ROWS = _build()


def _resolve(table: str | None) -> str:
    """Demo mode accepts any typed-in table name — anything unknown falls back
    to the default sample so the flow never dead-ends."""
    return table if table in _SPECS else DEFAULT_TABLE


# ── public API (services.py talks to this) ──────────────────────────────
def tables() -> list[str]:
    """The sample `_aud` table names, as list_tables() would return them."""
    return sorted(_SPECS)


def preview(table: str | None = None) -> dict:
    """Classification payload for screen 2 — mirrors introspect.describe_table()."""
    return _describe(_resolve(table))


def example_id(table: str | None = None) -> str:
    """A sample identifier value to show as the 식별자 검색 placeholder."""
    return _SPECS[_resolve(table)]["example"]


def rows(table: str | None = None, id_value=None) -> list[dict]:
    """One record's audit rows, REV ascending — the 식별자 검색 path.

    An id that is not in the sample data returns nothing, which is how the
    demo reaches the "이력이 없습니다" empty state.
    """
    name = _resolve(table)
    ident = _SPECS[name]["ident"][0]
    wanted = str(id_value).strip()
    return [r for r in _ROWS[name] if str(r[ident]) == wanted]


def _in_range(row: dict, ts_range) -> bool:
    """Half-open [start, end) epoch-millis window, as the live SQL filter uses."""
    if not ts_range:
        return True
    return ts_range[0] <= row["__revts"] < ts_range[1]


def full_history(table: str | None = None, before_rev=None, ts_range=None,
                 limit_revs: int = 200) -> dict:
    """All-records changeset page — the demo twin of services._fetch_all_rows().

    Same shape as the live loader: a window of the newest ``limit_revs``
    revisions, every row inside it, and each record's last state *before* the
    window (the baseline, deliberately unfiltered by period) so the oldest
    shown diff still resolves a correct "before" value.
    """
    name = _resolve(table)
    ident = _SPECS[name]["ident"][0]
    table_rows = _ROWS[name]

    scoped = [r for r in table_rows
              if (before_rev is None or r["REV"] < before_rev) and _in_range(r, ts_range)]
    if not scoped:
        return {"rows": [], "baseline": [], "min_rev": None, "has_more": False}

    window = sorted({r["REV"] for r in scoped}, reverse=True)[:limit_revs]
    lo, hi = min(window), max(window)
    page = sorted((r for r in scoped if lo <= r["REV"] <= hi),
                  key=lambda r: (r[ident], r["REV"]))

    # Rows are REV-ascending, so the last write below each id wins.
    pre: dict = {}
    for r in table_rows:
        if r["REV"] < lo:
            pre[r[ident]] = r

    has_more = any(r["REV"] < lo and _in_range(r, ts_range) for r in table_rows)
    return {"rows": page, "baseline": list(pre.values()), "min_rev": lo, "has_more": has_more}


def full_history_count(table: str | None = None, ts_range=None) -> dict:
    """Pre-load tally for the whole table (mirrors the live COUNT query)."""
    scoped = [r for r in _ROWS[_resolve(table)] if _in_range(r, ts_range)]
    times = sorted(r["__revts"] for r in scoped)
    return {
        "revisions": len({r["REV"] for r in scoped}),
        "rows": len(scoped),
        "first_ts": format_ts(times[0]) if times else None,
        "last_ts": format_ts(times[-1]) if times else None,
    }
