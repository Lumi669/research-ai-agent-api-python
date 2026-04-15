# Research AI Agent API Python

FastAPI port of the research AI agent API. This service is designed to be consumed by your existing TypeScript app.

## Features

- `GET /health`
- `POST /v1/papers/summarize`
- `POST /v1/papers/extract`
- `POST /v1/papers/read-pdf`
- `POST /v1/papers/compare-pdfs`
- `POST /v1/conferences/analyze`
- `POST /v1/conferences/analyze/jobs`
- `GET /v1/conferences/analyze/jobs/{job_id}`
- `POST /v1/agent/chat`
- `GET /v1/usage/summary`
- `GET /v1/usage/events`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

## Notes

- Protected endpoints require `x-api-key: <INTERNAL_API_KEY>`.
- `MOCK_OPENAI=true` enables deterministic local responses.
- `/v1/agent/chat` now uses a LangChain tool-calling agent when mock mode is disabled.
- `OPENAI_MODEL` defaults to `gpt-5.4-mini`.
- The job store and usage store are in-memory for now.
