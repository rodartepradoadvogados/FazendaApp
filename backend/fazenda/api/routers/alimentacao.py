"""
Router de alimentação — plano de dieta por lote, consumo diário estimado,
necessidade mensal (com conversão para sacos) e a baixa automática de
estoque (opção A: o sistema recalcula quantos dias se passaram desde a
última baixa e desconta o consumo acumulado de uma vez, sempre que a tela
é aberta — sem botão manual nem cron real).
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from fazenda.auth import get_current_user
from fazenda.database import get_session
from fazenda.models import (
    AlimentacaoEstado, Alimento, Animal, CategoriaAlimento, Dieta, DietaItemProgramado, DietaLancamento,
    DietaRegistroReal, Estoque, IngredienteMS, Lote, MovimentoEstoque, Usuario,
)
from fazenda.rules.alimentacao import calcular_consumo, calcular_necessidade_mensal, _codigo_grupo
from fazenda.rules.auditoria import mapa_usuarios
from fazenda.rules.farmacia import pode_baixar_estoque

# Nº de tratos por dia (fornecimentos). Hoje são 2.
NUM_TRATOS = 2

router = APIRouter(prefix="/alimentacao", tags=["alimentacao"])

# Alimentos do protocolo padrão — sugestão no lançamento; o campo aceita
# qualquer texto (inclusive itens do Estoque não listados aqui).
ALIMENTOS_PADRAO = [
    "Silagem", "Ração Teck Milk 24%", "Milk Proteico", "Ração Pré-parto", "Corte 21",
    "Ração Bezerro 1", "Ração Bezerro 2",
]


def _dietas_e_animais(session: Session) -> tuple[list[dict], list[dict]]:
    dietas = [d.model_dump() for d in session.exec(select(Dieta)).all()]
    animais = [
        a.model_dump() for a in session.exec(select(Animal).where(Animal.ativo == True)).all()  # noqa: E712
        if not a.eh_semen and a.sexo != "M"
    ]
    return dietas, animais


def _lotes_cadastro(session: Session) -> list[dict]:
    return [l.model_dump() for l in session.exec(select(Lote)).all()]


def _estoque_por_alimento(session: Session) -> tuple[dict[str, list[dict]], set[str]]:
    """Vínculo Alimento → Estoque (ver `Estoque.alimento_id`), chaveado pelo
    nome do Alimento normalizado (trim + minúsculas) — usado como segunda
    tentativa quando o nome do ingrediente do plano de dieta não casa
    diretamente com nenhum `Estoque.nome` (ver `calcular_necessidade_mensal`
    e `_dar_baixa_automatica`)."""
    alimentos = {a.id: a for a in session.exec(select(Alimento)).all()}
    por_alimento: dict[str, list[dict]] = {}
    for e in session.exec(select(Estoque).where(Estoque.alimento_id.is_not(None))).all():  # type: ignore[union-attr]
        alimento = alimentos.get(e.alimento_id)
        if not alimento:
            continue
        chave = alimento.nome.strip().lower()
        por_alimento.setdefault(chave, []).append(e.model_dump())
    cadastrados = {a.nome.strip().lower() for a in alimentos.values()}
    return por_alimento, cadastrados


def _dar_baixa_automatica(session: Session) -> dict:
    """
    Baixa automática de estoque por dias decorridos (opção A). Usa uma trava
    otimista (compare-and-swap) na linha única de AlimentacaoEstado: só quem
    conseguir avançar `ultima_data_deducao` de fato aplica a baixa — uma
    segunda requisição concorrente vê 0 linhas afetadas e não faz nada,
    evitando baixa duplicada quando dois usuários abrem a tela ao mesmo tempo.
    """
    hoje = date.today()
    estado = session.get(AlimentacaoEstado, 1)
    if not estado:
        # Primeiro acesso: cria a linha única de estado. Duas requisições
        # concorrentes podem cair aqui ao mesmo tempo — a segunda perde a
        # corrida na constraint de chave primária; trata como "já criada"
        # e segue sem tentar deduzir nada agora (não há baseline anterior).
        try:
            session.add(AlimentacaoEstado(id=1, ultima_data_deducao=hoje))
            session.commit()
        except IntegrityError:
            session.rollback()
        return {"dias_deduzidos": 0, "ultima_data_deducao": hoje.isoformat()}

    dias = (hoje - estado.ultima_data_deducao).days if estado.ultima_data_deducao else 0
    if dias <= 0:
        return {"dias_deduzidos": 0, "ultima_data_deducao": estado.ultima_data_deducao.isoformat()}

    resultado = session.execute(
        text("UPDATE alimentacao_estado SET ultima_data_deducao = :novo WHERE id = 1 AND ultima_data_deducao = :antigo"),
        {"novo": hoje.isoformat(), "antigo": estado.ultima_data_deducao.isoformat()},
    )
    session.commit()
    if resultado.rowcount == 0:
        # Outra requisição venceu a corrida e já processou essa janela de dias.
        atualizado = session.get(AlimentacaoEstado, 1)
        return {"dias_deduzidos": 0, "ultima_data_deducao": atualizado.ultima_data_deducao.isoformat()}

    dietas, animais = _dietas_e_animais(session)
    consumo_total = calcular_consumo(dietas, animais, _lotes_cadastro(session))["consumo_total"]
    estoque_por_alimento, _ = _estoque_por_alimento(session)

    itens_baixados = []
    for item in consumo_total:
        estoque_item = session.exec(select(Estoque).where(Estoque.nome == item["ingrediente"])).first()
        if not estoque_item:
            # Sem item de Estoque com o mesmo nome — tenta pelo vínculo via
            # cadastro de Alimento (mesma resolução usada na necessidade mensal).
            candidatos = estoque_por_alimento.get((item["ingrediente"] or "").strip().lower())
            if candidatos:
                estoque_item = session.get(Estoque, candidatos[0]["id"])
        if not estoque_item or not item["consumo_dia"] or estoque_item.estocavel is False:
            continue
        # Gatilho de comunicação: só deduz insumo cujo estoque inicial/primeira
        # compra já foi registrado (None = insumo legado, mantém comportamento).
        if not pode_baixar_estoque(estoque_item):
            continue
        baixa = round(item["consumo_dia"] * dias, 2)
        estoque_item.quantidade = round((estoque_item.quantidade or 0) - baixa, 2)
        if estoque_item.estoque_minimo is not None:
            estoque_item.abaixo_minimo = estoque_item.quantidade < estoque_item.estoque_minimo
        estoque_item.atualizado_em = datetime.utcnow()
        session.add(estoque_item)
        session.add(MovimentoEstoque(
            nome_item=estoque_item.nome, movimento="Saída de ajuste", quantidade=baixa,
            unidade=estoque_item.unidade, data_movimento=hoje,
            observacao=f"Baixa automática da Alimentação — {dias} dia(s) desde a última baixa",
        ))
        itens_baixados.append({"ingrediente": item["ingrediente"], "baixa": baixa})

    session.commit()
    return {"dias_deduzidos": dias, "ultima_data_deducao": hoje.isoformat(), "itens": itens_baixados}


@router.get("/")
def obter_alimentacao(session: Session = Depends(get_session)) -> dict:
    """Plano de dieta por lote cruzado com o efetivo atual → consumo/dia por ingrediente."""
    _dar_baixa_automatica(session)
    dietas, animais = _dietas_e_animais(session)
    return calcular_consumo(dietas, animais, _lotes_cadastro(session))


@router.get("/necessidade-mensal")
def necessidade_mensal(session: Session = Depends(get_session)) -> dict:
    """Projeção de 30 dias por ingrediente, convertida em sacos quando o item é ensacado."""
    _dar_baixa_automatica(session)
    dietas, animais = _dietas_e_animais(session)
    consumo_total = calcular_consumo(dietas, animais, _lotes_cadastro(session))["consumo_total"]
    estoque_por_nome = {e.nome: e.model_dump() for e in session.exec(select(Estoque)).all()}
    estoque_por_alimento, alimentos_cadastrados = _estoque_por_alimento(session)
    return {"itens": calcular_necessidade_mensal(consumo_total, estoque_por_nome, estoque_por_alimento, alimentos_cadastrados)}


@router.get("/estado-baixa")
def estado_baixa(session: Session = Depends(get_session)) -> dict:
    """Última data em que a baixa automática de estoque foi aplicada."""
    estado = session.get(AlimentacaoEstado, 1)
    return {"ultima_data_deducao": estado.ultima_data_deducao.isoformat() if estado and estado.ultima_data_deducao else None}


# ---------------------------------------------------------------------------
# Categorias de alimento (Configurações > Cadastro > Alimentação >
# Categorias) e cadastro de Alimento (...> Alimentos) — a camada que
# normaliza o vínculo com o Estoque em vez de depender do nome bater
# (ver `calcular_necessidade_mensal`/`_dar_baixa_automatica` acima).
# ---------------------------------------------------------------------------
CATEGORIAS_ALIMENTO_PADRAO = ["Volumoso", "Concentrado", "Mineral"]


def _seed_categorias_alimento(session: Session) -> None:
    existentes = {c.nome for c in session.exec(select(CategoriaAlimento)).all()}
    novas = [CategoriaAlimento(nome=nome) for nome in CATEGORIAS_ALIMENTO_PADRAO if nome not in existentes]
    if novas:
        session.add_all(novas)
        session.commit()


# Alimentos padrão + categoria sugerida — preenche o cadastro na primeira
# vez com os alimentos já usados pela fazenda (mesmos nomes de ALIMENTOS_PADRAO,
# para que o vínculo funcione de cara com dietas já lançadas) mais os
# exemplos adicionais pedidos explicitamente (silagens específicas, mineral).
# Cada alimento é ligado automaticamente a um item de Estoque de MESMO NOME,
# se existir um — do contrário fica "sem vínculo" até o usuário linkar.
_ALIMENTOS_PADRAO_CATEGORIA: list[tuple[str, str]] = [
    ("Silagem", "Volumoso"), ("Silagem de milho", "Volumoso"), ("Silagem de sorgo", "Volumoso"),
    ("Ração Teck Milk 24%", "Concentrado"), ("Milk Proteico", "Concentrado"), ("Corte 21", "Concentrado"),
    ("Ração Bezerro 1", "Concentrado"), ("Ração Bezerro 2", "Concentrado"),
    ("Ração Pré-parto", "Mineral"), ("Reprodução 80", "Mineral"),
]


def seed_alimentos(session: Session) -> None:
    """Idempotente — só cria o que ainda não existe (nunca sobrescreve edição
    manual). Chamado no startup (ver `main.py`)."""
    _seed_categorias_alimento(session)
    categorias = {c.nome: c.id for c in session.exec(select(CategoriaAlimento)).all()}
    existentes = {a.nome for a in session.exec(select(Alimento)).all()}
    estoque_por_nome = {e.nome.strip().lower(): e for e in session.exec(select(Estoque)).all()}
    novos = []
    for nome, categoria_nome in _ALIMENTOS_PADRAO_CATEGORIA:
        if nome in existentes:
            continue
        alimento = Alimento(nome=nome, categoria_alimento_id=categorias.get(categoria_nome))
        novos.append(alimento)
    if novos:
        session.add_all(novos)
        session.commit()
        for alimento in novos:
            session.refresh(alimento)
            item = estoque_por_nome.get(alimento.nome.strip().lower())
            if item and item.alimento_id is None:
                item.alimento_id = alimento.id
                session.add(item)
        session.commit()


@router.get("/categorias")
def listar_categorias_alimento(session: Session = Depends(get_session)) -> list[dict]:
    _seed_categorias_alimento(session)
    return [c.model_dump() for c in session.exec(select(CategoriaAlimento).order_by(CategoriaAlimento.nome)).all()]


class CategoriaAlimentoIn(BaseModel):
    nome: str
    ativo: bool = True


@router.post("/categorias", status_code=201)
def criar_categoria_alimento(dados: CategoriaAlimentoIn, session: Session = Depends(get_session)) -> dict:
    if session.exec(select(CategoriaAlimento).where(CategoriaAlimento.nome == dados.nome)).first():
        raise HTTPException(status_code=409, detail=f'Já existe uma categoria chamada "{dados.nome}"')
    cat = CategoriaAlimento(nome=dados.nome, ativo=dados.ativo)
    session.add(cat)
    session.commit()
    session.refresh(cat)
    return cat.model_dump()


@router.put("/categorias/{categoria_id}")
def atualizar_categoria_alimento(categoria_id: int, dados: CategoriaAlimentoIn, session: Session = Depends(get_session)) -> dict:
    cat = session.get(CategoriaAlimento, categoria_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    outra = session.exec(select(CategoriaAlimento).where(CategoriaAlimento.nome == dados.nome, CategoriaAlimento.id != categoria_id)).first()
    if outra:
        raise HTTPException(status_code=409, detail=f'Já existe uma categoria chamada "{dados.nome}"')
    cat.nome = dados.nome
    cat.ativo = dados.ativo
    session.add(cat)
    session.commit()
    return cat.model_dump()


@router.delete("/categorias/{categoria_id}")
def excluir_categoria_alimento(categoria_id: int, session: Session = Depends(get_session)) -> dict:
    cat = session.get(CategoriaAlimento, categoria_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    em_uso = session.exec(select(Alimento).where(Alimento.categoria_alimento_id == categoria_id)).first()
    if em_uso:
        raise HTTPException(status_code=409, detail=f'Categoria em uso pelo alimento "{em_uso.nome}" — mova ou exclua o(s) alimento(s) primeiro')
    session.delete(cat)
    session.commit()
    return {"ok": True}


def _serializar_alimento(session: Session, a: Alimento) -> dict:
    vinculados = session.exec(select(Estoque).where(Estoque.alimento_id == a.id)).all()
    return {**a.model_dump(), "estoque_vinculado": [e.model_dump() for e in vinculados]}


@router.get("/alimentos")
def listar_alimentos(session: Session = Depends(get_session)) -> list[dict]:
    return [_serializar_alimento(session, a) for a in session.exec(select(Alimento).order_by(Alimento.nome)).all()]


class AlimentoIn(BaseModel):
    nome: str
    categoria_alimento_id: int | None = None
    observacao: str | None = None
    ativo: bool = True
    # Itens de Estoque a vincular a este alimento — substitui o conjunto
    # anterior (ver `_vincular_estoque_ao_alimento`).
    estoque_ids: list[int] = []


def _vincular_estoque_ao_alimento(session: Session, alimento_id: int, estoque_ids: list[int]) -> None:
    """Substitui o conjunto de itens de Estoque vinculados a este Alimento
    pelos informados. Um item de Estoque só pode estar vinculado a UM
    alimento por vez (campo escalar `Estoque.alimento_id`) — vincular aqui
    "rouba" o vínculo de qualquer outro alimento que o item estivesse usando."""
    atuais = session.exec(select(Estoque).where(Estoque.alimento_id == alimento_id)).all()
    for e in atuais:
        if e.id not in estoque_ids:
            e.alimento_id = None
            session.add(e)
    for eid in estoque_ids:
        item = session.get(Estoque, eid)
        if item and item.alimento_id != alimento_id:
            item.alimento_id = alimento_id
            session.add(item)
    session.commit()


@router.post("/alimentos", status_code=201)
def criar_alimento(dados: AlimentoIn, session: Session = Depends(get_session)) -> dict:
    if session.exec(select(Alimento).where(Alimento.nome == dados.nome)).first():
        raise HTTPException(status_code=409, detail=f'Já existe um alimento chamado "{dados.nome}"')
    alimento = Alimento(
        nome=dados.nome, categoria_alimento_id=dados.categoria_alimento_id,
        observacao=dados.observacao, ativo=dados.ativo,
    )
    session.add(alimento)
    session.commit()
    session.refresh(alimento)
    _vincular_estoque_ao_alimento(session, alimento.id, dados.estoque_ids)
    return _serializar_alimento(session, alimento)


@router.put("/alimentos/{alimento_id}")
def atualizar_alimento(alimento_id: int, dados: AlimentoIn, session: Session = Depends(get_session)) -> dict:
    alimento = session.get(Alimento, alimento_id)
    if not alimento:
        raise HTTPException(status_code=404, detail="Alimento não encontrado")
    outro = session.exec(select(Alimento).where(Alimento.nome == dados.nome, Alimento.id != alimento_id)).first()
    if outro:
        raise HTTPException(status_code=409, detail=f'Já existe um alimento chamado "{dados.nome}"')
    alimento.nome = dados.nome
    alimento.categoria_alimento_id = dados.categoria_alimento_id
    alimento.observacao = dados.observacao
    alimento.ativo = dados.ativo
    alimento.atualizado_em = datetime.utcnow()
    session.add(alimento)
    session.commit()
    _vincular_estoque_ao_alimento(session, alimento_id, dados.estoque_ids)
    return _serializar_alimento(session, alimento)


@router.delete("/alimentos/{alimento_id}")
def excluir_alimento(alimento_id: int, session: Session = Depends(get_session)) -> dict:
    alimento = session.get(Alimento, alimento_id)
    if not alimento:
        raise HTTPException(status_code=404, detail="Alimento não encontrado")
    for e in session.exec(select(Estoque).where(Estoque.alimento_id == alimento_id)).all():
        e.alimento_id = None
        session.add(e)
    session.delete(alimento)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Lançamento de dieta (Lançamentos > Alimentação) — histórico por lote, com
# comparação entre o programado (nutricionista) e o real oferecido. Só uma
# dieta pode estar ativa (sem encerramento efetivo) por lote de cada vez.
# ---------------------------------------------------------------------------
@router.get("/alimentos-padrao")
def alimentos_padrao() -> list[str]:
    return ALIMENTOS_PADRAO


# % de matéria seca padrão por ingrediente (volumosos ~33%, concentrados ~88%);
# o usuário edita na aba Matéria seca.
_MS_PADRAO = {
    "Silagem": 33.24, "Ração Teck Milk 24%": 88.0, "Milk Proteico": 88.0, "Ração Pré-parto": 88.0,
    "Corte 21": 88.0, "Ração Bezerro 1": 88.0, "Ração Bezerro 2": 88.0,
}


def _seed_materia_seca(session: Session) -> None:
    from fazenda.models import IngredienteMS
    existentes = {i.nome for i in session.exec(select(IngredienteMS)).all()}
    novos = [IngredienteMS(nome=nome, ms_pct=_MS_PADRAO.get(nome)) for nome in ALIMENTOS_PADRAO if nome not in existentes]
    if novos:
        for n in novos:
            session.add(n)
        session.commit()


@router.get("/materia-seca")
def listar_materia_seca(session: Session = Depends(get_session)) -> list[dict]:
    """Lista de ingredientes padrão com seu % de matéria seca (editável)."""
    from fazenda.models import IngredienteMS
    _seed_materia_seca(session)
    itens = session.exec(select(IngredienteMS).order_by(IngredienteMS.nome)).all()
    return [i.model_dump() for i in itens]


class IngredienteMSIn(BaseModel):
    nome: str
    ms_pct: float | None = None


@router.put("/materia-seca")
def salvar_materia_seca(dados: IngredienteMSIn, session: Session = Depends(get_session)) -> dict:
    """Upsert do % de matéria seca de um ingrediente (cadastro/edição)."""
    from fazenda.models import IngredienteMS
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome do ingrediente é obrigatório")
    if dados.ms_pct is not None and not (0 < dados.ms_pct <= 100):
        raise HTTPException(status_code=400, detail="% de matéria seca deve ser maior que 0 e no máximo 100.")
    item = session.exec(select(IngredienteMS).where(IngredienteMS.nome == nome)).first()
    if not item:
        item = IngredienteMS(nome=nome)
    item.ms_pct = dados.ms_pct
    item.atualizado_em = datetime.utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    return item.model_dump()


def _seed_tabela_nutricional(session: Session) -> None:
    from fazenda.models import TabelaNutricionalProduto, TabelaNutricionalValor
    from fazenda.rules.tabela_nutricional import ALIMENTOS, LINHAS
    if session.exec(select(TabelaNutricionalProduto)).first():
        return
    produtos = [TabelaNutricionalProduto(nome=nome, ordem=i) for i, nome in enumerate(ALIMENTOS)]
    for p in produtos:
        session.add(p)
    session.commit()
    for p in produtos:
        session.refresh(p)
    for linha in LINHAS:
        nutriente = linha[0]
        for p, valor in zip(produtos, linha[1:]):
            if valor:
                session.add(TabelaNutricionalValor(produto_id=p.id, nutriente=nutriente, valor=valor))
    session.commit()


def _tabela_nutricional_montada(session: Session):
    from fazenda.models import TabelaNutricionalProduto, TabelaNutricionalValor
    produtos = session.exec(select(TabelaNutricionalProduto).order_by(TabelaNutricionalProduto.ordem, TabelaNutricionalProduto.nome)).all()
    valores = session.exec(select(TabelaNutricionalValor).order_by(TabelaNutricionalValor.id)).all()
    por_produto: dict[int, dict[str, str]] = {}
    nutrientes_ordem: list[str] = []
    for v in valores:
        por_produto.setdefault(v.produto_id, {})[v.nutriente] = v.valor
        if v.nutriente not in nutrientes_ordem:
            nutrientes_ordem.append(v.nutriente)
    return produtos, nutrientes_ordem, por_produto


@router.get("/tabela-nutricional")
def obter_tabela_nutricional(session: Session = Depends(get_session)) -> dict:
    """Tabela nutricional (nutriente × produto), cadastrável em Alimentação >
    Tabela nutricional — consulta rápida (modal + calculadora) e edição."""
    _seed_tabela_nutricional(session)
    produtos, nutrientes_ordem, por_produto = _tabela_nutricional_montada(session)
    linhas = [[nutriente] + [por_produto.get(p.id, {}).get(nutriente, "") for p in produtos] for nutriente in nutrientes_ordem]
    return {"alimentos": [p.nome for p in produtos], "produto_ids": [p.id for p in produtos], "linhas": linhas}


class TabelaNutricionalProdutoIn(BaseModel):
    nome: str


@router.post("/tabela-nutricional/produtos", status_code=201)
def criar_produto_tabela_nutricional(dados: TabelaNutricionalProdutoIn, session: Session = Depends(get_session)) -> dict:
    from fazenda.models import TabelaNutricionalProduto
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome do produto é obrigatório")
    if session.exec(select(TabelaNutricionalProduto).where(TabelaNutricionalProduto.nome == nome)).first():
        raise HTTPException(status_code=409, detail=f'Já existe um produto chamado "{nome}" na tabela nutricional')
    maior_ordem = session.exec(select(TabelaNutricionalProduto).order_by(TabelaNutricionalProduto.ordem.desc())).first()
    produto = TabelaNutricionalProduto(nome=nome, ordem=(maior_ordem.ordem + 1) if maior_ordem else 0)
    session.add(produto)
    session.commit()
    session.refresh(produto)
    return produto.model_dump()


@router.put("/tabela-nutricional/produtos/{produto_id}")
def renomear_produto_tabela_nutricional(produto_id: int, dados: TabelaNutricionalProdutoIn, session: Session = Depends(get_session)) -> dict:
    from fazenda.models import TabelaNutricionalProduto
    produto = session.get(TabelaNutricionalProduto, produto_id)
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome do produto é obrigatório")
    produto.nome = nome
    session.add(produto)
    session.commit()
    session.refresh(produto)
    return produto.model_dump()


@router.delete("/tabela-nutricional/produtos/{produto_id}")
def excluir_produto_tabela_nutricional(produto_id: int, session: Session = Depends(get_session)) -> dict:
    from fazenda.models import TabelaNutricionalProduto, TabelaNutricionalValor
    produto = session.get(TabelaNutricionalProduto, produto_id)
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    for v in session.exec(select(TabelaNutricionalValor).where(TabelaNutricionalValor.produto_id == produto_id)).all():
        session.delete(v)
    session.delete(produto)
    session.commit()
    return {"excluido": True, "id": produto_id}


class ValorTabelaNutricionalIn(BaseModel):
    produto_id: int
    nutriente: str
    valor: str = ""


class SalvarValoresTabelaNutricionalIn(BaseModel):
    itens: list[ValorTabelaNutricionalIn]


@router.put("/tabela-nutricional/valores")
def salvar_valores_tabela_nutricional(dados: SalvarValoresTabelaNutricionalIn, session: Session = Depends(get_session)) -> dict:
    """Upsert em lote — salva a grade inteira (nutriente × produto) de uma vez."""
    from fazenda.models import TabelaNutricionalValor
    existentes = {(v.produto_id, v.nutriente): v for v in session.exec(select(TabelaNutricionalValor)).all()}
    salvos = 0
    for item in dados.itens:
        nutriente = item.nutriente.strip()
        if not nutriente:
            continue
        chave = (item.produto_id, nutriente)
        v = existentes.get(chave)
        if v:
            v.valor = item.valor
            session.add(v)
        elif item.valor.strip():
            session.add(TabelaNutricionalValor(produto_id=item.produto_id, nutriente=nutriente, valor=item.valor))
        salvos += 1
    session.commit()
    return {"salvos": salvos}


@router.get("/tabela-nutricional/modelo")
def baixar_modelo_tabela_nutricional(session: Session = Depends(get_session)) -> Response:
    """Planilha (.xlsx) com os produtos e nutrientes já cadastrados — baixe,
    edite/complete e reimporte em POST /tabela-nutricional/importar."""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    _seed_tabela_nutricional(session)
    produtos, nutrientes_ordem, por_produto = _tabela_nutricional_montada(session)

    wb = Workbook()
    ws = wb.active
    ws.title = "Tabela nutricional"
    cabecalho = ["Nutriente"] + [p.nome for p in produtos]
    ws.append(cabecalho)
    for cel in ws[1]:
        cel.font = Font(bold=True, color="FFFFFF")
        cel.fill = PatternFill("solid", fgColor="4A6B3A")
    for nutriente in nutrientes_ordem:
        ws.append([nutriente] + [por_produto.get(p.id, {}).get(nutriente, "") for p in produtos])
    for idx in range(1, len(cabecalho) + 1):
        ws.column_dimensions[ws.cell(row=1, column=idx).column_letter].width = 22

    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=tabela_nutricional_modelo.xlsx"},
    )


@router.post("/tabela-nutricional/importar")
async def importar_tabela_nutricional(file: UploadFile, session: Session = Depends(get_session)) -> dict:
    """
    Importa a planilha no mesmo formato do modelo baixado: 1ª coluna =
    nutriente, demais colunas = um produto cada (nome no cabeçalho). Produtos
    com nome novo são criados; existentes (mesmo nome) têm os valores
    atualizados/completados.
    """
    import io
    from openpyxl import load_workbook
    from fazenda.models import TabelaNutricionalProduto, TabelaNutricionalValor

    content = await file.read()
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Não foi possível ler o arquivo — envie um .xlsx válido")
    ws = wb.active
    linhas = list(ws.iter_rows(values_only=True))
    if not linhas:
        raise HTTPException(status_code=400, detail="Planilha vazia")
    cabecalho = [str(c).strip() if c is not None else "" for c in linhas[0]]
    if len(cabecalho) < 2 or not any(cabecalho[1:]):
        raise HTTPException(status_code=400, detail="A planilha precisa de ao menos uma coluna de produto (além de 'Nutriente')")

    existentes = {p.nome: p for p in session.exec(select(TabelaNutricionalProduto)).all()}
    maior_ordem = max([p.ordem for p in existentes.values()], default=-1)
    produto_por_coluna: dict[int, "TabelaNutricionalProduto"] = {}
    for idx, nome in enumerate(cabecalho[1:], start=1):
        if not nome:
            continue
        produto = existentes.get(nome)
        if not produto:
            maior_ordem += 1
            produto = TabelaNutricionalProduto(nome=nome, ordem=maior_ordem)
            session.add(produto)
            session.commit()
            session.refresh(produto)
            existentes[nome] = produto
        produto_por_coluna[idx] = produto

    valores_existentes = {(v.produto_id, v.nutriente): v for v in session.exec(select(TabelaNutricionalValor)).all()}
    nutrientes_importados = 0
    for row in linhas[1:]:
        if not row or not row[0]:
            continue
        nutriente = str(row[0]).strip()
        teve_valor = False
        for idx, produto in produto_por_coluna.items():
            valor_bruto = row[idx] if idx < len(row) else None
            valor = "" if valor_bruto is None else str(valor_bruto).strip()
            if not valor:
                continue
            teve_valor = True
            chave = (produto.id, nutriente)
            v = valores_existentes.get(chave)
            if v:
                v.valor = valor
                session.add(v)
            else:
                v = TabelaNutricionalValor(produto_id=produto.id, nutriente=nutriente, valor=valor)
                session.add(v)
                valores_existentes[chave] = v
        if teve_valor:
            nutrientes_importados += 1
    session.commit()
    return {"produtos": len(produto_por_coluna), "nutrientes": nutrientes_importados}


# ─────────────────────────── Análise bromatológica ───────────────────────────
# Laudo de laboratório de um lote/silo de alimento da própria fazenda — não
# confundir com Tabela Nutricional (referência padrão) ou Matéria seca (só o
# %MS por ingrediente genérico). Registro pontual, sem edição/exclusão (mesmo
# padrão de Qualidade do leite).
class AnaliseBromatologicaIn(BaseModel):
    data: date
    alimento: str
    ms_pct: float | None = None
    pb_pct: float | None = None
    fdn_pct: float | None = None
    fda_pct: float | None = None
    ndt_pct: float | None = None
    ee_pct: float | None = None
    cinzas_pct: float | None = None
    ca_pct: float | None = None
    p_pct: float | None = None
    observacao: str | None = None


@router.get("/analise-bromatologica")
def listar_analise_bromatologica(session: Session = Depends(get_session)) -> dict:
    from fazenda.models import AnaliseBromatologica
    registros = session.exec(select(AnaliseBromatologica).order_by(AnaliseBromatologica.data.desc())).all()
    nomes = mapa_usuarios(session, {r.usuario_id for r in registros})
    linhas = []
    for r in registros:
        linha = r.model_dump()
        linha["usuario_nome"] = nomes.get(linha.pop("usuario_id"))
        linhas.append(linha)
    return {"registros": linhas, "total": len(registros)}


@router.post("/analise-bromatologica", status_code=201)
def criar_analise_bromatologica(
    dados: AnaliseBromatologicaIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
) -> dict:
    from fazenda.models import AnaliseBromatologica
    if not dados.alimento.strip():
        raise HTTPException(status_code=400, detail="Alimento é obrigatório")
    registro = AnaliseBromatologica(**dados.model_dump(), usuario_id=user.id)
    session.add(registro)
    session.commit()
    session.refresh(registro)
    return registro.model_dump()


class ItemProgramadoIn(BaseModel):
    alimento: str
    quantidade: float
    unidade: str
    base: str | None = None       # "MN" (matéria natural) | "MS" (matéria seca)
    ms_pct: float | None = None   # % de matéria seca do alimento


def _quantidade_fisica(quantidade: float, unidade: str | None, base: str | None, ms_pct: float | None) -> float:
    """Converte a quantidade lançada em matéria seca (MS) para o físico
    (matéria natural, MN) a oferecer de fato no vagão — só se aplica a
    unidades de massa (kg/g); nas demais (L, dose, unidade...) a conversão de
    MS não faz sentido e a quantidade é usada como está."""
    if base == "MS" and ms_pct and (unidade or "").lower() in ("kg", "g"):
        return quantidade / (ms_pct / 100)
    return quantidade


class DietaLancamentoIn(BaseModel):
    lote: int
    responsavel: str | None = None
    data_abertura: date
    data_prevista_encerramento: date | None = None
    observacao: str | None = None
    base_quantidade: str | None = None  # "total" (padrão) | "animal" (por cabeça/dia)
    leite_bezerros_kg_dia: float | None = None  # kg/dia de leite p/ bezerros (relatório Controle × Entregue)
    itens: list[ItemProgramadoIn]
    # Se True e já houver dieta ativa no lote, encerra-a na data de início
    # desta (o veterinário responde "sim" ao salvar). Se False e houver ativa,
    # devolve 409 como antes.
    encerrar_anterior: bool = False


def _serializar_dieta(session: Session, d: DietaLancamento) -> dict:
    itens = session.exec(
        select(DietaItemProgramado).where(DietaItemProgramado.dieta_lancamento_id == d.id)
    ).all()
    return {**d.model_dump(), "ativa": d.data_efetivo_encerramento is None, "itens_programados": [i.model_dump() for i in itens]}


@router.get("/dietas")
def listar_dietas(
    lote: int | None = None, ativo: bool | None = None, session: Session = Depends(get_session),
) -> list[dict]:
    dietas = session.exec(select(DietaLancamento)).all()
    saida = [_serializar_dieta(session, d) for d in dietas]
    nomes = mapa_usuarios(session, {s["usuario_id"] for s in saida})
    for s in saida:
        s["usuario_nome"] = nomes.get(s["usuario_id"])
    if lote is not None:
        saida = [s for s in saida if s["lote"] == lote]
    if ativo is not None:
        saida = [s for s in saida if s["ativa"] == ativo]
    return sorted(saida, key=lambda s: s["data_abertura"], reverse=True)


@router.post("/dietas", status_code=201)
def criar_dieta(dados: DietaLancamentoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Informe ao menos um alimento do plano programado")
    ms_por_nome = {i.nome: i.ms_pct for i in session.exec(select(IngredienteMS)).all()}
    for item in dados.itens:
        if item.ms_pct is None:
            item.ms_pct = ms_por_nome.get(item.alimento)
        if item.base == "MS" and not item.ms_pct:
            raise HTTPException(
                status_code=400,
                detail=f'Informe o % de matéria seca de "{item.alimento}" em Configurações > Cadastro > '
                       f'Alimentação > Matéria seca antes de lançar em base MS.',
            )
        if item.ms_pct is not None and not (0 < item.ms_pct <= 100):
            raise HTTPException(status_code=400, detail=f'% de matéria seca inválido para "{item.alimento}" — deve ser entre 0 e 100.')
    ativa_existente = session.exec(
        select(DietaLancamento).where(
            DietaLancamento.lote == dados.lote, DietaLancamento.data_efetivo_encerramento == None  # noqa: E711
        )
    ).first()
    if ativa_existente:
        if dados.encerrar_anterior:
            ativa_existente.data_efetivo_encerramento = dados.data_abertura
            session.add(ativa_existente)
            session.commit()
        else:
            raise HTTPException(
                status_code=409,
                detail=f"Já existe uma dieta ativa para o lote {dados.lote} — encerre-a antes de lançar uma nova",
            )
    dieta = DietaLancamento(
        lote=dados.lote, responsavel=dados.responsavel, data_abertura=dados.data_abertura,
        data_prevista_encerramento=dados.data_prevista_encerramento, observacao=dados.observacao,
        base_quantidade=dados.base_quantidade or "total",
        leite_bezerros_kg_dia=dados.leite_bezerros_kg_dia,
        usuario_id=user.id,
    )
    session.add(dieta)
    session.commit()
    session.refresh(dieta)
    # Resolve o alimento_id automaticamente pelo nome do item de Estoque
    # escolhido no formulário (EstoquePicker) — sem exigir nenhuma mudança na
    # tela de lançamento: se existir um Alimento com esse mesmo nome (ou um
    # item de Estoque já vinculado a um Alimento), o vínculo entra sozinho.
    estoque_por_nome = {e.nome: e for e in session.exec(select(Estoque)).all()}
    alimento_por_nome = {a.nome: a.id for a in session.exec(select(Alimento)).all()}
    for item in dados.itens:
        estoque_item = estoque_por_nome.get(item.alimento)
        alimento_id = (estoque_item.alimento_id if estoque_item else None) or alimento_por_nome.get(item.alimento)
        session.add(DietaItemProgramado(dieta_lancamento_id=dieta.id, alimento_id=alimento_id, **item.model_dump()))
    session.commit()
    return _serializar_dieta(session, dieta)


def _animais_do_lote(session: Session, lote: int) -> list[Animal]:
    ativos = session.exec(select(Animal).where(Animal.ativo == True)).all()  # noqa: E712
    return [
        a for a in ativos
        if not a.eh_semen and a.sexo != "M" and (_codigo_grupo(a.grupo_primario) or "") == f"{lote:02d}"
    ]


@router.get("/dietas/contexto/{lote}")
def contexto_dieta(lote: int, session: Session = Depends(get_session)) -> dict:
    """Contexto do lote para o veterinário formular a dieta: nome/nº do lote,
    nº de animais, última dieta (produtos e qtd/cabeça/dia), último controle
    leiteiro de cada animal e um resumo (DEL médio, média do CL, data do CL)."""
    lote_cad = session.exec(select(Lote).where(Lote.codigo == f"{lote:02d}")).first()
    animais = _animais_do_lote(session, lote)
    n = len(animais)

    dels = [a.del_dias for a in animais if a.del_dias is not None]
    cls = [a.ult_cl_kg for a in animais if a.ult_cl_kg is not None]
    datas_cl = [a.data_ult_leite for a in animais if a.data_ult_leite is not None]

    # Última dieta ativa do lote (produtos + qtd total/dia → por cabeça/dia).
    ativa = session.exec(
        select(DietaLancamento).where(
            DietaLancamento.lote == lote, DietaLancamento.data_efetivo_encerramento == None  # noqa: E711
        )
    ).first()
    ultima_dieta = None
    if ativa:
        itens = session.exec(select(DietaItemProgramado).where(DietaItemProgramado.dieta_lancamento_id == ativa.id)).all()
        ultima_dieta = {
            "data_abertura": ativa.data_abertura.isoformat(),
            "responsavel": ativa.responsavel,
            "itens": [
                {
                    "alimento": it.alimento, "unidade": it.unidade,
                    "total_dia": round(_quantidade_fisica(it.quantidade, it.unidade, it.base, it.ms_pct), 2),
                    "por_cabeca": round(_quantidade_fisica(it.quantidade, it.unidade, it.base, it.ms_pct) / n, 3) if n else None,
                }
                for it in itens
            ],
        }

    return {
        "lote": lote,
        "nome": lote_cad.nome if lote_cad else None,
        "qtd_animais": n,
        "del_medio": round(sum(dels) / len(dels)) if dels else None,
        "media_cl": round(sum(cls) / len(cls), 1) if cls else None,
        "data_ult_cl": max(datas_cl).isoformat() if datas_cl else None,
        "animais": sorted([
            {"numero": a.numero, "del_dias": a.del_dias, "ult_cl_kg": a.ult_cl_kg,
             "data_ult_leite": a.data_ult_leite.isoformat() if a.data_ult_leite else None}
            for a in animais
        ], key=lambda x: (x["ult_cl_kg"] is None, -(x["ult_cl_kg"] or 0))),
        "ultima_dieta": ultima_dieta,
    }


@router.get("/dietas/{dieta_id}/apresentacao")
def apresentacao_dieta(dieta_id: int, session: Session = Depends(get_session)) -> dict:
    """Como o funcionário vê a dieta para conferir no vagão: por produto — qtd/
    cabeça, total/dia, total/trato; e o somatório de kg no vagão do lote."""
    dieta = session.get(DietaLancamento, dieta_id)
    if not dieta:
        raise HTTPException(status_code=404, detail="Dieta não encontrada")
    n = len(_animais_do_lote(session, dieta.lote))
    lote_cad = session.exec(select(Lote).where(Lote.codigo == f"{dieta.lote:02d}")).first()
    itens = session.exec(select(DietaItemProgramado).where(DietaItemProgramado.dieta_lancamento_id == dieta_id)).all()
    linhas = []
    total_dia = 0.0
    for it in itens:
        td = _quantidade_fisica(it.quantidade, it.unidade, it.base, it.ms_pct)  # total físico (MN) do lote/dia
        linhas.append({
            "alimento": it.alimento, "unidade": it.unidade,
            "total_dia": round(td, 2),
            "por_cabeca": round(td / n, 3) if n else None,
            "total_trato": round(td / NUM_TRATOS, 2),
        })
        if (it.unidade or "").lower() in ("kg", "g"):
            total_dia += td
    return {
        "lote": dieta.lote, "nome": lote_cad.nome if lote_cad else None, "qtd_animais": n,
        "data_abertura": dieta.data_abertura.isoformat(),
        "data_prevista_encerramento": dieta.data_prevista_encerramento.isoformat() if dieta.data_prevista_encerramento else None,
        "num_tratos": NUM_TRATOS, "itens": linhas,
        # Somatório de quilos que deve estar no vagão (só itens em kg).
        "vagao_kg_dia": round(total_dia, 2),
        "vagao_kg_trato": round(total_dia / NUM_TRATOS, 2),
    }


class EncerrarDietaIn(BaseModel):
    data_efetivo_encerramento: date


@router.put("/dietas/{dieta_id}/encerrar")
def encerrar_dieta(dieta_id: int, dados: EncerrarDietaIn, session: Session = Depends(get_session)) -> dict:
    dieta = session.get(DietaLancamento, dieta_id)
    if not dieta:
        raise HTTPException(status_code=404, detail="Dieta não encontrada")
    if dieta.data_efetivo_encerramento is not None:
        raise HTTPException(status_code=400, detail="Esta dieta já está encerrada")
    dieta.data_efetivo_encerramento = dados.data_efetivo_encerramento
    session.add(dieta)
    session.commit()
    return {"encerrada": True, "lote": dieta.lote}


class RegistroRealIn(BaseModel):
    data: date
    itens: list[ItemProgramadoIn]


@router.post("/dietas/{dieta_id}/real", status_code=201)
def registrar_real(dieta_id: int, dados: RegistroRealIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    dieta = session.get(DietaLancamento, dieta_id)
    if not dieta:
        raise HTTPException(status_code=404, detail="Dieta não encontrada")
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Informe ao menos um alimento oferecido")
    for item in dados.itens:
        session.add(DietaRegistroReal(dieta_lancamento_id=dieta_id, data=dados.data, usuario_id=user.id, **item.model_dump()))
    session.commit()
    return {"registrados": len(dados.itens)}


@router.get("/dietas/{dieta_id}/comparativo")
def comparativo_dieta(dieta_id: int, session: Session = Depends(get_session)) -> dict:
    """Programado × real por alimento — soma total real e média por dia distinto registrado."""
    dieta = session.get(DietaLancamento, dieta_id)
    if not dieta:
        raise HTTPException(status_code=404, detail="Dieta não encontrada")
    programados = session.exec(select(DietaItemProgramado).where(DietaItemProgramado.dieta_lancamento_id == dieta_id)).all()
    reais = session.exec(select(DietaRegistroReal).where(DietaRegistroReal.dieta_lancamento_id == dieta_id)).all()

    por_alimento: dict[str, dict] = {}
    for p in programados:
        acc = por_alimento.setdefault(p.alimento, {"alimento": p.alimento, "unidade": p.unidade, "programado": 0.0, "real_total": 0.0, "real_dias": 0, "real_media_dia": None})
        acc["programado"] += p.quantidade

    dias_por_alimento: dict[str, set] = {}
    for r in reais:
        acc = por_alimento.setdefault(r.alimento, {"alimento": r.alimento, "unidade": r.unidade, "programado": 0.0, "real_total": 0.0, "real_dias": 0, "real_media_dia": None})
        acc["real_total"] = round(acc["real_total"] + r.quantidade, 2)
        dias_por_alimento.setdefault(r.alimento, set()).add(r.data.isoformat())

    for alimento, dias in dias_por_alimento.items():
        por_alimento[alimento]["real_dias"] = len(dias)
        por_alimento[alimento]["real_media_dia"] = round(por_alimento[alimento]["real_total"] / len(dias), 2) if dias else None

    return {"dieta": _serializar_dieta(session, dieta), "itens": sorted(por_alimento.values(), key=lambda x: x["alimento"])}
