"""
Estado reprodutivo AO VIVO — fonte única de verdade para as listas de Rebanho
(app de campo e site).

## Por que este módulo existe

Até aqui, TODA lista de Rebanho (Gestantes, Inseminadas, PEV, Aptas,
Atrasadas) era filtrada por `Animal.sit_rep` — um TEXTO congelado, importado
do GERAL.csv do Ideagri. Consequência: a lista só mudava no próximo upload de
CSV, nunca ao lançar um parto/serviço/diagnóstico no próprio sistema. Isso
produziu erros de classificação reais e perigosos, ex.:

  - novilha que pariu continuava listada como "gestante" (o parto não voltava
    para a lista de PEV);
  - vaca que já passou do PEV continuava em "PEV";
  - novilha recém-inseminada aparecia em "atrasadas";
  - vaca em protocolo de IATF aparecia em "aptas".

Aqui a classificação é recalculada a partir dos REGISTROS (Parto, Servico,
ProtocoloIatfAplicacao) toda vez que a lista é pedida. `sit_rep` e `del_dias`
não são mais consultados para decidir categoria.

## Matriz de exclusão (a ordem É a regra)

Cada animal recebe UM e apenas um estado. A primeira regra que casar vence —
por isso a ordem abaixo importa mais que qualquer condição individual:

  1. GESTANTE     diagnóstico POSITIVO no serviço vigente, sem perda de
                  prenhez e sem parto posterior.
  2. INSEMINADA   tem serviço vigente aguardando diagnóstico. Exclui
                  ATRASADA por definição: quem foi inseminada não está
                  atrasada, só espera o dia do toque.
  3. EM_PROTOCOLO dentro da janela D0–D11 de IATF e ainda SEM serviço neste
                  ciclo. Exclui APTA: quem está em protocolo já está sendo
                  trabalhada, não é candidata a novo serviço.
  4. PEV          pariu há menos de `pev_dias`. Descanso obrigatório.
  5. APTA         passou do PEV (vaca), ou teve diagnóstico negativo/perda
                  sem serviço depois, ou é novilha que atingiu idade e peso
                  de aptidão. É a definição dada pelo produtor.
  6. ATRASADA     seria APTA, mas já passou do DEL máximo para 1º serviço —
                  subconjunto de "deveria ter sido inseminada e não foi".
  7. NAO_APTA     novilha que ainda não atingiu idade/peso.
  8. VAZIA        fallback (sem dados suficientes para classificar).

"Serviço vigente" = último serviço com data POSTERIOR ao último parto. É esse
recorte que faz o parto zerar o ciclo — a correção central do bug da novilha
que pariu e continuava gestante.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

# Estados possíveis — mutuamente exclusivos (ver matriz no topo do módulo).
GESTANTE = "gestante"
INSEMINADA = "inseminada"
EM_PROTOCOLO = "em_protocolo"
PEV = "pev"
APTA = "apta"
ATRASADA = "atrasada"
NAO_APTA = "nao_apta"
VAZIA = "vazia"

ROTULOS = {
    GESTANTE: "Gestante",
    INSEMINADA: "Inseminada",
    EM_PROTOCOLO: "Em protocolo (IA atual)",
    PEV: "PEV",
    APTA: "Apta",
    ATRASADA: "Atrasada",
    NAO_APTA: "Não apta",
    VAZIA: "Vazia",
}

# Gestação média de bovino leiteiro — usada para prever o parto a partir da
# data do serviço que emprenhou.
DIAS_GESTACAO = 280
# Janela do protocolo IATF: D0 (implante) até D11 (inseminação).
DIA_FINAL_PROTOCOLO = 11

_POSITIVO = "POSITIVO"
_NEGATIVO = "NEGATIVO"


def _d(valor: Any) -> date | None:
    """Aceita date ou 'AAAA-MM-DD' (os dicts vêm de model_dump em alguns
    chamadores) e devolve date."""
    if valor is None or isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _get(obj: Any, campo: str) -> Any:
    """Lê tanto de objeto SQLModel quanto de dict — os dois formatos circulam
    no projeto (routers passam models; regras já achatadas passam dicts)."""
    if isinstance(obj, dict):
        return obj.get(campo)
    return getattr(obj, campo, None)


def classificar_animal(
    numero: str,
    *,
    hoje: date,
    partos: list[Any],
    servicos: list[Any],
    aplicacoes_iatf: list[Any],
    pev_dias: int,
    del_max_1o_servico: int | None,
    eh_vaca: bool,
    idade_dias: int | None = None,
    peso_kg: float | None = None,
    idade_apta_dias: int | None = None,
    peso_apta_kg: float | None = None,
) -> dict:
    """Estado reprodutivo de UM animal, recalculado dos registros.

    `partos`/`servicos`/`aplicacoes_iatf` são só os registros DESTE animal.
    Devolve o estado + os dados derivados que as telas mostram (dias de
    gestação, parto previsto, DEL, dados da inseminação), para a tela não ter
    que recalcular nada nem voltar ao banco.
    """
    datas_parto = sorted([d for d in (_d(_get(p, "data_parto")) for p in partos) if d])
    ultimo_parto = datas_parto[-1] if datas_parto else None
    del_dias = (hoje - ultimo_parto).days if ultimo_parto else None

    # Só o que veio DEPOIS do último parto conta para o ciclo atual — é isso
    # que faz um parto lançado hoje derrubar a gestação anterior.
    vigentes = [
        s for s in servicos
        if (ds := _d(_get(s, "data_servico"))) is not None
        and ds <= hoje
        and (ultimo_parto is None or ds > ultimo_parto)
    ]
    vigentes.sort(key=lambda s: _d(_get(s, "data_servico")))
    ultimo_servico = vigentes[-1] if vigentes else None

    base = {
        "numero": numero,
        "del_dias": del_dias,
        "data_ultimo_parto": ultimo_parto.isoformat() if ultimo_parto else None,
        "dias_gestacao": None,
        "parto_previsto": None,
        "data_servico": None,
        "tipo_servico": None,
        "protocolo": None,
        "dias_desde_servico": None,
    }

    if ultimo_servico is not None:
        ds = _d(_get(ultimo_servico, "data_servico"))
        base["data_servico"] = ds.isoformat() if ds else None
        base["tipo_servico"] = _get(ultimo_servico, "tipo_servico")
        base["protocolo"] = _get(ultimo_servico, "protocolo")
        base["dias_desde_servico"] = (hoje - ds).days if ds else None

        diagnostico = (_get(ultimo_servico, "diagnostico") or "").strip().upper()
        perdeu = _d(_get(ultimo_servico, "data_perda_prenhez")) is not None

        # 1. GESTANTE — prenhez confirmada e ainda de pé.
        if diagnostico == _POSITIVO and not perdeu:
            base["dias_gestacao"] = (hoje - ds).days if ds else None
            base["parto_previsto"] = (ds + timedelta(days=DIAS_GESTACAO)).isoformat() if ds else None
            return {**base, "estado": GESTANTE}

        # 2. INSEMINADA — serviço feito, resultado ainda em aberto. Vence
        #    ATRASADA: não há o que fazer com ela além de esperar o toque.
        if diagnostico not in (_POSITIVO, _NEGATIVO) and not perdeu:
            return {**base, "estado": INSEMINADA}

    # 3. EM_PROTOCOLO — dentro de D0–D11 e sem serviço neste ciclo.
    d0 = _d0_protocolo_ativo(aplicacoes_iatf, hoje)
    if d0 is not None:
        servico_no_ciclo = any(
            (ds := _d(_get(s, "data_servico"))) is not None and ds >= d0 for s in vigentes
        )
        if not servico_no_ciclo:
            return {
                **base,
                "estado": EM_PROTOCOLO,
                "protocolo_d0": d0.isoformat(),
                "protocolo_dia_atual": (hoje - d0).days,
            }

    # 4. PEV — descanso pós-parto obrigatório.
    if del_dias is not None and del_dias < pev_dias:
        return {**base, "estado": PEV}

    # 5/6. APTA x ATRASADA (vaca) — passou do PEV e está livre para servir.
    if eh_vaca or ultimo_parto is not None:
        if del_max_1o_servico is not None and del_dias is not None and del_dias > del_max_1o_servico:
            return {**base, "estado": ATRASADA}
        return {**base, "estado": APTA}

    # 7. Novilha nulípara: aptidão por idade E peso, conforme parâmetros.
    atingiu_idade = idade_apta_dias is None or (idade_dias is not None and idade_dias >= idade_apta_dias)
    atingiu_peso = peso_apta_kg is None or (peso_kg is not None and peso_kg >= peso_apta_kg)
    if atingiu_idade and atingiu_peso and (idade_dias is not None or peso_kg is not None):
        return {**base, "estado": APTA}
    return {**base, "estado": NAO_APTA}


def _d0_protocolo_ativo(aplicacoes_iatf: list[Any], hoje: date) -> date | None:
    """D0 do protocolo IATF em andamento (janela D0..D11 contendo hoje), ou
    None. Agrupa por lançamento: as 4 linhas D0/D7/D9/D11 são UM protocolo,
    não quatro (ver também a ficha do animal, que contava 4 IATFs)."""
    por_lancamento: dict[Any, list[Any]] = {}
    for ap in aplicacoes_iatf:
        por_lancamento.setdefault(_get(ap, "lancamento_id"), []).append(ap)

    d0_ativo: date | None = None
    for aplicacoes in por_lancamento.values():
        datas_d0 = [
            d for ap in aplicacoes
            if _get(ap, "dia") == 0 and (d := _d(_get(ap, "data_prevista"))) is not None
        ]
        if not datas_d0:
            continue
        d0 = min(datas_d0)
        if d0 <= hoje <= d0 + timedelta(days=DIA_FINAL_PROTOCOLO):
            # Mais de um protocolo aberto (não deveria) → vale o mais recente.
            if d0_ativo is None or d0 > d0_ativo:
                d0_ativo = d0
    return d0_ativo


def descrever_servico(servico: Any) -> str:
    """Texto curto do tipo de serviço para as listas: distingue monta natural
    de IA e, sendo IA, cio natural de IATF (pedido do produtor na lista de
    Inseminadas)."""
    tipo = (_get(servico, "tipo_servico") or "").strip()
    protocolo = (_get(servico, "protocolo") or "").strip()
    tipo_l = tipo.lower()
    if "monta" in tipo_l or "natural" in tipo_l and "cio" not in tipo_l:
        return "Monta natural"
    if protocolo and protocolo.lower() not in ("cio natural", "cio", "-", "—"):
        return f"IA — IATF ({protocolo})"
    return "IA — cio natural"
