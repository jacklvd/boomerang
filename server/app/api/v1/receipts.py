from fastapi import APIRouter, HTTPException

from app.models.receipt import ReceiptExtraction, ReceiptPayload
from app.services.extractor import ReceiptExtractionError, extract_receipt_data

router = APIRouter(prefix="/api/v1/receipts", tags=["receipts"])


@router.post("/parse", response_model=ReceiptExtraction)
async def parse_receipt(payload: ReceiptPayload) -> ReceiptExtraction:
    try:
        return await extract_receipt_data(payload.raw_email_text)
    except ReceiptExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
