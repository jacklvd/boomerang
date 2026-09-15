"""Tests for ``GET /v1/preferences`` and ``PUT /v1/preferences``.

These run against a stand-in repository (see ``serve_repository`` in ``conftest.py``), the
same pattern ``test_routes_me.py`` establishes: the object under test is the route's own
logic — response shaping, normalization, and request validation — not the database chain,
which the ``me`` route tests already cover.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.db.models import PreferenceSetRow, PreferenceValueRow
from app.models import Preference

TIMESTAMP = datetime(2026, 9, 4, 16, 8, 12, tzinfo=UTC)


def _preference_row(
    values: list[Preference], *, account_id: str = "acct_test", updated_at: datetime = TIMESTAMP
) -> PreferenceSetRow:
    row = PreferenceSetRow(account_id=account_id, updated_at=updated_at)
    row.values = [PreferenceValueRow(account_id=account_id, value=value) for value in values]
    return row


class StubRepository:
    """Answers ``get_preference_set``/``replace_preference_set`` from canned state.

    ``replace_calls`` records exactly what the route passed through, so a test can prove
    both that a rejected request never reaches the repository and that an accepted one
    passes on the caller-supplied values untouched (unsorted, undeduplicated beyond what
    the route itself is responsible for).
    """

    def __init__(self, preference_row: PreferenceSetRow | None = None) -> None:
        self._preference_row = preference_row
        self.replace_calls: list[tuple[list[Preference], datetime]] = []

    async def get_preference_set(self) -> PreferenceSetRow | None:
        return self._preference_row

    async def replace_preference_set(
        self, values: list[Preference], updated_at: datetime
    ) -> PreferenceSetRow:
        self.replace_calls.append((list(values), updated_at))
        return _preference_row(list(values), updated_at=updated_at)


# ---------------------------------------------------------------------------
# GET /v1/preferences
# ---------------------------------------------------------------------------


def test_get_returns_an_empty_array_for_a_brand_new_account(api_app, sign_in, serve_repository):
    sign_in("acct_test")
    serve_repository(StubRepository(preference_row=None))

    response = TestClient(api_app).get("/v1/preferences")

    assert response.status_code == 200
    assert response.json() == {
        "account_id": "acct_test",
        "values": [],
        "updated_at": None,
    }


def test_get_returns_the_stored_set_normalized_to_canonical_order(
    api_app, sign_in, serve_repository
):
    sign_in("acct_test")
    # Stored (row) order is deliberately not canonical order, proving the route sorts
    # rather than trusting whatever order the mapper handed back.
    row = _preference_row([Preference.NO_PRINTER, Preference.LOWEST_COST])
    serve_repository(StubRepository(preference_row=row))

    response = TestClient(api_app).get("/v1/preferences")

    assert response.status_code == 200
    assert response.json() == {
        "account_id": "acct_test",
        "values": ["lowest_cost", "no_printer"],
        "updated_at": "2026-09-04T16:08:12Z",
    }


def test_get_uses_the_signed_in_principal_as_account_id(api_app, sign_in, serve_repository):
    sign_in("acct_someone_else")
    serve_repository(StubRepository(preference_row=_preference_row([], account_id="acct_test")))

    response = TestClient(api_app).get("/v1/preferences")

    # The stub's own row carries a different account id in storage; the response must
    # still reflect the authenticated principal, never a value read back from storage.
    assert response.json()["account_id"] == "acct_someone_else"


def test_get_is_unauthenticated_without_a_principal(api_app):
    response = TestClient(api_app).get("/v1/preferences")

    assert response.status_code == 401
    assert response.json()["reason"] == "unauthenticated"


# ---------------------------------------------------------------------------
# PUT /v1/preferences
# ---------------------------------------------------------------------------


def test_put_replaces_the_set_and_normalizes_shuffled_input(api_app, sign_in, serve_repository):
    sign_in("acct_test")
    stub = serve_repository(StubRepository())

    response = TestClient(api_app).put(
        "/v1/preferences",
        json={"values": ["no_printer", "more_sustainable", "lowest_cost"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["account_id"] == "acct_test"
    assert body["values"] == ["lowest_cost", "no_printer", "more_sustainable"]
    assert body["updated_at"] is not None

    # The repository itself receives whatever the caller sent; normalization is this
    # route's job on the way out, not something it asks the repository to do.
    [(received_values, received_updated_at)] = stub.replace_calls
    assert set(received_values) == {
        Preference.NO_PRINTER,
        Preference.MORE_SUSTAINABLE,
        Preference.LOWEST_COST,
    }
    assert received_updated_at.tzinfo is not None


def test_put_accepts_an_empty_array(api_app, sign_in, serve_repository):
    sign_in("acct_test")
    stub = serve_repository(StubRepository())

    response = TestClient(api_app).put("/v1/preferences", json={"values": []})

    assert response.status_code == 200
    assert response.json()["values"] == []
    assert stub.replace_calls[0][0] == []


def test_put_rejects_duplicate_values(api_app, sign_in, serve_repository):
    sign_in("acct_test")
    stub = serve_repository(StubRepository())

    response = TestClient(api_app).put(
        "/v1/preferences",
        json={"values": ["lowest_cost", "lowest_cost"]},
    )

    assert response.status_code == 422
    assert response.json()["reason"] == "validation_failed"
    assert stub.replace_calls == []


def test_put_rejects_an_unknown_value_for_the_whole_request(api_app, sign_in, serve_repository):
    sign_in("acct_test")
    stub = serve_repository(StubRepository())

    response = TestClient(api_app).put(
        "/v1/preferences",
        json={"values": ["lowest_cost", "not_a_real_preference"]},
    )

    assert response.status_code == 422
    assert response.json()["reason"] == "validation_failed"
    assert stub.replace_calls == []


def test_put_rejects_an_unknown_request_field(api_app, sign_in, serve_repository):
    sign_in("acct_test")
    stub = serve_repository(StubRepository())

    response = TestClient(api_app).put(
        "/v1/preferences",
        json={"values": ["lowest_cost"], "priority": "lowest_cost"},
    )

    assert response.status_code == 422
    assert response.json()["reason"] == "validation_failed"
    assert stub.replace_calls == []


def test_put_uses_the_signed_in_principal_as_account_id(api_app, sign_in, serve_repository):
    sign_in("acct_someone_else")
    serve_repository(StubRepository())

    response = TestClient(api_app).put("/v1/preferences", json={"values": []})

    assert response.json()["account_id"] == "acct_someone_else"


def test_put_is_unauthenticated_without_a_principal(api_app):
    response = TestClient(api_app).put("/v1/preferences", json={"values": []})

    assert response.status_code == 401
    assert response.json()["reason"] == "unauthenticated"
