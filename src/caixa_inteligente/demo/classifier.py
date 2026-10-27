"""Ridge classifier trained on frozen DINO features, with independent similarity evidence."""

import json

import numpy as np


def _normalize(values):
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 2 or not np.isfinite(values).all():
        raise ValueError("Features devem formar matriz finita.")
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    if np.any(norms <= 0):
        raise ValueError("Features não podem ser nulas.")
    return values / norms


class ProductClassifier:
    def __init__(self, skus, weights, references, reference_classes):
        self.skus = list(skus)
        self.weights = np.asarray(weights, dtype=np.float64)
        self.references = _normalize(references)
        self.reference_classes = np.asarray(reference_classes, dtype=np.int64)

    @classmethod
    def fit(cls, features, labels, regularization=1.0):
        features = _normalize(features)
        skus = sorted(set(labels))
        if len(labels) != len(features) or len(skus) < 2 or regularization <= 0:
            raise ValueError("Treinamento precisa de rótulos, duas classes e regularização.")
        indices = np.array([skus.index(label) for label in labels])
        targets = np.eye(len(skus))[indices]
        # Equal contribution per class prevents the public dataset overwhelming user products.
        balance = 1 / np.bincount(indices)[indices]
        balance *= len(features) / balance.sum()
        augmented = np.column_stack([features, np.ones(len(features))])
        weighted = augmented * balance[:, None]
        penalty = np.eye(augmented.shape[1]) * regularization
        penalty[-1, -1] = 1e-6
        weights = np.linalg.solve(augmented.T @ weighted + penalty, weighted.T @ targets)
        return cls(skus, weights, features, indices)

    def rank(self, vector):
        vector = _normalize(np.asarray(vector)[None, :])[0]
        if len(vector) != self.weights.shape[0] - 1:
            raise ValueError("Dimensão incompatível com encoder.")
        scores = np.append(vector, 1) @ self.weights
        similarities = self.references @ vector
        rows = []
        for index, sku in enumerate(self.skus):
            rows.append(
                {
                    "sku": sku,
                    "score": float(scores[index]),
                    "similarity": float(
                        np.clip(similarities[self.reference_classes == index].max(), -1, 1)
                    ),
                }
            )
        return sorted(rows, key=lambda row: (-row["score"], row["sku"]))

    def save(self, path, *, signature):
        np.savez_compressed(
            path,
            skus=np.array(self.skus),
            weights=self.weights,
            references=self.references,
            classes=self.reference_classes,
            metadata=np.array(json.dumps({"schema": 1, "signature": signature})),
        )

    @classmethod
    def load(cls, path, *, signature):
        with np.load(path, allow_pickle=False) as data:
            metadata = json.loads(str(data["metadata"]))
            if metadata != {"schema": 1, "signature": signature}:
                raise ValueError("Artefato incompatível com encoder/schema.")
            return cls(data["skus"].tolist(), data["weights"], data["references"], data["classes"])
