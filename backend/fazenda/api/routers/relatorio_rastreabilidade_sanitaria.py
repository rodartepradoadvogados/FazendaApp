"""
Relatório de rastreabilidade sanitária (Sanidade > Rastreabilidade) — a
resposta completa para "esse animal (ou esse GTA) teve qual histórico
sanitário?": reúne, numa única linha do tempo por animal, os GTAs de compra/
venda, as aplicações sanitárias (vacina/vermífugo/curativo), os protocolos
sanitários lançados, os resultados de exame (tuberculose, brucelose etc.) e as
doenças/ocorrências clínicas registradas — filtrável por número do animal,
período (de/até) ou número de GTA.

Não emite GTA (documento oficial emitido pelo órgão estadual) — só registra e
consulta o que a fazenda já lançou nas telas de Compra/Venda de animal.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import (
    Animal, BaixaAnimal, CompraAnimal, Estoque, EventoSanitario, ExameResultado, MedicamentoComercial,
    OcorrenciaClinica, ProtocoloSanitario, ProtocoloSanitarioLancamento, Sanidade, VendaAnimal,
)
from fazenda.rules.estoque_baixa import carencia_para_item, resolver_marca_comercial

router = APIRouter(prefix="/relatorio-rastreabilidade-sanitaria", tags=["relatorio-rastreabilidade-sanitaria"])


@router.get("/")
def relatorio(
    numero: str | None = Query(None, description="Número do animal"),
    gta: str | None = Query(None, description="Número da GTA (compra ou venda)"),
    data_de: date | None = None,
    data_ate: date | None = None,
    session: Session = Depends(get_session),
) -> list[dict]:
    # Determina o conjunto de animais a percorrer: um número específico, os
    # animais ligados a uma GTA (compra ou venda), ou todos (sem filtro).
    numeros: set[str] | None = None
    if numero:
        numeros = {numero}
    elif gta:
        numeros = {c.numero_animal for c in session.exec(select(CompraAnimal).where(CompraAnimal.gta == gta)).all()}
        numeros |= {v.numero_animal for v in session.exec(select(VendaAnimal).where(VendaAnimal.gta == gta)).all()}

    def _dentro_periodo(d: date | None) -> bool:
        if d is None:
            return False
        if data_de and d < data_de:
            return False
        if data_ate and d > data_ate:
            return False
        return True

    def _incluido(n: str) -> bool:
        return numeros is None or n in numeros

    linhas: list[dict] = []

    for c in session.exec(select(CompraAnimal)).all():
        if not _incluido(c.numero_animal) or not _dentro_periodo(c.data_compra):
            continue
        linhas.append({
            "numero_animal": c.numero_animal, "tipo_evento": "Compra", "data": c.data_compra,
            "gta": c.gta, "descricao": f"Compra de {c.vendedor}", "contraparte": c.vendedor,
            "produto": None, "resultado": None, "doenca": None, "responsavel": c.responsavel,
        })

    for v in session.exec(select(VendaAnimal)).all():
        if not _incluido(v.numero_animal) or not _dentro_periodo(v.data_venda):
            continue
        linhas.append({
            "numero_animal": v.numero_animal, "tipo_evento": "Venda", "data": v.data_venda,
            "gta": v.gta, "descricao": f"Venda para {v.comprador}", "contraparte": v.comprador,
            "produto": None, "resultado": None, "doenca": None, "responsavel": v.responsavel,
        })

    # Item de Estoque por nome do produto — casa cada aplicação com a marca
    # comercial dona da carência (mesma resolução de sanidade.listar_aplicacoes),
    # cacheada por nome porque o mesmo produto se repete em muitas linhas. Este
    # relatório não filtra por fazenda (nenhum outro campo aqui filtra), então
    # o casamento também não filtra — coerente com o resto do arquivo.
    estoque_por_nome = {(e.nome or "").strip().lower(): e for e in session.exec(select(Estoque)).all()}
    resolvido_por_produto: dict[str, tuple[Estoque | None, MedicamentoComercial | None]] = {}

    def _item_e_marca(produto: str | None) -> tuple[Estoque | None, MedicamentoComercial | None]:
        chave = (produto or "").strip().lower()
        if chave not in resolvido_por_produto:
            item = estoque_por_nome.get(chave)
            marca = resolver_marca_comercial(
                session, item=item, nome=produto,
                principio_ativo_id=item.principio_ativo_id if item else None,
            )
            resolvido_por_produto[chave] = (item, marca)
        return resolvido_por_produto[chave]

    for s in session.exec(select(Sanidade)).all():
        if not _incluido(s.numero_matriz) or not _dentro_periodo(s.data_aplicacao):
            continue
        item_produto, marca_produto = _item_e_marca(s.produto)
        linhas.append({
            "numero_animal": s.numero_matriz, "tipo_evento": "Aplicação sanitária", "data": s.data_aplicacao,
            "gta": None, "descricao": s.produto, "contraparte": None,
            "produto": s.produto, "resultado": None, "doenca": s.atividade, "responsavel": s.responsavel,
            "carencia": carencia_para_item(item_produto, marca_produto, data_aplicacao=s.data_aplicacao),
        })

    protocolos_nomes = {p.id: p.nome for p in session.exec(select(ProtocoloSanitario)).all()}
    for p in session.exec(select(ProtocoloSanitarioLancamento)).all():
        if not _incluido(p.numero_matriz) or not _dentro_periodo(p.data_inicio):
            continue
        linhas.append({
            "numero_animal": p.numero_matriz, "tipo_evento": "Protocolo sanitário", "data": p.data_inicio,
            "gta": None, "descricao": protocolos_nomes.get(p.protocolo_id, "—"), "contraparte": None,
            "produto": None, "resultado": None, "doenca": None, "responsavel": p.responsavel,
        })

    eventos_nomes = {e.id: e.nome for e in session.exec(select(EventoSanitario)).all()}
    for e in session.exec(select(ExameResultado)).all():
        if not _incluido(e.numero_matriz) or not _dentro_periodo(e.data_exame):
            continue
        linhas.append({
            "numero_animal": e.numero_matriz, "tipo_evento": "Exame", "data": e.data_exame,
            "gta": None, "descricao": eventos_nomes.get(e.evento_sanitario_id, "—"), "contraparte": None,
            "produto": None, "resultado": e.resultado, "doenca": None, "responsavel": e.veterinario,
        })

    for o in session.exec(select(OcorrenciaClinica)).all():
        if not _incluido(o.numero_matriz) or not _dentro_periodo(o.data_ocorrencia):
            continue
        linhas.append({
            "numero_animal": o.numero_matriz, "tipo_evento": "Doença (ocorrência clínica)", "data": o.data_ocorrencia,
            "gta": None, "descricao": o.doenca, "contraparte": None,
            "produto": None, "resultado": None, "doenca": o.doenca, "responsavel": None,
        })

    for b in session.exec(select(BaixaAnimal)).all():
        if not _incluido(b.numero_animal) or not _dentro_periodo(b.data_baixa):
            continue
        linhas.append({
            "numero_animal": b.numero_animal, "tipo_evento": "Baixa", "data": b.data_baixa,
            "gta": None, "descricao": f"{b.tipo_baixa} — {b.motivo}", "contraparte": b.cliente,
            "produto": None, "resultado": None, "doenca": b.motivo_doenca, "responsavel": b.responsavel,
        })

    # Nome do animal, para exibir junto do número na tabela do relatório.
    nomes_animal = {
        a.numero: a.nome for a in session.exec(select(Animal)).all()
        if numeros is None or a.numero in numeros
    }
    for l in linhas:
        l["nome_animal"] = nomes_animal.get(l["numero_animal"])
        # Só a linha de "Aplicação sanitária" tem carência (é a única com
        # produto/dose) — as demais ganham a chave com None, pra UI poder
        # sempre ler `l.carencia` sem checar o tipo de evento primeiro.
        l.setdefault("carencia", None)

    linhas.sort(key=lambda l: (l["numero_animal"], l["data"]))
    return linhas
