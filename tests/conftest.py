from pathlib import Path

import pytest

from warehouse.confirmation import ConfirmationStore
from warehouse.data_store import DataStore

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STOCK_CSV = str(DATA_DIR / "stock_snapshot.csv")
DOCK_JSONL = str(DATA_DIR / "dock_schedule.jsonl")


@pytest.fixture
def leeds_store():
    return DataStore("LEEDS-01", STOCK_CSV, DOCK_JSONL)


@pytest.fixture
def reading_store():
    return DataStore("READING-02", STOCK_CSV, DOCK_JSONL)


@pytest.fixture
def glasgow_store():
    return DataStore("GLASGOW-03", STOCK_CSV, DOCK_JSONL)


@pytest.fixture
def confirmation_store():
    return ConfirmationStore()
