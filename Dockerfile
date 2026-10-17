FROM ghcr.io/astral-sh/uv:0.13.1 AS uv
FROM python:3.15.0-slim-bookworm

COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    TORCH_HOME=/app/.cache/torch \
    XFORMERS_DISABLED=1 \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev
ENTRYPOINT ["caixa"]
CMD ["--help"]
