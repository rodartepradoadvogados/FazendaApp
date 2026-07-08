"""
Router de Importar dados (Configurações > Importar dados) — CSV manual e
simplificado para as categorias que não têm um parser rico do Ideagri.

Efetividade: cada linha é processada chamando a MESMA função que já grava de
verdade quando o usuário lança manualmente pela tela (criar_pesagens,
criar_lancamento, movimentar_estoque) ou grava direto nas mesmas tabelas
reais (Estoque, Fornecedor) usadas em todo o site — nunca numa tabela à
parte. As categorias que já têm parser rico do Ideagri (animais,
reprodutivo, produção, sanidade) continuam em POST /upload/{tipo}; aqui só
listamos seus modelos para aparecerem lado a lado na mesma tela.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlmodel import Session, select

from fazenda.api.routers.estoque import MovimentoIn, movimentar_estoque
from fazenda.api.routers.financeiro import ItemIn, LancamentoIn, ParcelaIn, criar_lancamento
from fazenda.api.routers.producao import PesagensIn, PesoIn, criar_pesagens
from fazenda.database import get_session
from fazenda.models import Estoque, Fornecedor
from fazenda.parsers.utils import iter_csv_rows, parse_bool, parse_date, parse_float

router = APIRouter(prefix="/importar", tags=["importar"])

CATEGORIAS_NOVAS = {
    "pesagem": {
        "label": "Histórico de pesagem corporal",
        "colunas": ["numero_matriz", "data_pesagem (DD/MM/AAAA)", "peso_kg"],
    },
    "financeiro": {
        "label": "Financeiro simplificado (uma parcela à vista por linha)",
        "colunas": ["data (DD/MM/AAAA)", "tipo (receita/despesa)", "descricao", "valor", "fornecedor_cliente"],
    },
    "estoque_movimento": {
        "label": "Movimentação de estoque simplificada",
        "colunas": [
            "nome_item", "movimento (Aplicação/Saída de ajuste/Entrada de ajuste/Entrada de cortesia/Doação)",
            "quantidade", "unidade", "data_movimento (DD/MM/AAAA)", "observacao",
        ],
    },
    "produtos_estoque": {
        "label": "Cadastro de sêmen/medicamento/hormônio/alimento",
        "colunas": ["nome", "categoria", "unidade", "ensacado (Sim/Não)", "kg_por_saco", "fornecedor_nome"],
    },
    "fornecedores": {
        "label": "Fornecedores, fabricantes e clientes",
        "colunas": ["nome", "tipo (fornecedor/fabricante/cliente)", "cnpj_cpf", "telefone", "email"],
    },
}

# Categorias que já têm parser rico do Ideagri — seguem usando POST /upload/{tipo}.
CATEGORIAS_EXISTENTES = {
    "animais": {"label": "Animais / rebanho geral", "tipo_upload": "geral"},
    "reprodutivo": {"label": "Reprodutivo (serviços e partos)", "tipo_upload": "reprodutivo"},
    "producao_leiteira": {"label": "Produção / controle leiteiro", "tipo_upload": "controle_leiteiro"},
    "sanitario": {"label": "Sanitário", "tipo_upload": "sanidade"},
}


@router.get("/modelos")
def listar_modelos() -> dict:
    return {"novas": CATEGORIAS_NOVAS, "existentes": CATEGORIAS_EXISTENTES}


@router.post("/pesagem")
async def importar_pesagem(file: UploadFile, session: Session = Depends(get_session)) -> dict:
    content = await file.read()
    por_data: dict[date, list[PesoIn]] = {}
    erros: list[str] = []

    for i, row in enumerate(iter_csv_rows(content), start=2):
        numero = row.get("numero_matriz", "").strip()
        data = parse_date(row.get("data_pesagem", ""))
        peso = parse_float(row.get("peso_kg", ""))
        if not numero or not data or not peso:
            erros.append(f"Linha {i}: número, data e peso são obrigatórios")
            continue
        por_data.setdefault(data, []).append(PesoIn(numero_matriz=numero, peso_kg=peso))

    criados = 0
    for data, entradas in por_data.items():
        resultado = criar_pesagens(PesagensIn(data_pesagem=data, entradas=entradas), session)
        criados += resultado["criados"]
    return {"categoria": "pesagem", "criados": criados, "erros": erros}


@router.post("/financeiro")
async def importar_financeiro(file: UploadFile, session: Session = Depends(get_session)) -> dict:
    content = await file.read()
    criados = 0
    erros: list[str] = []

    for i, row in enumerate(iter_csv_rows(content), start=2):
        tipo = row.get("tipo", "").strip().lower()
        data = parse_date(row.get("data", ""))
        valor = parse_float(row.get("valor", ""))
        descricao = row.get("descricao", "").strip()
        if tipo not in ("receita", "despesa") or not data or not valor or not descricao:
            erros.append(f"Linha {i}: data, tipo (receita/despesa), descrição e valor são obrigatórios")
            continue
        try:
            dados = LancamentoIn(
                tipo=tipo,
                itens=[ItemIn(produto=descricao, valor_total=valor)],
                fornecedor_cliente=row.get("fornecedor_cliente", "").strip() or None,
                data_emissao=data,
                data_competencia=data,
                parcelas=[ParcelaIn(data_vencimento=data, valor=valor)],
            )
            criar_lancamento(dados, session)
            criados += 1
        except HTTPException as exc:
            erros.append(f"Linha {i}: {exc.detail}")

    return {"categoria": "financeiro", "criados": criados, "erros": erros}


@router.post("/estoque_movimento")
async def importar_estoque_movimento(file: UploadFile, session: Session = Depends(get_session)) -> dict:
    content = await file.read()
    criados = 0
    erros: list[str] = []

    for i, row in enumerate(iter_csv_rows(content), start=2):
        nome = row.get("nome_item", "").strip()
        movimento = row.get("movimento", "").strip()
        quantidade = parse_float(row.get("quantidade", ""))
        data_movimento = parse_date(row.get("data_movimento", ""))
        if not nome or not movimento or not quantidade or not data_movimento:
            erros.append(f"Linha {i}: item, movimento, quantidade e data são obrigatórios")
            continue
        try:
            dados = MovimentoIn(
                nome=nome, movimento=movimento, quantidade=quantidade,
                unidade=row.get("unidade", "").strip() or None,
                data_movimento=data_movimento,
                observacao=row.get("observacao", "").strip() or None,
            )
            movimentar_estoque(dados, session)
            criados += 1
        except HTTPException as exc:
            erros.append(f"Linha {i}: {exc.detail}")

    return {"categoria": "estoque_movimento", "criados": criados, "erros": erros}


@router.post("/produtos_estoque")
async def importar_produtos_estoque(file: UploadFile, session: Session = Depends(get_session)) -> dict:
    content = await file.read()
    criados, atualizados = 0, 0
    erros: list[str] = []

    for i, row in enumerate(iter_csv_rows(content), start=2):
        nome = row.get("nome", "").strip()
        if not nome:
            erros.append(f"Linha {i}: nome é obrigatório")
            continue

        fornecedor_id = None
        fornecedor_nome = row.get("fornecedor_nome", "").strip()
        if fornecedor_nome:
            fornecedor = session.exec(select(Fornecedor).where(Fornecedor.nome == fornecedor_nome)).first()
            if not fornecedor:
                erros.append(f"Linha {i}: fornecedor '{fornecedor_nome}' não encontrado — cadastre-o antes")
            else:
                fornecedor_id = fornecedor.id

        item = session.exec(select(Estoque).where(Estoque.nome == nome)).first()
        if not item:
            item = Estoque(nome=nome, categoria=row.get("categoria", "").strip() or None,
                            unidade=row.get("unidade", "").strip() or None, quantidade=0)
            criados += 1
        else:
            atualizados += 1
        item.ensacado = parse_bool(row.get("ensacado", ""))
        kg = parse_float(row.get("kg_por_saco", ""))
        if kg is not None:
            item.kg_por_saco = kg
        if fornecedor_id is not None:
            item.fornecedor_id = fornecedor_id
        session.add(item)

    session.commit()
    return {"categoria": "produtos_estoque", "criados": criados, "atualizados": atualizados, "erros": erros}


@router.post("/fornecedores")
async def importar_fornecedores(file: UploadFile, session: Session = Depends(get_session)) -> dict:
    content = await file.read()
    criados, atualizados = 0, 0
    erros: list[str] = []

    for i, row in enumerate(iter_csv_rows(content), start=2):
        nome = row.get("nome", "").strip()
        tipo = row.get("tipo", "").strip().lower()
        if not nome or tipo not in ("fornecedor", "fabricante", "cliente"):
            erros.append(f"Linha {i}: nome e tipo (fornecedor/fabricante/cliente) são obrigatórios")
            continue

        f = session.exec(select(Fornecedor).where(Fornecedor.nome == nome)).first()
        if not f:
            f = Fornecedor(nome=nome, tipo=tipo)
            criados += 1
        else:
            f.tipo = tipo
            atualizados += 1
        f.cnpj_cpf = row.get("cnpj_cpf", "").strip() or None
        f.telefone = row.get("telefone", "").strip() or None
        f.email = row.get("email", "").strip() or None
        session.add(f)

    session.commit()
    return {"categoria": "fornecedores", "criados": criados, "atualizados": atualizados, "erros": erros}
