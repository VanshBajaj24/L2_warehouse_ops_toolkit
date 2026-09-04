"""Schema rejection tests — invalid inputs rejected before business logic."""

import pytest
from pydantic import ValidationError

from warehouse.data_store import DataStore
from warehouse.errors import ToolError
from warehouse.models import (
    AdjustStockCountInput,
    BookDockSlotInput,
    CancelDockBookingInput,
    CloseExceptionInput,
    GetStockInput,
    ListDockSlotsInput,
    MoveStockInput,
    RaiseExceptionInput,
    SearchStockInput,
)


class TestGetStockSchema:
    def test_invalid_sku_format(self):
        with pytest.raises(ValidationError):
            GetStockInput(sku="INVALID")

    def test_sku_too_short(self):
        with pytest.raises(ValidationError):
            GetStockInput(sku="SKU-1")

    def test_sku_no_prefix(self):
        with pytest.raises(ValidationError):
            GetStockInput(sku="8801")

    def test_valid_sku(self):
        m = GetStockInput(sku="SKU-8801")
        assert m.sku == "SKU-8801"


class TestSearchStockSchema:
    def test_query_too_short(self):
        with pytest.raises(ValidationError):
            SearchStockInput(query="a")

    def test_empty_query(self):
        with pytest.raises(ValidationError):
            SearchStockInput(query="")

    def test_valid_query(self):
        m = SearchStockInput(query="wrap")
        assert m.query == "wrap"


class TestBookDockSlotSchema:
    def test_invalid_slot_time(self):
        with pytest.raises(ValidationError):
            BookDockSlotInput(date="2026-04-08", slot="09:30", carrier="Test")

    def test_empty_carrier(self):
        with pytest.raises(ValidationError):
            BookDockSlotInput(date="2026-04-08", slot="06:00", carrier="")

    def test_valid(self):
        m = BookDockSlotInput(date="2026-04-08", slot="06:00", carrier="Test Co")
        assert m.slot.value == "06:00"


class TestCancelDockBookingSchema:
    def test_invalid_slot_time(self):
        with pytest.raises(ValidationError):
            CancelDockBookingInput(date="2026-04-08", slot="07:00")


class TestAdjustStockCountSchema:
    def test_negative_quantity(self):
        with pytest.raises(ValidationError):
            AdjustStockCountInput(sku="SKU-8801", new_quantity=-1, reason="test")

    def test_empty_reason(self):
        with pytest.raises(ValidationError):
            AdjustStockCountInput(sku="SKU-8801", new_quantity=10, reason="")

    def test_zero_quantity_valid(self):
        m = AdjustStockCountInput(sku="SKU-8801", new_quantity=0, reason="all gone")
        assert m.new_quantity == 0

    def test_valid(self):
        m = AdjustStockCountInput(sku="SKU-8801", new_quantity=100, reason="recount")
        assert m.new_quantity == 100


class TestMoveStockSchema:
    def test_zero_quantity(self):
        with pytest.raises(ValidationError):
            MoveStockInput(sku="SKU-8801", from_bin="A-1", to_bin="A-2", quantity=0)

    def test_negative_quantity(self):
        with pytest.raises(ValidationError):
            MoveStockInput(sku="SKU-8801", from_bin="A-1", to_bin="A-2", quantity=-5)

    def test_valid(self):
        m = MoveStockInput(sku="SKU-8801", from_bin="A-1", to_bin="A-2", quantity=10)
        assert m.quantity == 10


class TestRaiseExceptionSchema:
    def test_invalid_category(self):
        with pytest.raises(ValidationError):
            RaiseExceptionInput(sku="SKU-8801", category="broken", description="test")

    def test_valid_category(self):
        m = RaiseExceptionInput(sku="SKU-8801", category="damaged", description="test")
        assert m.category.value == "damaged"


class TestDockStatusSchema:
    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            ListDockSlotsInput(date="2026-04-08", status="pending")

    def test_valid_status(self):
        m = ListDockSlotsInput(date="2026-04-08", status="available")
        assert m.status.value == "available"

    def test_none_status_valid(self):
        m = ListDockSlotsInput(date="2026-04-08")
        assert m.status is None


class TestDateValidation:
    def test_invalid_date_format_dock(self, leeds_store):
        with pytest.raises(ToolError) as exc_info:
            leeds_store.list_dock_slots("08-04-2026")
        assert exc_info.value.code == "INVALID_DATE_FORMAT"

    def test_invalid_date_format_book(self, leeds_store):
        with pytest.raises(ToolError):
            leeds_store.preview_book_dock_slot("April 8", "06:00", "Test")
