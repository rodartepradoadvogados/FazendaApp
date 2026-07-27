"""
Painel Mestre CowData — Equipe própria da CowData (Sócio/Comercial/T.I./
Financeiro/Marketing/Suporte) e Financeiro CowData (livro-caixa independente
de qualquer fazenda-cliente). Ver fazenda/models/multitenant.py::
Fazenda.eh_empresa_cowdata e fazenda/models/cowdata_interno.py::LancamentoCowData.

Tudo aqui é `exigir_dono`-gated (só o proprietário da CowData) e opera sempre
sobre a ÚNICA fazenda marcada `eh_empresa_cowdata=True` — nunca sobre a
fazenda selecionada no token (get_fazenda_atual_id), que é irrelevante aqui.
Reaproveita os modelos Pessoa/FolhaPagamento (mesmo formato da folha de
pagamento de qualquer fazenda-cliente), mas por endpoints NOVOS e isolados —
nenhuma alteração nos routers tenant-facing já testados.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_dono
from fazenda.database import get_session
from fazenda.models import CobrancaAsaas, Fazenda, FolhaPagamento, Pessoa, SeedFlag, TipoPessoa, Usuario
from fazenda.models.cowdata_interno import LancamentoCowData

router = APIRouter(prefix="/painel-cowdata", tags=["painel-cowdata"])

NOME_FAZENDA_COWDATA = "CowData (empresa)"

CARGOS_COWDATA = ["Sócio", "Comercial", "T.I.", "Financeiro", "Marketing", "Suporte"]


def seed_cowdata_empresa(session: Session) -> Fazenda:
    """Garante a existência da fazenda "lógica" que ancora Equipe/Financeiro
    CowData (get-or-create — idempotente) e semeia os cargos padrão (uma vez,
    via SeedFlag, mesmo padrão de seed_tipos_pessoa) sem nunca sobrescrever
    cargos adicionados depois pelo usuário."""
    fazenda = session.exec(select(Fazenda).where(Fazenda.eh_empresa_cowdata == True)).first()  # noqa: E712
    if not fazenda:
        fazenda = Fazenda(nome=NOME_FAZENDA_COWDATA, eh_empresa_cowdata=True)
        session.add(fazenda)
        session.commit()
        session.refresh(fazenda)

    chave = "cowdata_cargos_v1"
    if not session.get(SeedFlag, chave):
        for nome in CARGOS_COWDATA:
            existe = session.exec(
                select(TipoPessoa).where(TipoPessoa.nome == nome, TipoPessoa.fazenda_id == fazenda.id)
            ).first()
            if not existe:
                session.add(TipoPessoa(nome=nome, fazenda_id=fazenda.id))
        session.add(SeedFlag(chave=chave))
        session.commit()
    return fazenda


def _fazenda_cowdata_id(session: Session) -> int:
    fazenda = session.exec(select(Fazenda).where(Fazenda.eh_empresa_cowdata == True)).first()  # noqa: E712
    if not fazenda:
        raise HTTPException(status_code=500, detail="Fazenda interna da CowData não provisionada")
    return fazenda.id


# ---------------------------------------------------------------------------
# Equipe CowData
# ---------------------------------------------------------------------------
class PessoaCowDataIn(BaseModel):
    nome: str
    cargo: str  # um de CARGOS_COWDATA (ou outro já cadastrado)
    telefones: list[str] = []
    emails: list[str] = []
    cpf_cnpj: Optional[str] = None
    cep: Optional[str] = None
    salario_base: Optional[float] = None
    data_admissao: Optional[date] = None
    observacoes: Optional[str] = None
    ativo: bool = True


def _pessoa_publica(p: Pessoa) -> dict:
    return {
        "id": p.id,
        "nome": p.nome,
        "cargo": p.tipo,
        "telefones": json.loads(p.telefones) if p.telefones else [],
        "emails": json.loads(p.emails) if p.emails else [],
        "cpf_cnpj": p.cpf_cnpj,
        "cep": p.cep,
        "salario_base": p.salario_base,
        "data_admissao": p.data_admissao,
        "observacoes": p.observacoes,
        "ativo": p.ativo,
    }


@router.get("/equipe/cargos")
def listar_cargos(_: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> list[str]:
    fazenda_id = _fazenda_cowdata_id(session)
    tipos = session.exec(
        select(TipoPessoa).where(TipoPessoa.fazenda_id == fazenda_id, TipoPessoa.ativo == True)  # noqa: E712
    ).all()
    return [t.nome for t in tipos]


@router.get("/equipe/pessoas")
def listar_equipe(_: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> list[dict]:
    fazenda_id = _fazenda_cowdata_id(session)
    pessoas = session.exec(select(Pessoa).where(Pessoa.fazenda_id == fazenda_id)).all()
    return [_pessoa_publica(p) for p in sorted(pessoas, key=lambda p: p.nome)]


@router.post("/equipe/pessoas")
def criar_membro_equipe(
    dados: PessoaCowDataIn, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)
) -> dict:
    fazenda_id = _fazenda_cowdata_id(session)
    cargo_existe = session.exec(
        select(TipoPessoa).where(TipoPessoa.nome == dados.cargo, TipoPessoa.fazenda_id == fazenda_id)
    ).first()
    if not cargo_existe:
        raise HTTPException(status_code=400, detail="Cargo inválido")
    pessoa = Pessoa(
        fazenda_id=fazenda_id,
        nome=dados.nome,
        tipo=dados.cargo,
        telefones=json.dumps(dados.telefones) if dados.telefones else None,
        emails=json.dumps(dados.emails) if dados.emails else None,
        telefone=dados.telefones[0] if dados.telefones else None,
        email=dados.emails[0] if dados.emails else None,
        cpf_cnpj=dados.cpf_cnpj,
        cep=dados.cep,
        salario_base=dados.salario_base,
        data_admissao=dados.data_admissao,
        observacoes=dados.observacoes,
        ativo=dados.ativo,
    )
    session.add(pessoa)
    session.commit()
    session.refresh(pessoa)
    return _pessoa_publica(pessoa)


def _pessoa_equipe_ou_404(session: Session, pessoa_id: int) -> Pessoa:
    fazenda_id = _fazenda_cowdata_id(session)
    pessoa = session.get(Pessoa, pessoa_id)
    if not pessoa or pessoa.fazenda_id != fazenda_id:
        raise HTTPException(status_code=404, detail="Membro da equipe não encontrado")
    return pessoa


@router.put("/equipe/pessoas/{pessoa_id}")
def editar_membro_equipe(
    pessoa_id: int, dados: PessoaCowDataIn, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)
) -> dict:
    pessoa = _pessoa_equipe_ou_404(session, pessoa_id)
    pessoa.nome = dados.nome
    pessoa.tipo = dados.cargo
    pessoa.telefones = json.dumps(dados.telefones) if dados.telefones else None
    pessoa.emails = json.dumps(dados.emails) if dados.emails else None
    pessoa.telefone = dados.telefones[0] if dados.telefones else None
    pessoa.email = dados.emails[0] if dados.emails else None
    pessoa.cpf_cnpj = dados.cpf_cnpj
    pessoa.cep = dados.cep
    pessoa.salario_base = dados.salario_base
    pessoa.data_admissao = dados.data_admissao
    pessoa.observacoes = dados.observacoes
    pessoa.ativo = dados.ativo
    session.add(pessoa)
    session.commit()
    session.refresh(pessoa)
    return _pessoa_publica(pessoa)


@router.delete("/equipe/pessoas/{pessoa_id}")
def excluir_membro_equipe(
    pessoa_id: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)
) -> dict:
    pessoa = _pessoa_equipe_ou_404(session, pessoa_id)
    session.delete(pessoa)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Folha de pagamento da Equipe CowData — mesmo formato de FolhaPagamento
# usado pela folha de pagamento de qualquer fazenda-cliente, sem recorrência
# automática nem geração de Contas a Pagar (não existe "Contas a Pagar" aqui
# — ver LancamentoCowData/livro-caixa abaixo, onde a folha paga entra como
# despesa "Folha").
# ---------------------------------------------------------------------------
class FolhaCowDataIn(BaseModel):
    competencia: str  # "AAAA-MM"
    valor_bruto: float
    descontos: float = 0.0
    valor_liquido: float
    status: str = "pendente"  # pendente | pago
    data_pagamento: Optional[date] = None
    observacao: Optional[str] = None


def _folha_publica(f: FolhaPagamento) -> dict:
    return {
        "id": f.id,
        "pessoa_id": f.pessoa_id,
        "competencia": f.competencia,
        "valor_bruto": f.valor_bruto,
        "descontos": f.descontos,
        "valor_liquido": f.valor_liquido,
        "status": f.status,
        "data_pagamento": f.data_pagamento,
        "observacao": f.observacao,
    }


@router.get("/equipe/pessoas/{pessoa_id}/folha")
def listar_folha_membro(
    pessoa_id: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)
) -> list[dict]:
    _pessoa_equipe_ou_404(session, pessoa_id)
    lancamentos = session.exec(select(FolhaPagamento).where(FolhaPagamento.pessoa_id == pessoa_id)).all()
    return [_folha_publica(f) for f in sorted(lancamentos, key=lambda f: f.competencia, reverse=True)]


@router.post("/equipe/pessoas/{pessoa_id}/folha")
def lancar_folha_membro(
    pessoa_id: int, dados: FolhaCowDataIn, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)
) -> dict:
    fazenda_id = _fazenda_cowdata_id(session)
    _pessoa_equipe_ou_404(session, pessoa_id)
    folha = FolhaPagamento(
        fazenda_id=fazenda_id,
        pessoa_id=pessoa_id,
        competencia=dados.competencia,
        valor_bruto=dados.valor_bruto,
        descontos=dados.descontos,
        valor_liquido=dados.valor_liquido,
        status=dados.status,
        data_pagamento=dados.data_pagamento,
        observacao=dados.observacao,
    )
    session.add(folha)
    session.commit()
    session.refresh(folha)
    return _folha_publica(folha)


def _folha_equipe_ou_404(session: Session, folha_id: int) -> FolhaPagamento:
    fazenda_id = _fazenda_cowdata_id(session)
    folha = session.get(FolhaPagamento, folha_id)
    if not folha or folha.fazenda_id != fazenda_id:
        raise HTTPException(status_code=404, detail="Lançamento de folha não encontrado")
    return folha


@router.put("/equipe/folha/{folha_id}")
def editar_folha_membro(
    folha_id: int, dados: FolhaCowDataIn, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)
) -> dict:
    folha = _folha_equipe_ou_404(session, folha_id)
    folha.competencia = dados.competencia
    folha.valor_bruto = dados.valor_bruto
    folha.descontos = dados.descontos
    folha.valor_liquido = dados.valor_liquido
    folha.status = dados.status
    folha.data_pagamento = dados.data_pagamento
    folha.observacao = dados.observacao
    session.add(folha)
    session.commit()
    session.refresh(folha)
    return _folha_publica(folha)


@router.delete("/equipe/folha/{folha_id}")
def excluir_folha_membro(folha_id: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    folha = _folha_equipe_ou_404(session, folha_id)
    session.delete(folha)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Financeiro CowData — livro-caixa independente (receita/despesa manual +
# receita de assinatura real das fazendas-clientes + folha paga da equipe).
# ---------------------------------------------------------------------------
CATEGORIAS_RECEITA = ["assinatura_avulsa", "servico_avulso", "outra_receita"]
CATEGORIAS_DESPESA = ["folha_equipe", "servidor_infra", "ferramentas_software", "marketing", "juridico_contabil", "outra_despesa"]


class LancamentoCowDataIn(BaseModel):
    tipo: str  # receita | despesa
    categoria: str
    descricao: str
    contraparte: Optional[str] = None
    valor: float
    data: date


def _lancamento_publico(l: LancamentoCowData) -> dict:  # noqa: E741
    return {
        "id": l.id,
        "tipo": l.tipo,
        "categoria": l.categoria,
        "descricao": l.descricao,
        "contraparte": l.contraparte,
        "valor": l.valor,
        "data": l.data,
        "origem": "manual",
    }


@router.get("/financeiro/categorias")
def listar_categorias(_: Usuario = Depends(exigir_dono)) -> dict:
    return {"receita": CATEGORIAS_RECEITA, "despesa": CATEGORIAS_DESPESA}


@router.get("/financeiro/lancamentos")
def listar_lancamentos(
    de: Optional[date] = None,
    ate: Optional[date] = None,
    _: Usuario = Depends(exigir_dono),
    session: Session = Depends(get_session),
) -> list[dict]:
    query = select(LancamentoCowData)
    if de:
        query = query.where(LancamentoCowData.data >= de)
    if ate:
        query = query.where(LancamentoCowData.data <= ate)
    lancamentos = session.exec(query).all()
    return [_lancamento_publico(l) for l in sorted(lancamentos, key=lambda l: l.data, reverse=True)]


@router.post("/financeiro/lancamentos")
def criar_lancamento(
    dados: LancamentoCowDataIn, user: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)
) -> dict:
    if dados.tipo not in ("receita", "despesa"):
        raise HTTPException(status_code=400, detail="Tipo deve ser receita ou despesa")
    lancamento = LancamentoCowData(
        tipo=dados.tipo,
        categoria=dados.categoria,
        descricao=dados.descricao,
        contraparte=dados.contraparte,
        valor=dados.valor,
        data=dados.data,
        usuario_id=user.id,
    )
    session.add(lancamento)
    session.commit()
    session.refresh(lancamento)
    return _lancamento_publico(lancamento)


@router.put("/financeiro/lancamentos/{lancamento_id}")
def editar_lancamento(
    lancamento_id: int, dados: LancamentoCowDataIn, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)
) -> dict:
    lancamento = session.get(LancamentoCowData, lancamento_id)
    if not lancamento:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    lancamento.tipo = dados.tipo
    lancamento.categoria = dados.categoria
    lancamento.descricao = dados.descricao
    lancamento.contraparte = dados.contraparte
    lancamento.valor = dados.valor
    lancamento.data = dados.data
    session.add(lancamento)
    session.commit()
    session.refresh(lancamento)
    return _lancamento_publico(lancamento)


@router.delete("/financeiro/lancamentos/{lancamento_id}")
def excluir_lancamento(lancamento_id: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    lancamento = session.get(LancamentoCowData, lancamento_id)
    if not lancamento:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    session.delete(lancamento)
    session.commit()
    return {"ok": True}


def _movimentos_periodo(session: Session, de: date, ate: date) -> list[dict]:
    """Livro-caixa consolidado do período: lançamentos manuais (receita/
    despesa) + folha da equipe CowData paga no período (despesa) + assinaturas
    de fazendas-clientes pagas no período (receita real, via Asaas) — nunca
    duplica: a folha e a assinatura não passam por LancamentoCowData."""
    movimentos: list[dict] = []

    for l in session.exec(  # noqa: E741
        select(LancamentoCowData).where(LancamentoCowData.data >= de, LancamentoCowData.data <= ate)
    ).all():
        movimentos.append({
            "data": l.data, "tipo": l.tipo, "categoria": l.categoria, "descricao": l.descricao, "valor": l.valor,
        })

    fazenda_id_cowdata = _fazenda_cowdata_id(session)
    for cobranca in session.exec(
        select(CobrancaAsaas).where(
            CobrancaAsaas.status == "paga",
            CobrancaAsaas.pago_em >= de,
            CobrancaAsaas.pago_em <= ate,
            CobrancaAsaas.fazenda_id != fazenda_id_cowdata,
        )
    ).all():
        fazenda = session.get(Fazenda, cobranca.fazenda_id)
        movimentos.append({
            "data": cobranca.pago_em.date(), "tipo": "receita", "categoria": "assinatura",
            "descricao": f"Assinatura — {fazenda.nome if fazenda else cobranca.fazenda_id}", "valor": cobranca.valor,
        })

    for folha in session.exec(
        select(FolhaPagamento).where(
            FolhaPagamento.fazenda_id == fazenda_id_cowdata,
            FolhaPagamento.status == "pago",
            FolhaPagamento.data_pagamento >= de,
            FolhaPagamento.data_pagamento <= ate,
        )
    ).all():
        pessoa = session.get(Pessoa, folha.pessoa_id)
        movimentos.append({
            "data": folha.data_pagamento, "tipo": "despesa", "categoria": "folha_equipe",
            "descricao": f"Folha — {pessoa.nome if pessoa else folha.pessoa_id} ({folha.competencia})",
            "valor": folha.valor_liquido,
        })

    return sorted(movimentos, key=lambda m: m["data"])


@router.get("/financeiro/resumo")
def resumo_financeiro(
    de: date, ate: date, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)
) -> dict:
    movimentos = _movimentos_periodo(session, de, ate)
    receita = sum(m["valor"] for m in movimentos if m["tipo"] == "receita")
    despesa = sum(m["valor"] for m in movimentos if m["tipo"] == "despesa")
    return {"receita": round(receita, 2), "despesa": round(despesa, 2), "resultado": round(receita - despesa, 2)}


@router.get("/financeiro/livro-caixa")
def livro_caixa(
    de: date, ate: date, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)
) -> list[dict]:
    movimentos = _movimentos_periodo(session, de, ate)
    saldo = 0.0
    linhas = []
    for m in movimentos:
        saldo += m["valor"] if m["tipo"] == "receita" else -m["valor"]
        linhas.append({**m, "saldo_acumulado": round(saldo, 2)})
    return linhas


@router.get("/financeiro/fluxo-caixa")
def fluxo_caixa(
    de: date, ate: date, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)
) -> list[dict]:
    """Agrupado por mês (entradas/saídas/saldo do mês/saldo acumulado) —
    distinto do livro-caixa (lançamento a lançamento)."""
    movimentos = _movimentos_periodo(session, de, ate)
    por_mes: dict[str, dict] = {}
    for m in movimentos:
        chave = f"{m['data'].year:04d}-{m['data'].month:02d}"
        bucket = por_mes.setdefault(chave, {"competencia": chave, "entradas": 0.0, "saidas": 0.0})
        if m["tipo"] == "receita":
            bucket["entradas"] += m["valor"]
        else:
            bucket["saidas"] += m["valor"]
    saldo_acumulado = 0.0
    linhas = []
    for chave in sorted(por_mes.keys()):
        bucket = por_mes[chave]
        saldo_mes = bucket["entradas"] - bucket["saidas"]
        saldo_acumulado += saldo_mes
        linhas.append({
            "competencia": chave, "entradas": round(bucket["entradas"], 2), "saidas": round(bucket["saidas"], 2),
            "saldo_mes": round(saldo_mes, 2), "saldo_acumulado": round(saldo_acumulado, 2),
        })
    return linhas


@router.get("/financeiro/dre")
def dre(ano: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    """DRE simplificado do ano: receita total, despesas por categoria e
    resultado — mesma base de dados do livro-caixa/fluxo-caixa, só reagrupada."""
    de, ate = date(ano, 1, 1), date(ano, 12, 31)
    movimentos = _movimentos_periodo(session, de, ate)
    receita_total = sum(m["valor"] for m in movimentos if m["tipo"] == "receita")
    despesas_por_categoria: dict[str, float] = {}
    for m in movimentos:
        if m["tipo"] == "despesa":
            despesas_por_categoria[m["categoria"]] = despesas_por_categoria.get(m["categoria"], 0.0) + m["valor"]
    despesa_total = sum(despesas_por_categoria.values())
    return {
        "ano": ano,
        "receita_total": round(receita_total, 2),
        "despesas_por_categoria": {k: round(v, 2) for k, v in despesas_por_categoria.items()},
        "despesa_total": round(despesa_total, 2),
        "resultado": round(receita_total - despesa_total, 2),
    }
