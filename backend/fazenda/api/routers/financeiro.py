"""
Router financeiro — DRE, fluxo de caixa, KPIs e lançamentos financeiros
(contas a pagar/a receber, com parcelamento, conta bancária e importação de XML).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user
from fazenda.database import get_session
from fazenda.models import (
    CentroCusto, ContaCorrente, ContaGerencial, EntregaLeiteMensal, Estoque, FormaPagamentoCadastro, LancamentoItem, MovimentoEstoque,
    Patrimonio, PlanoContaGerencial, SeedFlag, TipoDocumento, Usuario,
)
from fazenda.rules.auditoria import mapa_usuarios
from fazenda.rules.centro_custo import CENTROS_CANONICOS, MAPA_CENTRO_CUSTO, mapear_centro_custo
from fazenda.rules.leitura_documento import MIME_ACEITOS, ler_documento
from fazenda.rules.nfe_xml import parse_nfe_xml
from fazenda.rules.rmca import calcular_custo_fisico, calcular_rmca_gerencial
from fazenda.rules.custo_leite import calcular_custo_por_litro, litros_leite_no_periodo
from fazenda.rules.patrimonio import calcular_depreciacao

router = APIRouter(prefix="/financeiro", tags=["financeiro"])

TIPOS_DOCUMENTO = ["Nota fiscal", "Recibo", "Folha de pagamento", "Fatura", "Contrato"]

# Seed inicial — as duas contas correntes da fazenda no Banco do Brasil (antes
# uma lista fixa em Python; agora cadastráveis em Configurações > Parâmetros
# financeiros). Ver seed_parametros_financeiros, chamada uma vez no startup.
SEED_CONTAS_CORRENTES = [
    {"banco": "Banco do Brasil", "agencia": "3775-3", "numero_conta": "3.615-3"},
    {"banco": "Banco do Brasil", "agencia": "4057-6", "numero_conta": "3.615-3"},
]


def rotulo_conta_corrente(c: ContaCorrente) -> str:
    return f"{c.banco} · Agência {c.agencia} · Conta corrente {c.numero_conta}"


def seed_parametros_financeiros(session: Session) -> None:
    """Cria as contas correntes padrão se a tabela ainda estiver vazia (idempotente)."""
    if not session.exec(select(ContaCorrente)).first():
        for dados in SEED_CONTAS_CORRENTES:
            session.add(ContaCorrente(**dados))
        session.commit()


def normalizar_plano_contas(session: Session) -> None:
    """Normaliza o plano de contas gerenciais conforme o padrão pedido pelo
    usuário — roda UMA única vez (guardada por SeedFlag), para nunca
    sobrescrever ajustes manuais feitos depois em Configurações:

    - Toda conta gerencial fica ATIVA (o plano importado marcava os grupos/
      cabeçalhos como inativos; agora a seleção é feita só nas contas-folha).
    - Todo item de "3.01.01 - Alimentação do rebanho" já entra marcado como
      custo de alimentação para o indicador RMCA.
    """
    chave = "plano_contas_normalizado_v1"
    if session.get(SeedFlag, chave):
        return
    contas = session.exec(select(PlanoContaGerencial)).all()
    if contas:  # nada a fazer num banco ainda sem plano importado
        for c in contas:
            if not c.ativa:
                c.ativa = True
                session.add(c)
            if c.codigo.startswith("3.01.01") and c.rmca_custo_alimentacao is None:
                c.rmca_custo_alimentacao = True
                session.add(c)
    session.add(SeedFlag(chave=chave))
    session.commit()


# Heurística de classificação padrão da natureza (serviço/produto/ambos) de
# cada conta gerencial, por palavra-chave no nome — roda a CADA start (não
# precisa de SeedFlag: só preenche onde `natureza` ainda está vazio, então
# nunca sobrescreve uma classificação que o usuário já ajustou manualmente
# em Configurações > Parâmetros financeiros > Conta gerencial).
_PALAVRAS_PRODUTO = (
    "racao", "alimento", "concentrado", "mineral", "medicamento", "vacina", "farmaco",
    "semen", "insumo", "combustivel", "oleo", "peca", "material", "equipamento",
    "ferramenta", "animal", "fertilizante", "semente", "embalagem", "uniforme", "epi",
    "graxa", "pneu", "bateria", "lubrificante", "ensacado", "suplemento", "silagem",
    "feno", "sal mineral", "produto",
)
_PALAVRAS_SERVICO = (
    "salario", "honorario", "comissao", "mao de obra", "frete", "transporte",
    "consultoria", "assessoria", "contabilidade", "advocacia", "exame", "veterinario",
    "manutencao", "aluguel", "energia", "agua", "telefone", "internet", "seguro",
    "imposto", "taxa", "juros", "tarifa", "bancaria", "bancario", "corretagem",
    "servico", "mensalidade", "assinatura", "publicidade", "marketing", "inseminacao",
    "diaria", "deslocamento", "hospedagem", "cartorio", "auditoria",
)


def _sem_acento_nat(txt: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn")


def classificar_natureza_plano_contas(session: Session) -> None:
    contas = session.exec(select(PlanoContaGerencial)).all()
    for c in contas:
        if c.natureza is not None:
            continue
        nome = _sem_acento_nat((c.nome or "").lower())
        eh_produto = any(p in nome for p in _PALAVRAS_PRODUTO)
        eh_servico = any(p in nome for p in _PALAVRAS_SERVICO)
        if eh_produto and not eh_servico:
            c.natureza = "produto"
        elif eh_servico and not eh_produto:
            c.natureza = "servico"
        else:
            # Nem bateu com nenhuma palavra-chave, nem bateu com as duas —
            # "ambos" é o padrão mais seguro (nunca bloqueia um lançamento
            # legítimo); o usuário pode restringir manualmente depois.
            c.natureza = "ambos"
        session.add(c)
    if contas:
        session.commit()


def normalizar_centros_custo(session: Session) -> None:
    """Padroniza os centros de custo (uma vez, guardado por SeedFlag):
    PL → Pecuária Leiteira, C|26 → Financiamento 2026, ARR → Arrendamento.
    Renomeia nos lançamentos e no padrão do estoque, garante os três nomes
    canônicos no cadastro e remove os cadastros com as siglas antigas — para
    existir só o nome legível, selecionável em todos os lugares.
    """
    chave = "centros_custo_canonicos_v1"
    if session.get(SeedFlag, chave):
        return
    for c in session.exec(select(ContaGerencial)).all():
        novo = mapear_centro_custo(c.centro_custo)
        if novo != c.centro_custo:
            c.centro_custo = novo
            session.add(c)
    for e in session.exec(select(Estoque)).all():
        novo = mapear_centro_custo(e.centro_custo_padrao)
        if novo != e.centro_custo_padrao:
            e.centro_custo_padrao = novo
            session.add(e)
    existentes = {cc.nome.strip().upper(): cc for cc in session.exec(select(CentroCusto)).all()}
    for sigla, canonico in MAPA_CENTRO_CUSTO.items():
        antigo = existentes.get(sigla)
        if antigo:
            session.delete(antigo)
        if canonico.strip().upper() not in existentes:
            novo = CentroCusto(nome=canonico, ativo=True)
            session.add(novo)
            existentes[canonico.strip().upper()] = novo
    session.add(SeedFlag(chave=chave))
    session.commit()


class ParcelaIn(BaseModel):
    data_vencimento: date
    valor: float


class ItemIn(BaseModel):
    codigo_conta_gerencial: Optional[str] = None
    nome_conta_gerencial: Optional[str] = None
    produto: str
    tipo_item: Optional[str] = None  # "produto" | "servico"
    descricao: Optional[str] = None
    quantidade: Optional[float] = None
    valor_unitario: Optional[float] = None
    valor_total: float


class LancamentoIn(BaseModel):
    tipo: str  # "receita" | "despesa"
    itens: list[ItemIn]  # um ou mais produtos/serviços da mesma nota
    centro_custo: Optional[str] = None
    fornecedor_cliente: Optional[str] = None
    responsavel: Optional[str] = None
    tipo_documento: Optional[str] = None
    numero_documento: Optional[str] = None
    data_emissao: Optional[date] = None
    data_vencimento: Optional[date] = None  # vencimento do lançamento não-parcelado (vai p/ contas a pagar e agenda)
    data_competencia: Optional[date] = None
    data_prevista_entrada: Optional[date] = None
    data_pedido: Optional[date] = None
    entregue: Optional[bool] = None
    desconto: float = 0
    acrescimo: float = 0
    parcelas: list[ParcelaIn] = []
    # Preenchidos só quando o lançamento já nasce pago/recebido (sem parcelamento).
    data_pagamento: Optional[date] = None
    valor_pago: Optional[float] = None
    conta_bancaria: Optional[str] = None
    numero_documento_pagamento: Optional[str] = None
    forma_pagamento: Optional[str] = None
    # Vincula esta nota fiscal/recibo a um Pedido (Pedidos > módulo próprio) —
    # é só a partir deste vínculo que o pedido passa a refletir em Financeiro.
    pedido_id: Optional[int] = None


FORMAS_PAGAMENTO = ["pix", "transferencia", "boleto", "credito", "debito"]


class PagamentoIn(BaseModel):
    data_pagamento: date
    valor_pago: float
    conta_bancaria: Optional[str] = None
    numero_documento_pagamento: Optional[str] = None
    forma_pagamento: Optional[str] = None
    data_vencimento_cartao: Optional[date] = None


class BaixaLoteIn(BaseModel):
    lancamento_ids: list[int]
    data_pagamento: date
    conta_bancaria: Optional[str] = None
    forma_pagamento: Optional[str] = None
    data_vencimento_cartao: Optional[date] = None
    numero_documento_pagamento: Optional[str] = None


class BaixaLoteItemIn(BaseModel):
    """Pagamento de UMA nota dentro da baixa em lote — cada uma com sua própria
    data, valor, conta e forma."""
    lancamento_id: int
    data_pagamento: date
    valor_pago: float
    conta_bancaria: Optional[str] = None
    forma_pagamento: Optional[str] = None
    data_vencimento_cartao: Optional[date] = None
    numero_documento_pagamento: Optional[str] = None


class BaixaLoteDetalhadaIn(BaseModel):
    itens: list[BaixaLoteItemIn]


class XmlIn(BaseModel):
    xml: str


def _proximo_numero_lancamento(session: Session, ano: int) -> str:
    prefixo = f"LC-{ano}-"
    existentes = session.exec(
        select(ContaGerencial.numero_lancamento).where(ContaGerencial.numero_lancamento.like(f"{prefixo}%"))
    ).all()
    maior = 0
    for n in existentes:
        if n and n.startswith(prefixo):
            try:
                maior = max(maior, int(n[len(prefixo):]))
            except ValueError:
                continue
    return f"{prefixo}{maior + 1:05d}"


@router.get("/dre")
def dre(
    data_inicio: date = Query(..., description="Data inicial (competência)"),
    data_fim: date = Query(..., description="Data final (competência)"),
    centro_custo: Optional[str] = Query(None),
    regime: str = Query("competencia", description="'competencia' ou 'caixa'"),
    session: Session = Depends(get_session),
) -> dict:
    """
    Retorna DRE (Demonstrativo de Resultado) por regime de competência ou caixa.
    """
    campo_data = "data_competencia" if regime == "competencia" else "data_pagamento"

    contas = session.exec(select(ContaGerencial)).all()

    filtradas = []
    for c in contas:
        data_ref = c.data_competencia if regime == "competencia" else c.data_pagamento
        if data_ref and data_inicio <= data_ref <= data_fim:
            if centro_custo is None or c.centro_custo == centro_custo:
                filtradas.append(c)

    receitas = sum(c.valor_total or 0 for c in filtradas if c.tipo == "receita")
    despesas = sum(c.valor_total or 0 for c in filtradas if c.tipo == "despesa")
    resultado = receitas - despesas

    # Agrupa por código de conta
    por_conta: dict[str, dict] = {}
    for c in filtradas:
        codigo = c.codigo_conta or "Sem classificação"
        nivel1 = codigo.split(".")[0] if "." in codigo else codigo
        if nivel1 not in por_conta:
            por_conta[nivel1] = {"descricao": c.descricao or "", "receitas": 0.0, "despesas": 0.0}
        if c.tipo == "receita":
            por_conta[nivel1]["receitas"] += c.valor_total or 0
        else:
            por_conta[nivel1]["despesas"] += c.valor_total or 0

    return {
        "periodo": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()},
        "regime": regime,
        "centro_custo": centro_custo,
        "receitas_total": round(receitas, 2),
        "despesas_total": round(despesas, 2),
        "resultado": round(resultado, 2),
        "por_conta": por_conta,
    }


@router.get("/lancamentos")
def listar_lancamentos(session: Session = Depends(get_session)) -> dict:
    """
    Movimentações achatadas para o dashboard financeiro interativo.
    O front filtra por regime (competência/caixa), ano e centro de custo.
    """
    itens_por_lancamento: dict[str, list[dict]] = {}
    for it in session.exec(select(LancamentoItem)).all():
        itens_por_lancamento.setdefault(it.numero_lancamento, []).append({
            "id": it.id,
            "codigo_conta_gerencial": it.codigo_conta_gerencial,
            "nome_conta_gerencial": it.nome_conta_gerencial,
            "produto": it.produto,
            "descricao": it.descricao,
            "quantidade": it.quantidade,
            "valor_unitario": it.valor_unitario,
            "valor_total": it.valor_total,
        })

    contas = session.exec(select(ContaGerencial)).all()
    nomes_usuarios = mapa_usuarios(session, {c.usuario_id for c in contas})

    registros = []
    for c in contas:
        dc = c.data_competencia
        dp = c.data_pagamento
        registros.append({
            "id": c.id,
            "numero_lancamento": c.numero_lancamento,
            "tipo": c.tipo,
            "usuario_nome": nomes_usuarios.get(c.usuario_id),
            "valor": c.valor_total or 0.0,
            "valor_pago": c.valor_pago,
            "desconto_acrescimo": c.desconto_acrescimo,
            "desconto_nota": c.desconto_nota,
            "acrescimo_nota": c.acrescimo_nota,
            "centro_custo": c.centro_custo or "(sem centro)",
            "codigo_conta": (c.codigo_conta or "").split(".")[0] or "(sem conta)",
            "conta_completa": c.codigo_conta or "",
            "descricao": c.descricao or "",
            "fornecedor": c.fornecedor_cliente or "",
            "responsavel": c.responsavel,
            "tipo_documento": c.tipo_documento,
            "numero_documento": c.numero_nota,
            "numero_documento_pagamento": c.numero_documento_pagamento,
            "conta_bancaria": c.conta_bancaria,
            "forma_pagamento": c.forma_pagamento,
            "data_vencimento_cartao": c.data_vencimento_cartao.isoformat() if c.data_vencimento_cartao else None,
            "quantidade": c.quantidade,
            "valor_unitario": c.valor_unitario,
            "entregue": c.entregue,
            "parcela_num": c.parcela_num,
            "parcela_total": c.parcela_total,
            "origem": c.origem,
            "itens": itens_por_lancamento.get(c.numero_lancamento or "", []),
            "data_competencia": dc.isoformat() if dc else None,
            "data_pagamento": dp.isoformat() if dp else None,
            "data_vencimento": c.data_vencimento.isoformat() if c.data_vencimento else None,
            "data_emissao": c.data_emissao.isoformat() if c.data_emissao else None,
            "data_prevista_entrada": c.data_prevista_entrada.isoformat() if c.data_prevista_entrada else None,
            "data_pedido": c.data_pedido.isoformat() if c.data_pedido else None,
            "mes_competencia": f"{dc.year}-{dc.month:02d}" if dc else None,
            "ano_competencia": dc.year if dc else None,
            "mes_caixa": f"{dp.year}-{dp.month:02d}" if dp else None,
            "ano_caixa": dp.year if dp else None,
        })
    return {"lancamentos": registros, "total": len(registros)}


@router.get("/possiveis-duplicados")
def possiveis_duplicados(
    tipo: str, valor_total: float, fornecedor_cliente: str = "", data_emissao: date | None = None,
    excluir_numero_lancamento: str = "", session: Session = Depends(get_session),
) -> list[dict]:
    """
    Lançamentos já existentes parecidos com o que está sendo digitado agora —
    mesmo tipo (receita/despesa), fornecedor/cliente igual, valor dentro de
    uma pequena tolerância e data próxima. Usado no formulário para avisar
    "possível duplicado" antes de salvar, com uma comparação lado a lado.
    """
    fornecedor_norm = (fornecedor_cliente or "").strip().lower()
    tolerancia_valor = max(0.01, abs(valor_total) * 0.01)  # 1% do valor, ou 1 centavo — o que for maior
    janela_dias = 10

    candidatos = session.exec(select(ContaGerencial).where(ContaGerencial.tipo == tipo)).all()
    por_numero: dict[str, ContaGerencial] = {}
    for c in candidatos:
        if excluir_numero_lancamento and c.numero_lancamento == excluir_numero_lancamento:
            continue
        if fornecedor_norm and (c.fornecedor_cliente or "").strip().lower() != fornecedor_norm:
            continue
        if c.valor_total is None or abs(c.valor_total - valor_total) > tolerancia_valor:
            continue
        data_referencia = c.data_emissao or c.data_competencia
        if data_emissao and data_referencia and abs((data_referencia - data_emissao).days) > janela_dias:
            continue
        # Uma nota parcelada tem várias linhas com o mesmo numero_lancamento —
        # mostra só uma vez (a de menor id) por lançamento encontrado.
        chave = c.numero_lancamento or str(c.id)
        if chave not in por_numero or c.id < por_numero[chave].id:
            por_numero[chave] = c

    achados = [
        {
            "id": c.id, "numero_lancamento": c.numero_lancamento, "tipo": c.tipo,
            "fornecedor_cliente": c.fornecedor_cliente, "valor_total": c.valor_total,
            "numero_documento": c.numero_nota,
            "data_emissao": c.data_emissao.isoformat() if c.data_emissao else None,
            "data_competencia": c.data_competencia.isoformat() if c.data_competencia else None,
            "centro_custo": c.centro_custo, "origem": c.origem,
        }
        for c in por_numero.values()
    ]
    achados.sort(key=lambda a: a["numero_lancamento"] or "", reverse=True)
    return achados[:10]


@router.get("/itens-por-conta")
def itens_por_conta(
    data_inicio: date = Query(...),
    data_fim: date = Query(...),
    session: Session = Depends(get_session),
) -> list[dict]:
    """
    Produtos/serviços lançados no período (por competência), um por linha —
    usado no DRE para o detalhamento correto por conta gerencial quando uma
    nota tem vários produtos com contas diferentes.
    """
    itens = session.exec(select(LancamentoItem)).all()
    return [
        {
            "numero_lancamento": it.numero_lancamento,
            "tipo": it.tipo,
            "codigo_conta_gerencial": it.codigo_conta_gerencial,
            "nome_conta_gerencial": it.nome_conta_gerencial,
            "produto": it.produto,
            "valor_total": it.valor_total,
            "data_competencia": it.data_competencia.isoformat() if it.data_competencia else None,
        }
        for it in itens
        if it.data_competencia and data_inicio <= it.data_competencia <= data_fim
    ]


@router.get("/opcoes")
def opcoes(session: Session = Depends(get_session)) -> dict:
    """Listas para os seletores do lançamento — plano de contas real + dados já importados."""
    plano = session.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.ativa == True)).all()
    # Só as contas-FOLHA são lançáveis (nível mais baixo da hierarquia): uma
    # conta é folha quando nenhuma outra tem o código dela como prefixo "X.".
    todos_codigos = [c.codigo for c in plano]
    def _eh_folha(codigo: str) -> bool:
        prefixo = codigo + "."
        return not any(outro.startswith(prefixo) for outro in todos_codigos)
    contas_gerenciais = sorted(
        [{"codigo": c.codigo, "nome": c.nome} for c in plano if _eh_folha(c.codigo)],
        key=lambda x: x["codigo"],
    )
    contas = session.exec(select(ContaGerencial)).all()
    # União com os valores já lançados como texto livre (antes do cadastro
    # formal existir) — nada que já foi usado deixa de aparecer no filtro.
    centros_cadastrados = {c.nome for c in session.exec(select(CentroCusto).where(CentroCusto.ativo == True)).all()}
    # Os centros canônicos (Pecuária Leiteira / Financiamento 2026 / Arrendamento)
    # ficam sempre disponíveis para seleção, mesmo antes de aparecerem num lançamento.
    centros_custo = sorted(centros_cadastrados | set(CENTROS_CANONICOS) | {c.centro_custo for c in contas if c.centro_custo})
    fornecedores = sorted({c.fornecedor_cliente for c in contas if c.fornecedor_cliente})
    produtos = sorted({it.produto for it in session.exec(select(LancamentoItem)).all() if it.produto})
    contas_correntes = session.exec(
        select(ContaCorrente).where(ContaCorrente.ativo == True).order_by(ContaCorrente.banco)
    ).all()
    tipos_doc_cadastrados = [t.nome for t in session.exec(select(TipoDocumento).where(TipoDocumento.ativo == True).order_by(TipoDocumento.nome)).all()]
    formas_pgto_cadastradas = [f.nome for f in session.exec(select(FormaPagamentoCadastro).where(FormaPagamentoCadastro.ativo == True).order_by(FormaPagamentoCadastro.nome)).all()]
    return {
        "contas_gerenciais": contas_gerenciais,
        "centros_custo": centros_custo,
        "fornecedores": fornecedores,
        "produtos": produtos,
        "contas_bancarias": [rotulo_conta_corrente(c) for c in contas_correntes],
        "tipos_documento": tipos_doc_cadastrados or TIPOS_DOCUMENTO,
        "formas_pagamento": formas_pgto_cadastradas or FORMAS_PAGAMENTO,
    }


@router.get("/plano-contas")
def plano_contas(session: Session = Depends(get_session)) -> list[dict]:
    """
    Plano de contas gerenciais COMPLETO (inclui os códigos de grupo/cabeçalho,
    que vêm com Ativa=Não e não aparecem em /opcoes — aqui servem só para dar
    nome à hierarquia nos relatórios, não para lançar diretamente neles).
    """
    plano = session.exec(select(PlanoContaGerencial)).all()
    return sorted(
        [
            {
                "id": c.id, "codigo": c.codigo, "nome": c.nome, "ativa": c.ativa,
                "nivel": c.codigo.count(".") + 1,
                "fluxo": c.fluxo, "tipo_fixo_variavel": c.tipo_fixo_variavel,
                "rmca_receita_leite": c.rmca_receita_leite, "rmca_custo_alimentacao": c.rmca_custo_alimentacao,
                "natureza": c.natureza,
            }
            for c in plano
        ],
        key=lambda x: x["codigo"],
    )


# ---------------------------------------------------------------------------
# Parâmetros financeiros (Configurações) — conta corrente, centro de custo e
# conta gerencial cadastráveis, além da importação de CSV do plano de contas.
# ---------------------------------------------------------------------------
class ContaCorrenteIn(BaseModel):
    banco: str
    agencia: str
    numero_conta: str
    ativo: bool = True


@router.get("/contas-correntes")
def listar_contas_correntes(session: Session = Depends(get_session)) -> list[dict]:
    contas = session.exec(select(ContaCorrente).order_by(ContaCorrente.banco, ContaCorrente.agencia)).all()
    return [{**c.model_dump(), "rotulo": rotulo_conta_corrente(c)} for c in contas]


@router.post("/contas-correntes")
def criar_conta_corrente(dados: ContaCorrenteIn, session: Session = Depends(get_session)) -> dict:
    c = ContaCorrente(**dados.model_dump())
    session.add(c)
    session.commit()
    session.refresh(c)
    return {**c.model_dump(), "rotulo": rotulo_conta_corrente(c)}


@router.put("/contas-correntes/{conta_id}")
def atualizar_conta_corrente(conta_id: int, dados: ContaCorrenteIn, session: Session = Depends(get_session)) -> dict:
    c = session.get(ContaCorrente, conta_id)
    if not c:
        raise HTTPException(status_code=404, detail="Conta corrente não encontrada")
    for campo, valor in dados.model_dump().items():
        setattr(c, campo, valor)
    session.add(c)
    session.commit()
    session.refresh(c)
    return {**c.model_dump(), "rotulo": rotulo_conta_corrente(c)}


class CentroCustoIn(BaseModel):
    nome: str
    ativo: bool = True


@router.get("/centros-custo")
def listar_centros_custo(session: Session = Depends(get_session)) -> list[dict]:
    return [c.model_dump() for c in session.exec(select(CentroCusto).order_by(CentroCusto.nome)).all()]


@router.post("/centros-custo")
def criar_centro_custo(dados: CentroCustoIn, session: Session = Depends(get_session)) -> dict:
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    if session.exec(select(CentroCusto).where(CentroCusto.nome == nome)).first():
        raise HTTPException(status_code=409, detail="Já existe um centro de custo com esse nome")
    c = CentroCusto(nome=nome, ativo=dados.ativo)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c.model_dump()


@router.put("/centros-custo/{centro_id}")
def atualizar_centro_custo(centro_id: int, dados: CentroCustoIn, session: Session = Depends(get_session)) -> dict:
    c = session.get(CentroCusto, centro_id)
    if not c:
        raise HTTPException(status_code=404, detail="Centro de custo não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    c.nome = nome
    c.ativo = dados.ativo
    session.add(c)
    session.commit()
    session.refresh(c)
    return c.model_dump()


class NomeAtivoFinanceiroIn(BaseModel):
    nome: str
    ativo: bool = True


def _crud_nome_ativo_financeiro(model, rotulo: str):
    """Mesma fábrica de CRUD nome+ativo do cadastro.py, para os cadastros que
    vivem em Parâmetros financeiros (Tipo de documento, Forma de pagamento)."""

    def listar(session: Session = Depends(get_session)) -> list[dict]:
        return [m.model_dump() for m in session.exec(select(model).order_by(model.nome)).all()]

    def criar(dados: NomeAtivoFinanceiroIn, session: Session = Depends(get_session)) -> dict:
        nome = dados.nome.strip()
        if not nome:
            raise HTTPException(status_code=400, detail="Nome é obrigatório")
        if session.exec(select(model).where(model.nome == nome)).first():
            raise HTTPException(status_code=409, detail=f"Já existe um(a) {rotulo} com esse nome")
        obj = model(nome=nome, ativo=dados.ativo)
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj.model_dump()

    def atualizar(item_id: int, dados: NomeAtivoFinanceiroIn, session: Session = Depends(get_session)) -> dict:
        obj = session.get(model, item_id)
        if not obj:
            raise HTTPException(status_code=404, detail=f"{rotulo.capitalize()} não encontrado(a)")
        nome = dados.nome.strip()
        if not nome:
            raise HTTPException(status_code=400, detail="Nome é obrigatório")
        obj.nome = nome
        obj.ativo = dados.ativo
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj.model_dump()

    return listar, criar, atualizar


_listar_tipos_doc, _criar_tipo_doc, _atualizar_tipo_doc = _crud_nome_ativo_financeiro(TipoDocumento, "tipo de documento")
router.get("/tipos-documento")(_listar_tipos_doc)
router.post("/tipos-documento")(_criar_tipo_doc)
router.put("/tipos-documento/{item_id}")(_atualizar_tipo_doc)

_listar_formas_pgto, _criar_forma_pgto, _atualizar_forma_pgto = _crud_nome_ativo_financeiro(FormaPagamentoCadastro, "forma de pagamento")
router.get("/formas-pagamento-cadastro")(_listar_formas_pgto)
router.post("/formas-pagamento-cadastro")(_criar_forma_pgto)
router.put("/formas-pagamento-cadastro/{item_id}")(_atualizar_forma_pgto)


# Seed inicial — migra as listas fixas que existiam antes (TIPOS_DOCUMENTO,
# FORMAS_PAGAMENTO) para os cadastros acima, mais os itens pedidos que ainda
# não existiam (Ordem de serviço/Outros; dinheiro/outros) — idempotente.
SEED_TIPOS_DOCUMENTO = [*TIPOS_DOCUMENTO, "Boleto", "Ordem de serviço", "Outros"]
SEED_FORMAS_PAGAMENTO_CADASTRO = [*FORMAS_PAGAMENTO, "dinheiro", "outros"]


def seed_tipos_documento_formas_pagamento(session: Session) -> None:
    # Só acrescenta os nomes que ainda não existem — nunca duplica, e continua
    # funcionando em bancos que já tinham a lista antiga (ex.: sem "Boleto").
    existentes_doc = {t.nome for t in session.exec(select(TipoDocumento)).all()}
    for nome in SEED_TIPOS_DOCUMENTO:
        if nome not in existentes_doc:
            session.add(TipoDocumento(nome=nome))
    session.commit()
    existentes_forma = {f.nome for f in session.exec(select(FormaPagamentoCadastro)).all()}
    for nome in SEED_FORMAS_PAGAMENTO_CADASTRO:
        if nome not in existentes_forma:
            session.add(FormaPagamentoCadastro(nome=nome))
    session.commit()


class PlanoContaGerencialIn(BaseModel):
    codigo: str
    nome: str
    ativa: bool = True
    participa_atividade: bool | None = None
    fluxo: bool | None = None
    tipo_fixo_variavel: str | None = None
    # Marcação para o indicador RMCA (ver GET /financeiro/rmca).
    rmca_receita_leite: bool | None = None
    rmca_custo_alimentacao: bool | None = None
    # "servico" | "produto" | "ambos" — restringe o que pode ser lançado nesta
    # conta em Financeiro > Contas a pagar/a receber (ver FormFinanceiro).
    natureza: str | None = None


@router.post("/plano-contas")
def criar_conta_gerencial(dados: PlanoContaGerencialIn, session: Session = Depends(get_session)) -> dict:
    codigo = dados.codigo.strip()
    if not codigo or not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Código e nome são obrigatórios")
    if session.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.codigo == codigo)).first():
        raise HTTPException(status_code=409, detail="Já existe uma conta gerencial com esse código")
    campos = {**dados.model_dump(), "codigo": codigo}
    # Item de "3.01.01 - Alimentação do rebanho" já nasce marcado para o RMCA
    # (custo de alimentação), a menos que o usuário tenha desmarcado no formulário.
    if codigo.startswith("3.01.01") and dados.rmca_custo_alimentacao is None:
        campos["rmca_custo_alimentacao"] = True
    conta = PlanoContaGerencial(**campos)
    session.add(conta)
    session.commit()
    session.refresh(conta)
    return conta.model_dump()


@router.put("/plano-contas/{conta_id}")
def atualizar_conta_gerencial(conta_id: int, dados: PlanoContaGerencialIn, session: Session = Depends(get_session)) -> dict:
    conta = session.get(PlanoContaGerencial, conta_id)
    if not conta:
        raise HTTPException(status_code=404, detail="Conta gerencial não encontrada")
    for campo, valor in dados.model_dump().items():
        setattr(conta, campo, valor)
    session.add(conta)
    session.commit()
    session.refresh(conta)
    return conta.model_dump()


@router.get("/rmca")
def rmca(
    data_inicio: date = Query(..., description="Data inicial (competência)"),
    data_fim: date = Query(..., description="Data final (competência)"),
    session: Session = Depends(get_session),
) -> dict:
    """
    Indicador RMCA (Receita Menos Custo com Alimentação), em duas versões
    lado a lado: "gerencial" (soma dos lançamentos financeiros pelas contas
    marcadas em Configurações > Parâmetros financeiros) e "físico" (receita
    igual, mas custo a partir do consumo real registrado pela Alimentação em
    MovimentoEstoque × valor unitário do item no Estoque).
    """
    plano = session.exec(select(PlanoContaGerencial)).all()
    codigos_receita = {c.codigo for c in plano if c.rmca_receita_leite}
    codigos_custo = {c.codigo for c in plano if c.rmca_custo_alimentacao}

    itens = [
        it.model_dump() for it in session.exec(select(LancamentoItem)).all()
        if it.data_competencia and data_inicio <= it.data_competencia <= data_fim
    ]
    gerencial = calcular_rmca_gerencial(itens, codigos_receita, codigos_custo)

    movimentos = [
        m.model_dump() for m in session.exec(select(MovimentoEstoque)).all()
        if m.movimento == "Saída de ajuste" and data_inicio <= m.data_movimento <= data_fim
    ]
    estoque_por_nome = {e.nome: e.model_dump() for e in session.exec(select(Estoque)).all()}
    fisico = calcular_custo_fisico(movimentos, estoque_por_nome)

    return {
        "periodo": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()},
        "configurado": bool(codigos_receita) and bool(codigos_custo),
        "contas_receita": sorted(c.nome for c in plano if c.codigo in codigos_receita),
        "contas_custo": sorted(c.nome for c in plano if c.codigo in codigos_custo),
        "gerencial": gerencial,
        "fisico": {
            "receita_leite": gerencial["receita_leite"],
            "custo_alimentacao": fisico["custo_total"],
            "rmca": round(gerencial["receita_leite"] - fisico["custo_total"], 2),
            "itens": fisico["itens"],
        },
    }


@router.get("/custo-litro-leite")
def custo_litro_leite(
    data_inicio: date = Query(..., description="Data inicial (competência)"),
    data_fim: date = Query(..., description="Data final (competência)"),
    session: Session = Depends(get_session),
) -> dict:
    """
    Custo por litro de leite — total gasto com alimentação no período (as
    mesmas contas marcadas em Configurações > Parâmetros financeiros para o
    custo do RMCA) dividido pelos litros de leite entregues no período
    (Entrega mensal do leite), projetados proporcionalmente por dia quando o
    período não cobre o mês inteiro.
    """
    plano = session.exec(select(PlanoContaGerencial)).all()
    codigos_custo = {c.codigo for c in plano if c.rmca_custo_alimentacao}

    itens = [
        it.model_dump() for it in session.exec(select(LancamentoItem)).all()
        if it.data_competencia and data_inicio <= it.data_competencia <= data_fim
    ]
    custo_total = round(sum(i["valor_total"] or 0 for i in itens if i["codigo_conta_gerencial"] in codigos_custo), 2)

    entregas = {e.competencia: e.quantidade_litros for e in session.exec(select(EntregaLeiteMensal)).all()}
    litros = litros_leite_no_periodo(entregas, data_inicio, data_fim)

    return {
        "periodo": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()},
        "configurado": bool(codigos_custo),
        "tem_entrega": bool(entregas),
        "contas_custo": sorted(c.nome for c in plano if c.codigo in codigos_custo),
        **calcular_custo_por_litro(custo_total, litros),
    }


@router.get("/patrimonio")
def listar_patrimonio(session: Session = Depends(get_session)) -> dict:
    """Lista o patrimônio/imobilizado da fazenda (LISTA_DE_PATRIMONIO.csv),
    já com a depreciação linear calculada (valor atual = valor total menos a
    depreciação acumulada desde a imobilização)."""
    hoje = date.today()
    itens_raw = session.exec(select(Patrimonio)).all()
    itens: list[dict] = []
    inconsistencias: list[dict] = []
    valor_total_bruto = 0.0
    valor_atual_total = 0.0
    for i in itens_raw:
        d = i.model_dump()
        dep = calcular_depreciacao(d, hoje)
        d.update(dep)
        itens.append(d)
        if not i.data_baixa:
            valor_total_bruto += i.valor_total or 0
            valor_atual_total += dep["valor_atual"] or 0
        if dep["inconsistencia"]:
            inconsistencias.append({"item": i.nome, "numero": i.numero, "motivo": dep["inconsistencia"]})
    return {
        "itens": itens, "total": len(itens_raw),
        "valor_total": round(valor_total_bruto, 2),
        "valor_atual_total": round(valor_atual_total, 2),
        "inconsistencias": inconsistencias,
    }


@router.post("/lancamentos", status_code=201)
def criar_lancamento(dados: LancamentoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    """
    Cria um lançamento financeiro com um ou mais produtos/serviços (itens).
    Desconto/acréscimo ajustam o valor bruto dos itens para o valor líquido,
    que é o que efetivamente vira parcela(s). Sem data de pagamento, o
    lançamento nasce em aberto (contas a pagar/receber).
    """
    if dados.tipo not in ("receita", "despesa"):
        raise HTTPException(status_code=400, detail="tipo deve ser 'receita' ou 'despesa'")
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Informe ao menos um produto ou serviço")
    for item in dados.itens:
        if item.tipo_item is not None and item.tipo_item not in ("produto", "servico"):
            raise HTTPException(status_code=400, detail="tipo_item deve ser 'produto' ou 'servico'")

    valor_bruto = round(sum(i.valor_total for i in dados.itens), 2)
    valor_liquido = round(valor_bruto - (dados.desconto or 0) + (dados.acrescimo or 0), 2)
    if valor_liquido <= 0:
        raise HTTPException(status_code=400, detail="O valor líquido do lançamento deve ser positivo")

    ano = (dados.data_emissao or dados.data_competencia or date.today()).year
    numero_lancamento = _proximo_numero_lancamento(session, ano)
    data_competencia = dados.data_competencia or dados.data_emissao

    itens_criados = [
        LancamentoItem(
            numero_lancamento=numero_lancamento,
            tipo=dados.tipo,
            data_competencia=data_competencia,
            codigo_conta_gerencial=item.codigo_conta_gerencial,
            nome_conta_gerencial=item.nome_conta_gerencial,
            produto=item.produto,
            tipo_item=item.tipo_item,
            descricao=item.descricao,
            quantidade=item.quantidade,
            valor_unitario=item.valor_unitario,
            valor_total=item.valor_total,
        )
        for item in dados.itens
    ]

    # Resumo p/ os relatórios legados que só olham 1 conta/descrição por linha.
    descricao_resumo = ", ".join(i.produto for i in dados.itens)[:500]
    codigo_resumo = dados.itens[0].codigo_conta_gerencial if len(dados.itens) == 1 else None

    campos_comuns = dict(
        numero_lancamento=numero_lancamento,
        codigo_conta=codigo_resumo,
        descricao=descricao_resumo,
        centro_custo=mapear_centro_custo(dados.centro_custo),
        fornecedor_cliente=dados.fornecedor_cliente,
        responsavel=dados.responsavel,
        tipo_documento=dados.tipo_documento,
        numero_nota=dados.numero_documento,
        data_emissao=dados.data_emissao,
        data_competencia=data_competencia,
        data_prevista_entrada=dados.data_prevista_entrada,
        data_pedido=dados.data_pedido,
        entregue=dados.entregue,
        tipo=dados.tipo,
        origem="manual",
        desconto_nota=dados.desconto or None,
        acrescimo_nota=dados.acrescimo or None,
        pedido_id=dados.pedido_id,
        # Alguns fluxos (importação de CSV, lançamento via Telegram) chamam esta
        # função diretamente, fora do ciclo de requisição do FastAPI — nesses
        # casos `user` não é resolvido pela injeção de dependência e chega aqui
        # como o próprio sentinel Depends(...), não uma instância de Usuario.
        usuario_id=user.id if isinstance(user, Usuario) else None,
    )

    criados: list[ContaGerencial] = []
    if dados.parcelas:
        total_parcelas = len(dados.parcelas)
        for i, p in enumerate(dados.parcelas, start=1):
            criados.append(ContaGerencial(
                **campos_comuns,
                data_vencimento=p.data_vencimento,
                valor_total=p.valor,
                parcela_num=i,
                parcela_total=total_parcelas,
            ))
    else:
        registro = ContaGerencial(
            **campos_comuns,
            # Vencimento explícito do lançamento; se não vier, cai na data
            # prevista de entrada (comportamento antigo) e, por fim, na emissão.
            data_vencimento=dados.data_vencimento or dados.data_prevista_entrada or dados.data_emissao,
            valor_total=valor_liquido,
            parcela_num=1,
            parcela_total=1,
        )
        if dados.data_pagamento:
            registro.data_pagamento = dados.data_pagamento
            registro.valor_pago = dados.valor_pago
            registro.conta_bancaria = dados.conta_bancaria
            registro.numero_documento_pagamento = dados.numero_documento_pagamento
            registro.forma_pagamento = dados.forma_pagamento
            registro.desconto_acrescimo = round((dados.valor_pago or 0) - valor_liquido, 2)
        criados.append(registro)

    for it in itens_criados:
        session.add(it)
    for c in criados:
        session.add(c)
    session.commit()
    for c in criados:
        session.refresh(c)

    if dados.pedido_id:
        from fazenda.api.routers.pedidos import atualizar_status_por_lancamento
        atualizar_status_por_lancamento(session, dados.pedido_id, valor_liquido)

    return {
        "numero_lancamento": numero_lancamento,
        "ids": [c.id for c in criados],
        "valor_bruto": valor_bruto,
        "valor_liquido": valor_liquido,
    }


class LancamentoEditIn(BaseModel):
    """Edição dos campos descritivos/de valor de UMA conta gerencial (parcela).

    Todos os campos são opcionais — só os enviados são atualizados. Campos de
    pagamento (data_pagamento/valor_pago) não entram aqui: editar é
    independente de dar baixa, e uma conta já paga/recebida pode ser editada.
    """
    descricao: Optional[str] = None
    codigo_conta: Optional[str] = None
    centro_custo: Optional[str] = None
    fornecedor_cliente: Optional[str] = None
    numero_nota: Optional[str] = None
    numero_documento_pagamento: Optional[str] = None
    tipo_documento: Optional[str] = None
    data_emissao: Optional[date] = None
    data_vencimento: Optional[date] = None
    data_competencia: Optional[date] = None
    data_prevista_entrada: Optional[date] = None
    data_pedido: Optional[date] = None
    quantidade: Optional[float] = None
    valor_unitario: Optional[float] = None
    valor_total: Optional[float] = None
    desconto_acrescimo: Optional[float] = None
    responsavel: Optional[str] = None


@router.put("/lancamentos/{lancamento_id}/pagar")
def pagar_lancamento(lancamento_id: int, dados: PagamentoIn, session: Session = Depends(get_session)) -> dict:
    """Dá baixa (marca como pago/recebido) numa conta a pagar/a receber."""
    registro = session.get(ContaGerencial, lancamento_id)
    if not registro:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")

    if dados.forma_pagamento == "credito" and not dados.data_vencimento_cartao:
        raise HTTPException(status_code=400, detail="Informe a data de vencimento do cartão")

    registro.data_pagamento = dados.data_pagamento
    registro.valor_pago = dados.valor_pago
    registro.conta_bancaria = dados.conta_bancaria
    registro.numero_documento_pagamento = dados.numero_documento_pagamento
    registro.forma_pagamento = dados.forma_pagamento
    registro.data_vencimento_cartao = dados.data_vencimento_cartao if dados.forma_pagamento == "credito" else None
    registro.desconto_acrescimo = round(dados.valor_pago - (registro.valor_total or 0), 2)
    session.add(registro)
    session.commit()
    session.refresh(registro)
    return registro.model_dump()


@router.put("/lancamentos/baixa-lote")
def baixa_lote(dados: BaixaLoteIn, session: Session = Depends(get_session)) -> dict:
    """
    Dá baixa em vários lançamentos de uma vez, todos com o mesmo pagamento
    (data, conta corrente, forma de pagamento e nº de comprovante único) —
    cada lançamento é pago pelo próprio valor_total (sem desconto/acréscimo
    na baixa em lote; use a baixa individual para isso).
    """
    if not dados.lancamento_ids:
        raise HTTPException(status_code=400, detail="Selecione ao menos um lançamento")
    if dados.forma_pagamento == "credito" and not dados.data_vencimento_cartao:
        raise HTTPException(status_code=400, detail="Informe a data de vencimento do cartão")

    baixados = []
    nao_encontrados = []
    for lancamento_id in dados.lancamento_ids:
        registro = session.get(ContaGerencial, lancamento_id)
        if not registro:
            nao_encontrados.append(lancamento_id)
            continue
        registro.data_pagamento = dados.data_pagamento
        registro.valor_pago = registro.valor_total
        registro.desconto_acrescimo = 0.0
        registro.conta_bancaria = dados.conta_bancaria
        registro.forma_pagamento = dados.forma_pagamento
        registro.data_vencimento_cartao = dados.data_vencimento_cartao if dados.forma_pagamento == "credito" else None
        registro.numero_documento_pagamento = dados.numero_documento_pagamento
        session.add(registro)
        baixados.append(lancamento_id)

    session.commit()
    return {"baixados": len(baixados), "nao_encontrados": nao_encontrados}


@router.put("/lancamentos/baixa-lote-detalhada")
def baixa_lote_detalhada(dados: BaixaLoteDetalhadaIn, session: Session = Depends(get_session)) -> dict:
    """
    Dá baixa em várias notas de uma vez, mas cada uma com o SEU próprio
    pagamento (data, valor, conta, forma e comprovante) — permite pagar cada
    conta de forma diferente numa única operação. Valor diferente do total vira
    desconto/acréscimo (como na baixa individual).
    """
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Selecione ao menos um lançamento")
    for it in dados.itens:
        if it.forma_pagamento == "credito" and not it.data_vencimento_cartao:
            raise HTTPException(status_code=400, detail=f"Informe o vencimento do cartão do lançamento {it.lancamento_id}")

    baixados = []
    nao_encontrados = []
    for it in dados.itens:
        registro = session.get(ContaGerencial, it.lancamento_id)
        if not registro:
            nao_encontrados.append(it.lancamento_id)
            continue
        registro.data_pagamento = it.data_pagamento
        registro.valor_pago = it.valor_pago
        registro.desconto_acrescimo = round(it.valor_pago - (registro.valor_total or 0), 2)
        registro.conta_bancaria = it.conta_bancaria
        registro.forma_pagamento = it.forma_pagamento
        registro.data_vencimento_cartao = it.data_vencimento_cartao if it.forma_pagamento == "credito" else None
        registro.numero_documento_pagamento = it.numero_documento_pagamento
        session.add(registro)
        baixados.append(it.lancamento_id)

    session.commit()
    return {"baixados": len(baixados), "nao_encontrados": nao_encontrados}


# Definido DEPOIS de /baixa-lote de propósito: uma rota de segmento único como
# /lancamentos/{lancamento_id} capturaria "baixa-lote" e quebraria aquela rota.
@router.put("/lancamentos/{lancamento_id}")
def editar_lancamento(lancamento_id: int, dados: LancamentoEditIn, session: Session = Depends(get_session)) -> dict:
    """
    Edita os campos descritivos/de valor de UMA conta gerencial (uma parcela),
    identificada pelo seu id. Não mexe no pagamento — uma conta já paga/recebida
    também pode ser editada. Quando o lançamento é de parcela única e tem
    exatamente um item, espelha as mudanças no LancamentoItem para manter os
    relatórios por item (DRE/RMCA) coerentes.
    """
    registro = session.get(ContaGerencial, lancamento_id)
    if not registro:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")

    enviados = dados.model_dump(exclude_unset=True)
    for campo, valor in enviados.items():
        if campo == "centro_custo":
            registro.centro_custo = mapear_centro_custo(valor)
        else:
            setattr(registro, campo, valor)
    registro.atualizado_em = datetime.utcnow()
    session.add(registro)

    # Espelha no item quando é seguro (parcela única + 1 item), para relatórios
    # baseados em LancamentoItem (DRE/RMCA) ficarem consistentes.
    if registro.parcela_total == 1 and registro.numero_lancamento:
        itens = session.exec(
            select(LancamentoItem).where(LancamentoItem.numero_lancamento == registro.numero_lancamento)
        ).all()
        if len(itens) == 1:
            item = itens[0]
            if "descricao" in enviados:
                item.descricao = registro.descricao
            if "valor_total" in enviados:
                item.valor_total = registro.valor_total
            if "quantidade" in enviados:
                item.quantidade = registro.quantidade
            if "valor_unitario" in enviados:
                item.valor_unitario = registro.valor_unitario
            if "codigo_conta" in enviados:
                item.codigo_conta_gerencial = registro.codigo_conta
            session.add(item)

    session.commit()
    session.refresh(registro)
    return registro.model_dump()


@router.post("/importar-xml")
def importar_xml(dados: XmlIn) -> dict:
    """Extrai os campos de um XML de NF-e para pré-preencher o lançamento."""
    try:
        return parse_nfe_xml(dados.xml)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Não foi possível ler o XML: {e}")


@router.post("/ler-documento")
async def ler_documento_anexado(file: UploadFile) -> dict:
    """Lê um PDF/JPEG/PNG anexado (nota fiscal ou recibo) via IA e devolve os
    campos extraídos para pré-preencher o lançamento — tudo editável no front."""
    if file.content_type not in MIME_ACEITOS:
        raise HTTPException(status_code=400, detail=f"Tipo de arquivo não suportado: {file.content_type} (aceitos: PDF, JPEG, PNG)")
    conteudo = await file.read()
    try:
        return ler_documento(conteudo, file.content_type)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Não foi possível ler o documento: {e}")


@router.get("/contas-a-pagar")
def contas_a_pagar(
    dias: int = Query(10, description="Janela em dias"),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Retorna contas com vencimento nos próximos N dias (não quitadas)."""
    hoje = date.today()
    limite = hoje + __import__("datetime").timedelta(days=dias)

    contas = session.exec(select(ContaGerencial)).all()
    nomes_usuarios = mapa_usuarios(session, {c.usuario_id for c in contas})
    resultado = []
    for c in contas:
        if (
            c.data_vencimento
            and hoje <= c.data_vencimento <= limite
            and (c.valor_pago or 0) < (c.valor_total or 0)
            and c.tipo == "despesa"
        ):
            resultado.append({**c.model_dump(), "usuario_nome": nomes_usuarios.get(c.usuario_id)})

    return sorted(resultado, key=lambda x: x["data_vencimento"])
