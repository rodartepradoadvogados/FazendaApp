"""
Aplicação FastAPI — Fazenda Estreito Ponte de Pedra
Ponto de entrada principal.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fazenda.database import create_db_and_tables
from fazenda.api.routers import (
    agenda,
    alimentacao,
    animais,
    estoque,
    financeiro,
    indicadores,
    parametros,
    producao,
    reproducao,
    sanidade,
    upload,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cria tabelas ao iniciar (idempotente)."""
    create_db_and_tables()
    yield


app = FastAPI(
    title="Fazenda Estreito Ponte de Pedra — API",
    description="Backend para gestão de fazenda leiteira Girolando/Holandês",
    version="1.0.0",
    lifespan=lifespan,
)

import os

# Origens permitidas: localhost (dev) + produção (Railway/Vercel)
_origins_env = os.getenv("ALLOWED_ORIGINS", "")
_extra = [o.strip() for o in _origins_env.split(",") if o.strip()]
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    *_extra,
]

# Libera também as URLs de preview do Vercel (fazenda-app-*.vercel.app,
# incluindo os deploys de branch: <projeto>-git-<hash>-<time>.vercel.app).
_VERCEL_PREVIEW_REGEX = r"^https://fazenda-?app[a-z0-9-]*\.vercel\.app$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=_VERCEL_PREVIEW_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(animais.router)
app.include_router(upload.router)
app.include_router(agenda.router)
app.include_router(financeiro.router)
app.include_router(indicadores.router)
app.include_router(parametros.router)
app.include_router(alimentacao.router)
app.include_router(producao.router)
app.include_router(reproducao.router)
app.include_router(estoque.router)
app.include_router(sanidade.router)


@app.get("/")
def root():
    return {
        "app": "Fazenda Estreito Ponte de Pedra",
        "versao": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
