"""Catálogo de preços; o dataset fornece imagens, não preços reais."""

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import CheckConstraint, Numeric, String, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (CheckConstraint("price > 0", name="positive_price"),)

    sku: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))


@dataclass(frozen=True)
class ProductInfo:
    sku: str
    name: str
    price: Decimal


def init_catalog(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def read_catalog(path: Path) -> list[ProductInfo]:
    products: list[ProductInfo] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["sku", "name", "price"]:
            raise ValueError("O catálogo CSV deve ter cabeçalho sku,name,price.")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(
                    f"Linha {reader.line_num}: use exatamente sku,name,price e ponto decimal."
                )
            sku, name = row["sku"].strip(), row["name"].strip()
            try:
                price = Decimal(row["price"])
            except InvalidOperation as exc:
                raise ValueError(f"Preço inválido para {sku}.") from exc
            if not sku or len(sku) > 64 or not name or len(name) > 160 or sku in seen:
                raise ValueError(f"SKU/nome inválido ou duplicado: {sku}.")
            if (
                not price.is_finite()
                or price <= 0
                or price >= Decimal("100000000")
                or price != price.quantize(Decimal("0.01"))
            ):
                raise ValueError(f"Preço deve ser positivo, com até 2 casas decimais: {sku}.")
            seen.add(sku)
            products.append(ProductInfo(sku, name, price))
    if not products:
        raise ValueError("O catálogo está vazio.")
    return products


def import_catalog(engine: Engine, path: Path) -> int:
    products = read_catalog(path)
    with Session(engine) as session, session.begin():
        for product in products:
            session.merge(Product(sku=product.sku, name=product.name, price=product.price))
    return len(products)


def find_product(engine: Engine, sku: str) -> ProductInfo | None:
    with Session(engine) as session:
        product = session.scalar(select(Product).where(Product.sku == sku))
        return ProductInfo(product.sku, product.name, product.price) if product else None
