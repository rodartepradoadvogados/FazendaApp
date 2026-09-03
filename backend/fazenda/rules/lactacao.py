"""
Lactação — a fonte única de "esta matriz está em lactação?" e "qual o DEL
dela?".

## O bug que este módulo existe para fechar

O sistema não tinha a entidade lactação. Cada tela inferia o estado do seu
próprio jeito, e as inferências não concordavam entre si:

  * a Ficha do animal: "existe um `Parto`?" — e o aborto NÃO criava `Parto`,
    então a matriz que abortou continuava "novilha gestante, sem parto"
    mesmo depois de o usuário lançar o aborto, mandar abrir a lactação, o
    animal entrar no lote de lactação e já ter controle leiteiro lançado;
  * o lançamento de controle leiteiro: "o código do lote é 01/02/03?" OU
    "`Animal.del_dias > 0`?" — o primeiro depende de o funcionário ter
    movido a vaca de lote, o segundo de um campo CONGELADO, que nasce 0 no
    instante do parto e só volta a bater com a realidade no próximo upload
    do CSV;
  * a curva de lactação do rebanho: `ControleLeiteiro.del_no_controle`
    recebia esse mesmo `Animal.del_dias` congelado, então toda vaca que
    pariu pelo app entrava na curva com DEL 0.

Com a `Lactacao` materializada (ver `fazenda.models.producao.Lactacao`), as
duas perguntas viram uma consulta só:

    lactacao_aberta(session, numero_matriz="14", data=hoje)  -> Lactacao | None
    del_vivo(session, numero_matriz="14", data=hoje)          -> int | None

`del_vivo` devolve `None` para quem NUNCA lactou — que é diferente de 0
("pariu hoje"). Essa distinção é o motivo de o retorno ser opcional em vez de
um inteiro com 0 como sentinela.

## Quem abre e quem fecha

Abre: `POST /reproducao/encerramento-gestacao` (parto, aborto ou natimorto,
com a data REAL do evento — retroativa quando for o caso), o backfill dos
partos que já existiam no banco, e `POST /producao/inducao-lactacao/
{lancamento_id}/{numero_matriz}/confirmar` (resposta ao card "Confirmar
início de lactação" da Agenda, quando um protocolo de indução de lactação em
lote termina todas as etapas de uma matriz — ver `inducao_concluida` abaixo e
`ORIGEM_INDUCAO`). Fecha: `POST /producao/secagem`.

Nada aqui dá commit — as funções recebem a `Session` do chamador e fazem
parte da transação dele (o endpoint de encerramento de gestação grava
`Parto`, perda de prenhez e `Lactacao` de uma vez só ou nada).
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlmodel import Session, select

from fazenda.models import Animal, Lactacao, Parto, Secagem
from fazenda.rules.parto import eh_parto_produtivo

# ---------------------------------------------------------------------------
# Origens de uma lactação
# ---------------------------------------------------------------------------
ORIGEM_PARTO = "parto"
ORIGEM_ABORTO = "aborto"
ORIGEM_INDUCAO = "inducao"
ORIGEM_IMPORTACAO = "importacao"

ORIGENS_VALIDAS = (ORIGEM_PARTO, ORIGEM_ABORTO, ORIGEM_INDUCAO, ORIGEM_IMPORTACAO)


def _escopo(query, modelo, fazenda_id: int | None):
    """Filtro de fazenda quando há uma selecionada — mesmo piloto conservador
    do resto do projeto (token sem fazenda continua vendo tudo)."""
    if fazenda_id is not None:
        query = query.where(modelo.fazenda_id == fazenda_id)
    return query


# ---------------------------------------------------------------------------
# Indução de lactação — apoio ao card "Confirmar início de lactação" da Agenda
# ---------------------------------------------------------------------------
def inducao_concluida(aplicacoes: list) -> tuple[bool, date | None]:
    """Recebe as `ProtocoloInducaoAplicacao` de UMA MATRIZ dentro de UM
    `ProtocoloInducaoLancamento` e devolve `(concluida, data_sugerida)`.

    Diferente de `fazenda.rules.cura_protocolo.protocolo_terminado` — que
    olha só as aplicações do ÚLTIMO DIA porque lá o lançamento é de UM
    animal só — aqui a lista já chega filtrada por animal (o lançamento de
    indução é em LOTE, várias matrizes por `ProtocoloInducaoLancamento`, ver
    `ProtocoloInducaoAplicacao`). "Concluída" é então TODAS as etapas DESSE
    animal estarem `realizada=True`, não só as do último dia dele.

    `data_sugerida` é a data real da última etapa (`data_realizacao`, quando
    já lançada) ou a `data_prevista` dela quando não houver — o ponto de
    partida editável da lactação mostrado no card da Agenda (ver
    `fazenda.api.routers.agenda` e `POST /producao/inducao-lactacao/
    {lancamento_id}/{numero_matriz}/confirmar`)."""
    if not aplicacoes or not all(a.realizada for a in aplicacoes):
        return False, None
    ultima = max(aplicacoes, key=lambda a: a.dia)
    return True, (ultima.data_realizacao or ultima.data_prevista)


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
def lactacoes_da_matriz(
    session: Session, *, numero_matriz: str, fazenda_id: int | None = None,
) -> list[Lactacao]:
    """Todas as lactações da matriz, da mais antiga para a mais nova."""
    query = _escopo(
        select(Lactacao).where(Lactacao.numero_matriz == numero_matriz), Lactacao, fazenda_id,
    )
    return sorted(session.exec(query).all(), key=lambda l: l.data_inicio)


def lactacao_aberta(
    session: Session, *, numero_matriz: str, data: date | None = None, fazenda_id: int | None = None,
) -> Lactacao | None:
    """A lactação da matriz que estava ABERTA na `data` informada (padrão:
    hoje), ou `None`.

    "Aberta em D" = começou em D ou antes E (ainda não foi fechada OU foi
    fechada depois de D). A segunda metade é o que permite lançar um controle
    leiteiro retroativo de uma vaca que já secou desde então — o controle
    pertence à lactação que estava de pé NAQUELE dia, não à situação de hoje.

    Empate no dia do parto conta como lactação aberta (`data_inicio <=
    data`): a vaca pariu e já está sendo ordenhada. Empate no dia da secagem
    conta como FECHADA (`data_fim > data` é exigido): o dia da secagem é o
    último em que ela não é mais ordenhada.

    Quando mais de uma lactação satisfaz o critério (dado incoerente — duas
    aberturas sem fechamento no meio), devolve a MAIS RECENTE: é ela que
    descreve o estado atual da matriz.
    """
    dia = data or date.today()
    candidatas = [
        l for l in lactacoes_da_matriz(session, numero_matriz=numero_matriz, fazenda_id=fazenda_id)
        if l.data_inicio <= dia and (l.data_fim is None or l.data_fim > dia)
    ]
    return candidatas[-1] if candidatas else None


def del_vivo(
    session: Session, *, numero_matriz: str, data: date | None = None, fazenda_id: int | None = None,
) -> int | None:
    """DEL (dias em lactação) da matriz na `data`, calculado da lactação
    ABERTA naquele dia — `None` quando ela não estava em lactação (inclusive
    quando nunca lactou).

    `None` e `0` são coisas diferentes de propósito: 0 é "pariu exatamente
    hoje", `None` é "não há lactação". Quem grava isso num campo (ex.:
    `ControleLeiteiro.del_no_controle`) precisa dessa distinção — foi
    justamente confundir as duas que encheu a curva de lactação do rebanho
    de DEL 0.
    """
    dia = data or date.today()
    lact = lactacao_aberta(session, numero_matriz=numero_matriz, data=dia, fazenda_id=fazenda_id)
    if lact is None:
        return None
    return (dia - lact.data_inicio).days


def em_lactacao_por_matriz(
    session: Session, numeros: set[str] | list[str] | None = None, *,
    data: date | None = None, fazenda_id: int | None = None,
) -> dict[str, Lactacao]:
    """{numero_matriz: lactação aberta na `data`} para o rebanho inteiro (ou
    só para `numeros`).

    UMA consulta para todos — a listagem de animais (GET /animais/) precisa
    disso por animal e chamá-la em laço faria uma consulta por vaca.
    """
    dia = data or date.today()
    query = _escopo(select(Lactacao), Lactacao, fazenda_id)
    if numeros:
        query = query.where(Lactacao.numero_matriz.in_(list(numeros)))
    abertas: dict[str, Lactacao] = {}
    for l in session.exec(query).all():
        if l.data_inicio > dia or (l.data_fim is not None and l.data_fim <= dia):
            continue
        atual = abertas.get(l.numero_matriz)
        if atual is None or l.data_inicio >= atual.data_inicio:
            abertas[l.numero_matriz] = l
    return abertas


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------
def proximo_numero_lactacao(
    session: Session, *, numero_matriz: str, fazenda_id: int | None = None,
) -> int:
    """Ordem da próxima lactação da matriz. Conta TODAS as lactações
    anteriores, inclusive as abertas por aborto ou indução — é a ordem da
    LACTAÇÃO, não a ordem de parto (ver `fazenda.rules.parto`)."""
    return len(lactacoes_da_matriz(session, numero_matriz=numero_matriz, fazenda_id=fazenda_id)) + 1


def abrir_lactacao(
    session: Session, *, numero_matriz: str, data_inicio: date, origem: str,
    parto_id: int | None = None, animal_id: int | None = None,
    fazenda_id: int | None = None, usuario_id: int | None = None,
    observacao: str | None = None,
) -> Lactacao:
    """Cria (ou reaproveita) a lactação que começa em `data_inicio`.

    IDEMPOTENTE por (matriz, data_inicio): relançar o mesmo evento — duplo
    clique, retry da fila offline do app de campo, reimportação — devolve a
    lactação que já existe em vez de abrir uma segunda. Sem isso, a matriz
    ficaria com duas lactações abertas no mesmo dia e o DEL passaria a
    depender de qual delas a consulta pegasse primeiro.

    Fecha automaticamente a lactação anterior que ainda estivesse aberta na
    véspera: um novo parto/aborto encerra a lactação anterior mesmo sem
    secagem lançada (é o que acontece na vida real quando a vaca pariu de
    novo sem ter passado pelo lote de secas). `secagem_id` fica NULL nesse
    caso — não houve secagem, e inventar uma seria fabricar um evento de
    manejo que não aconteceu.

    Não dá commit: quem chama commita a transação inteira.
    """
    if origem not in ORIGENS_VALIDAS:
        raise ValueError(f"origem de lactação inválida: {origem!r}")

    ja_existe = next(
        (
            l for l in lactacoes_da_matriz(session, numero_matriz=numero_matriz, fazenda_id=fazenda_id)
            if l.data_inicio == data_inicio
        ),
        None,
    )
    if ja_existe is not None:
        # Completa o vínculo com o parto se ele só apareceu agora (ex.: a
        # lactação veio do backfill e o parto foi relançado pelo app).
        if ja_existe.parto_id is None and parto_id is not None:
            ja_existe.parto_id = parto_id
            session.add(ja_existe)
        return ja_existe

    for anterior in lactacoes_da_matriz(session, numero_matriz=numero_matriz, fazenda_id=fazenda_id):
        if anterior.data_inicio < data_inicio and (anterior.data_fim is None or anterior.data_fim > data_inicio):
            anterior.data_fim = data_inicio
            session.add(anterior)

    if animal_id is None:
        query_animal = _escopo(select(Animal).where(Animal.numero == numero_matriz), Animal, fazenda_id)
        animal = session.exec(query_animal).first()
        animal_id = animal.id if animal else None

    lactacao = Lactacao(
        fazenda_id=fazenda_id,
        animal_id=animal_id,
        numero_matriz=numero_matriz,
        data_inicio=data_inicio,
        origem=origem,
        parto_id=parto_id,
        numero_lactacao=proximo_numero_lactacao(session, numero_matriz=numero_matriz, fazenda_id=fazenda_id),
        usuario_id=usuario_id,
        observacao=observacao,
        criado_em=datetime.utcnow(),
    )
    session.add(lactacao)
    return lactacao


def fechar_lactacao_por_secagem(
    session: Session, *, numero_matriz: str, data_secagem: date, secagem_id: int | None = None,
    fazenda_id: int | None = None,
) -> Lactacao | None:
    """Fecha a lactação que estava aberta na data da secagem — devolve a
    lactação fechada, ou `None` quando não havia nenhuma aberta (secagem
    lançada para quem o sistema não sabe que estava lactando; não é erro,
    só não há o que fechar).

    Idempotente: uma segunda secagem na mesma data não reabre nem duplica
    nada. Não dá commit."""
    lact = lactacao_aberta(session, numero_matriz=numero_matriz, data=data_secagem, fazenda_id=fazenda_id)
    if lact is None:
        return None
    lact.data_fim = data_secagem
    if secagem_id is not None:
        lact.secagem_id = secagem_id
    session.add(lact)
    return lact


def reabrir_lactacao_fechada_por_secagem(
    session: Session, *, secagem_id: int, fazenda_id: int | None = None,
) -> Lactacao | None:
    """Desfaz o fechamento que ESTA secagem causou — devolve a `Lactacao` que
    ela tinha fechado (`data_fim = None`, `secagem_id = None`), ou `None`
    quando esta secagem não fechou nenhuma (lançada para quem já constava
    seco; não é erro, só não há o que reabrir).

    Usada em dois lugares: ao EXCLUIR a secagem (ver
    `api/routers/exclusoes.py`) e ao SUBSTITUIR a data de uma secagem lançada
    errada (ver `POST /producao/secagem`, campo `substituir_secagem_id`) —
    nos dois casos o evento real não aconteceu (ou não naquela data), e a
    lactação que ele fechou por engano precisa voltar a ficar aberta antes de
    prosseguir. Não dá commit."""
    query = select(Lactacao).where(Lactacao.secagem_id == secagem_id)
    if fazenda_id is not None:
        query = query.where(Lactacao.fazenda_id == fazenda_id)
    lact = session.exec(query).first()
    if lact is None:
        return None
    lact.data_fim = None
    lact.secagem_id = None
    session.add(lact)
    return lact


# ---------------------------------------------------------------------------
# Backfill — reconstrói o histórico de lactações a partir do que já existe
# ---------------------------------------------------------------------------
def backfill_lactacoes(session: Session, *, fazenda_id: int | None = None) -> dict[str, int]:
    """Gera uma `Lactacao` para cada `Parto` PRODUTIVO já gravado no banco,
    fechando cada uma com o que veio primeiro: a `Secagem` seguinte daquele
    animal ou o parto seguinte dele.

    100% determinístico a partir dos dados existentes — não inventa data
    nenhuma. Abortos importados (`tipo_parto = "Aborto"`, ver
    `fazenda.rules.parto`) NÃO geram lactação aqui de propósito: no
    histórico importado não há como saber se a fazenda ordenhou aquela vaca
    depois do aborto, e afirmar que sim inventaria uma lactação inteira. A
    partir de agora essa resposta passa a ser explícita — é a pergunta do
    popup de aborto ("deseja abrir lactação?") gravada no
    `abrir_lactacao` do endpoint de encerramento de gestação.

    IDEMPOTENTE: rodar de novo não duplica nada (`abrir_lactacao` reaproveita
    por (matriz, data_inicio)), então serve tanto para a migração de dados
    quanto para reprocessar depois de uma importação de CSV.

    Não dá commit — quem chama decide quando (a migração Alembic commita a
    transação dela).

    `Parto.abriu_lactacao` (ver `fazenda.rules.parto`) só existe a partir da
    migração `3bd371891acd`, mas esta função também é chamada por UMA
    migração ANTERIOR na cadeia (`c1a2b3d4e5f6_lactacao.py`, que reconstrói
    o histórico de lactações a partir dos partos já gravados) — um
    `alembic upgrade` do ZERO replaya essa chamada ANTES de a coluna existir
    fisicamente na tabela. `select(Parto)` lista TODAS as colunas mapeadas
    pela classe Python ATUAL, então confere o schema de verdade primeiro:
    sem isso, todo `alembic upgrade` do zero quebraria ao re-executar aquela
    migração antiga assim que `Parto` ganhasse qualquer coluna nova.
    """
    tem_abriu_lactacao = "abriu_lactacao" in {
        c["name"] for c in sa_inspect(session.get_bind()).get_columns("parto")
    }
    query_partos = select(Parto) if tem_abriu_lactacao else select(
        Parto.id, Parto.numero_matriz, Parto.data_parto, Parto.tipo_parto, Parto.animal_id, Parto.fazenda_id,
    )
    partos = [p for p in session.exec(_escopo(query_partos, Parto, fazenda_id)).all()
              if p.data_parto and eh_parto_produtivo(p)]
    secagens = session.exec(_escopo(select(Secagem), Secagem, fazenda_id)).all()

    secagens_por_matriz: dict[str, list[date]] = {}
    for s in secagens:
        if s.data_secagem:
            secagens_por_matriz.setdefault(s.numero_matriz, []).append(s.data_secagem)
    secagem_id_por_chave = {
        (s.numero_matriz, s.data_secagem): s.id for s in secagens if s.data_secagem
    }

    partos_por_matriz: dict[str, list[Parto]] = {}
    for p in partos:
        partos_por_matriz.setdefault(p.numero_matriz, []).append(p)

    criadas = fechadas = 0
    for numero, lista in partos_por_matriz.items():
        lista.sort(key=lambda p: p.data_parto)
        datas_secagem = sorted(secagens_por_matriz.get(numero, []))
        for i, parto in enumerate(lista):
            inicio = parto.data_parto
            lactacao = abrir_lactacao(
                session, numero_matriz=numero, data_inicio=inicio, origem=ORIGEM_IMPORTACAO,
                parto_id=parto.id, animal_id=parto.animal_id, fazenda_id=parto.fazenda_id,
                observacao="Reconstruída a partir do histórico de partos.",
            )
            criadas += 1

            proximo_parto = lista[i + 1].data_parto if i + 1 < len(lista) else None
            # A secagem que fecha esta lactação é a primeira DEPOIS do parto
            # (estritamente: secar no mesmo dia do parto não é secagem desta
            # lactação) e, quando há um parto seguinte, anterior a ele.
            secagem_da_janela = next(
                (d for d in datas_secagem if d > inicio and (proximo_parto is None or d < proximo_parto)),
                None,
            )
            fim = secagem_da_janela or proximo_parto
            if fim is not None:
                lactacao.data_fim = fim
                if secagem_da_janela is not None:
                    lactacao.secagem_id = secagem_id_por_chave.get((numero, secagem_da_janela))
                session.add(lactacao)
                fechadas += 1

    return {"criadas": criadas, "fechadas": fechadas}


# ---------------------------------------------------------------------------
# Compatibilidade com o campo congelado
# ---------------------------------------------------------------------------
def sincronizar_del_do_animal(
    session: Session, *, numero_matriz: str, data: date | None = None, fazenda_id: int | None = None,
) -> int | None:
    """Reescreve `Animal.del_dias` com o DEL ao vivo da lactação aberta.

    Existe só por COMPATIBILIDADE: `Animal.del_dias` é um campo congelado que
    boa parte das telas ainda lê. A migração de todos esses consumidores para
    ler a `Lactacao` direto é a Peça 1 (motor de estado único), fora do
    escopo desta rodada — até lá, manter o campo em dia no momento do evento
    evita que a Ficha e o lançamento de controle discordem entre si.

    Não dá commit."""
    dia = data or date.today()
    del_atual = del_vivo(session, numero_matriz=numero_matriz, data=dia, fazenda_id=fazenda_id)
    query = _escopo(select(Animal).where(Animal.numero == numero_matriz), Animal, fazenda_id)
    animal = session.exec(query).first()
    if animal is None:
        return del_atual
    animal.del_dias = del_atual
    animal.atualizado_em = datetime.utcnow()
    session.add(animal)
    return del_atual


def sincronizar_categoria_do_animal(
    session: Session, *, numero_matriz: str, fazenda_id: int | None = None,
) -> tuple[str | None, str | None]:
    """Troca a palavra "gestante" por "vazia" em `Animal.categoria_completa`/
    `categoria_abrev`, no momento em que uma gestação termina (parto, aborto
    ou natimorto) — sem isso, os dois campos (escritos só pelo upload do
    GERAL.csv) continuam dizendo "gestante" indefinidamente depois de um
    aborto, mesmo com o `Parto` lançado, a lactação aberta e controle
    leiteiro em andamento (caso relatado: novilha "14", abortou 30/07/2026,
    categoria seguiu "Novilha gestante").

    Só troca a PALAVRA "gestante" — preserva o resto do texto do Ideagri que
    não temos como reconstruir aqui (ex.: "Vaca gestante 3ª lact." vira "Vaca
    vazia 3ª lact.", não um texto genérico inventado). Textos que não têm a
    palavra ficam intocados, mesmo critério conservador de `_categoria_ao_vivo`
    (`api/routers/animais.py`) — que resolve a transição "novilha" -> "vaca"
    mas nunca tratou esta ("gestante" -> "vazia").

    Não dá commit."""
    query = _escopo(select(Animal).where(Animal.numero == numero_matriz), Animal, fazenda_id)
    animal = session.exec(query).first()
    if animal is None:
        return None, None

    def _tira_gestante(texto: str | None) -> str | None:
        if not texto or "gestante" not in texto.lower():
            return texto
        return re.sub("gestante", "vazia", texto, flags=re.IGNORECASE)

    animal.categoria_completa = _tira_gestante(animal.categoria_completa)
    animal.categoria_abrev = _tira_gestante(animal.categoria_abrev)
    animal.atualizado_em = datetime.utcnow()
    session.add(animal)
    return animal.categoria_completa, animal.categoria_abrev
