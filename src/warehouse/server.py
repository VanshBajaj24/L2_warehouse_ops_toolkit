import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from .confirmation import ConfirmationStore
from .data_store import DataStore, VALID_SITES
from .errors import ToolError
from .models import (
    AdjustStockCountInput,
    BookDockSlotInput,
    CancelDockBookingInput,
    CloseExceptionInput,
    ConfirmOperationInput,
    GetStockInput,
    ListDockSlotsInput,
    ListOpenExceptionsInput,
    MoveStockInput,
    RaiseExceptionInput,
    SearchStockInput,
)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

site_id = os.environ.get("WAREHOUSE_SITE", "")
if site_id not in VALID_SITES:
    raise RuntimeError(
        f"WAREHOUSE_SITE must be one of {VALID_SITES}, got '{site_id}'. "
        "Set the WAREHOUSE_SITE environment variable before starting the server."
    )

store = DataStore(
    site_id=site_id,
    stock_csv_path=str(DATA_DIR / "stock_snapshot.csv"),
    dock_jsonl_path=str(DATA_DIR / "dock_schedule.jsonl"),
)
confirmations = ConfirmationStore()

mcp = MCPServer("Kestrel Warehouse")



@mcp.tool(
    description=(
        "Retrieve a single stock item by its exact SKU code. Returns the item's "
        "description, bin location, quantity, and unit. Use this when the user "
        'provides a full SKU (e.g., "SKU-8801"). If the SKU is unknown, use '
        "search_stock instead."
    )
)
def get_stock(sku: str) -> dict:
    try:
        params = GetStockInput(sku=sku)
    except Exception as e:
        return ToolError(
            "INVALID_SKU_FORMAT",
            f"Invalid SKU format: {sku}",
            "SKU codes follow the pattern SKU-NNNN (e.g., SKU-8801).",
        ).to_dict()
    try:
        return store.get_stock(params.sku)
    except ToolError as e:
        return e.to_dict()


@mcp.tool(
    description=(
        "Search stock items by description keyword. Returns ALL matching items at "
        "this site — do not assume the first result is correct. If multiple items "
        "match, present every candidate to the user and ask which one they mean. "
        "If only one matches, you may proceed with it. Use this when the user "
        "describes a product by name rather than SKU."
    )
)
def search_stock(query: str) -> dict:
    try:
        params = SearchStockInput(query=query)
    except Exception:
        return ToolError(
            "QUERY_TOO_SHORT",
            "Query must be at least 2 characters.",
            "Provide a longer search term (minimum 2 characters).",
        ).to_dict()
    try:
        return store.search_stock(params.query)
    except ToolError as e:
        return e.to_dict()


@mcp.tool(
    description=(
        "List dock slots for a given date at this site. Optionally filter by status. "
        "Use this to check availability before booking, or to show the user the "
        "current schedule. This is read-only — to book or cancel, use "
        "book_dock_slot or cancel_dock_booking."
    )
)
def list_dock_slots(date: str, status: str | None = None) -> dict:
    if status is not None and status not in ("available", "booked"):
        return ToolError(
            "INVALID_STATUS",
            f"Invalid status filter: '{status}'.",
            'Valid values: "available", "booked".',
        ).to_dict()
    try:
        return store.list_dock_slots(date, status)
    except ToolError as e:
        return e.to_dict()


@mcp.tool(
    description=(
        "List all open (unresolved) exception tickets at this site. Use this to "
        "discover exception IDs before closing them with close_exception, or to "
        "show the user what issues are currently outstanding."
    )
)
def list_open_exceptions(sku: str | None = None) -> dict:
    try:
        return store.list_open_exceptions(sku)
    except ToolError as e:
        return e.to_dict()

@mcp.tool(
    description=(
        "Book an available dock slot for a carrier. This tool validates the request "
        "and returns a preview with a confirmation_id. To execute the booking, pass "
        "the confirmation_id to confirm_operation after the user approves. Only "
        "books slots at this site."
    )
)
def book_dock_slot(date: str, slot: str, carrier: str) -> dict:
    try:
        params = BookDockSlotInput(date=date, slot=slot, carrier=carrier)
    except Exception:
        return ToolError(
            "INVALID_SLOT_TIME",
            f"Invalid slot time: '{slot}'.",
            "Valid slot times: 06:00, 08:00, 10:00, 12:00, 14:00, 16:00.",
        ).to_dict()
    try:
        preview = store.preview_book_dock_slot(params.date, params.slot.value, params.carrier)
        return confirmations.create(
            action="book_dock_slot",
            params={"date": params.date, "slot": params.slot.value, "carrier": params.carrier},
            preview=preview,
        )
    except ToolError as e:
        return e.to_dict()


@mcp.tool(
    description=(
        "Cancel an existing dock booking. Returns a preview with a confirmation_id. "
        "Pass the confirmation_id to confirm_operation after the user approves. "
        "Use when a carrier no-shows or a booking needs to be released."
    )
)
def cancel_dock_booking(date: str, slot: str) -> dict:
    try:
        params = CancelDockBookingInput(date=date, slot=slot)
    except Exception:
        return ToolError(
            "INVALID_SLOT_TIME",
            f"Invalid slot time: '{slot}'.",
            "Valid slot times: 06:00, 08:00, 10:00, 12:00, 14:00, 16:00.",
        ).to_dict()
    try:
        preview = store.preview_cancel_dock_booking(params.date, params.slot.value)
        return confirmations.create(
            action="cancel_dock_booking",
            params={"date": params.date, "slot": params.slot.value},
            preview=preview,
        )
    except ToolError as e:
        return e.to_dict()


@mcp.tool(
    description=(
        "Correct the recorded quantity of a stock item. This creates an audit record "
        "that feeds the month-end count and CANNOT be undone — even a reversal "
        "creates a second audit entry, it does not erase the first. Returns a "
        "preview with a confirmation_id. Pass the confirmation_id to "
        "confirm_operation after confirming the new quantity with the user. Do not "
        "use this for bin moves — use move_stock instead."
    )
)
def adjust_stock_count(sku: str, new_quantity: int, reason: str) -> dict:
    try:
        params = AdjustStockCountInput(sku=sku, new_quantity=new_quantity, reason=reason)
    except Exception as e:
        if new_quantity is not None and new_quantity < 0:
            return ToolError(
                "NEGATIVE_QUANTITY",
                "Quantity cannot be negative.",
                "Quantity must be zero or a positive integer.",
            ).to_dict()
        if not reason:
            return ToolError(
                "MISSING_REASON",
                "A reason is required.",
                "A reason is required for the audit trail.",
            ).to_dict()
        return ToolError(
            "INVALID_INPUT",
            str(e),
            "Check the input parameters and try again.",
        ).to_dict()
    try:
        preview = store.preview_adjust_stock_count(params.sku, params.new_quantity, params.reason)
        return confirmations.create(
            action="adjust_stock_count",
            params={"sku": params.sku, "new_quantity": params.new_quantity, "reason": params.reason},
            preview=preview,
            irreversible=True,
        )
    except ToolError as e:
        return e.to_dict()


@mcp.tool(
    description=(
        "Record a bin-to-bin move of stock within this site. This changes the item's "
        "location but does not alter total quantity. Returns a preview with a "
        "confirmation_id. Pass the confirmation_id to confirm_operation after the "
        "user approves. Use adjust_stock_count if the quantity itself is wrong."
    )
)
def move_stock(sku: str, from_bin: str, to_bin: str, quantity: int) -> dict:
    try:
        params = MoveStockInput(sku=sku, from_bin=from_bin, to_bin=to_bin, quantity=quantity)
    except Exception as e:
        return ToolError(
            "INVALID_INPUT",
            str(e),
            "Check the input parameters and try again.",
        ).to_dict()
    try:
        preview = store.preview_move_stock(params.sku, params.from_bin, params.to_bin, params.quantity)
        return confirmations.create(
            action="move_stock",
            params={
                "sku": params.sku,
                "from_bin": params.from_bin,
                "to_bin": params.to_bin,
                "quantity": params.quantity,
            },
            preview=preview,
        )
    except ToolError as e:
        return e.to_dict()


@mcp.tool(
    description=(
        "Open an exception ticket for a stock problem (damaged, missing, etc.). "
        "Returns a preview with a confirmation_id. Pass the confirmation_id to "
        "confirm_operation after the user approves. The execution response includes "
        "an exception ID that can later be passed to close_exception."
    )
)
def raise_exception(sku: str, category: str, description: str) -> dict:
    try:
        params = RaiseExceptionInput(sku=sku, category=category, description=description)
    except Exception:
        return ToolError(
            "INVALID_CATEGORY",
            f"Invalid exception category: '{category}'.",
            "Valid categories: damaged, missing, wrong_item, contaminated, other.",
        ).to_dict()
    try:
        preview = store.preview_raise_exception(params.sku, params.category.value, params.description)
        return confirmations.create(
            action="raise_exception",
            params={"sku": params.sku, "category": params.category.value, "description": params.description},
            preview=preview,
        )
    except ToolError as e:
        return e.to_dict()


@mcp.tool(
    description=(
        "Close an open exception ticket with a resolution note. Returns a preview "
        "with a confirmation_id. Pass the confirmation_id to confirm_operation "
        "after the user approves. Once closed, an exception cannot be reopened — "
        "if the issue recurs, raise a new exception."
    )
)
def close_exception(exception_id: str, resolution: str) -> dict:
    try:
        params = CloseExceptionInput(exception_id=exception_id, resolution=resolution)
    except Exception as e:
        return ToolError(
            "INVALID_INPUT",
            str(e),
            "Check the input parameters and try again.",
        ).to_dict()
    try:
        preview = store.preview_close_exception(params.exception_id, params.resolution)
        return confirmations.create(
            action="close_exception",
            params={"exception_id": params.exception_id, "resolution": params.resolution},
            preview=preview,
        )
    except ToolError as e:
        return e.to_dict()



EXECUTORS = {
    "book_dock_slot": lambda p: store.book_dock_slot(p["date"], p["slot"], p["carrier"]),
    "cancel_dock_booking": lambda p: store.cancel_dock_booking(p["date"], p["slot"]),
    "adjust_stock_count": lambda p: store.adjust_stock_count(p["sku"], p["new_quantity"], p["reason"]),
    "move_stock": lambda p: store.move_stock(p["sku"], p["from_bin"], p["to_bin"], p["quantity"]),
    "raise_exception": lambda p: store.raise_exception(p["sku"], p["category"], p["description"]),
    "close_exception": lambda p: store.close_exception(p["exception_id"], p["resolution"]),
}


@mcp.tool(
    description=(
        "Execute a previously previewed state-changing operation. Every state-changing "
        "tool (book_dock_slot, cancel_dock_booking, adjust_stock_count, move_stock, "
        "raise_exception, close_exception) returns a confirmation_id in its preview. "
        "Pass that ID here after the user has approved the action. Confirmation IDs "
        "expire after 5 minutes."
    )
)
def confirm_operation(confirmation_id: str) -> dict:
    try:
        pending = confirmations.confirm(confirmation_id)
        executor = EXECUTORS.get(pending.action)
        if executor is None:
            return ToolError(
                "INVALID_CONFIRMATION_ID",
                f"Unknown action: {pending.action}",
                "The confirmation ID is invalid. Call the original tool again to get a new preview.",
            ).to_dict()
        return executor(pending.params)
    except ToolError as e:
        return e.to_dict()


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
