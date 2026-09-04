"""Error shape tests — every error has code, message, hint."""

import pytest

from warehouse.errors import ToolError


def assert_error_shape(exc: ToolError):
    """Verify the error follows the standard shape."""
    d = exc.to_dict()
    assert d["error"] is True
    assert isinstance(d["code"], str) and len(d["code"]) > 0
    assert isinstance(d["message"], str) and len(d["message"]) > 0
    assert isinstance(d["hint"], str) and len(d["hint"]) > 0


class TestGetStockErrors:
    def test_sku_not_found(self, leeds_store):
        with pytest.raises(ToolError) as exc_info:
            leeds_store.get_stock("SKU-9999")
        assert exc_info.value.code == "SKU_NOT_FOUND"
        assert_error_shape(exc_info.value)


class TestSearchStockErrors:
    def test_no_matches(self, leeds_store):
        with pytest.raises(ToolError) as exc_info:
            leeds_store.search_stock("xyznonexistent")
        assert exc_info.value.code == "NO_MATCHES"
        assert_error_shape(exc_info.value)


class TestDockErrors:
    def test_invalid_date_format(self, leeds_store):
        with pytest.raises(ToolError) as exc_info:
            leeds_store.list_dock_slots("not-a-date")
        assert exc_info.value.code == "INVALID_DATE_FORMAT"
        assert_error_shape(exc_info.value)

    def test_slot_already_booked(self, leeds_store):
        with pytest.raises(ToolError) as exc_info:
            leeds_store.preview_book_dock_slot("2026-04-08", "08:00", "Test")
        assert exc_info.value.code == "SLOT_ALREADY_BOOKED"
        assert_error_shape(exc_info.value)

    def test_slot_not_booked(self, leeds_store):
        with pytest.raises(ToolError) as exc_info:
            leeds_store.preview_cancel_dock_booking("2026-04-08", "06:00")
        assert exc_info.value.code == "SLOT_NOT_BOOKED"
        assert_error_shape(exc_info.value)


class TestStockWriteErrors:
    def test_adjust_sku_not_found(self, leeds_store):
        with pytest.raises(ToolError) as exc_info:
            leeds_store.preview_adjust_stock_count("SKU-9999", 10, "test")
        assert exc_info.value.code == "SKU_NOT_FOUND"
        assert_error_shape(exc_info.value)

    def test_move_bin_mismatch(self, leeds_store):
        with pytest.raises(ToolError) as exc_info:
            leeds_store.preview_move_stock("SKU-8801", "WRONG-BIN", "A-15-1", 10)
        assert exc_info.value.code == "BIN_MISMATCH"
        assert_error_shape(exc_info.value)

    def test_move_insufficient_stock(self, leeds_store):
        with pytest.raises(ToolError) as exc_info:
            leeds_store.preview_move_stock("SKU-8801", "A-12-3", "A-15-1", 99999)
        assert exc_info.value.code == "INSUFFICIENT_STOCK"
        assert_error_shape(exc_info.value)

    def test_move_same_bin(self, leeds_store):
        with pytest.raises(ToolError) as exc_info:
            leeds_store.preview_move_stock("SKU-8801", "A-12-3", "A-12-3", 10)
        assert exc_info.value.code == "SAME_BIN"
        assert_error_shape(exc_info.value)


class TestExceptionErrors:
    def test_raise_sku_not_found(self, leeds_store):
        with pytest.raises(ToolError) as exc_info:
            leeds_store.preview_raise_exception("SKU-9999", "damaged", "test")
        assert exc_info.value.code == "SKU_NOT_FOUND"
        assert_error_shape(exc_info.value)

    def test_close_not_found(self, leeds_store):
        with pytest.raises(ToolError) as exc_info:
            leeds_store.preview_close_exception("EXC-00000000-999", "resolved")
        assert exc_info.value.code == "EXCEPTION_NOT_FOUND"
        assert_error_shape(exc_info.value)

    def test_close_already_closed(self, leeds_store):
        result = leeds_store.raise_exception("SKU-8801", "damaged", "test")
        exc_id = result["exception_id"]
        leeds_store.close_exception(exc_id, "fixed")
        with pytest.raises(ToolError) as exc_info:
            leeds_store.preview_close_exception(exc_id, "again")
        assert exc_info.value.code == "ALREADY_CLOSED"
        assert_error_shape(exc_info.value)


class TestConfirmationErrors:
    def test_invalid_id_shape(self, confirmation_store):
        with pytest.raises(ToolError) as exc_info:
            confirmation_store.confirm("BOGUS")
        assert exc_info.value.code == "INVALID_CONFIRMATION_ID"
        assert_error_shape(exc_info.value)

    def test_expired_shape(self, confirmation_store):
        import time
        from warehouse.confirmation import CONFIRMATION_TTL_SECONDS

        conf = confirmation_store.create("test", {}, "preview")
        cid = conf["confirmation_id"]
        confirmation_store._pending[cid].created_at = (
            time.time() - CONFIRMATION_TTL_SECONDS - 1
        )
        with pytest.raises(ToolError) as exc_info:
            confirmation_store.confirm(cid)
        assert exc_info.value.code == "CONFIRMATION_EXPIRED"
        assert_error_shape(exc_info.value)

    def test_already_confirmed_shape(self, confirmation_store):
        conf = confirmation_store.create("test", {}, "preview")
        cid = conf["confirmation_id"]
        confirmation_store.confirm(cid)
        with pytest.raises(ToolError) as exc_info:
            confirmation_store.confirm(cid)
        assert exc_info.value.code == "ALREADY_CONFIRMED"
        assert_error_shape(exc_info.value)
