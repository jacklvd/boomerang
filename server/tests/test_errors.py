"""Tests for the v1 error envelope in ``app.api.errors``.

Covers the closed ``reason``-to-status mapping, the wire shape of the envelope, how
FastAPI/Starlette-raised errors get normalized into it, and the contract's sharpest
requirement: cross-account access must be indistinguishable from not-found.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api import errors as errors_module
from app.api.errors import (
    ApiError,
    ErrorReason,
    install_error_handling,
    not_found_error,
    unauthenticated_error,
)


def _build_app() -> FastAPI:
    app = FastAPI()
    install_error_handling(app)

    @app.get("/boom-not-found")
    async def boom_not_found() -> None:
        raise not_found_error()

    @app.get("/boom-unauthenticated")
    async def boom_unauthenticated() -> None:
        raise unauthenticated_error(details={"cause": "example"})

    @app.get("/boom-unexpected")
    async def boom_unexpected() -> None:
        msg = "kaboom"
        raise ValueError(msg)

    class Item(BaseModel):
        model_config = {"extra": "forbid"}

        values: list[str]

    @app.post("/items")
    async def create_item(item: Item) -> Item:
        return item

    @app.post("/lists")
    async def create_list(values: list[str]) -> list[str]:
        return values

    return app


def test_api_error_produces_the_contract_shape():
    response = TestClient(_build_app()).get("/boom-not-found")

    assert response.status_code == 404
    body = response.json()
    assert body["reason"] == "not_found"
    assert isinstance(body["message"], str)
    assert body["message"]
    assert body["details"] is None
    assert isinstance(body["request_id"], str)
    assert body["request_id"]
    assert response.headers["x-request-id"] == body["request_id"]


def test_unauthenticated_carries_a_details_discriminator_without_a_new_reason():
    response = TestClient(_build_app()).get("/boom-unauthenticated")

    body = response.json()
    assert response.status_code == 401
    assert body["reason"] == "unauthenticated"
    assert body["details"] == {"cause": "example"}


def test_malformed_json_is_invalid_request_not_validation_failed():
    response = TestClient(_build_app()).post(
        "/items", content=b"{not-json", headers={"content-type": "application/json"}
    )

    assert response.status_code == 400
    assert response.json()["reason"] == "invalid_request"


def test_unknown_field_is_validation_failed_with_field_paths():
    response = TestClient(_build_app()).post("/items", json={"values": ["a"], "extra": "nope"})

    assert response.status_code == 422
    body = response.json()
    assert body["reason"] == "validation_failed"
    paths = {field["path"] for field in body["details"]["fields"]}
    assert "extra" in paths


def test_nested_list_item_error_appends_an_index_to_the_existing_path():
    response = TestClient(_build_app()).post("/items", json={"values": [123]})

    assert response.status_code == 422
    body = response.json()
    assert body["details"]["fields"][0]["path"] == "values[0]"


def test_index_at_the_start_of_the_path_renders_without_a_leading_field_name():
    response = TestClient(_build_app()).post("/lists", json=[123])

    assert response.status_code == 422
    body = response.json()
    assert body["details"]["fields"][0]["path"] == "[0]"


def test_missing_field_reports_the_field_path_without_the_body_prefix():
    response = TestClient(_build_app()).post("/items", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["details"]["fields"][0]["path"] == "values"


def test_unmatched_route_still_returns_the_envelope_shape():
    response = TestClient(_build_app()).get("/does-not-exist")

    assert response.status_code == 404
    assert response.json()["reason"] == "not_found"


def test_method_not_allowed_falls_back_to_a_sensible_reason():
    response = TestClient(_build_app()).put("/boom-not-found")

    assert response.status_code == 405
    assert response.json()["reason"] == "invalid_request"


def test_unexpected_exception_never_leaks_a_stack_trace():
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.get("/boom-unexpected")

    assert response.status_code == 500
    body = response.json()
    assert body["reason"] == "internal_error"
    assert "kaboom" not in response.text
    assert "Traceback" not in response.text


def test_request_id_header_present_on_success_responses():
    app = FastAPI()
    install_error_handling(app)

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    response = TestClient(app).get("/ok")

    assert response.status_code == 200
    assert response.headers["x-request-id"].startswith("req_")


def test_every_reason_maps_to_the_contract_tables_status():
    expected = {
        ErrorReason.INVALID_REQUEST: 400,
        ErrorReason.UNAUTHENTICATED: 401,
        ErrorReason.NOT_FOUND: 404,
        ErrorReason.STATE_TRANSITION_NOT_ALLOWED: 409,
        ErrorReason.STATE_BLOCKED: 409,
        ErrorReason.VALIDATION_FAILED: 422,
        ErrorReason.RATE_LIMITED: 429,
        ErrorReason.INTERNAL_ERROR: 500,
        ErrorReason.TEMPORARILY_UNAVAILABLE: 503,
    }

    for reason, status_code in expected.items():
        assert ApiError(reason, "message").status_code == status_code


def test_cross_account_item_and_missing_item_are_byte_identical(monkeypatch):
    """The contract requires cross-account access to be indistinguishable from not-found.

    A caller scoped to ``acct_owner`` asks for an item that belongs to a different
    account, and separately for an item id that never existed at all. Both requests
    reach the identical ``not_found_error()`` call site — there is only one branch, not
    a branch per cause — so the two responses must be byte-identical.
    """
    app = FastAPI()
    install_error_handling(app)

    items_by_account = {"acct_owner": {"item_mine"}, "acct_other": {"item_not_mine"}}

    @app.get("/items/{item_id}")
    async def get_item(item_id: str) -> dict[str, str]:
        account_id = "acct_owner"  # the resolved AccountScope, held fixed for this test
        if item_id not in items_by_account[account_id]:
            raise not_found_error()
        return {"item_id": item_id}

    # Freeze the request-id generator so the one field the contract allows to vary
    # per-request is pinned too — what's left, compared byte-for-byte, is everything
    # the contract actually requires to be identical.
    monkeypatch.setattr(errors_module, "_new_request_id", lambda: "req_fixed_for_test")

    client = TestClient(app)
    cross_account_response = client.get("/items/item_not_mine")
    never_existed_response = client.get("/items/item_never_existed")

    assert cross_account_response.status_code == never_existed_response.status_code == 404
    assert (
        cross_account_response.headers["content-type"]
        == never_existed_response.headers["content-type"]
    )
    assert cross_account_response.content == never_existed_response.content
