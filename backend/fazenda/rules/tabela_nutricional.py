"""
Tabela nutricional dos alimentos (referência do veterinário) — importada da
planilha TABELA_NUTRICIONAL_SILAGEM. Matriz nutriente x alimento; servida
pelo endpoint GET /alimentacao/tabela-nutricional para o modal + calculadora.
"""
from __future__ import annotations

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
