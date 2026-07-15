"""
Router de estoque — inventário completo de insumos e lançamento de
entradas/saídas (dá baixa ou soma direto em Estoque.quantidade).
"""
from __future__ import annotations

import unicodedata
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user
from fazenda.database import get_session
from fazenda.models import Estoque, Fornecedor, MovimentoEstoque, Usuario
from fazenda.rules.auditoria import mapa_usuarios

router = APIRouter(prefix="/estoque", tags=["estoque"])

MOVIMENTOS_ENTRADA = ["Entrada de ajuste", "Entrada de cortesia"]
MOVIMENTOS_SAIDA = ["Aplicação", "Saída de ajuste", "Doação"]
MOVIMENTOS_VALIDOS = set(MOVIMENTOS_ENTRADA + MOVIMENTOS_SAIDA)


def _sem_acento(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
# Só itens estocáveis podem ser doados ou recebidos de cortesia — itens não
# estocáveis existem só para lançamento financeiro, sem controle de quantidade.
MOVIMENTOS_SOMENTE_ESTOCAVEL = {"Doação", "Entrada de cortesia"}

UNIDADES_EMBALAGEM = ["Saca", "Pote", "Frasco", "Pacote", "Bag", "Fardo", "Garrafa", "Unidade"]
MEDIDAS_EMBALAGEM = ["kg/saca", "litros/garrafa", "mililitros/frasco", "unidades/fardo", "potes/caixa", "unidades"]


@router.get("/")
def listar_estoque(session: Session = Depends(get_session)) -> dict:
    """Todos os itens de estoque para o dashboard interativo (filtra no cliente)."""
    fornecedores = {f.id: f.nome for f in session.exec(select(Fornecedor)).all()}
    itens = [
        {**e.model_dump(), "fornecedor_nome": fornecedores.get(e.fornecedor_id)}
        for e in session.exec(select(Estoque).order_by(Estoque.nome)).all()
    ]
    return {"itens": itens, "total": len(itens)}


class EstoqueIn(BaseModel):
    nome: str
    categoria: str | None = None
    finalidade: str | None = None
    numero_produto: str | None = None
    unidade: str | None = None
    quantidade: float | None = None
    estoque_minimo: float | None = None
    valor_unitario: float | None = None
    local_armazenamento: str | None = None
    unidade_embalagem: str | None = None
    medida_embalagem: str | None = None
    quantidade_embalagem: float | None = None
    fornecedor_id: int | None = None
    ativo: bool = True
    observacao: str | None = None
    carencia_dias: int | None = None
    centro_custo_padrao: str | None = None
    conta_gerencial_despesa_padrao: str | None = None
    conta_gerencial_receita_padrao: str | None = None
    gera_receita: bool = False
    exibir_necessidade_compra_agenda: bool = False
    estocavel: bool = True
    data_inicio_controle: date | None = None
    principio_ativo: str | None = None
    classificacao_medicamento: str | None = None


def _validar_embalagem(unidade_embalagem: str | None, medida_embalagem: str | None) -> None:
    if unidade_embalagem and unidade_embalagem not in UNIDADES_EMBALAGEM:
        raise HTTPException(status_code=400, detail=f"Unidade de embalagem inválida — use uma de: {', '.join(UNIDADES_EMBALAGEM)}")
    if medida_embalagem and medida_embalagem not in MEDIDAS_EMBALAGEM:
        raise HTTPException(status_code=400, detail=f"Unidade de medida inválida — use uma de: {', '.join(MEDIDAS_EMBALAGEM)}")


@router.post("/", status_code=201)
def criar_item_estoque(dados: EstoqueIn, session: Session = Depends(get_session)) -> dict:
    """Cadastra um item de estoque novo (não existe ainda um com esse nome)."""
    existente = session.exec(select(Estoque).where(Estoque.nome == dados.nome)).first()
    if existente:
        raise HTTPException(status_code=409, detail=f'Já existe um item de estoque chamado "{dados.nome}"')
    _validar_embalagem(dados.unidade_embalagem, dados.medida_embalagem)

    valor_total = (dados.quantidade or 0) * (dados.valor_unitario or 0) if dados.quantidade and dados.valor_unitario else None
    item = Estoque(
        nome=dados.nome,
        categoria=dados.categoria,
        finalidade=dados.finalidade,
        numero_produto=dados.numero_produto,
        unidade=dados.unidade,
        quantidade=dados.quantidade,
        estoque_minimo=dados.estoque_minimo,
        valor_unitario=dados.valor_unitario,
        valor_total=valor_total,
        abaixo_minimo=(dados.quantidade is not None and dados.estoque_minimo is not None and dados.quantidade < dados.estoque_minimo),
        local_armazenamento=dados.local_armazenamento,
        unidade_embalagem=dados.unidade_embalagem,
        medida_embalagem=dados.medida_embalagem,
        quantidade_embalagem=dados.quantidade_embalagem,
        fornecedor_id=dados.fornecedor_id,
        ativo=dados.ativo,
        observacao=dados.observacao,
        carencia_dias=dados.carencia_dias,
        centro_custo_padrao=dados.centro_custo_padrao,
        conta_gerencial_despesa_padrao=dados.conta_gerencial_despesa_padrao,
        conta_gerencial_receita_padrao=dados.conta_gerencial_receita_padrao,
        gera_receita=dados.gera_receita,
        exibir_necessidade_compra_agenda=dados.exibir_necessidade_compra_agenda,
        estocavel=dados.estocavel,
        data_inicio_controle=dados.data_inicio_controle if dados.estocavel else None,
        principio_ativo=dados.principio_ativo,
        classificacao_medicamento=dados.classificacao_medicamento,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item.model_dump()


def _eh_medicamento(e: Estoque) -> bool:
    """Item "candidato a medicamento" — usado quando NENHUM critério (princípio
    ativo/classificação/doença/secagem/vacina) foi passado, para que os
    seletores gerais de medicamento/hormônio (ex.: EditorHormoniosIatf, "todos"
    em Sanidade avulsa) não mostrem ração/material/equipamento junto."""
    return (
        e.finalidade == "Medicamento"
        or e.classificacao_medicamento is not None
        or e.principio_ativo_id is not None
        or bool((e.principio_ativo or "").strip())
    )


@router.get("/medicamentos")
def listar_medicamentos(
    principio_ativo: str = "", classificacao: str = "", doenca: str = "",
    finalidade: str = "", incluir_sem_estoque: bool = False,
    session: Session = Depends(get_session),
) -> list[dict]:
    """Medicamentos (itens de estoque) que cumprem um critério — usado ao
    lançar por princípio ativo, por classificação OU por doença. Sem nenhum
    critério, vira o catálogo geral de medicamento/hormônio/vacina (ver
    `_eh_medicamento`) — o que faz deste endpoint a fonte única para qualquer
    seletor que hoje mostrava todo o estoque sem filtro.

    Por padrão só entram itens com saldo em estoque (`quantidade > 0`) e
    ativos — `incluir_sem_estoque=true` resolve o problema na hora e ignora
    esse filtro (mesma ideia do "incluir touros sem estoque" da Inseminação).

    O casamento por princípio ativo/doença usa a Farmácia: além do texto legado
    `principio_ativo`, resolve o vínculo relacional (principio_ativo_id →
    PrincipioAtivo.nome / PrincipioAtivo.doenca_id → Doenca.nome), para que os
    medicamentos ligados ao princípio/doença apareçam mesmo sem o campo texto."""
    from fazenda.models import Doenca, PrincipioAtivo

    algum_criterio = bool(principio_ativo or classificacao or doenca or finalidade)

    pa_ids: set[int] = set()
    if principio_ativo:
        alvo = principio_ativo.strip().lower()
        for pa in session.exec(select(PrincipioAtivo)).all():
            if (pa.nome or "").strip().lower() == alvo:
                pa_ids.add(pa.id)

    # Doença → princípios ativos ligados a ela (via doenca_id da Farmácia).
    pa_ids_doenca: set[int] = set()
    if doenca:
        alvo_d = doenca.strip().lower()
        doenca_ids = {d.id for d in session.exec(select(Doenca)).all() if (d.nome or "").strip().lower() == alvo_d}
        for pa in session.exec(select(PrincipioAtivo)).all():
            if pa.doenca_id in doenca_ids:
                pa_ids_doenca.add(pa.id)

    # Finalidade: "secagem" = antimicrobianos intramamários de vaca seca;
    # "vacina" = todos os biológicos; "vacina_pre_parto" = só as vacinas
    # aplicadas na vaca seca/pré-parto (Clostridiose, Diarreia Neonatal,
    # Reprodutiva/Leptospirose — primovacinação — e Pasteurelose/Paratifo dos
    # Bezerros), excluindo biológicos que não são pré-parto (Brucelose,
    # Tuberculina). Casa pela categoria da Farmácia (categoria_software /
    # eh_biologico / doença) e, como reforço, pelo texto da classificação do
    # estoque.
    DOENCAS_VACINA_PRE_PARTO = {
        "clostridiose", "diarreia neonatal", "leptospirose", "pasteurelose e paratifo dos bezerros",
    }
    pa_ids_secagem: set[int] = set()
    pa_ids_vacina: set[int] = set()
    pa_ids_vacina_pre_parto: set[int] = set()
    if finalidade in ("secagem", "vacina", "vacina_pre_parto"):
        doencas_por_id = {d.id: (d.nome or "").strip().lower() for d in session.exec(select(Doenca)).all()}
        for pa in session.exec(select(PrincipioAtivo)).all():
            cat = (getattr(pa, "categoria_software", "") or "").lower()
            if ("vaca seca" in cat) or ("intramamario" in _sem_acento(cat)):
                pa_ids_secagem.add(pa.id)
            if getattr(pa, "eh_biologico", False) or "vacina" in cat:
                pa_ids_vacina.add(pa.id)
            if getattr(pa, "eh_biologico", False) and doencas_por_id.get(pa.doenca_id) in DOENCAS_VACINA_PRE_PARTO:
                pa_ids_vacina_pre_parto.add(pa.id)

    itens = session.exec(select(Estoque)).all()
    saida = []
    for e in itens:
        if e.ativo is False:
            continue
        if not algum_criterio and not _eh_medicamento(e):
            continue
        if principio_ativo:
            casa_texto = (e.principio_ativo or "").strip().lower() == principio_ativo.strip().lower()
            casa_link = e.principio_ativo_id in pa_ids
            if not (casa_texto or casa_link):
                continue
        if doenca and e.principio_ativo_id not in pa_ids_doenca:
            continue
        if classificacao and (e.classificacao_medicamento or "").strip().lower() != classificacao.strip().lower():
            continue
        if finalidade == "secagem":
            classe = _sem_acento((e.classificacao_medicamento or "").lower())
            if e.principio_ativo_id not in pa_ids_secagem and "vaca seca" not in classe and "intramamario" not in classe:
                continue
        if finalidade == "vacina":
            classe = (e.classificacao_medicamento or "").lower()
            if e.principio_ativo_id not in pa_ids_vacina and "vacina" not in classe:
                continue
        if finalidade == "vacina_pre_parto" and e.principio_ativo_id not in pa_ids_vacina_pre_parto:
            continue
        # Saldo None = item nunca inventariado (não é a mesma coisa que
        # confirmadamente zerado) — só esconde quando o saldo é conhecido e
        # <= 0, para não sumir com itens legados sem saldo lançado ainda.
        if not incluir_sem_estoque and e.quantidade is not None and e.quantidade <= 0:
            continue
        saida.append({
            "nome": e.nome, "unidade": e.unidade, "quantidade": e.quantidade,
            "principio_ativo": e.principio_ativo, "classificacao_medicamento": e.classificacao_medicamento,
            "laboratorio": e.laboratorio, "estoque_id": e.id,
        })
    return sorted(saida, key=lambda x: x["nome"])


@router.get("/movimentos")
def listar_movimentos(session: Session = Depends(get_session)) -> dict:
    """Histórico de entradas/saídas lançadas manualmente."""
    movs = session.exec(select(MovimentoEstoque).order_by(MovimentoEstoque.data_movimento.desc())).all()
    nomes = mapa_usuarios(session, {m.usuario_id for m in movs})
    movimentos = [{**m.model_dump(), "usuario_nome": nomes.get(m.usuario_id)} for m in movs]
    return {"movimentos": movimentos, "total": len(movs)}


class MovimentoIn(BaseModel):
    nome: str
    movimento: str
    quantidade: float
    unidade: str | None = None
    data_movimento: date
    observacao: str | None = None


def _criar_movimento_estoque(dados: MovimentoIn, session: Session, usuario_id: int | None = None) -> Estoque:
    """Lógica de fato de um lançamento de movimento (sem o commit ser feito
    pelo chamador direto) — usada pelo endpoint HTTP e pela importação de CSV
    (fazenda.api.routers.importar), que chama isto fora do ciclo de requisição
    e por isso não tem um usuário logado (usuario_id fica None nesse caso)."""
    if dados.movimento not in MOVIMENTOS_VALIDOS:
        raise HTTPException(status_code=400, detail="Tipo de movimento inválido")
    if dados.quantidade <= 0:
        raise HTTPException(status_code=400, detail="Quantidade deve ser maior que zero")

    item = session.exec(select(Estoque).where(Estoque.nome == dados.nome)).first()
    if not item:
        raise HTTPException(status_code=404, detail=f'Item de estoque "{dados.nome}" não encontrado')
    if dados.movimento in MOVIMENTOS_SOMENTE_ESTOCAVEL and item.estocavel is False:
        raise HTTPException(status_code=400, detail="Somente itens estocáveis podem ser doados ou recebidos de cortesia")

    baixa = dados.movimento in MOVIMENTOS_SAIDA
    item.quantidade = (item.quantidade or 0) + (-dados.quantidade if baixa else dados.quantidade)
    if item.estoque_minimo is not None:
        item.abaixo_minimo = item.quantidade < item.estoque_minimo
    item.atualizado_em = datetime.utcnow()
    session.add(item)

    session.add(MovimentoEstoque(
        nome_item=dados.nome,
        movimento=dados.movimento,
        quantidade=dados.quantidade,
        unidade=dados.unidade or item.unidade,
        data_movimento=dados.data_movimento,
        observacao=dados.observacao,
        usuario_id=usuario_id,
    ))
    session.commit()
    session.refresh(item)
    return item


@router.post("/movimentar")
def movimentar_estoque(dados: MovimentoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    item = _criar_movimento_estoque(dados, session, usuario_id=user.id)
    return item.model_dump()
