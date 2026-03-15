FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"


FROM base AS build

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY data_collector/ ./data_collector/
RUN uv build --wheel && pip install dist/*.whl


FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.source=https://github.com/melvyndekort/network-monitor

COPY --from=build /venv /venv

ENV PATH="/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

CMD ["python3", "-m", "data_collector.main"]
