"""Experimental image/text retrieval. Scores are not calibrated probabilities.

No automatic acceptance: this module only ranks candidates until a separate
calibration/open-set evaluation justifies a decision policy.
"""

import json
import math
import unicodedata
from collections import Counter
from pathlib import Path

from caixa_inteligente.vision import Candidate


def terms(text: str) -> Counter:
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(char for char in text if char.isalnum())
    # Character bigrams handle Latin tokens and Chinese without a tokenizer.
    return Counter(text[index : index + 2] for index in range(len(text) - 1))


class TextGallery:
    def __init__(self, references: list[dict], signature: str):
        if not references or not isinstance(signature, str) or not signature:
            raise ValueError("Galeria textual vazia ou sem assinatura.")
        self.references = references
        self.signature = signature
        frequency = Counter()
        for reference in references:
            if not isinstance(reference.get("sku"), str) or not reference["sku"].strip():
                raise ValueError("SKU textual inválido.")
            if not isinstance(reference.get("text"), str):
                raise ValueError("Texto de referência inválido.")
            if not isinstance(reference.get("sha256"), str) or len(reference["sha256"]) != 64:
                raise ValueError("Hash de referência inválido.")
            frequency.update(set(terms(reference["text"])))
        self.idf = {
            term: math.log((1 + len(references)) / (1 + count)) + 1
            for term, count in frequency.items()
        }
        self.vectors = [self._vector(ref["text"]) for ref in references]

    def _vector(self, text: str) -> dict[str, float]:
        vector = {
            term: count * self.idf[term] for term, count in terms(text).items() if term in self.idf
        }
        norm = math.sqrt(sum(value * value for value in vector.values()))
        return {term: value / norm for term, value in vector.items()} if norm else {}

    def rank(self, text: str) -> list[Candidate]:
        query = self._vector(text)
        scores = {}
        for reference, vector in zip(self.references, self.vectors, strict=True):
            score = sum(value * vector.get(term, 0) for term, value in query.items())
            scores[reference["sku"]] = max(scores.get(reference["sku"], 0), min(score, 1.0))
        return [
            Candidate(sku, score)
            for sku, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        ]

    def save(self, path: Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(
                {"schema": 1, "signature": self.signature, "references": self.references},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path, signature: str):
        contents = json.loads(Path(path).read_text(encoding="utf-8"))
        if contents.get("schema") != 1 or contents.get("signature") != signature:
            raise ValueError("Galeria textual incompatível; reconstrua o índice.")
        return cls(contents["references"], signature)


def fuse(visual: list[Candidate], textual: list[Candidate], text_weight: float = 0.2):
    if not math.isfinite(text_weight) or not 0 <= text_weight <= 1:
        raise ValueError("Peso textual deve estar entre 0 e 1.")
    visual_scores = {candidate.sku: candidate.similarity for candidate in visual}
    text_scores = {candidate.sku: candidate.similarity for candidate in textual}
    if visual_scores.keys() != text_scores.keys():
        raise ValueError("Galerias visual e textual devem conter os mesmos SKUs.")
    # With no usable text there is no additional evidence; preserve visual ranking.
    if not any(text_scores.values()):
        text_weight = 0.0
    candidates = [
        {
            "sku": sku,
            "visual_score": score,
            "text_score": text_scores[sku],
            "score": (1 - text_weight) * score + text_weight * text_scores[sku],
        }
        for sku, score in visual_scores.items()
    ]
    return sorted(candidates, key=lambda candidate: (-candidate["score"], candidate["sku"]))
