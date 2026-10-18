"""Exercise CUDA kernels, rather than relying on the driver version string."""

import json
import time

import torch

if not torch.cuda.is_available():
    raise SystemExit("CUDA indisponível neste ambiente.")
started = time.perf_counter()
device = torch.cuda.get_device_properties(0)
with torch.inference_mode():
    tensor = torch.randn((512, 512), device="cuda")
    product = tensor @ tensor.T
    assert torch.isfinite(product).all().item()
    attention_input = torch.randn((1, 4, 64, 64), device="cuda")
    attention = torch.nn.functional.scaled_dot_product_attention(
        attention_input, attention_input, attention_input
    )
    assert torch.isfinite(attention).all().item()
torch.cuda.synchronize()
print(
    json.dumps(
        {
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "gpu": device.name,
            "compute_capability": list(torch.cuda.get_device_capability()),
            "total_vram_bytes": device.total_memory,
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "kernel_test_seconds": round(time.perf_counter() - started, 3),
            "matrix_multiply": "passed",
            "attention": "passed",
        },
        indent=2,
    )
)
