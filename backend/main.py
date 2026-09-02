"""
Aplicação FastAPI — Fazenda Estreito Ponte de Pedra
Ponto de entrada principal.
"""
import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from fazenda.auth import (
    bloquear_escrita_contador, exigir_admin_ou_consultor_fazenda, exigir_contrato_ativo, exigir_modulo,
    exigir_modulo_contratado, exigir_modulo_qualquer, exigir_segredo_de_producao, get_current_user, seed_admin,
    seed_email_dono_backfill, seed_email_dono_correcao_202607c, seed_permissao_publicar_dono,
)
from fazenda.database import create_db_and_tables, engine, get_session
from fazenda.models import IdempotenciaChave
from fazenda.api.routers import (
    agenda,
    alertas_indicador,
    alimentacao,
    animais,
    aprovacoes,
    asaas,
    assistente,
    auditoria,
    auth,
    baixas,
    cadastro,
    cartao_credito,
    central_documentos,
    central_protocolos,
    chamados,
    cobranca,
    cofre_acesso,
    compra_animal,
    compra_semen,
    documentos,
    estoque,
    exclusoes,
    farmacia,
    fazendas,
    filtros_salvos,
    financeiro,
    formulacao_dietas,
    fotos,
    importar,
    indicadores,
    lida,
    lotes,
    manual_fazenda,
    movimentacoes,
    nao_conformidades,
    news,
    notificacoes,
    onboarding,
    painel_cowdata,
    painel_cowdata_cadastros,
    painel_cowdata_farmacia,
    painel_cowdata_parametros,
    painel_cowdata_usuarios,
    parametros,
    pedidos,
    planejamento,
    portal,
    producao,
    protocolos_customizados,
    push,
    recria,
    relatorio_acasalamento,
    relatorio_compra_semen,
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
from fazenda.api.routers.reproducao import (
    backfill_categoria_crias, backfill_fechar_servicos_abertos, backfill_numero_cria_partos, deduplicar_partos,
)
from fazenda.api.routers.cadastro import (
    seed_cadastro_sanitario, seed_motivos_baixa, seed_motivos_venda, seed_pessoas, seed_pessoa_robo_milknews,
    seed_servicos, seed_semen_categorias,
    seed_estoque_semen_inicial, configurar_calendario_sanitario_padrao, atualizar_estoque_semen_202607,
    seed_protocolos_inducao_lactacao, seed_tipos_metodos_servico, seed_protocolos_sanitarios_curativos, seed_racas_grau_sangue,
    sindicar_conta_gerencial_estoque, seed_tipos_pessoa, seed_tipo_geral, seed_tipos_papel_administrativo,
    seed_inducao_lactacao_ativos1_d0,
    seed_cadastros_estoque,
)
from fazenda.api.routers.estoque import (
    sindicar_estoque_semen, backfill_estoque_semen_generico, backfill_estoque_semen_fazenda_id,
    backfill_estoque_semen_duplicados_mesmo_tipo, backfill_estoque_semen_fazenda_para_convencional_nomeados,
)
from fazenda.api.routers.recria import seed_recria
from fazenda.api.routers.agenda import seed_lembrete_touros
from fazenda.api.routers.alimentacao import seed_alimentos
from fazenda.api.routers.news import (
    desligar_fontes_rss_e_apagar_noticias_202607, publicar_lotes_milknews, seed_fontes_news, seed_nota_capa_202607,
)
from fazenda.api.routers.painel_cowdata import seed_cowdata_empresa
from fazenda.rules.farmacia import bootstrap_farmacia
from fazenda.rules.recria_doenca import backfill_doenca_catalogo
from fazenda.rules.touros import bootstrap_touros_naab
from fazenda.rules.parametros import seed_parametros
from fazenda.rules.backup import executar_backup_se_necessario
from fazenda.rules.manual_fazenda import enviar_manual_semanal_se_necessario
from fazenda.rules.supabase_storage import garantir_buckets
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
    # Antes de qualquer coisa: recusa subir em produção assinando sessões com
    # o segredo público de desenvolvimento (ver fazenda/auth.py).
    exigir_segredo_de_producao()
    create_db_and_tables()
    # A suíte de testes cria ~1500 TestClient(main.app) — um por teste, cada
    # um disparando este lifespan inteiro. Os ~50 seeds abaixo bootstrapam um
    # banco de PRODUÇÃO vazio; testes que constroem seu próprio engine isolado
    # já semeiam exatamente as linhas que usam, então rodar os 50 de novo em
    # cada teste é puro custo (o que fazia a suíte levar ~57s/teste). A tabela
    # ainda é criada (create_db_and_tables acima) — só os SEEDS ficam de fora.
    if os.environ.get("FAZENDA_TESTING"):
        yield
        return
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
        backfill_fechar_servicos_abertos(session)
        backfill_numero_cria_partos(session)
        seed_tipos_pessoa(session, fazenda_id=1)
        # "Geral" libera Portal > Comunicação > Delegar tarefa (#515) a quem não
        # tem um papel técnico específico (Veterinário/Zootecnista) nem é admin.
        seed_tipo_geral(session, fazenda_id=1)
        # Backfill de Administrador/Contador (ago/2026) — cobre a fazenda #1
        # do piloto legado mesmo que o seed original já tenha rodado antes
        # desses dois tipos existirem (ver seed_tipos_papel_administrativo).
        seed_tipos_papel_administrativo(session, fazenda_id=1)
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
        # Vincula ao catálogo (Doenca) o texto livre já lançado em
        # OcorrenciaClinica/JanelaPontoCritico — casa por nome ou cria a
        # doença nova na fazenda dona do registro (ver decisão (b) do dono do
        # produto). Depois do bootstrap_farmacia (precisa do catálogo global
        # já semeado) e do seed_recria (que acabou de criar as janelas padrão).
        backfill_doenca_catalogo(session)
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
        # Cadastros de apoio ao item de estoque (categoria, finalidade,
        # unidade, unidade de embalagem, unidade de medida, local de
        # armazenamento) — Configurações > Cadastro > Estoque.
        seed_cadastros_estoque(session)
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
        # Corrige o histórico: o item de Estoque espelhado de sêmen (acima)
        # nascia sem fazenda_id (bug em sincronizar_item_estoque_semen) —
        # preenche a partir do EstoqueSemen vinculado nos itens legados.
        backfill_estoque_semen_fazenda_id(session)
        # Corrige o histórico: funde linhas de EstoqueSemen duplicadas (mesmo
        # touro, mesmo tipo, mesma fazenda — nunca cadastrado assim de
        # propósito) — precisa rodar ANTES do backfill nomeado abaixo, para
        # este ter só um candidato convencional/sexado por nome ao fundir.
        backfill_estoque_semen_duplicados_mesmo_tipo(session)
        # Corrige o histórico: Henessy/Heineken/Halle (confirmado pelo
        # produtor — só sêmen comprado, nunca touro de monta natural na
        # fazenda dele) apareciam também como tipo="fazenda" por engano.
        backfill_estoque_semen_fazenda_para_convencional_nomeados(session)
    # Cria (se ainda não existir) os buckets do Supabase Storage usados pelo
    # sistema — sem isso, um bucket novo (ex.: "fotos-campo") só existiria
    # depois de alguém criar manualmente pelo painel do Supabase.
    garantir_buckets()
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


# Folha de pagamento/RH mora hoje sob "/cadastro" (rh_folha.py, rh_contratos.py
# e rh_vale_item.py, todos montados dentro de fazenda.api.routers.cadastro),
# não sob "/financeiro" como o comentário antigo desta constante dizia —
# aquilo ficou desatualizado depois da divisão do cadastro.py monolítico
# (ver docstring de fazenda/api/routers/cadastro/__init__.py) e por isso uma
# sessão de suporte CowData conseguia ESCREVER folha, rescisão, férias, 13º,
# diária e vale de uma fazenda-cliente — só "/financeiro" estava na lista.
# Falha corrigida aqui (ver PR #132): listamos cada prefixo de RH sob
# "/cadastro" explicitamente, em vez de bloquear "/cadastro" inteiro (que
# também tem cadastros operacionais legítimos — raças, motivos, unidades de
# estoque etc. — que o suporte precisa poder ajustar).
_PREFIXOS_RH_MODO_SUPORTE = (
    "/cadastro/folha-pagamento",           # inclui /folha-pagamento/guias e /folha-pagamento/proporcional-admissao
    "/cadastro/folha-pagamento-unificada",  # ledger consolidado (rh_contratos.py) — só leitura, mas fica na lista por clareza
    "/cadastro/ferias",
    "/cadastro/decimo-terceiro",
    "/cadastro/rescisao",                  # /rescisao/calcular
    "/cadastro/rescisoes",
    "/cadastro/vales",
    "/cadastro/vale-item",
    "/cadastro/vale-avulso",
    "/cadastro/empreitadas",
    "/cadastro/contratos",
    "/cadastro/diarias",
    # BUG DE SEGURANÇA CORRIGIDO: /cadastro/pessoas guarda salario_base, CPF e
    # anexos de documentos pessoais (RG, holerite, contrato...) — tão
    # sensível quanto o resto do RH acima, mas tinha ficado de fora da lista.
    "/cadastro/pessoas",
)

# Prefixos de rota tratados como "dados sensíveis" em modo suporte (ver
# _bloquear_modo_suporte, abaixo) — escrita bloqueada mesmo com a claim
# "suporte" válida, para QUALQUER nível de sigilo (inclusive "total": nível
# de sigilo é sobre LEITURA, ver _PREFIXOS_LEITURA_BLOQUEADA_POR_NIVEL
# abaixo — escrita nesses domínios continua proibida em modo suporte mesmo
# para quem enxerga tudo, porque a trava aqui é "ação destrutiva/financeira
# não é coisa de sessão de suporte", não "confiança").
_PREFIXOS_SENSIVEIS_MODO_SUPORTE = ("/financeiro", "/planejamento", "/chamados", "/cobranca", "/asaas") + _PREFIXOS_RH_MODO_SUPORTE

# Nível de sigilo por conta (#132) — quais grupos de prefixo ficam bloqueados
# também para LEITURA (GET) em modo suporte, abaixo do nível carimbado no
# token (claim "nsig", ver fazenda.auth.criar_token). Cada grupo carrega o
# nome de área usado na mensagem de erro (requisito: explicar o motivo, não
# só devolver um 403 mudo). "/financeiro" aqui cobre também os relatórios de
# custo (relatorio_custo_hectare.py/_producao.py/_safra.py e cartao_credito.py
# reaproveitam o mesmo prefixo "/financeiro" — ver fazenda/api/routers/), daí
# "financeiro e custos" ficar liberado já no nível "tecnico". RH continua
# fechado até "total" — mesmo grupo de prefixos que já tem a escrita sempre
# bloqueada (_PREFIXOS_RH_MODO_SUPORTE), só que agora também pra leitura nos
# dois primeiros níveis. Rota fora de todo grupo = sempre livre para leitura
# (rebanho/reprodução/sanidade/produção/estoque e demais operacionais).
_PREFIXOS_LEITURA_BLOQUEADA_POR_NIVEL: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "basico": (
        ("financeiro e custos", ("/financeiro",)),
        ("folha de pagamento, RH e contratos", _PREFIXOS_RH_MODO_SUPORTE),
    ),
    "tecnico": (
        ("folha de pagamento, RH e contratos", _PREFIXOS_RH_MODO_SUPORTE),
    ),
    "total": (),
}


def _registrar_acao_auditoria_suporte(request, dados: dict, bloqueado: bool, status_code: int | None) -> None:
    """Grava uma linha de auditoria granular durante modo suporte — toda
    escrita tentada (permitida ou bloqueada) e toda LEITURA bloqueada por
    nível de sigilo (#132; leitura permitida não gera linha, ver chamador)
    — ver AcaoAuditoriaSuporte. Nunca deixa uma falha de auditoria derrubar o
    request de verdade: qualquer erro aqui é engolido, só a escrita/bloqueio
    original importa pra quem chamou a rota."""
    try:
        from sqlmodel import select

        from fazenda.models import Usuario
        from fazenda.models.cofre_acesso import AcaoAuditoriaSuporte

        with _sessao_idempotencia(request) as session:
            # O token só carrega "sub" (username), não o id numérico — resolve
            # aqui, igual _nome_usuario/exigir_dono fazem em outras rotas.
            usuario = session.exec(select(Usuario).where(Usuario.username == dados.get("sub"))).first()
            if not usuario or dados.get("ssid") is None or dados.get("fid") is None:
                return
            session.add(AcaoAuditoriaSuporte(
                sessao_id=dados["ssid"], fazenda_id=dados["fid"], usuario_id=usuario.id,
                metodo=request.method, caminho=request.url.path, status_code=status_code, bloqueado=bloqueado,
            ))
            session.commit()
    except Exception:
        pass


@app.middleware("http")
async def _bloquear_modo_suporte(request, call_next):
    """Sessão aberta a partir do Painel CowData (ver cofre_acesso.py) carrega
    a claim "suporte" no token — quem entra assim NÃO pode excluir nada (é o
    caso mais irreversível) nem escrever em dados financeiros/RH, mesmo
    sendo dono-equivalente. Quem entra DIRETO na fazenda (token sem essa
    claim) continua com acesso total de administrador, sem nenhuma mudança.
    Pedido explícito do usuário ("restringir ações" no modo suporte, não só
    marcar/auditar). Toda escrita tentada (bloqueada ou não) também vira uma
    linha em AcaoAuditoriaSuporte — "tudo o que ocorrer nesse acesso de
    suporte deve ficar disponível para ser auditado" (pedido explícito).

    #132 — Nível de sigilo por conta: além da escrita (sempre restrita, ver
    _PREFIXOS_SENSIVEIS_MODO_SUPORTE), passou a barrar também LEITURA (GET)
    das áreas que o nível de sigilo da sessão (claim "nsig" do token) não
    alcança — ver _PREFIXOS_LEITURA_BLOQUEADA_POR_NIVEL. Leitura fora desses
    grupos (rebanho, reprodução, sanidade, produção, estoque, etc.) continua
    sempre livre, em qualquer nível."""
    from fastapi.responses import JSONResponse

    from fazenda.auth import _validar_token_payload
    from fazenda.models.equipe_cowdata_acesso import NIVEL_SIGILO_PADRAO

    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        dados = _validar_token_payload(auth.split(" ", 1)[1])
        if dados and dados.get("suporte") and request.method in ("POST", "PUT", "PATCH", "DELETE", "GET"):
            path = request.url.path
            # A rota de encerrar a própria sessão de suporte não é uma "ação
            # do cliente" — não teria sentido poluir a auditoria dele com o
            # próprio encerramento do acesso.
            eh_encerramento = path.startswith("/painel-cowdata/cofre/sessoes/") and path.endswith("/encerrar")

            # BUG DE SEGURANÇA CORRIGIDO: POST .../sessoes/{id}/encerrar só
            # gravava sessao.encerrada_em no banco — o token JWT já emitido
            # continuava validando normalmente (a claim "suporte" não é
            # reconferida aqui contra o banco) até a própria expiração do
            # JWT. Ou seja, "encerrar" pelo Painel CowData não cortava o
            # acesso de fato. Agora, toda vez que o token carrega "ssid",
            # confere no banco se a sessão ainda está ativa (não encerrada,
            # não expirada) antes de deixar a requisição passar.
            ssid = dados.get("ssid")
            if ssid is not None:
                from datetime import datetime as _datetime

                from fazenda.models.cofre_acesso import SessaoAcessoSuporte

                with _sessao_idempotencia(request) as _sessao_bd:
                    sessao_atual = _sessao_bd.get(SessaoAcessoSuporte, ssid)
                sessao_valida = (
                    sessao_atual is not None
                    and sessao_atual.encerrada_em is None
                    and sessao_atual.expira_em > _datetime.utcnow()
                )
                if not sessao_valida:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Esta sessão de suporte foi encerrada ou expirou. Abra uma nova sessão no Painel CowData."},
                    )

            mensagem_bloqueio: str | None = None

            if request.method == "GET":
                # Nunca confia em claim ausente pra abrir acesso — token sem
                # "nsig" (não deveria existir, mas por segurança) cai no
                # nível mais restritivo, igual ao default do próprio modelo.
                nivel = dados.get("nsig") or NIVEL_SIGILO_PADRAO
                grupos = _PREFIXOS_LEITURA_BLOQUEADA_POR_NIVEL.get(nivel, _PREFIXOS_LEITURA_BLOQUEADA_POR_NIVEL[NIVEL_SIGILO_PADRAO])
                area_bloqueada = next((area for area, prefixos in grupos if any(path.startswith(p) for p in prefixos)), None)
                if area_bloqueada:
                    mensagem_bloqueio = (
                        f'Esta sessão de suporte tem nível de sigilo "{nivel}" e não alcança dados de {area_bloqueada}. '
                        "Para consultar isso, é preciso uma sessão com nível de sigilo mais alto."
                    )
            else:
                # Mesclagem de Estoque (POST .../mesclar) é bloqueada por
                # SUFIXO exato de rota, nunca acrescentando "/estoque" à
                # lista de prefixos acima — isso bloquearia também toda
                # edição legítima de Estoque em modo suporte (ex.: corrigir
                # cadastro a pedido do cliente). "Restaurar padrão" (o
                # oposto — reverter uma personalização ao padrão CowData) é
                # deliberadamente PERMITIDO aqui: é a única ação de escrita
                # em Estoque que só EXISTE em modo suporte (ver
                # `fazenda.auth.exigir_sessao_suporte`), então não faz
                # sentido também bloqueá-la neste middleware.
                eh_mesclagem_estoque = request.method == "POST" and path.rstrip("/").endswith("/mesclar")
                bloquear = request.method == "DELETE" or eh_mesclagem_estoque or (
                    request.method in ("POST", "PUT", "PATCH")
                    and any(path.startswith(p) for p in _PREFIXOS_SENSIVEIS_MODO_SUPORTE)
                )
                if bloquear:
                    mensagem_bloqueio = "Ação bloqueada em modo suporte CowData — para isso, entre na fazenda como administrador."

            if mensagem_bloqueio:
                if not eh_encerramento:
                    _registrar_acao_auditoria_suporte(request, dados, bloqueado=True, status_code=403)
                return JSONResponse(status_code=403, content={"detail": mensagem_bloqueio})

            resposta = await call_next(request)
            # GET permitido não vira linha de auditoria — só bloqueio (acima)
            # é digno de registro; logar toda leitura liberada inundaria a
            # auditoria sem agregar nada (ao contrário de escrita, que é rara
            # e cada uma importa).
            if request.method != "GET" and not eh_encerramento:
                _registrar_acao_auditoria_suporte(request, dados, bloqueado=False, status_code=resposta.status_code)
            return resposta
    return await call_next(request)


@contextlib.contextmanager
def _sessao_idempotencia(request):
    """Sessão de banco pro middleware de idempotência abaixo — respeita
    app.dependency_overrides[get_session] em vez de abrir direto contra o
    `engine` de produção. Sem isso, a suíte de testes (que roda cada teste
    contra um engine SQLite isolado em memória, sobrescrevendo só a
    dependency get_session — ver tests/test_alimentacao.py) acabaria
    gravando a chave de idempotência no banco de desenvolvimento de verdade
    por baixo do pano, em vez do banco isolado do teste."""
    fabrica = request.app.dependency_overrides.get(get_session, get_session)
    gerador = fabrica()
    session = next(gerador)
    try:
        yield session
    finally:
        with contextlib.suppress(StopIteration):
            next(gerador)


@app.middleware("http")
async def _idempotencia(request, call_next):
    """Evita duplicar um lançamento quando a fila offline do app de campo
    (frontend/lib/offline.ts) reenvia um POST/PUT/PATCH cuja resposta se
    perdeu por queda de conexão — o pedido já tinha sido processado com
    sucesso no servidor, mas o cliente viu erro de rede e reenfileirou.

    Sem o header `Idempotency-Key`, é um no-op completo (comportamento igual
    a antes deste middleware existir). Com o header: se já existe uma
    resposta salva para (chave, método, caminho), devolve ela direto, sem
    chamar a rota de novo. Se não existe, deixa seguir e só grava a resposta
    se o resultado for 2xx — um erro de validação (4xx) não fica em cache,
    pra reenviar com o payload corrigido processar normalmente."""
    chave = request.headers.get("idempotency-key")
    if not chave or request.method not in ("POST", "PUT", "PATCH"):
        return await call_next(request)

    metodo = request.method
    caminho = request.url.path
    with _sessao_idempotencia(request) as session:
        existente = session.exec(
            select(IdempotenciaChave).where(
                IdempotenciaChave.chave == chave,
                IdempotenciaChave.metodo == metodo,
                IdempotenciaChave.caminho == caminho,
            )
        ).first()
        if existente:
            # Devolver o cache pula toda a auth/permissão da rota (call_next
            # nem é chamado) — trava mínima pra não virar um jeito de ler a
            # resposta de outra fazenda sem token, ou de outro tenant, só
            # "adivinhando" uma chave: só serve se quem pede tem um token
            # válido da MESMA fazenda que gravou (ou nenhuma das duas tem
            # fazenda, ex.: endpoint sem token/legado). Não bateu → ignora o
            # cache e segue pro fluxo normal (roda a rota com a auth de sempre).
            fid_requisitante = None
            auth = request.headers.get("authorization") or ""
            if auth.lower().startswith("bearer "):
                from fazenda.auth import _validar_token_payload
                dados = _validar_token_payload(auth.split(" ", 1)[1])
                if dados:
                    fid_requisitante = dados.get("fid")
            if existente.fazenda_id is None or existente.fazenda_id == fid_requisitante:
                return Response(
                    content=existente.resposta_json,
                    status_code=existente.status_code,
                    media_type="application/json",
                )

    response = await call_next(request)
    if not (200 <= response.status_code < 300):
        return response  # erro de validação etc. — não grava, deixa a resposta original seguir intacta (streaming)

    # Reconstrói o corpo (StreamingResponse só permite ler uma vez) — junta os
    # chunks e devolve num Response novo, senão o corpo já foi consumido e o
    # cliente não recebe nada.
    corpo = b"".join([chunk async for chunk in response.body_iterator])

    fid = None
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        from fazenda.auth import _validar_token_payload
        dados = _validar_token_payload(auth.split(" ", 1)[1])
        if dados:
            fid = dados.get("fid")
    try:
        texto = corpo.decode("utf-8")
    except UnicodeDecodeError:
        texto = None  # resposta binária (ex.: PDF) — fora do que este cache assume; segue sem gravar

    if texto is not None:
        # Best-effort: a resposta original já reflete um pedido processado com
        # SUCESSO (o commit de verdade, da rota, já aconteceu) — gravar o
        # cache de idempotência é só uma otimização por cima disso. Um
        # `except IntegrityError` sozinho aqui deixava escapar qualquer OUTRO
        # erro (ex.: uma conexão soltando com o Postgres em produção) direto
        # pra fora do middleware, derrubando a resposta inteira — o navegador
        # via "Failed to fetch" mesmo com o lançamento já salvo (bug real,
        # relatado em 01/09/2026 no pagamento de Contas a Pagar).
        try:
            with _sessao_idempotencia(request) as session:
                session.add(IdempotenciaChave(
                    chave=chave, metodo=metodo, caminho=caminho, fazenda_id=fid,
                    status_code=response.status_code, resposta_json=texto,
                ))
                session.commit()
        except Exception:
            pass

    return Response(content=corpo, status_code=response.status_code, media_type=response.headers.get("content-type"))

# Auth (aberto) + rotas de dados (exigem login).
app.include_router(auth.router)
# Fazendas: gerencia os próprios contratos/planos — não leva a trava de
# módulo contratado (seria circular).
app.include_router(fazendas.router)
# Painel Mestre CowData: exigir_dono em cada endpoint (mesmo padrão de
# fazendas.router) — nunca a trava de módulo contratado (é a própria CowData).
app.include_router(painel_cowdata.router)
# Cadastros globais do Painel CowData (motivos/raças/unidades/tipos-métodos
# aplicáveis a todas as fazendas ou às selecionadas) — mesmo padrão
# exigir_area_painel_cowdata("cadastros"), nunca a trava de módulo contratado.
app.include_router(painel_cowdata_cadastros.router)
# Parâmetros gerais/financeiros (ParametroFazenda) aplicáveis a todas as
# fazendas ou às selecionadas — mesmo padrão de painel_cowdata_cadastros.
app.include_router(painel_cowdata_parametros.router)
# Usuários de UMA fazenda-cliente por vez, sem entrar via modo suporte —
# mesmo padrão exigir_area_painel_cowdata("cadastros").
app.include_router(painel_cowdata_usuarios.router)
# Farmácia padrão CowData (categorias/princípios ativos/medicamentos) —
# catálogo global + fan-out de Estoque para toda fazenda-cliente, mesmo
# padrão exigir_area_painel_cowdata("farmacia").
app.include_router(painel_cowdata_farmacia.router)
# Cofre de acesso: mesmo padrão exigir_dono — ver fazenda/api/routers/cofre_acesso.py.
app.include_router(cofre_acesso.router)

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
# Protocolos customizados: lançar/listar ativos/cancelar exige só acesso
# normal ao sistema (mesma regra da Agenda) — editar o MOLDE do protocolo
# exige o módulo "parametros", via cadastro.router.
app.include_router(protocolos_customizados.router, dependencies=_protegido + _contrato_ativo)
app.include_router(lida.router, dependencies=_protegido + _contrato_ativo)
# Central de Protocolos (Acompanhamento/Histórico) — só lê dados de IATF,
# Indução, Sanitário e Customizado; mesma regra de acesso deles (protegido +
# contrato ativo, sem gate de módulo específico).
app.include_router(central_protocolos.router, dependencies=_protegido + _contrato_ativo)
# Fotos do campo (app móvel) — mesma regra do Upload CSV: não é módulo
# comercial próprio, só exige contrato ativo.
app.include_router(fotos.router, dependencies=_protegido + _contrato_ativo)
# Filtros salvos — preferência pessoal do usuário, sem gate de módulo
# contratado (nem sequer exige contrato ativo: é só uma lista de nomes).
app.include_router(filtros_salvos.router, dependencies=_protegido)
# Financeiro exige o módulo "financeiro" (usuário sem acesso recebe 403).
# bloquear_escrita_contador vem por último: o vínculo `contador` (Painel do
# Contador) já tem permissoes=["financeiro"] pelo cadastro normal do usuário
# — sem essa trava adicional, ele conseguiria escrever em qualquer endpoint
# destes 4 routers, não só ler (ver fazenda/auth.py::bloquear_escrita_contador).
app.include_router(financeiro.router, dependencies=[Depends(exigir_modulo("financeiro")), Depends(exigir_modulo_contratado("financeiro")), Depends(bloquear_escrita_contador())])
app.include_router(cartao_credito.router, dependencies=[Depends(exigir_modulo("financeiro")), Depends(exigir_modulo_contratado("financeiro")), Depends(bloquear_escrita_contador())])
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
# escrita em Financeiro/Planejamento/Chamados fica atrás do cadeado. Este
# router continua exigindo só o módulo financeiro (não admin) — é o próprio
# fluxo de upload/gestão, usado inclusive pelo contador; a restrição a
# administrador que a Central de Documentos precisa (ver abaixo) é sobre a
# TELA DE CONSULTA unificada, decidida dentro de central_documentos.py, não
# aqui — apertar aqui quebraria o upload do contador.
app.include_router(documentos.router, dependencies=[Depends(exigir_modulo("financeiro")), Depends(exigir_modulo_contratado("financeiro"))])
# Central de Documentos (Administração) — busca unificada e só-leitura sobre
# documentos.router (fiscal, admin-only) + anexos de lançamento (financeiro,
# quem tem o módulo) — cada tier de acesso é decidido DENTRO do endpoint
# (ver central_documentos.py), não aqui; por isso a única exigência comum é
# estar autenticado com contrato ativo, igual a qualquer outra rota.
app.include_router(central_documentos.router, dependencies=_protegido + _contrato_ativo)
# Chamados (suporte) — mesmo padrão de financeiro: contador só escreve
# (abrir chamado) com o cadeado destravado.
app.include_router(chamados.router, dependencies=[Depends(exigir_modulo("financeiro")), Depends(exigir_modulo_contratado("financeiro")), Depends(bloquear_escrita_contador())])
app.include_router(indicadores.router, dependencies=_protegido + _contrato_ativo)
# Alertas de indicador — preferência pessoal do usuário (config de "avise-me
# se X passar de Y"), sem gate de módulo contratado.
app.include_router(alertas_indicador.router, dependencies=_protegido)
# Não conformidades — área transversal (reprodução/recria/financeiro/manejo),
# mesmo gate de indicadores.router; cada seção interna já se auto-restringe
# por módulo do usuário (ver fazenda/api/routers/nao_conformidades.py).
app.include_router(nao_conformidades.router, dependencies=_protegido + _contrato_ativo)
app.include_router(parametros.router, dependencies=_protegido + _contrato_ativo)
app.include_router(manual_fazenda.router, dependencies=_protegido + _contrato_ativo)
app.include_router(alimentacao.router, dependencies=_protegido + [Depends(exigir_modulo_contratado("alimentacao"))])
# Formulação de Dietas: eixo de acesso à parte (admin OU consultor desta
# fazenda — NUNCA operador comum, mesmo com o módulo "alimentacao"
# liberado), por isso não leva exigir_modulo nem entra em MODULOS/
# ROTA_MODULO — ver fazenda/auth.py::exigir_admin_ou_consultor_fazenda.
app.include_router(
    formulacao_dietas.router,
    dependencies=[Depends(exigir_admin_ou_consultor_fazenda()), Depends(exigir_modulo_contratado("formulacao_dietas"))],
)
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
app.include_router(relatorio_compra_semen.router, dependencies=[Depends(exigir_modulo("rebanho")), Depends(exigir_modulo_contratado("rebanho"))])
# Exclusões: qualquer usuário logado pode buscar/solicitar; excluir de fato,
# aprovar e rejeitar são restritos a administradores (gate por rota, dentro
# do próprio router — ver exclusoes.py).
app.include_router(exclusoes.router, dependencies=_protegido + _contrato_ativo)
app.include_router(notificacoes.router, dependencies=_protegido + _contrato_ativo)
# Onboarding — preferência pessoal do usuário (progresso do checklist),
# sem gate de módulo contratado, mesmo padrão de filtros_salvos.
app.include_router(onboarding.router, dependencies=_protegido)
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
