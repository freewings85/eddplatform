"""测试公共夹具：真 MySQL 测试库（eddplatform_test），每测清表。

MySQL 不可达时 skip 依赖它的测试（本项目约定本机必有 MySQL，skip 仅为容错）。
"""
import os

import pytest

os.environ.setdefault("EDD_MYSQL_DB", "eddplatform_test")

from eddplatform.store.db import Db  # noqa: E402


def _mysql_available() -> bool:
    import socket
    try:
        s = socket.create_connection(
            (os.environ.get("EDD_MYSQL_HOST", "127.0.0.1"),
             int(os.environ.get("EDD_MYSQL_PORT", "3306"))), timeout=2)
        s.close()
        return True
    except OSError:
        return False


@pytest.fixture()
def test_db() -> Db:
    if not _mysql_available():
        pytest.skip("MySQL 不可达（127.0.0.1:3306）")
    db = Db(database="eddplatform_test")
    db.truncate_all()
    return db
