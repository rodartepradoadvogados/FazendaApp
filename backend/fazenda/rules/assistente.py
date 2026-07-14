"""
Assistente Claude — protótipo de um assistente conversacional embutido no
site, capaz de consultar os dados reais da fazenda (indicadores, ficha de
animal, agenda do dia) via tool-use antes de responder.

Requer a variável de ambiente ANTHROPIC_API_KEY (mesmo padrão de
`fazenda.rules.leitura_documento`). Sem ela, `responder` levanta RuntimeError
com uma mensagem clara para o administrador configurar.

Escopo deste protótipo: 3 ferramentas somente-leitura (nenhuma delas altera
dados) e um laço de tool-use limitado a poucas rodadas — o suficiente para
validar a arquitetura antes de decidir se vale expandir (mais ferramentas,
memória de conversa persistida, streaming).
"""
from __future__ import annotations

import os
from datetime import date

from sqlmodel import Session, select

from fazenda.models import Animal, Parto, PesagemCorporal, Servico, Usuario
from fazenda.rules.indicadores import calcular_indicadores

MODEL = "claude-sonnet-5"
MAX_RODADAS_TOOL_USE = 4

SYSTEM_PROMPT = """Você é o assistente virtual do sistema de gestão da Fazenda Estreito Ponte de Pedra \
(fazenda leiteira Girolando/Holandês). Responda em português, de forma direta e objetiva, sempre baseado \
nos dados reais que você consulta pelas ferramentas disponíveis — nunca invente números.

Se a pergunta não puder ser respondida com as ferramentas disponíveis (ex.: pedir para lançar ou alterar \
algo, ou consultar um dado fora do escopo das ferramentas), explique isso ao usuário e diga que essa \
capacidade ainda não existe neste protótipo."""

TOOLS = [
    {
        "name": "consultar_indicadores",
        "description": (
            "Retorna o painel de indicadores gerais do rebanho hoje: composição (total de fêmeas, "
            "distribuição por grupo), situação reprodutiva (taxa de prenhez, taxa de concepção, IEP médio, "
            "partos previstos em 30/60/90 dias) e produção (DEL médio, litros/dia). Use para perguntas sobre "
            "desempenho geral da fazenda."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "buscar_animal",
        "description": "Busca os dados cadastrais de um animal específico pelo número (brinco/matriz).",
        "input_schema": {
            "type": "object",
            "properties": {"numero": {"type": "string", "description": "Número do animal, ex.: '123'."}},
            "required": ["numero"],
            "additionalProperties": False,
        },
    },
    {
        "name": "consultar_agenda_hoje",
        "description": (
            "Retorna os eventos e pendências da agenda para o dia de hoje (candidatas a IATF, exames de "
            "BST, contas a pagar/receber, etc.), já filtrados pelas permissões do usuário logado."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
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
    return calcular_indicadores(animais, servicos, partos, data_ref=date.today(), peso_por_animal=peso_por_animal)


def _tool_buscar_animal(session: Session, numero: str) -> dict:
    animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
    if not animal:
        return {"erro": f"Animal {numero} não encontrado."}
    return animal.model_dump()


def _tool_consultar_agenda_hoje(session: Session, usuario: Usuario) -> dict:
    from fazenda.api.routers.agenda import calcular_agenda
    hoje = date.today()
    agenda = calcular_agenda(data=hoje, dias=0, session=session, usuario=usuario)
    eventos_hoje = [e for e in agenda["eventos"] if e["data"] == hoje.isoformat()]
    return {"data": hoje.isoformat(), "eventos": eventos_hoje, "total": len(eventos_hoje)}


def _executar_tool(nome: str, entrada: dict, session: Session, usuario: Usuario) -> dict:
    if nome == "consultar_indicadores":
        return _tool_consultar_indicadores(session)
    if nome == "buscar_animal":
        return _tool_buscar_animal(session, entrada.get("numero", ""))
    if nome == "consultar_agenda_hoje":
        return _tool_consultar_agenda_hoje(session, usuario)
    return {"erro": f"Ferramenta desconhecida: {nome}"}


def responder(mensagem: str, historico: list[dict], session: Session, usuario: Usuario) -> dict:
    """
    Manda a mensagem do usuário (mais o histórico da conversa) para o Claude,
    executa as ferramentas que ele pedir e devolve a resposta final em texto —
    junto do histórico atualizado, para o front reenviar na próxima pergunta.
    """
    import anthropic

    client = _client()
    mensagens: list[dict] = [*historico, {"role": "user", "content": mensagem}]

    for _ in range(MAX_RODADAS_TOOL_USE):
        resposta = client.messages.create(
            model=MODEL,
            max_tokens=1536,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
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
