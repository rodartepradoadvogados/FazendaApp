"""
Assistente Virtual — protótipo de um assistente conversacional embutido no
site, capaz de consultar os dados reais da fazenda via tool-use antes de
responder.

Disponível para qualquer usuário logado — mas cada ferramenta só é oferecida
(e só é executada) se o usuário tiver o módulo correspondente liberado nas
permissões dele (mesma checagem usada para esconder abas no menu — ver
`fazenda.auth.tem_modulo`). Um usuário sem acesso a Financeiro, por exemplo,
nunca vê a ferramenta `consultar_financeiro` na lista oferecida à Claude, e o
próprio Assistente explica que não tem essa permissão se for perguntado.

O provedor de LLM é escolhido por `fazenda.rules.assistente_llm` (OpenRouter
ou Anthropic — variáveis ASSISTENTE_PROVEDOR, OPENROUTER_API_KEY,
ANTHROPIC_API_KEY, ASSISTENTE_MODELO). Falhas viram `ErroAssistente`
(RuntimeError) com mensagem clara, tratada em routers/assistente.py.
"""
from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from fazenda.auth import tem_modulo
from fazenda.models import (
    Animal, AssistenteEnsinamento, ContaGerencial, ControleLeiteiro, Estoque, EventoSanitario, ExameResultado,
    Fornecedor, Lote, Parto, PesagemCorporal, Secagem, Servico, Usuario,
)
from fazenda.rules import assistente_consultas as _consultas
from fazenda.rules import assistente_llm
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.indicadores import calcular_indicadores

MODEL = assistente_llm.MODELO_PADRAO[assistente_llm.PROVEDOR_ANTHROPIC]  # compatibilidade
MAX_RODADAS_TOOL_USE = 4

SYSTEM_PROMPT = """Você é o assistente virtual do sistema de gestão da Fazenda Estreito Ponte de Pedra \
(fazenda leiteira Girolando/Holandês). Responda em português, de forma direta e objetiva, sempre baseado \
nos dados reais que você consulta pelas ferramentas disponíveis — nunca invente números.

As ferramentas oferecidas a você já refletem as permissões do usuário logado — se uma ferramenta não está \
na lista (ex.: financeiro), é porque este usuário não tem acesso àquele módulo no site; nesse caso, diga \
educadamente que ele não tem permissão para consultar aquele assunto, sem tentar contornar isso.

Se a pergunta não puder ser respondida com as ferramentas disponíveis por outro motivo (ex.: pedir para \
lançar ou alterar algo), explique isso ao usuário e diga que essa capacidade ainda não existe neste protótipo."""

# Cada ferramenta é gated pelo módulo indicado (mesma lista de fazenda.auth.MODULOS).
_TOOLS_DISPONIVEIS = [
    {
        "modulo": "indicadores",
        "spec": {
            "name": "consultar_indicadores",
            "description": (
                "Retorna o painel de indicadores gerais do rebanho hoje: composição (total de fêmeas, "
                "distribuição por grupo), situação reprodutiva (taxa de prenhez, taxa de concepção, IEP médio, "
                "partos previstos em 30/60/90 dias) e produção (DEL médio, litros/dia). Use para perguntas sobre "
                "desempenho geral da fazenda."
            ),
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "modulo": "rebanho",
        "spec": {
            "name": "buscar_animal",
            "description": "Busca os dados cadastrais de um animal específico pelo número (brinco/matriz).",
            "input_schema": {
                "type": "object",
                "properties": {"numero": {"type": "string", "description": "Número do animal, ex.: '123'."}},
                "required": ["numero"],
                "additionalProperties": False,
            },
        },
    },
    {
        "modulo": "agenda",
        "spec": {
            "name": "consultar_agenda_hoje",
            "description": (
                "Retorna os eventos e pendências da agenda para o dia de hoje (candidatas a IATF, exames de "
                "BST, contas a pagar/receber, etc.), já filtrados pelas permissões do usuário logado."
            ),
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "modulo": "financeiro",
        "spec": {
            "name": "consultar_financeiro",
            "description": (
                "Retorna um resumo financeiro: total em aberto a pagar, total em aberto a receber, e "
                "quantidade de contas vencidas (a pagar e a receber)."
            ),
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "modulo": "estoque",
        "spec": {
            "name": "consultar_estoque",
            "description": (
                "Retorna os itens de estoque abaixo do mínimo cadastrado (nome, quantidade atual, mínimo, "
                "fornecedor principal) e o total de itens cadastrados."
            ),
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "modulo": "sanidade",
        "spec": {
            "name": "consultar_calendario_sanitario",
            "description": (
                "Retorna as próximas regras do calendário sanitário preventivo (vacinas/exames) que vencem "
                "até 30 dias a partir de hoje — nome do evento, categoria de animais alvo e data prevista."
            ),
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "modulo": "reproducao",
        "spec": {
            "name": "consultar_analise_reprodutiva",
            "description": (
                "Retorna a série mensal (últimos meses) de taxa de concepção, número de serviços, número de "
                "IATF/IA em cio/monta natural e perdas de prenhez — para perguntas sobre desempenho "
                "reprodutivo ao longo do tempo."
            ),
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "modulo": "sanidade",
        "spec": {
            "name": "consultar_exames",
            "description": (
                "Retorna resultados de exames sanitários já realizados (ex.: brucelose, tuberculose, "
                "qualquer exame preventivo cadastrado) — número do animal, data, resultado (positivo/negativo) "
                "e veterinário. Informe pelo menos a data (AAAA-MM-DD) ou o nome do exame/doença; sem nenhum "
                "filtro, não busca (o volume seria grande demais). Diferente de consultar_calendario_sanitario, "
                "que só mostra o que ainda vai vencer — esta ferramenta é para exames já feitos, no passado."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "data": {"type": "string", "description": "Data do exame no formato AAAA-MM-DD. Opcional."},
                    "evento": {"type": "string", "description": "Nome (ou parte do nome) do exame/doença, ex.: 'Brucelose'. Opcional."},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "modulo": "rebanho",
        "spec": {
            "name": "listar_lotes",
            "description": "Retorna todos os lotes de manejo cadastrados, com código, nome e quantidade de animais em cada um.",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "modulo": "rebanho",
        "spec": {
            "name": "consultar_lote",
            "description": (
                "Retorna os animais de um lote específico (pelo código de 2 dígitos, ex.: '04') — número, "
                "categoria, DEL e situação reprodutiva de cada um. Use para perguntas sobre o que tem em um lote."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"codigo": {"type": "string", "description": "Código do lote, 2 dígitos, ex.: '04'."}},
                "required": ["codigo"],
                "additionalProperties": False,
            },
        },
    },
]


def modulo_liberado(usuario: Usuario, modulo) -> bool:
    """`modulo` é um nome de módulo OU uma tupla (basta ter um deles) — as
    ferramentas novas de relatórios/reprodução servem a mais de uma área."""
    modulos = (modulo,) if isinstance(modulo, str) else tuple(modulo)
    return any(tem_modulo(usuario, m) for m in modulos)


def modulo_na_lista(modulo, liberados: set[str]) -> bool:
    """Mesma regra de `modulo_liberado`, para a lista AGENTE_MODULOS."""
    modulos = (modulo,) if isinstance(modulo, str) else tuple(modulo)
    return any(m in liberados for m in modulos)


def _ferramentas_do_usuario(usuario: Usuario) -> list[dict]:
    """Só oferece à Claude as ferramentas cujo módulo o usuário tem liberado."""
    return [t["spec"] for t in _TOOLS_DISPONIVEIS if modulo_liberado(usuario, t["modulo"])]


def _system_prompt(session: Session, fazenda_id: int | None) -> str:
    """SYSTEM_PROMPT fixo + o que um admin ensinou (AssistenteEnsinamento
    ativos da fazenda — cadastro restrito a admin, ver
    fazenda.api.routers.assistente._exigir_admin) — sem nenhum ensinamento
    cadastrado, o prompt fica idêntico ao de sempre (não mexe no texto
    original, só acrescenta uma seção)."""
    query = select(AssistenteEnsinamento).where(AssistenteEnsinamento.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(AssistenteEnsinamento.fazenda_id == fazenda_id)
    ensinamentos = session.exec(query).all()
    if not ensinamentos:
        return SYSTEM_PROMPT
    linhas = "\n".join(f"- {e.titulo}: {e.texto}" for e in ensinamentos)
    return f"{SYSTEM_PROMPT}\n\n## O que foi ensinado sobre esta fazenda e este sistema\n{linhas}"


def _tool_consultar_indicadores(session: Session, fazenda_id: int | None = None) -> dict:
    query_animal = select(Animal).where(Animal.ativo == True)  # noqa: E712
    query_servico = select(Servico)
    query_parto = select(Parto)
    if fazenda_id is not None:
        query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
        query_servico = query_servico.where(Servico.fazenda_id == fazenda_id)
        query_parto = query_parto.where(Parto.fazenda_id == fazenda_id)
    todos = session.exec(query_animal).all()
    animais = [a.model_dump() for a in todos if not a.eh_semen and a.sexo != "M"]
    servicos = [s.model_dump() for s in session.exec(query_servico).all()]
    partos = [p.model_dump() for p in session.exec(query_parto).all()]
    peso_por_animal: dict[str, float] = {}
    ultima_data: dict[str, date] = {}
    # FURO DE MULTI-TENANT CORRIGIDO: PesagemCorporal e Lote já têm
    # fazenda_id (o comentário antigo dizia o contrário — desatualizado);
    # sem o filtro, o Assistente misturava peso/lote de OUTRAS fazendas nos
    # indicadores calculados para esta.
    query_pesagem = select(PesagemCorporal)
    query_lote = select(Lote)
    if fazenda_id is not None:
        query_pesagem = query_pesagem.where(PesagemCorporal.fazenda_id == fazenda_id)
        query_lote = query_lote.where(Lote.fazenda_id == fazenda_id)
    for p in session.exec(query_pesagem).all():
        atual = ultima_data.get(p.numero_matriz)
        if not atual or p.data_pesagem > atual:
            ultima_data[p.numero_matriz] = p.data_pesagem
            peso_por_animal[p.numero_matriz] = p.peso_kg
    lotes = [l.model_dump() for l in session.exec(query_lote).all()]
    # Controles/secagens — sem eles, a resposta da Claude sobre produção
    # saía só de `Animal.ult_cl_kg` (campo congelado do CSV do Ideagri
    # aposentado) e o DEL citado usava o congelado em vez do ao vivo.
    query_controles = select(ControleLeiteiro)
    query_secagens = select(Secagem)
    if fazenda_id is not None:
        query_controles = query_controles.where(ControleLeiteiro.fazenda_id == fazenda_id)
        query_secagens = query_secagens.where(Secagem.fazenda_id == fazenda_id)
    controles = [c.model_dump() for c in session.exec(query_controles).all()]
    secagens = [s.model_dump() for s in session.exec(query_secagens).all()]
    return calcular_indicadores(
        animais, servicos, partos, data_ref=date.today(), peso_por_animal=peso_por_animal, lotes=lotes,
        controles=controles, secagens=secagens,
    )


def _tool_buscar_animal(session: Session, numero: str, fazenda_id: int | None = None) -> dict:
    query = select(Animal).where(Animal.numero == numero)
    if fazenda_id is not None:
        query = query.where(Animal.fazenda_id == fazenda_id)
    animal = session.exec(query).first()
    if not animal:
        return {"erro": f"Animal {numero} não encontrado."}
    return animal.model_dump()


def _tool_consultar_exames(session: Session, data: str | None, evento: str | None, fazenda_id: int | None = None) -> dict:
    if not data and not evento:
        return {"erro": "Informe uma data (AAAA-MM-DD) e/ou o nome do exame/doença — sem nenhum filtro o resultado seria grande demais."}
    query = select(ExameResultado, EventoSanitario).join(EventoSanitario, ExameResultado.evento_sanitario_id == EventoSanitario.id)
    if fazenda_id is not None:
        query = query.where(ExameResultado.fazenda_id == fazenda_id)
    if data:
        try:
            data_alvo = date.fromisoformat(data)
        except ValueError:
            return {"erro": f"Data inválida: '{data}'. Use o formato AAAA-MM-DD."}
        query = query.where(ExameResultado.data_exame == data_alvo)
    if evento:
        query = query.where(EventoSanitario.nome.ilike(f"%{evento}%"))
    linhas = session.exec(query).all()
    exames = [
        {"numero_animal": ex.numero_matriz, "evento": ev.nome, "data_exame": ex.data_exame.isoformat(),
         "resultado": ex.resultado, "veterinario": ex.veterinario}
        for ex, ev in linhas[:200]
    ]
    return {"total": len(exames), "exames": exames}


def _codigo_grupo(grupo: str | None) -> str | None:
    """Extrai o código de 2 dígitos de Animal.grupo_primario (ex.: "04 - SECAS" -> "04") —
    mesma lógica de frontend/components/lancamentos/comumForms.tsx:codigoGrupo()."""
    g = (grupo or "").strip()
    return g[:2] if len(g) >= 2 and g[:2].isdigit() else None


def _tool_listar_lotes(session: Session, fazenda_id: int | None = None) -> dict:
    # FURO DE MULTI-TENANT CORRIGIDO: Lote já tem fazenda_id (comentário
    # antigo desatualizado) — sem o filtro, o Assistente listava também os
    # lotes de OUTRAS fazendas.
    query_lote = select(Lote).where(Lote.ativo == True)  # noqa: E712
    query_animal = select(Animal).where(Animal.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_lote = query_lote.where(Lote.fazenda_id == fazenda_id)
        query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
    lotes = session.exec(query_lote).all()
    animais = session.exec(query_animal).all()
    contagem: dict[str, int] = {}
    for a in animais:
        if a.eh_semen:
            continue
        cod = _codigo_grupo(a.grupo_primario)
        if cod:
            contagem[cod] = contagem.get(cod, 0) + 1
    return {"lotes": [{"codigo": l.codigo, "nome": l.nome, "total_animais": contagem.get(l.codigo, 0)} for l in lotes]}


def _tool_consultar_lote(session: Session, codigo: str, fazenda_id: int | None = None) -> dict:
    codigo = (codigo or "").strip().zfill(2)[:2]
    # FURO DE MULTI-TENANT CORRIGIDO: ver nota em _tool_listar_lotes.
    query_lote = select(Lote).where(Lote.codigo == codigo)
    query_animal = select(Animal).where(Animal.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_lote = query_lote.where(Lote.fazenda_id == fazenda_id)
        query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
    lote = session.exec(query_lote).first()
    animais = session.exec(query_animal).all()
    do_lote = [a for a in animais if not a.eh_semen and _codigo_grupo(a.grupo_primario) == codigo]
    if not lote and not do_lote:
        return {"erro": f"Lote {codigo} não encontrado."}
    return {
        "codigo": codigo,
        "nome": lote.nome if lote else None,
        "total_animais": len(do_lote),
        "animais": [
            {"numero": a.numero, "categoria": a.categoria_completa or a.categoria_abrev,
             "del_dias": a.del_dias, "sit_rep": a.sit_rep, "diagnostico": a.diagnostico}
            for a in do_lote
        ],
    }


def _tool_consultar_agenda_hoje(session: Session, usuario: Usuario, fazenda_id: int | None = None) -> dict:
    from fazenda.api.routers.agenda import calcular_agenda
    hoje = date.today()
    agenda = calcular_agenda(data=hoje, dias=0, session=session, usuario=usuario, fazenda_id=fazenda_id)
    eventos_hoje = [e for e in agenda["eventos"] if e["data"] == hoje.isoformat()]
    return {"data": hoje.isoformat(), "eventos": eventos_hoje, "total": len(eventos_hoje)}


def _tool_consultar_financeiro(session: Session, fazenda_id: int | None = None) -> dict:
    hoje = date.today()
    query = select(ContaGerencial)
    if fazenda_id is not None:
        query = query.where(ContaGerencial.fazenda_id == fazenda_id)
    contas = session.exec(query).all()
    abertas = [c for c in contas if (c.valor_pago or 0) < (c.valor_total or 0)]
    total_pagar = sum(c.valor_total or 0 for c in abertas if c.tipo == "despesa")
    total_receber = sum(c.valor_total or 0 for c in abertas if c.tipo == "receita")
    vencidas = [c for c in abertas if c.data_vencimento and c.data_vencimento < hoje]
    return {
        "total_em_aberto_a_pagar": round(total_pagar, 2),
        "total_em_aberto_a_receber": round(total_receber, 2),
        "qtd_contas_vencidas_a_pagar": sum(1 for c in vencidas if c.tipo == "despesa"),
        "qtd_contas_vencidas_a_receber": sum(1 for c in vencidas if c.tipo == "receita"),
    }


def _tool_consultar_estoque(session: Session, fazenda_id: int | None = None) -> dict:
    # FURO DE MULTI-TENANT CORRIGIDO: Estoque/Fornecedor já têm fazenda_id (o
    # comentário antigo, "ainda não têm", estava desatualizado) — sem o filtro,
    # o Assistente listava itens de OUTRAS fazendas.
    query_fornecedor = select(Fornecedor)
    query_estoque = select(Estoque)
    if fazenda_id is not None:
        query_fornecedor = query_fornecedor.where(Fornecedor.fazenda_id == fazenda_id)
        query_estoque = query_estoque.where(Estoque.fazenda_id == fazenda_id)
    fornecedores = {f.id: f.nome for f in session.exec(query_fornecedor).all()}
    itens = [e.model_dump() for e in session.exec(query_estoque).all()]
    abaixo_minimo = [
        {"nome": i["nome"], "quantidade": i["quantidade"], "estoque_minimo": i.get("estoque_minimo"),
         "fornecedor": fornecedores.get(i.get("fornecedor_id"))}
        for i in itens if i.get("abaixo_minimo") and i.get("ativo") is not False
    ]
    return {"total_itens": len(itens), "abaixo_do_minimo": abaixo_minimo, "qtd_abaixo_do_minimo": len(abaixo_minimo)}


def _tool_consultar_calendario_sanitario(session: Session, fazenda_id: int | None = None) -> dict:
    from datetime import timedelta
    from fazenda.api.routers.sanidade import listar_calendario
    hoje = date.today()
    limite = hoje + timedelta(days=30)
    itens = listar_calendario(session=session, fazenda_id=fazenda_id)
    proximos = [
        {"evento": i.get("evento_sanitario_nome"), "categoria": i.get("categoria_preventiva"), "data_prevista": i.get("proxima_ocorrencia")}
        for i in itens
        if i.get("proxima_ocorrencia") and i["proxima_ocorrencia"] <= limite.isoformat()
    ]
    return {"ate": limite.isoformat(), "proximos": proximos, "total": len(proximos)}


def _tool_consultar_analise_reprodutiva(session: Session, fazenda_id: int | None = None) -> dict:
    from fazenda.models import ControleLeiteiro, Secagem
    from fazenda.rules.reproducao_analise import agregar_mensal, analisar_servicos
    query_servico = select(Servico)
    if fazenda_id is not None:
        query_servico = query_servico.where(Servico.fazenda_id == fazenda_id)
    servicos = [s.model_dump() for s in session.exec(query_servico).all()]
    registros = analisar_servicos(servicos)
    # FURO DE MULTI-TENANT CORRIGIDO: Secagem/ControleLeiteiro já têm fazenda_id.
    query_secagem = select(Secagem)
    query_controle = select(ControleLeiteiro)
    if fazenda_id is not None:
        query_secagem = query_secagem.where(Secagem.fazenda_id == fazenda_id)
        query_controle = query_controle.where(ControleLeiteiro.fazenda_id == fazenda_id)
    secagens = [s.model_dump() for s in session.exec(query_secagem).all()]
    controles = [c.model_dump() for c in session.exec(query_controle).all()]
    from fazenda.rules.parametros import dias_resultado_conhecido

    agregado = agregar_mensal(registros, secagens, controles, dias_resultado=dias_resultado_conhecido())
    # Só os últimos 12 meses — evita mandar um histórico enorme para a Claude.
    meses = agregado["meses"][-12:]
    offset = len(agregado["meses"]) - len(meses)
    series = {k: v[offset:] for k, v in agregado["series"].items()}
    # A Claude precisa saber que o mês mais recente pode estar com a janela de
    # diagnóstico aberta (R7) — sem isto ela lê o número baixo como piora de
    # manejo em vez de "ainda não deu tempo de saber".
    janela_dg_completa = agregado["janela_dg_completa"][offset:]
    return {"meses": meses, "series": series, "janela_dg_completa": janela_dg_completa}


_EXECUTORES = {
    "consultar_indicadores": lambda session, usuario, entrada, fazenda_id: _tool_consultar_indicadores(session, fazenda_id),
    "buscar_animal": lambda session, usuario, entrada, fazenda_id: _tool_buscar_animal(session, entrada.get("numero", ""), fazenda_id),
    "consultar_agenda_hoje": lambda session, usuario, entrada, fazenda_id: _tool_consultar_agenda_hoje(session, usuario, fazenda_id),
    "consultar_financeiro": lambda session, usuario, entrada, fazenda_id: _tool_consultar_financeiro(session, fazenda_id),
    "consultar_estoque": lambda session, usuario, entrada, fazenda_id: _tool_consultar_estoque(session, fazenda_id),
    "consultar_calendario_sanitario": lambda session, usuario, entrada, fazenda_id: _tool_consultar_calendario_sanitario(session, fazenda_id),
    "consultar_analise_reprodutiva": lambda session, usuario, entrada, fazenda_id: _tool_consultar_analise_reprodutiva(session, fazenda_id),
    "listar_lotes": lambda session, usuario, entrada, fazenda_id: _tool_listar_lotes(session, fazenda_id),
    "consultar_lote": lambda session, usuario, entrada, fazenda_id: _tool_consultar_lote(session, entrada.get("codigo", ""), fazenda_id),
    "consultar_exames": lambda session, usuario, entrada, fazenda_id: _tool_consultar_exames(session, entrada.get("data"), entrada.get("evento"), fazenda_id),
}

# Ferramentas com PARÂMETROS (período, filtros) — ver rules/assistente_consultas.py.
_TOOLS_DISPONIVEIS.extend({"modulo": f["modulo"], "spec": f["spec"]} for f in _consultas.FERRAMENTAS)
_EXECUTORES.update({f["spec"]["name"]: f["executor"] for f in _consultas.FERRAMENTAS})

_MODULO_DA_TOOL = {t["spec"]["name"]: t["modulo"] for t in _TOOLS_DISPONIVEIS}


def todas_as_ferramentas() -> list[tuple[str, dict]]:
    """[(módulo, spec)] de TODAS as ferramentas — mesma fonte que
    `_ferramentas_do_usuario`; usada pela API de leitura para agentes
    externos (routers/agente_leitura.py), que as expõe sem duplicar nada."""
    return [(t["modulo"], t["spec"]) for t in _TOOLS_DISPONIVEIS]


def _executar_tool(nome: str, entrada: dict, session: Session, usuario: Usuario, fazenda_id: int | None = None) -> dict:
    modulo = _MODULO_DA_TOOL.get(nome)
    if modulo is None:
        return {"erro": f"Ferramenta desconhecida: {nome}"}
    if not modulo_liberado(usuario, modulo):
        # Segunda barreira (a primeira é nem oferecer a ferramenta à Claude) —
        # cobre o caso do modelo tentar chamar algo fora da lista oferecida.
        nome_modulo = modulo if isinstance(modulo, str) else " ou ".join(modulo)
        return {"erro": f"Usuário sem permissão para o módulo '{nome_modulo}'."}
    return _EXECUTORES[nome](session, usuario, entrada, fazenda_id)


def responder(mensagem: str, historico: list[dict], session: Session, usuario: Usuario, fazenda_id: int | None = None) -> dict:
    """
    Manda a mensagem do usuário (mais o histórico da conversa) para o LLM do
    provedor configurado, executa as ferramentas que ele pedir — só as que o
    usuário tem permissão de usar — e devolve a resposta final em texto, junto
    do histórico atualizado (formato neutro de provedor, ver assistente_llm),
    para o front reenviar na próxima pergunta. Histórico em formato antigo/
    incompatível é descartado. Falhas do provedor levantam ErroAssistente.

    `fazenda_id` filtra as ferramentas que já suportam isolamento por
    fazenda (ver notas nos `_tool_*` acima) — None (chamada direta fora do
    ciclo de requisição, ou token legado) mantém o comportamento de sempre.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    ferramentas = _ferramentas_do_usuario(usuario)
    system = _system_prompt(session, fazenda_id)
    mensagens: list[dict] = [*assistente_llm.limpar_historico(historico), {"role": "user", "content": mensagem}]

    for _ in range(MAX_RODADAS_TOOL_USE):
        resposta = assistente_llm.completar(system, mensagens, ferramentas)
        mensagens.append(resposta)
        chamadas = resposta.get("tool_calls") or []
        if not chamadas:
            return {"resposta": resposta.get("content") or "(sem resposta)", "historico": mensagens}
        for chamada in chamadas:
            resultado = _executar_tool(chamada["name"], chamada["arguments"], session, usuario, fazenda_id)
            if chamada["name"] in _consultas.NOMES and "erro" not in resultado:
                # Mesma sanitização/paginação do /agente (e `truncado`) para o modelo.
                resultado = _consultas.formatar_para_chat(resultado, chamada["arguments"])
            mensagens.append({
                "role": "tool", "tool_call_id": chamada["id"], "name": chamada["name"],
                "content": _serializar(resultado),
            })

    return {
        "resposta": "Não consegui concluir a resposta dentro do limite de consultas deste protótipo — tente reformular a pergunta.",
        "historico": mensagens,
    }


def _serializar(dados: dict) -> str:
    import json
    return json.dumps(dados, ensure_ascii=False, default=str)
