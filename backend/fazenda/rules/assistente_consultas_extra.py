"""
Segunda leva de ferramentas de LEITURA do Assistente do site e do agente
externo (Hermes, via /agente): indicadores por data, ficha completa do animal,
sêmen e touros, fluxo de caixa / caixa real, RMCA, dietas e "remédios por
doença".

Mesmos princípios de `assistente_consultas.py` (leia o docstring de lá) — este
módulo só existe separado para a lista crescer sem mexer no arquivo grande:

- 100% somente leitura (nada aqui chama add/commit/flush; os testes rodam todas
  as ferramentas na sessão READ ONLY do /agente);
- ZERO cálculo novo: cada ferramenta chama a função/regra que o endpoint do site
  usa (`_chamar`). Onde o site calcula no NAVEGADOR (Fluxo de Caixa mensal/diário
  e Livro Caixa de Financeiro) a conta foi portada 1:1 de
  frontend/app/financeiro/page.tsx, com teste contra o endpoint;
- GETs do site que ESCREVEM (ex.: Alimentação `GET /alimentacao/` dá baixa
  automática de estoque) NÃO são chamados: a ferramenta usa só a parte pura
  de leitura;
- isolamento por fazenda em toda consulta; datas AAAA-MM-DD; período máx. 5 anos.

Registro: `fazenda.rules.assistente` junta `FERRAMENTAS` daqui às demais.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlmodel import Session, select

from fazenda.rules.assistente_consultas import (
    LIMITE_ANOS, MAX_LINHAS, ErroConsulta, _arred_js, _bool, _chamar, _com_erro, _contem, _cortar, _data,
    _DF, _DI, _escolha, _escopo, _inteiro, _iso, _no_periodo, _periodo, _schema, _sem_acento, _txt,
)


# ===========================================================================
# 1. Indicadores gerais por data
# ===========================================================================
_SECOES_INDICADORES = ("resumo", "rebanho", "reproducao", "producao", "benchmark", "tudo")
# Listas nominais (drill-down dos cards): ficam fora por padrão para não estourar o limite de bytes.
_LISTAS_NOMINAIS_REPRO = (
    "aptas_nums", "prenhes_programa_nums", "vazias_programa_nums", "partos_previstos_nums", "partos_previstos_datas",
    "gestantes_detalhe", "iep_por_matriz",
)
_LISTAS_NOMINAIS_PRODUCAO = ("controle_nums", "del_medio_animais")


def _indicadores_na_data(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers.indicadores import calcular_indicadores_fazenda
    from fazenda.rules.lactacao import em_lactacao_por_matriz

    hoje = date.today()
    ref = _data(entrada, "data") or hoje
    if abs((ref - hoje).days) > LIMITE_ANOS * 366:
        raise ErroConsulta(f"'data' a mais de {LIMITE_ANOS} anos de hoje. Informe uma data mais próxima (AAAA-MM-DD).")
    secao = _escolha(entrada, "secao", _SECOES_INDICADORES, "resumo")
    listas = _bool(entrada, "incluir_listas_nominais", False)

    ind = calcular_indicadores_fazenda(session, fazenda_id, ref)  # MESMO cálculo de GET /indicadores/?data=

    def _limpa(bloco: dict, nominais: tuple[str, ...]) -> dict:
        return {k: v for k, v in bloco.items() if listas or k not in nominais}

    saida: dict[str, Any] = {"data_referencia": ref.isoformat(), "e_hoje": ref == hoje}
    if secao in ("resumo", "rebanho", "tudo"):
        saida["rebanho"] = ind["rebanho"]
    if secao in ("resumo", "reproducao", "tudo"):
        saida["reproducao"] = _limpa(ind["reproducao"], _LISTAS_NOMINAIS_REPRO)
    if secao in ("resumo", "producao", "tudo"):
        saida["producao"] = _limpa(ind["producao"], _LISTAS_NOMINAIS_PRODUCAO)
    if secao in ("benchmark", "tudo"):
        saida["benchmark"] = ind["benchmark"]
        saida["benchmark_categorias"] = ind["benchmark_categorias"]
        saida["reproducao_categorias"] = {
            cat: {k: v for k, v in blocos.items() if listas or not k.endswith("_nums")}
            for cat, blocos in (ind.get("reproducao_categorias") or {}).items()
        }

    # "Em lactação em D" pela fonte única do sistema (tabela Lactação — rules/lactacao.py):
    # é a única contagem que acompanha a data (abertura por parto/aborto/indução e fechamento por secagem).
    abertas = em_lactacao_por_matriz(session, data=ref, fazenda_id=fazenda_id)
    dels = [(ref - l.data_inicio).days for l in abertas.values()]
    saida["lactacao_na_data_pela_tabela_lactacao"] = {
        "vacas_em_lactacao": len(abertas),
        "del_medio_dias": round(sum(dels) / len(dels), 1) if dels else None,
        "regra": "Lactação aberta em D = começou em D ou antes e ainda não fechou (secagem) até D (rules/lactacao.py).",
    }
    saida["limitacoes"] = [
        "O site NÃO guarda histórico/snapshot dos indicadores: o parâmetro 'data' só pede ao cálculo para considerar "
        "a data de referência (DEL, prazos, partos previstos, situação reprodutiva) usando os registros que existem HOJE.",
        "rebanho.vacas_lactacao/vacas_secas/pre_parto vêm do LOTE ATUAL de cada animal ativo, não da data; "
        "para 'quantas vacas em lactação em D' use lactacao_na_data_pela_tabela_lactacao.vacas_em_lactacao.",
        "Animais baixados (vendidos/mortos) depois de D não entram nos totais do rebanho; registros posteriores a D "
        "(serviços, partos) também são considerados.",
        "Para taxas reprodutivas e produção de um PERÍODO exato use consultar_indicadores_reprodutivos e consultar_producao_leite.",
    ] if ref != hoje else [
        "Foto de hoje (mesmo número da Capa/Indicadores do site). Para outra data veja 'limitacoes' ao informar 'data'.",
    ]
    return saida


# ===========================================================================
# 2. Ficha completa do animal
# ===========================================================================
_SECOES_FICHA = (
    "cadastro", "genealogia", "estado_reprodutivo", "previsoes", "lactacoes", "partos", "servicos", "diagnosticos",
    "protocolos", "sanidade", "exames", "ocorrencias", "producao", "qualidade_leite", "pesagens", "movimentacoes",
    "comercial", "secagens", "agenda", "colostragem", "linha_tempo_sanitaria", "curvas",
)
_SECOES_FICHA_PADRAO = ("cadastro", "genealogia", "estado_reprodutivo", "previsoes", "lactacoes")
# seção -> (chave da ficha, campo de data usado para ordenar/filtrar)
_LISTAS_FICHA = {
    "partos": ("partos", "data_parto"),
    "servicos": ("servicos", "data_servico"),
    "sanidade": ("aplicacoes_sanitarias", "data_aplicacao"),
    "exames": ("exames_resultados", "data_exame"),
    "ocorrencias": ("ocorrencias_clinicas", "data_ocorrencia"),
    "producao": ("controles_leiteiros", "data_controle"),
    "qualidade_leite": ("qualidade_leite", "data_coleta"),
    "pesagens": ("pesagens_corporais", "data_pesagem"),
    "movimentacoes": ("movimentos_lote", "data_movimento"),
    "secagens": ("secagens", "data_secagem"),
    "agenda": ("eventos_agenda", "data_evento"),
    "linha_tempo_sanitaria": ("linha_tempo_sanitaria", "data"),
}
_CAMPOS_DIAGNOSTICO = (
    "data_servico", "reprodutor", "tipo_servico", "ordem_tentativa", "diagnostico", "data_diagnostico", "metodo_diagnostico",
    "data_perda_prenhez", "motivo_perda_prenhez", "parto_resultante_data",
)


def _parse_secoes(entrada: dict) -> tuple[str, ...]:
    bruto = _txt(entrada, "secoes")
    if not bruto:
        return _SECOES_FICHA_PADRAO
    pedidas = [_sem_acento(x).replace(" ", "_").replace("-", "_") for x in bruto.split(",") if x.strip()]
    if any(p in ("todas", "tudo") for p in pedidas):
        return tuple(x for x in _SECOES_FICHA if x != "curvas")
    invalidas = [p for p in pedidas if p not in _SECOES_FICHA]
    if invalidas:
        raise ErroConsulta(
            f"Seção(ões) inválida(s) em 'secoes': {', '.join(invalidas)}. Use: {', '.join(_SECOES_FICHA)} (ou 'todas')."
        )
    return tuple(dict.fromkeys(pedidas))


def _ficha_animal(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers.animais import ficha_animal
    from fazenda.api.routers.indicadores import estados_reprodutivos
    from fazenda.rules.lactacao import lactacoes_da_matriz

    numero = _txt(entrada, "numero")
    if not numero:
        raise ErroConsulta("Informe 'numero' do animal (brinco/matriz). Se o usuário não disse qual, pergunte.")
    secoes = _parse_secoes(entrada)
    ini, fim = _periodo(entrada, obrigatorio=False)
    maximo = _inteiro(entrada, "max_itens", 1, 500) or 100

    ficha = _chamar(ficha_animal, session, fazenda_id, numero=numero)  # MESMA ficha de GET /animais/{numero}/ficha
    animal = ficha["animal"]
    saida: dict[str, Any] = {"numero": numero, "secoes_incluidas": list(secoes), "totais": {}}
    if ini or fim:
        saida["periodo"] = {"data_inicio": _iso(ini), "data_fim": _iso(fim)}

    if "cadastro" in secoes:
        saida["cadastro"] = {k: _iso(v) for k, v in animal.items()}
    if "genealogia" in secoes:
        saida["genealogia"] = {
            "pai": ficha.get("pai"),
            "mae_numero": animal.get("mae_numero"), "mae_nome": animal.get("mae_nome"),
            **{k: _iso(v) for k, v in animal.items() if k.startswith(("pai_", "avo_", "bisavo_"))},
        }
    if "estado_reprodutivo" in secoes:
        vivo = _chamar(estados_reprodutivos, session, fazenda_id, data=date.today())  # GET /indicadores/estados-reprodutivos
        saida["estado_reprodutivo"] = next((e for e in vivo["animais"] if str(e.get("numero")) == numero), None) or {
            "aviso": "Estado reprodutivo ao vivo existe só para fêmeas ativas; este animal é macho, sêmen ou está inativo.",
        }
    if "previsoes" in secoes:
        saida["previsoes"] = {
            "previsao_parto": _iso(ficha.get("previsao_parto")), "previsao_secagem": _iso(ficha.get("previsao_secagem")),
            "precisao_parto": {k: _iso(v) for k, v in (ficha.get("precisao_parto") or {}).items()} or None,
        }
    if "lactacoes" in secoes:
        saida["lactacoes"] = {
            "quadro_por_parto": ficha.get("resumo_partos"), "ultima_cria": ficha.get("ultima_cria"),
            "registros_de_lactacao": [
                {"numero_lactacao": l.numero_lactacao, "data_inicio": _iso(l.data_inicio), "data_fim": _iso(l.data_fim),
                 "origem": l.origem, "aberta": l.data_fim is None}
                for l in lactacoes_da_matriz(session, numero_matriz=numero, fazenda_id=fazenda_id)
            ],
        }
    if "protocolos" in secoes:
        saida["protocolos"] = {
            "iatf": ficha.get("protocolos_iatf"), "sanitarios": ficha.get("protocolos_sanitarios"),
            "inducao_lactacao": ficha.get("inducao_lactacao"), "customizados": ficha.get("protocolos_customizados"),
        }
    if "colostragem" in secoes:
        saida["colostragem"] = ficha.get("colostragem")
    if "comercial" in secoes:
        saida["comercial"] = {k: ficha.get(k) for k in ("compras", "vendas", "baixa", "gtas")}
    if "curvas" in secoes:
        saida["curvas"] = {k: ficha.get(k) for k in ("curva_wood", "curva_referencia_rebanho", "curva_referencia_grupo_ordem_parto")}

    def _lista(secao: str, linhas: list[dict], campo_data: str) -> None:
        if ini or fim:
            linhas = [r for r in linhas if _no_periodo(r.get(campo_data), ini, fim)]
        linhas = sorted(linhas, key=lambda r: str(_iso(r.get(campo_data)) or ""), reverse=True)  # mais recentes primeiro
        saida["totais"][secao] = len(linhas)
        cortadas, cortou = _cortar(linhas, maximo)
        saida[secao] = [{k: _iso(v) for k, v in r.items()} for r in cortadas]
        if cortou:
            saida.setdefault("limitado_pelo_max_itens", []).append(secao)

    for secao, (chave, campo) in _LISTAS_FICHA.items():
        if secao in secoes:
            linhas = list(ficha.get(chave) or [])
            if secao == "servicos":
                linhas = [{k: v for k, v in r.items() if k != "touro"} for r in linhas]  # prova completa do touro: consultar_touros_catalogo
            _lista(secao, linhas, campo)
    if "diagnosticos" in secoes:
        diag = [{c: r.get(c) for c in _CAMPOS_DIAGNOSTICO} for r in (ficha.get("servicos") or [])]
        _lista("diagnosticos", diag, "data_servico")
    saida["como_ler"] = (
        "Mesma ficha da tela Rebanho › Ficha do animal (GET /animais/{numero}/ficha). Listas vêm das mais recentes para as mais "
        "antigas e 'totais' diz quantos registros existem; use 'secoes' (e data_inicio/data_fim, max_itens) para pedir só o que "
        "precisa. 'diagnosticos' é a visão dos serviços com o resultado do diagnóstico."
    )
    return saida


# ===========================================================================
# 3. Sêmen e touros
# ===========================================================================
_TIPOS_SEMEN = ("convencional", "sexado", "fazenda", "todos")
_ORDEM_TOUROS = ("tpi", "nm_dolar", "leite_kg", "gordura_kg", "proteina_kg", "tipo_composto", "ubere_composto",
                 "pernas_composto", "fertilidade_filhas", "facilidade_parto", "nome")


def _semen_ns(d: dict):
    from types import SimpleNamespace
    return SimpleNamespace(**d)


def _mapas_touros(session: Session) -> tuple[dict, dict, list]:
    from fazenda.models import Touro
    touros = session.exec(select(Touro)).all()  # catálogo GLOBAL (sem fazenda_id) — o mesmo do site
    return (
        {(t.naab or "").strip().upper(): t for t in touros},
        {(t.nome or "").strip().lower(): t for t in touros if t.nome},
        touros,
    )


def _estoque_semen(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers.cadastro.genetica import listar_estoque_semen, prova_media_semen, semen_disponivel
    from fazenda.rules.touros import casar_touro

    busca, local = _txt(entrada, "touro"), _txt(entrada, "local")
    tipo = _escolha(entrada, "tipo", _TIPOS_SEMEN, "todos")
    situacao = _escolha(entrada, "situacao", ("disponivel", "zerado", "todos"), "todos")
    incluir_inativos = _bool(entrada, "incluir_inativos", False)
    com_prova = _bool(entrada, "incluir_provas", False)

    itens = _chamar(listar_estoque_semen, session, fazenda_id)  # GET /cadastro/estoque-semen (Rebanho › Touros › Sêmen)
    painel = _chamar(semen_disponivel, session, fazenda_id)  # GET /cadastro/estoque-semen/disponivel (totais e mínimos)
    por_naab, por_nome, _todos = _mapas_touros(session)

    if not incluir_inativos:
        itens = [i for i in itens if i.get("ativo") is not False]
    if busca:
        itens = [i for i in itens if _contem(i.get("touro_nome"), busca) or _contem(i.get("naab"), busca) or _contem(i.get("codigo"), busca)]
    if tipo != "todos":
        itens = [i for i in itens if (i.get("tipo") or "convencional") == tipo]
    if local:
        itens = [i for i in itens if _contem(i.get("local_armazenamento"), local)]
    if situacao == "disponivel":
        itens = [i for i in itens if (i.get("doses") or 0) > 0]
    elif situacao == "zerado":
        itens = [i for i in itens if (i.get("doses") or 0) <= 0]

    linhas = []
    for i in itens:
        d = {
            "touro": i.get("touro_nome"), "naab": i.get("naab") or i.get("codigo"), "central": i.get("central"),
            "tipo": i.get("tipo"), "doses": i.get("doses") or 0, "valor_unitario": i.get("valor_unitario"),
            "valor_total_em_estoque": round((i.get("doses") or 0) * i["valor_unitario"], 2) if i.get("valor_unitario") is not None else None,
            "local_armazenamento": i.get("local_armazenamento"), "ativo": i.get("ativo") is not False,
            "observacao": i.get("observacao"),
        }
        if com_prova:
            t = casar_touro(_semen_ns(i), por_naab, por_nome)
            d["prova"] = {k: getattr(t, k) for k in ("tpi", "nm_dolar", "leite_kg", "gordura_kg", "proteina_kg", "fertilidade_filhas", "facilidade_parto")} if t else None
        linhas.append(d)
    por_tipo: dict[str, dict] = defaultdict(lambda: {"touros": 0, "doses": 0})
    for d in linhas:
        por_tipo[d["tipo"] or "convencional"]["touros"] += 1
        por_tipo[d["tipo"] or "convencional"]["doses"] += d["doses"]
    cortadas, cortou = _cortar(sorted(linhas, key=lambda d: (str(d["touro"] or "").lower())))
    saida: dict[str, Any] = {
        "total_touros": len(linhas), "total_doses": sum(d["doses"] for d in linhas), "por_tipo": dict(por_tipo),
        "painel_do_site": {
            "totais_convencional_sexado": painel["totais"], "minimos": painel["minimos"], "abaixo_minimo": painel["abaixo_minimo"],
        },
        "itens": cortadas, "limitado_pela_ferramenta": cortou,
        "como_ler": (
            "Estoque de sêmen da tela Rebanho › Touros › Sêmen (doses por touro). 'painel_do_site' = totais e estoque mínimo por categoria "
            "como a inseminação mostra (convencional e sexado; touro 'fazenda' = monta natural, sem dose). Itens inativos ficam de fora "
            "(incluir_inativos=true para ver). Não há controle de botijão/partida além de 'local_armazenamento' (ex.: Caneca 1)."
        ),
    }
    if com_prova:
        saida["prova_media_do_estoque"] = _chamar(prova_media_semen, session, fazenda_id)  # GET /cadastro/estoque-semen/prova-media
    return saida


def _touros_catalogo(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    import json as _json
    from fazenda.api.routers.cadastro.genetica import listar_touros
    from fazenda.models import EstoqueSemen
    from fazenda.rules.touros import casar_touro

    busca, central, raca = _txt(entrada, "busca"), _txt(entrada, "central"), _txt(entrada, "raca")
    no_estoque = _bool(entrada, "apenas_no_estoque", False)
    ordem = _escolha(entrada, "ordenar_por", _ORDEM_TOUROS, "tpi")
    extra = _bool(entrada, "incluir_dados_extra", False)

    touros = _chamar(listar_touros, session, fazenda_id)  # GET /cadastro/touros (catálogo global NAAB/provas)
    total_catalogo = len(touros)
    if busca:
        touros = [t for t in touros if any(_contem(t.get(c), busca) for c in ("nome", "nome_completo", "naab"))]
    if central:
        touros = [t for t in touros if _contem(t.get("central"), central) or _contem(t.get("fonte"), central)]
    if raca:
        touros = [t for t in touros if _contem(t.get("raca"), raca)]
    estoque: dict[str, int] = {}  # NAAB do catálogo -> doses desta fazenda
    por_naab, por_nome, _ = _mapas_touros(session)
    for e in session.exec(_escopo(select(EstoqueSemen), EstoqueSemen.fazenda_id, fazenda_id)).all():
        if e.ativo is False:
            continue
        t = casar_touro(e, por_naab, por_nome)
        if t is not None:
            estoque[t.naab] = estoque.get(t.naab, 0) + (e.doses or 0)
    if no_estoque:
        touros = [t for t in touros if estoque.get(t["naab"], 0) > 0]
    if ordem == "nome":
        touros.sort(key=lambda t: _sem_acento(t.get("nome") or t.get("naab")))
    else:
        touros.sort(key=lambda t: (t.get(ordem) is None, -(t.get(ordem) or 0)))  # maior primeiro; sem prova por último
    cortados, cortou = _cortar(touros)
    linhas = []
    for t in cortados:
        d = {k: _iso(v) for k, v in t.items() if k not in ("dados_extra", "id")}
        d["doses_em_estoque_na_fazenda"] = estoque.get(t["naab"], 0)
        if extra and t.get("dados_extra"):
            try:
                d["dados_extra_da_planilha"] = _json.loads(t["dados_extra"])
            except (ValueError, TypeError):
                d["dados_extra_da_planilha"] = None
        linhas.append(d)
    return {
        "total_encontrados": len(touros), "total_no_catalogo": total_catalogo, "ordenado_por": ordem,
        "touros": linhas, "limitado_pela_ferramenta": cortou,
        "como_ler": (
            "Catálogo genético GLOBAL de touros (NAAB/provas do fornecedor, igual à tela Rebanho › Touros) — não é só o que a fazenda tem. "
            "tpi/nm_dolar/leite_kg etc. são as provas; 'doses_em_estoque_na_fazenda' mostra se há sêmen dele no estoque desta fazenda. "
            "O sistema não tem uma coluna PRODIGENS própria: colunas extras da planilha do fornecedor ficam em dados_extra (incluir_dados_extra=true)."
        ),
    }


def _uso_semen(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers.cadastro.genetica import listar_estoque_semen, prova_ao_vivo_semen
    from fazenda.api.routers.relatorio_compra_semen import relatorio as relatorio_compras
    from fazenda.rules.reproducao_analise import resumo_periodo

    ini, fim = _periodo(entrada, obrigatorio=True)
    touro = _txt(entrada, "touro")
    tipo = _escolha(entrada, "tipo", _TIPOS_SEMEN, "todos")
    com_prova = _bool(entrada, "incluir_prova_ao_vivo", False)

    from fazenda.rules.assistente_consultas import _servicos_do_site
    regs = [r for r in _servicos_do_site(session, fazenda_id) if _no_periodo(r.get("data"), ini, fim)]
    if touro:
        regs = [r for r in regs if _contem(r.get("touro"), touro)]
    if tipo != "todos":
        regs = [r for r in regs if (r.get("tipo_semen") or "") == tipo]
    estoque = {str(e.get("touro_nome") or "").strip().lower(): e for e in _chamar(listar_estoque_semen, session, fazenda_id)}

    grupos: dict[str, list[dict]] = defaultdict(list)
    for r in regs:
        grupos[r.get("touro") or "(sem touro)"].append(r)
    por_touro = []
    for nome, g in grupos.items():
        resumo = resumo_periodo(g)  # MESMA conta da tela Análise reprodutiva, recortada neste touro
        est = estoque.get(nome.strip().lower())
        por_touro.append({
            "touro": nome, "naab": (est or {}).get("naab"), "tipo_semen": next((r["tipo_semen"] for r in g if r.get("tipo_semen")), (est or {}).get("tipo")),
            "servicos": resumo["servicos_total"], "diagnosticados": resumo["diagnosticados"], "positivos": resumo["positivos"],
            "negativos": resumo["negativos"], "sem_diagnostico": resumo["sem_diagnostico"],
            "taxa_concepcao_pct": resumo["taxa_concepcao_pct"], "perdas_prenhez": resumo["perdas_prenhez"],
            "doses_em_estoque_hoje": (est or {}).get("doses"),
        })
    por_touro.sort(key=lambda x: (-x["servicos"], x["touro"]))
    t = resumo_periodo(regs)

    compras = _chamar(
        relatorio_compras, session, fazenda_id, touro=touro, naab=None, vendedor=None, data_de=ini, data_ate=fim, numero_documento=None,
    )
    if tipo != "todos":
        compras = [c for c in compras if (c.get("tipo") or "") == tipo]
    comp_touro: dict[str, dict] = defaultdict(lambda: {"doses": 0, "valor_total": 0.0})
    for c in compras:
        comp_touro[c["touro_nome"]]["doses"] += c["doses"] or 0
        comp_touro[c["touro_nome"]]["valor_total"] = round(comp_touro[c["touro_nome"]]["valor_total"] + (c["valor_total"] or 0), 2)
    cortados, cortou = _cortar(por_touro)
    saida: dict[str, Any] = {
        "periodo": {"data_inicio": ini.isoformat(), "data_fim": fim.isoformat()},
        "filtros": {"touro": touro, "tipo": tipo},
        "total_servicos": t["servicos_total"], "taxa_concepcao_pct_geral": t["taxa_concepcao_pct"],
        "por_touro": cortados, "limitado_pela_ferramenta": cortou,
        "compras_no_periodo": {
            "total_doses": sum(v["doses"] for v in comp_touro.values()),
            "valor_total": round(sum(v["valor_total"] for v in comp_touro.values()), 2),
            "por_touro": [{"touro": k, **v} for k, v in sorted(comp_touro.items())],
        },
        "como_ler": (
            "Uso = serviços (IA/IATF/monta) lançados no período; 1 serviço de IA = 1 dose (monta natural/tipo 'fazenda' não usa dose). "
            "taxa_concepcao_pct = positivos ÷ diagnosticados (a mesma da tela Relatórios › Análise reprodutiva) — serviços recentes ainda sem "
            "diagnóstico não entram na taxa. Compras: relatório de compra de sêmen. Para comparar touros com mais filtros use "
            "consultar_indicadores_reprodutivos(agrupar_por='touro')."
        ),
    }
    if com_prova:
        saida["prova_ao_vivo"] = _chamar(prova_ao_vivo_semen, session, fazenda_id, de=ini.isoformat(), ate=fim.isoformat())
    return saida


# ===========================================================================
# 4. Fluxo de caixa (Financeiro › Fluxo de Caixa / Livro Caixa) e Caixa Real
# ===========================================================================
_VISOES_FLUXO = ("mensal", "diario", "livro", "por_conta")


def _contem_exato(texto: str | None, alvo: str | None) -> bool:
    return _sem_acento(texto) == _sem_acento(alvo)


def _fluxo_caixa(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers.financeiro import listar_lancamentos, plano_contas

    ini, fim = _periodo(entrada, obrigatorio=True)
    visao = _escolha(entrada, "visao", _VISOES_FLUXO, "mensal")
    centro = _txt(entrada, "centro_custo")
    tipo = _escolha(entrada, "tipo", ("entradas", "saidas", "todos"), "todos")
    fornecedor, conta = _txt(entrada, "fornecedor"), _txt(entrada, "conta")
    previsto = _bool(entrada, "incluir_previsto", False)

    regs = _chamar(listar_lancamentos, session, fazenda_id)["lancamentos"]  # GET /financeiro/lancamentos (o que a tela baixa)

    def _passa(r: dict, centro_ok: bool = True) -> bool:
        # Mesmos filtros da tela (frontend/app/financeiro/page.tsx, `filtrados`): centro de custo, tipo, fornecedor, conta
        # gerencial (a selecionada e todos os descendentes: "3.01" casa "3.01.02").
        if centro_ok and centro and not _contem_exato(r.get("centro_custo"), centro):
            return False
        if tipo != "todos" and r["tipo"] != ("receita" if tipo == "entradas" else "despesa"):
            return False
        if fornecedor and not _contem(r.get("fornecedor"), fornecedor):
            return False
        if conta:
            c = r.get("conta_completa") or r.get("codigo_conta") or ""
            if not (c == conta or c.startswith(conta + ".")):
                return False
        return True

    # Fluxo de Caixa e Livro Caixa = REGIME DE CAIXA: a data que vale é a do PAGAMENTO.
    no_periodo = [r for r in regs if r.get("data_pagamento") and _no_periodo(r["data_pagamento"], ini, fim)]
    filtrados = [r for r in no_periodo if _passa(r)]
    entradas = sum(r["valor"] for r in filtrados if r["tipo"] == "receita")
    saidas = sum(r["valor"] for r in filtrados if r["tipo"] == "despesa")

    centros: dict[str, dict] = {}
    for r in no_periodo:
        if not _passa(r, centro_ok=False):
            continue
        c = centros.setdefault(r.get("centro_custo") or "Sem centro de custo", {"entradas": 0.0, "saidas": 0.0})
        c["entradas" if r["tipo"] == "receita" else "saidas"] += r["valor"]

    saida: dict[str, Any] = {
        "periodo": {"data_inicio": ini.isoformat(), "data_fim": fim.isoformat()}, "regime": "caixa (data do pagamento)",
        "filtros": {"centro_custo": centro, "tipo": tipo, "fornecedor": fornecedor, "conta": conta}, "visao": visao,
        "totais": {"entradas": round(entradas, 2), "saidas": round(saidas, 2), "resultado": round(entradas - saidas, 2),
                   "lancamentos": len(filtrados)},
        "por_centro_custo": {
            k: {"entradas": round(v["entradas"], 2), "saidas": round(v["saidas"], 2), "resultado": round(v["entradas"] - v["saidas"], 2)}
            for k, v in sorted(centros.items())
        },
    }

    def _serie(chave) -> list[dict]:
        por: dict[str, dict] = {}
        for r in filtrados:
            k = chave(r)
            if not k:
                continue
            e = por.setdefault(k, {"entradas": 0.0, "saidas": 0.0, "lancamentos": 0})
            e["entradas" if r["tipo"] == "receita" else "saidas"] += r["valor"]
            e["lancamentos"] += 1
        acc, linhas = 0.0, []
        for k in sorted(por):
            e = por[k]
            acc += e["entradas"] - e["saidas"]
            linhas.append({"periodo": k, "entradas": round(e["entradas"], 2), "saidas": round(e["saidas"], 2),
                           "saldo": round(e["entradas"] - e["saidas"], 2), "acumulado": _arred_js(acc), "lancamentos": e["lancamentos"]})
        return linhas

    if visao == "mensal":
        saida["meses"], saida["limitado_pela_ferramenta"] = _cortar(_serie(lambda r: r.get("mes_caixa")))
    elif visao == "diario":
        saida["dias"], saida["limitado_pela_ferramenta"] = _cortar(_serie(lambda r: r.get("data_pagamento")))
    elif visao == "livro":
        acc, linhas = 0.0, []
        for r in sorted(filtrados, key=lambda r: r["data_pagamento"]):
            entrada_, saida_ = (r["valor"], 0.0) if r["tipo"] == "receita" else (0.0, r["valor"])
            acc += entrada_ - saida_
            linhas.append({"data": r["data_pagamento"], "descricao": r.get("descricao"), "fornecedor": r.get("fornecedor"),
                           "entrada": round(entrada_, 2), "saida": round(saida_, 2), "saldo": _arred_js(acc)})
        saida["lancamentos"], saida["limitado_pela_ferramenta"] = _cortar(linhas)
    else:  # por_conta: mesma hierarquia da DRE, uma coluna por mês
        nomes = {p["codigo"]: p["nome"] for p in _chamar(plano_contas, session, fazenda_id)}
        por: dict[str, dict] = {}
        for r in filtrados:
            folha, mes = r.get("conta_completa") or r.get("codigo_conta") or "", r.get("mes_caixa")
            if not folha or not mes:
                continue
            partes = folha.split(".")
            for i in range(len(partes)):
                codigo = ".".join(partes[: i + 1])
                nome_conhecido = nomes.get(codigo)
                if not nome_conhecido and i != len(partes) - 1:
                    continue  # nível intermediário sem nome cadastrado não gera linha (como na tela)
                e = por.setdefault(codigo, {"codigo": codigo, "nome": nome_conhecido or r.get("descricao") or codigo,
                                            "nivel": i + 1, "por_mes": {}, "total": 0.0})
                e["por_mes"][mes] = round(e["por_mes"].get(mes, 0.0) + r["valor"], 2)
                e["total"] = round(e["total"] + r["valor"], 2)
        saida["contas"], saida["limitado_pela_ferramenta"] = _cortar(sorted(por.values(), key=lambda e: e["codigo"]))

    if previsto:
        # Previsto = contas ainda EM ABERTO (sem data de pagamento) com vencimento no período, como na aba Contas a pagar/receber.
        abertas = [r for r in regs if not r.get("data_pagamento") and _no_periodo(r.get("data_vencimento") or r.get("data_competencia"), ini, fim) and _passa(r)]
        por_mes: dict[str, dict] = {}
        for r in abertas:
            m = (r.get("data_vencimento") or r.get("data_competencia") or "")[:7]
            e = por_mes.setdefault(m, {"a_receber": 0.0, "a_pagar": 0.0})
            e["a_receber" if r["tipo"] == "receita" else "a_pagar"] += r["valor"]
        pr, pg = sum(e["a_receber"] for e in por_mes.values()), sum(e["a_pagar"] for e in por_mes.values())
        saida["previsto_em_aberto"] = {
            "a_receber": round(pr, 2), "a_pagar": round(pg, 2), "resultado_previsto": round(pr - pg, 2), "lancamentos": len(abertas),
            "por_mes": [{"mes": m, "a_receber": round(e["a_receber"], 2), "a_pagar": round(e["a_pagar"], 2)} for m, e in sorted(por_mes.items())],
            "origem": "Contas ainda não pagas com vencimento no período (abas Contas a pagar/receber). Não é uma tela de 'previsto' do Fluxo de Caixa.",
        }
        saida["previsto_x_realizado"] = {
            "realizado_entradas": saida["totais"]["entradas"], "previsto_a_receber": round(pr, 2),
            "realizado_saidas": saida["totais"]["saidas"], "previsto_a_pagar": round(pg, 2),
        }
    saida["como_ler"] = (
        "Igual à tela Financeiro › Fluxo de Caixa (e Livro Caixa): REGIME DE CAIXA, só lançamentos PAGOS/RECEBIDOS, no mês/dia do pagamento; "
        "entradas = receitas, saídas = despesas, acumulado = soma corrida do período. A tela abre filtrada em 'Pecuária Leiteira' — "
        "sem centro_custo esta ferramenta soma todos os centros (veja por_centro_custo para citar cada um). Para regime de competência "
        "use executar_relatorio('dre'); para contas ainda a pagar/receber use consultar_contas_financeiras; para o saldo projetado "
        "futuro use consultar_caixa_real."
    )
    return saida


def _caixa_real(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers.financeiro import caixa_real

    if getattr(usuario, "papel", None) != "admin":
        raise ErroConsulta("O Caixa Real (saldo e projeção de liquidez) é restrito a administradores, como no site.")
    dias = _inteiro(entrada, "dias", 1, 730)
    r = _chamar(caixa_real, session, fazenda_id, dias=dias, _=usuario)  # GET /financeiro/caixa-real
    serie = r.pop("serie", [])
    com_movimento = [d for d in serie if d["entradas"] or d["saidas"]]
    cortados, cortou = _cortar(com_movimento)
    contas = [
        {"instituicao": str(c["nome"]).split("·")[0].strip(), "saldo": c["saldo"]}  # sem agência/número da conta (dado bancário)
        for c in r.pop("contas", [])
    ]
    for d in cortados:
        d["itens"] = d.get("itens", [])[:10]
    return {
        **r, "contas_correntes": contas,
        "dias_com_movimento": cortados, "limitado_pela_ferramenta": cortou,
        "como_ler": (
            "Mesma projeção da tela Financeiro › Caixa Real: saldo de partida = soma das contas correntes cadastradas; depois entram as contas "
            "AINDA NÃO PAGAS no dia do vencimento (vencidas entram no 1º dia). Não é a DRE. 'dias_com_movimento' mostra só os dias com entrada/saída."
        ),
    }


# ===========================================================================
# 5. RMCA (Receita Menos Custo com Alimentação)
# ===========================================================================
def _rmca(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    import calendar
    from fazenda.api.routers.financeiro import rmca

    ini, fim = _periodo(entrada, obrigatorio=True)
    por_mes = _bool(entrada, "por_mes", False)
    itens_fisicos = _bool(entrada, "incluir_itens_fisicos", False)

    def _um(a: date, b: date) -> dict:
        return _chamar(rmca, session, fazenda_id, data_inicio=a, data_fim=b)  # GET /financeiro/rmca

    r = _um(ini, fim)
    if not itens_fisicos:
        r["fisico"] = {**r["fisico"], "itens": [
            {k: it.get(k) for k in ("ingrediente", "quantidade", "unidade", "valor_unitario", "custo")} for it in r["fisico"]["itens"]
        ]}
    if por_mes:
        meses, cursor = [], ini.replace(day=1)
        if (fim.year - ini.year) * 12 + fim.month - ini.month >= 24:
            raise ErroConsulta("Para por_mes=true use no máximo 24 meses de período.")
        while cursor <= fim:
            a, b = max(cursor, ini), min(cursor.replace(day=calendar.monthrange(cursor.year, cursor.month)[1]), fim)
            m = _um(a, b)
            meses.append({"mes": cursor.strftime("%Y-%m"), "gerencial": m["gerencial"],
                          "fisico": {k: m["fisico"][k] for k in ("receita_leite", "custo_alimentacao", "rmca")}})
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        r["por_mes"] = meses
    r["como_ler"] = (
        "RMCA = Receita do leite − Custo com alimentação, nas duas versões da tela Financeiro › RMCA: 'gerencial' (lançamentos financeiros, por "
        "COMPETÊNCIA, nas contas marcadas em Parâmetros financeiros) e 'fisico' (receita igual; custo = consumo real da Alimentação × valor do "
        "item). 'configurado'=false significa que as contas de receita/custo ainda não foram marcadas. O RMCA do site não é por centro de "
        "custo; para resultado por centro use executar_relatorio('dre', centro_custo=...). meta_rmca é a meta configurada."
    )
    return r


# ===========================================================================
# 6. Dietas (Alimentação): dietas por lote, consumo/sobra do cocho, alimentos
# ---------------------------------------------------------------------------
# NÃO chamamos GET /alimentacao/ nem /alimentacao/necessidade-mensal: os dois dão a
# baixa automática de estoque ao abrir (escrevem). Usamos as mesmas funções de
# leitura que eles usam (plano por lote fundido + calcular_consumo/necessidade).
# A Formulação de Dietas (simulações, custo/dia da dieta formulada) é restrita ao dono e
# aos consultores CowData no site e NÃO é exposta ao agente.
# ===========================================================================
def _dietas_lotes(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers.alimentacao import (
        _dietas_e_animais, _estoque_por_alimento, _lotes_cadastro, apresentacao_dieta, listar_dietas,
    )
    from fazenda.models import Estoque
    from fazenda.rules.alimentacao import calcular_consumo, calcular_necessidade_mensal

    lote = _inteiro(entrada, "lote", 0, 99)
    situacao = _escolha(entrada, "situacao", ("ativas", "encerradas", "todas"), "ativas")
    plano = _bool(entrada, "incluir_plano_consumo", True)
    necessidade = _bool(entrada, "incluir_necessidade_mensal", False)

    lancadas = _chamar(listar_dietas, session, fazenda_id, lote=lote, ativo={"ativas": True, "encerradas": False, "todas": None}[situacao])
    cortadas, cortou = _cortar(lancadas, 60)
    dietas = []
    for d in cortadas:
        ap = _chamar(apresentacao_dieta, session, fazenda_id, dieta_id=d["id"])  # GET /alimentacao/dietas/{id}/apresentacao
        dietas.append({
            "dieta_id": d["id"], "lote": d["lote"], "nome_lote": ap["nome"], "ativa": d["ativa"], "responsavel": d.get("responsavel"),
            "data_abertura": _iso(d["data_abertura"]), "data_prevista_encerramento": _iso(d.get("data_prevista_encerramento")),
            "data_encerramento": _iso(d.get("data_efetivo_encerramento")), "base_quantidade": d.get("base_quantidade") or "total",
            "leite_bezerros_kg_dia": d.get("leite_bezerros_kg_dia"), "observacao": d.get("observacao"),
            "qtd_animais_no_lote_hoje": ap["qtd_animais"], "itens": ap["itens"],
            "vagao_kg_dia": ap["vagao_kg_dia"], "vagao_kg_trato": ap["vagao_kg_trato"], "num_tratos": ap["num_tratos"],
        })
    saida: dict[str, Any] = {
        "filtros": {"lote": lote, "situacao": situacao}, "total_dietas": len(lancadas), "dietas": dietas,
        "limitado_pela_ferramenta": cortou,
    }
    if plano or necessidade:
        dietas_plano, animais = _dietas_e_animais(session, fazenda_id)  # mesma fusão (dieta lançada ativa × import antigo) da tela
        consumo = calcular_consumo(dietas_plano, animais, _lotes_cadastro(session, fazenda_id))
        if lote is not None:
            consumo = {**consumo, "por_lote": [l for l in consumo["por_lote"] if l["lote"] == lote]}
        if plano:
            saida["plano_por_lote"] = consumo["por_lote"]
            saida["consumo_total_dia_rebanho"] = consumo["consumo_total"]
        if necessidade:
            estoque_por_nome = {e.nome: e.model_dump() for e in session.exec(_escopo(select(Estoque), Estoque.fazenda_id, fazenda_id)).all()}
            por_alimento, cadastrados = _estoque_por_alimento(session, fazenda_id)
            saida["necessidade_mensal_30_dias"] = calcular_necessidade_mensal(consumo["consumo_total"], estoque_por_nome, por_alimento, cadastrados)
    saida["como_ler"] = (
        "Dietas lançadas em Lançamentos › Alimentação (uma ativa por lote). 'itens' = o que o funcionário vê para conferir no vagão: "
        "por cabeça, total/dia do lote e por trato; vagao_kg_* soma só os itens em kg. 'plano_por_lote' é o consumo/dia por ingrediente da tela "
        "Alimentação (efetivo atual × dieta, incluindo lotes que só têm a dieta do import antigo). O CUSTO por vaca/dia da dieta só existe no módulo "
        "Formulação de Dietas (restrito) — o agente não o expõe; para custo realizado use consultar_rmca (custo físico por ingrediente) ou "
        "executar_relatorio('custo_vaca_lote')."
    )
    return saida


def _consumo_sobra(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers.alimentacao import obter_consumo, relatorio_sobra
    from fazenda.models import ConsumoAlimento, ConsumoSobra

    ini, fim = _periodo(entrada, obrigatorio=True)
    lote = _inteiro(entrada, "lote", 0, 99)

    pares: set[tuple[int, date]] = set()
    for modelo in (ConsumoAlimento, ConsumoSobra):
        q = _escopo(select(modelo.lote, modelo.data).where(modelo.data >= ini, modelo.data <= fim), modelo.fazenda_id, fazenda_id)
        if lote is not None:
            q = q.where(modelo.lote == lote)
        pares.update((l, d) for l, d in session.exec(q).all())
    if len(pares) > 400:
        raise ErroConsulta(f"O período tem {len(pares)} lote×dia com lançamentos (máximo 400). Reduza o período ou filtre por 'lote'.")

    dias = []
    for l, d in sorted(pares, key=lambda p: (p[1], p[0]), reverse=True):
        c = _chamar(obter_consumo, session, fazenda_id, lote=l, data=d)  # GET /alimentacao/consumo (a tela de consumo do dia)
        dias.append({k: c[k] for k in ("lote", "data", "num_animais", "itens", "kg_fornecido_total", "sobra_kg", "sobra_pct", "dentro_da_faixa")})
    por_lote: dict[int, dict] = {}
    for c in dias:
        p = por_lote.setdefault(c["lote"], {"lote": c["lote"], "dias_com_lancamento": 0, "kg_fornecido": 0.0, "kg_sobra": 0.0})
        p["dias_com_lancamento"] += 1
        p["kg_fornecido"] = round(p["kg_fornecido"] + c["kg_fornecido_total"], 2)
        p["kg_sobra"] = round(p["kg_sobra"] + (c["sobra_kg"] or 0), 2)
    for p in por_lote.values():
        p["sobra_pct_media"] = round(p["kg_sobra"] / p["kg_fornecido"] * 100, 2) if p["kg_fornecido"] > 0 else None
    resumo = _chamar(relatorio_sobra, session, fazenda_id, de=ini, ate=fim, lote=lote)  # GET /alimentacao/sobra/relatorio
    cortados, cortou = _cortar(dias)
    return {
        "periodo": {"data_inicio": ini.isoformat(), "data_fim": fim.isoformat()}, "filtros": {"lote": lote},
        "relatorio_sobra_do_site": resumo, "por_lote": [por_lote[k] for k in sorted(por_lote)],
        "dias": cortados, "limitado_pela_ferramenta": cortou,
        "como_ler": (
            "Consumo = o que foi FORNECIDO ao lote (lançamentos de Alimentação, somados por dia); sobra = kg medidos no cocho. 'relatorio_sobra_do_site' é o relatório "
            "Alimentação › Sobra (total, % médio e rateio por alimento pela proporção da dieta ativa de cada lote); em 'dias', sobra_pct = sobra ÷ fornecido do dia e "
            "dentro_da_faixa compara com a faixa dos Parâmetros. Itens em litro/dose não convertem para kg e ficam fora das somas em kg."
        ),
    }


def _alimentos(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers.alimentacao import listar_alimentos
    from fazenda.models import CategoriaAlimento

    nome, categoria = _txt(entrada, "nome"), _txt(entrada, "categoria")
    incluir_inativos = _bool(entrada, "incluir_inativos", False)
    sem_vinculo = _bool(entrada, "apenas_sem_estoque_vinculado", False)
    cats = {c.id: c.nome for c in session.exec(_escopo(select(CategoriaAlimento), CategoriaAlimento.fazenda_id, fazenda_id)).all()}
    itens = _chamar(listar_alimentos, session, fazenda_id)  # GET /alimentacao/alimentos
    if not incluir_inativos:
        itens = [a for a in itens if a.get("ativo") is not False]
    if nome:
        itens = [a for a in itens if _contem(a.get("nome"), nome)]
    if categoria:
        itens = [a for a in itens if _contem(cats.get(a.get("categoria_alimento_id")), categoria)]
    if sem_vinculo:
        itens = [a for a in itens if not a.get("estoque_vinculado")]
    linhas = [{
        "alimento": a["nome"], "categoria": cats.get(a.get("categoria_alimento_id")), "ativo": a.get("ativo") is not False,
        "observacao": a.get("observacao"),
        "estoque_vinculado": [
            {"item": e["nome"], "saldo": e.get("quantidade"), "unidade": e.get("unidade"), "valor_unitario": e.get("valor_unitario"),
             "item_ativo": e.get("ativo") is not False}
            for e in a.get("estoque_vinculado", [])
        ],
    } for a in itens]
    cortadas, cortou = _cortar(linhas)
    return {
        "total": len(linhas), "alimentos": cortadas, "limitado_pela_ferramenta": cortou,
        "como_ler": (
            "Cadastro de alimentos/ingredientes (Configurações › Cadastro › Alimentação) com o item de estoque de onde sai a baixa. Alimento sem estoque vinculado "
            "aparece com lista vazia. Saldo e valor por unidade vêm do Estoque."
        ),
    }


# ===========================================================================
# Registro
# ===========================================================================
FERRAMENTAS: list[dict] = [
    {
        "modulo": "indicadores",
        "spec": {
            "name": "consultar_indicadores_na_data",
            "description": (
                "Indicadores gerais do rebanho (composição, reprodução, produção) para uma DATA DE REFERÊNCIA, com os mesmos "
                "números da tela Indicadores/Capa do site (GET /indicadores/?data=). Use para 'como estavam os indicadores em "
                "30/06/2026?', 'qual o DEL médio hoje?', 'quantas vacas em lactação eu tinha em 30/06/2026?' (veja "
                "lactacao_na_data_pela_tabela_lactacao). ATENÇÃO: o site não guarda histórico dos indicadores — para datas "
                "passadas é um recálculo com os dados de hoje e o resultado traz 'limitacoes' que você deve repassar ao usuário. "
                "Sem 'data' = hoje. secao: resumo (padrão), rebanho, reproducao, producao, benchmark ou tudo. "
                "Para taxa de concepção/serviços de um PERÍODO use consultar_indicadores_reprodutivos; para produção de leite de "
                "um período use consultar_producao_leite; consultar_indicadores (antiga) é só a foto de hoje."
            ),
            "input_schema": _schema({
                "data": ("string", "Data de referência, formato AAAA-MM-DD (ex.: 2026-06-30). Opcional; padrão hoje."),
                "secao": ("string", "Opcional. resumo (padrão), rebanho, reproducao, producao, benchmark ou tudo."),
                "incluir_listas_nominais": ("boolean", "Opcional. true = inclui as listas de números de animais por trás de cada card."),
            }),
        },
        "executor": _com_erro(_indicadores_na_data),
    },
    {
        "modulo": "rebanho",
        "spec": {
            "name": "consultar_ficha_animal",
            "description": (
                "FICHA COMPLETA de UM animal (Rebanho › ficha): cadastro, genealogia (pai/mãe/avôs), estado reprodutivo ao vivo, "
                "previsão de parto/secagem, lactações e quadro por parto, partos, serviços/inseminações, diagnósticos, protocolos "
                "(IATF, indução, sanitários), aplicações sanitárias, exames, doenças, controle leiteiro, qualidade do leite, pesagens, "
                "movimentações de lote, compra/venda/baixa e secagens. Use para 'me mostre a ficha da vaca 123', 'quando foi o último "
                "parto da 123?', 'qual o histórico de inseminações da 123?', 'qual a mãe da bezerra 456?'. Informe 'numero' (obrigatório) "
                "e escolha 'secoes' (separadas por vírgula; padrão = cadastro, genealogia, estado_reprodutivo, previsoes, lactacoes; "
                "'todas' traz tudo menos as curvas) para não estourar o tamanho da resposta. Opcional: data_inicio/data_fim restringem as "
                "listas por data; max_itens (padrão 100). Só cadastro básico: buscar_animal; só aplicações de medicamento de vários "
                "animais: consultar_aplicacoes_sanitarias; lista de animais de um lote: consultar_lote."
            ),
            "input_schema": _schema({
                "numero": ("string", "Número do animal (brinco/matriz), ex.: '123'."),
                "secoes": ("string", "Opcional. Seções separadas por vírgula: " + ", ".join(_SECOES_FICHA) + ", ou 'todas'."),
                "data_inicio": _DI, "data_fim": _DF,
                "max_itens": ("integer", "Opcional. Máximo de registros por seção (1 a 500, padrão 100; os mais recentes primeiro)."),
            }, ["numero"]),
        },
        "executor": _com_erro(_ficha_animal),
    },
    {
        "modulo": ("rebanho", "reproducao"),
        "spec": {
            "name": "consultar_estoque_semen",
            "description": (
                "ESTOQUE DE SÊMEN da fazenda (Rebanho › Touros › Sêmen): doses por touro, NAAB, central, tipo (convencional, sexado, fazenda), "
                "valor por dose, local (caneca/botijão) e o painel de estoque mínimo por categoria. Use para 'quantas doses de sêmen tenho?', "
                "'tenho sêmen do touro X?', 'quantas doses sexadas tenho?', 'o sêmen está abaixo do mínimo?'. Filtros: touro (nome/NAAB), "
                "tipo, situacao (disponivel, zerado ou todos), local, incluir_provas=true (TPI, NM$ e prova média ponderada pelas doses). "
                "Compras de sêmen: executar_relatorio('compra_semen'); uso por touro no período: consultar_uso_semen; provas do catálogo "
                "inteiro: consultar_touros_catalogo; saldo de insumos comuns: consultar_estoque_itens."
            ),
            "input_schema": _schema({
                "touro": ("string", "Opcional. Parte do nome do touro ou do NAAB."),
                "tipo": ("string", "Opcional. convencional, sexado, fazenda ou todos (padrão)."),
                "situacao": ("string", "Opcional. disponivel (com dose), zerado ou todos (padrão)."),
                "local": ("string", "Opcional. Parte do local de armazenamento (ex.: 'Caneca 1')."),
                "incluir_provas": ("boolean", "Opcional. true = TPI/NM$ de cada touro e a prova média do estoque."),
                "incluir_inativos": ("boolean", "Opcional. true = inclui touros desativados."),
            }),
        },
        "executor": _com_erro(_estoque_semen),
    },
    {
        "modulo": ("rebanho", "reproducao"),
        "spec": {
            "name": "consultar_touros_catalogo",
            "description": (
                "CATÁLOGO GENÉTICO DE TOUROS (Rebanho › Touros, NAAB/provas do fornecedor): nome, central, raça e as provas (TPI, NM$, leite, "
                "gordura, proteína, tipo, úbere, pernas, CCS, fertilidade das filhas, facilidade de parto). Use para 'qual o TPI do touro X?', "
                "'quais os melhores touros em NM$ que tenho em estoque?' (apenas_no_estoque=true), 'touros da central ABS'. Filtros: busca "
                "(nome/NAAB), central, raca, apenas_no_estoque; ordenar_por: tpi (padrão), nm_dolar, leite_kg, gordura_kg, proteina_kg, "
                "tipo_composto, ubere_composto, pernas_composto, fertilidade_filhas, facilidade_parto ou nome. É o catálogo global, não o "
                "estoque (doses): para doses use consultar_estoque_semen; para resultado de uso (concepção) use consultar_uso_semen."
            ),
            "input_schema": _schema({
                "busca": ("string", "Opcional. Parte do nome ou do NAAB."), "central": ("string", "Opcional. Central/fonte (ex.: ABS, Alta, Semex)."),
                "raca": ("string", "Opcional. Raça (ex.: Holandês, Jersey, Gir)."),
                "apenas_no_estoque": ("boolean", "Opcional. true = só touros com dose em estoque na fazenda."),
                "ordenar_por": ("string", "Opcional. " + ", ".join(_ORDEM_TOUROS) + " (padrão tpi, maior primeiro)."),
                "incluir_dados_extra": ("boolean", "Opcional. true = colunas extras da planilha do fornecedor."),
            }),
        },
        "executor": _com_erro(_touros_catalogo),
    },
    {
        "modulo": ("rebanho", "reproducao", "analise"),
        "spec": {
            "name": "consultar_uso_semen",
            "description": (
                "USO DE SÊMEN POR TOURO em um período e o RESULTADO: serviços (doses usadas), diagnósticos positivos/negativos, taxa de "
                "concepção por touro (a mesma da Análise reprodutiva), perdas, doses restantes e compras do período. Use para 'quais touros mais "
                "usei em 2026?', 'qual a concepção do touro X de janeiro a junho?', 'quanto sêmen usei e comprei no semestre?'. OBRIGATÓRIO "
                "data_inicio e data_fim (AAAA-MM-DD); se faltarem, pergunte. Filtros: touro, tipo (convencional, sexado, fazenda); "
                "incluir_prova_ao_vivo=true traz a prova genética ponderada pelo uso. Para doses em estoque hoje use consultar_estoque_semen; "
                "para concepção com outros filtros (inseminador, ordem de parto) use consultar_indicadores_reprodutivos."
            ),
            "input_schema": _schema({
                "data_inicio": _DI, "data_fim": _DF,
                "touro": ("string", "Opcional. Parte do nome do touro."),
                "tipo": ("string", "Opcional. convencional, sexado, fazenda ou todos (padrão)."),
                "incluir_prova_ao_vivo": ("boolean", "Opcional. true = provas genéticas ponderadas pelo uso no período."),
            }, ["data_inicio", "data_fim"]),
        },
        "executor": _com_erro(_uso_semen),
    },
    {
        "modulo": "financeiro",
        "spec": {
            "name": "consultar_fluxo_caixa",
            "description": (
                "FLUXO DE CAIXA realizado (Financeiro › Fluxo de Caixa e Livro Caixa), por mês, por dia, em livro ou por conta/categoria: "
                "entradas, saídas, saldo e acumulado, no regime de CAIXA (data do pagamento). Use para 'qual o fluxo de caixa de agosto?', "
                "'quanto entrou e saiu em 2026 por mês?', 'quanto gastei com cada categoria mês a mês?', 'qual o saldo acumulado do livro caixa?'. "
                "OBRIGATÓRIO data_inicio e data_fim (AAAA-MM-DD); se faltarem, pergunte. visao: mensal (padrão), diario, livro ou por_conta. "
                "Filtros: centro_custo (a tela abre em 'Pecuária Leiteira'; sem filtro soma todos e mostra por_centro_custo), tipo "
                "(entradas/saidas), fornecedor, conta (código da conta gerencial, ex.: '3.01'). incluir_previsto=true compara com as contas "
                "ainda em aberto com vencimento no período. Para o resultado por competência (DRE) use executar_relatorio('dre'); para listar "
                "contas a pagar/receber use consultar_contas_financeiras; para o saldo projetado para frente use consultar_caixa_real."
            ),
            "input_schema": _schema({
                "data_inicio": _DI, "data_fim": _DF,
                "visao": ("string", "Opcional. mensal (padrão), diario, livro ou por_conta."),
                "centro_custo": ("string", "Opcional. Centro de custo exato (ex.: 'Pecuária Leiteira')."),
                "tipo": ("string", "Opcional. entradas, saidas ou todos (padrão)."),
                "fornecedor": ("string", "Opcional. Parte do nome do fornecedor/cliente."),
                "conta": ("string", "Opcional. Código da conta gerencial (inclui as filhas), ex.: '3.01'."),
                "incluir_previsto": ("boolean", "Opcional. true = acrescenta o previsto (contas em aberto com vencimento no período)."),
            }, ["data_inicio", "data_fim"]),
        },
        "executor": _com_erro(_fluxo_caixa),
    },
    {
        "modulo": "financeiro",
        "spec": {
            "name": "consultar_caixa_real",
            "description": (
                "CAIXA REAL — projeção de liquidez (Financeiro › Caixa Real): saldo das contas correntes hoje, como o saldo evolui dia a dia "
                "com as contas a pagar/receber já lançadas, fundo de reserva, primeiro dia negativo e folga mínima. Use para 'quanto tenho em "
                "caixa?', 'vou ficar sem dinheiro nos próximos 60 dias?', 'qual o saldo projetado?'. dias = horizonte (padrão do parâmetro da "
                "fazenda, em geral 90). Restrito a administradores, como no site. Para o que JÁ entrou/saiu use consultar_fluxo_caixa."
            ),
            "input_schema": _schema({"dias": ("integer", "Opcional. Horizonte da projeção em dias (1 a 730).")}),
        },
        "executor": _com_erro(_caixa_real),
    },
    {
        "modulo": "financeiro",
        "spec": {
            "name": "consultar_rmca",
            "description": (
                "RMCA — Receita Menos Custo com Alimentação (Financeiro › RMCA): receita do leite, custo com alimentação e o resultado, nas "
                "versões gerencial (lançamentos) e física (consumo da Alimentação × valor do item), mais a meta e o preço médio do litro. Use "
                "para 'qual o RMCA de agosto?', 'quanto gastei com alimentação versus receita do leite no semestre?', 'o RMCA está acima da "
                "meta?'. OBRIGATÓRIO data_inicio e data_fim (AAAA-MM-DD, por competência); se faltarem, pergunte. por_mes=true devolve o "
                "RMCA de cada mês do período (até 24 meses); incluir_itens_fisicos=true detalha preços por kg. Para custo por litro use "
                "executar_relatorio('custo_litro_leite'); para o resultado geral (DRE) use executar_relatorio('dre')."
            ),
            "input_schema": _schema({
                "data_inicio": _DI, "data_fim": _DF,
                "por_mes": ("boolean", "Opcional. true = RMCA mês a mês dentro do período."),
                "incluir_itens_fisicos": ("boolean", "Opcional. true = preço por kg padrão/última compra de cada ingrediente."),
            }, ["data_inicio", "data_fim"]),
        },
        "executor": _com_erro(_rmca),
    },
    {
        "modulo": "alimentacao",
        "spec": {
            "name": "consultar_dietas_lotes",
            "description": (
                "DIETAS por lote (Alimentação / Lançamentos › Alimentação): a dieta ativa (ou as encerradas) de cada lote com a composição — "
                "alimento, quantidade por cabeça, total/dia do lote, por trato e kg no vagão —, responsável, datas e o plano de consumo/dia por "
                "ingrediente do rebanho. Use para 'qual a dieta do lote 02?', 'quanto de silagem por vaca no lote 01?', 'quanto de ração o "
                "rebanho consome por dia?', 'quanto preciso comprar para 30 dias?' (incluir_necessidade_mensal=true). Filtros: lote (número), "
                "situacao (ativas padrão, encerradas, todas). Somente leitura: não formula nem altera dieta. Consumo/sobra realmente lançados: "
                "consultar_consumo_sobra_cocho; cadastro de alimentos: consultar_alimentos_cadastrados; custo da alimentação: consultar_rmca."
            ),
            "input_schema": _schema({
                "lote": ("integer", "Opcional. Número do lote (ex.: 2 para o lote 02)."),
                "situacao": ("string", "Opcional. ativas (padrão), encerradas ou todas."),
                "incluir_plano_consumo": ("boolean", "Opcional. Plano de consumo/dia por lote e ingrediente (padrão true)."),
                "incluir_necessidade_mensal": ("boolean", "Opcional. true = projeção de 30 dias por ingrediente (sacos/estoque)."),
            }),
        },
        "executor": _com_erro(_dietas_lotes),
    },
    {
        "modulo": "alimentacao",
        "spec": {
            "name": "consultar_consumo_sobra_cocho",
            "description": (
                "CONSUMO REAL (o que foi fornecido) e SOBRA DO COCHO por lote e por dia (Lançamentos › Alimentação): kg fornecidos por alimento, "
                "kg de sobra, % de sobra e se está dentro da faixa, mais o relatório de sobra do período. Use para 'quanto de sobra tive no lote "
                "02 em setembro?', 'qual o consumo da semana?', 'a sobra está dentro da faixa?'. OBRIGATÓRIO data_inicio e data_fim (AAAA-MM-DD); se "
                "faltarem, pergunte. Filtro: lote (número). Para a composição da dieta use consultar_dietas_lotes."
            ),
            "input_schema": _schema({
                "data_inicio": _DI, "data_fim": _DF, "lote": ("integer", "Opcional. Número do lote (ex.: 2 para o lote 02)."),
            }, ["data_inicio", "data_fim"]),
        },
        "executor": _com_erro(_consumo_sobra),
    },
    {
        "modulo": "alimentacao",
        "spec": {
            "name": "consultar_alimentos_cadastrados",
            "description": (
                "ALIMENTOS/INGREDIENTES cadastrados (Configurações › Cadastro › Alimentação) com categoria e os itens de estoque vinculados "
                "(saldo, unidade e valor unitário). Use para 'quais alimentos tenho cadastrados?', 'qual o saldo de silagem?', 'quais alimentos "
                "estão sem estoque vinculado?'. Filtros: nome, categoria, apenas_sem_estoque_vinculado, incluir_inativos. Estoque de qualquer "
                "insumo: consultar_estoque_itens; dietas: consultar_dietas_lotes."
            ),
            "input_schema": _schema({
                "nome": ("string", "Opcional. Parte do nome do alimento."), "categoria": ("string", "Opcional. Categoria (ex.: Volumoso, Concentrado)."),
                "apenas_sem_estoque_vinculado": ("boolean", "Opcional. true = só alimentos sem item de estoque."),
                "incluir_inativos": ("boolean", "Opcional. true = inclui alimentos desativados."),
            }),
        },
        "executor": _com_erro(_alimentos),
    },
]

NOMES = frozenset(f["spec"]["name"] for f in FERRAMENTAS)
