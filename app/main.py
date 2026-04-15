from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes.agent import router as agent_router
from app.api.routes.conferences import router as conferences_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.health import router as health_router
from app.api.routes.papers import router as papers_router
from app.api.routes.usage import router as usage_router
from app.core.errors import AppError

app = FastAPI(title="Research AI Agent API Python", version="0.1.0")


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.message})


@app.exception_handler(Exception)
async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"error": str(exc)})


app.include_router(health_router)
app.include_router(agent_router)
app.include_router(conversations_router)
app.include_router(papers_router)
app.include_router(conferences_router)
app.include_router(usage_router)
