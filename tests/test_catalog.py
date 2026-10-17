from decimal import Decimal

import pytest
from sqlalchemy import create_engine

from caixa_inteligente.catalog import find_product, import_catalog, init_catalog, read_catalog


def test_import_is_idempotent_and_updates_price(tmp_path):
    engine = create_engine("sqlite://")
    init_catalog(engine)
    path = tmp_path / "catalog.csv"
    path.write_text("sku,name,price\nbanana,Banana,2.30\n", encoding="utf-8")
    assert import_catalog(engine, path) == 1
    path.write_text("sku,name,price\nbanana,Banana,3.45\n", encoding="utf-8")
    assert import_catalog(engine, path) == 1
    assert find_product(engine, "banana").price == Decimal("3.45")
    assert find_product(engine, "unknown") is None


@pytest.mark.parametrize("price", ["0", "-1", "nan", "inf", "1.001", "100000000"])
def test_invalid_prices_are_rejected(tmp_path, price):
    path = tmp_path / "catalog.csv"
    path.write_text(f"sku,name,price\nbanana,Banana,{price}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_catalog(path)


def test_invalid_csv_does_not_partially_change_catalog(tmp_path):
    engine = create_engine("sqlite://")
    init_catalog(engine)
    path = tmp_path / "catalog.csv"
    path.write_text("sku,name,price\na,Apple,1.00\na,Duplicate,2.00\n", encoding="utf-8")
    with pytest.raises(ValueError):
        import_catalog(engine, path)
    assert find_product(engine, "a") is None


@pytest.mark.parametrize("row", ["banana,Banana,2,30", "banana,Banana", "banana"])
def test_malformed_csv_rows_cannot_silently_change_prices(tmp_path, row):
    path = tmp_path / "catalog.csv"
    path.write_text(f"sku,name,price\n{row}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exatamente sku,name,price"):
        read_catalog(path)
