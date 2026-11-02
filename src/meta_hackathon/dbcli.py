"""`krishi-db`: set up and fill the Postgres database (DB_URI). Runs as the
login role, which owns the tables and bypasses row-level security.

    uv run krishi-db migrate              # app schema, RLS policies, officer roster, LangGraph tables (idempotent)
    uv run krishi-db load-agri [PATH]     # reference data from agri.db into the `agri` schema
    uv run krishi-db import-sqlite [PATH] # cases and photo records from the old .data/krishi.sqlite3

load-agri replaces the whole `agri` schema in one transaction: readers see the
old data or the new, never a half-loaded mix.
"""

import argparse
import csv
import json
import sqlite3
import sys
import time
from pathlib import Path

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore

from meta_hackathon.config import settings

PACKAGE = Path(__file__).parent
SCHEMA_SQL = PACKAGE / "sql" / "schema.sql"
OFFICERS_CSV = PACKAGE / "assets" / "officers.csv"
AGRI_DB = PACKAGE / "assets" / "agri.db"

# agri.db (built by the pesticide-rag project): the DAE pesticide register and
# the Krishoker Janala advice, linked. The FTS5 tables are SQLite-only and
# are not copied, except kj_fts's content, as agri.kj_search.
AGRI_TABLES = [
    "ingredients",
    "products",
    "recommendations",
    "aliases",
    "actives",
    "ingredient_actives",
    "kj_crops",
    "kj_problems",
    "kj_sections",
    "kj_mentions",
    "kj_links",
]
_TYPES = {"INTEGER": "bigint", "REAL": "double precision"}

AGRI_POST = """
CREATE TABLE agri.kj_search (problem_id bigint PRIMARY KEY, name_bn text, crop_bn text, crop_en text, slug text, body text);

CREATE INDEX ON agri.products (reg_no);
CREATE INDEX ON agri.products (ingredient_id);
CREATE INDEX ON agri.recommendations (product_id);
CREATE INDEX ON agri.recommendations (lower(crop));
CREATE INDEX ON agri.recommendations (lower(pest));
CREATE INDEX ON agri.kj_problems (crop_id);
CREATE INDEX ON agri.kj_sections (problem_id);
CREATE INDEX ON agri.kj_links (problem_id);
CREATE INDEX ON agri.kj_links (product_id);
CREATE INDEX ON agri.kj_mentions (problem_id);

CREATE VIEW agri.v_flat AS
  SELECT r.id AS rec_id, i.category, i.name AS active_ingredient, p.id AS product_id, p.brand,
         p.formulation, p.reg_no, p.holder, r.crop, r.pest, r.dosage, r.page
  FROM agri.recommendations r
  JOIN agri.products p ON p.id = r.product_id
  JOIN agri.ingredients i ON i.id = p.ingredient_id;

CREATE VIEW agri.v_kj_problem AS
  SELECT p.id, p.crop_id, c.name_bn AS crop_bn, c.name_en AS crop_en, p.name_bn, p.problem_type, p.pest_keyword,
         (SELECT string_agg(text_bn, E'\\n' ORDER BY ord) FROM agri.kj_sections s WHERE s.problem_id = p.id AND s.kind = 'symptoms') AS symptoms_bn,
         (SELECT string_agg(text_bn, E'\\n' ORDER BY ord) FROM agri.kj_sections s WHERE s.problem_id = p.id AND s.kind = 'management') AS management_bn,
         (SELECT string_agg(text_bn, E'\\n' ORDER BY ord) FROM agri.kj_sections s WHERE s.problem_id = p.id AND s.kind = 'do') AS do_bn,
         (SELECT string_agg(text_bn, E'\\n' ORDER BY ord) FROM agri.kj_sections s WHERE s.problem_id = p.id AND s.kind = 'dont') AS dont_bn,
         p.images, p.source_url
  FROM agri.kj_problems p JOIN agri.kj_crops c USING (crop_id);

CREATE VIEW agri.v_kj_links AS
  SELECT l.problem_id, l.method, l.confidence, l.crop_level, l.evidence, v.product_id, v.brand, v.reg_no, v.holder,
         v.active_ingredient, v.category, v.crop AS reg_crop, v.pest AS reg_pest, v.dosage AS reg_dosage, v.page
  FROM agri.kj_links l
  JOIN agri.v_flat v ON v.product_id = l.product_id AND (l.rec_id IS NULL OR v.rec_id = l.rec_id);

GRANT USAGE ON SCHEMA agri TO krishi_app;
GRANT SELECT ON ALL TABLES IN SCHEMA agri TO krishi_app;
"""


def _connect() -> psycopg.Connection:
    return psycopg.connect(settings.DB_URI, autocommit=True, connect_timeout=15)


def migrate() -> None:
    with _connect() as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        with OFFICERS_CSV.open(encoding="utf-8") as f:
            officers = list(csv.DictReader(f))
        cols = list(officers[0])
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "id")
        with conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO officers ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
                f"ON CONFLICT (id) DO UPDATE SET {updates}",
                [[o[c] for c in cols] for o in officers],
            )
    # The conversation checkpoints and memories (persistence.py).
    with PostgresSaver.from_conn_string(settings.DB_URI) as saver:
        saver.setup()
    with PostgresStore.from_conn_string(settings.DB_URI) as memory:
        memory.setup()
    print(f"Schema applied; {len(officers)} officers in the roster.")


def _sqlite(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        sys.exit(f"No such file: {path}")
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _copy(conn: psycopg.Connection, table: str, columns: list[str], rows) -> int:
    n = 0
    with conn.cursor() as cur, cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)
            n += 1
    return n


def load_agri(path: Path) -> None:
    src = _sqlite(path)
    started = time.monotonic()
    with _connect() as conn, conn.transaction():
        conn.execute("DROP SCHEMA IF EXISTS agri CASCADE")
        conn.execute("CREATE SCHEMA agri")
        for table in AGRI_TABLES:
            info = src.execute(f"PRAGMA table_info({table})").fetchall()  # cid, name, type, notnull, default, pk
            columns = [c[1] for c in info]
            defs = [
                f"{name} {_TYPES.get((ctype or '').upper(), 'text')}" + (" PRIMARY KEY" if pk == 1 else "")
                for _, name, ctype, _, _, pk in info
            ]
            conn.execute(f"CREATE TABLE agri.{table} ({', '.join(defs)})")
            n = _copy(conn, f"agri.{table}", columns, src.execute(f"SELECT {', '.join(columns)} FROM {table}"))
            print(f"  agri.{table}: {n} rows")
        conn.execute(AGRI_POST)
        n = _copy(
            conn,
            "agri.kj_search",
            ["name_bn", "crop_bn", "crop_en", "slug", "body", "problem_id"],
            src.execute("SELECT c0, c1, c2, c3, c4, c5 FROM kj_fts_content"),
        )
        print(f"  agri.kj_search: {n} rows")
    print(f"Loaded {path.name} into schema agri in {time.monotonic() - started:.0f} s.")


def import_sqlite(path: Path) -> None:
    src = _sqlite(path)
    tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    cases = src.execute("SELECT id, phone, data, updated_at FROM crop_cases").fetchall() if "crop_cases" in tables else []
    images = (
        src.execute("SELECT name, phone, thread_id, labels, created_at FROM images").fetchall() if "images" in tables else []
    )
    with _connect() as conn, conn.transaction(), conn.cursor() as cur:
        phones = {r[1] for r in cases} | {r[1] for r in images}
        cur.executemany("INSERT INTO farmers (phone) VALUES (%s) ON CONFLICT DO NOTHING", [(p,) for p in phones])
        cur.executemany(
            "INSERT INTO crop_cases (id, phone, data, updated_at) VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
            [(i, p, json.dumps(json.loads(d), ensure_ascii=False), u) for i, p, d, u in cases],
        )
        cur.executemany(
            "INSERT INTO images (name, phone, thread_id, labels, created_at) VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (name) DO NOTHING",
            images,
        )
    print(f"Imported {len(cases)} cases and {len(images)} photo records for {len(phones)} farmers.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="krishi-db", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="apply the app schema and seed the officer roster")
    p = sub.add_parser("load-agri", help="load agri.db into the agri schema")
    p.add_argument("path", nargs="?", type=Path, default=AGRI_DB)
    p = sub.add_parser("import-sqlite", help="import cases and photo records from the old SQLite file")
    p.add_argument("path", nargs="?", type=Path, default=Path(settings.DATA_DIR) / "krishi.sqlite3")
    args = parser.parse_args()
    if args.command == "migrate":
        migrate()
    elif args.command == "load-agri":
        load_agri(args.path)
    else:
        import_sqlite(args.path)


if __name__ == "__main__":
    main()
