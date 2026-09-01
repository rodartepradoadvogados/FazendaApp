"""
Tabela nutricional dos alimentos (referência do veterinário) — importada da
planilha TABELA_NUTRICIONAL_SILAGEM. Matriz nutriente x alimento; servida
pelo endpoint GET /alimentacao/tabela-nutricional para o modal + calculadora.
"""
from __future__ import annotations

import re

ALIMENTOS = ["SILAGEM DE MILHO (60d)", "TECK MILK 24%", "MILK PROTEICO F. PREMIX", "CORTE 21", "BOVINOS PRÉ-PARTO", "BEZERRO 1"]

# Cada linha: [nutriente, valor_alim1, valor_alim2, ...] (string vazia = sem dado)
LINHAS = [
    ["Umidade", "66,76%", "125,00 g (Máx)", "125,00 g (Máx)", "125,00 g (Máx)", "125,00 g (Máx)", "125,00 g (Máx)"],
    ["Matéria Seca (MS)", "33,24%", "", "", "", "", ""],
    ["Proteína Bruta", "6,71% MS", "240,00 g (Mín)", "440,00 g (Mín)", "210,00 g (Mín)", "200,00 g (Mín)", "180,00 g (Mín)"],
    ["Proteína Solúvel", "65,16% PB", "", "", "", "", ""],
    ["Proteína Disponível", "6,39% MS", "", "", "", "", ""],
    ["PIDA", "0,32% MS", "", "", "", "", ""],
    ["PIDN", "0,90% MS", "", "", "", "", ""],
    ["Extrato Etéreo (Gordura)", "2,70% MS", "15,00 g (Mín)", "30,00 g (Mín)", "15,00 g (Mín)", "15,00 g (Mín)", "20,00 g (Mín)"],
    ["Matéria Fibrosa", "", "100,00 g (Máx)", "100,00 g (Máx)", "120,00 g (Máx)", "100,00 g (Máx)", "100,00 g (Máx)"],
    ["FDN (Fibra em Det. Neutro)", "44,50% MS", "", "", "", "", ""],
    ["FDNmo", "43,21% MS", "", "", "", "", ""],
    ["FDA (Fibra em Det. Ácido)", "27,02% MS", "100,00 g (Máx)", "240,00 g (Máx)", "150,00 g (Máx)", "120,00 g (Máx)", "100,00 g (Máx)"],
    ["Matéria Mineral / Cinzas", "4,50% MS", "100,00 g (Máx)", "120,00 g (Máx)", "100,00 g (Máx)", "100,00 g (Máx)", "120,00 g (Máx)"],
    ["NDT", "68,20% MS", "740,00 g (Mín)", "550,00 g (Mín)", "740,00 g (Mín)", "720,00 g (Mín)", "720,00 g (Mín)"],
    ["CNF (Carb. Não Fibrosos)", "42,49% MS", "", "", "", "", ""],
    ["Amido", "28,63% MS", "", "", "", "", ""],
    ["Lignina", "5,14% MS", "", "", "", "", ""],
    ["Cálcio (Mín)", "0,17% MS", "5.500,00 mg", "6.000,00 mg", "5.000,00 mg", "3.000,00 mg", "2.500,00 mg"],
    ["Cálcio (Máx)", "", "15,00 g", "12,00 g", "13,00 g", "20,00 g", "18,00 g"],
    ["Fósforo (Mín)", "0,19% MS", "3.500,00 mg", "5.500,00 mg", "3.500,00 mg", "3.500,00 mg", "4.500,00 mg"],
    ["Magnésio (Mín)", "0,12% MS", "1.970,00 mg", "2.100,00 mg", "1.000,00 mg", "2.000,00 mg", "2.000,00 mg"],
    ["Enxofre (Mín)", "0,07% MS", "3.320,00 mg", "6.000,00 mg", "3.300,00 mg", "4.000,00 mg", "2.500,00 mg"],
    ["Sódio (Mín)", "", "2.100,00 mg", "4.000,00 mg", "2.700,00 mg", "4.000,00 mg", "4.000,00 mg"],
    ["Potássio", "0,98% MS", "", "", "", "", ""],
    ["Cobalto (Mín)", "", "0,80 mg", "0,70 mg", "0,35 mg", "2,00 mg", "1,00 mg"],
    ["Cobre (Mín)", "", "18,00 mg", "20,00 mg", "17,00 mg", "33,00 mg", "15,00 mg"],
    ["Cromo (Mín)", "", "0,50 mg", "", "", "1,20 mg", "0,60 mg"],
    ["Ferro (Mín)", "", "80,00 mg", "", "", "40,00 mg", "Não informado"],
    ["Iodo (Mín)", "", "1,50 mg", "0,80 mg", "1,00 mg", "1,35 mg", "0,80 mg"],
    ["Manganês (Mín)", "", "55,00 mg", "48,00 mg", "40,00 mg", "130,00 mg", "Não informado"],
    ["Selênio (Mín)", "", "0,50 mg", "0,70 mg", "0,30 mg", "1,80 mg", "0,40 mg"],
    ["Zinco (Mín)", "", "100,00 mg", "100,00 mg", "100,00 mg", "230,00 mg", "100,00 mg"],
    ["Cloro (Mín)", "", "", "6.200,00 mg", "4.300,00 mg", "", ""],
    ["Vitamina A (Mín)", "", "13.300,00 UI", "9.000,00 UI", "8.800,00 UI", "30.000,00 UI", "14.000,00 UI"],
    ["Vitamina D3 (Mín)", "", "2.500,00 UI", "3.240,00 UI", "1.300,00 UI", "7.800,00 UI", "3.100,00 UI"],
    ["Vitamina E (Mín)", "", "25,00 UI", "400,00 UI", "5,00 UI", "70,05 UI", "30,00 UI"],
    ["Biotina (Mín)", "", "50,00 mg", "1,50 mg", "", "1,40 mg", "0,80 mg"],
    ["Colina (Mín)", "", "", "", "", "15,00 mg", "5.500,00 mg"],
    ["Mananos (Mín)", "", "", "300,00 mg", "", "90,00 mg", "300,00 mg"],
    ["Betaglucanos (Mín)", "", "", "300,00 mg", "", "90,00 mg", "300,00 mg"],
    ["Monensina (Mín)", "", "32,00 mg", "134,00 mg", "28,00 mg", "80,00 mg", "25,00 mg"],
    ["NNP Eq. Prot. (Máx)", "", "", "62,00 g", "80,00 g", "", ""],
    ["Lactose (Mín)", "", "", "", "", "", "2.000,00 mg"],
    ["Antioxidante (Mín)", "", "30,00 mg", "", "", "30,00 mg", ""],
    ["Saccharomyces cerevisiae", "", "400.000,00 ufc/g", "", "2.000.000,00 ufc/g", "1.500.000,00 ufc/g", ""],
    ["Ácido Láctico", "4,06% MS", "", "", "", "", ""],
    ["Ácido Acético", "3,56% MS", "", "", "", "", ""],
    ["Ácido Butírico", "0,00% MS", "", "", "", "", ""],
]


def tabela_nutricional() -> dict:
    return {"alimentos": ALIMENTOS, "linhas": LINHAS}


# ---------------------------------------------------------------------------
# Compor AlimentoNutricional (biblioteca de referência) a partir da Tabela
# Nutricional — pedido do usuário (01/09/2026): usar a composição já digitada
# por produto (texto livre, unidades mistas) em vez de deixar a importação de
# dieta cair sempre no template genérico da categoria.
#
# A tabela mistura DOIS jeitos de expressar composição, e cada um pede um
# tratamento diferente:
#   - Volumoso (ex.: silagem): já vem em "% da MS" — usa direto, sem conversão.
#   - Concentrado/mineral/premix comercial: vem como garantia de rótulo, em
#     massa por kg de PRODUTO (g ou mg/kg) — é preciso (a) converter pra
#     percentual do produto (÷10, já que 1kg = 1000g) e (b) reexpressar em
#     percentual da MS (÷ MS do produto/100), porque todo o motor de cálculo
#     (fazenda.rules.nutricao) trata os campos `_pct` como % da MS, salvo o
#     próprio `ms_pct`. A MS do produto raramente vem explícita no rótulo,
#     mas quase sempre dá pra derivar da linha "Umidade (Máx)" (MS ≈ 100% -
#     umidade) — é o mesmo raciocínio de qualquer boletim de garantia.
# Nutrientes em mg/UI/ufc (traço, vitaminas, aditivos) não têm campo tipado em
# AlimentoNutricional (ver docstring da classe) — ficam em `extras_json`,
# nunca descartados.
# ---------------------------------------------------------------------------

# nutriente da tabela -> campo de AlimentoNutricional (ver CAMPOS_NUTRICIONAIS
# em fazenda/rules/nutricao/tipos.py). Cálcio/Fósforo etc. têm variantes
# "(Mín)"/"(Máx)" como linhas SEPARADAS na tabela — o nome aqui já inclui o
# sufixo porque é assim que a linha chega; MAPA_FALLBACK cobre o caso de só
# existir a variante Máx.
MAPA_NUTRIENTE_PARA_CAMPO: dict[str, str] = {
    "Proteína Bruta": "pb_pct",
    "PIDA": "pida_pct",
    "PIDN": "pidn_pct",
    "Extrato Etéreo (Gordura)": "ee_pct",
    "FDN (Fibra em Det. Neutro)": "fdn_pct",
    "FDA (Fibra em Det. Ácido)": "fda_pct",
    "Matéria Mineral / Cinzas": "cinzas_pct",
    "Amido": "amido_pct",
    "Lignina": "lignina_pct",
    "Cálcio (Mín)": "ca_pct",
    "Fósforo (Mín)": "p_pct",
    "Magnésio (Mín)": "mg_pct",
    "Enxofre (Mín)": "s_pct",
    "Sódio (Mín)": "na_pct",
    "Cloro (Mín)": "cl_pct",
    "Potássio": "k_pct",
}
# Só usado se a variante "(Mín)" da mesma linha não existir nesta coluna.
MAPA_NUTRIENTE_FALLBACK: dict[str, str] = {
    "Cálcio (Máx)": "ca_pct",
    "Fósforo (Máx)": "p_pct",
    "Magnésio (Máx)": "mg_pct",
    "Enxofre (Máx)": "s_pct",
    "Sódio (Máx)": "na_pct",
    "Cloro (Máx)": "cl_pct",
}

_RE_VALOR = re.compile(r"^\s*([\d.]+,\d+|\d+)\s*(.*)$")


def parse_valor(texto: str) -> tuple[float, str] | None:
    """"5.500,00 mg" -> (5500.0, "mg"); "6,71% MS" -> (6.71, "% MS");
    "Não informado" ou vazio -> None (nada a extrair)."""
    texto = (texto or "").strip()
    if not texto:
        return None
    m = _RE_VALOR.match(texto)
    if not m:
        return None
    numero_str, unidade = m.group(1), m.group(2).strip()
    numero = float(numero_str.replace(".", "").replace(",", "."))
    return numero, unidade


def _pct_de_unidade_massa(numero: float, unidade: str) -> float | None:
    """Converte uma garantia "X g/kg de produto" ou "X mg/kg de produto" em
    percentual do PRODUTO (base como oferecido, ainda não é % da MS)."""
    u = unidade.lower()
    if u.startswith("mg"):
        return numero / 1000.0 / 10.0  # mg -> g, depois g/kg -> %
    if u.startswith("g"):
        return numero / 10.0
    return None


def compor_alimento_nutricional_de_tabela(nutriente_valores: dict[str, str]) -> tuple[dict[str, float], dict[str, str]]:
    """Recebe {nutriente: valor_bruto} de UM produto (uma coluna da tabela) e
    devolve (campos_convertidos, nao_convertidos) — o primeiro pronto pra
    gravar em AlimentoNutricional, o segundo guarda o texto original de cada
    nutriente que não tem campo tipado correspondente (destino: extras_json)."""
    convertidos: dict[str, float] = {}
    nao_convertidos: dict[str, str] = {}

    # 1) MS do produto — direto se a linha existir, senão derivado de Umidade
    # (MS ≈ 100% - umidade máxima admitida). Precisa vir ANTES do resto porque
    # os itens em massa/kg de produto dependem dela para virar % da MS.
    ms_pct: float | None = None
    bruto_ms = parse_valor(nutriente_valores.get("Matéria Seca (MS)", ""))
    if bruto_ms and "%" in bruto_ms[1]:
        ms_pct = bruto_ms[0]
    else:
        bruto_umidade = parse_valor(nutriente_valores.get("Umidade", ""))
        if bruto_umidade:
            numero, unidade = bruto_umidade
            umidade_pct = numero if "%" in unidade else _pct_de_unidade_massa(numero, unidade)
            if umidade_pct is not None:
                ms_pct = max(0.0, min(100.0, 100.0 - umidade_pct))
    if ms_pct is not None:
        convertidos["ms_pct"] = round(ms_pct, 2)

    # 2) Demais nutrientes mapeados — "(Mín)" tem prioridade sobre "(Máx)".
    for nutriente, valor_bruto in nutriente_valores.items():
        if nutriente in ("Matéria Seca (MS)", "Umidade"):
            continue
        campo = MAPA_NUTRIENTE_PARA_CAMPO.get(nutriente)
        eh_fallback_ja_coberto = False
        if campo is None:
            campo = MAPA_NUTRIENTE_FALLBACK.get(nutriente)
            if campo is not None:
                # só usa o "(Máx)" se a linha "(Mín)" correspondente estiver
                # vazia/ausente nesta mesma coluna — "(Mín)" já processado
                # no laço não garante ordem, então checa direto o valor bruto.
                nome_min = nutriente.replace("(Máx)", "(Mín)")
                eh_fallback_ja_coberto = bool(parse_valor(nutriente_valores.get(nome_min, "")))
        if campo is None:
            if valor_bruto and valor_bruto.strip() and valor_bruto.strip().lower() != "não informado":
                nao_convertidos[nutriente] = valor_bruto
            continue
        if eh_fallback_ja_coberto:
            continue  # a variante "(Mín)" já preencheu este campo

        bruto = parse_valor(valor_bruto)
        if not bruto:
            continue
        numero, unidade = bruto
        u = unidade.lower()
        if "%" in u:
            # já é percentual — "% MS"/"% da MS" é direto; "% PB" (ex.:
            # Proteína Solúvel) não tem campo tipado, mas isso já não chega
            # aqui porque só nutrientes MAPEADOS entram neste ramo, e nenhum
            # deles usa base "% PB".
            convertidos[campo] = round(numero, 2)
        elif u.startswith("g") or u.startswith("mg"):
            pct_produto = _pct_de_unidade_massa(numero, unidade)
            if pct_produto is None:
                continue
            if ms_pct and ms_pct > 0:
                convertidos[campo] = round(pct_produto / (ms_pct / 100.0), 2)
            else:
                # Sem MS conhecida do produto — melhor aproximação disponível
                # é assumir garantia≈%MS (erro típico de poucos pontos
                # percentuais pra produto seco); documentado em `fonte`.
                convertidos[campo] = round(pct_produto, 2)
        else:
            nao_convertidos[nutriente] = valor_bruto

    return convertidos, nao_convertidos
