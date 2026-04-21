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
- Browser uploads to S3 need bucket CORS that allows your frontend origin to send `PUT` requests with `Content-Type`.
  Example S3 CORS configuration:
  ```json
  [
    {
      "AllowedHeaders": ["Content-Type", "*"],
      "AllowedMethods": ["PUT", "GET", "HEAD"],
      "AllowedOrigins": ["http://localhost:8000", "http://localhost:3000"],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 3000
    }
  ]
  ```
  Replace the example origins with the exact frontend URLs that will call the presigned upload URL.
- `MOCK_OPENAI=true` enables deterministic local responses.
- `/v1/agent/chat` now uses a LangChain tool-calling agent when mock mode is disabled.
- `AGENT_SYSTEM_PROMPT` lets you override the default research-agent system prompt without editing code.
- `/v1/conversations/*` stores separate multi-round conversations so each tab can keep its own history and resume later.
- Conversation messages may include structured `parts`, not just plain `content`. Assistant replies can now return markdown tables as `table` parts, for example:
  ```json
  {
    "role": "assistant",
    "content": null,
    "parts": [
      {
        "type": "table",
        "table": {
          "columns": ["Paper", "Key finding", "Worth pursuing?"],
          "rows": [
            ["VideoLLaMB", "Long-video understanding with recurrent memory", "Yes"],
            ["Principles of Visual Tokens", "More efficient video understanding", "Yes"],
            ["St4RTrack", "Joint 4D reconstruction and tracking", "Yes"]
          ]
        }
      }
    ]
  }
  ```
  Frontends should prefer rendering `message.parts` by type, especially `text`, `table`, `image`, and `file`.
- `/v1/uploads/presign` returns presigned S3 upload URLs and attachment parts that can be stored in DynamoDB-backed messages.
- `/playground` provides a small local UI for testing conversation creation plus image/file uploads through the presign flow.
- `OPENAI_MODEL` defaults to `gpt-5.4-mini`.
- The job store is in-memory for now.
