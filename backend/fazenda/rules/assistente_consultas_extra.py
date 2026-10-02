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
]

NOMES = frozenset(f["spec"]["name"] for f in FERRAMENTAS)
