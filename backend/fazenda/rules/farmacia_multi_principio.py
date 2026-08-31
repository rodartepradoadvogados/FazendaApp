"""
Multi-princípio ativo por medicamento/item de estoque — generaliza o vínculo
escalar `MedicamentoComercial.principio_ativo_id`/`Estoque.principio_ativo_id`
(hoje só 1) para N princípios, via as tabelas de junção
`MedicamentoPrincipioAtivo`/`EstoquePrincipioAtivo` (ver models/sanidade.py e
models/estoque.py). Pedido do usuário (31/08/2026): "precisa poder
acrescentar mais de um princípio ativo ao medicamento, tanto no painel
CowData como nos tenants, pois hoje só pode 1".

Regra de ouro: a coluna escalar NUNCA é removida — ela é o "princípio
principal", sempre igual à linha `principal=True` da tabela de junção. Todo
código pré-existente que só lê o escalar continua funcionando sem mudança;
só quem precisa saber de TODOS os princípios (filtros de doença/secagem/
vacina em routers/estoque.py e rules/estoque_baixa.py) passa a consultar
também a junção.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlmodel import Session, select

from fazenda.models import (
    CalendarioSanitario,
    Estoque,
    EstoquePrincipioAtivo,
    ExameDefinicao,
    IndicacaoTerapeutica,
    MedicamentoComercial,
    MedicamentoPrincipioAtivo,
    PrincipioAtivo,
    ProtocoloIatfEtapa,
    ProtocoloInducaoLactacaoEtapa,
)


def principios_do_medicamento(session: Session, medicamento_comercial_id: int) -> list[int]:
    """Ids de todos os princípios ativos ligados a um medicamento — o
    principal primeiro (mesma ordem que MedicamentoComercial.principio_ativo_id
    sempre respeita)."""
    vinculos = session.exec(
        select(MedicamentoPrincipioAtivo)
        .where(MedicamentoPrincipioAtivo.medicamento_comercial_id == medicamento_comercial_id)
        .order_by(MedicamentoPrincipioAtivo.principal.desc(), MedicamentoPrincipioAtivo.id)
    ).all()
    return [v.principio_ativo_id for v in vinculos]


def principios_do_estoque(session: Session, estoque_id: int) -> list[int]:
    vinculos = session.exec(
        select(EstoquePrincipioAtivo)
        .where(EstoquePrincipioAtivo.estoque_id == estoque_id)
        .order_by(EstoquePrincipioAtivo.principal.desc(), EstoquePrincipioAtivo.id)
    ).all()
    return [v.principio_ativo_id for v in vinculos]


def definir_principios_medicamento(
    session: Session, medicamento: MedicamentoComercial, principio_ids: list[int], fazenda_id: int | None,
) -> None:
    """Substitui os princípios ligados a um medicamento pela lista informada
    — o primeiro da lista vira o principal (espelhado em
    `MedicamentoComercial.principio_ativo_id`, lido por ~15 pontos do sistema
    que ainda não sabem de multi-princípio). Nunca deixa a lista vazia — todo
    medicamento precisa de pelo menos 1 princípio."""
    ids_unicos = list(dict.fromkeys(principio_ids))  # remove duplicata mantendo ordem
    if not ids_unicos:
        raise HTTPException(status_code=400, detail="Selecione ao menos um princípio ativo")

    existentes = session.exec(
        select(MedicamentoPrincipioAtivo).where(MedicamentoPrincipioAtivo.medicamento_comercial_id == medicamento.id)
    ).all()
    existentes_por_pa = {v.principio_ativo_id: v for v in existentes}

    for pa_id in ids_unicos:
        v = existentes_por_pa.pop(pa_id, None)
        if v is None:
            v = MedicamentoPrincipioAtivo(
                medicamento_comercial_id=medicamento.id, principio_ativo_id=pa_id,
                principal=(pa_id == ids_unicos[0]), fazenda_id=fazenda_id,
            )
        else:
            v.principal = (pa_id == ids_unicos[0])
        session.add(v)
    for sobra in existentes_por_pa.values():
        session.delete(sobra)

    medicamento.principio_ativo_id = ids_unicos[0]
    session.add(medicamento)


def definir_principios_estoque(session: Session, item: Estoque, principio_ids: list[int]) -> None:
    """Mesma lógica de `definir_principios_medicamento`, para item de Estoque
    do tenant. Lista vazia é permitida aqui (item de estoque não-medicamento,
    ou medicamento em texto livre sem princípio cadastrado ainda)."""
    ids_unicos = list(dict.fromkeys(principio_ids))

    existentes = session.exec(
        select(EstoquePrincipioAtivo).where(EstoquePrincipioAtivo.estoque_id == item.id)
    ).all()
    existentes_por_pa = {v.principio_ativo_id: v for v in existentes}

    for pa_id in ids_unicos:
        v = existentes_por_pa.pop(pa_id, None)
        if v is None:
            v = EstoquePrincipioAtivo(estoque_id=item.id, principio_ativo_id=pa_id, principal=(pa_id == ids_unicos[0]))
        else:
            v.principal = (pa_id == ids_unicos[0])
        session.add(v)
    for sobra in existentes_por_pa.values():
        session.delete(sobra)

    item.principio_ativo_id = ids_unicos[0] if ids_unicos else None


def checar_e_desvincular_exclusao_principio(
    session: Session, pa: PrincipioAtivo,
) -> tuple[list[str], list]:
    """Prevê o impacto de excluir um Princípio Ativo e desfaz os vínculos
    opcionais — usada tanto por `POST /exclusoes/impacto` (tipo=
    "principio_ativo") quanto por `DELETE /farmacia/principios/{id}`, pra não
    duplicar a regra em dois lugares.

    BLOQUEIA (400) se algum Medicamento (marca comercial) ainda usa este
    princípio — `MedicamentoComercial.principio_ativo_id` é obrigatório, não
    dá pra simplesmente desvincular. As demais referências são opcionais/de
    catálogo e são desfeitas (calendário, exame, indução, IATF, item de
    estoque) ou removidas por serem puro vínculo (indicação terapêutica,
    junção de estoque).

    Retorna (descrições de impacto, objetos a excluir) — quem chama ainda
    precisa `session.delete()` cada objeto retornado e `session.commit()`.
    """
    medicamentos_diretos = session.exec(
        select(MedicamentoComercial).where(MedicamentoComercial.principio_ativo_id == pa.id)
    ).all()
    medicamentos_via_junction = session.exec(
        select(MedicamentoComercial)
        .join(MedicamentoPrincipioAtivo, MedicamentoPrincipioAtivo.medicamento_comercial_id == MedicamentoComercial.id)
        .where(MedicamentoPrincipioAtivo.principio_ativo_id == pa.id)
    ).all()
    medicamentos = {m.id: m for m in [*medicamentos_diretos, *medicamentos_via_junction]}.values()
    if medicamentos:
        nomes = ", ".join(sorted({m.nome_comercial for m in medicamentos})[:5])
        raise HTTPException(
            status_code=400,
            detail=f"Não é possível excluir '{pa.nome}': {len(medicamentos)} medicamento(s) usam este "
                   f"princípio ({nomes}). Edite ou exclua o(s) medicamento(s) primeiro.",
        )

    impacto = [f"Princípio ativo {pa.nome}"]
    vinculados_calendario = session.exec(select(CalendarioSanitario).where(CalendarioSanitario.principio_ativo_id == pa.id)).all()
    vinculados_exame = session.exec(select(ExameDefinicao).where(ExameDefinicao.principio_ativo_id == pa.id)).all()
    vinculados_inducao = session.exec(select(ProtocoloInducaoLactacaoEtapa).where(ProtocoloInducaoLactacaoEtapa.principio_ativo_id == pa.id)).all()
    vinculados_iatf = session.exec(select(ProtocoloIatfEtapa).where(ProtocoloIatfEtapa.principio_ativo_id == pa.id)).all()
    indicacoes = session.exec(select(IndicacaoTerapeutica).where(IndicacaoTerapeutica.principio_ativo_id == pa.id)).all()
    itens_estoque = session.exec(select(Estoque).where(Estoque.principio_ativo_id == pa.id)).all()
    vinculos_estoque_junction = session.exec(select(EstoquePrincipioAtivo).where(EstoquePrincipioAtivo.principio_ativo_id == pa.id)).all()

    if vinculados_calendario:
        impacto.append(f"{len(vinculados_calendario)} regra(s) do calendário sanitário perderão esse vínculo")
        for regra in vinculados_calendario:
            regra.principio_ativo_id = None
            session.add(regra)
    if vinculados_exame:
        impacto.append(f"{len(vinculados_exame)} definição(ões) de exame perderão esse vínculo")
        for exame in vinculados_exame:
            exame.principio_ativo_id = None
            session.add(exame)
    if vinculados_inducao:
        impacto.append(f"{len(vinculados_inducao)} etapa(s) de indução de lactação perderão esse vínculo")
        for etapa in vinculados_inducao:
            etapa.principio_ativo_id = None
            session.add(etapa)
    if vinculados_iatf:
        impacto.append(f"{len(vinculados_iatf)} etapa(s) de protocolo IATF perderão esse vínculo")
        for etapa in vinculados_iatf:
            etapa.principio_ativo_id = None
            session.add(etapa)
    if indicacoes:
        impacto.append(f"{len(indicacoes)} indicação(ões) terapêutica(s) serão removidas")
    if itens_estoque:
        impacto.append(f"{len(itens_estoque)} item(ns) de estoque perderão esse vínculo (o texto do princípio é mantido)")
        for item in itens_estoque:
            item.principio_ativo_id = None
            session.add(item)

    return impacto, [pa, *indicacoes, *vinculos_estoque_junction]
