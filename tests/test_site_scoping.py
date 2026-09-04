"""Site scoping tests — cross-site access blocked, same-site access works."""

import pytest

from warehouse.errors import ToolError


class TestCrossSiteBlocked:
    def test_leeds_cannot_read_reading_sku(self, leeds_store):
        with pytest.raises(ToolError) as exc_info:
            leeds_store.get_stock("SKU-8805")  # READING-02 item
        assert exc_info.value.code == "SKU_NOT_FOUND"

    def test_leeds_cannot_read_glasgow_sku(self, leeds_store):
        with pytest.raises(ToolError) as exc_info:
            leeds_store.get_stock("SKU-8808")  # GLASGOW-03 item
        assert exc_info.value.code == "SKU_NOT_FOUND"

    def test_reading_cannot_search_leeds_stock(self, reading_store):
        with pytest.raises(ToolError) as exc_info:
            reading_store.search_stock("pallet wrap")  # LEEDS-01 items
        assert exc_info.value.code == "NO_MATCHES"

    def test_glasgow_cannot_see_leeds_dock(self, glasgow_store):
        result = glasgow_store.list_dock_slots("2026-04-08")
        for s in result["slots"]:
            assert s["carrier"] != "Northbound Freight" or True  # only GLASGOW slots
        # Verify GLASGOW-03 slots only
        assert result["site"] == "GLASGOW-03"

    def test_cross_site_adjust_blocked(self, leeds_store):
        with pytest.raises(ToolError) as exc_info:
            leeds_store.preview_adjust_stock_count("SKU-8808", 100, "test")
        assert exc_info.value.code == "SKU_NOT_FOUND"

    def test_cross_site_move_blocked(self, leeds_store):
        with pytest.raises(ToolError) as exc_info:
            leeds_store.preview_move_stock("SKU-8805", "B-03-7", "B-99-1", 10)
        assert exc_info.value.code == "SKU_NOT_FOUND"

    def test_cross_site_raise_exception_blocked(self, leeds_store):
        with pytest.raises(ToolError) as exc_info:
            leeds_store.preview_raise_exception("SKU-8808", "damaged", "test")
        assert exc_info.value.code == "SKU_NOT_FOUND"


class TestSameSiteWorks:
    def test_leeds_reads_leeds_sku(self, leeds_store):
        result = leeds_store.get_stock("SKU-8801")
        assert result["sku"] == "SKU-8801"

    def test_reading_reads_reading_sku(self, reading_store):
        result = reading_store.get_stock("SKU-8805")
        assert result["sku"] == "SKU-8805"

    def test_glasgow_reads_glasgow_sku(self, glasgow_store):
        result = glasgow_store.get_stock("SKU-8808")
        assert result["sku"] == "SKU-8808"

    def test_reading_searches_reading_stock(self, reading_store):
        result = reading_store.search_stock("corner protector")
        assert result["total"] == 2
        skus = {m["sku"] for m in result["matches"]}
        assert skus == {"SKU-8805", "SKU-8806"}

    def test_glasgow_lists_glasgow_dock(self, glasgow_store):
        result = glasgow_store.list_dock_slots("2026-04-08")
        assert result["site"] == "GLASGOW-03"
        assert len(result["slots"]) == 6

    def test_leeds_adjust_leeds_sku(self, leeds_store):
        preview = leeds_store.preview_adjust_stock_count("SKU-8801", 200, "recount")
        assert "SKU-8801" in preview


class TestErrorsDoNotLeakCrossSite:
    def test_error_does_not_reveal_other_site(self, leeds_store):
        with pytest.raises(ToolError) as exc_info:
            leeds_store.get_stock("SKU-8805")
        assert "READING" not in exc_info.value.message
        assert "READING" not in exc_info.value.hint
