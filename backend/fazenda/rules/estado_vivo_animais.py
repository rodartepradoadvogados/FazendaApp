"""Estado reprodutivo AO VIVO em lote para GET /animais/ e a ficha (campo `estado_reprodutivo`).

`Animal.categoria_completa` é texto importado do GERAL.csv; lançar protocolo/inseminação/diagnóstico não o reescreve.
Quem precisa do estado certo (ex.: o bot Hermes) lê `estado_reprodutivo` — o mesmo cálculo de
GET /indicadores/estados-reprodutivos (e da ferramenta do assistente `consultar_estados_reprodutivos`), com os rótulos
de `estado_reprodutivo.ROTULOS`. Carrega serviços/partos/IATF/pesagens/lactações em LOTE (sem N+1)."""
from __future__ import annotations

from datetime import date
from typing import Any, Sequence

from sqlmodel import Session, select

from fazenda.models import Animal, Lactacao, Parto, PesagemCorporal, ProtocoloIatfAplicacao, Servico
from fazenda.rules.estado_reprodutivo import ROTULOS, estados_ao_vivo
from fazenda.rules.parametros import (
    get_param, idade_apta_min_meses, idade_max_1a_cobertura_meses, peso_apta_min, pev_dias,
)

# Acima disto, carrega a fazenda inteira em vez de filtrar por `IN (...)` (limite de parâmetros do SQLite).
_LIMITE_IN = 500


def estados_vivos_por_animal(
    session: Session, animais: Sequence[Animal], *, fazenda_id: int | None, hoje: date,
    servicos: Sequence[Servico] | None = None, partos: Sequence[Parto] | None = None,
) -> dict[str, dict[str, Any]]:
    """{numero -> {"estado": codigo, "estado_reprodutivo": rotulo}} das FÊMEAS de `animais` (machos/sêmen ficam de
    fora). `servicos`/`partos` podem vir já carregados pelo chamador (a listagem os tem)."""
    femeas = [a for a in animais if a.numero and not a.eh_semen and a.sexo != "M"]
    if not femeas:
        return {}
    numeros = [a.numero for a in femeas]
    filtrar = len(numeros) <= _LIMITE_IN

    def carregar(modelo, coluna):
        q = select(modelo)
        if fazenda_id is not None:
            q = q.where(modelo.fazenda_id == fazenda_id)
        if filtrar:
            q = q.where(coluna.in_(numeros))
        return session.exec(q).all()

    servicos = servicos if servicos is not None else carregar(Servico, Servico.numero_matriz)
    partos = partos if partos is not None else carregar(Parto, Parto.numero_matriz)
    iatf = carregar(ProtocoloIatfAplicacao, ProtocoloIatfAplicacao.numero_matriz)

    peso_por: dict[str, float] = {}
    ultima: dict[str, date] = {}
    for pes in carregar(PesagemCorporal, PesagemCorporal.numero_matriz):
        if pes.numero_matriz not in ultima or pes.data_pesagem > ultima[pes.numero_matriz]:
            ultima[pes.numero_matriz] = pes.data_pesagem
            peso_por[pes.numero_matriz] = pes.peso_kg

    inicio_lactacao: dict[str, date] = {}
    for lact in carregar(Lactacao, Lactacao.numero_matriz):
        if (lact.data_fim is not None and lact.data_fim <= hoje) or lact.data_inicio is None:
            continue
        inicio_lactacao[lact.numero_matriz] = lact.data_inicio

    estados = estados_ao_vivo(
        femeas, hoje=hoje, partos=list(partos), servicos=list(servicos), aplicacoes_iatf=iatf,
        pev_dias=pev_dias(), del_max_1o_servico=int(get_param("meta_del_max_1o_servico", 100) or 100),
        peso_por_animal=peso_por, idade_apta_dias=int(idade_apta_min_meses() * 30.44),
        idade_atraso_dias=int(idade_max_1a_cobertura_meses() * 30.44), peso_apta_kg=peso_apta_min(),
        inicio_lactacao_por_animal=inicio_lactacao,
    )
    return {
        n: {"estado": e["estado"], "estado_reprodutivo": ROTULOS.get(e["estado"], e["estado"])}
        for n, e in estados.items()
    }
