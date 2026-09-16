# Production Multi-Stage Dockerfile for agent-eval-harness
# Provides a secure, containerized environment for running agent evaluations and CI gates

FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir build && \
    python -m build --wheel

# Final production stage
FROM python:3.12-slim AS runner

LABEL org.opencontainers.image.title="agent-eval-harness" \
      org.opencontainers.image.description="A CI gate and evaluation harness for AI agents" \
      org.opencontainers.image.version="0.2.0" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    AEH_RUNS_DIR=/app/evals/runs \
    AEH_BASELINES_DIR=/app/evals/baselines \
    AEH_GATES_CONFIG=/app/configs/gates.yaml

WORKDIR /app

# Create a secure non-root user
RUN groupadd -g 10001 aeh && \
    useradd -u 10001 -g aeh -s /bin/bash -m aeh

# Install wheel from builder stage
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -rf /tmp/*.whl

# Copy repository assets (benchmarks, datasets, configs, evals, prompts)
COPY --chown=aeh:aeh benchmarks/ ./benchmarks/
COPY --chown=aeh:aeh datasets/ ./datasets/
COPY --chown=aeh:aeh configs/ ./configs/
COPY --chown=aeh:aeh evals/ ./evals/
COPY --chown=aeh:aeh prompts/ ./prompts/
COPY --chown=aeh:aeh Makefile QUICKSTART.md README.md ./

USER aeh

EXPOSE 8000

ENTRYPOINT ["agent-eval"]
CMD ["status"]
