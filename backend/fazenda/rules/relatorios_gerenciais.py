"""
Relatórios gerenciais e de manejo reprodutivo.

Duas famílias:
- MANEJO: 8 listas semaforizadas (verde/amarelo/vermelho) que dizem o que fazer
  HOJE com cada animal (PEV, a inseminar, inseminados, toque/confirmação,
  prenhes, secagem, previsão de partos, estoque de sêmen).
- GERENCIAL: 7 análises/gráficos que medem a velocidade e a eficiência do
  programa reprodutivo (distribuição de DEL, prenhezes por DEL, dias para
  diagnóstico, intervalo entre serviços, dias para re-inseminação, taxa de
  serviço/prenhez, fluxo mensal de vacas em lactação).

Referência conceitual: ABS Monitor / DairyComp. As funções são puras: recebem
listas de dicts (já achatadas dos modelos) e a data de hoje, e devolvem
estruturas prontas para o front desenhar.
"""
from __future__ import annotations

from datetime import date, timedelta

from fazenda.rules.estado_reprodutivo import APTA, ATRASADA, GESTANTE, INSEMINADA, ROTULOS, estados_ao_vivo
from fazenda.rules.gestation import dias_gestacao
from fazenda.rules.parametros import (
    dias_reinseminacao_max,
    dias_reinseminacao_min,
    get_param,
    idade_apta_min_meses as _idade_apta_min_meses,
    idade_max_1a_cobertura_meses as _idade_max_1a_cobertura_meses,
    meta_taxa_servico,
    peso_apta_min as _peso_apta_min,
)

# Gestação média usada SÓ no IEP agregado do gráfico de distribuição de DEL
# (estatística por faixa de todo o rebanho, sem animal associado — não dá
# pra usar a gestação por raça aí). Toda previsão POR ANIMAL (parto/secagem
# em `relatorios_manejo` e `fluxo_lactacao`, abaixo) usa a gestação
# ESPECÍFICA da raça do bicho (`fazenda.rules.gestation.dias_gestacao`) — a
# mesma regra usada pela Agenda (`agenda_engine.py`) e por `producao.py::
# secagem-info`. Antes este módulo usava 280 dias fixos pra TODO animal,
# inclusive Girolando (287) e Gir/Zebu/Nelore (295): a previsão de secagem
# do Rebanho ficava até 15 dias adiantada em relação à da Agenda para
# raças não-Holandês, fazendo as duas telas "discordarem" da mesma vaca.
GESTACAO_DIAS = 280

# Quando a previsão de secagem (baseada na concepção em curso) já passou há
# mais que isso sem o animal ter sido secado, o atraso deixa de ser real —
# é sinal de parto/secagem que não foi lançado a tempo (dado histórico
# incompleto), não de um animal que precisa ser secado retroativamente hoje.
# Nesse caso considera-se secada 60 dias antes do último parto (ver uso em
# `relatorios_manejo` e em `animais.py::ficha_animal`) em vez de seguir
# cobrando o usuário animal por animal.
LIMITE_SECAGEM_RETROATIVA_DIAS = 60


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _dias(de: date | None, ate: date | None) -> int | None:
    if isinstance(de, date) and isinstance(ate, date):
        return (ate - de).days
    return None


def _eh_vaca(numero: str, partos_por_animal: dict[str, list[dict]]) -> bool:
    """Vaca = tem pelo menos um parto registrado; senão é novilha."""
    return bool(partos_por_animal.get(numero))


def _ultimo_parto(numero: str, partos_por_animal: dict[str, list[dict]]) -> date | None:
    datas = [p["data_parto"] for p in partos_por_animal.get(numero, []) if p.get("data_parto")]
    return max(datas) if datas else None


def _servicos_do_animal(numero: str, servicos_por_animal: dict[str, list[dict]]) -> list[dict]:
    servs = servicos_por_animal.get(numero, [])
    return sorted(servs, key=lambda s: (s.get("data_servico") or date.min))


def _ultimo_servico(numero: str, servicos_por_animal: dict[str, list[dict]]) -> dict | None:
    servs = _servicos_do_animal(numero, servicos_por_animal)
    return servs[-1] if servs else None


def _ultimo_servico_positivo(
    numero: str, servicos_por_animal: dict[str, list[dict]],
    partos_por_animal: dict[str, list[dict]] | None = None,
) -> dict | None:
    """Serviço VIGENTE da matriz (o mais recente — e, quando
    `partos_por_animal` é informado, também posterior ao último parto), SE
    ele estiver positivo e sem perda de prenhez registrada. Não é "o último
    serviço positivo do histórico": um serviço mais novo (mesmo sem
    diagnóstico ainda) ou um parto já encerram aquela prenhez — contá-la
    mesmo assim fazia uma vaca reinseminada sem diagnóstico (ou já parida)
    continuar aparecendo como prenhe, com previsão de parto/secagem de uma
    gestação que não existe mais (ver fazenda.rules.perda_prenhez)."""
    servs = _servicos_do_animal(numero, servicos_por_animal)
    if partos_por_animal is not None:
        ultimo_parto = _ultimo_parto(numero, partos_por_animal)
        if ultimo_parto is not None:
            servs = [s for s in servs if s.get("data_servico") and s["data_servico"] > ultimo_parto]
    if not servs:
        return None
    ultimo = servs[-1]
    if (ultimo.get("diagnostico") or "").strip().upper() == "POSITIVO" and not ultimo.get("data_perda_prenhez"):
        return ultimo
    return None


def _indexar(servicos: list[dict], partos: list[dict]) -> tuple[dict, dict]:
    serv_idx: dict[str, list[dict]] = {}
    for s in servicos:
        m = s.get("numero_matriz")
        if m:
            serv_idx.setdefault(m, []).append(s)
    parto_idx: dict[str, list[dict]] = {}
    for p in partos:
        m = p.get("numero_matriz")
        if m:
            parto_idx.setdefault(m, []).append(p)
    return serv_idx, parto_idx


def _indexar_secagens(secagens: list[dict] | None) -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = {}
    for s in secagens or []:
        m = s.get("numero_matriz")
        if m:
            idx.setdefault(m, []).append(s)
    return idx


def _ultima_secagem(numero: str, secagens_por_animal: dict[str, list[dict]]) -> date | None:
    datas = [s["data_secagem"] for s in secagens_por_animal.get(numero, []) if s.get("data_secagem")]
    return max(datas) if datas else None


# ===========================================================================
# MANEJO — 8 listas semaforizadas
# ===========================================================================
def relatorios_manejo(animais: list[dict], servicos: list[dict], partos: list[dict],
                      semen: list[dict], hoje: date, secagens: list[dict] | None = None,
                      aplicacoes_iatf: list[dict] | None = None,
                      peso_por_animal: dict[str, float] | None = None) -> dict:
    pev = int(get_param("pev_dias", 45) or 45)
    meta_1a = int(get_param("meta_del_max_1o_servico", 100) or 100)
    dias_toque = int(get_param("dias_toque", 30) or 30)
    dias_reconf = int(get_param("dias_reconfirmacao", 30) or 30)
    visita_vet = int(get_param("intervalo_visita_vet", 30) or 30)
    seco = int(get_param("periodo_seco_dias", 60) or 60)

    serv_idx, parto_idx = _indexar(servicos, partos)
    secagem_idx = _indexar_secagens(secagens)
    femeas = [a for a in animais if a.get("ativo") and not a.get("eh_semen") and a.get("sexo") != "M"]
    # Sexado/convencional por nome do touro — fallback para serviços antigos
    # que não gravaram tipo_semen no momento da inseminação (ver Servico.tipo_semen).
    tipo_semen_por_touro: dict[str, str] = {}
    for s in semen:
        nome = (s.get("touro_nome") or "").strip().lower()
        if nome:
            tipo_semen_por_touro.setdefault(nome, s.get("tipo") or "convencional")

    # Estado reprodutivo AO VIVO de cada fêmea, recalculado dos registros —
    # substitui os três booleanos que liam `sit_rep` (congelado no último
    # GERAL.csv). `servicos`/`partos` aqui já são o histórico completo
    # passado pelo chamador, então `classificar_animal` enxerga o ciclo
    # vigente corretamente (posterior ao último parto).
    estados_vivos = estados_ao_vivo(
        femeas,
        hoje=hoje,
        partos=partos,
        servicos=servicos,
        aplicacoes_iatf=aplicacoes_iatf or [],
        pev_dias=pev,
        del_max_1o_servico=meta_1a,
        peso_por_animal=peso_por_animal or {},
        idade_apta_dias=int(_idade_apta_min_meses() * 30.44),
        idade_atraso_dias=int(_idade_max_1a_cobertura_meses() * 30.44),
        peso_apta_kg=_peso_apta_min(),
    )

    l_pev, l_inseminar, l_inseminados, l_tocar, l_reconfirmar = [], [], [], [], []
    l_prenhes, l_secagem, l_partos = [], [], []

    for a in femeas:
        num = a["numero"]
        grupo = a.get("grupo_primario")
        eh_vaca = _eh_vaca(num, parto_idx)
        dparto = _ultimo_parto(num, parto_idx)
        dpp = _dias(dparto, hoje) if dparto else None  # dias pós-parto
        us = _ultimo_servico(num, serv_idx)
        ups = _ultimo_servico_positivo(num, serv_idx, parto_idx)
        # `ups` já garante vigência (mais recente, positivo, sem perda) — não
        # precisa checar `data_perda_prenhez` de novo aqui (e checar em `us`,
        # como antes, estava errado: `us` é sempre o serviço MAIS recente,
        # que pode já ser outro, sem a perda, deixado por uma reinseminação).
        # `ups` continua sendo a fonte das DATAS (concepção, prevista de parto
        # e de secagem, abaixo) — só a CLASSIFICAÇÃO vem do estado ao vivo.
        estado_vivo = (estados_vivos.get(num) or {}).get("estado")
        prenhe = estado_vivo == GESTANTE
        inseminada = estado_vivo == INSEMINADA
        # "Vazia" aqui = disponível para receber serviço. NÃO usar o estado
        # VAZIA de estado_reprodutivo.py: `classificar_animal` nunca devolve
        # esse valor (está declarado, mas nenhum `return` o usa).
        vazia = estado_vivo in (APTA, ATRASADA)
        # Serviço em aberto = já tem data_servico lançada e ainda sem
        # diagnóstico — fonte viva (Servico), ao contrário de sit_rep (só
        # atualizado na importação de planilha; nunca pelos lançamentos do
        # próprio site, então fica desatualizado assim que o usuário lança um
        # serviço novo pelo app). Sem checar isto, um animal podia cair em "a
        # inseminar" (por sit_rep desatualizado) e em "inseminados" (pelo
        # Servico real) ao mesmo tempo — os dois nunca podem coexistir.
        tem_servico_aberto = bool(us is not None and us.get("data_servico") and not us.get("diagnostico") and not prenhe)
        # Novilha (nunca pariu) dispensa 2º toque/reconfirmação nesta fazenda —
        # uma vez tocada positiva já é considerada confirmada; só vacas passam
        # pelo 2º exame aos 60+ dias.
        reconfirmada_efetiva = bool(ups and (ups.get("data_reconfirmacao") or not eh_vaca))

        # 1) Vacas no PEV (0-45 DPP)
        if eh_vaca and dpp is not None and 0 <= dpp <= pev:
            cor = "vermelho" if dpp <= 14 else "amarelo" if dpp <= 29 else "verde"
            l_pev.append({"numero": num, "grupo": grupo, "dias_pos_parto": dpp,
                          "data_parto": dparto, "cor": cor})

        # 2) Vacas a inseminar (terminou PEV e não está prenhe nem aguardando diagnóstico)
        precisa_inseminar = (not prenhe and not inseminada and not tem_servico_aberto) and (
            (eh_vaca and dpp is not None and dpp >= pev) or (not eh_vaca and vazia)
        )
        # Corte de `a_descartar` só entra AQUI, não nas demais listas. Esta é
        # a única lista que pede uma AÇÃO (oferecer a vaca para serviço) que
        # contradiz a decisão de descarte já tomada. As outras são biológicas:
        # a vaca marcada a descartar que está prenhe continua precisando ser
        # secada e continua parindo — tirá-la de "prenhes", "secagem" ou
        # "previsão de partos" perderia trabalho real que ainda precisa
        # acontecer antes dela sair do rebanho.
        if precisa_inseminar and not a.get("a_descartar"):
            if eh_vaca and dpp is not None:
                if dpp > meta_1a or vazia and dpp > meta_1a:
                    cor = "vermelho"
                elif dpp >= meta_1a - 15:
                    cor = "amarelo"
                else:
                    cor = "verde"
                if vazia and dpp > meta_1a:
                    cor = "vermelho"
            else:
                cor = "verde"
            l_inseminar.append({"numero": num, "grupo": grupo, "dias_pos_parto": dpp,
                                 "eh_vaca": eh_vaca, "situacao": ROTULOS.get(estado_vivo, "—"), "cor": cor})

        # 3) Animais inseminados (aguardando diagnóstico)
        aguardando = inseminada or tem_servico_aberto
        if aguardando and us and us.get("data_servico"):
            di = _dias(us["data_servico"], hoje)  # dias de inseminada
            if di is not None:
                cor_di = "verde" if di < dias_toque else "amarelo" if di <= dias_toque + 30 else "vermelho"
                if di in (16, 17, 25, 26):
                    cor_cio = "amarelo"
                elif 18 <= di <= 24:
                    cor_cio = "vermelho"
                else:
                    cor_cio = None
                if (us.get("tipo_servico") or "") == "Monta natural":
                    tipo_ia = "Monta natural"
                elif us.get("protocolo"):
                    tipo_ia = "IATF"
                else:
                    tipo_ia = "Cio natural"
                tipo_semen = us.get("tipo_semen") or tipo_semen_por_touro.get((us.get("reprodutor") or "").strip().lower())
                l_inseminados.append({"numero": num, "grupo": grupo, "dias_inseminada": di,
                                      "data_ultima_ia": us.get("data_servico"), "touro": us.get("reprodutor"),
                                      "tipo": tipo_ia, "tipo_semen": tipo_semen, "cor_dias": cor_di, "cor_cio": cor_cio,
                                      "cor": cor_di})

                # 4a) Toque — já passou o período de toque e ainda sem diagnóstico
                if di >= dias_toque:
                    cor_t = "amarelo" if di <= dias_toque + visita_vet else "vermelho"
                    l_tocar.append({"numero": num, "grupo": grupo, "dias_inseminada": di,
                                    "touro": us.get("reprodutor"), "cor": cor_t})

        # 4b) Reconfirmação — positivo, passou dias de reconfirmação, ainda sem
        # reconfirmar. Só vacas: novilha (nunca pariu) dispensa o 2º toque
        # nesta fazenda, ver reconfirmada_efetiva. `ups.get("id") == us.get("id")`
        # garante que o último positivo (ups) ainda É o serviço mais recente do
        # animal — sem isso, um animal com uma nova IA aberta desde então (us
        # mais novo) caía aqui E em "a tocar" ao mesmo tempo, o que é
        # impossível: se já foi tocado (tem um positivo mais recente que
        # qualquer outro serviço), está para reconfirmar; se não foi tocado
        # (o serviço mais recente ainda está em aberto), está a tocar — nunca
        # os dois.
        if eh_vaca and ups and us and ups.get("id") == us.get("id") and ups.get("data_servico") and not ups.get("data_reconfirmacao"):
            dp = _dias(ups["data_servico"], hoje)
            if dp is not None and dp >= dias_toque + dias_reconf:
                cor_r = "amarelo" if dp <= dias_toque + dias_reconf + visita_vet else "vermelho"
                l_reconfirmar.append({"numero": num, "grupo": grupo, "dias_inseminada": dp, "cor": cor_r})

        # 5) Animais prenhes
        if prenhe and ups:
            concep = ups.get("data_servico")
            dias_gest = _dias(concep, hoje)
            # Dias de gestação ESPECÍFICOS da raça do animal (280/287/295 —
            # ver fazenda.rules.gestation), a mesma conta usada pela Agenda
            # (agenda_engine.py) e por producao.py::secagem-info — não o
            # GESTACAO_DIAS fixo de 280 daqui, que fazia esta previsão
            # divergir da Agenda para qualquer raça não-Holandês.
            dias_gest_raca = dias_gestacao(a.get("raca"))
            prev_parto = concep + timedelta(days=dias_gest_raca) if concep else None
            if not eh_vaca:
                cor = "branco"
                dpp_conc = None
            else:
                dpp_conc = _dias(dparto, concep) if (dparto and concep) else None  # dias pós-parto na concepção
                if dpp_conc is None:
                    cor = "verde"
                elif dpp_conc <= 150:
                    cor = "verde"
                elif dpp_conc <= 300:
                    cor = "amarelo"
                else:
                    cor = "vermelho"
            l_prenhes.append({"numero": num, "grupo": grupo, "dias_gestacao": dias_gest,
                              "dpp_concepcao": dpp_conc, "previsao_parto": prev_parto,
                              "reconfirmada": reconfirmada_efetiva, "cor": cor})

            # 6) Secagem — vaca prenhe em lactação. "Em lactação" AO VIVO (secagem
            # mais recente, se houver, é ANTERIOR ao último parto — senão já foi
            # secada nesse ciclo), não `Animal.del_dias` (congelado no valor do
            # último GERAL.csv, nunca atualizado por uma Secagem lançada no app —
            # uma vaca recém-parida pelo app nunca entrava aqui, e uma vaca
            # recém-secada pelo app nunca saía, ver auditoria ago/2026).
            ult_secagem = _ultima_secagem(num, secagem_idx)
            em_lactacao_viva = ult_secagem is None or (dparto is not None and ult_secagem < dparto)
            if eh_vaca and em_lactacao_viva and concep:
                prev_secagem = concep + timedelta(days=dias_gest_raca - seco)
                d_secar = _dias(hoje, prev_secagem)
                if d_secar is not None and d_secar < -LIMITE_SECAGEM_RETROATIVA_DIAS:
                    pass  # atraso implausível — considerada secada 60 dias antes do último parto, sai da pendência
                elif d_secar is not None and d_secar <= 60:  # só as próximas
                    if d_secar > 15:
                        cor, luzes = "verde", 0
                    elif d_secar >= 8:
                        cor, luzes = "amarelo", 0
                    elif d_secar >= 0:
                        cor, luzes = "vermelho", 1
                    else:
                        cor, luzes = "vermelho", 2
                    l_secagem.append({"numero": num, "grupo": grupo, "dias_para_secagem": d_secar,
                                     "previsao_secagem": prev_secagem, "luzes": luzes, "cor": cor})

            # 7) Previsão de partos — reconfirmada e >200 dias de gestação
            if reconfirmada_efetiva and dias_gest is not None and dias_gest > 200 and prev_parto:
                d_parir = _dias(hoje, prev_parto)
                if d_parir is not None:
                    if d_parir > 15:
                        cor, luzes = "verde", 0
                    elif d_parir >= 8:
                        cor, luzes = "amarelo", 0
                    elif d_parir >= 0:
                        cor, luzes = "vermelho", 1
                    else:
                        cor, luzes = "vermelho", 2
                    l_partos.append({"numero": num, "grupo": grupo, "dias_para_parto": d_parir,
                                    "previsao_parto": prev_parto, "dias_gestacao": dias_gest,
                                    "luzes": luzes, "cor": cor})

    # 8) Estoque de sêmen
    l_semen = []
    for s in semen:
        if not s.get("ativo", True):
            continue
        doses = s.get("doses") or 0
        tipo = (s.get("tipo") or "convencional").lower()
        if tipo == "sexado":
            cor = "vermelho" if doses < 5 else "amarelo" if doses <= 15 else "verde"
        else:
            cor = "vermelho" if doses < 15 else "amarelo" if doses <= 25 else "verde"
        l_semen.append({"touro_nome": s.get("touro_nome"), "codigo": s.get("codigo"),
                        "central": s.get("central"), "tipo": tipo, "doses": doses, "cor": cor})

    def _ordena(lst):
        return sorted(lst, key=lambda x: ({"vermelho": 0, "amarelo": 1, "verde": 2, "branco": 3}.get(x["cor"], 4),
                                          _chave_num(x.get("numero", ""))))

    return {
        "parametros": {"pev": pev, "meta_1a_ia": meta_1a, "dias_toque": dias_toque,
                       "dias_reconfirmacao": dias_reconf, "periodo_seco": seco},
        "pev": _ordena(l_pev),
        "a_inseminar": _ordena(l_inseminar),
        "inseminados": _ordena(l_inseminados),
        "a_tocar": _ordena(l_tocar),
        "a_reconfirmar": _ordena(l_reconfirmar),
        "prenhes": _ordena(l_prenhes),
        "secagem": _ordena(l_secagem),
        "previsao_partos": _ordena(l_partos),
        "estoque_semen": sorted(l_semen, key=lambda x: ({"vermelho": 0, "amarelo": 1, "verde": 2}.get(x["cor"], 3),
                                                        x.get("touro_nome") or "")),
    }


def _chave_num(n: str):
    try:
        return (0, float(n))
    except (TypeError, ValueError):
        return (1, str(n))


# ===========================================================================
# GERENCIAL — gráficos
# ===========================================================================
def _del_servico(s: dict) -> int | None:
    d = s.get("del_servico")
    if isinstance(d, (int, float)) and d >= 0:
        return int(d)
    ds, dp = s.get("data_servico"), s.get("data_ult_parto")
    if isinstance(ds, date) and isinstance(dp, date) and ds >= dp:
        return (ds - dp).days
    return None


def distribuicao_del(servicos: list[dict], ordem: int, del_min: int, del_max: int) -> dict:
    """Cada ponto = uma inseminação de determinada ordem (1ª, 2ª, 3ª, 4ª+),
    com o DEL na ocasião. Semáforo por PEV e Meta de dias para 1ª IA."""
    pev = int(get_param("pev_dias", 45) or 45)
    meta = int(get_param("meta_del_max_1o_servico", 100) or 100)

    pontos = []
    for s in servicos:
        o = s.get("ordem_tentativa") or 0
        if ordem >= 4:
            if o < 4:
                continue
        elif o != ordem:
            continue
        d = _del_servico(s)
        if d is None or d < del_min or d > del_max or d > 350:
            continue
        cor = "verde" if pev <= d <= meta else "amarelo" if d < pev else "vermelho"
        pontos.append({"numero": s.get("numero_matriz"), "del": d, "cor": cor})
    pontos.sort(key=lambda p: p["del"])

    total = len(pontos)
    no_periodo = sum(1 for p in pontos if p["cor"] == "verde")
    no_pev = sum(1 for p in pontos if p["cor"] == "amarelo")
    apos_meta = sum(1 for p in pontos if p["cor"] == "vermelho")

    def pct(n):
        return round(100 * n / total, 0) if total else 0

    tabela = [
        {"label": f"Inseminadas no período desejado (PEV a {meta}d)", "vacas": no_periodo,
         "atual": pct(no_periodo), "meta": 95, "cor": "verde" if pct(no_periodo) >= 95 else "vermelho"},
        {"label": "Inseminadas ainda dentro do PEV (antes do ideal)", "vacas": no_pev,
         "atual": pct(no_pev), "meta": 0, "cor": "verde" if no_pev == 0 else "vermelho"},
        {"label": f"Inseminadas após a meta de {meta} dias", "vacas": apos_meta,
         "atual": pct(apos_meta), "meta": 2, "cor": "verde" if pct(apos_meta) <= 2 else "vermelho"},
    ]
    return {"pontos": pontos, "pev": pev, "meta": meta, "tabela": tabela, "total": total}


def prenhezes_por_del(servicos: list[dict], del_min: int, del_max: int) -> dict:
    """Barras: nº de prenhezes por ciclo de 21 dias após o PEV. Linha: acumulado
    %. IEP projetado por faixa (concepção + gestação)."""
    pev = int(get_param("pev_dias", 45) or 45)
    positivos = [s for s in servicos if (s.get("diagnostico") or "").strip().upper() == "POSITIVO"]
    dels = [d for s in positivos if (d := _del_servico(s)) is not None and del_min <= d <= del_max]
    total = len(dels)

    faixas = [("PEV", 0, pev)]
    ini = pev + 1
    while ini <= 354:
        faixas.append((f"{ini} - {ini + 21}", ini, ini + 21))
        ini += 22
    faixas.append(("+354", 355, 10000))

    barras, acumulado = [], 0
    for label, lo, hi in faixas:
        n = sum(1 for d in dels if lo <= d <= hi)
        acumulado += n
        mid = (lo + min(hi, 354)) / 2
        iep = round((mid + GESTACAO_DIAS) / 30.44, 2) if n else 0
        barras.append({"faixa": label, "prenhezes": n,
                       "acumulado_pct": round(100 * acumulado / total, 0) if total else 0,
                       "iep_projetado": iep})
    return {"barras": barras, "total": total, "pev": pev}


def dias_para_diagnostico(servicos: list[dict], del_min: int, del_max: int) -> dict:
    """Histograma: dias entre serviço e diagnóstico. Faixa ideal = dias_toque."""
    toque = int(get_param("dias_toque", 30) or 30)
    reconf = int(get_param("dias_reconfirmacao", 30) or 30)
    dias = []
    for s in servicos:
        ds, dd = s.get("data_servico"), s.get("data_diagnostico")
        if isinstance(ds, date) and isinstance(dd, date) and dd >= ds:
            dias.append((dd - ds).days)
    faixas = [("0-20", 0, 20), (f"21-{toque}", 21, toque), (f"{toque+1}-45", toque + 1, 45),
              ("46-60", 46, 60), ("61-90", 61, 90), (">90", 91, 10000)]
    barras = [{"faixa": lbl, "servicos": sum(1 for d in dias if lo <= d <= hi)} for lbl, lo, hi in faixas]
    return {"barras": barras, "total": len(dias), "ideal_min": toque, "ideal_max": toque + reconf}


def _buckets_intervalo(valores: list[int]) -> list[dict]:
    faixas = [("1-3 dias", 1, 3), ("4-17 dias", 4, 17), ("18-24 dias", 18, 24),
              ("25-35 dias", 25, 35), ("36-48 dias", 36, 48), (">48 dias", 49, 100000)]
    total = len(valores)
    return [{"faixa": lbl, "servicos": (n := sum(1 for v in valores if lo <= v <= hi)),
             "pct": round(100 * n / total, 2) if total else 0} for lbl, lo, hi in faixas]


def _buckets_dias_reinseminacao(valores: list[int]) -> list[dict]:
    """Faixas do gráfico de dias-para-reinseminação — ao contrário de
    `_buckets_intervalo` (fixas), calculadas a partir da janela configurada
    em Configurações > Parâmetros > Reinseminação e observação de cio
    (dias_reinseminacao_min/max): antes da janela = reinseminação adiantada,
    dentro = dentro do padrão da fazenda, depois = atrasada."""
    minimo, maximo = dias_reinseminacao_min(), dias_reinseminacao_max()
    faixas = []
    if minimo > 1:
        faixas.append((f"1-{minimo - 1} dias (adiantada)", 1, minimo - 1))
    faixas.append((f"{minimo}-{maximo} dias (janela ideal)", minimo, maximo))
    faixas.append((f">{maximo} dias (atrasada)", maximo + 1, 100000))
    total = len(valores)
    return [{"faixa": lbl, "servicos": (n := sum(1 for v in valores if lo <= v <= hi)),
             "pct": round(100 * n / total, 2) if total else 0} for lbl, lo, hi in faixas]


def intervalo_entre_servicos(servicos: list[dict]) -> dict:
    """Distribuição do intervalo em dias entre serviços consecutivos."""
    intervalos = [s["intervalo_tentativas"] for s in servicos
                  if isinstance(s.get("intervalo_tentativas"), (int, float)) and s["intervalo_tentativas"] > 0]
    return {"barras": _buckets_intervalo([int(i) for i in intervalos]), "total": len(intervalos)}


def dias_para_reinseminacao(servicos: list[dict], partos: list[dict]) -> dict:
    """Dias desde que a vaca foi identificada VAZIA (diagnóstico negativo ou perda)
    até a re-inseminação (o serviço seguinte)."""
    serv_idx, _ = _indexar(servicos, partos)
    valores = []
    for num, servs in serv_idx.items():
        ordenados = sorted(servs, key=lambda s: (s.get("data_servico") or date.min))
        for i, s in enumerate(ordenados[:-1]):
            prox = ordenados[i + 1]
            vazia_em = None
            if (s.get("diagnostico") or "").strip().upper() == "NEGATIVO" and s.get("data_diagnostico"):
                vazia_em = s["data_diagnostico"]
            elif s.get("data_perda_prenhez"):
                vazia_em = s["data_perda_prenhez"]
            prox_serv = prox.get("data_servico")
            if vazia_em and isinstance(prox_serv, date) and prox_serv >= vazia_em:
                valores.append((prox_serv - vazia_em).days)
    return {"barras": _buckets_dias_reinseminacao(valores), "total": len(valores)}


def taxa_servico_prenhez(animais: list[dict], servicos: list[dict], partos: list[dict], hoje: date) -> dict:
    """Taxa de serviço e taxa de prenhez por faixa de DEL + acumulado de prenhas.
    Referências: meta de taxa de serviço aos 100d vem de Configurações >
    Parâmetros (`meta_taxa_servico`, editável); 75% até 150d e ≤10% aos 300d
    ainda não têm parâmetro equivalente, continuam fixos."""
    serv_idx, parto_idx = _indexar(servicos, partos)
    femeas = [a for a in animais if a.get("ativo") and not a.get("eh_semen") and a.get("sexo") != "M"
              and _eh_vaca(a["numero"], parto_idx)]

    faixas = [("0-50", 0, 50), ("51-100", 51, 100), ("101-150", 101, 150),
              ("151-200", 151, 200), ("201-250", 201, 250), ("251-300", 251, 300), (">300", 301, 100000)]
    linhas = []
    prenhas_acum = 0
    total_vacas = len(femeas)
    for lbl, lo, hi in faixas:
        na_faixa = []
        for a in femeas:
            dparto = _ultimo_parto(a["numero"], parto_idx)
            dpp = _dias(dparto, hoje) if dparto else None
            if dpp is not None and lo <= dpp <= hi:
                na_faixa.append(a)
        n = len(na_faixa)
        servidas = sum(1 for a in na_faixa if _ultimo_servico(a["numero"], serv_idx))
        # Gestação AO VIVO: `_ultimo_servico_positivo` é o mesmo predicado que
        # o estado GESTANTE de `estado_reprodutivo` (serviço vigente, posterior
        # ao último parto, positivo e sem perda). Antes contava `sit_rep ==
        # "Ges."`, o texto congelado — a vaca que engravidava pelo app não
        # entrava nesta curva até o próximo GERAL.csv.
        prenhas = sum(1 for a in na_faixa if _ultimo_servico_positivo(a["numero"], serv_idx, parto_idx))
        prenhas_acum += prenhas
        linhas.append({
            "faixa": lbl, "vacas": n,
            "taxa_servico": round(100 * servidas / n, 0) if n else 0,
            "taxa_prenhez": round(100 * prenhas / n, 0) if n else 0,
            "acumulado_prenhas_pct": round(100 * prenhas_acum / total_vacas, 0) if total_vacas else 0,
        })
    return {"linhas": linhas, "total_vacas": total_vacas,
            "parametros": {"meta_100d": meta_taxa_servico(), "meta_150d": 75, "max_300d": 10}}


def fluxo_lactacao(animais: list[dict], servicos: list[dict], partos: list[dict], hoje: date, meses: int = 8,
                    secagens: list[dict] | None = None) -> dict:
    """Projeção mensal do saldo de vacas em lactação: parte do total atual,
    subtrai as que vão secar e soma as que vão parir, mês a mês."""
    seco = int(get_param("periodo_seco_dias", 60) or 60)
    serv_idx, parto_idx = _indexar(servicos, partos)
    secagem_idx = _indexar_secagens(secagens)
    femeas = [a for a in animais if a.get("ativo") and not a.get("eh_semen") and a.get("sexo") != "M"]

    def _em_lactacao_viva(numero: str, dparto: date | None) -> bool:
        # Mesmo critério AO VIVO de `relatorios_manejo` (ver comentário lá,
        # item 6): secagem mais recente, se houver, ANTERIOR ao último parto
        # — senão já foi secada nesse ciclo. Não `Animal.del_dias`, congelado
        # no último GERAL.csv: uma vaca recém-secada pelo app nunca saía
        # daqui, e uma recém-parida nunca entrava, até o próximo upload.
        ult_secagem = _ultima_secagem(numero, secagem_idx)
        return ult_secagem is None or (dparto is not None and ult_secagem < dparto)

    em_lactacao = 0
    for a in femeas:
        num = a["numero"]
        dparto = _ultimo_parto(num, parto_idx)
        dpp = _dias(dparto, hoje) if dparto else None
        if dpp is not None and dpp > 0 and _em_lactacao_viva(num, dparto):
            em_lactacao += 1

    # Previsões por mês (chave AAAA-MM)
    secar_por_mes: dict[str, dict[str, int]] = {}
    parir_por_mes: dict[str, dict[str, int]] = {}
    for a in femeas:
        num = a["numero"]
        ups = _ultimo_servico_positivo(num, serv_idx, parto_idx)
        if not ups or not ups.get("data_servico"):
            continue
        # `ups` já É o sinal ao vivo de gestação (vigente, positivo, sem
        # perda — ver `_ultimo_servico_positivo`); não precisa nem deve
        # confirmar de novo com `sit_rep`. O filtro antigo (`sit_rep`
        # começando com "Vaz.") descartava daqui a matriz que engravidou pelo
        # app e cujo texto congelado ainda dizia vazia — some da projeção de
        # secagem/parto até o próximo GERAL.csv.
        concep = ups["data_servico"]
        reconf = bool(ups.get("data_reconfirmacao"))
        dias_gest_raca = dias_gestacao(a.get("raca"))
        prev_parto = concep + timedelta(days=dias_gest_raca)
        prev_secagem = concep + timedelta(days=dias_gest_raca - seco)
        dparto = _ultimo_parto(num, parto_idx)
        eh_vaca = _eh_vaca(num, parto_idx)
        if eh_vaca and _em_lactacao_viva(num, dparto) and prev_secagem >= hoje:
            k = prev_secagem.strftime("%Y-%m")
            secar_por_mes.setdefault(k, {"confirmada": 0, "prevista": 0})
            secar_por_mes[k]["confirmada" if reconf else "prevista"] += 1
        if prev_parto >= hoje:
            k = prev_parto.strftime("%Y-%m")
            parir_por_mes.setdefault(k, {"confirmada": 0, "prevista": 0})
            parir_por_mes[k]["confirmada" if reconf else "prevista"] += 1

    linhas = []
    saldo = em_lactacao
    ano, mes = hoje.year, hoje.month
    for _ in range(meses):
        k = f"{ano:04d}-{mes:02d}"
        sec = secar_por_mes.get(k, {"confirmada": 0, "prevista": 0})
        par = parir_por_mes.get(k, {"confirmada": 0, "prevista": 0})
        secar_tot = sec["confirmada"] + sec["prevista"]
        parir_tot = par["confirmada"] + par["prevista"]
        saldo = saldo - secar_tot + parir_tot
        linhas.append({
            "mes": k,
            "secar": secar_tot, "secar_confirmada": sec["confirmada"], "secar_prevista": sec["prevista"],
            "parir": parir_tot, "parir_confirmada": par["confirmada"], "parir_prevista": par["prevista"],
            "saldo_lactacao": saldo,
        })
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)

    return {"lactacao_inicial": em_lactacao, "linhas": linhas}
