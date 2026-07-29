"""
Aplicação FastAPI — Fazenda Estreito Ponte de Pedra
Ponto de entrada principal.
"""
import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from fazenda.auth import (
    bloquear_escrita_contador, exigir_contrato_ativo, exigir_modulo, exigir_modulo_contratado, exigir_modulo_qualquer,
    get_current_user, seed_admin, seed_email_dono_backfill, seed_email_dono_correcao_202607c,
    seed_permissao_publicar_dono,
)
from fazenda.database import create_db_and_tables, engine
from fazenda.api.routers import (
    agenda,
    alimentacao,
    animais,
    aprovacoes,
    asaas,
    assistente,
    auditoria,
    auth,
    baixas,
    cadastro,
    chamados,
    cobranca,
    cofre_acesso,
    compra_animal,
    compra_semen,
    consultores,
    documentos,
    estoque,
    exclusoes,
    farmacia,
    fazendas,
    financeiro,
    importar,
    indicadores,
    lotes,
    manual_fazenda,
    movimentacoes,
    news,
    notificacoes,
    painel_cowdata,
    parametros,
    pedidos,
    planejamento,
    portal,
    producao,
    push,
    recria,
    relatorio_acasalamento,
    relatorio_compra_venda_animal,
    relatorio_custo_hectare,
    relatorio_custo_producao,
    relatorio_custo_safra,
    relatorio_rastreabilidade_sanitaria,
    relatorios,
    reproducao,
    safra,
    sanidade,
    cobranca,
    telegram,
    upload,
    venda_animal,
    zapsign,
)
from fazenda.api.routers.telegram import registrar_webhook_telegram
from fazenda.api.routers.movimentacoes import seed_motivos_movimentacao
from fazenda.api.routers.financeiro import (
    seed_parametros_financeiros, normalizar_plano_contas, normalizar_centros_custo, classificar_natureza_plano_contas,
    seed_tipos_documento_formas_pagamento, seed_centro_custo_agricultura,
)
from fazenda.api.routers.reproducao import deduplicar_partos, backfill_categoria_crias, backfill_numero_cria_partos
from fazenda.api.routers.cadastro import (
    seed_cadastro_sanitario, seed_motivos_baixa, seed_motivos_venda, seed_pessoas, seed_pessoa_robo_milknews,
    seed_servicos, seed_semen_categorias,
    seed_estoque_semen_inicial, configurar_calendario_sanitario_padrao, atualizar_estoque_semen_202607,
    seed_protocolos_inducao_lactacao, seed_tipos_metodos_servico, seed_protocolos_sanitarios_curativos, seed_racas_grau_sangue,
    sindicar_conta_gerencial_estoque, seed_tipos_pessoa, seed_tipo_geral, seed_inducao_lactacao_ativos1_d0,
)
from fazenda.api.routers.estoque import sindicar_estoque_semen, backfill_estoque_semen_generico
from fazenda.api.routers.recria import seed_recria
from fazenda.api.routers.agenda import seed_lembrete_touros
from fazenda.api.routers.alimentacao import seed_alimentos
from fazenda.api.routers.news import (
    desligar_fontes_rss_e_apagar_noticias_202607, publicar_lotes_milknews, seed_fontes_news, seed_nota_capa_202607,
)
from fazenda.api.routers.painel_cowdata import seed_cowdata_empresa
from fazenda.rules.farmacia import bootstrap_farmacia
from fazenda.rules.touros import bootstrap_touros_naab
from fazenda.rules.parametros import seed_parametros
from fazenda.rules.backup import executar_backup_se_necessario
from fazenda.rules.manual_fazenda import enviar_manual_semanal_se_necessario
from fazenda.api.routers.push import despachar_agenda_do_dia, despachar_push_pendentes

# Confere a cada 6h se já passou 1 semana desde o último backup automático
# bem-sucedido (ver fazenda.rules.backup) — não uma tarefa agendada em
# horário fixo, então sobrevive normalmente a reinícios/deploys sem duplicar
# nem perder execuções (o estado de "quando foi o último" fica no banco).
_INTERVALO_VERIFICACAO_BACKUP_SEGUNDOS = 6 * 3600

# Varredura periódica do push (Web Push): cobre o caso de ninguém estar com
# o app aberto no momento em que um alerta passa a valer (ex.: conta que
# vence hoje) — sem isso, o rewire em notificacoes.py só dispara push quando
# alguém efetivamente consulta o sino. Reaproveita 100% a mesma função de
# decisão (montar_itens_notificacoes); só itera usuários com subscription.
_INTERVALO_DESPACHO_PUSH_SEGUNDOS = 30 * 60

# Checa a cada 30 min se é segunda-feira depois das 7h e o Manual da Fazenda
# semanal ainda não foi enviado nesta semana ISO (ver
# fazenda.rules.manual_fazenda.deve_enviar_manual_semanal) — mesmo espírito
# do backup automático (estado "já enviei essa semana?" fica no banco, não
# depende de um agendador externo em horário fixo).
_INTERVALO_VERIFICACAO_MANUAL_SEMANAL_SEGUNDOS = 30 * 60


async def _loop_backup_automatico() -> None:
    while True:
        try:
            with Session(engine) as session:
                executar_backup_se_necessario(session)
        except Exception:
            pass  # nunca deixa essa tarefa de fundo derrubar o resto da aplicação
        await asyncio.sleep(_INTERVALO_VERIFICACAO_BACKUP_SEGUNDOS)


async def _loop_despacho_push() -> None:
    while True:
        try:
            with Session(engine) as session:
                despachar_push_pendentes(session)
                # "Agenda do dia": resumo 1x/dia (não 1 push por item) — dedup
                # por usuário+dia em despachar_agenda_do_dia já evita reenvio
                # a cada volta deste mesmo loop de 30 min.
                despachar_agenda_do_dia(session)
        except Exception:
            pass  # nunca deixa essa tarefa de fundo derrubar o resto da aplicação
        await asyncio.sleep(_INTERVALO_DESPACHO_PUSH_SEGUNDOS)


async def _loop_manual_fazenda_semanal() -> None:
    while True:
        try:
            with Session(engine) as session:
                enviar_manual_semanal_se_necessario(session)
        except Exception:
            pass  # nunca deixa essa tarefa de fundo derrubar o resto da aplicação
        await asyncio.sleep(_INTERVALO_VERIFICACAO_MANUAL_SEMANAL_SEGUNDOS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cria tabelas e garante o admin inicial e os dados padrão (idempotente)."""
    create_db_and_tables()
    with Session(engine) as session:
        seed_admin(session)
        seed_email_dono_backfill(session)
        seed_email_dono_correcao_202607c(session)
        seed_motivos_movimentacao(session, fazenda_id=1)
        seed_parametros_financeiros(session)
        seed_tipos_documento_formas_pagamento(session)
        normalizar_plano_contas(session)
        # Classificação padrão (serviço/produto/ambos) por palavra-chave —
        # só preenche onde ainda está vazio, nunca sobrescreve edição manual.
        classificar_natureza_plano_contas(session)
        normalizar_centros_custo(session)
        # Centro de custo "Agricultura" (Opção A do plano de custo agrícola —
        # ver models.Safra) — já serve qualquer fazenda que planta para a
        # própria produção de leite (decisão do usuário).
        seed_centro_custo_agricultura(session)
        deduplicar_partos(session)
        backfill_categoria_crias(session)
        backfill_numero_cria_partos(session)
        seed_tipos_pessoa(session, fazenda_id=1)
        # "Geral" libera Portal > Comunicação > Delegar tarefa (#515) a quem não
        # tem um papel técnico específico (Veterinário/Zootecnista) nem é admin.
        seed_tipo_geral(session, fazenda_id=1)
        seed_pessoas(session)
        # Identidade de cadastro para o robô de automação (Telegram/MilkNews) —
        # permite vincular um usuário de sistema a essa pessoa, como qualquer outra.
        seed_pessoa_robo_milknews(session, fazenda_id=1)
        seed_cadastro_sanitario(session)
        # Calendário sanitário padrão (vacinas/exames sazonais e por fase
        # fisiológica) — idempotente, só cria/compatibiliza o que falta.
        configurar_calendario_sanitario_padrao(session)
        seed_motivos_baixa(session, fazenda_id=1)
        seed_motivos_venda(session, fazenda_id=1)
        seed_servicos(session)
        seed_racas_grau_sangue(session, fazenda_id=1)
        # Tipos de serviço (Cobertura/IA) e métodos (Monta Natural/IA em cio
        # natural/IATF) — vocabulário do lançamento de Serviço/Inseminação.
        seed_tipos_metodos_servico(session, fazenda_id=1)
        seed_semen_categorias(session, fazenda_id=1)
        seed_estoque_semen_inicial(session, fazenda_id=1)
        atualizar_estoque_semen_202607(session, fazenda_id=1)
        # Protocolo de indução de lactação (18 e 28 dias) — cronograma por
        # princípio ativo, editável depois em Configurações > Cadastro.
        seed_protocolos_inducao_lactacao(session)
        # Padronização em D0 (jul/2026): quem já tinha o protocolo "Ativos 1"
        # em D1..D28 (dia_inicial=1) de um deploy anterior é renumerado para
        # D0..D27 (dia_inicial=0), mesmas datas de aplicação.
        seed_inducao_lactacao_ativos1_d0(session)
        # Protocolos sanitários curativos (mastite, pós-parto/retenção de
        # placenta, pneumonia, diarreia) das planilhas do produtor.
        seed_protocolos_sanitarios_curativos(session)
        # Farmácia: catálogo de princípios ativos/marcas + compatibilização do
        # estoque já existente (idempotente, sem perda de dados).
        bootstrap_farmacia(session)
        # Recria: metas, curva de peso-alvo e janelas de ponto crítico padrão.
        seed_recria(session, fazenda_id=1)
        # Catálogo NAAB completo (Alta Genetics) empacotado no repo — carrega
        # uma única vez, sem depender de upload manual do usuário.
        bootstrap_touros_naab(session)
        # Lembrete admin (a cada 3 meses) para importar o catálogo de touros NAAB.
        seed_lembrete_touros(session)
        # Parâmetros da fazenda — só cria as chaves que ainda não existem
        # (nunca sobrescreve um valor já editado pela UI de Parâmetros).
        seed_parametros(session)
        # Categorias de alimento (Volumoso/Concentrado/Mineral) + cadastro de
        # Alimento — vinculado automaticamente a itens de Estoque de mesmo
        # nome, quando existirem.
        seed_alimentos(session, fazenda_id=1)
        # News: 3 fontes nacionais + 2 internacionais de jornalismo sobre
        # pecuária leiteira — editável depois em Configurações > News (admin).
        seed_fontes_news(session)
        # Decisão do usuário (jul/2026): desliga essas 5 fontes RSS e apaga o
        # que já tinha sido importado — a aba News passa a ser alimentada só
        # pelo robô agendado /milknews, sob aprovação do administrador.
        desligar_fontes_rss_e_apagar_noticias_202607(session)
        # Publica os lotes novos do robô agendado /milknews (MILKNEWS_LOTES) —
        # cada lote roda uma única vez, sob a fonte manual "robô Milknews".
        publicar_lotes_milknews(session)
        # Nota informativa na Capa para o produtor (jul/2026) — editável só
        # pelo dono da plataforma depois disso.
        seed_nota_capa_202607(session)
        # O proprietário já nasce com permissão de publicar matérias no blog
        # (ele já usa essa função hoje); todos os demais usuários começam sem
        # essa permissão, por padrão (uma única vez, ver seed_permissao_publicar_dono).
        seed_permissao_publicar_dono(session)
        # Compatibiliza cada item de estoque sem conta gerencial padrão com a
        # conta correspondente (a partir da finalidade) — só preenche o que
        # está vazio, nunca sobrescreve um vínculo já feito manualmente.
        sindicar_conta_gerencial_estoque(session)
        # Painel Mestre CowData: fazenda "lógica" que ancora Equipe/Financeiro
        # da própria CowData (nunca uma fazenda-cliente — ver Fazenda.eh_empresa_cowdata).
        seed_cowdata_empresa(session)
        # Vincula cada item de estoque genérico ao touro correspondente do
        # Estoque de Sêmen (por nome ou NAAB/código) — a partir daí, toda
        # entrada/saída deste item também atualiza as doses do touro.
        sindicar_estoque_semen(session)
        # Corrige o histórico: cria/atualiza o item de Estoque espelhado de
        # cada touro do Estoque de Sêmen (compras antigas nunca criavam esse
        # item — só apareciam em Rebanho > Touros > Sêmen).
        backfill_estoque_semen_generico(session)
    # Aponta o Telegram para o nosso webhook (só age se o bot estiver configurado).
    registrar_webhook_telegram()
    tarefa_backup = asyncio.create_task(_loop_backup_automatico())
    tarefa_push = asyncio.create_task(_loop_despacho_push())
    tarefa_manual_fazenda = asyncio.create_task(_loop_manual_fazenda_semanal())
    yield
    tarefa_backup.cancel()
    tarefa_push.cancel()
    tarefa_manual_fazenda.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await tarefa_backup
    with contextlib.suppress(asyncio.CancelledError):
        await tarefa_push
    with contextlib.suppress(asyncio.CancelledError):
        await tarefa_manual_fazenda


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


@app.middleware("http")
async def _carimbar_fazenda_atual(request, call_next):
    """Carimba a fazenda do token no contexto do request, para
    `fazenda.rules.parametros.get_param` saber de quem é o parâmetro sem
    receber fazenda_id em toda função de regra (ela é chamada de dezenas de
    funções puras). SEMPRE define — inclusive como None — para nenhum request
    herdar a fazenda de outro que rodou antes na mesma thread."""
    from fazenda.auth import _validar_token_payload
    from fazenda.rules.parametros import fazenda_atual

    fid = None
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        dados = _validar_token_payload(auth.split(" ", 1)[1])
        if dados:
            fid = dados.get("fid")
    token = fazenda_atual.set(fid)
    try:
        return await call_next(request)
    finally:
        fazenda_atual.reset(token)

# Auth (aberto) + rotas de dados (exigem login).
app.include_router(auth.router)
# Fazendas: gerencia os próprios contratos/planos — não leva a trava de
# módulo contratado (seria circular).
app.include_router(fazendas.router)
# Painel Mestre CowData: exigir_dono em cada endpoint (mesmo padrão de
# fazendas.router) — nunca a trava de módulo contratado (é a própria CowData).
app.include_router(painel_cowdata.router)
# Cofre de acesso: mesmo padrão exigir_dono — ver fazenda/api/routers/cofre_acesso.py.
app.include_router(cofre_acesso.router)
# Consultor (Fase 2C): produto independente, escopado por USUÁRIO (não por
# fazenda) — cada endpoint já tem sua própria trava interna (get_current_user
# nos públicos, exigir_consultor_ativo/exigir_dono nos demais); não faz
# sentido usar a trava de módulo contratado por fazenda aqui.
app.include_router(consultores.router)

_protegido = [Depends(get_current_user)]
# Trava por PLANO CONTRATADO (fazenda/tenant) — soma-se à permissão por
# usuário (exigir_modulo/exigir_modulo_qualquer) já usada abaixo. Token sem
# "fid" (legado) pula a checagem, como o resto do piloto de multi-fazenda —
# ver fazenda/auth.py::exigir_modulo_contratado/exigir_contrato_ativo.
_contrato_ativo = [Depends(exigir_contrato_ativo())]

app.include_router(animais.router, dependencies=_protegido + [Depends(exigir_modulo_contratado("rebanho"))])
# Upload/Importar CSV e áreas transversais (Agenda, Indicadores, Parâmetros)
# não pertencem a um módulo comercial específico — exigem só que a fazenda
# tenha ALGUM contrato ativo (Rebanho é obrigatório em todo plano).
app.include_router(upload.router, dependencies=_protegido + _contrato_ativo)
# Importar dados (Configurações) reaproveita a mesma permissão do Upload CSV.
app.include_router(importar.router, dependencies=[Depends(exigir_modulo("upload"))] + _contrato_ativo)
app.include_router(agenda.router, dependencies=_protegido + _contrato_ativo)
# Financeiro exige o módulo "financeiro" (usuário sem acesso recebe 403).
# bloquear_escrita_contador vem por último: o vínculo `contador` (Painel do
# Contador) já tem permissoes=["financeiro"] pelo cadastro normal do usuário
# — sem essa trava adicional, ele conseguiria escrever em qualquer endpoint
# destes 4 routers, não só ler (ver fazenda/auth.py::bloquear_escrita_contador).
app.include_router(financeiro.router, dependencies=[Depends(exigir_modulo("financeiro")), Depends(exigir_modulo_contratado("financeiro")), Depends(bloquear_escrita_contador())])
app.include_router(relatorio_custo_hectare.router, dependencies=[Depends(exigir_modulo("financeiro")), Depends(exigir_modulo_contratado("financeiro")), Depends(bloquear_escrita_contador())])
app.include_router(relatorio_custo_producao.router, dependencies=[Depends(exigir_modulo("financeiro")), Depends(exigir_modulo_contratado("financeiro")), Depends(bloquear_escrita_contador())])
app.include_router(relatorio_custo_safra.router, dependencies=[Depends(exigir_modulo("financeiro")), Depends(exigir_modulo_contratado("financeiro")), Depends(bloquear_escrita_contador())])
# Planejamento (Orçamento/Planejamento financeiro) é uma sub-aba de Financeiro
# na permissão do usuário, mas um módulo comercial PRÓPRIO no contrato (Silver
# não inclui, Gold/Diamond incluem — "financeiro completo"). Pedidos também é
# módulo próprio (não mexe em Estoque/Financeiro sozinho — só quando um
# lançamento/movimento é vinculado a ele).
app.include_router(planejamento.router, dependencies=[Depends(exigir_modulo("financeiro")), Depends(exigir_modulo_contratado("planejamento")), Depends(bloquear_escrita_contador())])
app.include_router(pedidos.router, dependencies=[Depends(exigir_modulo("pedidos")), Depends(exigir_modulo_contratado("pedidos"))])
# Arquivo fiscal-contábil (Documentos) — SEM bloquear_escrita_contador: o
# contador pode arquivar documentos livremente (decisão do usuário), só a
# escrita em Financeiro/Planejamento/Chamados fica atrás do cadeado.
app.include_router(documentos.router, dependencies=[Depends(exigir_modulo("financeiro")), Depends(exigir_modulo_contratado("financeiro"))])
# Chamados (suporte) — mesmo padrão de financeiro: contador só escreve
# (abrir chamado) com o cadeado destravado.
app.include_router(chamados.router, dependencies=[Depends(exigir_modulo("financeiro")), Depends(exigir_modulo_contratado("financeiro")), Depends(bloquear_escrita_contador())])
app.include_router(indicadores.router, dependencies=_protegido + _contrato_ativo)
app.include_router(parametros.router, dependencies=_protegido + _contrato_ativo)
app.include_router(manual_fazenda.router, dependencies=_protegido + _contrato_ativo)
app.include_router(alimentacao.router, dependencies=_protegido + [Depends(exigir_modulo_contratado("alimentacao"))])
app.include_router(producao.router, dependencies=_protegido + [Depends(exigir_modulo_contratado("produtivo"))])
app.include_router(reproducao.router, dependencies=_protegido + [Depends(exigir_modulo_contratado("reprodutivo"))])
app.include_router(relatorio_acasalamento.router, dependencies=_protegido + [Depends(exigir_modulo_contratado("reprodutivo"))])
app.include_router(relatorios.router, dependencies=[Depends(exigir_modulo("reproducao")), Depends(exigir_modulo_contratado("reprodutivo"))])
app.include_router(estoque.router, dependencies=_protegido + [Depends(exigir_modulo_contratado("estoque"))])
app.include_router(farmacia.router, dependencies=_protegido + [Depends(exigir_modulo_contratado("sanitario"))])
app.include_router(sanidade.router, dependencies=_protegido + [Depends(exigir_modulo_contratado("sanitario"))])
app.include_router(relatorio_rastreabilidade_sanitaria.router, dependencies=_protegido + [Depends(exigir_modulo_contratado("sanitario"))])
app.include_router(recria.router, dependencies=_protegido + [Depends(exigir_modulo_contratado("produtivo"))])
# Cadastro de lotes vive em Configurações (permissão "parametros"), mas é
# dado de Rebanho no contrato. Cadastro de Safra é módulo "agricultura".
# cadastro.router é um cadastro-base amplo (fornecedores, pessoas, tipos,
# serviços, farmácia...) usado por vários módulos comerciais ao mesmo tempo —
# fica com a trava transversal (contrato ativo), não um módulo específico.
app.include_router(lotes.router, dependencies=[Depends(exigir_modulo("parametros")), Depends(exigir_modulo_contratado("rebanho"))])
app.include_router(safra.router, dependencies=[Depends(exigir_modulo("parametros")), Depends(exigir_modulo_contratado("agricultura"))])
app.include_router(cadastro.router, dependencies=[Depends(exigir_modulo("parametros"))] + _contrato_ativo)
# Leitura do banco de touros: Rebanho > Touros também consulta este catálogo
# (módulo "rebanho"), então aceita "parametros" OU "rebanho" — só a listagem,
# não o cadastro/edição (que fica no router acima, exigindo "parametros").
app.include_router(cadastro.router_touros_leitura, dependencies=[Depends(exigir_modulo_qualquer("parametros", "rebanho")), Depends(exigir_modulo_contratado("rebanho"))])
app.include_router(movimentacoes.router, dependencies=[Depends(exigir_modulo("rebanho")), Depends(exigir_modulo_contratado("rebanho"))])
app.include_router(baixas.router, dependencies=[Depends(exigir_modulo("rebanho")), Depends(exigir_modulo_contratado("rebanho"))])
app.include_router(compra_animal.router, dependencies=[Depends(exigir_modulo("rebanho")), Depends(exigir_modulo_contratado("rebanho"))])
app.include_router(compra_semen.router, dependencies=[Depends(exigir_modulo("rebanho")), Depends(exigir_modulo_contratado("rebanho"))])
app.include_router(venda_animal.router, dependencies=[Depends(exigir_modulo("rebanho")), Depends(exigir_modulo_contratado("rebanho"))])
app.include_router(relatorio_compra_venda_animal.router, dependencies=[Depends(exigir_modulo("rebanho")), Depends(exigir_modulo_contratado("rebanho"))])
# Exclusões: qualquer usuário logado pode buscar/solicitar; excluir de fato,
# aprovar e rejeitar são restritos a administradores (gate por rota, dentro
# do próprio router — ver exclusoes.py).
app.include_router(exclusoes.router, dependencies=_protegido + _contrato_ativo)
app.include_router(notificacoes.router, dependencies=_protegido + _contrato_ativo)
# Push (Web Push API): GET /push/chave-publica é pública (o frontend precisa
# dela antes mesmo de terminar a inscrição); subscribe/unsubscribe exigem
# login internamente (ver fazenda/api/routers/push.py) — por isso este
# router NÃO leva a dependência _protegido global, igual news.router.
app.include_router(push.router)
app.include_router(portal.router, dependencies=_protegido + _contrato_ativo)
app.include_router(auditoria.router, dependencies=_protegido + _contrato_ativo)
# Telegram: webhook é público (o Telegram chama sem login; a segurança é o
# segredo do cabeçalho + a whitelist de chats liberados).
app.include_router(telegram.router)
# ZapSign: webhook também público (assinatura eletrônica do contrato CowData
# — ver fazenda/rules/zapsign.py) — segurança é o segredo na própria URL
# (ZapSign não documenta cabeçalho de assinatura própria).
app.include_router(zapsign.router)
# Cobrança (boleto/PIX via BB, ver fazenda/rules/banco_brasil.py): rotas de
# emissão já exigem exigir_dono internamente; o webhook de baixa é público
# (mesmo princípio do ZapSign acima), por isso o router não leva _protegido.
app.include_router(cobranca.router)
# Asaas (integração ativa, ver fazenda/rules/asaas.py): mesmo princípio —
# rotas de cobrança exigem exigir_dono internamente; webhook público,
# validado pelo próprio token (ASAAS_WEBHOOK_TOKEN) + reconfirmação na API.
app.include_router(asaas.router)
# Aprovações: cada rota já exige admin (exigir_admin) internamente — a fila
# de aprovação ainda não tem fazenda_id (gap conhecido), então não leva a
# trava de contrato ainda (evitaria ficar inconsistente com o resto do módulo).
app.include_router(aprovacoes.router)
# News: leitura (GET /news/) é pública — qualquer visitante lê o blog sem
# login; cada rota de gestão (cadastro de fontes, publicar/excluir/revisar
# matéria) já exige a permissão certa internamente (exigir_admin /
# exigir_pode_publicar) — por isso este router NÃO leva o _protegido global,
# nem a trava de contrato (o blog é compartilhado entre todas as fazendas).
app.include_router(news.router)
# Assistente Claude (protótipo): aberto a qualquer usuário logado — já
# restrito à fazenda #1 (FAZENDA_ID_PILOTO, ver assistente.py), então a trava
# de contrato aqui é redundante hoje, mas evita reabrir um buraco se essa
# restrição for removida antes do assistente virar um módulo comercial.
app.include_router(assistente.router, dependencies=_protegido + _contrato_ativo)


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
