"""Loopback-only assisted demo. Inference never writes a receipt or chooses a price."""

import hashlib
import tempfile
import threading
import warnings
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from caixa_inteligente.demo.checkout import CheckoutError, CheckoutStore

MAX_BYTES = 25_000_000
MAX_PIXELS = 30_000_000


class Confirmation(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    sku: str = Field(min_length=1, max_length=128)


def create_app(infer, catalog, state_dir, samples=None):
    app = FastAPI(title="BIXDATA — demonstração assistida", docs_url=None, redoc_url=None)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )
    store = CheckoutStore(Path(state_dir) / "checkout.sqlite3", catalog)
    samples = {sample["id"]: sample for sample in (samples or [])}
    lock = threading.Lock()

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        origin = request.headers.get("origin")
        allowed = {f"http://{request.headers.get('host', '')}"}
        if origin and origin not in allowed:
            return JSONResponse({"detail": "Origem não autorizada."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; "
            "connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'"
        )
        return response

    @app.exception_handler(CheckoutError)
    async def checkout_error(request, error):
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.get("/", response_class=HTMLResponse)
    def home():
        return (Path(__file__).parent / "web/index.html").read_text(encoding="utf-8")

    @app.get("/api/health")
    def health():
        return {
            "status": "ready",
            "simulated": True,
            "mode": "assisted",
            "catalog_classes": len(catalog),
        }

    @app.get("/api/catalog")
    def products():
        return catalog

    @app.post("/api/sessions")
    def session():
        return {"session_id": store.create_session(), "simulated": True}

    @app.post("/api/sessions/{session_id}/close")
    def close(session_id: str):
        store.close_session(session_id)
        return {"closed": True}

    @app.get("/api/sessions/{session_id}/receipt")
    def receipt(session_id: str):
        result = store.receipt(session_id)
        return {**result, "lines": result["items"]}

    @app.get("/api/samples")
    def listed_samples():
        return [
            {"id": sample["id"], "name": sample["name"], "split": "test"}
            for sample in samples.values()
        ]

    @app.get("/api/samples/{sample_id}/image")
    def sample_image(sample_id: str):
        if sample_id not in samples:
            raise HTTPException(404, "Amostra inexistente.")
        return FileResponse(samples[sample_id]["path"], media_type="image/jpeg")

    def process(raw, session_id, event_id):
        # Validate session before spending GPU time. No image/path from the caller is trusted.
        store.receipt(session_id)
        with tempfile.TemporaryDirectory(prefix="caixa-") as directory:
            path = Path(directory) / "input.jpg"
            try:
                from io import BytesIO

                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(BytesIO(raw)) as source:
                        if source.width * source.height > MAX_PIXELS:
                            raise ValueError("Imagem excede 30 megapixels.")
                        image = ImageOps.exif_transpose(source).convert("RGB")
                        image.thumbnail((1600, 1600))
                        image.save(path, quality=95)
            except (
                UnidentifiedImageError,
                OSError,
                ValueError,
                Image.DecompressionBombError,
                Image.DecompressionBombWarning,
            ) as exc:
                raise HTTPException(422, "Imagem inválida ou acima do limite.") from exc
            if not lock.acquire(blocking=False):
                raise HTTPException(429, "Reconhecimento ocupado; tente novamente.")
            try:
                result = infer(path)
            finally:
                lock.release()
        sku = result.get("sku")
        # Every addition requires deliberate operator confirmation in this proof of concept.
        observation = store.observe(
            session_id, event_id, hashlib.sha256(raw).hexdigest(), sku, "review", ttl=180
        )
        return {
            **result,
            "event_id": event_id,
            "session_id": session_id,
            "decision": "review",
            "expires": observation["expires"],
            "simulated": True,
        }

    @app.post("/api/events")
    async def event(
        session_id: Annotated[str, Form(min_length=1, max_length=128)],
        event_id: Annotated[str, Form(min_length=1, max_length=128)],
        image: Annotated[UploadFile, File()],
    ):
        raw = await image.read(MAX_BYTES + 1)
        await image.close()
        if not raw or len(raw) > MAX_BYTES:
            raise HTTPException(413, "Envie uma imagem de até 25 MB.")
        return await run_in_threadpool(process, raw, session_id, event_id)

    @app.post("/api/events/{event_id}/confirm")
    def confirm(event_id: str, body: Confirmation):
        return store.commit(
            event_id, sku=body.sku, operator_confirmed=True, session_id=body.session_id
        )

    return app
