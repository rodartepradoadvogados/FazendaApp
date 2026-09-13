"""
Copia os campos de "identidade CowData" de um MedicamentoComercial padrão
para um item de Estoque do tenant — o mesmo bloco de campos que 3 pontos do
sistema precisam preencher, de formas ligeiramente diferentes:

1. Fan-out em massa (toda fazenda-cliente, item novo) — painel_cowdata_
   farmacia.py::_fan_out_medicamento.
2. Ativação avulsa numa única fazenda (Diagnóstico > "Ausente") — mesmo
   código do item 1, só que pra 1 fazenda em vez de todas.
3. Vincular um item ÓRFÃO ao catálogo central (Diagnóstico > "Órfão") ou
   "restaurar padrão" de um item já vinculado — o item já existe e mantém
   nome/ativo/estocavel/quantidade/valor/histórico; só a identidade muda.

Consolidado aqui pra não haver cópias divergentes do mesmo bloco de campos —
foi exatamente uma divergência dessas que fez o fan-out gravar "Medicamentos"
no campo errado até a correção de 01/09/2026 (commit ab33a60), enquanto uma
2ª cópia do mesmo bug sobrevivia intacta em restaurar_padrao_cowdata
(api/routers/estoque.py) até este módulo existir.
"""
from __future__ import annotations

from sqlmodel import Session

from fazenda.models import (
    Estoque, EstoqueCategoriaMedicamento, EstoqueClassificacaoMedicamento,
    MedicamentoCategoria, MedicamentoClassificacao, MedicamentoComercial, PrincipioAtivo,
)
from fazenda.rules.farmacia_multi_principio import definir_principios_estoque, principios_do_medicamento
from fazenda.rules.farmacia_tags import definir_tags, tags_de


def aplicar_identidade_padrao(
    session: Session, item: Estoque, medicamento: MedicamentoComercial, *, renomear: bool,
) -> None:
    """Grava em `item` a identidade do medicamento padrão: finalidade,
    categoria (sempre "Medicamentos") + classificação médica (escalar E tags
    cumulativas), princípio(s) ativo(s), laboratório, carência/lactação.
    NUNCA toca ativo/estocavel/quantidade/valor/histórico.

    `renomear=True` só faz sentido pra um item que JÁ representa fisicamente
    este medicamento (fan-out de item novo, ou "restaurar padrão" de um item
    já vinculado) — um item órfão sendo vinculado pela 1ª vez mantém o nome
    que a fazenda escolheu, mesmo que difira do nome comercial central.
    """
    principio_ids = principios_do_medicamento(session, medicamento.id)
    principal = session.get(PrincipioAtivo, principio_ids[0]) if principio_ids else None
    categoria_ids = tags_de(session, MedicamentoCategoria, "medicamento_comercial_id", medicamento.id, "categoria_medicamento_id")
    classificacao_ids = tags_de(session, MedicamentoClassificacao, "medicamento_comercial_id", medicamento.id, "classificacao_medicamento_id")

    if renomear:
        item.nome = medicamento.nome_comercial
    item.finalidade = "Medicamento"
    item.categoria = "Medicamentos"
    item.classificacao_medicamento = medicamento.classificacao_medicamento
    item.laboratorio = medicamento.laboratorio
    item.carencia_dias = medicamento.carencia_leite_dias
    item.carencia_leite_dias = medicamento.carencia_leite_dias
    item.carencia_carne_dias = medicamento.carencia_carne_dias
    item.proibido_lactacao = medicamento.proibido_lactacao
    item.medicamento_comercial_id = medicamento.id
    if principio_ids:
        item.principio_ativo_id = principio_ids[0]
        item.principio_ativo = principal.nome if principal else None
    session.add(item)
    session.flush()  # garante item.id (item novo do fan-out ainda não tem PK)

    if principio_ids:
        definir_principios_estoque(session, item, principio_ids)
    definir_tags(
        session, EstoqueCategoriaMedicamento, "estoque_id", item.id, "categoria_medicamento_id",
        categoria_ids, fazenda_id=item.fazenda_id,
    )
    definir_tags(
        session, EstoqueClassificacaoMedicamento, "estoque_id", item.id, "classificacao_medicamento_id",
        classificacao_ids, fazenda_id=item.fazenda_id,
    )
