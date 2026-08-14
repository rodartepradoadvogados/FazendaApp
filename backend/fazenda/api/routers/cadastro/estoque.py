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

from fazenda.auth import get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    CategoriaEstoque, Estoque, EstoqueSemen, FinalidadeEstoque, Fornecedor, LocalArmazenamento, PlanoContaGerencial,
    SeedFlag, UnidadeEmbalagemEstoque, UnidadeEstoque, UnidadeMedidaEmbalagemEstoque,
)
from fazenda.rules.auditoria import fazenda_id_seguro
from ._comum import _crud_nome_ativo

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
    dados: FornecedorIn, fazenda_id: int = Depends(get_fazenda_id_escrita), session: Session = Depends(get_session),
) -> dict:
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
def atualizar_fornecedor(
    fornecedor_id: int, dados: FornecedorIn,
    fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    if dados.tipo not in TIPOS_FORNECEDOR:
        raise HTTPException(status_code=400, detail="Tipo inválido")
    f = session.get(Fornecedor, fornecedor_id)
    # 404 (e não 403) para fornecedor de outra fazenda — mesma convenção dos
    # demais IDOR já corrigidos (ver tests/test_isolamento_rotas_criticas.py):
    # não confirma nem desmente a existência do id para quem não é dono dele.
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not f or (fazenda_id is not None and f.fazenda_id != fazenda_id):
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
def atualizar_meta_estoque(
    item_id: int, dados: EstoqueMetaIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    item = session.get(Estoque, item_id)
    if not item or (fazenda_id is not None and item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Item de estoque não encontrado")
    if dados.fornecedor_id is not None and not session.get(Fornecedor, dados.fornecedor_id):
        raise HTTPException(status_code=400, detail="Fornecedor não encontrado")
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


# ---------------------------------------------------------------------------
# Cadastros de apoio ao item de estoque (Configurações > Cadastro > Estoque):
# Local de Armazenamento, Categoria, Finalidade, Unidade, Unidade (embalagem)
# e Unidade de Medida — antes listas fixas em Python/TypeScript ou texto
# livre sem sugestão (local_armazenamento), agora cadastráveis (mesmo padrão
# "nome + ativo" de Raça/MotivoBaixa, ver `_crud_nome_ativo`).
# ---------------------------------------------------------------------------
SEED_CATEGORIAS_ESTOQUE = [
    "Ração e insumos alimentares", "Sêmen e genética", "Medicamentos e produtos veterinários",
    "Equipamentos e manutenção", "Combustível e transporte", "Serviços veterinários/técnicos",
    "Energia e utilidades", "Embalagens e materiais", "Outros",
]
SEED_FINALIDADES_ESTOQUE = ["Medicamento", "Ração/Alimento", "Material/Insumo", "Equipamento", "Outro"]
SEED_UNIDADES_ESTOQUE = ["ml", "kg", "L", "unidade", "dose", "metro", "saca 30kg", "saca 60kg"]
SEED_UNIDADES_EMBALAGEM_ESTOQUE = ["Saca", "Pote", "Frasco", "Pacote", "Bag", "Fardo", "Garrafa", "Unidade"]
SEED_UNIDADES_MEDIDA_EMBALAGEM_ESTOQUE = ["kg/saca", "litros/garrafa", "mililitros/frasco", "unidades/fardo", "potes/caixa", "unidades"]


def seed_cadastros_estoque(session: Session) -> None:
    """Cria os cadastros de apoio ao item de estoque padrão (categoria,
    finalidade, unidade, unidade de embalagem, unidade de medida) se as
    tabelas ainda estiverem vazias (idempotente) — mesma lista que já era
    hardcoded em CATEGORIAS_ESTOQUE/FINALIDADES_ESTOQUE/UNIDADES/etc, agora
    cadastrável e editável em Configurações > Cadastro > Estoque.
    Local de armazenamento não tem lista padrão — semeado a partir dos
    valores já digitados em Estoque/EstoqueSemen (auto-preenche o cadastro
    com o que o usuário já vinha usando como texto livre)."""
    if not session.exec(select(CategoriaEstoque)).first():
        for nome in SEED_CATEGORIAS_ESTOQUE:
            session.add(CategoriaEstoque(nome=nome))
    if not session.exec(select(FinalidadeEstoque)).first():
        for nome in SEED_FINALIDADES_ESTOQUE:
            session.add(FinalidadeEstoque(nome=nome))
    if not session.exec(select(UnidadeEstoque)).first():
        for nome in SEED_UNIDADES_ESTOQUE:
            session.add(UnidadeEstoque(nome=nome))
    if not session.exec(select(UnidadeEmbalagemEstoque)).first():
        for nome in SEED_UNIDADES_EMBALAGEM_ESTOQUE:
            session.add(UnidadeEmbalagemEstoque(nome=nome))
    if not session.exec(select(UnidadeMedidaEmbalagemEstoque)).first():
        for nome in SEED_UNIDADES_MEDIDA_EMBALAGEM_ESTOQUE:
            session.add(UnidadeMedidaEmbalagemEstoque(nome=nome))
    if not session.exec(select(LocalArmazenamento)).first():
        nomes = {e.local_armazenamento.strip() for e in session.exec(select(Estoque)).all() if e.local_armazenamento and e.local_armazenamento.strip()}
        nomes |= {e.local_armazenamento.strip() for e in session.exec(select(EstoqueSemen)).all() if e.local_armazenamento and e.local_armazenamento.strip()}
        for nome in sorted(nomes):
            session.add(LocalArmazenamento(nome=nome))
    session.commit()


_listar_locais_armazenamento, _criar_local_armazenamento, _atualizar_local_armazenamento, _excluir_local_armazenamento = _crud_nome_ativo(LocalArmazenamento, com_fazenda=True)
router.get("/locais-armazenamento")(_listar_locais_armazenamento)
router.post("/locais-armazenamento")(_criar_local_armazenamento)
router.put("/locais-armazenamento/{item_id}")(_atualizar_local_armazenamento)
router.delete("/locais-armazenamento/{item_id}")(_excluir_local_armazenamento)

_listar_categorias_estoque, _criar_categoria_estoque, _atualizar_categoria_estoque, _excluir_categoria_estoque = _crud_nome_ativo(CategoriaEstoque, com_fazenda=True)
router.get("/categorias-estoque")(_listar_categorias_estoque)
router.post("/categorias-estoque")(_criar_categoria_estoque)
router.put("/categorias-estoque/{item_id}")(_atualizar_categoria_estoque)
router.delete("/categorias-estoque/{item_id}")(_excluir_categoria_estoque)

_listar_finalidades_estoque, _criar_finalidade_estoque, _atualizar_finalidade_estoque, _excluir_finalidade_estoque = _crud_nome_ativo(FinalidadeEstoque, com_fazenda=True)
router.get("/finalidades-estoque")(_listar_finalidades_estoque)
router.post("/finalidades-estoque")(_criar_finalidade_estoque)
router.put("/finalidades-estoque/{item_id}")(_atualizar_finalidade_estoque)
router.delete("/finalidades-estoque/{item_id}")(_excluir_finalidade_estoque)

_listar_unidades_estoque, _criar_unidade_estoque, _atualizar_unidade_estoque, _excluir_unidade_estoque = _crud_nome_ativo(UnidadeEstoque, com_fazenda=True)
router.get("/unidades-estoque")(_listar_unidades_estoque)
router.post("/unidades-estoque")(_criar_unidade_estoque)
router.put("/unidades-estoque/{item_id}")(_atualizar_unidade_estoque)
router.delete("/unidades-estoque/{item_id}")(_excluir_unidade_estoque)

_listar_unidades_embalagem_estoque, _criar_unidade_embalagem_estoque, _atualizar_unidade_embalagem_estoque, _excluir_unidade_embalagem_estoque = _crud_nome_ativo(UnidadeEmbalagemEstoque, com_fazenda=True)
router.get("/unidades-embalagem-estoque")(_listar_unidades_embalagem_estoque)
router.post("/unidades-embalagem-estoque")(_criar_unidade_embalagem_estoque)
router.put("/unidades-embalagem-estoque/{item_id}")(_atualizar_unidade_embalagem_estoque)
router.delete("/unidades-embalagem-estoque/{item_id}")(_excluir_unidade_embalagem_estoque)

_listar_unidades_medida_embalagem_estoque, _criar_unidade_medida_embalagem_estoque, _atualizar_unidade_medida_embalagem_estoque, _excluir_unidade_medida_embalagem_estoque = _crud_nome_ativo(UnidadeMedidaEmbalagemEstoque, com_fazenda=True)
router.get("/unidades-medida-embalagem-estoque")(_listar_unidades_medida_embalagem_estoque)
router.post("/unidades-medida-embalagem-estoque")(_criar_unidade_medida_embalagem_estoque)
router.put("/unidades-medida-embalagem-estoque/{item_id}")(_atualizar_unidade_medida_embalagem_estoque)
router.delete("/unidades-medida-embalagem-estoque/{item_id}")(_excluir_unidade_medida_embalagem_estoque)
