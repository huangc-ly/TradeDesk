from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import db
from app.api.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: connect to DuckDB
    db.connect()
    yield
    # Shutdown: close DuckDB connection
    db.close()


app = FastAPI(
    title=settings.app_name,
    docs_url="/docs",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(api_router, prefix="/api")


@app.get("/health")
async def health_check():
    return {"status": "ok"}
