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
]

NOMES = frozenset(f["spec"]["name"] for f in FERRAMENTAS)
