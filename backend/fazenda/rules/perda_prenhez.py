"""
Perda de prenhez — a fonte única da regra "este serviço ainda vale como
prenhez vigente" e a detecção automática de perda por reinseminação.

## O bug que este módulo existe para fechar

Antes, "a vaca está prenha" era decidido de formas diferentes em cada tela:
algumas liam `Animal.sit_rep == "Ges."` (texto congelado do CSV), outras
filtravam `Servico.diagnostico == "POSITIVO"` e pegavam o mais recente ENTRE
OS POSITIVOS — o que continuava contando uma prenhez como vigente mesmo
depois de:
  (a) uma perda de prenhez ter sido registrada nesse mesmo serviço;
  (b) um serviço mais novo (mesmo sem diagnóstico ainda) já ter sucedido
      aquele positivo — ex.: a vaca foi reinseminada sem que ninguém tivesse
      registrado a perda antes;
  (c) um parto já ter resolvido aquela gestação.

`servico_esta_positivo_vigente` e `servicos_positivos_vigentes` são a
implementação única desse critério ("serviço vigente é POSITIVO, sem perda,
e nada mais recente já resolveu essa gestação") — todo consumidor que
precisa saber "isso aqui está prenha AGORA" deve usar uma delas em vez de
repetir o filtro.

## Detecção automática de perda por reinseminação

Pedido do produtor: se uma vaca tem diagnóstico POSITIVO vigente (sem perda
registrada) e ninguém lançou uma nova perda, mas o sistema recebe uma NOVA
inseminação para ela, isso só pode significar uma coisa — a prenhez anterior
se perdeu e ninguém contou pro sistema. `detectar_e_registrar_perda_por_reinseminacao`
grava a perda automaticamente no serviço anterior (dia anterior à nova IA),
deixando `motivo_perda_prenhez` em aberto — é isso que alimenta a pendência
"Cadastrar motivo da perda de prenhez" na Agenda (ver agenda.py). Um parto
real entre os dois serviços NUNCA vira perda — ali a gestação se resolveu do
jeito certo.

Chamada por TODO caminho que cria um `Servico` novo (ver
`fazenda.api.routers.reproducao.registrar_servico`/`_registrar_um_servico`) —
propositalmente NÃO a importação de CSV (`fazenda.parsers.reprodutivo`), que
já traz sua própria coluna "DATA DA PERDA DE PRENHEZ" do sistema de origem
(Ideagri) e não deve ser reinterpretada por heurística.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Sequence

# ---------------------------------------------------------------------------
# Motivos
# ---------------------------------------------------------------------------
MOTIVO_ABORTO = "aborto"
MOTIVO_NATIMORTO = "natimorto"
MOTIVO_OUTROS = "outros"
# Sentinela gravado pelo botão "Descartar" da pendência da Agenda: o usuário
# decidiu não informar o motivo, mas a perda em si CONTINUA registrada — não
# é a mesma coisa que `motivo_perda_prenhez is None` (que ainda está
# pendente de decisão). Ver `ROTULOS_MOTIVO_PERDA` para o texto de tela.
MOTIVO_NAO_INFORMADO = "nao_informado"

# Motivos aceitos no lançamento manual (POST /reproducao/perda-prenhez) e na
# edição direta do serviço quando o usuário ESCOLHE um motivo — "nao_informado"
# não é uma opção de escolha, só o resultado de "Descartar" (ver acima).
MOTIVOS_PERDA_PRENHEZ = [MOTIVO_ABORTO, MOTIVO_NATIMORTO, MOTIVO_OUTROS]

# Todos os valores válidos para `Servico.motivo_perda_prenhez`, incluindo o
# sentinela — usado para validar PUT /reproducao/servicos/{id}.
MOTIVOS_PERDA_PRENHEZ_VALIDOS = [*MOTIVOS_PERDA_PRENHEZ, MOTIVO_NAO_INFORMADO]

ROTULOS_MOTIVO_PERDA = {
    MOTIVO_ABORTO: "Aborto",
    MOTIVO_NATIMORTO: "Natimorto",
    MOTIVO_OUTROS: "Outros",
    MOTIVO_NAO_INFORMADO: "Não informado",
}

ORIGEM_REINSEMINACAO = "reinseminacao"


def _get(obj: Any, campo: str) -> Any:
    """Lê tanto de objeto SQLModel quanto de dict — os dois formatos circulam
    no projeto (routers passam models; regras já achatadas passam dicts)."""
    if isinstance(obj, dict):
        return obj.get(campo)
    return getattr(obj, campo, None)


def servico_esta_positivo_vigente(servico: Any) -> bool:
    """True quando ESTE serviço, isoladamente, ainda representa uma prenhez
    de pé: diagnóstico POSITIVO e sem perda registrada. Não decide sozinho se
    é o serviço VIGENTE do animal (depende da posição dele no histórico —
    ver `servicos_positivos_vigentes`/`fazenda.rules.estado_reprodutivo` para
    a classificação completa); serve para quem já tem em mãos "o serviço
    atual" do animal (ex.: via `ult_ocorrencia == 1`) e só precisa checar se
    ele ainda vale como prenhez — sem esquecer `data_perda_prenhez`, erro que
    fazia uma vaca com perda já registrada continuar aparecendo como
    gestante."""
    diagnostico = (_get(servico, "diagnostico") or "").strip().upper()
    perdeu = _get(servico, "data_perda_prenhez") is not None
    return diagnostico == "POSITIVO" and not perdeu


def servicos_positivos_vigentes(
    servicos: Sequence[Any], partos: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """numero_matriz -> serviço, só para quem tem uma prenhez VIGENTE agora:
    o serviço mais recente da matriz (e, quando `partos` é informado, também
    posterior ao último parto dela) precisa ser POSITIVO e sem perda —
    mesma regra de `fazenda.rules.estado_reprodutivo.classificar_animal`
    (ramo GESTANTE). Corrige o padrão repetido em vários consumidores de
    filtrar `Servico.diagnostico == 'POSITIVO'` e pegar o mais recente ENTRE
    OS POSITIVOS: isso continuava contando uma prenhez como vigente mesmo
    depois de um serviço mais novo (sem diagnóstico ainda, ou negativo) ou um
    parto já terem resolvido aquela gestação.

    Animais sem prenhez vigente simplesmente não aparecem no dict — o
    chamador não precisa filtrar `None` à parte."""
    ultimo_parto_por_matriz: dict[str, date] = {}
    for p in partos or []:
        numero = _get(p, "numero_matriz")
        data = _get(p, "data_parto")
        if not numero or not data:
            continue
        if numero not in ultimo_parto_por_matriz or data > ultimo_parto_por_matriz[numero]:
            ultimo_parto_por_matriz[numero] = data

    por_matriz: dict[str, list[Any]] = {}
    for s in servicos:
        numero = _get(s, "numero_matriz")
        data = _get(s, "data_servico")
        if not numero or not data:
            continue
        ultimo_parto = ultimo_parto_por_matriz.get(numero)
        if ultimo_parto is not None and data <= ultimo_parto:
            continue  # anterior (ou igual) ao último parto — fora do ciclo atual
        por_matriz.setdefault(numero, []).append(s)

    resultado: dict[str, Any] = {}
    for numero, lista in por_matriz.items():
        vigente = max(lista, key=lambda s: _get(s, "data_servico"))
        if servico_esta_positivo_vigente(vigente):
            resultado[numero] = vigente
    return resultado


def detectar_e_registrar_perda_por_reinseminacao(
    session: Any, *, numero_matriz: str, nova_data_servico: date, fazenda_id: int | None,
) -> Any | None:
    """Chamada ANTES (ou depois, tanto faz — só não usa o próprio serviço
    novo) de criar o novo `Servico`, em TODO caminho de lançamento de
    inseminação/cobertura. Se o serviço imediatamente anterior da matriz
    estiver POSITIVO sem perda registrada, e nenhum parto tiver acontecido
    entre ele e esta nova inseminação, grava a perda no dia anterior à nova
    IA — `motivo_perda_prenhez` fica em aberto (é o que gera a pendência
    "Cadastrar motivo da perda de prenhez" na Agenda).

    Idempotente: se o serviço anterior já tem `data_perda_prenhez`, não faz
    nada (não sobrescreve uma perda já registrada, automática ou manual).
    Não dá commit — quem chama já commita a criação do novo serviço junto.

    Devolve o `Servico` alterado (para o chamador incluir em `session.add`
    se quiser) ou `None` quando nada foi feito.
    """
    from sqlmodel import select

    from fazenda.models import Parto, Servico

    query = select(Servico).where(
        Servico.numero_matriz == numero_matriz, Servico.data_servico < nova_data_servico,
    )
    if fazenda_id is not None:
        query = query.where(Servico.fazenda_id == fazenda_id)
    anteriores = session.exec(query).all()
    anterior = max(anteriores, key=lambda s: s.data_servico, default=None)
    if anterior is None or not servico_esta_positivo_vigente(anterior):
        return None

    query_partos = select(Parto).where(
        Parto.numero_matriz == numero_matriz,
        Parto.data_parto > anterior.data_servico,
        Parto.data_parto < nova_data_servico,
    )
    if fazenda_id is not None:
        query_partos = query_partos.where(Parto.fazenda_id == fazenda_id)
    if session.exec(query_partos).first() is not None:
        return None  # pariu entre os dois serviços — gestação resolvida por parto, não por perda

    perda_em = nova_data_servico - timedelta(days=1)
    if perda_em < anterior.data_servico:
        return None  # nova IA no mesmo dia (ou antes) do serviço anterior — dado incoerente, não mexe

    anterior.data_perda_prenhez = perda_em
    anterior.motivo_perda_prenhez = None
    anterior.origem_perda_prenhez = ORIGEM_REINSEMINACAO
    session.add(anterior)
    return anterior
