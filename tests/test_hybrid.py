import json

import numpy as np
import pytest

from caixa_inteligente.hybrid import TextGallery, fuse
from caixa_inteligente.ocr import evidence_text
from caixa_inteligente.vision import DINOV2_SIGNATURE, Candidate, Gallery


def reference(sku, text):
    return {"sku": sku, "text": text, "sha256": "a" * 64}


def test_ocr_disambiguates_similar_packages_without_changing_visual_model():
    gallery = TextGallery(
        [reference("a", "Leite integral 1L"), reference("b", "Leite desnatado 1L")], "test"
    )
    visual = [Candidate("a", 0.80), Candidate("b", 0.79)]
    ranked = fuse(visual, gallery.rank("Leite desnatado 1L"))
    assert ranked[0]["sku"] == "b"


def test_empty_or_out_of_vocabulary_text_preserves_visual_order():
    gallery = TextGallery([reference("a", "milk"), reference("b", "rice")], "test")
    visual = [Candidate("b", 0.8), Candidate("a", 0.7)]
    for query in ["", "不存在"]:
        assert [row["sku"] for row in fuse(visual, gallery.rank(query))] == ["b", "a"]


def test_chinese_and_quantity_variants_are_not_removed():
    gallery = TextGallery([reference("a", "牛奶 200ml"), reference("b", "牛奶 400ml")], "test")
    assert gallery.rank("牛奶 400ml")[0].sku == "b"


def test_text_roundtrip_and_signature_rejection(tmp_path):
    path = tmp_path / "text.json"
    TextGallery([reference("a", "café")], "one").save(path)
    assert TextGallery.load(path, "one").rank("CAFE")[0].similarity == pytest.approx(1)
    with pytest.raises(ValueError, match="incompatível"):
        TextGallery.load(path, "two")
    contents = json.loads(path.read_text(encoding="utf-8"))
    contents["references"][0]["text"] = None
    path.write_text(json.dumps(contents), encoding="utf-8")
    with pytest.raises(ValueError, match="Texto"):
        TextGallery.load(path, "one")


def test_mismatched_sku_sets_are_not_silently_fused():
    with pytest.raises(ValueError, match="mesmos SKUs"):
        fuse([Candidate("a", 1)], [Candidate("b", 1)])


@pytest.mark.parametrize("weight", [float("nan"), -0.1, 1.1])
def test_invalid_fusion_weight_is_rejected(weight):
    with pytest.raises(ValueError, match="Peso"):
        fuse([], [], weight)


def test_weak_ocr_is_excluded_from_text_fingerprint():
    evidence = {"lines": [{"text": "inventado", "score": 0.2}, {"text": "200 ml", "score": 0.9}]}
    assert evidence_text(evidence) == "200 ml"


def test_public_visual_ranking_preserves_all_distinct_classes():
    gallery = Gallery(
        ["a", "a", "b", "c"], np.array([[1, 0], [1, 0], [0.8, 0.2], [0, 1]]), DINOV2_SIGNATURE
    )
    ranked = gallery.rank(np.array([1, 0]))
    assert [candidate.sku for candidate in ranked] == ["a", "b", "c"]
    assert gallery.recognize(np.array([1, 0])).candidates == ranked
