"""Regras puras de "acasalamento direcionado" — sugestão de touro por
vaca/fêmea a inseminar, combinando 3 critérios (nesta ordem de prioridade):

  1. Evitar consanguinidade — compara a genealogia da fêmea (linha paterna,
     3 gerações prontas no cadastro do Animal, + linha materna resolvida por
     recursão fora desta função) com o NAAB/nome do touro candidato.
  2. Complementar características — usa os índices/provas do touro (TPI,
     NM$, produção) para favorecer quem compensa pontos fracos da vaca/lote.
  3. Só considerar touros com sêmen em estoque — a filtragem por estoque é
     feita ANTES de chamar esta função (no router); aqui o estoque só entra
     como desempate leve.

Função pura (sem FastAPI/DB) — recebe dicts já resolvidos pelo router, para
ficar testável isoladamente sem fixture de banco (mesmo padrão de
`fazenda.rules.custo_leite` / `fazenda.rules.patrimonio`).
"""
from __future__ import annotations

# Penalidade aplicada quando o touro candidato é um ancestral comum
# (pai/avô/bisavô paterno da vaca, ou ascendente materno resolvido pelo
# router) — grande o suficiente para dominar qualquer TPI/NM$ realista (a
# ordenação em si já é lexicográfica por tem_consang, então isto só garante
# que o `score` exibido também fique visivelmente pior, não só a posição).
PENALIDADE_CONSANGUINIDADE = 1_000_000.0

_ROTULOS_DOSES = {"convencional": "convencionais", "sexado": "sexadas"}


def criterios_explicacao() -> list[str]:
    """Texto fixo, em linguagem simples, dos 3 critérios usados na sugestão —
    para a tela de acasalamento direcionado exibir como nota fixa, sempre
    visível, explicando como a lista foi montada."""
    return [
        "Evita consanguinidade: compara a genealogia da vaca (pai, avô e "
        "bisavô paternos, e ascendentes maternos quando cadastrados) com a "
        "do touro candidato, para não repetir um ancestral comum recente.",
        "Complementa características: dá preferência a touros com índices "
        "(TPI, produção) que reforcem os pontos fracos da vaca ou do lote, "
        "ou aos touros com melhores provas em geral quando não há dado "
        "suficiente da vaca.",
        "Só sugere touros com sêmen em estoque: a lista já vem filtrada "
        "para touros convencionais/sexados com doses disponíveis, ou touros "
        "de monta natural da fazenda.",
    ]


def _norm(v) -> str:
    return (v or "").strip().lower()


def _ancestrais_paternos(vaca: dict) -> list[tuple[str, str]]:
    """[(rótulo, naab_ou_nome)] dos ascendentes paternos com dado disponível
    (prioriza NAAB; cai para nome quando o touro não tem NAAB cadastrado)."""
    ascendentes = [
        ("pai", vaca.get("pai_naab"), vaca.get("pai_nome")),
        ("avô paterno", vaca.get("avo_paterno_naab"), vaca.get("avo_paterno_nome")),
        ("bisavô paterno", vaca.get("bisavo_paterno_naab"), vaca.get("bisavo_paterno_nome")),
    ]
    out = []
    for rotulo, naab, nome in ascendentes:
        valor = naab or nome
        if valor:
            out.append((rotulo, valor))
    return out


def _bate_com_touro(touro: dict, valor: str) -> bool:
    valor_n = _norm(valor)
    if not valor_n:
        return False
    naab_t = _norm(touro.get("naab"))
    nome_t = _norm(touro.get("nome") or touro.get("nome_completo"))
    return valor_n == naab_t or (bool(nome_t) and valor_n == nome_t)


def _checar_consanguinidade(
    vaca: dict, touro: dict, ancestrais_maternos: list[str] | None,
) -> tuple[bool, str | None]:
    """Retorna (tem_ancestral_comum, rótulo_do_ascendente_que_bateu)."""
    for rotulo, valor in _ancestrais_paternos(vaca):
        if _bate_com_touro(touro, valor):
            return True, rotulo
    for valor in (ancestrais_maternos or []):
        if _bate_com_touro(touro, valor):
            return True, "ascendente materno"
    return False, None


def _score_complementaridade(vaca: dict, touro: dict) -> float:
    """Score simples e explicável: parte do TPI absoluto do touro (índice
    econômico geral), com NM$ como desempate leve. Quando a vaca tem
    produção recente conhecida (`ult_cl_kg`) e a média do lote é informada
    (`media_lote_kg`), reforça um pouco mais o PTA de leite do touro se a
    vaca estiver abaixo da média — para "compensar" o ponto fraco."""
    tpi = touro.get("tpi")
    score = float(tpi) if tpi is not None else 0.0
    nm = touro.get("nm_dolar")
    if nm is not None:
        score += float(nm) / 1000.0
    producao_vaca = vaca.get("ult_cl_kg")
    media_lote = vaca.get("media_lote_kg")
    leite_touro = touro.get("leite_kg")
    if producao_vaca is not None and media_lote and leite_touro is not None and producao_vaca < media_lote:
        score += float(leite_touro) * 0.05
    return score


def _motivo(vaca: dict, touro: dict, tem_consang: bool, rotulo_consang: str | None) -> str:
    partes: list[str] = []
    if tem_consang:
        partes.append(f"⚠️ Ancestral comum detectado ({rotulo_consang}) — evite este cruzamento.")
    else:
        linha = "linha paterna e materna" if vaca.get("_ancestrais_maternos_avaliados") else "linha paterna (3 gerações)"
        partes.append(f"Sem ancestral comum na {linha} registrada.")

    tpi = touro.get("tpi")
    if tpi is not None:
        partes.append(f"TPI {tpi:g}.")

    tipo = touro.get("tipo")
    doses = touro.get("doses")
    if tipo == "fazenda":
        partes.append("Touro de monta natural (fazenda), sempre disponível.")
    elif doses is not None:
        rotulo_tipo = _ROTULOS_DOSES.get(tipo, tipo or "")
        partes.append(f"{doses} dose(s) {rotulo_tipo} em estoque.".replace("  ", " "))

    return " ".join(partes)


def sugerir_touros(
    vaca: dict,
    touros_disponiveis: list[dict],
    ancestrais_maternos: list[str] | None = None,
    top_n: int = 5,
) -> list[dict]:
    """Ordena `touros_disponiveis` (já filtrados por estoque > 0 ou monta
    natural) para a vaca `vaca`, priorizando:
      1) evitar consanguinidade — penaliza fortemente touro com ancestral
         comum nas gerações conhecidas (paterna sempre, materna se
         `ancestrais_maternos` vier preenchida);
      2) complementar características — score por TPI/NM$/produção;
      3) estoque como leve desempate (mais doses primeiro, a igualdade de
         score).

    Cada item retornado inclui os campos originais do touro/estoque mais
    `score` e um `motivo` legível explicando o porquê daquela sugestão
    específica.
    """
    vaca = dict(vaca)
    vaca["_ancestrais_maternos_avaliados"] = bool(ancestrais_maternos)

    resultados = []
    for touro in touros_disponiveis:
        tem_consang, rotulo = _checar_consanguinidade(vaca, touro, ancestrais_maternos)
        score = _score_complementaridade(vaca, touro)
        if tem_consang:
            score -= PENALIDADE_CONSANGUINIDADE
        doses = touro.get("doses") or 0

        item = dict(touro)
        item["score"] = round(score, 3)
        item["tem_ancestral_comum"] = tem_consang
        item["motivo"] = _motivo(vaca, touro, tem_consang, rotulo)
        resultados.append((tem_consang, score, doses, item))

    # Consanguinidade é o critério de MAIOR prioridade (#1) — nenhum touro
    # com ancestral comum pode superar um sem ancestral comum, não importa
    # a diferença de TPI entre eles. Por isso o desempate é lexicográfico
    # (tem_consang primeiro), não uma subtração de score que um TPI alto
    # poderia superar.
    resultados.sort(key=lambda t: (t[0], -t[1], -t[2]))
    return [item for _, _, _, item in resultados[:top_n]]
