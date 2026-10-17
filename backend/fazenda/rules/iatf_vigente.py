"""
Quem está num protocolo IATF VIGENTE — a regra que impede lançar a mesma
matriz duas vezes no mesmo ciclo hormonal.

## O problema

Colocar uma matriz num protocolo IATF é decidir que ela vai ser inseminada
daqui a ~11 dias. Se, no meio do caminho, ela entra de novo num protocolo
(outro lançamento, ou "adicionar a um em andamento" com o animal já em outro),
ou recebe uma inseminação de cio natural / monta natural enquanto o hormônio
ainda corre, o rebanho passa a ter dois ciclos para o mesmo animal: duas
agendas, dupla baixa de hormônio, e uma inseminação que "não fecha" o
protocolo que ficou aberto.

Antes isto era barrado só pela memória de quem lançava; a tela de Lançamentos
agora mostra a matriz desabilitada com o motivo, e este módulo é a mesma regra
do lado do servidor (que é quem manda).

## Definição de "vigente" (por animal)

Um animal está em protocolo vigente quando existe um lançamento de protocolo
IATF que:

  * está ativo (não foi cancelado) e não foi encerrado manualmente na Central
    de Protocolos;
  * tem etapas dele (`ProtocoloIatfAplicacao`);
  * ainda NÃO teve serviço lançado depois do D0 — mesma definição de
    `pronta_para_inseminar` em `GET /reproducao/protocolo-iatf/ativos`
    (`_vigente`): a inseminação em si encerra o ciclo;
  * não está abandonado: o dia da inseminação (maior dia do animal no
    lançamento) ainda não passou de `GRACA_ABANDONO_DIAS`. É a mesma tolerância
    de `GRACA_D11_ATRASADO_DIAS` da lista de "em andamento"; sem ela, um
    protocolo esquecido (ninguém inseminou nem encerrou) bloquearia a matriz
    para sempre.

Função de leitura apenas — não grava nada.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from sqlmodel import Session, select

from fazenda.models import ProtocoloIatfAplicacao, ProtocoloIatfLancamento, Servico

# Mesmo valor de reproducao.GRACA_D11_ATRASADO_DIAS (a lista "em andamento"
# esconde o protocolo vencido por mais do que isto). Duplicado de propósito: o
# router importa regras, não o contrário.
GRACA_ABANDONO_DIAS = 7

MOTIVO_EM_PROTOCOLO = "em_protocolo"


@dataclass(frozen=True)
class ProtocoloVigente:
    lancamento_id: int
    nome_protocolo: str
    data_d0: date


def protocolos_vigentes_por_animal(
    session: Session, *, fazenda_id: int | None, hoje: date | None = None,
    numeros: Iterable[str] | None = None,
) -> dict[str, ProtocoloVigente]:
    """número da matriz -> protocolo IATF vigente em que ela está.

    `numeros` restringe o resultado (e a leitura de serviços) aos animais
    pedidos; sem ele, devolve todos da fazenda. Se a matriz estiver em mais de
    um lançamento vigente (dado legado), vale o de D0 mais recente.
    """
    hoje = hoje or date.today()
    alvo = set(numeros) if numeros is not None else None

    q_lanc = select(ProtocoloIatfLancamento).where(
        ProtocoloIatfLancamento.ativo == True,  # noqa: E712
        ProtocoloIatfLancamento.encerrado_em.is_(None),
    )
    if fazenda_id is not None:
        q_lanc = q_lanc.where(ProtocoloIatfLancamento.fazenda_id == fazenda_id)
    lancamentos = {l.id: l for l in session.exec(q_lanc).all()}
    if not lancamentos:
        return {}

    q_ap = select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.lancamento_id.in_(list(lancamentos)))
    if fazenda_id is not None:
        q_ap = q_ap.where(ProtocoloIatfAplicacao.fazenda_id == fazenda_id)
    por_animal_lanc: dict[tuple[str, int], list[ProtocoloIatfAplicacao]] = {}
    for ap in session.exec(q_ap).all():
        if alvo is not None and ap.numero_matriz not in alvo:
            continue
        por_animal_lanc.setdefault((ap.numero_matriz, ap.lancamento_id), []).append(ap)
    if not por_animal_lanc:
        return {}

    q_serv = select(Servico.numero_matriz, Servico.data_servico)
    if fazenda_id is not None:
        q_serv = q_serv.where(Servico.fazenda_id == fazenda_id)
    datas_servico: dict[str, list[date]] = {}
    envolvidos = {n for n, _ in por_animal_lanc}
    for numero, data_servico in session.exec(q_serv).all():
        if data_servico is not None and numero in envolvidos:
            datas_servico.setdefault(numero, []).append(data_servico)

    resultado: dict[str, ProtocoloVigente] = {}
    for (numero, lanc_id), aps in por_animal_lanc.items():
        lanc = lancamentos[lanc_id]
        if any(d >= lanc.data_d0 for d in datas_servico.get(numero, [])):
            continue  # a inseminação já foi lançada: o ciclo acabou
        maior_dia = max(a.dia for a in aps)
        data_insem = max(a.data_prevista for a in aps if a.dia == maior_dia)
        if hoje > data_insem + timedelta(days=GRACA_ABANDONO_DIAS):
            continue  # protocolo abandonado
        atual = resultado.get(numero)
        if atual is None or lanc.data_d0 > atual.data_d0:
            resultado[numero] = ProtocoloVigente(lanc.id, lanc.nome_protocolo, lanc.data_d0)
    return resultado


def mensagem_em_protocolo(numero: str, p: ProtocoloVigente, *, acao: str) -> str:
    """Texto único para o 409 e para a tela: `acao` completa a frase."""
    return (
        f"{numero} já está em protocolo IATF vigente (“{p.nome_protocolo}”, D0 em {p.data_d0.strftime('%d/%m/%Y')}) — {acao}"
    )
