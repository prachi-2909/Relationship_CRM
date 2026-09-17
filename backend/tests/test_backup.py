import sqlite3
import time

from app.services import backup


def _make_db(path) -> str:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    return f"sqlite+pysqlite:///{path}"


def test_create_backup_writes_a_file(tmp_path):
    url = _make_db(tmp_path / "app.db")
    dest = backup.create_backup(database_url=url)
    assert dest is not None
    assert dest.exists()
    assert dest.parent == tmp_path / "backups"


def test_create_backup_skips_missing_database(tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'missing.db'}"
    assert backup.create_backup(database_url=url) is None


def test_create_backup_skips_non_sqlite():
    assert backup.create_backup(database_url="postgresql+psycopg://x/y") is None


def test_create_backup_skips_in_memory():
    assert backup.create_backup(database_url="sqlite+pysqlite:///:memory:") is None


def test_retention_prunes_oldest(tmp_path, monkeypatch):
    url = _make_db(tmp_path / "app.db")
    monkeypatch.setattr(backup.get_settings(), "backup_retention_count", 2)
    paths = []
    for _ in range(3):
        paths.append(backup.create_backup(database_url=url))
        time.sleep(1.1)  # filenames are second-resolution timestamps
    remaining = sorted((tmp_path / "backups").glob("relationship_crm-*.db"))
    assert len(remaining) == 2
    assert remaining == sorted(paths)[1:]


def test_last_backup_at_reflects_latest(tmp_path):
    url = _make_db(tmp_path / "app.db")
    assert backup.last_backup_at(database_url=url) is None
    dest = backup.create_backup(database_url=url)
    seen = backup.last_backup_at(database_url=url)
    assert seen is not None
    assert abs((seen.timestamp()) - dest.stat().st_mtime) < 1
