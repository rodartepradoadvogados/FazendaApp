"""
Cadastro > Estoque — Fornecedores/fabricantes/clientes e metadados dos itens
de estoque (embalagem, fornecedor, sindicância com conta gerencial padrão).
Extraído do antigo `cadastro.py` monolítico.
"""
from __future__ import annotations

import unicodedata

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import Estoque, Fornecedor, PlanoContaGerencial, SeedFlag
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.api.routers.estoque import _validar_embalagem

router = APIRouter()

# ---------------------------------------------------------------------------
# Fornecedores / fabricantes / clientes
# ---------------------------------------------------------------------------
TIPOS_FORNECEDOR = ("fornecedor", "fabricante", "cliente", "corretor")


class FornecedorIn(BaseModel):
    nome: str
    tipo: str  # "fornecedor" | "fabricante" | "cliente" | "corretor"
    categoria: str | None = None
    cnpj_cpf: str | None = None
    telefone: str | None = None
    email: str | None = None
    observacoes: str | None = None
    ativo: bool = True


@router.get("/fornecedores")
def listar_fornecedores(
    fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Fornecedor)
    if fazenda_id is not None:
        query = query.where(Fornecedor.fazenda_id == fazenda_id)
    return [f.model_dump() for f in session.exec(query.order_by(Fornecedor.nome)).all()]


@router.post("/fornecedores")
def criar_fornecedor(
    dados: FornecedorIn, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if dados.tipo not in TIPOS_FORNECEDOR:
        raise HTTPException(status_code=400, detail="Tipo inválido")
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    f = Fornecedor(**dados.model_dump(), fazenda_id=fazenda_id)
    session.add(f)
    session.commit()
    session.refresh(f)
    return f.model_dump()


@router.put("/fornecedores/{fornecedor_id}")
def atualizar_fornecedor(fornecedor_id: int, dados: FornecedorIn, session: Session = Depends(get_session)) -> dict:
    if dados.tipo not in TIPOS_FORNECEDOR:
        raise HTTPException(status_code=400, detail="Tipo inválido")
    f = session.get(Fornecedor, fornecedor_id)
    if not f:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado")
    for campo, valor in dados.model_dump().items():
        setattr(f, campo, valor)
    session.add(f)
    session.commit()
    session.refresh(f)
    return f.model_dump()



# ---------------------------------------------------------------------------
# Sindicância automática: vincula cada item de estoque à sua conta gerencial
# padrão de despesa, a partir da finalidade do item — roda uma única vez
# (SeedFlag), sem nunca sobrescrever um vínculo já feito manualmente.
# ---------------------------------------------------------------------------
_PALAVRAS_CHAVE_FINALIDADE = {
    "Ração/Alimento": ["aliment"],
    "Medicamento": ["sanidade", "medicamento", "veterinar"],
    "Material/Insumo": ["insumo", "material"],
    "Equipamento": ["equipamento"],
}


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def sindicar_conta_gerencial_estoque(session: Session) -> None:
    """Para cada item de estoque sem `conta_gerencial_despesa_padrao`, tenta
    achar a conta gerencial correspondente a partir da `finalidade` do item
    (ver rules.categorias.FINALIDADES_ESTOQUE): "Ração/Alimento" vai para a
    conta "3.01.01" (Alimentação do rebanho) quando ela existir; as demais
    finalidades (e o fallback de Ração/Alimento, se "3.01.01" não existir
    ainda) são casadas por palavra-chave no nome da conta. "Outro" e itens
    sem finalidade definida ficam de fora — precisam de escolha manual.
    Nunca sobrescreve um vínculo já existente. Roda uma única vez; depois
    disso o cadastro/edição do item escolhe a conta gerencial no formulário."""
    chave = "estoque_conta_gerencial_padrao_202607"
    if session.get(SeedFlag, chave):
        return
    contas = session.exec(select(PlanoContaGerencial)).all()
    itens = session.exec(select(Estoque).where(Estoque.conta_gerencial_despesa_padrao.is_(None))).all()
    for item in itens:
        finalidade = item.finalidade
        if not finalidade or finalidade == "Outro":
            continue
        conta = None
        if finalidade == "Ração/Alimento":
            conta = next((c for c in contas if c.codigo == "3.01.01"), None)
        if conta is None:
            palavras = _PALAVRAS_CHAVE_FINALIDADE.get(finalidade, [])
            conta = next((c for c in contas if any(p in _sem_acento(c.nome) for p in palavras)), None)
        if conta:
            item.conta_gerencial_despesa_padrao = conta.codigo
            session.add(item)
    session.add(SeedFlag(chave=chave))
    session.commit()


# ---------------------------------------------------------------------------
# Metadados de itens de estoque — embalagem (usada pela Alimentação para
# converter kg necessários em sacos/potes/fardos) e fornecedor principal do
# item. A quantidade em si continua vindo do ESTOQUE.csv / movimentações;
# aqui só descrevemos o item.
# ---------------------------------------------------------------------------
class EstoqueMetaIn(BaseModel):
    unidade_embalagem: str | None = None
    medida_embalagem: str | None = None
    quantidade_embalagem: float | None = None
    fornecedor_id: int | None = None
    estocavel: bool | None = None
    principio_ativo: str | None = None
    principio_ativo_id: int | None = None
    classificacao_medicamento: str | None = None
    # Vínculo com um touro do Estoque de Sêmen — ver `Estoque.estoque_semen_id`.
    estoque_semen_id: int | None = None
    conta_gerencial_despesa_padrao: str | None = None


@router.get("/estoque-itens")
def listar_itens_estoque(
    fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_fornecedor = select(Fornecedor)
    query_estoque = select(Estoque)
    if fazenda_id is not None:
        query_fornecedor = query_fornecedor.where(Fornecedor.fazenda_id == fazenda_id)
        query_estoque = query_estoque.where(Estoque.fazenda_id == fazenda_id)
    fornecedores = {f.id: f.nome for f in session.exec(query_fornecedor).all()}
    return [
        {**e.model_dump(), "fornecedor_nome": fornecedores.get(e.fornecedor_id)}
        for e in session.exec(query_estoque.order_by(Estoque.nome)).all()
    ]


@router.put("/estoque-itens/{item_id}")
def atualizar_meta_estoque(item_id: int, dados: EstoqueMetaIn, session: Session = Depends(get_session)) -> dict:
    item = session.get(Estoque, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item de estoque não encontrado")
    if dados.fornecedor_id is not None and not session.get(Fornecedor, dados.fornecedor_id):
        raise HTTPException(status_code=400, detail="Fornecedor não encontrado")
    _validar_embalagem(dados.unidade_embalagem, dados.medida_embalagem)
    item.unidade_embalagem = dados.unidade_embalagem
    item.medida_embalagem = dados.medida_embalagem
    item.quantidade_embalagem = dados.quantidade_embalagem
    item.fornecedor_id = dados.fornecedor_id
    item.estocavel = dados.estocavel
    item.principio_ativo = dados.principio_ativo
    item.principio_ativo_id = dados.principio_ativo_id
    item.classificacao_medicamento = dados.classificacao_medicamento
    item.estoque_semen_id = dados.estoque_semen_id
    item.conta_gerencial_despesa_padrao = dados.conta_gerencial_despesa_padrao
    session.add(item)
    session.commit()
    session.refresh(item)
    return item.model_dump()




