"""Prepare OCR evidence without using labels for fitting or indexing."""

import argparse
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from caixa_inteligente.cli import image_samples  # noqa: E402
from caixa_inteligente.ocr import OcrReader  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=Path(".cache/ocr-rpc-v1"))
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    args = parser.parse_args()
    samples = image_samples(args.images)
    local = threading.local()

    def process(sample):
        if not hasattr(local, "reader"):
            local.reader = OcrReader(args.cache)
        return bool(local.reader.read(sample[1])["lines"])

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = []
        for index, result in enumerate(pool.map(process, samples), 1):
            results.append(result)
            if index % 100 == 0:
                print(f"OCR: {index}/{len(samples)}", flush=True)
    print(f"Imagens: {len(results)}; com linhas detectadas: {sum(results)}")


if __name__ == "__main__":
    main()
