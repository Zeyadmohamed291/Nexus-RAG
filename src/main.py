import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from routes import base, data, nlp
from helpers.config import get_settings
from stores.llm.LLMProviderFactory import LLMProviderFactory
from stores.vectordb.VectorDBProviderFactory import VectorDBProviderFactory
from stores.llm.templates.template_parser import TemplateParser
from utils.metrics import setup_metrics

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Modern lifespan context manager managing startup and shutdown resource lifecycles:
    - Creates async PostgreSQL SQLAlchemy engine and session factory
    - Instantiates multi-backend LLM and Vector DB provider clients
    - Connects to vector database and compiles localized prompt templates
    - Performs clean, non-blocking asynchronous resource disposal on application termination
    """
    settings = get_settings()

    postgres_conn = (
        f"postgresql+asyncpg://{settings.POSTGRES_USERNAME}:{settings.POSTGRES_PASSWORD}@"
        f"{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_MAIN_DATABASE}"
    )

    logger.info(f"Initializing NexusRAG backend: Generation={settings.GENERATION_BACKEND}, VectorDB={settings.VECTOR_DB_BACKEND}")

    # Database engine and sessionmaker
    app.db_engine = create_async_engine(postgres_conn)
    app.db_client = sessionmaker(
        app.db_engine, class_=AsyncSession, expire_on_commit=False
    )

    # Provider factories
    llm_provider_factory = LLMProviderFactory(settings)
    vectordb_provider_factory = VectorDBProviderFactory(config=settings, db_client=app.db_client)

    # Generation client
    app.generation_client = llm_provider_factory.create(provider=settings.GENERATION_BACKEND)
    app.generation_client.set_generation_model(model_id=settings.GENERATION_MODEL_ID)

    # Embedding client
    app.embedding_client = llm_provider_factory.create(provider=settings.EMBEDDING_BACKEND)
    app.embedding_client.set_embedding_model(
        model_id=settings.EMBEDDING_MODEL_ID,
        embedding_size=settings.EMBEDDING_MODEL_SIZE
    )

    # Vector DB client
    app.vectordb_client = vectordb_provider_factory.create(provider=settings.VECTOR_DB_BACKEND)
    await app.vectordb_client.connect()

    # Template parser
    app.template_parser = TemplateParser(
        language=settings.PRIMARY_LANG,
        default_language=settings.DEFAULT_LANG,
    )

    yield

    # Clean asynchronous shutdown
    logger.info("NexusRAG shutting down: disposing database and vector store connections...")
    if hasattr(app, "db_engine") and app.db_engine:
        await app.db_engine.dispose()

    if hasattr(app, "vectordb_client") and app.vectordb_client:
        await app.vectordb_client.disconnect()


settings = get_settings()

app = FastAPI(
    title="NexusRAG API",
    description="Enterprise-Ready Asynchronous Retrieval-Augmented Generation (RAG) Platform",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Enable Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus and Grafana metrics instrumentation
setup_metrics(app)

# Static file serving & Web UI
static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", include_in_schema=False)
async def serve_ui():
    """Serve the NexusRAG interactive chat application."""
    index_path = static_dir / "index.html"
    if index_path.is_file():
        return FileResponse(str(index_path))
    return JSONResponse(
        content={
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "message": "NexusRAG API is running. UI not found in /static."
        }
    )


# Register modular routers
app.include_router(base.base_router)
app.include_router(data.data_router)
app.include_router(nlp.nlp_router)
