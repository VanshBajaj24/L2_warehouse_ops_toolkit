from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SlotTimeEnum(str, Enum):
    T0600 = "06:00"
    T0800 = "08:00"
    T1000 = "10:00"
    T1200 = "12:00"
    T1400 = "14:00"
    T1600 = "16:00"


class DockStatusEnum(str, Enum):
    AVAILABLE = "available"
    BOOKED = "booked"


class ExceptionCategoryEnum(str, Enum):
    DAMAGED = "damaged"
    MISSING = "missing"
    WRONG_ITEM = "wrong_item"
    CONTAMINATED = "contaminated"
    OTHER = "other"


class GetStockInput(BaseModel):
    sku: str = Field(
        ...,
        pattern=r"^SKU-\d{4}$",
        description='Exact SKU code (e.g., "SKU-8801").',
    )


class SearchStockInput(BaseModel):
    query: str = Field(
        ...,
        min_length=2,
        description="Keyword to match against descriptions (case-insensitive, substring). Minimum 2 characters.",
    )


class ListDockSlotsInput(BaseModel):
    date: str = Field(..., description="Date to check, format YYYY-MM-DD.")
    status: Optional[DockStatusEnum] = Field(
        None, description="Filter by slot status. Omit to return all slots."
    )


class ListOpenExceptionsInput(BaseModel):
    sku: Optional[str] = Field(
        None,
        description="Filter exceptions by SKU. Omit to list all open exceptions at this site.",
    )


class BookDockSlotInput(BaseModel):
    date: str = Field(..., description="Date of the slot, format YYYY-MM-DD.")
    slot: SlotTimeEnum = Field(..., description="Time slot to book.")
    carrier: str = Field(
        ..., min_length=1, description="Name of the carrier."
    )


class CancelDockBookingInput(BaseModel):
    date: str = Field(..., description="Date of the booking, format YYYY-MM-DD.")
    slot: SlotTimeEnum = Field(..., description="Time slot to cancel.")


class AdjustStockCountInput(BaseModel):
    sku: str = Field(..., description="The SKU to adjust.")
    new_quantity: int = Field(
        ..., ge=0, description="The corrected quantity (>= 0)."
    )
    reason: str = Field(
        ...,
        min_length=1,
        description="Why the count is being corrected (written to audit trail).",
    )


class MoveStockInput(BaseModel):
    sku: str = Field(..., description="The SKU to move.")
    from_bin: str = Field(
        ..., description="Current bin (must match the item's recorded location)."
    )
    to_bin: str = Field(..., description="Destination bin.")
    quantity: int = Field(..., gt=0, description="Number of units to move (> 0).")


class RaiseExceptionInput(BaseModel):
    sku: str = Field(..., description="The SKU the exception relates to.")
    category: ExceptionCategoryEnum = Field(
        ..., description="Type of exception."
    )
    description: str = Field(
        ..., min_length=1, description="Brief description of the problem."
    )


class CloseExceptionInput(BaseModel):
    exception_id: str = Field(
        ..., description='The exception ID to close (e.g., "EXC-20260408-001").'
    )
    resolution: str = Field(
        ..., min_length=1, description="What was done to resolve the issue."
    )


class ConfirmOperationInput(BaseModel):
    confirmation_id: str = Field(
        ...,
        description="The confirmation ID from a state-changing tool's preview response.",
    )
