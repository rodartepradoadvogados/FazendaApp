"""
Auditoria da classificação reprodutiva: o estado que o sistema dá a cada animal bate com os dados que ele apresenta?

Existem duas leituras do mesmo animal e elas já divergiram:

  * o ESTADO AO VIVO (`estado_reprodutivo.classificar_animal`): serviço de data mais recente que não seja futuro, depois
    do último parto OU início de lactação aberta; vale o exame de data mais recente (toque × retoque);
  * o ROTEIRO DO VETERINÁRIO (`agenda_veterinario.classificar_rebanho`): serviço de data mais recente (inclusive futuro),
    depois do último PARTO (lactação não conta), com toque e retoque lidos em campos separados.

Esta auditoria não decide qual está certa: aponta onde elas discordam entre si ou dos registros brutos, e diz a causa em
português claro. Só leitura. Cada achado traz `codigo`, `severidade` (alta | media), `titulo`, `explicacao` e, quando
cabe, as datas envolvidas — o suficiente para o administrador corrigir o dado (ou a regra) com segurança.

  reconfirmada_nao_gestante      há prenhez confirmada (toque/retoque positivo, sem perda) e o estado não é gestante/
                                 inseminada, SEM que um parto explique. Causas: data do serviço futura ou ausente,
                                 lactação aberta depois do serviço sem parto.
  classificadores_divergem       estado ao vivo e roteiro do veterinário em lados opostos (um diz prenha/inseminada, o
                                 outro diz vazia ou nenhuma lista).
  datas_incoerentes              toque antes da inseminação, retoque antes do toque, exame no futuro, resultado sem data
                                 (ou data sem resultado), resultado fora de POSITIVO/NEGATIVO/INDEFINIDO/ABERTO.
  ult_ocorrencia_diverge         a marca `ult_ocorrencia` (lida pelas candidatas de IATF e pelo histórico) não aponta o
                                 serviço mais recente por data.
  gestante_alem_do_parto_previsto  gestante com mais de (parto previsto + 21) dias e sem parto lançado: provavelmente já
                                 pariu e o parto não foi registrado.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fazenda.rules.estado_reprodutivo import GESTANTE, INSEMINADA, _d, _get, diagnostico_efetivo_do_servico

POSITIVO = "POSITIVO"
VOCABULARIO = {"POSITIVO", "NEGATIVO", "INDEFINIDO", "ABERTO", ""}
# Listas do roteiro do veterinário em que um animal "prenha ou inseminada" aparece.
LISTAS_PRENHA_OU_INSEMINADA = (
    "inseminadas_1_29", "inseminadas_30_59", "inseminadas_60_mais", "novilhas_gestantes", "vacas_gestantes",
    "verificar_pre_parto",
)
TOLERANCIA_PARTO_DIAS = 21
GESTACAO_MAXIMA_DIAS = 295  # Gir/Zebu: o teto das raças tratadas pelo sistema


def _fmt(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "sem data"


def _achado(numero: str, estado: str | None, roteiro: list[str], codigo: str, severidade: str, titulo: str, explicacao: str, **extra: Any) -> dict:
    return {"numero": numero, "estado": estado, "roteiro": roteiro, "codigo": codigo, "severidade": severidade,
            "titulo": titulo, "explicacao": explicacao, **extra}


def _positivo_vigente(servico: Any) -> bool:
    """Prenhez confirmada neste serviço: o exame que vale é POSITIVO e não há perda registrada."""
    return diagnostico_efetivo_do_servico(servico) == POSITIVO and _d(_get(servico, "data_perda_prenhez")) is None


def _causa_de_nao_ser_gestante(
    servico: Any, *, hoje: date, partos: list[date], lactacao_inicio: date | None,
) -> tuple[str, str] | None:
    """Por que um serviço com prenhez confirmada NÃO sustenta o estado gestante. None = há um motivo legítimo
    (o animal pariu depois, ou o serviço foi superado por um posterior) e não é inconsistência."""
    ds = _d(_get(servico, "data_servico"))
    if ds is None:
        return "sem_data", "o serviço não tem data da inseminação: o estado ao vivo descarta serviço sem data"
    if ds > hoje:
        return "data_futura", f"a data da inseminação ({_fmt(ds)}) é futura: o estado ao vivo ignora serviço de data futura, o roteiro do veterinário não"
    if any(p >= ds for p in partos):
        return None  # o ciclo terminou em parto: o estado "vazia/apta/atrasada" é o correto
    if lactacao_inicio is not None and lactacao_inicio >= ds:
        return "lactacao_sem_parto", (
            f"há uma lactação aberta em {_fmt(lactacao_inicio)}, depois da inseminação ({_fmt(ds)}), sem parto lançado: "
            "o estado ao vivo entendeu que a gestação acabou e o roteiro do veterinário não")
    return "desconhecida", "nenhuma das causas conhecidas explica; conferir os registros do animal"


def auditar(
    *,
    animais: list[dict],
    servicos_por_animal: dict[str, list[Any]],
    partos_por_animal: dict[str, list[date]],
    lactacao_inicio_por_animal: dict[str, date],
    estados: dict[str, dict],
    roteiro_por_animal: dict[str, list[str]],
    hoje: date,
) -> list[dict]:
    achados: list[dict] = []
    for animal in animais:
        numero = animal.get("numero")
        if not numero:
            continue
        estado_dict = estados.get(numero) or {}
        estado = estado_dict.get("estado")
        roteiro = roteiro_por_animal.get(numero, [])
        servicos = servicos_por_animal.get(numero, [])
        partos = partos_por_animal.get(numero, [])
        lactacao_inicio = lactacao_inicio_por_animal.get(numero)

        # 1. Prenhez confirmada que o estado não reconhece.
        if estado not in (GESTANTE, INSEMINADA):
            positivos = [s for s in servicos if _positivo_vigente(s)]
            # só o mais recente por data importa (os antigos pertencem a ciclos já encerrados)
            positivos.sort(key=lambda s: _d(_get(s, "data_servico")) or date.min)
            if positivos:
                s = positivos[-1]
                causa = _causa_de_nao_ser_gestante(s, hoje=hoje, partos=partos, lactacao_inicio=lactacao_inicio)
                posterior = any((_d(_get(o, "data_servico")) or date.min) > (_d(_get(s, "data_servico")) or date.min) for o in servicos if o is not s)
                if causa and not posterior:
                    achados.append(_achado(
                        numero, estado, roteiro, "reconfirmada_nao_gestante", "alta",
                        "Prenhez confirmada, mas o estado não é gestante",
                        f"O serviço de {_fmt(_d(_get(s, 'data_servico')))} tem diagnóstico positivo e sem perda, porém o animal consta como "
                        f"«{estado}»: {causa[1]}.",
                        causa=causa[0], servico_id=_get(s, "id"),
                    ))

        # 2. Os dois classificadores em lados opostos.
        prenha_no_roteiro = any(l in LISTAS_PRENHA_OU_INSEMINADA for l in roteiro)
        if estado in (GESTANTE, INSEMINADA) and not prenha_no_roteiro:
            achados.append(_achado(
                numero, estado, roteiro, "classificadores_divergem", "alta",
                "Estado ao vivo e roteiro do veterinário discordam",
                f"O estado ao vivo diz «{estado}», mas o roteiro do veterinário não coloca o animal em nenhuma lista de prenha/inseminada "
                f"({', '.join(roteiro) or 'nenhuma lista'}).",
            ))
        elif estado not in (GESTANTE, INSEMINADA) and estado is not None and prenha_no_roteiro:
            achados.append(_achado(
                numero, estado, roteiro, "classificadores_divergem", "alta",
                "Estado ao vivo e roteiro do veterinário discordam",
                f"O estado ao vivo diz «{estado}», mas o roteiro do veterinário o lista como prenha/inseminada ({', '.join(roteiro)}).",
            ))

        # 3. Datas e resultados incoerentes, serviço a serviço.
        for s in servicos:
            ds = _d(_get(s, "data_servico"))
            dt = _d(_get(s, "data_diagnostico"))
            dr = _d(_get(s, "data_reconfirmacao"))
            rt = (_get(s, "diagnostico") or "").strip().upper()
            rr = (_get(s, "diagnostico_reconfirmacao") or "").strip().upper()
            problemas: list[str] = []
            if ds and dt and dt < ds:
                problemas.append(f"toque ({_fmt(dt)}) antes da inseminação ({_fmt(ds)})")
            if dt and dr and dr < dt:
                problemas.append(f"retoque ({_fmt(dr)}) antes do toque ({_fmt(dt)})")
            if ds and dr and not dt and dr < ds:
                problemas.append(f"retoque ({_fmt(dr)}) antes da inseminação ({_fmt(ds)})")
            if (dt and dt > hoje) or (dr and dr > hoje):
                problemas.append("exame com data no futuro")
            if rr and not dr:
                problemas.append("resultado do retoque sem data")
            if dr and not rr:
                problemas.append("data do retoque sem resultado")
            if rt in ("POSITIVO", "NEGATIVO", "INDEFINIDO") and not dt:
                problemas.append("resultado do toque sem data")
            for nome, v in (("toque", rt), ("retoque", rr)):
                if v not in VOCABULARIO:
                    problemas.append(f"resultado do {nome} fora do vocabulário («{v}»)")
            if problemas:
                achados.append(_achado(
                    numero, estado, roteiro, "datas_incoerentes", "media",
                    "Datas ou resultados incoerentes no serviço",
                    f"Serviço de {_fmt(ds)}: " + "; ".join(problemas) + ".", servico_id=_get(s, "id"),
                ))

        # 4. Marca ult_ocorrencia.
        if servicos:
            marcados = [s for s in servicos if _get(s, "ult_ocorrencia") == 1]
            mais_recente = max(servicos, key=lambda s: (_d(_get(s, "data_servico")) or date.min, _get(s, "id") or 0))
            if len(marcados) != 1 or marcados[0] is not mais_recente:
                achados.append(_achado(
                    numero, estado, roteiro, "ult_ocorrencia_diverge", "media",
                    "A marca de «último serviço» não aponta o mais recente",
                    f"Serviços marcados como último: {len(marcados)}; o mais recente por data é o de "
                    f"{_fmt(_d(_get(mais_recente, 'data_servico')))}. Telas que leem a marca (candidatas de IATF, histórico) "
                    "podem mostrar outro serviço.",
                ))

        # 5. Gestante que já deveria ter parido.
        dias_gest = estado_dict.get("dias_gestacao")
        if estado == GESTANTE and dias_gest is not None and dias_gest > GESTACAO_MAXIMA_DIAS + TOLERANCIA_PARTO_DIAS:
            achados.append(_achado(
                numero, estado, roteiro, "gestante_alem_do_parto_previsto", "media",
                "Gestante além do parto previsto",
                f"Gestante há {dias_gest} dias, mais de {GESTACAO_MAXIMA_DIAS + TOLERANCIA_PARTO_DIAS} dias sem parto lançado: "
                "provavelmente já pariu e o parto não foi registrado.",
            ))
    return achados


def explicar_animal(
    numero: str, *, servicos: list[Any], partos: list[date], lactacao_inicio: date | None, estado: dict | None,
    roteiro: list[str], hoje: date,
) -> dict:
    """A linha do tempo do animal e o passo a passo de como o sistema chegou ao estado dele — o que o administrador
    precisa para enxergar POR QUE um animal «positivo e reconfirmado» aparece como vazio atrasado."""
    estado = estado or {}
    linhas: list[dict] = []
    for s in sorted(servicos, key=lambda x: _d(_get(x, "data_servico")) or date.min):
        ds = _d(_get(s, "data_servico"))
        linhas.append({
            "data": ds.isoformat() if ds else None, "tipo": "servico",
            "texto": f"Serviço ({_get(s, 'tipo_servico') or '—'}) — toque {(_get(s, 'diagnostico') or 'sem resultado')} "
                     f"em {_fmt(_d(_get(s, 'data_diagnostico')))}; retoque {(_get(s, 'diagnostico_reconfirmacao') or 'sem resultado')} "
                     f"em {_fmt(_d(_get(s, 'data_reconfirmacao')))}"
                     + (f"; perda de prenhez em {_fmt(_d(_get(s, 'data_perda_prenhez')))}" if _get(s, "data_perda_prenhez") else ""),
            "servico_id": _get(s, "id"),
        })
    for p in partos:
        linhas.append({"data": p.isoformat(), "tipo": "parto", "texto": "Parto lançado"})
    if lactacao_inicio:
        linhas.append({"data": lactacao_inicio.isoformat(), "tipo": "lactacao", "texto": "Lactação aberta (início)"})
    linhas.sort(key=lambda l: l["data"] or "")

    passos: list[str] = []
    ancora = max([d for d in (max(partos) if partos else None, lactacao_inicio) if d], default=None)
    passos.append(
        f"Âncora do ciclo: {_fmt(ancora)} ({'último parto' if partos and ancora == max(partos) else 'início da lactação' if ancora else 'nenhuma'})."
        " Só serviços depois da âncora e que não sejam futuros contam para o estado.")
    vigentes = [
        s for s in servicos
        if (ds := _d(_get(s, "data_servico"))) is not None and ds <= hoje and (ancora is None or ds > ancora)
    ]
    vigentes.sort(key=lambda s: _d(_get(s, "data_servico")))
    if vigentes:
        v = vigentes[-1]
        passos.append(
            f"Serviço vigente: {_fmt(_d(_get(v, 'data_servico')))}; exame que vale: {diagnostico_efetivo_do_servico(v) or 'nenhum'}.")
    else:
        passos.append("Nenhum serviço vigente: o animal é classificado só por parto/lactação, idade e peso.")
    passos.append(f"Estado ao vivo: «{estado.get('estado') or '—'}». Roteiro do veterinário: {', '.join(roteiro) or 'nenhuma lista'}.")
    return {"numero": numero, "estado": estado.get("estado"), "roteiro": roteiro, "linha_do_tempo": linhas, "passos": passos}
