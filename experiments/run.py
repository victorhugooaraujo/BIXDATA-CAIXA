"""Run the same application source with isolated CUDA/OCR dependencies."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("TORCH_HOME", str(ROOT / ".cache" / "torch"))

if __name__ == "__main__":
    from caixa_inteligente.cli import main

    raise SystemExit(main())
