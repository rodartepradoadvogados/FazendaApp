"""
Categorias fixas usadas em cadastros da fazenda — mantidas em um só lugar para
o backend validar e o frontend popular os seletores com a mesma lista.
"""
from __future__ import annotations

# Categorias de fornecedor — cobrem os tipos de fornecedor que já aparecem nas
# planilhas importadas (ração/insumos, sêmen, veterinário, manutenção...).
CATEGORIAS_FORNECEDOR = [
    "Ração e insumos alimentares",
    "Sêmen e genética",
    "Medicamentos e produtos veterinários",
    "Equipamentos e manutenção",
    "Combustível e transporte",
    "Serviços veterinários/técnicos",
    "Energia e utilidades",
    "Embalagens e materiais",
    "Outros",
]

# Finalidade de um item de ESTOQUE (Estoque.finalidade) — decide se ele pode
# aparecer nos seletores de "aplicação de medicamento"/hormônio. "Medicamento"
# cobre remédio, hormônio e vacina (a subclasse terapêutica continua vindo de
# `classificacao_medicamento`); os demais valores existem só para EXCLUIR
# ração/material/equipamento desses seletores. Sêmen não usa este campo — vive
# em EstoqueSemen, uma tabela própria.
FINALIDADES_ESTOQUE = [
    "Medicamento",
    "Ração/Alimento",
    "Material/Insumo",
    "Equipamento",
    "Outro",
]
