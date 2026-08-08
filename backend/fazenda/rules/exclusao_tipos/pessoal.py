"""
Tipos de exclusão do domínio de Pessoal/RH — G3 (`diaria_pagamento`), G9
(`empreitada`), G10 (`contrato`), G14 (`diaria`). G15 (parcela de vale) usa
endpoint próprio (`DELETE /cadastro/vales/{vale_id}/parcelas/{parcela_id}`
em rh_folha.py), não este registro.

`_reverter_vale_avulso`/`_numeros_pagos` (rh_contratos.py) são importados
LOCALMENTE dentro de cada `alvos`, nunca no topo do módulo — este pacote é
importado por `exclusoes.py` (via `rules/exclusao_tipos/__init__.py`) antes
de qualquer coisa que dependa dele, e um import de nível de módulo aqui
apontando para `api.routers.cadastro.rh_contratos` funcionaria na maioria das
ordens de carregamento, mas o padrão já estabelecido em
`exclusoes.py::_desvincular_vales_dos_alvos` é justamente evitar depender
dessa ordem — replicado aqui pela mesma razão.
"""
from __future__ import annotations

from sqlmodel import select
from fastapi import HTTPException

from fazenda.models import (
    AgendaManual,
    Contrato,
    ContratoParcela,
    ContaGerencial,
    Diaria,
    DiariaAuditoria,
    DiariaDia,
    DiariaPagamento,
    Empreitada,
    EmpreitadaEtapa,
    EmpreitadaParcela,
    Pessoa,
    ValeAvulso,
)
from fazenda.rules.exclusao_tipos._base import TipoExclusao, _br, _contem, _dentro_periodo


# ---------------------------------------------------------------------------
# G3 — diaria_pagamento
# ---------------------------------------------------------------------------
def _buscar_diaria_pagamento(termo, data_inicio, data_fim, session, fazenda_id=None) -> list[dict]:
    query = select(DiariaPagamento)
    if fazenda_id is not None:
        query = query.where(DiariaPagamento.fazenda_id == fazenda_id)
    rows = session.exec(query).all()
    diarias = {d.id: d for d in session.exec(select(Diaria)).all()}
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    out = []
    for pg in rows:
        diaria = diarias.get(pg.diaria_id)
        nome = pessoas.get(diaria.pessoa_id, "—") if diaria else "—"
        if not _contem(termo, nome, pg.observacao):
            continue
        if not _dentro_periodo(pg.data_pagamento, data_inicio, data_fim):
            continue
        out.append({
            "id": pg.id,
            "titulo": f"Pagamento de diária — {nome} — {_br(pg.data_pagamento)}",
            "subtitulo": f"R$ {pg.valor:,.2f}" + (f" · {pg.observacao}" if pg.observacao else ""),
            "_data": pg.data_pagamento,
        })
    return sorted(out, key=lambda x: x["titulo"], reverse=True)[:200]


def _alvos_diaria_pagamento(id_, session, fazenda_id=None) -> tuple[list[str], list]:
    pagamento = session.get(DiariaPagamento, int(id_))
    if not pagamento or (fazenda_id is not None and pagamento.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pagamento de diária não encontrado")
    diaria = session.get(Diaria, pagamento.diaria_id)
    pessoa = session.get(Pessoa, diaria.pessoa_id) if diaria else None
    nome = pessoa.nome if pessoa else "—"

    impacto = [f"Pagamento de R$ {pagamento.valor:,.2f} da diária de {nome} em {_br(pagamento.data_pagamento)}"]
    objetos: list = [pagamento]

    if pagamento.numero_lancamento_gerado:
        conta = session.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == pagamento.numero_lancamento_gerado)
        ).first()
        if conta:
            impacto.append(f"Lançamento financeiro {conta.numero_lancamento} (baixado) também será excluído")
            objetos.append(conta)

    if diaria:
        # O saldo devedor não é armazenado (ver _resumo_diaria em
        # rh_contratos.py) — recalculado aqui só para informar o impacto,
        # sem nenhuma mutação: apagar o DiariaPagamento já corrige o saldo
        # sozinho na próxima leitura, nada a reverter manualmente.
        from fazenda.api.routers.cadastro.rh_contratos import _resumo_diaria

        resumo = _resumo_diaria(session, diaria, nome)
        saldo_antes = resumo["saldo_devedor"]
        saldo_depois = round(saldo_antes + pagamento.valor, 2)
        impacto.append(f"Saldo devedor da diária volta de R$ {saldo_antes:,.2f} para R$ {saldo_depois:,.2f}")

    return impacto, objetos


# ---------------------------------------------------------------------------
# G9 — empreitada (cabeçalho)
# ---------------------------------------------------------------------------
def _buscar_empreitada(termo, data_inicio, data_fim, session, fazenda_id=None) -> list[dict]:
    query = select(Empreitada)
    if fazenda_id is not None:
        query = query.where(Empreitada.fazenda_id == fazenda_id)
    rows = session.exec(query).all()
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    out = []
    for e in rows:
        nome = pessoas.get(e.pessoa_id, "—")
        if not _contem(termo, e.descricao, nome, e.observacao):
            continue
        out.append({
            "id": e.id,
            "titulo": f"{nome} — {e.descricao}",
            "subtitulo": f"R$ {e.valor_total:,.2f} · {e.tipo_pagamento} · {e.status}",
        })
    return sorted(out, key=lambda x: x["titulo"])[:200]


def _alvos_empreitada(id_, session, fazenda_id=None) -> tuple[list[str], list]:
    # Import local (não no topo do módulo) — mesmo motivo do comentário no
    # topo do arquivo e de `_desvincular_vales_dos_alvos` em exclusoes.py.
    from fazenda.api.routers.cadastro.rh_contratos import _numeros_pagos, _reverter_vale_avulso
    from fazenda.rules.vale_item import limpar_vinculo_de_itens

    empreitada = session.get(Empreitada, int(id_))
    if not empreitada or (fazenda_id is not None and empreitada.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Empreitada não encontrada")
    pessoa = session.get(Pessoa, empreitada.pessoa_id)
    nome = pessoa.nome if pessoa else "—"

    parcelas = session.exec(select(EmpreitadaParcela).where(EmpreitadaParcela.empreitada_id == empreitada.id)).all()
    etapas = session.exec(select(EmpreitadaEtapa).where(EmpreitadaEtapa.empreitada_id == empreitada.id)).all()
    numeros = [n for n in [p.numero_lancamento_gerado for p in parcelas] + [et.numero_lancamento_gerado for et in etapas] if n]

    # 1. Bloqueia se qualquer parcela/etapa já foi paga — não reverte
    # pagamento automaticamente (o dinheiro já saiu do banco).
    pagos = _numeros_pagos(session, numeros)
    if pagos:
        raise HTTPException(
            status_code=400,
            detail=f"Não é possível excluir esta empreita: {len(pagos)} parcela(s)/etapa(s) já foi(ram) paga(s). "
                   "Estorne a baixa em Financeiro › Contas pagas e depois exclua.",
        )

    contas = session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros))).all() if numeros else []

    # 2. Reverte os vales avulsos antes de apagar as parcelas — sem isso
    # sobraria ValeAvulsoAbatimento órfão.
    vales = session.exec(
        select(ValeAvulso).where(ValeAvulso.origem_tipo == "empreitada", ValeAvulso.origem_id == empreitada.id)
    ).all()
    contas_vale: list = []
    for vale in vales:
        _reverter_vale_avulso(session, vale.id)
        limpar_vinculo_de_itens(session, vale_avulso_id=vale.id)
        if vale.numero_lancamento_gerado:
            conta_vale = session.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == vale.numero_lancamento_gerado)
            ).first()
            if conta_vale:
                contas_vale.append(conta_vale)

    impacto = [f"Empreita de {nome} — {empreitada.descricao} (R$ {empreitada.valor_total:,.2f})"]
    impacto.append(f"{len(parcelas)} parcela(s) e {len(etapas)} etapa(s)")
    if contas:
        impacto.append(f"{len(contas)} conta(s) a pagar em aberto serão excluídas")
    if vales:
        impacto.append(f"{len(vales)} vale(s) avulso(s) serão revertidos e excluídos")

    # 3. Os ValeAvulsoAbatimento já foram apagados por _reverter_vale_avulso.
    objetos = [empreitada, *parcelas, *etapas, *contas, *vales, *contas_vale]
    return impacto, objetos


# ---------------------------------------------------------------------------
# G10 — contrato
# ---------------------------------------------------------------------------
def _buscar_contrato(termo, data_inicio, data_fim, session, fazenda_id=None) -> list[dict]:
    query = select(Contrato)
    if fazenda_id is not None:
        query = query.where(Contrato.fazenda_id == fazenda_id)
    rows = session.exec(query).all()
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    out = []
    for c in rows:
        nome = pessoas.get(c.pessoa_id, "—")
        if not _contem(termo, c.descricao, nome, c.observacao):
            continue
        out.append({
            "id": c.id,
            "titulo": f"{nome} — {c.descricao}",
            "subtitulo": f"R$ {c.valor_total:,.2f} · {c.forma_pagamento or 'sem frequência'} · {c.status}",
        })
    return sorted(out, key=lambda x: x["titulo"])[:200]


def _alvos_contrato(id_, session, fazenda_id=None) -> tuple[list[str], list]:
    from fazenda.api.routers.cadastro.rh_contratos import _numeros_pagos, _reverter_vale_avulso
    from fazenda.rules.vale_item import limpar_vinculo_de_itens

    contrato = session.get(Contrato, int(id_))
    if not contrato or (fazenda_id is not None and contrato.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    pessoa = session.get(Pessoa, contrato.pessoa_id)
    nome = pessoa.nome if pessoa else "—"

    parcelas = session.exec(select(ContratoParcela).where(ContratoParcela.contrato_id == contrato.id)).all()
    numeros = [p.numero_lancamento_gerado for p in parcelas if p.numero_lancamento_gerado]

    # Bloqueio idêntico ao da empreitada: parcela paga → 400 apontando o estorno.
    pagos = _numeros_pagos(session, numeros)
    if pagos:
        raise HTTPException(
            status_code=400,
            detail=f"Não é possível excluir este contrato: {len(pagos)} parcela(s) já foi(ram) paga(s). "
                   "Estorne a baixa em Financeiro › Contas pagas e depois exclua.",
        )

    contas = session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros))).all() if numeros else []

    vales = session.exec(
        select(ValeAvulso).where(ValeAvulso.origem_tipo == "contrato", ValeAvulso.origem_id == contrato.id)
    ).all()
    contas_vale: list = []
    for vale in vales:
        _reverter_vale_avulso(session, vale.id)
        limpar_vinculo_de_itens(session, vale_avulso_id=vale.id)
        if vale.numero_lancamento_gerado:
            conta_vale = session.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == vale.numero_lancamento_gerado)
            ).first()
            if conta_vale:
                contas_vale.append(conta_vale)

    # Extra do contrato: o lembrete mensal de Agenda (criado quando
    # forma_pagamento é None) — e as ocorrências já materializadas dele
    # (ver _gerar_agenda_recorrente em agenda.py), senão o lembrete
    # continua nascendo pra sempre / sobram filhos órfãos.
    lembrete = session.get(AgendaManual, contrato.origem_lembrete_agenda_id) if contrato.origem_lembrete_agenda_id else None
    filhos_lembrete: list = []
    if lembrete:
        filhos_lembrete = session.exec(
            select(AgendaManual).where(AgendaManual.origem_recorrencia_id == lembrete.id)
        ).all()

    impacto = [f"Contrato de {nome} — {contrato.descricao} (R$ {contrato.valor_total:,.2f})"]
    if parcelas:
        impacto.append(f"{len(parcelas)} parcela(s)")
    if contas:
        impacto.append(f"{len(contas)} conta(s) a pagar em aberto serão excluídas")
    if vales:
        impacto.append(f"{len(vales)} vale(s) avulso(s) serão revertidos e excluídos")
    if lembrete:
        impacto.append(f'O lembrete mensal "{contrato.descricao}" na Agenda também será excluído')

    objetos = [contrato, *parcelas, *contas, *vales, *contas_vale]
    if lembrete:
        objetos.append(lembrete)
    objetos += filhos_lembrete
    return impacto, objetos


# ---------------------------------------------------------------------------
# G14 — diaria (cabeçalho)
# ---------------------------------------------------------------------------
def _buscar_diaria(termo, data_inicio, data_fim, session, fazenda_id=None) -> list[dict]:
    query = select(Diaria)
    if fazenda_id is not None:
        query = query.where(Diaria.fazenda_id == fazenda_id)
    rows = session.exec(query).all()
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    out = []
    for d in rows:
        nome = pessoas.get(d.pessoa_id, "—")
        if not _contem(termo, nome, d.observacao):
            continue
        if not _dentro_periodo(d.data_inicio, data_inicio, data_fim):
            continue
        # Reutiliza o cálculo já existente de saldo/nº de diárias — sem
        # duplicar a lógica de contagem de dias.
        from fazenda.api.routers.cadastro.rh_contratos import _resumo_diaria

        resumo = _resumo_diaria(session, d, nome)
        out.append({
            "id": d.id,
            "titulo": f"Diária de {nome} — R$ {d.valor_diaria:,.2f}/dia desde {_br(d.data_inicio)}",
            "subtitulo": f"{resumo['numero_diarias']} diária(s) · saldo R$ {resumo['saldo_devedor']:,.2f}",
            "_data": d.data_inicio,
        })
    return sorted(out, key=lambda x: x["titulo"], reverse=True)[:200]


def _alvos_diaria(id_, session, fazenda_id=None) -> tuple[list[str], list]:
    from fazenda.rules.vale_item import limpar_vinculo_de_itens

    diaria = session.get(Diaria, int(id_))
    if not diaria or (fazenda_id is not None and diaria.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Diária não encontrada")
    pessoa = session.get(Pessoa, diaria.pessoa_id)
    nome = pessoa.nome if pessoa else "—"

    # Decisão de produto: diária com pagamento já registrado é bloqueada —
    # o botão de excluir pagamento (G3) é a saída.
    pagamentos = session.exec(select(DiariaPagamento).where(DiariaPagamento.diaria_id == diaria.id)).all()
    if pagamentos:
        total_pago = round(sum(p.valor for p in pagamentos), 2)
        raise HTTPException(
            status_code=400,
            detail=f"Não é possível excluir esta diária: há {len(pagamentos)} pagamento(s) registrado(s) "
                   f"(R$ {total_pago:,.2f}). Exclua os pagamentos primeiro (Pessoal › Diárias, botão de excluir pagamento).",
        )

    vales = session.exec(
        select(ValeAvulso).where(ValeAvulso.origem_tipo == "diaria", ValeAvulso.origem_id == diaria.id)
    ).all()
    vales_com_saida = [v for v in vales if v.forma_pagamento != "desconto_proximo_pagamento"]
    if vales_com_saida:
        total_vale = round(sum(v.valor for v in vales_com_saida), 2)
        raise HTTPException(
            status_code=400,
            detail=f"Não é possível excluir esta diária: há {len(vales_com_saida)} vale(s) avulso(s) com saída de "
                   f"caixa já pago(s) (R$ {total_vale:,.2f}). Veja o Relatório de vales avulsos antes de excluir.",
        )

    auditorias = session.exec(select(DiariaAuditoria).where(DiariaAuditoria.diaria_id == diaria.id)).all()
    dias_calendario = session.exec(select(DiariaDia).where(DiariaDia.diaria_id == diaria.id)).all()

    impacto = [f"Diária de {nome} — R$ {diaria.valor_diaria:,.2f}/dia desde {_br(diaria.data_inicio)}"]
    if auditorias:
        impacto.append(f"{len(auditorias)} auditoria(s) de dias trabalhados")
    if dias_calendario:
        impacto.append(f"{len(dias_calendario)} dia(s) marcado(s) no calendário de dias trabalhados")
    if vales:
        impacto.append(f"{len(vales)} vale(s) avulso(s)")

    # Sem pagamento e sem vale de saída de caixa: excluir livremente,
    # levando auditorias, dias do calendário e vale(s) de desconto (sem
    # ValeAvulsoAbatimento — _aplicar_vale_avulso retorna cedo para "diaria")
    # junto.
    objetos: list = [diaria, *auditorias, *dias_calendario]
    for vale in vales:
        limpar_vinculo_de_itens(session, vale_avulso_id=vale.id)
        objetos.append(vale)
        if vale.numero_lancamento_gerado:
            conta_vale = session.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == vale.numero_lancamento_gerado)
            ).first()
            if conta_vale:
                objetos.append(conta_vale)
    return impacto, objetos


TIPOS_EXCLUSAO: list[TipoExclusao] = [
    TipoExclusao(
        id="diaria_pagamento", label="Pagamento de diária",
        buscar=_buscar_diaria_pagamento, alvos=_alvos_diaria_pagamento, sem_filtro_data=False,
    ),
    TipoExclusao(
        id="empreitada", label="Empreitada",
        buscar=_buscar_empreitada, alvos=_alvos_empreitada, sem_filtro_data=True,
    ),
    TipoExclusao(
        id="contrato", label="Contrato (Pessoal)",
        buscar=_buscar_contrato, alvos=_alvos_contrato, sem_filtro_data=True,
    ),
    TipoExclusao(
        id="diaria", label="Diária",
        buscar=_buscar_diaria, alvos=_alvos_diaria, sem_filtro_data=False,
    ),
]
