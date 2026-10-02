"""
Ferramentas de LEITURA com PARÂMETROS (período, filtros) do Assistente do site
e do agente externo (Hermes, via /agente) — a parte "o agente responde TUDO
que o site mostra".

Princípios (valem para TODAS as ferramentas deste módulo):

- 100% somente leitura: nada aqui chama add/commit/flush. Roda tanto na sessão
  normal do chat do site quanto na sessão READ ONLY de /agente (os testes
  executam todas as ferramentas na sessão read-only).
- ZERO lógica nova de cálculo: cada ferramenta chama a MESMA função/regra que
  o endpoint do site usa (`_chamar` invoca a função do router com `session` e
  `fazenda_id` explícitos), de modo que o número do agente é idêntico ao da
  tela. Quando o site calcula no navegador (ex.: Análise reprodutiva), a conta
  do navegador foi reproduzida em `rules/reproducao_analise.resumo_periodo`,
  com teste de consistência contra o endpoint.
- Isolamento por fazenda: toda consulta recebe `fazenda_id` (o do token, no
  site; o fixo AGENTE_FAZENDA_ID, em /agente).
- Parâmetros validados com mensagem clara em português: data inválida,
  período invertido, período acima de 5 anos, valor fora da lista.
- Erro de uso devolve `{"erro": "..."}` (HTTP 200), como as ferramentas
  antigas — o modelo lê a frase e pergunta ao usuário o que faltou.

Cada item de FERRAMENTAS tem `modulo` (str ou tupla = qualquer um dos módulos),
`spec` (nome, descrição em português com exemplos, schema) e `executor`
(session, usuario, entrada, fazenda_id) -> dict. Registro em
`fazenda.rules.assistente` (mesma lista compartilhada com /agente).
"""
from __future__ import annotations

import inspect
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Callable

from fastapi import HTTPException
from sqlmodel import Session, select

LIMITE_ANOS = 5
MAX_LINHAS = 1000  # teto de linhas devolvidas por lista (a paginação do /agente corta de novo)
_DATA_BR = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


# ---------------------------------------------------------------------------
# Utilitários de parâmetros
# ---------------------------------------------------------------------------
class ErroConsulta(Exception):
    """Erro de uso (parâmetro inválido) — vira {"erro": mensagem}."""


def _sem_acento(t: str | None) -> str:
    n = unicodedata.normalize("NFKD", t or "")
    return "".join(c for c in n if not unicodedata.combining(c)).casefold().strip()


def _contem(texto: str | None, trecho: str | None) -> bool:
    return _sem_acento(trecho) in _sem_acento(texto)


def _txt(entrada: dict, nome: str) -> str | None:
    v = entrada.get(nome)
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def _bool(entrada: dict, nome: str, padrao: bool = False) -> bool:
    v = entrada.get(nome)
    if v is None or v == "":
        return padrao
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "sim", "s", "yes", "verdadeiro")


def _inteiro(entrada: dict, nome: str, minimo: int | None = None, maximo: int | None = None) -> int | None:
    v = entrada.get(nome)
    if v is None or str(v).strip() == "":
        return None
    try:
        n = int(float(str(v).replace(",", ".")))
    except ValueError:
        raise ErroConsulta(f"Parâmetro '{nome}' deve ser um número inteiro (recebi '{v}').") from None
    if minimo is not None and n < minimo:
        raise ErroConsulta(f"Parâmetro '{nome}' deve ser no mínimo {minimo}.")
    if maximo is not None and n > maximo:
        raise ErroConsulta(f"Parâmetro '{nome}' deve ser no máximo {maximo}.")
    return n


def _escolha(entrada: dict, nome: str, validos: tuple[str, ...], padrao: str | None = None) -> str | None:
    v = _txt(entrada, nome)
    if v is None:
        return padrao
    alvo = _sem_acento(v).replace(" ", "_").replace("-", "_")
    for opcao in validos:
        if _sem_acento(opcao) == alvo:
            return opcao
    raise ErroConsulta(f"Valor inválido em '{nome}': '{v}'. Use um de: {', '.join(validos)}.")


def _data(entrada: dict, nome: str) -> date | None:
    v = entrada.get(nome)
    if v is None or str(v).strip() == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    texto = str(v).strip()
    m = _DATA_BR.match(texto)  # tolera 01/07/2026 (o modelo às vezes repete o formato do usuário)
    try:
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return date.fromisoformat(texto[:10])
    except ValueError:
        raise ErroConsulta(
            f"Data inválida em '{nome}': '{v}'. Use o formato AAAA-MM-DD (ex.: 2026-01-31) e uma data que exista."
        ) from None


def _periodo(
    entrada: dict, *, obrigatorio: bool, nome_ini: str = "data_inicio", nome_fim: str = "data_fim",
) -> tuple[date | None, date | None]:
    """(inicio, fim) validados. Obrigatório: os dois. Sempre: início <= fim e
    no máximo 5 anos (o volume de dados e o custo da consulta crescem rápido)."""
    ini, fim = _data(entrada, nome_ini), _data(entrada, nome_fim)
    if obrigatorio and (ini is None or fim is None):
        raise ErroConsulta(
            f"Informe '{nome_ini}' e '{nome_fim}' (AAAA-MM-DD). Se o usuário não disse o período, pergunte a ele."
        )
    if ini and fim:
        if ini > fim:
            raise ErroConsulta(
                f"Período invertido: {nome_ini} ({ini.isoformat()}) é depois de {nome_fim} ({fim.isoformat()})."
            )
        if (fim - ini).days > LIMITE_ANOS * 366:
            raise ErroConsulta(f"Período maior que {LIMITE_ANOS} anos. Consulte em fatias de até {LIMITE_ANOS} anos.")
    return ini, fim


def _no_periodo(d: date | str | None, ini: date | None, fim: date | None) -> bool:
    """True se a data cai no período; sem data só passa se não há período."""
    if ini is None and fim is None:
        return True
    if d is None or d == "":
        return False
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d[:10])
        except ValueError:
            return False
    if isinstance(d, datetime):
        d = d.date()
    return (ini is None or d >= ini) and (fim is None or d <= fim)


def _chamar(fn: Callable, session: Session, fazenda_id: int | None, **kw) -> Any:
    """Chama a função do router/regra do site passando `session` e `fazenda_id`
    e os parâmetros de `kw`; o que faltar usa o default declarado (inclusive
    `Query(...)` do FastAPI, que sozinho seria um objeto "verdadeiro")."""
    args: dict[str, Any] = {}
    for nome, p in inspect.signature(fn).parameters.items():
        if nome == "session":
            args[nome] = session
        elif nome == "fazenda_id":
            args[nome] = fazenda_id
        elif nome in kw:
            args[nome] = kw[nome]
        else:
            d = p.default
            if d is inspect.Parameter.empty:
                raise TypeError(f"{fn.__name__}: parâmetro '{nome}' sem valor")
            if hasattr(d, "dependency"):  # Depends(...)
                raise TypeError(f"{fn.__name__}: dependência '{nome}' não suportada")
            args[nome] = d.default if hasattr(d, "default") and type(d).__module__.startswith("fastapi") else d
    return fn(**args)


def _escopo(query, coluna, fazenda_id: int | None):
    return query if fazenda_id is None else query.where(coluna == fazenda_id)


def _cortar(linhas: list, maximo: int = MAX_LINHAS) -> tuple[list, bool]:
    return (linhas[:maximo], len(linhas) > maximo)


def _iso(d) -> str | None:
    if isinstance(d, (date, datetime)):
        return d.isoformat()
    return d


def _pegar(d: dict, campos: tuple[str, ...]) -> dict:
    return {c: _iso(d.get(c)) for c in campos}


def _arred_js(x: float) -> float:
    """Math.round do JavaScript (meio para cima) — a tela de Análise
    reprodutiva arredonda assim; o round() do Python (banker's) diverge em .5."""
    import math
    return math.floor(x + 0.5)


def _com_erro(fn: Callable[[Session, Any, dict, int | None], dict]):
    def _env(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
        try:
            return fn(session, usuario, entrada or {}, fazenda_id)
        except ErroConsulta as e:
            return {"erro": str(e)}
        except HTTPException as e:  # erro de uso do endpoint do site (ex.: 404 "Animal não encontrado")
            return {"erro": str(e.detail)}
    _env.__name__ = fn.__name__
    return _env


# ===========================================================================
# (a) Reprodução por período: indicadores, ciclos de 21 dias, serviços, partos
# ===========================================================================
_DIMENSOES_ANALISE = ("tipo_servico", "metodo_ia", "touro", "inseminador", "ordem_parto", "ordem_tentativa")


def _filtros_servicos(entrada: dict) -> dict[str, list[str]]:
    filtros: dict[str, list[str]] = {}
    for dim in _DIMENSOES_ANALISE:
        v = _txt(entrada, dim)
        if v:
            filtros[dim] = [x.strip() for x in v.split(",") if x.strip()]
    return filtros


def _passa_filtros(r: dict, filtros: dict[str, list[str]]) -> bool:
    """Mesma regra da tela de Análise reprodutiva (valor == um dos escolhidos),
    tolerando caixa/acento — o modelo escreve 'iatf' onde o cadastro tem 'IATF'."""
    for dim, valores in filtros.items():
        atual = _sem_acento(str(r.get(dim)))
        if not any(_sem_acento(v) == atual for v in valores):
            return False
    return True


def _servicos_do_site(session: Session, fazenda_id: int | None) -> list[dict]:
    from fazenda.api.routers.reproducao import listar_servicos_analise
    return _chamar(listar_servicos_analise, session, fazenda_id)["servicos"]


def _indicadores_reprodutivos(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers.reproducao import (
        indicadores_mensais_analise, listar_partos_historico, listar_secagens_historico,
    )
    from fazenda.rules.reproducao_analise import resumo_periodo

    ini, fim = _periodo(entrada, obrigatorio=True)
    filtros = _filtros_servicos(entrada)
    agrupar = _escolha(entrada, "agrupar_por", _DIMENSOES_ANALISE)

    regs = [
        r for r in _servicos_do_site(session, fazenda_id)
        if _no_periodo(r.get("data"), ini, fim) and _passa_filtros(r, filtros)
    ]
    resumo = resumo_periodo(regs, agrupar_por=agrupar)

    # Série mensal (critério R7 dos indicadores) = o MESMO endpoint que alimenta
    # o gráfico da tela (/reproducao/indicadores-mensais), com o mesmo recorte.
    mensal = _chamar(
        indicadores_mensais_analise, session, fazenda_id, ini=ini.isoformat(), fim=fim.isoformat(),
        **{d: (filtros.get(d) or None) for d in _DIMENSOES_ANALISE},
    )
    series = mensal["series"]
    chaves = ("num_servicos", "num_iatf", "num_ia_cio", "num_montas_naturais", "qtd_positivos", "qtd_negativos",
              "taxa_concepcao", "perdas_prenhez", "num_secagens")
    serie_mensal = [
        {"mes": m, **{k: series[k][i] for k in chaves}, "janela_dg_completa": mensal["janela_dg_completa"][i]}
        for i, m in enumerate(mensal["meses"])
    ]

    partos = [p for p in _chamar(listar_partos_historico, session, fazenda_id)["partos"] if _no_periodo(p.get("data"), ini, fim)]
    secagens = [s for s in _chamar(listar_secagens_historico, session, fazenda_id)["secagens"] if _no_periodo(s.get("data"), ini, fim)]
    por_tipo: dict[str, int] = defaultdict(int)
    for p in partos:
        por_tipo[p.get("tipo_parto") or "(sem tipo)"] += 1

    return {
        "periodo": {"data_inicio": ini.isoformat(), "data_fim": fim.isoformat()},
        "filtros": {k: v for k, v in filtros.items()},
        **resumo,
        "partos_no_periodo": {"total": len(partos), "por_tipo": dict(por_tipo)},
        "secagens_no_periodo": {"total": len(secagens)},
        "serie_mensal_criterio_r7": serie_mensal,
        "como_ler": (
            "taxa_concepcao_pct = positivos ÷ serviços já diagnosticados (positivo ou negativo) — é o número do "
            "KPI 'Taxa de concepção' da tela Relatórios › Análise reprodutiva para o mesmo período/filtros. "
            "A série mensal usa o critério dos Indicadores (R7: o serviço só entra no denominador depois de "
            "conhecido o resultado, ~28 dias; sem diagnóstico conta como não prenhe) e por isso pode diferir do KPI. "
            "Se o usuário não disser qual, dê o KPI da Análise reprodutiva e cite a diferença."
        ),
    }


def _ciclos_21_dias(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers.reproducao import ciclos_de_21_dias

    ini, fim = _periodo(entrada, obrigatorio=False)
    ancora = _data(entrada, "ancora")
    modo = _escolha(entrada, "modo", ("inicio", "fim"), "fim")
    categoria = _escolha(entrada, "categoria", ("todas", "vaca", "novilha"), "todas")
    n = _inteiro(entrada, "n_ciclos", 1, 26)
    if ini and fim and ancora is None:
        # Período pedido: ciclos de 21 dias terminando em data_fim e cobrindo o início.
        ancora, modo = fim, "fim"
        n = n or max(1, min(26, -(-((fim - ini).days + 1) // 21)))
    ancora = ancora or date.today()
    r = _chamar(ciclos_de_21_dias, session, fazenda_id, ancora=ancora, modo=modo, n_ciclos=n or 6, categoria=categoria)
    for c in r.get("ciclos", []):
        c.pop("animais", None)  # listas nominais ficam de fora (use a tela para auditar quem entrou em cada balde)
    return r


def _consultar_servicos(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    ini, fim = _periodo(entrada, obrigatorio=False)
    numero, touro = _txt(entrada, "numero"), _txt(entrada, "touro")
    filtros = _filtros_servicos({k: v for k, v in entrada.items() if k != "touro"})
    diag = _escolha(entrada, "diagnostico", ("POSITIVO", "NEGATIVO", "PENDENTE"))
    so_perdas = _bool(entrada, "apenas_perdas")
    padrao_aplicado = False
    if not (ini or fim or numero):
        fim = date.today()
        ini = fim - timedelta(days=90)
        padrao_aplicado = True

    linhas = []
    for r in _servicos_do_site(session, fazenda_id):
        if not _no_periodo(r.get("data"), ini, fim) or not _passa_filtros(r, filtros):
            continue
        if numero and str(r.get("numero")) != numero:
            continue
        if touro and not _contem(r.get("touro"), touro):
            continue
        d = r.get("diagnostico")
        if diag == "PENDENTE" and d in ("POSITIVO", "NEGATIVO"):
            continue
        if diag in ("POSITIVO", "NEGATIVO") and d != diag:
            continue
        if so_perdas and not r.get("perda"):
            continue
        linhas.append(r)
    linhas.sort(key=lambda r: (r.get("data") or "", str(r.get("numero"))), reverse=True)
    campos = ("numero", "data", "tipo_servico", "metodo_ia", "touro", "tipo_semen", "inseminador", "protocolo",
              "ordem_parto", "ordem_tentativa", "del_servico", "diagnostico", "data_diagnostico", "retoque",
              "data_reconfirmacao", "diagnostico_reconfirmacao", "perda", "data_perda", "motivo_perda", "data_d0")
    cortadas, cortou = _cortar(linhas)
    return {
        "periodo": {"data_inicio": _iso(ini), "data_fim": _iso(fim), "padrao_ultimos_90_dias": padrao_aplicado},
        "total": len(linhas),
        "positivos": sum(1 for r in linhas if r.get("positivo")),
        "negativos": sum(1 for r in linhas if r.get("diagnosticado") and not r.get("positivo")),
        "sem_diagnostico": sum(1 for r in linhas if not r.get("diagnosticado")),
        "perdas": sum(1 for r in linhas if r.get("perda")),
        "servicos": [_pegar(r, campos) for r in cortadas],
        "limitado_pela_ferramenta": cortou,
    }


def _consultar_partos_secagens(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers.reproducao import listar_partos_historico, listar_secagens_historico

    ini, fim = _periodo(entrada, obrigatorio=False)
    tipo = _escolha(entrada, "tipo", ("partos", "secagens", "ambos"), "ambos")
    numero = _txt(entrada, "numero")
    padrao_aplicado = False
    if not (ini or fim or numero):
        fim = date.today()
        ini = fim - timedelta(days=90)
        padrao_aplicado = True
    saida: dict[str, Any] = {"periodo": {"data_inicio": _iso(ini), "data_fim": _iso(fim), "padrao_ultimos_90_dias": padrao_aplicado}}
    if tipo in ("partos", "ambos"):
        partos = [
            p for p in _chamar(listar_partos_historico, session, fazenda_id)["partos"]
            if _no_periodo(p.get("data"), ini, fim) and (not numero or str(p.get("numero")) == numero)
        ]
        campos = ("numero", "data", "ordem_parto", "tipo_parto", "sexo_cria_1", "sexo_cria_2", "numero_cria_1",
                  "numero_cria_2", "gemelar", "gemelar_sexo", "retencao_placenta")
        cortadas, cortou = _cortar(partos)
        saida["total_partos"] = len(partos)
        saida["partos"] = [_pegar(p, campos) for p in cortadas]
        saida["partos_limitado_pela_ferramenta"] = cortou
    if tipo in ("secagens", "ambos"):
        secagens = [
            s for s in _chamar(listar_secagens_historico, session, fazenda_id)["secagens"]
            if _no_periodo(s.get("data"), ini, fim) and (not numero or str(s.get("numero")) == numero)
        ]
        campos = ("numero", "data", "motivo", "escore_condicao_corporal", "vacina_pre_parto", "observacao")
        cortadas, cortou = _cortar(secagens)
        saida["total_secagens"] = len(secagens)
        saida["secagens"] = [_pegar(s, campos) for s in cortadas]
        saida["secagens_limitado_pela_ferramenta"] = cortou
    return saida


# ===========================================================================
# (b) Hormônios / protocolos lançados / BST
# ===========================================================================
_STATUS_PROTOCOLO = {"andamento": "ativo", "concluido": "concluido", "encerrado": "encerrado", "cancelado": "cancelado"}


def _protocolos_lancados(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers import central_protocolos as cp

    ini, fim = _periodo(entrada, obrigatorio=False)
    status = _escolha(entrada, "status", ("andamento", "concluido", "encerrado", "cancelado", "todos"), "todos")
    tipo = _escolha(entrada, "tipo", ("reprodutivo", "produtivo", "sanitario", "lida"))
    origem = _escolha(entrada, "origem", ("iatf", "inducao", "sanitario", "customizado", "lida"))
    nome = _txt(entrada, "nome")
    origem_id = _inteiro(entrada, "origem_id", 1)

    if origem_id is not None:
        if not origem:
            raise ErroConsulta("Para ver o detalhe (grade animal × dia, hormônios), informe 'origem' (iatf, inducao, sanitario, customizado ou lida) junto com 'origem_id'.")
        d = _chamar(cp.detalhe, session, fazenda_id, origem=origem, origem_id=origem_id, incluir_sem_estoque=False)
        for dia in d.get("dias", []) if isinstance(d.get("dias"), list) else []:
            for h in dia.get("hormonios", []) or []:
                h.pop("opcoes", None)  # opções de frasco do estoque: ruído para quem só consulta
        return d

    linhas = cp._todas_as_linhas(session, fazenda_id)
    if status != "todos":
        linhas = [l for l in linhas if l["status"] == _STATUS_PROTOCOLO[status]]
    if origem:
        linhas = [l for l in linhas if l["origem"] == origem]
    # `_filtrar` é o MESMO filtro das abas Acompanhamento/Histórico (nome, tipo,
    # sobreposição de período, mais recentes primeiro).
    linhas = cp._filtrar(linhas, nome=nome, tipo=tipo, data_de=ini, data_ate=fim)
    por_status: dict[str, int] = defaultdict(int)
    for l in linhas:
        por_status[l["status"]] += 1
    cortadas, cortou = _cortar(linhas)
    return {
        "total": len(linhas),
        "por_status": dict(por_status),
        "protocolos": [{**l, "data_inicio": _iso(l["data_inicio"]), "data_fim": _iso(l["data_fim"]),
                        "encerrado_em": _iso(l["encerrado_em"])} for l in cortadas],
        "limitado_pela_ferramenta": cortou,
        "dica": "Para ver os animais/dias e os hormônios de um lançamento, repita com 'origem' e 'origem_id' da linha.",
    }


def _consultar_bst(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers.producao import relatorio_bst

    ini, fim = _periodo(entrada, obrigatorio=False)
    numero, lote = _txt(entrada, "numero"), _txt(entrada, "lote")
    padrao_aplicado = False
    if not (ini or fim or numero):
        fim = date.today()
        ini = fim - timedelta(days=90)
        padrao_aplicado = True
    linhas = [
        a for a in _chamar(relatorio_bst, session, fazenda_id)["aplicacoes"]
        if _no_periodo(a.get("data_aplicacao"), ini, fim)
        and (not numero or str(a.get("numero_matriz")) == numero)
        and (not lote or _contem(a.get("lote"), lote))
    ]
    animais = {a["numero_matriz"] for a in linhas}
    cortadas, cortou = _cortar(linhas)
    return {
        "periodo": {"data_inicio": _iso(ini), "data_fim": _iso(fim), "padrao_ultimos_90_dias": padrao_aplicado},
        "total_aplicacoes": len(linhas), "animais_distintos": len(animais),
        "aplicacoes": cortadas, "limitado_pela_ferramenta": cortou,
    }


# ===========================================================================
# (c) Sanidade: protocolos cadastrados, regras do preventivo, lista de espera,
#     agendamentos, histórico de aplicações
# ===========================================================================
_TIPOS_CADASTRO = ("sanitario_curativo", "sanitario_preventivo", "iatf", "inducao", "proprio", "todos")


def _protocolos_cadastrados(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers.cadastro.protocolos_customizados import listar_protocolos_customizados
    from fazenda.api.routers.cadastro.protocolos_sanitarios import (
        listar_protocolos_iatf_cadastrados, listar_protocolos_inducao, listar_protocolos_sanitarios,
    )

    tipo = _escolha(entrada, "tipo", _TIPOS_CADASTRO, "todos")
    nome = _txt(entrada, "nome")
    so_ativos = _bool(entrada, "apenas_ativos", False)
    saida: list[dict] = []

    def _etapas(p: dict, campos: tuple[str, ...]) -> list[dict]:
        return [_pegar(e, campos) for e in p.get("etapas", [])]

    if tipo in ("todos", "sanitario_curativo", "sanitario_preventivo"):
        for p in _chamar(listar_protocolos_sanitarios, session, fazenda_id):
            fin = p.get("finalidade") or "curativo"
            if tipo != "todos" and tipo != f"sanitario_{fin}":
                continue
            saida.append({
                "tipo": f"sanitario_{fin}", "nome": p["nome"], "ativo": p.get("ativo"), "doenca": p.get("doenca_nome"),
                "eh_mastite": p.get("eh_mastite"), "dia_inicial": p.get("dia_inicial"),
                "etapas": _etapas(p, ("dia", "criterio_tipo", "produto", "dosagem", "unidade", "via", "observacao")),
            })
    if tipo in ("todos", "iatf"):
        for p in _chamar(listar_protocolos_iatf_cadastrados, session, fazenda_id):
            saida.append({
                "tipo": "iatf", "nome": p["nome"], "ativo": p.get("ativo"), "observacao": p.get("observacao"),
                "etapas": _etapas(p, ("dia", "criterio_tipo", "produto", "dose", "unidade", "via")),
            })
    if tipo in ("todos", "inducao"):
        for p in _chamar(listar_protocolos_inducao, session, fazenda_id):
            saida.append({
                "tipo": "inducao", "nome": p["nome"], "ativo": p.get("ativo"), "observacao": p.get("observacao"),
                "etapas": _etapas(p, ("dia", "tipo", "produto", "dose", "unidade", "via", "acao_dispositivo")),
            })
    if tipo in ("todos", "proprio"):
        for p in _chamar(listar_protocolos_customizados, session, fazenda_id):
            saida.append({
                "tipo": "proprio", "nome": p["nome"], "ativo": p.get("ativo"), "categoria_agenda": p.get("categoria"),
                "classificacao": p.get("tipo"), "observacao": p.get("observacao"), "duracao_dias": p.get("duracao_dias"),
                "etapas": _etapas(p, ("dia", "descricao_evento", "produto", "dose", "unidade", "via")),
            })
    if so_ativos:
        saida = [p for p in saida if p.get("ativo") is not False]
    if nome:
        saida = [p for p in saida if _contem(p["nome"], nome)]
    por_tipo: dict[str, int] = defaultdict(int)
    for p in saida:
        por_tipo[p["tipo"]] += 1
    cortadas, cortou = _cortar(saida)
    return {"total": len(saida), "por_tipo": dict(por_tipo), "protocolos": cortadas, "limitado_pela_ferramenta": cortou}


def _regras_preventivo(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers.sanidade import listar_calendario
    from fazenda.rules.calendario_visao import montar_calendario_visual

    ini, fim = _periodo(entrada, obrigatorio=False)
    nome, categoria = _txt(entrada, "nome"), _txt(entrada, "categoria")
    regras = _chamar(listar_calendario, session, fazenda_id)
    if nome:
        regras = [r for r in regras if _contem(r.get("evento_sanitario_nome"), nome) or _contem(r.get("produto"), nome)]
    if categoria:
        regras = [r for r in regras if _contem(r.get("categoria_preventiva"), categoria) or _contem(r.get("categoria_alvo"), categoria)]
    campos = ("id", "evento_sanitario_nome", "categoria_preventiva", "categoria_alvo", "produto", "doenca_nome",
              "principio_ativo_nome", "frequencia_valor", "frequencia_unidade", "data_evento", "proxima_ocorrencia",
              "proxima_ocorrencia_por_animal", "ultimo_evento_data", "usa_cronograma", "ativo", "observacao")
    cortadas, cortou = _cortar(regras)
    saida: dict[str, Any] = {
        "total_regras": len(regras),
        "regras": [_pegar(r, campos) for r in cortadas],
        "limitado_pela_ferramenta": cortou,
    }
    if ini and fim:
        # Projeção das ocorrências no período — o mesmo card "Calendário Sanitário" do site.
        saida["ocorrencias_no_periodo"] = montar_calendario_visual(session, fazenda_id, ini, fim)
    return saida


def _lista_espera(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.rules import cronograma_sanitario as cron

    nome = _txt(entrada, "protocolo")
    calendario_id = _inteiro(entrada, "calendario_id", 1)
    # reconciliar=False: o endpoint do site (GET .../lista-espera) GRAVA a
    # reconciliação ao abrir; aqui a mesma lista é calculada sem escrever nada.
    r = cron.lista_espera(session, date.today(), fazenda_id, calendario_id, reconciliar=False)
    grupos = r["grupos"]
    if nome:
        grupos = [g for g in grupos if _contem(g.get("protocolo_nome"), nome) or _contem(g.get("produto"), nome)]
    detalhar = _bool(entrada, "detalhar_animais", True)
    saida_grupos = []
    for g in grupos:
        g = dict(g)
        if not detalhar:
            g.pop("animais", None)
        saida_grupos.append(g)
    return {
        "data_referencia": date.today().isoformat(),
        "total": sum(g["quantidade"] for g in grupos), "atrasadas": sum(g["atrasadas"] for g in grupos),
        "agendamentos_ativos": r["agendamentos_ativos"], "grupos": saida_grupos,
        "observacao": "Lista de espera = animais na janela do preventivo ainda sem agendamento (não aparecem na Agenda).",
    }


def _agendamentos_preventivo(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.rules import aplicacao_preventiva as ap

    ini, fim = _periodo(entrada, obrigatorio=False)
    situacao = _escolha(entrada, "situacao", ("agendados", "concluidos", "todos"), "agendados")
    protocolo = _txt(entrada, "protocolo")
    calendario_id = _inteiro(entrada, "calendario_id", 1)
    saida: dict[str, Any] = {}
    if situacao in ("agendados", "todos"):
        a = ap.acompanhamento(session, fazenda_id)
        itens = [
            i for i in a["agendamentos"]
            if (not calendario_id or i["calendario_sanitario_id"] == calendario_id)
            and (not protocolo or _contem(i.get("protocolo_nome"), protocolo) or _contem(i.get("produto"), protocolo))
            and _no_periodo(i.get("data_evento"), ini, fim)
        ]
        saida["agendados"] = {"total": len(itens), "agendamentos": itens, "totais_gerais": a["totais"]}
    if situacao in ("concluidos", "todos"):
        c = ap.concluidos(session, fazenda_id, calendario_id=calendario_id, de=ini, ate=fim, q=protocolo)
        saida["concluidos"] = c
    return saida


def _aplicacoes_sanitarias(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.models import Animal, Sanidade

    ini, fim = _periodo(entrada, obrigatorio=False)
    numero, produto = _txt(entrada, "numero"), _txt(entrada, "produto")
    natureza = _escolha(entrada, "natureza", ("curativo", "preventivo"))
    atividade, categoria = _txt(entrada, "atividade"), _txt(entrada, "categoria")
    if not (ini or fim or numero or produto or atividade):
        raise ErroConsulta(
            "Informe ao menos um filtro: período (data_inicio e data_fim), número do animal, produto ou atividade — "
            "o histórico inteiro seria grande demais."
        )
    q = _escopo(select(Sanidade), Sanidade.fazenda_id, fazenda_id)
    if ini:
        q = q.where(Sanidade.data_aplicacao >= ini)
    if fim:
        q = q.where(Sanidade.data_aplicacao <= fim)
    if numero:
        q = q.where(Sanidade.numero_matriz == numero)
    linhas = list(session.exec(q.order_by(Sanidade.data_aplicacao.desc(), Sanidade.id.desc())).all())
    if produto:
        linhas = [s for s in linhas if _contem(s.produto, produto)]
    if atividade:
        linhas = [s for s in linhas if _contem(s.atividade, atividade)]
    if categoria:
        linhas = [s for s in linhas if _contem(s.categoria, categoria)]
    if natureza:
        linhas = [s for s in linhas if (s.natureza or "curativo") == natureza]
    animais = {
        a.numero: a for a in session.exec(_escopo(select(Animal), Animal.fazenda_id, fazenda_id)).all()
    }
    por_produto: dict[str, int] = defaultdict(int)
    for s in linhas:
        por_produto[s.produto] += 1
    cortadas, cortou = _cortar(linhas)
    return {
        "periodo": {"data_inicio": _iso(ini), "data_fim": _iso(fim)},
        "total": len(linhas), "animais_distintos": len({s.numero_matriz for s in linhas}),
        "por_produto": dict(sorted(por_produto.items(), key=lambda kv: -kv[1])[:30]),
        "aplicacoes": [
            {
                "numero": s.numero_matriz, "data": _iso(s.data_aplicacao), "produto": s.produto, "categoria": s.categoria,
                "dose": s.dose, "unidade": s.unidade, "via": s.via, "responsavel": s.responsavel,
                "atividade": s.atividade, "natureza": s.natureza or "curativo", "obs": s.obs,
                "lote": s.lote or (animais[s.numero_matriz].grupo_primario if s.numero_matriz in animais else None),
            }
            for s in cortadas
        ],
        "limitado_pela_ferramenta": cortou,
    }


# ===========================================================================
# (d) Pedidos e cotações
# ===========================================================================
def _pedidos(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers.pedidos import listar_pedidos

    ini, fim = _periodo(entrada, obrigatorio=False)
    tipo = _escolha(entrada, "tipo", ("compra", "venda"))
    status = _escolha(entrada, "status", ("aberto", "parcialmente_atendido", "atendido", "cancelado"))
    fornecedor, produto, numero = _txt(entrada, "fornecedor"), _txt(entrada, "produto"), _txt(entrada, "numero_pedido")
    pedidos = _chamar(listar_pedidos, session, fazenda_id, tipo=tipo, status=status, data_inicio=ini, data_fim=fim)
    if fornecedor:
        pedidos = [p for p in pedidos if _contem(p.get("fornecedor_cliente"), fornecedor)]
    if numero:
        pedidos = [p for p in pedidos if _contem(p.get("numero_pedido"), numero)]
    if produto:
        pedidos = [p for p in pedidos if any(_contem(i.get("produto_servico"), produto) for i in p["itens"])]
    por_status: dict[str, dict] = {}
    for p in pedidos:
        d = por_status.setdefault(p["status"], {"pedidos": 0, "valor_estimado": 0.0})
        d["pedidos"] += 1
        d["valor_estimado"] = round(d["valor_estimado"] + (p.get("valor_total_estimado") or 0), 2)
    cortadas, cortou = _cortar(pedidos)
    campos = ("numero_pedido", "tipo", "status", "fornecedor_cliente", "centro_custo", "data_pedido", "data_prevista",
              "valor_total_estimado", "valor_atendido", "responsavel", "observacao", "enviado")
    item_campos = ("tipo_item", "produto_servico", "quantidade", "unidade", "valor_unitario_estimado",
                   "valor_total_estimado", "quantidade_entregue", "quantidade_atendida", "valor_atendido")
    return {
        "periodo": {"data_inicio": _iso(ini), "data_fim": _iso(fim)},
        "total": len(pedidos), "por_status": por_status,
        "valor_total_estimado": round(sum(p.get("valor_total_estimado") or 0 for p in pedidos), 2),
        "pedidos": [{**_pegar(p, campos), "itens": [_pegar(i, item_campos) for i in p["itens"]]} for p in cortadas],
        "limitado_pela_ferramenta": cortou,
    }


def _cotacoes(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers.cotacoes import listar_cotacoes, obter_cotacao
    from fazenda.models import Cotacao

    ini, fim = _periodo(entrada, obrigatorio=False)
    status = _escolha(entrada, "status", (
        "rascunho", "enviada", "parcialmente_respondida", "respondida", "comparada", "pedidos_gerados", "expirada", "cancelada",
    ))
    numero, categoria = _txt(entrada, "numero_cotacao"), _txt(entrada, "categoria")
    cotacoes = _chamar(listar_cotacoes, session, fazenda_id, status=status)
    cotacoes = [c for c in cotacoes if _no_periodo(c.get("criado_em"), ini, fim)]
    if categoria:
        cotacoes = [c for c in cotacoes if _contem(c.get("categoria"), categoria)]
    if numero:
        cotacoes = [c for c in cotacoes if _contem(c.get("numero_cotacao"), numero)]
    campos = ("id", "numero_cotacao", "categoria", "modo", "status", "prazo_resposta", "criado_em",
              "total_fornecedores", "total_respondidos", "observacao")
    saida: dict[str, Any] = {
        "periodo": {"data_inicio": _iso(ini), "data_fim": _iso(fim)},
        "total": len(cotacoes), "cotacoes": [_pegar(c, campos) for c in cotacoes[:MAX_LINHAS]],
    }
    if numero and len(cotacoes) == 1:  # detalhe: itens × fornecedores × preços (a "comparação" do site)
        d = _chamar(obter_cotacao, session, fazenda_id, cotacao_id=cotacoes[0]["id"])
        itens = {i["id"]: i for i in d["itens"]}
        forn = {f["id"]: f.get("fornecedor_nome") for f in d["fornecedores"]}
        saida["detalhe"] = {
            "itens": [_pegar(i, ("produto", "quantidade", "unidade")) for i in d["itens"]],
            "fornecedores": [
                {"fornecedor": f.get("fornecedor_nome"), "status_envio": f.get("status_envio"),
                 "canal": f.get("canal"), "respondido_em": _iso(f.get("respondido_em"))}
                for f in d["fornecedores"]
            ],
            "respostas": [
                {"fornecedor": forn.get(r["cotacao_fornecedor_id"]), "produto": itens.get(r["cotacao_item_id"], {}).get("produto"),
                 "recusado": r.get("recusado"), "preco_unitario": r.get("preco_unitario"),
                 "frete_incluso": r.get("frete_incluso"), "valor_frete": r.get("valor_frete"),
                 "prazo_entrega_dias": r.get("prazo_entrega_dias"), "condicao_pagamento": r.get("condicao_pagamento"),
                 "vencedor": r.get("vencedor")}
                for r in d["respostas"]
            ],
        }
    elif len(cotacoes) > 1 and not numero:
        saida["dica"] = "Para ver itens, fornecedores e preços de uma cotação, repita informando 'numero_cotacao'."
    _ = Cotacao  # (import mantido para deixar claro o modelo de origem)
    return saida


# ===========================================================================
# (e) Financeiro e estoque
# ===========================================================================
def _contas(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.models import ContaGerencial

    ini, fim = _periodo(entrada, obrigatorio=False)
    tipo = _escolha(entrada, "tipo", ("pagar", "receber", "todas"), "todas")
    situacao = _escolha(entrada, "situacao", ("aberta", "paga", "vencida", "todas"), "todas")
    campo = _escolha(entrada, "campo_data", ("vencimento", "pagamento", "competencia"), "vencimento")
    fornecedor, categoria = _txt(entrada, "fornecedor"), _txt(entrada, "categoria")
    centro, texto = _txt(entrada, "centro_custo"), _txt(entrada, "texto")
    if not (ini or fim) and situacao in ("todas", "paga"):
        raise ErroConsulta(
            "Informe o período (data_inicio e data_fim, AAAA-MM-DD) — ou use situacao='aberta' ou 'vencida' para ver "
            "só o que está pendente. Se o usuário não disse o período, pergunte."
        )
    coluna = {"vencimento": ContaGerencial.data_vencimento, "pagamento": ContaGerencial.data_pagamento,
              "competencia": ContaGerencial.data_competencia}[campo]
    q = _escopo(select(ContaGerencial), ContaGerencial.fazenda_id, fazenda_id)
    if ini:
        q = q.where(coluna >= ini)
    if fim:
        q = q.where(coluna <= fim)
    if tipo != "todas":
        q = q.where(ContaGerencial.tipo == ("despesa" if tipo == "pagar" else "receita"))
    hoje = date.today()
    contas = list(session.exec(q.order_by(coluna, ContaGerencial.id)).all())

    def _aberta(c) -> bool:  # mesma regra do site (contas-a-pagar / consultar_financeiro)
        return (c.valor_pago or 0) < (c.valor_total or 0)

    if situacao == "aberta":
        contas = [c for c in contas if _aberta(c)]
    elif situacao == "paga":
        contas = [c for c in contas if not _aberta(c)]
    elif situacao == "vencida":
        contas = [c for c in contas if _aberta(c) and c.data_vencimento and c.data_vencimento < hoje]
    if fornecedor:
        contas = [c for c in contas if _contem(c.fornecedor_cliente, fornecedor)]
    if categoria:
        contas = [c for c in contas if _contem(c.classificacao, categoria) or _contem(c.codigo_conta, categoria)]
    if centro:
        contas = [c for c in contas if _contem(c.centro_custo, centro)]
    if texto:
        contas = [c for c in contas if _contem(c.descricao, texto) or _contem(c.numero_nota, texto)]

    def _soma(itens, f) -> float:
        return round(sum(f(c) for c in itens), 2)

    em_aberto = lambda c: max((c.valor_total or 0) - (c.valor_pago or 0), 0) if _aberta(c) else 0.0  # noqa: E731
    pagar = [c for c in contas if c.tipo == "despesa"]
    receber = [c for c in contas if c.tipo == "receita"]
    por_cat: dict[str, dict] = {}
    for c in contas:
        d = por_cat.setdefault(c.classificacao or "(sem classificação)", {"despesas": 0.0, "receitas": 0.0, "lancamentos": 0})
        d["despesas" if c.tipo == "despesa" else "receitas"] = round(
            d["despesas" if c.tipo == "despesa" else "receitas"] + (c.valor_total or 0), 2)
        d["lancamentos"] += 1
    cortadas, cortou = _cortar(contas)
    return {
        "periodo": {"data_inicio": _iso(ini), "data_fim": _iso(fim), "campo_data": campo},
        "filtros": {"tipo": tipo, "situacao": situacao},
        "total_lancamentos": len(contas),
        "a_pagar": {"qtd": len(pagar), "valor_total": _soma(pagar, lambda c: c.valor_total or 0),
                    "valor_em_aberto": _soma(pagar, em_aberto)},
        "a_receber": {"qtd": len(receber), "valor_total": _soma(receber, lambda c: c.valor_total or 0),
                      "valor_em_aberto": _soma(receber, em_aberto)},
        "por_categoria": dict(sorted(por_cat.items(), key=lambda kv: -(kv[1]["despesas"] + kv[1]["receitas"]))[:30]),
        "lancamentos": [
            {
                "id": c.id, "numero_lancamento": c.numero_lancamento, "tipo": "pagar" if c.tipo == "despesa" else "receber",
                "descricao": c.descricao, "fornecedor_cliente": c.fornecedor_cliente, "classificacao": c.classificacao,
                "centro_custo": c.centro_custo, "valor_total": c.valor_total, "valor_pago": c.valor_pago,
                "valor_em_aberto": round(em_aberto(c), 2), "data_vencimento": _iso(c.data_vencimento),
                "data_pagamento": _iso(c.data_pagamento), "data_competencia": _iso(c.data_competencia),
                "parcela": f"{c.parcela_num}/{c.parcela_total}" if c.parcela_num and c.parcela_total else None,
                "situacao": ("vencida" if (_aberta(c) and c.data_vencimento and c.data_vencimento < hoje)
                             else "aberta" if _aberta(c) else "paga"),
                "forma_pagamento": c.forma_pagamento, "numero_nota": c.numero_nota,
            }
            for c in cortadas
        ],
        "limitado_pela_ferramenta": cortou,
        "como_ler": "valor_total = valor da parcela; valor_em_aberto = o que ainda falta pagar/receber (total − pago).",
    }


def _estoque_itens(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.models import Estoque, Fornecedor, LoteEstoque

    nome, categoria, finalidade = _txt(entrada, "nome"), _txt(entrada, "categoria"), _txt(entrada, "finalidade")
    situacao = _escolha(entrada, "situacao", ("abaixo_minimo", "zerado", "todos"), "todos")
    vence_em = _inteiro(entrada, "vencendo_em_dias", 0, 3650)
    incluir_lotes = _bool(entrada, "incluir_lotes", False) or vence_em is not None
    incluir_inativos = _bool(entrada, "incluir_inativos", False)
    hoje = date.today()

    fornecedores = {f.id: f.nome for f in session.exec(_escopo(select(Fornecedor), Fornecedor.fazenda_id, fazenda_id)).all()}
    itens = list(session.exec(_escopo(select(Estoque), Estoque.fazenda_id, fazenda_id).order_by(Estoque.nome)).all())
    if not incluir_inativos:
        itens = [i for i in itens if i.ativo is not False]
    if nome:
        itens = [i for i in itens if _contem(i.nome, nome)]
    if categoria:
        itens = [i for i in itens if _contem(i.categoria, categoria)]
    if finalidade:
        itens = [i for i in itens if _contem(i.finalidade, finalidade)]
    if situacao == "abaixo_minimo":
        itens = [i for i in itens if i.abaixo_minimo]
    elif situacao == "zerado":
        itens = [i for i in itens if (i.quantidade or 0) <= 0]

    lotes_por_item: dict[int, list] = defaultdict(list)
    if incluir_lotes and itens:
        ids = [i.id for i in itens]
        for l in session.exec(
            _escopo(select(LoteEstoque).where(LoteEstoque.estoque_id.in_(ids)), LoteEstoque.fazenda_id, fazenda_id)
        ).all():
            if l.ativo and (l.quantidade_restante or 0) > 0:
                lotes_por_item[l.estoque_id].append(l)
    if vence_em is not None:
        limite = hoje + timedelta(days=vence_em)
        itens = [i for i in itens if any(l.validade and l.validade <= limite for l in lotes_por_item.get(i.id, []))]

    def _lote(l) -> dict:
        return {
            "numero_lote": l.numero_lote, "validade": _iso(l.validade), "quantidade_restante": l.quantidade_restante,
            "data_compra": _iso(l.data_compra),
            "vencido": bool(l.validade and l.validade < hoje),
            "dias_para_vencer": (l.validade - hoje).days if l.validade else None,
        }

    cortadas, cortou = _cortar(itens)
    linhas = []
    for i in cortadas:
        d = {
            "nome": i.nome, "categoria": i.categoria, "finalidade": i.finalidade, "quantidade": i.quantidade,
            "unidade": i.unidade, "estoque_minimo": i.estoque_minimo, "abaixo_minimo": bool(i.abaixo_minimo),
            "valor_unitario": i.valor_unitario, "valor_total": i.valor_total, "fornecedor": fornecedores.get(i.fornecedor_id),
            "local": i.local_armazenamento, "ativo": i.ativo is not False,
        }
        if incluir_lotes:
            ls = sorted(lotes_por_item.get(i.id, []), key=lambda l: (l.validade is None, l.validade or date.max))
            d["lotes"] = [_lote(l) for l in ls]
        linhas.append(d)
    return {
        "total": len(itens), "abaixo_do_minimo": sum(1 for i in itens if i.abaixo_minimo),
        "valor_total_estoque": round(sum(i.valor_total or 0 for i in itens), 2),
        "itens": linhas, "limitado_pela_ferramenta": cortou,
        "como_ler": "Itens inativos ficam de fora (use incluir_inativos=true para vê-los). 'lotes' = frascos/lotes com saldo e validade.",
    }


# ===========================================================================
# (f) Produção de leite (controle leiteiro)
# ===========================================================================
def _producao_leite(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.api.routers.producao import listar_controles

    ini, fim = _periodo(entrada, obrigatorio=True)
    numero, lote = _txt(entrada, "numero"), _txt(entrada, "lote")
    agrupar = _escolha(entrada, "agrupar_por", ("dia", "mes", "animal", "lote", "nenhum"), "mes")
    regs = [
        r for r in _chamar(listar_controles, session, fazenda_id)["controles"]
        if _no_periodo(r.get("data"), ini, fim)
        and (not numero or str(r.get("numero")) == numero)
        and (not lote or _contem(r.get("grupo_primario"), lote))
    ]
    kg = [r["producao_kg"] for r in regs if r.get("producao_kg") is not None]

    def _agr(chave: Callable[[dict], str]) -> list[dict]:
        grupos: dict[str, list[float]] = defaultdict(list)
        animais: dict[str, set] = defaultdict(set)
        for r in regs:
            if r.get("producao_kg") is None:
                continue
            k = chave(r)
            grupos[k].append(r["producao_kg"])
            animais[k].add(r["numero"])
        return [
            {"grupo": k, "controles": len(v), "animais": len(animais[k]), "total_kg": round(sum(v), 1),
             "media_kg_por_controle": round(sum(v) / len(v), 2)}
            for k, v in sorted(grupos.items())
        ]

    saida: dict[str, Any] = {
        "periodo": {"data_inicio": ini.isoformat(), "data_fim": fim.isoformat()},
        "controles": len(kg), "animais_distintos": len({r["numero"] for r in regs if r.get("producao_kg") is not None}),
        "total_kg": round(sum(kg), 1), "media_kg_por_controle": round(sum(kg) / len(kg), 2) if kg else None,
        "como_ler": "Cada controle = 1 pesagem de 1 vaca num dia (producao_kg = soma das ordenhas do dia). 'lote' é o lote ATUAL da vaca.",
    }
    chaves = {"dia": lambda r: r["data"], "mes": lambda r: (r["data"] or "")[:7], "animal": lambda r: str(r["numero"]),
              "lote": lambda r: r.get("grupo_primario") or "(sem lote)"}
    if agrupar != "nenhum":
        grupos = _agr(chaves[agrupar])
        saida["agrupado_por"] = agrupar
        saida["grupos"], saida["grupos_limitado_pela_ferramenta"] = _cortar(grupos)
    if numero:
        regs.sort(key=lambda r: r["data"] or "", reverse=True)
        saida["controles_do_animal"], _ = _cortar([
            _pegar(r, ("data", "producao_kg", "ordenha1_kg", "ordenha2_kg", "ordenha3_kg", "del", "ordem_parto")) for r in regs
        ])
    return saida


# ===========================================================================
# (a) Catálogo de relatórios + execução
# ===========================================================================
def _catalogo_relatorios() -> dict[str, dict]:
    """id -> {titulo, descricao, modulo, parametros, executar(session, fid, p)}.
    Cada `executar` só delega ao endpoint do site que gera o relatório."""
    from fazenda.api.routers import (
        relatorio_acasalamento, relatorio_compra_semen, relatorio_compra_venda_animal, relatorio_custo_hectare,
        relatorio_custo_producao, relatorio_custo_safra, relatorio_rastreabilidade_sanitaria, relatorios,
    )
    from fazenda.api.routers import financeiro as fin
    from fazenda.api.routers import indicadores as ind
    from fazenda.api.routers import producao as prod
    from fazenda.api.routers import sanidade as san

    def p(descricao: str, tipo: str = "string", obrigatorio: bool = False) -> dict:
        return {"descricao": descricao, "tipo": tipo, "obrigatorio": obrigatorio}

    PERIODO = {"data_inicio": p("Início AAAA-MM-DD", obrigatorio=True), "data_fim": p("Fim AAAA-MM-DD", obrigatorio=True)}
    DE_ATE = {"data_inicio": p("Início AAAA-MM-DD"), "data_fim": p("Fim AAAA-MM-DD")}

    def _i(params, nome, padrao=None):
        v = params.get(nome)
        return padrao if v in (None, "") else _inteiro(params, nome)

    return {
        "manejo": {
            "titulo": "Relatórios de manejo (listas semaforizadas: o que fazer hoje)", "modulo": "reproducao", "parametros": {},
            "descricao": "8 listas de manejo reprodutivo de hoje (a inseminar, a diagnosticar, a secar, etc.). Sem parâmetros.",
            "executar": lambda s, f, a: _chamar(relatorios.relatorios_manejo, s, f),
        },
        "distribuicao_del": {
            "titulo": "Distribuição de DEL no serviço", "modulo": "reproducao",
            "parametros": {"ordem": p("1, 2, 3 ou 4 (=4º ou mais serviço)", "integer"), "del_min": p("DEL mínimo", "integer"), "del_max": p("DEL máximo", "integer")},
            "descricao": "Em que DEL os serviços foram feitos, por ordem do serviço.",
            "executar": lambda s, f, a: _chamar(relatorios.gerencial_distribuicao_del, s, f, ordem=_i(a, "ordem", 1), del_min=_i(a, "del_min", 0), del_max=_i(a, "del_max", 350)),
        },
        "prenhezes_por_del": {
            "titulo": "Prenhezes por DEL", "modulo": "reproducao",
            "parametros": {"del_min": p("DEL mínimo", "integer"), "del_max": p("DEL máximo", "integer")},
            "descricao": "Em que DEL as vacas ficaram prenhes.",
            "executar": lambda s, f, a: _chamar(relatorios.gerencial_prenhezes_por_del, s, f, del_min=_i(a, "del_min", 0), del_max=_i(a, "del_max", 400)),
        },
        "dias_para_diagnostico": {
            "titulo": "Dias do serviço ao diagnóstico", "modulo": "reproducao",
            "parametros": {"del_min": p("DEL mínimo", "integer"), "del_max": p("DEL máximo", "integer")},
            "descricao": "Quantos dias levou do serviço ao diagnóstico de gestação.",
            "executar": lambda s, f, a: _chamar(relatorios.gerencial_dias_diagnostico, s, f, del_min=_i(a, "del_min", 0), del_max=_i(a, "del_max", 400)),
        },
        "intervalo_entre_servicos": {
            "titulo": "Intervalo entre serviços", "modulo": "reproducao", "parametros": {},
            "descricao": "Distribuição do intervalo entre serviços consecutivos da mesma vaca.",
            "executar": lambda s, f, a: _chamar(relatorios.gerencial_intervalo_servicos, s, f),
        },
        "dias_para_reinseminacao": {
            "titulo": "Dias até a reinseminação", "modulo": "reproducao", "parametros": {},
            "descricao": "Dias do parto/negativo até a reinseminação.",
            "executar": lambda s, f, a: _chamar(relatorios.gerencial_dias_reinseminacao, s, f),
        },
        "taxa_servico_prenhez_por_del": {
            "titulo": "Taxa de serviço e de prenhez por faixa de DEL (hoje)", "modulo": "reproducao", "parametros": {},
            "descricao": "Foto de hoje: por faixa de DEL, quantas vacas foram servidas e quantas estão prenhes.",
            "executar": lambda s, f, a: _chamar(relatorios.gerencial_taxa_servico_prenhez, s, f),
        },
        "fluxo_lactacao": {
            "titulo": "Fluxo de lactação (projeção mensal)", "modulo": "reproducao",
            "parametros": {"meses": p("Meses de projeção (1 a 24, padrão 8)", "integer")},
            "descricao": "Projeção do saldo de vacas em lactação mês a mês.",
            "executar": lambda s, f, a: _chamar(relatorios.gerencial_fluxo_lactacao, s, f, meses=_inteiro(a, "meses", 1, 24) or 8),
        },
        "acasalamento": {
            "titulo": "Sugestão de acasalamento (touro) para uma vaca", "modulo": "reproducao",
            "parametros": {"numero": p("Número da vaca", obrigatorio=True)},
            "descricao": "Sugere touros (com sêmen em estoque) evitando consanguinidade.",
            "executar": lambda s, f, a: _chamar(relatorio_acasalamento.sugestao_acasalamento, s, f, numero_matriz=_txt(a, "numero") or ""),
        },
        "relatorio_personalizado": {
            "titulo": "Relatório personalizado (colunas escolhidas por animal)", "modulo": ("analise", "indicadores"),
            "parametros": {"colunas": p("Colunas separadas por vírgula (ex.: numero,categoria_completa,del_dias,numero_servicos). Veja o catálogo em /indicadores/relatorio-personalizado/catalogo", obrigatorio=True),
                           **DE_ATE},
            "descricao": "Tabela com as colunas pedidas para cada animal (ex.: nº de serviços, DEL, produção).",
            "executar": lambda s, f, a: _chamar(
                ind.relatorio_personalizado, s, f,
                dados=ind.RelatorioPersonalizadoIn(
                    parametros=[c.strip() for c in (_txt(a, "colunas") or "").split(",") if c.strip()],
                    data_de=_data(a, "data_inicio"), data_ate=_data(a, "data_fim"),
                ),
            ),
        },
        "taxa_cura": {
            "titulo": "Taxa de cura (tratamentos curativos)", "modulo": "sanidade", "parametros": {},
            "descricao": "Casos curativos avaliados e a taxa de cura.",
            "executar": lambda s, f, a: _chamar(san.relatorio_taxa_cura, s, f),
        },
        "rastreabilidade_sanitaria": {
            "titulo": "Rastreabilidade sanitária (aplicações por animal/GTA)", "modulo": "sanidade",
            "parametros": {"numero": p("Número do animal"), "gta": p("Número da GTA"), **DE_ATE},
            "descricao": "Histórico sanitário do animal com carência e destino.",
            "executar": lambda s, f, a: _chamar(relatorio_rastreabilidade_sanitaria.relatorio, s, f, numero=_txt(a, "numero"), gta=_txt(a, "gta"), data_de=_data(a, "data_inicio"), data_ate=_data(a, "data_fim")),
        },
        "compra_semen": {
            "titulo": "Compras de sêmen", "modulo": "rebanho",
            "parametros": {"touro": p("Nome do touro"), "naab": p("NAAB"), "vendedor": p("Vendedor"), "numero_documento": p("Nº do documento"), **DE_ATE},
            "descricao": "Compras de sêmen no período.",
            "executar": lambda s, f, a: _chamar(relatorio_compra_semen.relatorio, s, f, touro=_txt(a, "touro"), naab=_txt(a, "naab"), vendedor=_txt(a, "vendedor"), data_de=_data(a, "data_inicio"), data_ate=_data(a, "data_fim"), numero_documento=_txt(a, "numero_documento")),
        },
        "compra_venda_animal": {
            "titulo": "Compra e venda de animais", "modulo": "rebanho",
            "parametros": {"numero": p("Número do animal"), "gta": p("GTA"), "numero_documento": p("Nº do documento"), **DE_ATE},
            "descricao": "Compras e vendas de animais no período.",
            "executar": lambda s, f, a: _chamar(relatorio_compra_venda_animal.relatorio, s, f, numero=_txt(a, "numero"), data_de=_data(a, "data_inicio"), data_ate=_data(a, "data_fim"), numero_documento=_txt(a, "numero_documento"), gta=_txt(a, "gta")),
        },
        "dre": {
            "titulo": "DRE gerencial (receitas, despesas e resultado)", "modulo": "financeiro",
            "parametros": {**PERIODO, "regime": p("competencia (padrão) ou caixa"), "centro_custo": p("Centro de custo")},
            "descricao": "Demonstração do resultado do período, em cascata.",
            "executar": lambda s, f, a: _chamar(fin.dre, s, f, data_inicio=_data(a, "data_inicio"), data_fim=_data(a, "data_fim"), centro_custo=_txt(a, "centro_custo"), regime=_escolha(a, "regime", ("competencia", "caixa"), "competencia")),
        },
        "custo_litro_leite": {
            "titulo": "Custo por litro de leite", "modulo": "financeiro", "parametros": PERIODO,
            "descricao": "Gasto com alimentação ÷ litros entregues no período.",
            "executar": lambda s, f, a: _chamar(fin.custo_litro_leite, s, f, data_inicio=_data(a, "data_inicio"), data_fim=_data(a, "data_fim")),
        },
        "custo_vaca_lote": {
            "titulo": "Custo por vaca e por lote", "modulo": "financeiro",
            "parametros": {**PERIODO, "centro_custo": p("Centro de custo (padrão do relatório)")},
            "descricao": "Despesas do período divididas por vaca/lote.",
            "executar": lambda s, f, a: _chamar(relatorio_custo_producao.custo_por_vaca_e_lote, s, f, data_inicio=_data(a, "data_inicio"), data_fim=_data(a, "data_fim"), **({"centro_custo": _txt(a, "centro_custo")} if _txt(a, "centro_custo") else {})),
        },
        "custo_hectare": {
            "titulo": "Custo por hectare", "modulo": "financeiro",
            "parametros": {**PERIODO, "centro_custo": p("Centro de custo")},
            "descricao": "Custo agrícola por hectare no período.",
            "executar": lambda s, f, a: _chamar(relatorio_custo_hectare.custo_por_hectare, s, f, data_inicio=_data(a, "data_inicio"), data_fim=_data(a, "data_fim"), centro_custo=_txt(a, "centro_custo")),
        },
        "custo_safra": {
            "titulo": "Custo por safra", "modulo": "financeiro",
            "parametros": {"safra_id": p("ID da safra", "integer", True)},
            "descricao": "Custo de uma safra por categoria.",
            "executar": lambda s, f, a: _chamar(relatorio_custo_safra.custo_por_safra, s, f, safra_id=_inteiro(a, "safra_id", 1)),
        },
        "controle_x_entrega_leite": {
            "titulo": "Controle leiteiro × leite entregue", "modulo": "producao", "parametros": PERIODO,
            "descricao": "Leite do controle projetado × entregue ao laticínio, bezerros e equipe no período.",
            "executar": lambda s, f, a: _chamar(prod.relatorio_controle_entrega, s, f, data_inicio=_data(a, "data_inicio").isoformat(), data_fim=_data(a, "data_fim").isoformat()),
        },
    }


def _listar_relatorios(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.rules.assistente import modulo_liberado

    texto = _txt(entrada, "busca")
    itens = []
    for rid, r in _catalogo_relatorios().items():
        if not modulo_liberado(usuario, r["modulo"]):
            continue
        if texto and not (_contem(r["titulo"], texto) or _contem(r["descricao"], texto) or _contem(rid, texto)):
            continue
        itens.append({"relatorio": rid, "titulo": r["titulo"], "descricao": r["descricao"], "parametros": r["parametros"]})
    return {
        "total": len(itens), "relatorios": itens,
        "como_usar": "Chame executar_relatorio com 'relatorio' = o código e os parâmetros listados (datas em AAAA-MM-DD).",
        "outros_dados": "Taxa de concepção/prenhez/serviço por período: use consultar_indicadores_reprodutivos e consultar_ciclos_21_dias.",
    }


def _executar_relatorio(session: Session, usuario, entrada: dict, fazenda_id: int | None) -> dict:
    from fazenda.rules.assistente import modulo_liberado

    rid = _txt(entrada, "relatorio")
    catalogo = _catalogo_relatorios()
    if not rid:
        raise ErroConsulta("Informe 'relatorio' (código). Use listar_relatorios para ver os disponíveis.")
    r = catalogo.get(_sem_acento(rid).replace(" ", "_").replace("-", "_"))
    if r is None:
        raise ErroConsulta(f"Relatório desconhecido: '{rid}'. Use listar_relatorios para ver os códigos válidos.")
    if not modulo_liberado(usuario, r["modulo"]):
        raise ErroConsulta(f"Usuário sem permissão para o módulo deste relatório ('{r['modulo']}').")
    params = {k: v for k, v in entrada.items() if k != "relatorio"}
    _periodo(params, obrigatorio=False)  # valida data_inicio/data_fim (formato, ordem, 5 anos) antes de tudo
    desconhecidos = sorted(set(params) - set(r["parametros"]))
    if desconhecidos:
        raise ErroConsulta(f"Parâmetro(s) desconhecido(s) para '{rid}': {', '.join(desconhecidos)}. Aceitos: {', '.join(r['parametros']) or 'nenhum'}.")
    faltando = [k for k, d in r["parametros"].items() if d.get("obrigatorio") and not _txt(params, k)]
    if faltando:
        raise ErroConsulta(f"Informe: {', '.join(faltando)}. Se o usuário não disse, pergunte a ele.")
    return {"relatorio": rid, "titulo": r["titulo"], "dados": r["executar"](session, fazenda_id, params)}


# ===========================================================================
# Registro das ferramentas
# ===========================================================================
def _schema(props: dict[str, tuple[str, str]], required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": {k: {"type": t, "description": d} for k, (t, d) in props.items()},
        **({"required": required} if required else {}),
        "additionalProperties": False,
    }


_DI = ("string", "Data inicial do período, formato AAAA-MM-DD (ex.: 2026-01-01).")
_DF = ("string", "Data final do período, formato AAAA-MM-DD (ex.: 2026-07-01). Máximo 5 anos entre as duas.")
_FILTROS_REPRO = {
    "tipo_servico": ("string", "Opcional. Tipo do serviço, ex.: 'Inseminação' ou 'Cobertura' (vários separados por vírgula)."),
    "metodo_ia": ("string", "Opcional. 'IATF', 'IA em cio natural' ou 'Monta natural'."),
    "touro": ("string", "Opcional. Nome do touro/sêmen (igual ao cadastro)."),
    "inseminador": ("string", "Opcional. Nome do inseminador."),
    "ordem_parto": ("string", "Opcional. Ordem de parto da vaca (1, 2, 3...)."),
    "ordem_tentativa": ("string", "Opcional. Ordem da tentativa de inseminação (1, 2, 3...)."),
}

_MODULOS_RELATORIOS = ("indicadores", "reproducao", "analise", "sanidade", "financeiro", "producao", "rebanho")

FERRAMENTAS: list[dict] = [
    # ---- (a) reprodução por período --------------------------------------
    {
        "modulo": ("reproducao", "analise"),
        "spec": {
            "name": "consultar_indicadores_reprodutivos",
            "description": (
                "Indicadores reprodutivos de um PERÍODO (taxa de concepção, serviços, diagnósticos positivos/negativos, "
                "perdas de prenhez, partos e secagens). Use para perguntas como 'qual a minha taxa de concepção de "
                "01/01/2026 a 01/07/2026?', 'quantos partos tive no 1º semestre?', 'qual a taxa de concepção do touro X "
                "ou da IATF neste período?'. Os números são os mesmos da tela Relatórios › Análise reprodutiva. "
                "OBRIGATÓRIO informar data_inicio e data_fim (AAAA-MM-DD); se o usuário não disse o período, pergunte. "
                "Filtros opcionais: tipo_servico, metodo_ia, touro, inseminador, ordem_parto, ordem_tentativa; "
                "agrupar_por quebra a taxa por uma dessas dimensões (ex.: agrupar_por='touro' para comparar touros). "
                "Para taxa de serviço/prenhez em ciclos de 21 dias use consultar_ciclos_21_dias."
            ),
            "input_schema": _schema({
                "data_inicio": _DI, "data_fim": _DF, **_FILTROS_REPRO,
                "agrupar_por": ("string", "Opcional. Quebra a taxa por: tipo_servico, metodo_ia, touro, inseminador, ordem_parto ou ordem_tentativa."),
            }),
        },
        "executor": _com_erro(_indicadores_reprodutivos),
    },
    {
        "modulo": ("reproducao", "analise"),
        "spec": {
            "name": "consultar_ciclos_21_dias",
            "description": (
                "Taxa de serviço, taxa de prenhez e taxa de concepção por CICLOS DE 21 DIAS (o 'BREDSUM' da tela "
                "Reprodução › Ciclos de 21 dias), respeitando Configurações › Parâmetros (PEV, meta, janela de resultado). "
                "Use para 'qual minha taxa de serviço/prenhez nos últimos ciclos?'. Informe data_inicio e data_fim (os ciclos "
                "terminam em data_fim e cobrem o início) OU ancora + n_ciclos. Sem nada, devolve os 6 últimos ciclos até hoje. "
                "categoria: todas, vaca ou novilha."
            ),
            "input_schema": _schema({
                "data_inicio": _DI, "data_fim": _DF,
                "ancora": ("string", "Opcional. Data de referência dos ciclos (AAAA-MM-DD); alternativa ao período."),
                "modo": ("string", "Opcional. 'fim' (conta para trás a partir da âncora, padrão) ou 'inicio' (conta para frente)."),
                "n_ciclos": ("integer", "Opcional. Quantidade de ciclos de 21 dias (1 a 26, padrão 6)."),
                "categoria": ("string", "Opcional. 'todas' (padrão), 'vaca' ou 'novilha'."),
            }),
        },
        "executor": _com_erro(_ciclos_21_dias),
    },
    {
        "modulo": ("reproducao", "analise"),
        "spec": {
            "name": "consultar_servicos_reprodutivos",
            "description": (
                "Lista as INSEMINAÇÕES/SERVIÇOS (IA, IATF, monta) com touro, inseminador, método, ordem de parto/tentativa, "
                "DEL, diagnóstico de gestação, reconfirmação e perda de prenhez — o histórico de Reprodução › Serviços/IAs/"
                "Diagnósticos/Perdas. Use para 'quais vacas inseminei em junho?', 'qual o histórico de serviços da vaca 123?', "
                "'quais diagnósticos deram positivo neste mês?', 'quais perderam a prenhez?'. Filtros: período, numero (animal), "
                "touro, metodo_ia, tipo_servico, inseminador, diagnostico (POSITIVO, NEGATIVO ou PENDENTE), apenas_perdas. "
                "Sem nenhum filtro de data/animal, usa os últimos 90 dias. Para a TAXA, use consultar_indicadores_reprodutivos."
            ),
            "input_schema": _schema({
                "data_inicio": _DI, "data_fim": _DF,
                "numero": ("string", "Opcional. Número do animal (brinco)."), **_FILTROS_REPRO,
                "diagnostico": ("string", "Opcional. POSITIVO, NEGATIVO ou PENDENTE (sem diagnóstico ainda)."),
                "apenas_perdas": ("boolean", "Opcional. true = só serviços com perda de prenhez."),
            }),
        },
        "executor": _com_erro(_consultar_servicos),
    },
    {
        "modulo": ("reproducao", "analise"),
        "spec": {
            "name": "consultar_partos_secagens",
            "description": (
                "Lista PARTOS e/ou SECAGENS de um período (Reprodução › Histórico). Use para 'quais vacas pariram em maio?', "
                "'quantas secagens fiz no trimestre?', 'quando a vaca 123 secou/pariu?'. tipo: partos, secagens ou ambos "
                "(padrão). Filtros: data_inicio/data_fim e numero (animal). Sem filtro de data/animal usa os últimos 90 dias."
            ),
            "input_schema": _schema({
                "data_inicio": _DI, "data_fim": _DF,
                "tipo": ("string", "Opcional. 'partos', 'secagens' ou 'ambos' (padrão)."),
                "numero": ("string", "Opcional. Número do animal."),
            }),
        },
        "executor": _com_erro(_consultar_partos_secagens),
    },
    {
        "modulo": _MODULOS_RELATORIOS,
        "spec": {
            "name": "listar_relatorios",
            "description": (
                "Lista o CATÁLOGO de relatórios que o site tem (manejo reprodutivo, DEL, intervalo entre serviços, fluxo de "
                "lactação, acasalamento, relatório personalizado, taxa de cura, rastreabilidade sanitária, compras de sêmen e de "
                "animais, DRE, custos por litro/vaca/hectare/safra, controle × entrega de leite) com os PARÂMETROS de cada um. "
                "Use primeiro quando o usuário pedir um relatório 'conforme parâmetros' e você não souber o código; depois "
                "chame executar_relatorio. Só aparecem os relatórios que o usuário pode ver. 'busca' filtra por palavra."
            ),
            "input_schema": _schema({"busca": ("string", "Opcional. Palavra para filtrar (ex.: 'custo', 'DEL', 'sêmen').")}),
        },
        "executor": _com_erro(_listar_relatorios),
    },
    {
        "modulo": _MODULOS_RELATORIOS,
        "spec": {
            "name": "executar_relatorio",
            "description": (
                "Use para rodar um relatório do catálogo (veja listar_relatorios) com os parâmetros pedidos — o mesmo resultado da tela "
                "do site. Informe 'relatorio' (código, ex.: 'dre', 'custo_litro_leite', 'fluxo_lactacao', 'compra_semen') e os "
                "parâmetros dele; datas em AAAA-MM-DD, período de no máximo 5 anos. Se faltar parâmetro obrigatório (ex.: período do "
                "DRE), a resposta traz 'erro' dizendo o que perguntar ao usuário."
            ),
            "input_schema": _schema({
                "relatorio": ("string", "Código do relatório (ex.: 'dre'). Veja listar_relatorios."),
                "data_inicio": _DI, "data_fim": _DF,
                "regime": ("string", "dre: 'competencia' (padrão) ou 'caixa'."),
                "centro_custo": ("string", "dre / custos: centro de custo."),
                "numero": ("string", "Número do animal (acasalamento, rastreabilidade, compra/venda de animal)."),
                "gta": ("string", "Número da GTA."), "touro": ("string", "Nome do touro (compra de sêmen)."),
                "naab": ("string", "NAAB (compra de sêmen)."), "vendedor": ("string", "Vendedor (compra de sêmen)."),
                "numero_documento": ("string", "Número do documento."),
                "colunas": ("string", "relatorio_personalizado: colunas separadas por vírgula."),
                "meses": ("integer", "fluxo_lactacao: meses de projeção (1 a 24)."),
                "ordem": ("integer", "distribuicao_del: ordem do serviço (1 a 4)."),
                "del_min": ("integer", "Faixa de DEL mínima."), "del_max": ("integer", "Faixa de DEL máxima."),
                "safra_id": ("integer", "custo_safra: ID da safra."),
            }, ["relatorio"]),
        },
        "executor": _com_erro(_executar_relatorio),
    },
    # ---- (b) protocolos IATF/indução lançados, BST -----------------------
    {
        "modulo": ("sanidade", "reproducao"),
        "spec": {
            "name": "consultar_protocolos_lancados",
            "description": (
                "Protocolos JÁ LANÇADOS (IATF, indução de lactação, sanitário curativo/preventivo por lote, protocolos próprios) "
                "como na Central de Protocolos (Acompanhamento e Histórico): nome, tipo, datas, etapas realizadas/total, nº de "
                "animais e STATUS (andamento, concluido, encerrado, cancelado). Use para 'quais protocolos IATF estão em "
                "andamento?', 'quais foram cancelados em 2026?', 'quais hormônios do protocolo X?'. Filtros: status, tipo "
                "(reprodutivo, produtivo, sanitario), origem (iatf, inducao, sanitario, customizado), nome, período (sobreposição). "
                "Para ver a grade animal × dia e os HORMÔNIOS/medicamentos de um lançamento, repita com origem + origem_id da linha."
            ),
            "input_schema": _schema({
                "status": ("string", "Opcional. andamento, concluido, encerrado, cancelado ou todos (padrão)."),
                "tipo": ("string", "Opcional. reprodutivo, produtivo, sanitario ou lida."),
                "origem": ("string", "Opcional. iatf, inducao, sanitario, customizado ou lida."),
                "nome": ("string", "Opcional. Parte do nome do protocolo/lançamento."),
                "data_inicio": _DI, "data_fim": _DF,
                "origem_id": ("integer", "Opcional. ID do lançamento (com 'origem') para ver o detalhe e os hormônios."),
            }),
        },
        "executor": _com_erro(_protocolos_lancados),
    },
    {
        "modulo": ("producao", "sanidade"),
        "spec": {
            "name": "consultar_bst",
            "description": (
                "Histórico de aplicações de BST (somatotropina) do relatório de BST de Produção: animal, data, produto, dose, lote. "
                "Use para 'quando apliquei BST na vaca 123?', 'quantas vacas receberam BST em agosto?'. Filtros: período, numero, "
                "lote. Sem filtro de data/animal usa os últimos 90 dias. A agenda de BST de HOJE está em consultar_agenda_hoje."
            ),
            "input_schema": _schema({
                "data_inicio": _DI, "data_fim": _DF, "numero": ("string", "Opcional. Número do animal."),
                "lote": ("string", "Opcional. Lote (ex.: '03' ou parte do nome)."),
            }),
        },
        "executor": _com_erro(_consultar_bst),
    },
    # ---- (c) sanidade -----------------------------------------------------
    {
        "modulo": ("sanidade", "reproducao"),
        "spec": {
            "name": "consultar_protocolos_cadastrados",
            "description": (
                "Protocolos CADASTRADOS (os moldes, não os lançamentos): sanitário curativo, sanitário preventivo, IATF, indução de "
                "lactação e protocolos próprios, com as etapas (dia, produto, dose, via). Use para 'quais protocolos de mastite "
                "tenho?', 'o que tem no protocolo IATF X?', 'quais protocolos preventivos existem?'. tipo: sanitario_curativo, "
                "sanitario_preventivo, iatf, inducao, proprio ou todos (padrão); nome filtra; apenas_ativos=true esconde os desativados."
            ),
            "input_schema": _schema({
                "tipo": ("string", "Opcional. sanitario_curativo, sanitario_preventivo, iatf, inducao, proprio ou todos (padrão)."),
                "nome": ("string", "Opcional. Parte do nome."), "apenas_ativos": ("boolean", "Opcional. true = só os ativos."),
            }),
        },
        "executor": _com_erro(_protocolos_cadastrados),
    },
    {
        "modulo": "sanidade",
        "spec": {
            "name": "consultar_regras_preventivo",
            "description": (
                "REGRAS do calendário sanitário preventivo (vacinas/exames): evento, produto, categoria-alvo, frequência, próxima "
                "ocorrência e última aplicação. Com data_inicio e data_fim, também projeta as ocorrências do período (card Calendário "
                "Sanitário). Use para 'quais vacinas estão no calendário?', 'de quanto em quanto tempo é a aftosa?', 'o que vence entre "
                "01/10 e 31/12?'. Filtros: nome (evento/produto), categoria. Diferente de consultar_calendario_sanitario, que só olha 30 dias."
            ),
            "input_schema": _schema({
                "nome": ("string", "Opcional. Parte do nome do evento/produto (ex.: 'aftosa')."),
                "categoria": ("string", "Opcional. 'vacina', 'exame' ou categoria-alvo."),
                "data_inicio": _DI, "data_fim": _DF,
            }),
        },
        "executor": _com_erro(_regras_preventivo),
    },
    {
        "modulo": "sanidade",
        "spec": {
            "name": "consultar_lista_espera_preventivo",
            "description": (
                "LISTA DE ESPERA do preventivo (Protocolos › Aplicar): animais que entraram na janela de uma vacina/exame e ainda "
                "NÃO foram agendados, por protocolo, com situação 'atrasada' (dias de atraso) ou 'na janela'. Use para 'quantas "
                "vacas estão na lista de espera da vacina X?', 'o que está atrasado no preventivo?'. Filtro: protocolo (parte do nome). "
                "detalhar_animais=false devolve só os totais por protocolo. Somente leitura (não reconcilia nada)."
            ),
            "input_schema": _schema({
                "protocolo": ("string", "Opcional. Parte do nome do protocolo/produto."),
                "calendario_id": ("integer", "Opcional. ID da regra do calendário."),
                "detalhar_animais": ("boolean", "Opcional. false = só totais (padrão true)."),
            }),
        },
        "executor": _com_erro(_lista_espera),
    },
    {
        "modulo": "sanidade",
        "spec": {
            "name": "consultar_agendamentos_preventivo",
            "description": (
                "AGENDAMENTOS do preventivo: situacao='agendados' (Protocolos › Acompanhamento: data, hora, animais, checklist, "
                "responsável, atrasado/hoje), 'concluidos' (Protocolos › Concluídos: aplicações feitas, estornadas e agendamentos "
                "cancelados) ou 'todos'. Use para 'o que está agendado para esta semana?', 'quais vacinas foram aplicadas em setembro?'. "
                "Filtros: protocolo (nome), período (data_inicio/data_fim: data do agendamento ou da aplicação)."
            ),
            "input_schema": _schema({
                "situacao": ("string", "Opcional. agendados (padrão), concluidos ou todos."),
                "protocolo": ("string", "Opcional. Parte do nome do protocolo/produto."),
                "calendario_id": ("integer", "Opcional. ID da regra do calendário."), "data_inicio": _DI, "data_fim": _DF,
            }),
        },
        "executor": _com_erro(_agendamentos_preventivo),
    },
    {
        "modulo": "sanidade",
        "spec": {
            "name": "consultar_aplicacoes_sanitarias",
            "description": (
                "HISTÓRICO de aplicações de medicamentos/vacinas (Sanidade): animal, data, produto, dose, via, responsável, natureza "
                "(curativo/preventivo), atividade. Use para 'o que a vaca 123 já tomou?', 'quem recebeu ivermectina em agosto?', "
                "'quantas doses de aftosa apliquei no ano?'. Exige pelo menos um filtro: período, numero, produto ou atividade. "
                "Também: natureza (curativo/preventivo), categoria. Para BST use consultar_bst."
            ),
            "input_schema": _schema({
                "data_inicio": _DI, "data_fim": _DF, "numero": ("string", "Opcional. Número do animal."),
                "produto": ("string", "Opcional. Parte do nome do produto."),
                "natureza": ("string", "Opcional. curativo ou preventivo."),
                "atividade": ("string", "Opcional. Atividade (ex.: 'Secagem', 'BST', 'Vacinação')."),
                "categoria": ("string", "Opcional. Categoria do produto (Vacina, Antiparasitário...)."),
            }),
        },
        "executor": _com_erro(_aplicacoes_sanitarias),
    },
    # ---- (d) pedidos e cotações ------------------------------------------
    {
        "modulo": "pedidos",
        "spec": {
            "name": "consultar_pedidos",
            "description": (
                "PEDIDOS de compra/venda (tela Pedidos): número, fornecedor/cliente, status (aberto, parcialmente_atendido, atendido, "
                "cancelado), datas, itens e valores. Use para 'quais pedidos estão abertos?', 'o que pedi ao fornecedor X em setembro?', "
                "'quanto tenho em pedidos de compra em aberto?'. Filtros: tipo (compra/venda), status, fornecedor, produto, "
                "numero_pedido, período (data do pedido)."
            ),
            "input_schema": _schema({
                "tipo": ("string", "Opcional. compra ou venda."),
                "status": ("string", "Opcional. aberto, parcialmente_atendido, atendido ou cancelado."),
                "fornecedor": ("string", "Opcional. Parte do nome do fornecedor/cliente."),
                "produto": ("string", "Opcional. Parte do nome do produto/serviço."),
                "numero_pedido": ("string", "Opcional. Número do pedido."), "data_inicio": _DI, "data_fim": _DF,
            }),
        },
        "executor": _com_erro(_pedidos),
    },
    {
        "modulo": "pedidos",
        "spec": {
            "name": "consultar_cotacoes",
            "description": (
                "COTAÇÕES de preço com fornecedores (tela Cotações): número, categoria, status (rascunho, enviada, "
                "parcialmente_respondida, respondida, comparada, pedidos_gerados, expirada, cancelada), prazo e quantos fornecedores "
                "responderam. Informando 'numero_cotacao' devolve também itens, fornecedores e os PREÇOS de cada um (a comparação). "
                "Use para 'quais cotações estão aguardando resposta?', 'qual fornecedor deu o melhor preço na cotação COT-2026-003?'. "
                "Filtros: status, categoria, período (data de criação)."
            ),
            "input_schema": _schema({
                "status": ("string", "Opcional. Status da cotação."), "categoria": ("string", "Opcional. Categoria (ex.: Medicamentos)."),
                "numero_cotacao": ("string", "Opcional. Número da cotação (devolve o detalhe com preços)."),
                "data_inicio": _DI, "data_fim": _DF,
            }),
        },
        "executor": _com_erro(_cotacoes),
    },
    # ---- (e) financeiro e estoque ----------------------------------------
    {
        "modulo": "financeiro",
        "spec": {
            "name": "consultar_contas_financeiras",
            "description": (
                "CONTAS a pagar e a receber por PERÍODO, situação e categoria (Financeiro › lançamentos): totais (valor e em aberto), "
                "totais por categoria e a lista de lançamentos. Use para 'quanto tenho a pagar em outubro?', 'quanto gastei com "
                "medicamentos no 1º semestre?', 'quais contas estão vencidas?', 'quanto recebo do laticínio este mês?'. tipo: pagar, "
                "receber ou todas; situacao: aberta, paga, vencida ou todas; campo_data: vencimento (padrão), pagamento ou competencia "
                "(decide a que data o período se refere); filtros fornecedor, categoria (classificação), centro_custo, texto. "
                "Para 'paga'/'todas' o período é obrigatório; 'aberta'/'vencida' funcionam sem período. Para resultado/DRE use "
                "executar_relatorio('dre')."
            ),
            "input_schema": _schema({
                "data_inicio": _DI, "data_fim": _DF,
                "tipo": ("string", "Opcional. pagar, receber ou todas (padrão)."),
                "situacao": ("string", "Opcional. aberta, paga, vencida ou todas (padrão)."),
                "campo_data": ("string", "Opcional. A data a que o período se refere: vencimento (padrão), pagamento ou competencia."),
                "fornecedor": ("string", "Opcional. Parte do nome do fornecedor/cliente."),
                "categoria": ("string", "Opcional. Parte da classificação do lançamento (ex.: 'Medicamentos')."),
                "centro_custo": ("string", "Opcional. Parte do centro de custo."),
                "texto": ("string", "Opcional. Parte da descrição ou do número da nota."),
            }),
        },
        "executor": _com_erro(_contas),
    },
    {
        "modulo": "estoque",
        "spec": {
            "name": "consultar_estoque_itens",
            "description": (
                "ITENS de estoque com saldo, mínimo, valor e fornecedor; com incluir_lotes=true traz os lotes/frascos com VALIDADE e "
                "saldo. Itens inativos ficam de fora. Use para 'quanto tenho de ivermectina?', 'quais itens estão abaixo do mínimo?', "
                "'o que vence nos próximos 60 dias?' (vencendo_em_dias=60), 'qual o valor total do estoque?'. Filtros: nome, categoria, "
                "finalidade, situacao (abaixo_minimo, zerado ou todos)."
            ),
            "input_schema": _schema({
                "nome": ("string", "Opcional. Parte do nome do item."), "categoria": ("string", "Opcional. Categoria."),
                "finalidade": ("string", "Opcional. Ex.: Medicamento, Ração/Alimento, Material/Insumo."),
                "situacao": ("string", "Opcional. abaixo_minimo, zerado ou todos (padrão)."),
                "incluir_lotes": ("boolean", "Opcional. true = lotes com validade e saldo."),
                "vencendo_em_dias": ("integer", "Opcional. Só itens com lote vencido ou que vence em até N dias."),
                "incluir_inativos": ("boolean", "Opcional. true = inclui itens desativados."),
            }),
        },
        "executor": _com_erro(_estoque_itens),
    },
    # ---- (f) produção de leite -------------------------------------------
    {
        "modulo": "producao",
        "spec": {
            "name": "consultar_producao_leite",
            "description": (
                "PRODUÇÃO DE LEITE (controle leiteiro) de um período: total de kg, nº de controles e animais, média por controle e "
                "agrupamento por dia, mês, animal ou lote. Use para 'quanto leite produzi em agosto?', 'qual a produção da vaca 123 "
                "no semestre?', 'média por lote em setembro?'. OBRIGATÓRIO data_inicio e data_fim (AAAA-MM-DD); se faltarem, pergunte. "
                "Filtros: numero (animal), lote. agrupar_por: dia, mes (padrão), animal, lote ou nenhum. Com 'numero' devolve também "
                "cada controle do animal. Leite ENTREGUE ao laticínio: executar_relatorio('controle_x_entrega_leite')."
            ),
            "input_schema": _schema({
                "data_inicio": _DI, "data_fim": _DF, "numero": ("string", "Opcional. Número do animal."),
                "lote": ("string", "Opcional. Lote atual (código ou parte do nome)."),
                "agrupar_por": ("string", "Opcional. dia, mes (padrão), animal, lote ou nenhum."),
            }),
        },
        "executor": _com_erro(_producao_leite),
    },
]

NOMES = frozenset(f["spec"]["name"] for f in FERRAMENTAS)


def formatar_para_chat(resultado: dict, entrada: dict | None = None) -> dict:
    """Saída das ferramentas deste módulo no chat do site: mesma sanitização e
    mesmo envelope de paginação/limite de bytes do /agente, para o modelo ver o
    mesmo formato (e `truncado`) nos dois canais."""
    from fazenda.rules import agente_leitura as al

    limite = (entrada or {}).get("limite")
    offset = (entrada or {}).get("offset")
    try:
        limite = int(limite) if limite not in (None, "") else al.LIMITE_PADRAO
        offset = int(offset) if offset not in (None, "") else 0
    except (TypeError, ValueError):
        limite, offset = al.LIMITE_PADRAO, 0
    envelope = al.paginar(al.sanitizar(resultado), limite, offset, al.max_bytes())
    return envelope if envelope["truncado"] else envelope["resultado"]
