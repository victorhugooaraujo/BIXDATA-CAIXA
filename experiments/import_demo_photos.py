"""Reproduce reviewed training crops directly from the user's original archive."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    from pillow_heif import register_heif_opener

    from caixa_inteligente.demo.dataset import prepare_archive

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True)
    args = parser.parse_args()
    register_heif_opener()
    annotations = json.loads((ROOT / "configs/demo-user-products.json").read_text(encoding="utf-8"))
    prepare_archive(args.zip, annotations, ROOT / "artifacts/demo-training")
    print("77 fotos importadas com hash, recortes e splits revisados.")


if __name__ == "__main__":
    main()
