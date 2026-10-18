import json
from decimal import Decimal

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from caixa_inteligente.catalog import Product, init_catalog
from caixa_inteligente.cli import main
from caixa_inteligente.vision import Gallery


class FakeEncoder:
    signature = json.dumps({"model": "fixture", "preprocessing": "fixture"})

    def __init__(self, device="cpu"):
        pass

    def encode(self, path):
        return np.array([1.0, 0.0])


@pytest.fixture
def recognition_args(tmp_path, monkeypatch):
    monkeypatch.setattr("caixa_inteligente.vision.DinoV2Encoder", FakeEncoder)
    path = tmp_path / "gallery.npz"
    Gallery(["banana", "orange"], np.eye(2), FakeEncoder.signature).save(path)
    return ["recognize", "fixture.jpg", "--gallery", str(path)]


def test_accepted_product_uses_mysql_catalog_price(recognition_args, monkeypatch, capsys):
    # SQLite only checks the integration logic; tests/test_mysql.py covers the actual backend.
    engine = create_engine("sqlite://")
    init_catalog(engine)
    with Session(engine) as session, session.begin():
        session.add(Product(sku="banana", name="Banana", price=Decimal("2.30")))
    monkeypatch.setattr("caixa_inteligente.cli.database_engine", lambda: engine)
    assert main(recognition_args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["requires_review"] is False
    assert result["product"] == {"sku": "banana", "name": "Banana", "unit_price_brl": "2.30"}


def test_visual_match_without_catalog_product_requires_review(
    recognition_args, monkeypatch, capsys
):
    engine = create_engine("sqlite://")
    init_catalog(engine)
    monkeypatch.setattr("caixa_inteligente.cli.database_engine", lambda: engine)
    assert main(recognition_args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["sku"] is None
    assert result["product"] is None
    assert result["reason"] == "product_not_in_catalog"
    assert result["requires_review"] is True


def test_ambiguous_image_does_not_fetch_a_price(recognition_args, monkeypatch, capsys):
    monkeypatch.setattr(FakeEncoder, "encode", lambda self, path: np.array([1.0, 1.0]))

    def unexpected_database_access():
        pytest.fail("Rejected recognition must not request a product price")

    monkeypatch.setattr("caixa_inteligente.cli.database_engine", unexpected_database_access)
    assert main(recognition_args + ["--min-similarity", "0.5"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["sku"] is None
    assert result["product"] is None
    assert result["reason"] == "ambiguous"
    assert result["requires_review"] is True


def test_index_can_combine_separate_dataset_directories(tmp_path, monkeypatch):
    monkeypatch.setattr("caixa_inteligente.vision.DinoV2Encoder", FakeEncoder)
    roots = [tmp_path / "grocery", tmp_path / "rpc"]
    for root, sku in zip(roots, ["6", "rpc-006"], strict=True):
        folder = root / sku
        folder.mkdir(parents=True)
        (folder / "fixture.jpg").write_bytes(b"used-by-fake-encoder")
    gallery_path = tmp_path / "market.npz"
    assert (
        main(
            [
                "index",
                "--images",
                *(str(root) for root in roots),
                "--gallery",
                str(gallery_path),
            ]
        )
        == 0
    )
    gallery = Gallery.load(gallery_path, expected_signature=FakeEncoder.signature)
    assert gallery.sample_count == 2
    assert gallery.class_count == 2
