"""
Aplicação FastAPI — Fazenda Estreito Ponte de Pedra
Ponto de entrada principal.
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from fazenda.auth import exigir_modulo, exigir_modulo_qualquer, get_current_user, seed_admin
from fazenda.database import create_db_and_tables, engine
from fazenda.api.routers import (
    agenda,
    alimentacao,
    animais,
    aprovacoes,
    assistente,
    auth,
    baixas,
    cadastro,
    compra_animal,
    estoque,
    exclusoes,
    farmacia,
    financeiro,
    importar,
    indicadores,
    lotes,
    movimentacoes,
    notificacoes,
    parametros,
    producao,
    recria,
    relatorios,
    reproducao,
    sanidade,
    telegram,
    upload,
)
from fazenda.api.routers.telegram import registrar_webhook_telegram
from fazenda.api.routers.movimentacoes import seed_motivos_movimentacao
from fazenda.api.routers.financeiro import seed_parametros_financeiros, normalizar_plano_contas, normalizar_centros_custo
from fazenda.api.routers.reproducao import deduplicar_partos
from fazenda.api.routers.cadastro import (
    seed_cadastro_sanitario, seed_motivos_baixa, seed_pessoas, seed_servicos, seed_semen_categorias,
    seed_estoque_semen_inicial, configurar_calendario_sanitario_padrao, atualizar_estoque_semen_202607,
    seed_protocolos_inducao_lactacao, seed_tipos_metodos_servico, seed_protocolos_sanitarios_curativos,
)
from fazenda.api.routers.recria import seed_recria
from fazenda.api.routers.agenda import seed_lembrete_touros
from fazenda.rules.farmacia import bootstrap_farmacia
from fazenda.rules.touros import bootstrap_touros_naab


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cria tabelas e garante o admin inicial e os dados padrão (idempotente)."""
    create_db_and_tables()
    with Session(engine) as session:
        seed_admin(session)
        seed_motivos_movimentacao(session)
        seed_parametros_financeiros(session)
        normalizar_plano_contas(session)
        normalizar_centros_custo(session)
        deduplicar_partos(session)
        seed_pessoas(session)
        seed_cadastro_sanitario(session)
        # Calendário sanitário padrão (vacinas/exames sazonais e por fase
        # fisiológica) — idempotente, só cria/compatibiliza o que falta.
        configurar_calendario_sanitario_padrao(session)
        seed_motivos_baixa(session)
        seed_servicos(session)
        # Tipos de serviço (Cobertura/IA) e métodos (Monta Natural/IA em cio
        # natural/IATF) — vocabulário do lançamento de Serviço/Inseminação.
        seed_tipos_metodos_servico(session)
        seed_semen_categorias(session)
        seed_estoque_semen_inicial(session)
        atualizar_estoque_semen_202607(session)
        # Protocolo de indução de lactação (18 e 28 dias) — cronograma por
        # princípio ativo, editável depois em Configurações > Cadastro.
        seed_protocolos_inducao_lactacao(session)
        # Protocolos sanitários curativos (mastite, pós-parto/retenção de
        # placenta, pneumonia, diarreia) das planilhas do produtor.
        seed_protocolos_sanitarios_curativos(session)
        # Farmácia: catálogo de princípios ativos/marcas + compatibilização do
        # estoque já existente (idempotente, sem perda de dados).
        bootstrap_farmacia(session)
        # Recria: metas, curva de peso-alvo e janelas de ponto crítico padrão.
        seed_recria(session)
        # Catálogo NAAB completo (Alta Genetics) empacotado no repo — carrega
        # uma única vez, sem depender de upload manual do usuário.
        bootstrap_touros_naab(session)
        # Lembrete admin (a cada 3 meses) para importar o catálogo de touros NAAB.
        seed_lembrete_touros(session)
    # Aponta o Telegram para o nosso webhook (só age se o bot estiver configurado).
    registrar_webhook_telegram()
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
# Importar dados (Configurações) reaproveita a mesma permissão do Upload CSV.
app.include_router(importar.router, dependencies=[Depends(exigir_modulo("upload"))])
app.include_router(agenda.router, dependencies=_protegido)
# Financeiro exige o módulo "financeiro" (usuário sem acesso recebe 403).
app.include_router(financeiro.router, dependencies=[Depends(exigir_modulo("financeiro"))])
app.include_router(indicadores.router, dependencies=_protegido)
app.include_router(parametros.router, dependencies=_protegido)
app.include_router(alimentacao.router, dependencies=_protegido)
app.include_router(producao.router, dependencies=_protegido)
app.include_router(reproducao.router, dependencies=_protegido)
app.include_router(relatorios.router, dependencies=[Depends(exigir_modulo("reproducao"))])
app.include_router(estoque.router, dependencies=_protegido)
app.include_router(farmacia.router, dependencies=_protegido)
app.include_router(sanidade.router, dependencies=_protegido)
app.include_router(recria.router, dependencies=_protegido)
# Cadastro de lotes/parâmetros vive em Configurações (mesmo módulo de "parametros").
app.include_router(lotes.router, dependencies=[Depends(exigir_modulo("parametros"))])
app.include_router(cadastro.router, dependencies=[Depends(exigir_modulo("parametros"))])
# Leitura do banco de touros: Rebanho > Touros também consulta este catálogo
# (módulo "rebanho"), então aceita "parametros" OU "rebanho" — só a listagem,
# não o cadastro/edição (que fica no router acima, exigindo "parametros").
app.include_router(cadastro.router_touros_leitura, dependencies=[Depends(exigir_modulo_qualquer("parametros", "rebanho"))])
app.include_router(movimentacoes.router, dependencies=[Depends(exigir_modulo("rebanho"))])
app.include_router(baixas.router, dependencies=[Depends(exigir_modulo("rebanho"))])
app.include_router(compra_animal.router, dependencies=[Depends(exigir_modulo("rebanho"))])
# Exclusões: qualquer usuário logado pode buscar/solicitar; excluir de fato,
# aprovar e rejeitar são restritos a administradores (gate por rota, dentro
# do próprio router — ver exclusoes.py).
app.include_router(exclusoes.router, dependencies=_protegido)
app.include_router(notificacoes.router, dependencies=_protegido)
# Telegram: webhook é público (o Telegram chama sem login; a segurança é o
# segredo do cabeçalho + a whitelist de chats liberados).
app.include_router(telegram.router)
# Aprovações: cada rota já exige admin (exigir_admin) internamente.
app.include_router(aprovacoes.router)
# Assistente Claude (protótipo): aberto a qualquer usuário logado — cada
# ferramenta interna é oferecida só conforme os módulos liberados dele.
app.include_router(assistente.router, dependencies=_protegido)


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
