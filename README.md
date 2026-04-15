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
- `POST /v1/conversations`
- `GET /v1/conversations`
- `GET /v1/conversations/{conversation_id}`
- `POST /v1/conversations/{conversation_id}/messages`
- `POST /v1/uploads/presign`
- `GET /v1/usage/summary`
- `GET /v1/usage/events`
- `GET /playground`

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
- Set `DYNAMODB_TABLE_NAME` to a DynamoDB table for persistent conversation threads.
- `AWS_REGION` controls the DynamoDB region, and `DYNAMODB_ENDPOINT_URL` is optional for local DynamoDB testing.
- Set `S3_BUCKET_NAME` to enable presigned uploads for image/file attachments.
- `S3_UPLOAD_PREFIX` controls the object key prefix, and `S3_PRESIGN_TTL_SECONDS` controls upload URL expiry.
- `MOCK_OPENAI=true` enables deterministic local responses.
- `/v1/agent/chat` now uses a LangChain tool-calling agent when mock mode is disabled.
- `/v1/conversations/*` stores separate multi-round conversations so each tab can keep its own history and resume later.
- `/v1/uploads/presign` returns presigned S3 upload URLs and attachment parts that can be stored in DynamoDB-backed messages.
- `/playground` provides a small local UI for testing conversation creation plus image/file uploads through the presign flow.
- `OPENAI_MODEL` defaults to `gpt-5.4-mini`.
- The job store and usage store are in-memory for now.
