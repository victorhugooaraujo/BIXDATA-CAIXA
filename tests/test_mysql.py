"""Integração real, habilitada com TEST_DATABASE_URL (banco de testes dedicado)."""

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from caixa_inteligente.catalog import Product, find_product, import_catalog, init_catalog


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="MySQL de testes não configurado")
def test_mysql_catalog_roundtrip(tmp_path):
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    assert engine.dialect.name == "mysql"
    sku = f"test-{uuid.uuid4().hex}"
    init_catalog(engine)
    path = tmp_path / "catalog.csv"
    path.write_text(f"sku,name,price\n{sku},Banana,2.30\n", encoding="utf-8")
    try:
        import_catalog(engine, path)
        assert find_product(engine, sku).price == Decimal("2.30")
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(Product).where(Product.sku == sku))
        engine.dispose()
