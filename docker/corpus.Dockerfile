# Builds the TP-201 eval corpus for a dataset release (README, "Corpus release").
# Base image pinned by digest (python 3.13-slim-bookworm); libraries by uv.lock.
FROM python@sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72
RUN pip install --no-cache-dir uv==0.11.23
WORKDIR /repo
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY world ./world
ENV UV_LINK_MODE=copy
RUN uv sync --locked --no-dev
CMD ["uv", "run", "--locked", "--no-dev", "python", "-m", "traceq_dataset.render", "world/tp201.yaml", "world/tp202.yaml", "--out", "/out"]
