"""Db：建库建表 + 连接可用。打真 MySQL（eddplatform_test 库）。"""
from eddplatform.store.db import Db


def test_db_creates_database_and_tables(test_db: Db):
    conn = test_db.connect()
    try:
        with conn.cursor() as c:
            c.execute("SHOW TABLES")
            tables = {list(r.values())[0] for r in c.fetchall()}
    finally:
        conn.close()
    assert {"cases", "tags", "systems", "eval_programs", "tasks", "runs", "case_results"} <= tables


def test_truncate_all_clears_rows(test_db: Db):
    conn = test_db.connect()
    try:
        with conn.cursor() as c:
            c.execute("INSERT INTO systems(system_id, data) VALUES(%s, %s)", ("s1", "{}"))
        conn.commit()
    finally:
        conn.close()
    test_db.truncate_all()
    conn = test_db.connect()
    try:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) AS n FROM systems")
            assert c.fetchone()["n"] == 0
    finally:
        conn.close()
