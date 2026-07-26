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

Requer a variável de ambiente ANTHROPIC_API_KEY (mesmo padrão de
`fazenda.rules.leitura_documento`). Sem ela, `responder` levanta RuntimeError
com uma mensagem clara para o administrador configurar.
"""
from __future__ import annotations

import os
from datetime import date

from sqlmodel import Session, select

from fazenda.auth import tem_modulo
from fazenda.models import Animal, ContaGerencial, Estoque, Fornecedor, Lote, Parto, PesagemCorporal, Servico, Usuario
from fazenda.rules.indicadores import calcular_indicadores

MODEL = "claude-sonnet-5"
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


def _client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Assistente Claude não está configurado — falta a variável de ambiente ANTHROPIC_API_KEY. "
            "Configure-a nas variáveis do serviço (Railway > Variables) para habilitar."
        )
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def _ferramentas_do_usuario(usuario: Usuario) -> list[dict]:
    """Só oferece à Claude as ferramentas cujo módulo o usuário tem liberado."""
    return [t["spec"] for t in _TOOLS_DISPONIVEIS if tem_modulo(usuario, t["modulo"])]


def _tool_consultar_indicadores(session: Session) -> dict:
    todos = session.exec(select(Animal).where(Animal.ativo == True)).all()  # noqa: E712
    animais = [a.model_dump() for a in todos if not a.eh_semen and a.sexo != "M"]
    servicos = [s.model_dump() for s in session.exec(select(Servico)).all()]
    partos = [p.model_dump() for p in session.exec(select(Parto)).all()]
    peso_por_animal: dict[str, float] = {}
    ultima_data: dict[str, date] = {}
    for p in session.exec(select(PesagemCorporal)).all():
        atual = ultima_data.get(p.numero_matriz)
        if not atual or p.data_pesagem > atual:
            ultima_data[p.numero_matriz] = p.data_pesagem
            peso_por_animal[p.numero_matriz] = p.peso_kg
    lotes = [l.model_dump() for l in session.exec(select(Lote)).all()]
    return calcular_indicadores(animais, servicos, partos, data_ref=date.today(), peso_por_animal=peso_por_animal, lotes=lotes)


def _tool_buscar_animal(session: Session, numero: str) -> dict:
    animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
    if not animal:
        return {"erro": f"Animal {numero} não encontrado."}
    return animal.model_dump()


def _codigo_grupo(grupo: str | None) -> str | None:
    """Extrai o código de 2 dígitos de Animal.grupo_primario (ex.: "04 - SECAS" -> "04") —
    mesma lógica de frontend/components/lancamentos/comumForms.tsx:codigoGrupo()."""
    g = (grupo or "").strip()
    return g[:2] if len(g) >= 2 and g[:2].isdigit() else None


def _tool_listar_lotes(session: Session) -> dict:
    lotes = session.exec(select(Lote).where(Lote.ativo == True)).all()  # noqa: E712
    animais = session.exec(select(Animal).where(Animal.ativo == True)).all()  # noqa: E712
    contagem: dict[str, int] = {}
    for a in animais:
        if a.eh_semen:
            continue
        cod = _codigo_grupo(a.grupo_primario)
        if cod:
            contagem[cod] = contagem.get(cod, 0) + 1
    return {"lotes": [{"codigo": l.codigo, "nome": l.nome, "total_animais": contagem.get(l.codigo, 0)} for l in lotes]}


def _tool_consultar_lote(session: Session, codigo: str) -> dict:
    codigo = (codigo or "").strip().zfill(2)[:2]
    lote = session.exec(select(Lote).where(Lote.codigo == codigo)).first()
    animais = session.exec(select(Animal).where(Animal.ativo == True)).all()  # noqa: E712
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


def _tool_consultar_agenda_hoje(session: Session, usuario: Usuario) -> dict:
    from fazenda.api.routers.agenda import calcular_agenda
    hoje = date.today()
    agenda = calcular_agenda(data=hoje, dias=0, session=session, usuario=usuario)
    eventos_hoje = [e for e in agenda["eventos"] if e["data"] == hoje.isoformat()]
    return {"data": hoje.isoformat(), "eventos": eventos_hoje, "total": len(eventos_hoje)}


def _tool_consultar_financeiro(session: Session) -> dict:
    hoje = date.today()
    contas = session.exec(select(ContaGerencial)).all()
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


def _tool_consultar_estoque(session: Session) -> dict:
    fornecedores = {f.id: f.nome for f in session.exec(select(Fornecedor)).all()}
    itens = [e.model_dump() for e in session.exec(select(Estoque)).all()]
    abaixo_minimo = [
        {"nome": i["nome"], "quantidade": i["quantidade"], "estoque_minimo": i.get("estoque_minimo"),
         "fornecedor": fornecedores.get(i.get("fornecedor_id"))}
        for i in itens if i.get("abaixo_minimo")
    ]
    return {"total_itens": len(itens), "abaixo_do_minimo": abaixo_minimo, "qtd_abaixo_do_minimo": len(abaixo_minimo)}


def _tool_consultar_calendario_sanitario(session: Session) -> dict:
    from datetime import timedelta
    from fazenda.api.routers.sanidade import listar_calendario
    hoje = date.today()
    limite = hoje + timedelta(days=30)
    itens = listar_calendario(session=session)
    proximos = [
        {"evento": i.get("evento_sanitario_nome"), "categoria": i.get("categoria_preventiva"), "data_prevista": i.get("proxima_ocorrencia")}
        for i in itens
        if i.get("proxima_ocorrencia") and i["proxima_ocorrencia"] <= limite.isoformat()
    ]
    return {"ate": limite.isoformat(), "proximos": proximos, "total": len(proximos)}


def _tool_consultar_analise_reprodutiva(session: Session) -> dict:
    from fazenda.models import ControleLeiteiro, Secagem
    from fazenda.rules.reproducao_analise import agregar_mensal, analisar_servicos
    servicos = [s.model_dump() for s in session.exec(select(Servico)).all()]
    registros = analisar_servicos(servicos)
    secagens = [s.model_dump() for s in session.exec(select(Secagem)).all()]
    controles = [c.model_dump() for c in session.exec(select(ControleLeiteiro)).all()]
    agregado = agregar_mensal(registros, secagens, controles)
    # Só os últimos 12 meses — evita mandar um histórico enorme para a Claude.
    meses = agregado["meses"][-12:]
    offset = len(agregado["meses"]) - len(meses)
    series = {k: v[offset:] for k, v in agregado["series"].items()}
    return {"meses": meses, "series": series}


_EXECUTORES = {
    "consultar_indicadores": lambda session, usuario, entrada: _tool_consultar_indicadores(session),
    "buscar_animal": lambda session, usuario, entrada: _tool_buscar_animal(session, entrada.get("numero", "")),
    "consultar_agenda_hoje": lambda session, usuario, entrada: _tool_consultar_agenda_hoje(session, usuario),
    "consultar_financeiro": lambda session, usuario, entrada: _tool_consultar_financeiro(session),
    "consultar_estoque": lambda session, usuario, entrada: _tool_consultar_estoque(session),
    "consultar_calendario_sanitario": lambda session, usuario, entrada: _tool_consultar_calendario_sanitario(session),
    "consultar_analise_reprodutiva": lambda session, usuario, entrada: _tool_consultar_analise_reprodutiva(session),
    "listar_lotes": lambda session, usuario, entrada: _tool_listar_lotes(session),
    "consultar_lote": lambda session, usuario, entrada: _tool_consultar_lote(session, entrada.get("codigo", "")),
}

_MODULO_DA_TOOL = {t["spec"]["name"]: t["modulo"] for t in _TOOLS_DISPONIVEIS}


def _executar_tool(nome: str, entrada: dict, session: Session, usuario: Usuario) -> dict:
    modulo = _MODULO_DA_TOOL.get(nome)
    if modulo is None:
        return {"erro": f"Ferramenta desconhecida: {nome}"}
    if not tem_modulo(usuario, modulo):
        # Segunda barreira (a primeira é nem oferecer a ferramenta à Claude) —
        # cobre o caso do modelo tentar chamar algo fora da lista oferecida.
        return {"erro": f"Usuário sem permissão para o módulo '{modulo}'."}
    return _EXECUTORES[nome](session, usuario, entrada)


def responder(mensagem: str, historico: list[dict], session: Session, usuario: Usuario) -> dict:
    """
    Manda a mensagem do usuário (mais o histórico da conversa) para o Claude,
    executa as ferramentas que ele pedir — só as que o usuário tem permissão
    de usar — e devolve a resposta final em texto, junto do histórico
    atualizado, para o front reenviar na próxima pergunta.
    """
    client = _client()
    ferramentas = _ferramentas_do_usuario(usuario)
    mensagens: list[dict] = [*historico, {"role": "user", "content": mensagem}]

    for _ in range(MAX_RODADAS_TOOL_USE):
        resposta = client.messages.create(
            model=MODEL,
            max_tokens=1536,
            system=SYSTEM_PROMPT,
            tools=ferramentas,
            messages=mensagens,
        )
        # Serializa os blocos (texto/tool_use) para dict puro — tanto para o
        # histórico ir e voltar do front em JSON quanto para reenviar à API
        # na próxima rodada deste laço.
        conteudo = [bloco.model_dump() for bloco in resposta.content]
        mensagens.append({"role": "assistant", "content": conteudo})

        if resposta.stop_reason != "tool_use":
            texto = "".join(b.text for b in resposta.content if b.type == "text")
            return {"resposta": texto or "(sem resposta)", "historico": mensagens}

        blocos_resultado = []
        for bloco in resposta.content:
            if bloco.type != "tool_use":
                continue
            resultado = _executar_tool(bloco.name, bloco.input, session, usuario)
            blocos_resultado.append({
                "type": "tool_result",
                "tool_use_id": bloco.id,
                "content": [{"type": "text", "text": _serializar(resultado)}],
            })
        mensagens.append({"role": "user", "content": blocos_resultado})

    return {
        "resposta": "Não consegui concluir a resposta dentro do limite de consultas deste protótipo — tente reformular a pergunta.",
        "historico": mensagens,
    }


def _serializar(dados: dict) -> str:
    import json
    return json.dumps(dados, ensure_ascii=False, default=str)
