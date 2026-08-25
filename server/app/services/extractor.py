import logging

from anthropic import APIError
from pydantic import ValidationError

from app.bedrock import MODEL, client
from app.models.receipt import ReceiptExtraction

logger = logging.getLogger(__name__)

_TOOL_NAME = "record_receipt_data"

_RECEIPT_TOOL = {
    "name": _TOOL_NAME,
    "description": (
        "Record the order details and return policy extracted from a receipt email."
    ),
    "input_schema": ReceiptExtraction.model_json_schema(),
}

_SYSTEM_PROMPT = (
    "You extract structured order and return-policy data from raw e-commerce "
    "receipt emails (text or HTML). Use the record_receipt_data tool to report "
    "your findings. Infer return_policy fields from any policy language present "
    "in the email; if the email is silent on a field, use reasonable defaults "
    "and note the assumption in policy_summary."
)


class ReceiptExtractionError(Exception):
    """Raised when the LLM fails to produce a valid, schema-conforming extraction."""


async def extract_receipt_data(email_body: str) -> ReceiptExtraction:
    """Extract structured order + return-policy data from a raw receipt email via Claude."""
    try:
        response = await client().messages.create(
            model=MODEL,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            tools=[_RECEIPT_TOOL],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
            messages=[{"role": "user", "content": email_body}],
        )
    except APIError as exc:
        logger.exception("Bedrock request failed during receipt extraction")
        raise ReceiptExtractionError("LLM request failed") from exc

    tool_use = next(
        (block for block in response.content if block.type == "tool_use"),
        None,
    )
    if tool_use is None or tool_use.name != _TOOL_NAME:
        raise ReceiptExtractionError("Model did not return the expected structured data")

    try:
        return ReceiptExtraction.model_validate(tool_use.input)
    except ValidationError as exc:
        raise ReceiptExtractionError("Extracted data failed schema validation") from exc
