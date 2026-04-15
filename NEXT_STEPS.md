# Next Steps

This repo is in a good hybrid state already: it has real agent-style chat plus workflow-style AI endpoints. The best next work is to make the system more reliable, more structured for frontend rendering, and better at multi-paper analysis.

## Priority 1

### 1. Confirm frontend rendering contract

- Make sure the Next.js frontend always renders `message.parts` first, not only `message.content`.
- Support these part types consistently:
  - `text`
  - `table`
  - `image`
  - `file`
- Add one frontend test for assistant table rendering and one for attachment rendering.

### 2. Improve agent output structure

- Add stronger prompt rules so research comparison outputs are returned in structured sections.
- Prefer returning `table` parts for comparison-style answers when possible.
- Decide which outputs should be:
  - plain conversational text
  - structured `parts`
  - fixed workflow JSON

### 3. Add better observability

- Expose active provider/mode clearly in logs and health checks.
- Add request-level logging for:
  - conversation id
  - job id
  - provider
  - model
  - tool usage
- Add clearer error messages for OpenAI/tool failures.

## Priority 2

### 4. Strengthen conversation jobs

- Persist conversation message jobs instead of keeping them only in memory.
- Add job cleanup/retention policy.
- Add job status history if users need auditability.
- Consider resumable polling behavior from the frontend.

### 5. Make cancellation more robust

- Current cancellation is real at the app level, but provider interruption is still best-effort.
- Review long-running tool calls and add cancellation checks where practical.
- Document which operations are:
  - immediately cancelable
  - best-effort cancelable
  - non-cancelable once started

### 6. Expand automated tests

- Add backend tests for:
  - conversation creation
  - message posting with attachments
  - table-part generation
  - job cancellation
  - OpenAI-mode request compatibility
- Add frontend tests for:
  - upload flow
  - table rendering
  - disabled submit while processing

## Priority 3

### 7. Add RAG for multi-paper analysis

RAG is the next major upgrade if the product focus is comparing many papers or answering repeated questions over uploaded research documents.

Suggested shape:

1. Extract PDF text
2. Chunk text
3. Generate embeddings
4. Store embeddings with metadata
5. Retrieve top-k chunks per user query
6. Use retrieval results in workflow endpoints and agent chat

Important metadata:

- paper title
- source URL or S3 key
- page number if available
- section/chunk id
- upload/conversation id

### 8. Add a dedicated multi-paper workflow

Instead of relying only on free-form chat, add a workflow endpoint for:

- analyze 5 to 20 papers
- summarize each paper
- extract novelty
- extract achievements
- compare themes
- rank promising directions
- return a final table plus summary

This will likely be more reliable than letting the generic agent do everything through one chat prompt.

## Suggested Delivery Order

1. Finish frontend rendering and tests for `message.parts`
2. Add backend tests for structured assistant outputs
3. Persist jobs and improve cancellation behavior
4. Add a multi-paper workflow endpoint
5. Add light RAG for uploaded paper retrieval

## Short Product Guidance

- Use workflows for repeatable tasks like summarize/extract/compare.
- Use the agent for flexible research chat and tool selection.
- Use RAG when document count and context size start to grow.

