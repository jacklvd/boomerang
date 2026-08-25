from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

SAMPLE_EMAIL = """
Your Amazon.com order #112-1234567-1234567 has shipped.
Order date: January 5, 2026

1x Wireless Mouse - $24.99

Returns: Items can be returned within 30 days of delivery in original
packaging. No restocking fee applies.
"""

VALID_TOOL_INPUT = {
    "retailer_name": "Amazon",
    "order_date": "2026-01-05T00:00:00",
    "order_number": "112-1234567-1234567",
    "items": [{"name": "Wireless Mouse", "price": 24.99, "quantity": 1}],
    "return_policy": {
        "window_days": 30,
        "is_final_sale": False,
        "requires_original_packaging": True,
        "return_fee": None,
        "policy_summary": "30-day returns in original packaging, no fee.",
    },
}


def _mock_response(tool_input: dict | None, tool_name: str = "record_receipt_data"):
    block = SimpleNamespace(type="tool_use", name=tool_name, input=tool_input)
    return SimpleNamespace(content=[block] if tool_input is not None else [])


@pytest.fixture
def test_client():
    return TestClient(app)


def test_parse_receipt_success(test_client):
    mock_create = AsyncMock(return_value=_mock_response(VALID_TOOL_INPUT))
    with patch("app.services.extractor.client") as mock_client:
        mock_client.return_value.messages.create = mock_create
        response = test_client.post(
            "/api/v1/receipts/parse", json={"raw_email_text": SAMPLE_EMAIL}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["retailer_name"] == "Amazon"
    assert body["items"][0]["name"] == "Wireless Mouse"
    assert body["return_policy"]["window_days"] == 30

    _, kwargs = mock_create.call_args
    assert kwargs["tool_choice"] == {"type": "tool", "name": "record_receipt_data"}
    assert kwargs["tools"][0]["name"] == "record_receipt_data"


def test_parse_receipt_no_tool_use_returns_422(test_client):
    mock_create = AsyncMock(return_value=_mock_response(None))
    with patch("app.services.extractor.client") as mock_client:
        mock_client.return_value.messages.create = mock_create
        response = test_client.post(
            "/api/v1/receipts/parse", json={"raw_email_text": SAMPLE_EMAIL}
        )

    assert response.status_code == 422


def test_parse_receipt_invalid_schema_returns_422(test_client):
    bad_input = {**VALID_TOOL_INPUT, "items": "not-a-list"}
    mock_create = AsyncMock(return_value=_mock_response(bad_input))
    with patch("app.services.extractor.client") as mock_client:
        mock_client.return_value.messages.create = mock_create
        response = test_client.post(
            "/api/v1/receipts/parse", json={"raw_email_text": SAMPLE_EMAIL}
        )

    assert response.status_code == 422


def test_parse_receipt_missing_payload_field_returns_422(test_client):
    response = test_client.post("/api/v1/receipts/parse", json={})
    assert response.status_code == 422
