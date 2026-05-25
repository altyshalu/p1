from pathlib import Path


def test_async_alembic_files_exist_and_do_not_use_metadata_create_all() -> None:
    env_py = Path("alembic/env.py")
    versions = list(Path("alembic/versions").glob("*.py")) if Path("alembic/versions").exists() else []
    session_py = Path("src/l2l3_protocol/db/session.py").read_text(encoding="utf-8")

    assert env_py.exists()
    env_source = env_py.read_text(encoding="utf-8")
    assert "async_engine_from_config" in env_source
    assert "run_async_migrations" in env_source
    assert versions
    assert "Base.metadata.create_all" not in session_py
