"""
Parto — o que conta como parto PRODUTIVO e o que é só "fim de gestação".

## Por que este módulo existe

A partir do endpoint único de encerramento de gestação (POST
/reproducao/encerramento-gestacao), TODO fim de gestação vira um `Parto`:
parto normal, natimorto e **aborto**. Antes, o aborto não gerava registro
nenhum — só carimbava `data_perda_prenhez` num `Servico` —, e o resultado era
o bug que originou esta correção: a Ficha continuava dizendo "novilha
gestante, sem parto" mesmo depois de o aborto ter sido lançado, a lactação
aberta e o controle leiteiro começado, porque toda a lógica ao vivo do
sistema pergunta "existe `Parto` para esta matriz?".

Criar o `Parto` do aborto resolve isso de uma vez para todos os consumidores
de "esta gestação acabou?" (estado reprodutivo, DEL ao vivo, categoria ao
vivo, PEV, corte de serviços da lactação anterior) sem precisar ensinar cada
um deles a também consultar uma tabela nova.

Mas um aborto **não é** um parto produtivo: não gera cria, não avança a
ordem de parto, não entra no IEP, não conta no "3ª de 5 crias" da Ficha nem
na média de ordem de parto do rebanho. A distinção física é `ordem_parto`:

    parto produtivo  -> ordem_parto = 1, 2, 3 … (sequência da matriz)
    aborto           -> ordem_parto = NULL

`eh_parto_produtivo` é o ÚNICO lugar que decide isso. Nenhum consumidor de
`Parto` deve inventar seu próprio critério (ex.: comparar `tipo_parto` com a
string "Aborto" na mão, ou assumir que `ordem_parto is None` só acontece em
dado legado) — importe daqui.

## Estado da migração dos consumidores

Os consumidores que CONTAM partos (ordem/quantidade/IEP) já passaram a
filtrar por `eh_parto_produtivo`. Os que perguntam "quando esta matriz
encerrou a última gestação?" (DEL ao vivo, estado reprodutivo, categoria ao
vivo) continuam olhando TODOS os partos de propósito — para eles o aborto
conta, e é exatamente esse o conserto. A varredura completa dos demais
consumidores é a Peça 1 (motor de estado único), fora do escopo desta
rodada.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Iterable, TypeVar

# Valor gravado em `Parto.tipo_parto` quando o fim de gestação foi um aborto.
# Mesmo texto que a importação de CSV do Ideagri já traz na coluna de tipo de
# parto real (ver fazenda/parsers/reprodutivo.py), de propósito: os partos
# importados e os lançados pelo app precisam ser reconhecíveis pelo mesmo
# critério.
TIPO_PARTO_ABORTO = "Aborto"

# Tipos de fim de gestação aceitos pelo endpoint de encerramento. "natimorto"
# É um parto produtivo (a vaca pariu, a lactação abre, a ordem de parto
# avança) — só a cria não sobreviveu; a distinção entra em `Parto.tipo_parto`
# e no motivo da perda de prenhez, não na produtividade do parto.
TIPO_PARTO_NORMAL = "Parto normal"
TIPO_PARTO_NATIMORTO = "Natimorto"


def _normalizar(texto: Any) -> str:
    """minúsculo, sem acento e sem espaço nas pontas — o texto de
    `tipo_parto` chega de três origens (app, CSV do Ideagri, digitação livre)
    e nenhuma delas garante caixa nem acentuação."""
    if not isinstance(texto, str):
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.strip().lower()


def _get(obj: Any, campo: str) -> Any:
    """Lê tanto de objeto SQLModel quanto de dict — os dois formatos circulam
    no projeto (routers passam models; regras já achatadas passam dicts).
    Mesmo helper de `fazenda.rules.perda_prenhez`."""
    if isinstance(obj, dict):
        return obj.get(campo)
    return getattr(obj, campo, None)


def eh_aborto(parto: Any) -> bool:
    """True quando este `Parto` representa um aborto (fim de gestação sem
    cria)."""
    return _normalizar(_get(parto, "tipo_parto")) == _normalizar(TIPO_PARTO_ABORTO)


def eh_natimorto(parto: Any) -> bool:
    """True quando este `Parto` representa um natimorto: a vaca pariu de
    verdade (conta como parto produtivo — ver `eh_parto_produtivo`), mas a
    cria não sobreviveu. Usado por quem precisa distinguir "pariu sem cria
    viva" de "pariu com cria numerada/S-N" (ex.: campo `cria` do quadro por
    parto e "Última cria" da Ficha) — não compare `tipo_parto` na mão fora
    daqui, mesmo critério do resto do módulo."""
    return _normalizar(_get(parto, "tipo_parto")) == _normalizar(TIPO_PARTO_NATIMORTO)


def eh_parto_produtivo(parto: Any) -> bool:
    """True quando este `Parto` conta como uma cria/lactação na vida
    produtiva da matriz — ou seja, tudo que NÃO é aborto.

    Usado por todo consumidor que conta partos: ordem de parto (a próxima
    ordem é `max(ordem dos produtivos) + 1`), "N de M crias" da Ficha, quadro
    por parto, IEP, ordem média do rebanho.

    Deliberadamente NÃO olha só `ordem_parto is None`: partos importados de
    planilha legada podem vir sem ordem gravada e ainda assim serem partos de
    verdade. O critério é o TIPO do evento.
    """
    return not eh_aborto(parto)


T = TypeVar("T")


def partos_produtivos(partos: Iterable[T]) -> list[T]:
    """Só os partos que contam como cria — atalho para o filtro acima."""
    return [p for p in partos if eh_parto_produtivo(p)]


def proxima_ordem_parto(partos: Iterable[Any]) -> int:
    """A ordem do PRÓXIMO parto produtivo da matriz, a partir do histórico
    dela.

    `max(...) + 1` sobre os produtivos, e não `len(partos) + 1` nem
    "`ordem_parto` do mais recente + 1": o primeiro conta abortos, e o
    segundo depende de ordenar por uma coluna que agora é NULL em parte das
    linhas — em Postgres, `ORDER BY ordem_parto DESC` devolve os NULLs
    PRIMEIRO (ao contrário do SQLite), o que faria toda matriz com um aborto
    no histórico recomeçar a contagem do 1.

    Sem nenhuma ordem gravada (histórico importado de planilha que não
    trouxe a coluna), cai na CONTAGEM dos produtivos — melhor que o antigo
    `(ordem or 0) + 1`, que devolvia 1 para uma vaca de cinco crias.
    """
    produtivos = partos_produtivos(partos)
    ordens = [o for o in (_get(p, "ordem_parto") for p in produtivos) if o is not None]
    if ordens:
        return max(ordens) + 1
    return len(produtivos) + 1
