from datetime import datetime

from pydantic import BaseModel


class ExtractedItem(BaseModel):
    name: str
    price: float
    quantity: int


class ReturnPolicy(BaseModel):
    window_days: int = 30
    is_final_sale: bool
    requires_original_packaging: bool
    return_fee: float | None = None
    policy_summary: str


class ReceiptExtraction(BaseModel):
    retailer_name: str
    order_date: datetime
    order_number: str
    items: list[ExtractedItem]
    return_policy: ReturnPolicy


class ReceiptPayload(BaseModel):
    raw_email_text: str
