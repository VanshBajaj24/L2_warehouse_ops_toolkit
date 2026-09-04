import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .errors import ToolError

VALID_SITES = {"LEEDS-01", "READING-02", "GLASGOW-03"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DataStore:
    def __init__(self, site_id: str, stock_csv_path: str, dock_jsonl_path: str):
        if site_id not in VALID_SITES:
            raise ValueError(f"Invalid site_id: {site_id}. Must be one of {VALID_SITES}")
        self.site_id = site_id
        self._stock: list[dict] = []
        self._dock_slots: list[dict] = []
        self._exceptions: list[dict] = []
        self._audit_log: list[dict] = []
        self._exception_seq = 0

        self._load_stock(stock_csv_path)
        self._load_dock(dock_jsonl_path)

    def _load_stock(self, path: str) -> None:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["site"] == self.site_id:
                    row["quantity"] = int(row["quantity"])
                    self._stock.append(row)

    def _load_dock(self, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line)
                if entry["site"] == self.site_id:
                    self._dock_slots.append(entry)


    def get_stock(self, sku: str) -> dict:
        for item in self._stock:
            if item["sku"] == sku:
                return {
                    "sku": item["sku"],
                    "description": item["description"],
                    "bin": item["bin"],
                    "quantity": item["quantity"],
                    "unit": item["unit"],
                }
        raise ToolError(
            "SKU_NOT_FOUND",
            f"No stock item with SKU '{sku}' at this site.",
            "Use search_stock with a description keyword to find the correct SKU.",
        )

    def search_stock(self, query: str) -> dict:
        query_lower = query.lower()
        matches = []
        for item in self._stock:
            if query_lower in item["description"].lower():
                matches.append({
                    "sku": item["sku"],
                    "description": item["description"],
                    "bin": item["bin"],
                    "quantity": item["quantity"],
                    "unit": item["unit"],
                })
        if not matches:
            raise ToolError(
                "NO_MATCHES",
                f"No items matching '{query}' at this site.",
                "Try a broader keyword, or use get_stock if you have the exact SKU.",
            )
        return {"matches": matches, "total": len(matches)}

    def list_dock_slots(self, date: str, status: str | None = None) -> dict:
        if not DATE_RE.match(date):
            raise ToolError(
                "INVALID_DATE_FORMAT",
                f"Date '{date}' is not in YYYY-MM-DD format.",
                "Reformat the date as YYYY-MM-DD (e.g., 2026-04-08).",
            )
        slots = []
        for s in self._dock_slots:
            if s["date"] == date:
                if status is None or s["status"] == status:
                    slots.append({
                        "slot": s["slot"],
                        "status": s["status"],
                        "carrier": s["carrier"],
                    })
        return {"site": self.site_id, "date": date, "slots": slots}

    def list_open_exceptions(self, sku: str | None = None) -> dict:
        if sku is not None:
            found = any(item["sku"] == sku for item in self._stock)
            if not found:
                raise ToolError(
                    "SKU_NOT_FOUND",
                    f"No stock item with SKU '{sku}' at this site.",
                    "Use search_stock to find the correct SKU.",
                )
        results = []
        for exc in self._exceptions:
            if exc["status"] != "open":
                continue
            if sku is not None and exc["sku"] != sku:
                continue
            results.append({
                "exception_id": exc["exception_id"],
                "sku": exc["sku"],
                "category": exc["category"],
                "description": exc["description"],
                "raised_at": exc["raised_at"],
            })
        return {
            "site": self.site_id,
            "open_exceptions": results,
            "total": len(results),
        }


    def book_dock_slot(self, date: str, slot: str, carrier: str) -> dict:
        if not DATE_RE.match(date):
            raise ToolError(
                "INVALID_DATE_FORMAT",
                f"Date '{date}' is not in YYYY-MM-DD format.",
                "Reformat the date as YYYY-MM-DD (e.g., 2026-04-08).",
            )
        for s in self._dock_slots:
            if s["date"] == date and s["slot"] == slot:
                if s["status"] == "booked":
                    raise ToolError(
                        "SLOT_ALREADY_BOOKED",
                        f"Slot {slot} on {date} is already booked by '{s['carrier']}'.",
                        "Use list_dock_slots to find an available slot.",
                    )
                s["status"] = "booked"
                s["carrier"] = carrier
                return {
                    "action": "book_dock_slot",
                    "executed": True,
                    "date": date,
                    "slot": slot,
                    "carrier": carrier,
                    "message": "Dock slot booked successfully.",
                }
        
        new_slot = {
            "site": self.site_id,
            "date": date,
            "slot": slot,
            "status": "booked",
            "carrier": carrier,
        }
        self._dock_slots.append(new_slot)
        return {
            "action": "book_dock_slot",
            "executed": True,
            "date": date,
            "slot": slot,
            "carrier": carrier,
            "message": "Dock slot booked successfully.",
        }

    def cancel_dock_booking(self, date: str, slot: str) -> dict:
        if not DATE_RE.match(date):
            raise ToolError(
                "INVALID_DATE_FORMAT",
                f"Date '{date}' is not in YYYY-MM-DD format.",
                "Reformat the date as YYYY-MM-DD (e.g., 2026-04-08).",
            )
        for s in self._dock_slots:
            if s["date"] == date and s["slot"] == slot:
                if s["status"] != "booked":
                    raise ToolError(
                        "SLOT_NOT_BOOKED",
                        f"Slot {slot} on {date} is not currently booked.",
                        "Use list_dock_slots to see current bookings.",
                    )
                previous_carrier = s["carrier"]
                s["status"] = "available"
                s["carrier"] = None
                return {
                    "action": "cancel_dock_booking",
                    "executed": True,
                    "date": date,
                    "slot": slot,
                    "previous_carrier": previous_carrier,
                    "message": "Booking cancelled. Slot is now available.",
                }
        raise ToolError(
            "SLOT_NOT_BOOKED",
            f"No slot {slot} on {date} found in the schedule.",
            "Use list_dock_slots to see current bookings.",
        )

    def adjust_stock_count(self, sku: str, new_quantity: int, reason: str) -> dict:
        for item in self._stock:
            if item["sku"] == sku:
                previous_quantity = item["quantity"]
                item["quantity"] = new_quantity
                audit_entry = {
                    "action": "adjust_stock_count",
                    "sku": sku,
                    "previous_quantity": previous_quantity,
                    "new_quantity": new_quantity,
                    "reason": reason,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                self._audit_log.append(audit_entry)
                return {
                    "action": "adjust_stock_count",
                    "executed": True,
                    "sku": sku,
                    "previous_quantity": previous_quantity,
                    "new_quantity": new_quantity,
                    "unit": item["unit"],
                    "reason": reason,
                    "message": "Stock count adjusted. This adjustment will appear in the month-end count.",
                }
        raise ToolError(
            "SKU_NOT_FOUND",
            f"No stock item with SKU '{sku}' at this site.",
            "Use search_stock to find the correct SKU at this site.",
        )

    def move_stock(self, sku: str, from_bin: str, to_bin: str, quantity: int) -> dict:
        if from_bin == to_bin:
            raise ToolError(
                "SAME_BIN",
                "Source and destination bins are the same.",
                "Provide a different destination bin.",
            )
        for item in self._stock:
            if item["sku"] == sku:
                if item["bin"] != from_bin:
                    raise ToolError(
                        "BIN_MISMATCH",
                        f"SKU '{sku}' is in bin '{item['bin']}', not '{from_bin}'.",
                        "Use get_stock to check the current bin for this SKU.",
                    )
                if item["quantity"] < quantity:
                    raise ToolError(
                        "INSUFFICIENT_STOCK",
                        f"Only {item['quantity']} units available in bin '{from_bin}'.",
                        f"Only {item['quantity']} units available in that bin.",
                    )
                item["quantity"] -= quantity
                remaining = item["quantity"]
                # Check if destination bin already has this SKU
                dest_item = None
                for other in self._stock:
                    if other["sku"] == sku and other["bin"] == to_bin:
                        dest_item = other
                        break
                if dest_item:
                    dest_item["quantity"] += quantity
                else:
                    self._stock.append({
                        "sku": sku,
                        "description": item["description"],
                        "site": self.site_id,
                        "bin": to_bin,
                        "quantity": quantity,
                        "unit": item["unit"],
                    })
                return {
                    "action": "move_stock",
                    "executed": True,
                    "sku": sku,
                    "from_bin": from_bin,
                    "to_bin": to_bin,
                    "quantity_moved": quantity,
                    "remaining_in_source": remaining,
                    "message": "Stock move recorded.",
                }
        raise ToolError(
            "SKU_NOT_FOUND",
            f"No stock item with SKU '{sku}' at this site.",
            "Use search_stock to find the correct SKU.",
        )

    def raise_exception(self, sku: str, category: str, description: str) -> dict:
        found = any(item["sku"] == sku for item in self._stock)
        if not found:
            raise ToolError(
                "SKU_NOT_FOUND",
                f"No stock item with SKU '{sku}' at this site.",
                "Use search_stock to find the correct SKU.",
            )
        self._exception_seq += 1
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        exception_id = f"EXC-{today}-{self._exception_seq:03d}"
        now = datetime.now(timezone.utc).isoformat()
        exc = {
            "exception_id": exception_id,
            "sku": sku,
            "category": category,
            "description": description,
            "status": "open",
            "raised_at": now,
            "resolution": None,
        }
        self._exceptions.append(exc)
        return {
            "action": "raise_exception",
            "executed": True,
            "exception_id": exception_id,
            "sku": sku,
            "category": category,
            "description": description,
            "status": "open",
            "message": f"Exception raised. Use close_exception with ID '{exception_id}' when resolved.",
        }

    def close_exception(self, exception_id: str, resolution: str) -> dict:
        for exc in self._exceptions:
            if exc["exception_id"] == exception_id:
                if exc["status"] == "closed":
                    raise ToolError(
                        "ALREADY_CLOSED",
                        f"Exception {exception_id} is already closed.",
                        "This exception was already resolved. Raise a new one if the issue recurs.",
                    )
                exc["status"] = "closed"
                exc["resolution"] = resolution
                return {
                    "action": "close_exception",
                    "executed": True,
                    "exception_id": exception_id,
                    "status": "closed",
                    "resolution": resolution,
                    "message": "Exception closed.",
                }
        raise ToolError(
            "EXCEPTION_NOT_FOUND",
            f"No exception with ID '{exception_id}' at this site.",
            "Use list_open_exceptions to find valid exception IDs.",
        )

    # ── Preview builders (for confirmation flow) ────────────────────

    def preview_book_dock_slot(self, date: str, slot: str, carrier: str) -> str:
        if not DATE_RE.match(date):
            raise ToolError(
                "INVALID_DATE_FORMAT",
                f"Date '{date}' is not in YYYY-MM-DD format.",
                "Reformat the date as YYYY-MM-DD (e.g., 2026-04-08).",
            )
        for s in self._dock_slots:
            if s["date"] == date and s["slot"] == slot:
                if s["status"] == "booked":
                    raise ToolError(
                        "SLOT_ALREADY_BOOKED",
                        f"Slot {slot} on {date} is already booked by '{s['carrier']}'.",
                        "Use list_dock_slots to find an available slot.",
                    )
        return f"Book dock slot {slot} on {date} at {self.site_id} for '{carrier}'."

    def preview_cancel_dock_booking(self, date: str, slot: str) -> str:
        if not DATE_RE.match(date):
            raise ToolError(
                "INVALID_DATE_FORMAT",
                f"Date '{date}' is not in YYYY-MM-DD format.",
                "Reformat the date as YYYY-MM-DD (e.g., 2026-04-08).",
            )
        for s in self._dock_slots:
            if s["date"] == date and s["slot"] == slot:
                if s["status"] != "booked":
                    raise ToolError(
                        "SLOT_NOT_BOOKED",
                        f"Slot {slot} on {date} is not currently booked.",
                        "Use list_dock_slots to see current bookings.",
                    )
                return f"Cancel booking for '{s['carrier']}' at slot {slot} on {date} at {self.site_id}."
        raise ToolError(
            "SLOT_NOT_BOOKED",
            f"No slot {slot} on {date} found in the schedule.",
            "Use list_dock_slots to see current bookings.",
        )

    def preview_adjust_stock_count(self, sku: str, new_quantity: int, reason: str) -> str:
        for item in self._stock:
            if item["sku"] == sku:
                return (
                    f"Adjust {sku} ('{item['description']}') at bin {item['bin']}: "
                    f"{item['quantity']} → {new_quantity} {item['unit']}. "
                    f"Reason: '{reason}'."
                )
        raise ToolError(
            "SKU_NOT_FOUND",
            f"No stock item with SKU '{sku}' at this site.",
            "Use search_stock to find the correct SKU at this site.",
        )

    def preview_move_stock(self, sku: str, from_bin: str, to_bin: str, quantity: int) -> str:
        if from_bin == to_bin:
            raise ToolError(
                "SAME_BIN",
                "Source and destination bins are the same.",
                "Provide a different destination bin.",
            )
        for item in self._stock:
            if item["sku"] == sku:
                if item["bin"] != from_bin:
                    raise ToolError(
                        "BIN_MISMATCH",
                        f"SKU '{sku}' is in bin '{item['bin']}', not '{from_bin}'.",
                        "Use get_stock to check the current bin for this SKU.",
                    )
                if item["quantity"] < quantity:
                    raise ToolError(
                        "INSUFFICIENT_STOCK",
                        f"Only {item['quantity']} units available in bin '{from_bin}'.",
                        f"Only {item['quantity']} units available in that bin.",
                    )
                return (
                    f"Move {quantity} {item['unit']} of {sku} ('{item['description']}') "
                    f"from bin {from_bin} to bin {to_bin}."
                )
        raise ToolError(
            "SKU_NOT_FOUND",
            f"No stock item with SKU '{sku}' at this site.",
            "Use search_stock to find the correct SKU.",
        )

    def preview_raise_exception(self, sku: str, category: str, description: str) -> str:
        found_item = None
        for item in self._stock:
            if item["sku"] == sku:
                found_item = item
                break
        if not found_item:
            raise ToolError(
                "SKU_NOT_FOUND",
                f"No stock item with SKU '{sku}' at this site.",
                "Use search_stock to find the correct SKU.",
            )
        return f"Raise '{category}' exception for {sku} ('{found_item['description']}'): '{description}'."

    def preview_close_exception(self, exception_id: str, resolution: str) -> str:
        for exc in self._exceptions:
            if exc["exception_id"] == exception_id:
                if exc["status"] == "closed":
                    raise ToolError(
                        "ALREADY_CLOSED",
                        f"Exception {exception_id} is already closed.",
                        "This exception was already resolved. Raise a new one if the issue recurs.",
                    )
                return (
                    f"Close exception {exception_id} ({exc['category']}, {exc['sku']}) "
                    f"with resolution: '{resolution}'."
                )
        raise ToolError(
            "EXCEPTION_NOT_FOUND",
            f"No exception with ID '{exception_id}' at this site.",
            "Use list_open_exceptions to find valid exception IDs.",
        )
