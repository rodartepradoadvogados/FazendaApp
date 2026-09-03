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

Mas um aborto **não é**, em geral, um parto produtivo: não gera cria, não
avança a ordem de parto, não entra no IEP, não conta no "3ª de 5 crias" da
Ficha nem na média de ordem de parto do rebanho. Exceção: um aborto que abre
lactação (`Parto.abriu_lactacao=True`, gravado quando o usuário responde
"sim" ao popup de abertura de lactação no encerramento de gestação) É
produtivo — a vaca entrou em lactação de verdade, funcionalmente equivalente
a uma cria para fins de contagem. A distinção física é `ordem_parto`:

    parto produtivo            -> ordem_parto = 1, 2, 3 … (sequência da matriz)
    aborto sem abrir lactação  -> ordem_parto = NULL
    aborto que abre lactação   -> ordem_parto = 1, 2, 3 … (conta na sequência)

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
    produtiva da matriz — ou seja, tudo que NÃO é aborto, MAIS o aborto que
    abriu lactação (`Parto.abriu_lactacao`).

    Usado por todo consumidor que conta partos: ordem de parto (a próxima
    ordem é a CONTAGEM dos produtivos, ver `proxima_ordem_parto`), "N de M
    crias" da Ficha, quadro por parto, IEP, ordem média do rebanho.

    Um aborto que abre lactação é, para fins de contagem, funcionalmente
    equivalente a uma cria: a vaca entrou em lactação, e a próxima gestação
    dela vai contar como a cria seguinte tanto quanto contaria depois de um
    parto normal (pedido explícito do usuário, 27/08/2026). A informação de
    que ESTE aborto específico abriu lactação vive em `Lactacao.origem`
    (`ORIGEM_ABORTO`), não em `Parto` — por isso `Parto.abriu_lactacao` é
    gravado UMA VEZ, no momento da criação do `Parto`, em vez desta função
    consultar `Lactacao` (que quebraria a pureza do módulo — ver docstring
    do arquivo).

    Deliberadamente NÃO olha só `ordem_parto is None`: partos importados de
    planilha legada podem vir sem ordem gravada e ainda assim serem partos de
    verdade. O critério é o TIPO do evento (mais o flag acima para o caso do
    aborto com lactação).
    """
    return not eh_aborto(parto) or bool(_get(parto, "abriu_lactacao"))


T = TypeVar("T")


def partos_produtivos(partos: Iterable[T]) -> list[T]:
    """Só os partos que contam como cria — atalho para o filtro acima."""
    return [p for p in partos if eh_parto_produtivo(p)]


def proxima_ordem_parto(partos: Iterable[Any]) -> int:
    """A ordem do PRÓXIMO parto produtivo da matriz: `len(produtivos) + 1`,
    SEMPRE — nunca `max(ordem_parto já gravado) + 1`, nem "`ordem_parto` do
    mais recente + 1".

    Havia uma versão anterior que confiava no `max()` do que já estava
    gravado, e só caía na contagem quando NENHUM parto anterior tinha ordem.
    Isso é exatamente o bug: o histórico importado do Ideagri TEM
    `ordem_parto` gravado, só que numa convenção diferente da deste app (a
    planilha usa base 0 — "0" para a 1ª cria —, aqui é base 1). Uma matriz
    com o 1º parto importado (`ordem_parto=0`, errado) que pare de novo AO
    VIVO pelo app pegava `max([0]) + 1 = 1` — o SEGUNDO parto, lançado
    corretamente, gravava ordem 1 também, e o erro nunca parava de se
    propagar para a frente.

    Por isso a regra agora é: NUNCA confiar em `ordem_parto` armazenado (seja
    de import, seja de um parto anterior) para decidir o próximo — sempre
    CONTAR os produtivos do zero. É também o motivo de `len(...)`, e não
    "`ordem_parto` do mais recente + 1" ordenado por essa coluna: esta
    dependeria de como o banco ordena NULLs (abortos sem lactação ficam com
    `ordem_parto=None` — em Postgres, `ORDER BY ordem_parto DESC` devolve os
    NULLs PRIMEIRO, ao contrário do SQLite, o que faria toda matriz com um
    aborto no histórico recomeçar a contagem do 1).

    Dado histórico sujo (import com convenção errada) se corrige com a
    ferramenta administrativa de reconstrução de `Parto.ordem_parto`
    (Configurações > Cadastro > Ordem de Parto), não confiando nele aqui.
    """
    return len(partos_produtivos(partos)) + 1
