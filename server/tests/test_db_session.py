import pytest

from app.db import build_async_engine, build_session_factory


def test_async_engine_and_session_factory_are_explicit():
    engine = build_async_engine("postgresql+psycopg://user:pass@localhost/database")
    factory = build_session_factory(engine)

    assert engine.url.drivername == "postgresql+psycopg"
    assert factory.kw["expire_on_commit"] is False


def test_async_engine_rejects_non_postgresql_driver():
    with pytest.raises(ValueError, match=r"postgresql\+psycopg"):
        build_async_engine("sqlite+aiosqlite:///:memory:")
