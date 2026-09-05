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
    CategoriaEstoque, CategoriaMedicamento, ClassificacaoMedicamento, Estoque, EstoqueSemen, FinalidadeEstoque,
    Fornecedor, Laboratorio, LocalArmazenamento, PlanoContaGerencial, SeedFlag, UnidadeEmbalagemEstoque,
    UnidadeEstoque, UnidadeMedidaEmbalagemEstoque,
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
#
# Categoria/Finalidade/Unidade/Unidade de embalagem/Unidade de medida de
# embalagem são CATÁLOGO GLOBAL (`global_compartilhado=True` abaixo — mesmo
# padrão de Laboratorio/CategoriaMedicamento/PrincipioAtivo/Doenca, ver
# `_comum.py::_crud_nome_ativo` e `rules/visibilidade.py::visivel`): a
# listagem enxerga a global MAIS a própria; criar sempre nasce com
# fazenda_id da fazenda atual (personalização por cima do padrão), nunca
# global — só o Painel CowData cria linha global. Local de Armazenamento
# fica de fora disso: é dado DA FAZENDA (nasce do texto livre já digitado
# em Estoque/EstoqueSemen, nunca teve lista padrão), então continua
# `com_fazenda=True` simples (filtro estrito), sem `global_compartilhado`.
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


def _seed_catalogo_global(session: Session, model, nomes: list[str]) -> None:
    """Semeia `nomes` como linhas GLOBAIS (`fazenda_id` nulo) de `model`,
    idempotente por NOME entre as linhas já globais — nunca pelo "a tabela
    inteira está vazia" (bug real de produção: rodava só a primeira vez pro
    banco inteiro, então a 2ª fazenda cadastrada abria o cadastro de
    estoque e encontrava tudo em branco, sem erro nenhum). Cada fazenda
    continua livre pra criar as suas por cima (personalização), sem nunca
    tocar nas globais — mesmo modelo já usado por PrincipioAtivo/Doenca."""
    existentes = {
        m.nome for m in session.exec(select(model).where(model.fazenda_id.is_(None))).all()
    }
    for nome in nomes:
        if nome not in existentes:
            session.add(model(nome=nome, fazenda_id=None))


def _seed_locais_armazenamento(session: Session) -> None:
    """Local de armazenamento é DADO DA FAZENDA, não catálogo (não tem lista
    padrão — nasce só do texto livre já digitado em Estoque/EstoqueSemen).
    Por isso, ao contrário dos 5 catálogos acima, cada nome nasce com o
    MESMO `fazenda_id` do item de estoque de onde veio (nunca global) —
    idempotente por (nome, fazenda_id), o par que a unique constraint da
    tabela já protege."""
    pares: set[tuple[str, int | None]] = set()
    for e in session.exec(select(Estoque)).all():
        if e.local_armazenamento and e.local_armazenamento.strip():
            pares.add((e.local_armazenamento.strip(), e.fazenda_id))
    for e in session.exec(select(EstoqueSemen)).all():
        if e.local_armazenamento and e.local_armazenamento.strip():
            pares.add((e.local_armazenamento.strip(), e.fazenda_id))
    if not pares:
        return
    existentes = {(l.nome, l.fazenda_id) for l in session.exec(select(LocalArmazenamento)).all()}
    for nome, fazenda_id in sorted(pares, key=lambda p: (p[0], p[1] if p[1] is not None else -1)):
        if (nome, fazenda_id) not in existentes:
            session.add(LocalArmazenamento(nome=nome, fazenda_id=fazenda_id))


def seed_cadastros_estoque(session: Session) -> None:
    """Cadastros de apoio ao item de estoque (Configurações > Cadastro >
    Estoque). Dois grupos bem diferentes aqui (decisão do dono do produto,
    04/09/2026, depois do bug real de "2ª fazenda abre o cadastro e acha
    tudo vazio" — ver `_seed_catalogo_global`):

    - Categoria/Finalidade/Unidade/Unidade de embalagem/Unidade de medida de
      embalagem: CATÁLOGO GLOBAL (`fazenda_id` nulo = padrão de todo mundo),
      mesmo modelo de PrincipioAtivo/Doenca — cada fazenda pode criar as
      suas por cima, mas a lista padrão nunca é atribuída a uma fazenda
      específica (isso a faria sumir pra qualquer cliente futuro).
    - Local de armazenamento: dado DA FAZENDA (texto livre já digitado em
      Estoque/EstoqueSemen) — nunca global, ver `_seed_locais_armazenamento`.
    """
    _seed_catalogo_global(session, CategoriaEstoque, SEED_CATEGORIAS_ESTOQUE)
    _seed_catalogo_global(session, FinalidadeEstoque, SEED_FINALIDADES_ESTOQUE)
    _seed_catalogo_global(session, UnidadeEstoque, SEED_UNIDADES_ESTOQUE)
    _seed_catalogo_global(session, UnidadeEmbalagemEstoque, SEED_UNIDADES_EMBALAGEM_ESTOQUE)
    _seed_catalogo_global(session, UnidadeMedidaEmbalagemEstoque, SEED_UNIDADES_MEDIDA_EMBALAGEM_ESTOQUE)
    _seed_locais_armazenamento(session)
    session.commit()


_listar_locais_armazenamento, _criar_local_armazenamento, _atualizar_local_armazenamento, _excluir_local_armazenamento = _crud_nome_ativo(LocalArmazenamento, com_fazenda=True)
router.get("/locais-armazenamento")(_listar_locais_armazenamento)
router.post("/locais-armazenamento")(_criar_local_armazenamento)
router.put("/locais-armazenamento/{item_id}")(_atualizar_local_armazenamento)
router.delete("/locais-armazenamento/{item_id}")(_excluir_local_armazenamento)

_listar_categorias_estoque, _criar_categoria_estoque, _atualizar_categoria_estoque, _excluir_categoria_estoque = _crud_nome_ativo(CategoriaEstoque, com_fazenda=True, global_compartilhado=True)
router.get("/categorias-estoque")(_listar_categorias_estoque)
router.post("/categorias-estoque")(_criar_categoria_estoque)
router.put("/categorias-estoque/{item_id}")(_atualizar_categoria_estoque)
router.delete("/categorias-estoque/{item_id}")(_excluir_categoria_estoque)

_listar_finalidades_estoque, _criar_finalidade_estoque, _atualizar_finalidade_estoque, _excluir_finalidade_estoque = _crud_nome_ativo(FinalidadeEstoque, com_fazenda=True, global_compartilhado=True)
router.get("/finalidades-estoque")(_listar_finalidades_estoque)
router.post("/finalidades-estoque")(_criar_finalidade_estoque)
router.put("/finalidades-estoque/{item_id}")(_atualizar_finalidade_estoque)
router.delete("/finalidades-estoque/{item_id}")(_excluir_finalidade_estoque)

_listar_unidades_estoque, _criar_unidade_estoque, _atualizar_unidade_estoque, _excluir_unidade_estoque = _crud_nome_ativo(UnidadeEstoque, com_fazenda=True, global_compartilhado=True)
router.get("/unidades-estoque")(_listar_unidades_estoque)
router.post("/unidades-estoque")(_criar_unidade_estoque)
router.put("/unidades-estoque/{item_id}")(_atualizar_unidade_estoque)
router.delete("/unidades-estoque/{item_id}")(_excluir_unidade_estoque)

_listar_unidades_embalagem_estoque, _criar_unidade_embalagem_estoque, _atualizar_unidade_embalagem_estoque, _excluir_unidade_embalagem_estoque = _crud_nome_ativo(UnidadeEmbalagemEstoque, com_fazenda=True, global_compartilhado=True)
router.get("/unidades-embalagem-estoque")(_listar_unidades_embalagem_estoque)
router.post("/unidades-embalagem-estoque")(_criar_unidade_embalagem_estoque)
router.put("/unidades-embalagem-estoque/{item_id}")(_atualizar_unidade_embalagem_estoque)
router.delete("/unidades-embalagem-estoque/{item_id}")(_excluir_unidade_embalagem_estoque)

_listar_unidades_medida_embalagem_estoque, _criar_unidade_medida_embalagem_estoque, _atualizar_unidade_medida_embalagem_estoque, _excluir_unidade_medida_embalagem_estoque = _crud_nome_ativo(UnidadeMedidaEmbalagemEstoque, com_fazenda=True, global_compartilhado=True)
router.get("/unidades-medida-embalagem-estoque")(_listar_unidades_medida_embalagem_estoque)
router.post("/unidades-medida-embalagem-estoque")(_criar_unidade_medida_embalagem_estoque)
router.put("/unidades-medida-embalagem-estoque/{item_id}")(_atualizar_unidade_medida_embalagem_estoque)
router.delete("/unidades-medida-embalagem-estoque/{item_id}")(_excluir_unidade_medida_embalagem_estoque)

# Laboratório / Categoria (medicamento) / Classificação do medicamento — mesmo
# padrão dos cadastros acima, mas `global_compartilhado=True` (ver _comum.py):
# o que o Painel CowData cadastra em /painel-cowdata/farmacia/{laboratorios,
# categorias-medicamento,classificacoes-medicamento} vira padrão automático
# aqui, sem precisar recadastrar por fazenda (pedido do usuário, 01/09/2026).
_listar_laboratorios, _criar_laboratorio, _atualizar_laboratorio, _ = _crud_nome_ativo(Laboratorio, com_fazenda=True, global_compartilhado=True)
router.get("/laboratorios")(_listar_laboratorios)
router.post("/laboratorios")(_criar_laboratorio)
router.put("/laboratorios/{item_id}")(_atualizar_laboratorio)

_listar_categorias_medicamento, _criar_categoria_medicamento, _atualizar_categoria_medicamento, _ = _crud_nome_ativo(CategoriaMedicamento, com_fazenda=True, global_compartilhado=True)
router.get("/categorias-medicamento")(_listar_categorias_medicamento)
router.post("/categorias-medicamento")(_criar_categoria_medicamento)
router.put("/categorias-medicamento/{item_id}")(_atualizar_categoria_medicamento)

_listar_classificacoes_medicamento, _criar_classificacao_medicamento, _atualizar_classificacao_medicamento, _ = _crud_nome_ativo(ClassificacaoMedicamento, com_fazenda=True, global_compartilhado=True)
router.get("/classificacoes-medicamento")(_listar_classificacoes_medicamento)
router.post("/classificacoes-medicamento")(_criar_classificacao_medicamento)
router.put("/classificacoes-medicamento/{item_id}")(_atualizar_classificacao_medicamento)
