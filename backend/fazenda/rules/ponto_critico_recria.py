"""
Motor de alerta do Ponto Crítico da Recria — fonte ADITIVA de eventos da
Agenda (mesmo espírito de fazenda.rules.lida/protocolo_customizado, fora do
AgendaEngine de propósito).

Decisão (a) do dono do produto: até aqui `JanelaPontoCritico` era um cadastro
morto — guardava doença/faixa de dias/antecedência, mas nenhum código lia a
tabela (o card "ponto crítico" do dashboard vem do cálculo ESTATÍSTICO de
fazenda.rules.coorte.ponto_critico() em cima da curva de OcorrenciaClinica,
ignorando esse cadastro por completo). Este módulo faz o cadastro virar aviso
de verdade: para cada janela ATIVA, avisa quando há animal (ativo, da
fazenda) ENTRANDO na faixa de risco — idade em dias entre
(dia_min - dias_antecedencia) e dia_max.

Sem janela ativa ou sem nenhum animal na faixa: nenhum evento (não inventa
urgência). Reaparece todo dia enquanto valer (mesma convenção do alerta de
estoque mínimo de sêmen em agenda.py) — a chave inclui a data, então marcar
"realizado" só dispensa o alerta daquele dia; se a lista de animais mudar
amanhã, o alerta volta.
"""
from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from fazenda.models import Animal, JanelaPontoCritico
from fazenda.ordenacao import chave_numero

PREFIXO_EVENTO = "ponto_critico_recria_"


def chave_evento(janela_id: int, data_ref: date) -> str:
    return f"{PREFIXO_EVENTO}{janela_id}_{data_ref.isoformat()}"


def eventos_agenda(
    session: Session, data: date, realizados: set[str], fazenda_id: int | None = None,
) -> list[dict]:
    """Um evento por janela ATIVA com pelo menos 1 animal entrando na faixa de
    risco na data de referência informada."""
    query_janelas = select(JanelaPontoCritico).where(JanelaPontoCritico.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_janelas = query_janelas.where(JanelaPontoCritico.fazenda_id == fazenda_id)
    janelas = session.exec(query_janelas).all()
    if not janelas:
        return []

    query_animais = select(Animal).where(Animal.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
    animais = [a for a in session.exec(query_animais).all() if a.data_nasc and not a.eh_semen]

    saida: list[dict] = []
    for j in janelas:
        chave = chave_evento(j.id, data)
        if chave in realizados:
            continue
        entrando_desde = max(0, j.dia_min - j.dias_antecedencia)
        alvo = sorted(
            (a.numero for a in animais if entrando_desde <= (data - a.data_nasc).days <= j.dia_max),
            key=chave_numero,
        )
        if not alvo:
            continue
        saida.append({
            "id": chave,
            "data": data.isoformat(),
            "categoria": "sanidade",
            "descricao": (
                f"Bezerras entrando na janela de risco de {j.doenca} "
                f"({j.dia_min} a {j.dia_max} dias) — {len(alvo)} animal(is)"
            ),
            "numero_animal": alvo[0] if len(alvo) == 1 else None,
            "observacao": "Animais: " + ", ".join(alvo),
            "fonte": "auto", "cor": "var(--dourado)", "ref": None,
            "tipo": "ponto_critico_recria",
            "janela_id": j.id, "doenca": j.doenca, "doenca_id": j.doenca_id,
            "dia_min": j.dia_min, "dia_max": j.dia_max,
            "animais": alvo,
        })
    return saida
