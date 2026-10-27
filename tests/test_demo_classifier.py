import numpy as np
import pytest

from caixa_inteligente.demo.classifier import ProductClassifier


def test_training_learns_labels_instead_of_relying_on_reference_order():
    features = np.array([[1, 0.1, 0], [0.9, 0, 0.1], [0, 1, 0.1], [0.1, 0.9, 0]])
    labels = ["red", "red", "blue", "blue"]
    classifier = ProductClassifier.fit(features, labels, regularization=0.1)
    assert classifier.rank(np.array([1.0, 0, 0]))[0]["sku"] == "red"
    assert classifier.rank(np.array([0.0, 1, 0]))[0]["sku"] == "blue"
    flipped = ProductClassifier.fit(features, labels[::-1], regularization=0.1)
    assert flipped.rank(np.array([1.0, 0, 0]))[0]["sku"] == "blue"


def test_unrelated_vector_has_no_artificially_high_similarity():
    classifier = ProductClassifier.fit(np.eye(3)[:2], ["a", "b"])
    ranked = classifier.rank(np.array([0.0, 0, 1]))
    assert max(row["similarity"] for row in ranked) == pytest.approx(0)


def test_model_roundtrip_and_incompatible_embedding_rejected(tmp_path):
    classifier = ProductClassifier.fit(np.eye(3), ["a", "b", "c"])
    path = tmp_path / "head.npz"
    classifier.save(path, signature="encoder-v1")
    loaded = ProductClassifier.load(path, signature="encoder-v1")
    assert loaded.rank(np.array([0.0, 1, 0])) == classifier.rank(np.array([0.0, 1, 0]))
    with pytest.raises(ValueError, match="encoder"):
        ProductClassifier.load(path, signature="different")
    for vector in (np.array([1.0, 0]), np.zeros(3), np.array([np.nan, 1, 0])):
        with pytest.raises(ValueError):
            loaded.rank(vector)


def test_invalid_training_cannot_silently_create_a_model():
    for features, labels in (
        (np.zeros((2, 3)), ["a", "b"]),
        (np.eye(3), ["a"]),
        (np.eye(3), ["a", "a", "a"]),
    ):
        with pytest.raises(ValueError):
            ProductClassifier.fit(features, labels)
