# Boomerang server

The FastAPI service owns normalized account data in PostgreSQL while retailer sessions and detailed
workflow state remain in the browser extension. `app.models` contains strict Pydantic domain
records; `app.db` contains the SQLAlchemy mappings, relational constraints, and async session
factories. Future routes and services should exchange domain records rather than returning ORM rows
directly.

## Development

Install the Python 3.13 environment with `make install`. Run the current unit and quality suite with
`make check`. Those Docker-free commands exclude the PostgreSQL integration marker.

## Disposable PostgreSQL database

Docker is required for the local database harness. From the repository root, run this complete
sequence to start the pinned PostgreSQL 17.11 container, execute the two integration tests, and
remove the container and its ephemeral data:

```bash
make -C server test-db-up

TEST_DATABASE_URL=postgresql+psycopg://boomerang_test:boomerang_test@127.0.0.1:55432/boomerang_test \
  make -C server integration

make -C server test-db-down
```

The default test URL is:

```text
postgresql+psycopg://boomerang_test:boomerang_test@127.0.0.1:55432/boomerang_test
```

`POSTGRES_TEST_PORT` and `COMPOSE_PROJECT_NAME` may be overridden for concurrent worktrees.

The integration module contains only a schema-lifecycle test and a complete account-graph
persistence round trip. Each test creates tables with `Base.metadata.create_all()`; the lifecycle
test explicitly verifies `drop_all()`, while fixture cleanup defensively drops the schema after
either test.

This harness is not a production database design. It has fixed test-only credentials, binds only to
loopback, and stores PostgreSQL data in `tmpfs`.
