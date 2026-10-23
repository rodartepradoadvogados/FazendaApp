"""
Carência de LEITE — integração com a produção (D4) e a lista "Leite separado".

  - `carencia_leite_na_data`: o registro sanitário (preventivo) que deixa a
    vaca em carência de leite numa data, com o MODO decidido na caixa/dia
    (bloqueio > descarte > tanque, o mais restritivo vale).
  - `leite_separado`: curativos (Sanidade, carência pela bula/cadastro do
    produto) e preventivos (`sanitario_registro.carencia_leite_ate`) JUNTOS,
    um item por vaca × aplicação ainda dentro da carência. SÓ LÊ.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlmodel import Session, select

ORDEM_MODO = {"bloqueio": 0, "descarte": 1, "tanque": 2, None: 3}
JANELA_CURATIVO_DIAS = 180


def carencia_leite_na_data(session: Session, fazenda_id: Optional[int], numero: str, data: date):
    from fazenda.models import Animal, SanitarioRegistro

    if fazenda_id is None:
        return None
    a = session.exec(select(Animal).where(Animal.fazenda_id == fazenda_id, Animal.numero == numero)).first()
    if a is None:
        return None
    regs = session.exec(select(SanitarioRegistro).where(
        SanitarioRegistro.fazenda_id == fazenda_id, SanitarioRegistro.animal_id == a.id,
        SanitarioRegistro.estado == "valido", SanitarioRegistro.carencia_leite_ate != None,  # noqa: E711
        SanitarioRegistro.carencia_leite_ate >= data, SanitarioRegistro.data <= data,
    )).all()
    if not regs:
        return None
    return sorted(regs, key=lambda r: (ORDEM_MODO.get(r.carencia_modo, 3), -r.carencia_leite_ate.toordinal()))[0]


def leite_separado(session: Session, fazenda_id: int, hoje: date) -> list[dict]:
    from fazenda.models import Animal, SanitarioCaixa, SanitarioRegistro, Sanidade
    from fazenda.rules.estoque_baixa import carencia_para_item, resolver_item, resolver_marca_comercial

    out: list[dict] = []
    ativos = {a.numero for a in session.exec(select(Animal).where(
        Animal.fazenda_id == fazenda_id, Animal.ativo == True)).all()}  # noqa: E712
    # Preventivos
    nomes_cx: dict[int, str] = {}
    for r in session.exec(select(SanitarioRegistro).where(
        SanitarioRegistro.fazenda_id == fazenda_id, SanitarioRegistro.estado == "valido",
        SanitarioRegistro.carencia_leite_ate != None, SanitarioRegistro.carencia_leite_ate >= hoje,  # noqa: E711
    )).all():
        if r.caixa_id and r.caixa_id not in nomes_cx:
            cx = session.get(SanitarioCaixa, r.caixa_id)
            nomes_cx[r.caixa_id] = (cx.nome_curto or cx.nome) if cx else "?"
        out.append({
            "origem": "preventivo", "numero": r.numero_animal_texto, "animal_id": r.animal_id,
            "produto": r.produto_texto or (nomes_cx.get(r.caixa_id) if r.caixa_id else r.outro_texto),
            "caixa": nomes_cx.get(r.caixa_id) if r.caixa_id else r.outro_texto,
            "data_aplicacao": r.data.isoformat(), "liberacao_leite": r.carencia_leite_ate.isoformat(),
            "modo": r.carencia_modo or "tanque", "registro_id": r.id,
        })
    # Curativos (e BST/Indução): carência pela bula/cadastro do produto
    cache: dict[str, Optional[int]] = {}
    for s in session.exec(select(Sanidade).where(
        Sanidade.fazenda_id == fazenda_id, Sanidade.data_aplicacao != None,  # noqa: E711
        Sanidade.data_aplicacao >= hoje - timedelta(days=JANELA_CURATIVO_DIAS),
    )).all():
        if s.numero_matriz not in ativos:
            continue
        if s.produto not in cache:
            item = resolver_item(session, fazenda_id=fazenda_id, produto=s.produto)
            marca = resolver_marca_comercial(session, item=item, nome=s.produto,
                                             principio_ativo_id=item.principio_ativo_id if item else None)
            cache[s.produto] = carencia_para_item(item, marca).get("leite_dias")
        dias = cache[s.produto]
        if dias is None:
            continue
        lib = s.data_aplicacao + timedelta(days=int(dias))
        if lib < hoje:
            continue
        out.append({
            "origem": "curativo", "numero": s.numero_matriz, "animal_id": None, "produto": s.produto, "caixa": None,
            "data_aplicacao": s.data_aplicacao.isoformat(), "liberacao_leite": lib.isoformat(),
            "modo": "descarte", "sanidade_id": s.id,
        })
    out.sort(key=lambda x: (x["liberacao_leite"], x["numero"] or ""))
    return out
