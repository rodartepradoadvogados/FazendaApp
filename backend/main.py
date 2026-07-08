"""
Aplicação FastAPI — Fazenda Estreito Ponte de Pedra
Ponto de entrada principal.
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from fazenda.auth import exigir_modulo, get_current_user, seed_admin
from fazenda.database import create_db_and_tables, engine
from fazenda.api.routers import (
    agenda,
    alimentacao,
    animais,
    auth,
    estoque,
    exclusoes,
    financeiro,
    indicadores,
    lotes,
    movimentacoes,
    notificacoes,
    parametros,
    producao,
    reproducao,
    sanidade,
    upload,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cria tabelas e garante o admin inicial (idempotente)."""
    create_db_and_tables()
    with Session(engine) as session:
        seed_admin(session)
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

# Auth (aberto) + rotas de dados (exigem login).
app.include_router(auth.router)

_protegido = [Depends(get_current_user)]
app.include_router(animais.router, dependencies=_protegido)
app.include_router(upload.router, dependencies=_protegido)
app.include_router(agenda.router, dependencies=_protegido)
# Financeiro exige o módulo "financeiro" (usuário sem acesso recebe 403).
app.include_router(financeiro.router, dependencies=[Depends(exigir_modulo("financeiro"))])
app.include_router(indicadores.router, dependencies=_protegido)
app.include_router(parametros.router, dependencies=_protegido)
app.include_router(alimentacao.router, dependencies=_protegido)
app.include_router(producao.router, dependencies=_protegido)
app.include_router(reproducao.router, dependencies=_protegido)
app.include_router(estoque.router, dependencies=_protegido)
app.include_router(sanidade.router, dependencies=_protegido)
# Cadastro de lotes/parâmetros vive em Configurações (mesmo módulo de "parametros").
app.include_router(lotes.router, dependencies=[Depends(exigir_modulo("parametros"))])
app.include_router(movimentacoes.router, dependencies=[Depends(exigir_modulo("rebanho"))])
# Exclusões: qualquer usuário logado pode buscar/solicitar; excluir de fato,
# aprovar e rejeitar são restritos a administradores (gate por rota, dentro
# do próprio router — ver exclusoes.py).
app.include_router(exclusoes.router, dependencies=_protegido)
app.include_router(notificacoes.router, dependencies=_protegido)


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
