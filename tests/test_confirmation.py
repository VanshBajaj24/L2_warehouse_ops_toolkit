"""Confirmation flow tests — two-step, expiry, double-confirm, invalid ID."""

import time

import pytest

from warehouse.confirmation import ConfirmationStore, CONFIRMATION_TTL_SECONDS
from warehouse.errors import ToolError


class TestTwoStepFlow:
    def test_create_returns_preview(self, confirmation_store):
        result = confirmation_store.create(
            action="book_dock_slot",
            params={"date": "2026-04-08", "slot": "06:00", "carrier": "Test"},
            preview="Book slot 06:00 for Test.",
        )
        assert result["requires_confirmation"] is True
        assert "confirmation_id" in result
        assert result["confirmation_id"].startswith("CONF-")
        assert result["action"] == "book_dock_slot"
        assert result["preview"] == "Book slot 06:00 for Test."

    def test_confirm_returns_pending(self, confirmation_store):
        result = confirmation_store.create(
            action="book_dock_slot",
            params={"date": "2026-04-08", "slot": "06:00", "carrier": "Test"},
            preview="preview text",
        )
        pending = confirmation_store.confirm(result["confirmation_id"])
        assert pending.action == "book_dock_slot"
        assert pending.params == {"date": "2026-04-08", "slot": "06:00", "carrier": "Test"}
        assert pending.executed is True


class TestIrreversibleFlag:
    def test_irreversible_in_preview(self, confirmation_store):
        result = confirmation_store.create(
            action="adjust_stock_count",
            params={"sku": "SKU-8801", "new_quantity": 200, "reason": "recount"},
            preview="Adjust stock...",
            irreversible=True,
        )
        assert result.get("irreversible") is True

    def test_reversible_no_flag(self, confirmation_store):
        result = confirmation_store.create(
            action="book_dock_slot",
            params={"date": "2026-04-08", "slot": "06:00", "carrier": "Test"},
            preview="Book...",
            irreversible=False,
        )
        assert "irreversible" not in result


class TestExpiredConfirmation:
    def test_expired_id_rejected(self, confirmation_store):
        result = confirmation_store.create(
            action="book_dock_slot",
            params={},
            preview="preview",
        )
        cid = result["confirmation_id"]
        # Artificially expire by backdating created_at
        confirmation_store._pending[cid].created_at = (
            time.time() - CONFIRMATION_TTL_SECONDS - 1
        )
        with pytest.raises(ToolError) as exc_info:
            confirmation_store.confirm(cid)
        assert exc_info.value.code == "CONFIRMATION_EXPIRED"


class TestDoubleConfirm:
    def test_already_confirmed_rejected(self, confirmation_store):
        result = confirmation_store.create(
            action="book_dock_slot",
            params={},
            preview="preview",
        )
        cid = result["confirmation_id"]
        confirmation_store.confirm(cid)
        with pytest.raises(ToolError) as exc_info:
            confirmation_store.confirm(cid)
        assert exc_info.value.code == "ALREADY_CONFIRMED"


class TestInvalidConfirmationId:
    def test_nonexistent_id(self, confirmation_store):
        with pytest.raises(ToolError) as exc_info:
            confirmation_store.confirm("CONF-does-not-exist")
        assert exc_info.value.code == "INVALID_CONFIRMATION_ID"

    def test_empty_id(self, confirmation_store):
        with pytest.raises(ToolError) as exc_info:
            confirmation_store.confirm("")
        assert exc_info.value.code == "INVALID_CONFIRMATION_ID"


class TestFullFlowWithDataStore:
    def test_book_via_confirmation(self, leeds_store, confirmation_store):
        preview = leeds_store.preview_book_dock_slot("2026-04-08", "06:00", "FastFreight")
        conf = confirmation_store.create(
            action="book_dock_slot",
            params={"date": "2026-04-08", "slot": "06:00", "carrier": "FastFreight"},
            preview=preview,
        )
        pending = confirmation_store.confirm(conf["confirmation_id"])
        result = leeds_store.book_dock_slot(
            pending.params["date"], pending.params["slot"], pending.params["carrier"]
        )
        assert result["executed"] is True
        assert result["carrier"] == "FastFreight"

    def test_adjust_via_confirmation_irreversible(self, leeds_store, confirmation_store):
        preview = leeds_store.preview_adjust_stock_count("SKU-8801", 230, "damaged goods")
        conf = confirmation_store.create(
            action="adjust_stock_count",
            params={"sku": "SKU-8801", "new_quantity": 230, "reason": "damaged goods"},
            preview=preview,
            irreversible=True,
        )
        assert conf["irreversible"] is True
        pending = confirmation_store.confirm(conf["confirmation_id"])
        result = leeds_store.adjust_stock_count(
            pending.params["sku"], pending.params["new_quantity"], pending.params["reason"]
        )
        assert result["executed"] is True
        assert result["previous_quantity"] == 240
        assert result["new_quantity"] == 230
