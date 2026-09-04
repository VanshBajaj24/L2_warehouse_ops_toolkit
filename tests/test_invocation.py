"""Tool invocation tests — happy path for every tool."""

import pytest


class TestGetStock:
    def test_valid_sku(self, leeds_store):
        result = leeds_store.get_stock("SKU-8801")
        assert result["sku"] == "SKU-8801"
        assert result["description"] == "Pallet wrap, 500mm clear"
        assert result["bin"] == "A-12-3"
        assert result["quantity"] == 240
        assert result["unit"] == "each"

    def test_out_of_stock_item(self, glasgow_store):
        result = glasgow_store.get_stock("SKU-8809")
        assert result["quantity"] == 0


class TestSearchStock:
    def test_ambiguous_returns_multiple(self, leeds_store):
        result = leeds_store.search_stock("pallet wrap")
        assert result["total"] == 2
        skus = {m["sku"] for m in result["matches"]}
        assert skus == {"SKU-8801", "SKU-8802"}

    def test_unambiguous_returns_one(self, leeds_store):
        result = leeds_store.search_stock("air pillow")
        assert result["total"] == 1
        assert result["matches"][0]["sku"] == "SKU-8811"

    def test_case_insensitive(self, leeds_store):
        result = leeds_store.search_stock("PALLET WRAP")
        assert result["total"] == 2

    def test_includes_out_of_stock(self, glasgow_store):
        result = glasgow_store.search_stock("shrink film")
        skus = {m["sku"] for m in result["matches"]}
        assert "SKU-8809" in skus
        zero_item = [m for m in result["matches"] if m["sku"] == "SKU-8809"][0]
        assert zero_item["quantity"] == 0


class TestListDockSlots:
    def test_all_slots(self, leeds_store):
        result = leeds_store.list_dock_slots("2026-04-08")
        assert result["site"] == "LEEDS-01"
        assert result["date"] == "2026-04-08"
        assert len(result["slots"]) == 6

    def test_filter_available(self, leeds_store):
        result = leeds_store.list_dock_slots("2026-04-08", status="available")
        for s in result["slots"]:
            assert s["status"] == "available"
        assert len(result["slots"]) == 4

    def test_filter_booked(self, leeds_store):
        result = leeds_store.list_dock_slots("2026-04-08", status="booked")
        for s in result["slots"]:
            assert s["status"] == "booked"
        assert len(result["slots"]) == 2


class TestListOpenExceptions:
    def test_initially_empty(self, leeds_store):
        result = leeds_store.list_open_exceptions()
        assert result["total"] == 0
        assert result["open_exceptions"] == []


class TestBookDockSlot:
    def test_book_and_verify(self, leeds_store, confirmation_store):
        preview = leeds_store.preview_book_dock_slot("2026-04-08", "06:00", "ABC Logistics")
        conf = confirmation_store.create(
            action="book_dock_slot",
            params={"date": "2026-04-08", "slot": "06:00", "carrier": "ABC Logistics"},
            preview=preview,
        )
        assert conf["requires_confirmation"] is True
        pending = confirmation_store.confirm(conf["confirmation_id"])
        result = leeds_store.book_dock_slot(
            pending.params["date"], pending.params["slot"], pending.params["carrier"]
        )
        assert result["executed"] is True
        slots = leeds_store.list_dock_slots("2026-04-08", status="booked")
        booked_times = {s["slot"] for s in slots["slots"]}
        assert "06:00" in booked_times


class TestCancelDockBooking:
    def test_cancel_and_verify(self, leeds_store, confirmation_store):
        preview = leeds_store.preview_cancel_dock_booking("2026-04-08", "08:00")
        conf = confirmation_store.create(
            action="cancel_dock_booking",
            params={"date": "2026-04-08", "slot": "08:00"},
            preview=preview,
        )
        pending = confirmation_store.confirm(conf["confirmation_id"])
        result = leeds_store.cancel_dock_booking(pending.params["date"], pending.params["slot"])
        assert result["executed"] is True
        assert result["previous_carrier"] == "Northbound Freight"
        slots = leeds_store.list_dock_slots("2026-04-08")
        slot_08 = [s for s in slots["slots"] if s["slot"] == "08:00"][0]
        assert slot_08["status"] == "available"


class TestAdjustStockCount:
    def test_adjust_and_verify(self, leeds_store, confirmation_store):
        preview = leeds_store.preview_adjust_stock_count("SKU-8801", 235, "Five damaged")
        conf = confirmation_store.create(
            action="adjust_stock_count",
            params={"sku": "SKU-8801", "new_quantity": 235, "reason": "Five damaged"},
            preview=preview,
            irreversible=True,
        )
        assert conf.get("irreversible") is True
        pending = confirmation_store.confirm(conf["confirmation_id"])
        result = leeds_store.adjust_stock_count(
            pending.params["sku"], pending.params["new_quantity"], pending.params["reason"]
        )
        assert result["executed"] is True
        assert result["previous_quantity"] == 240
        assert result["new_quantity"] == 235
        updated = leeds_store.get_stock("SKU-8801")
        assert updated["quantity"] == 235
        assert len(leeds_store._audit_log) >= 1


class TestMoveStock:
    def test_move_and_verify(self, leeds_store, confirmation_store):
        preview = leeds_store.preview_move_stock("SKU-8801", "A-12-3", "A-15-1", 50)
        conf = confirmation_store.create(
            action="move_stock",
            params={"sku": "SKU-8801", "from_bin": "A-12-3", "to_bin": "A-15-1", "quantity": 50},
            preview=preview,
        )
        pending = confirmation_store.confirm(conf["confirmation_id"])
        result = leeds_store.move_stock(
            pending.params["sku"],
            pending.params["from_bin"],
            pending.params["to_bin"],
            pending.params["quantity"],
        )
        assert result["executed"] is True
        assert result["quantity_moved"] == 50
        assert result["remaining_in_source"] == 190


class TestRaiseException:
    def test_raise_and_list(self, leeds_store, confirmation_store):
        preview = leeds_store.preview_raise_exception("SKU-8801", "damaged", "Crushed rolls")
        conf = confirmation_store.create(
            action="raise_exception",
            params={"sku": "SKU-8801", "category": "damaged", "description": "Crushed rolls"},
            preview=preview,
        )
        pending = confirmation_store.confirm(conf["confirmation_id"])
        result = leeds_store.raise_exception(
            pending.params["sku"], pending.params["category"], pending.params["description"]
        )
        assert result["executed"] is True
        assert result["status"] == "open"
        exceptions = leeds_store.list_open_exceptions()
        assert exceptions["total"] == 1
        assert exceptions["open_exceptions"][0]["exception_id"] == result["exception_id"]


class TestCloseException:
    def test_close_and_verify(self, leeds_store, confirmation_store):
        # First raise one
        result = leeds_store.raise_exception("SKU-8801", "damaged", "Crushed rolls")
        exc_id = result["exception_id"]

        preview = leeds_store.preview_close_exception(exc_id, "Units removed")
        conf = confirmation_store.create(
            action="close_exception",
            params={"exception_id": exc_id, "resolution": "Units removed"},
            preview=preview,
        )
        pending = confirmation_store.confirm(conf["confirmation_id"])
        close_result = leeds_store.close_exception(
            pending.params["exception_id"], pending.params["resolution"]
        )
        assert close_result["executed"] is True
        assert close_result["status"] == "closed"
        exceptions = leeds_store.list_open_exceptions()
        assert exceptions["total"] == 0
