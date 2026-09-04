FROM python:3.12.7-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY pyproject.toml .
COPY engine engine
COPY agents agents
COPY audit audit
COPY config config
COPY domain domain
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
CMD ["uvicorn", "engine.run_api:app", "--host", "0.0.0.0", "--port", "8100"]
