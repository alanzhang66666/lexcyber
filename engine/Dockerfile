FROM python:3.12.7-slim
WORKDIR /app
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL}
COPY pyproject.toml .
COPY engine engine
COPY agents agents
COPY audit audit
COPY config config
COPY graph graph
COPY models models
COPY prompts prompts
COPY retrieval retrieval
COPY skill_runtime skill_runtime
COPY skills skills
COPY storage storage
COPY tools tools
RUN pip install --no-cache-dir .
EXPOSE 8100
CMD ["uvicorn", "engine.run_api_v03:app", "--host", "0.0.0.0", "--port", "8100"]
