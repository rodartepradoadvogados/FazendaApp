"""
Cadastro > Folha de Pagamento — RUBRICAS do holerite: os vencimentos e os
descontos que o dono acrescenta ao recibo de uma competência.

POR QUE UM MÓDULO PRÓPRIO, e não mais funções dentro de rh_folha.py: o que
entra aqui é um domínio novo (verba trabalhista com enquadramento tributário
próprio, ver `fazenda/rules/rubrica_folha.py`) e o arquivo de folha já passa
de 3.300 linhas. rh_folha.py recebe só o mínimo indispensável — a linha entrar
no discriminado, o líquido considerar a rubrica e a recorrência incorporar o
aumento —, tudo o mais é daqui.

O QUE ESTE MÓDULO NÃO DEIXA ACONTECER, e é a razão de existirem tantas
recusas explícitas abaixo:

1. **Rubrica em folha PAGA.** A discriminação da folha paga foi congelada no
   pagamento justamente porque o holerite é PROVA (ver o bloco de
   congelamento em rh_folha.py). Aceitar uma rubrica depois disso produziria
   um recibo que não bate com o dinheiro que saiu — o defeito que o
   congelamento fechou, reaberto por outra porta.
2. **Retenção sobre base errada.** Reembolso e indenização são
   indenizatórios: entram no líquido mas NÃO na base de INSS/IRRF/FGTS.
   Somar tudo ao bruto (o único jeito que existia antes desta tela) fazia o
   funcionário pagar contribuição sobre dinheiro que só estava sendo
   devolvido a ele.
3. **Compra de outra fazenda virando desconto.** O vínculo do desconto com a
   compra é uma FK: a validação na gravação é a fronteira do inquilino, e ela
   é feita com filtro na PRÓPRIA consulta — "de outra fazenda" e "sem
   fazenda" caem os dois em 404, nunca em 403.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, or_, select

from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import ContaGerencial, FolhaPagamento, FolhaRubrica, Pessoa, Usuario
from fazenda.rules import rubrica_folha
from fazenda.rules.auditoria import fazenda_id_seguro

from .rh_folha import _liquido_folha, _valor_vale

router = APIRouter()

# Teto de linhas devolvidas pela consulta de compras da janela sobreposta —
# a janela é para ESCOLHER uma compra, não para auditar o Financeiro inteiro
# (essa é a tela de Lançamentos). Sem o teto, uma fazenda com anos de notas
# devolveria dezenas de milhares de linhas para um <select> visual.
LIMITE_COMPRAS = 200


class RubricaFolhaIn(BaseModel):
    especie: str  # vencimento | desconto
    codigo: str  # ver CATALOGO_VENCIMENTOS / CATALOGO_DESCONTOS
    valor: float
    descricao: str | None = None
    # Só para `desconto_compra`: a parcela do lançamento financeiro que está
    # sendo descontada do funcionário.
    conta_gerencial_id: int | None = None


class RubricaFolhaEditIn(BaseModel):
    """
    A edição mexe só no VALOR e na descrição — nunca no código.

    Trocar o código de uma rubrica já lançada trocaria o enquadramento
    tributário congelado na linha (um reembolso viraria bonificação, entrando
    em bases das quais estava fora) mantendo o mesmo id e o mesmo histórico.
    Quem errou o código exclui a linha e lança de novo: são dois atos
    explícitos, e o recibo conta a mesma história que o banco.
    """

    valor: float
    descricao: str | None = None


def _folha_da_fazenda(session: Session, folha_id: int, fazenda_id: int | None) -> FolhaPagamento:
    """
    Carrega a folha JÁ FILTRANDO por fazenda na própria consulta (mesmo
    desenho de agenda.py::_buscar_da_fazenda). O filtro é INCONDICIONAL —
    `== fazenda_id`, que em None vira `IS NULL` —, nunca o tolerante
    `if fazenda_id is not None: query = query.where(...)`: um token legado sem
    a claim de fazenda estaria escrevendo dinheiro na folha de outro
    inquilino. Folha de outra fazenda e folha órfã caem as duas em 404.
    """
    folha = session.exec(
        select(FolhaPagamento).where(
            FolhaPagamento.id == folha_id,
            FolhaPagamento.fazenda_id == fazenda_id,
        )
    ).first()
    if not folha:
        raise HTTPException(status_code=404, detail="Folha de pagamento não encontrada")
    return folha


def _rubrica_da_fazenda(session: Session, rubrica_id: int, fazenda_id: int | None) -> FolhaRubrica:
    """Mesma regra de `_folha_da_fazenda`, para a linha."""
    rubrica = session.exec(
        select(FolhaRubrica).where(
            FolhaRubrica.id == rubrica_id,
            FolhaRubrica.fazenda_id == fazenda_id,
        )
    ).first()
    if not rubrica:
        raise HTTPException(status_code=404, detail="Rubrica não encontrada")
    return rubrica


def _exigir_folha_aberta(folha: FolhaPagamento) -> None:
    """
    Folha paga não recebe rubrica — ver o item 1 da docstring do módulo. O
    caminho para corrigir um recibo já pago existe e é explícito: estornar o
    pagamento (`POST /folha-pagamento/{id}/estornar`), que descongela a
    discriminação, e só então mexer nas linhas.
    """
    if folha.status == "pago" or folha.discriminacao_congelada_em is not None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Esta folha já foi paga e o recibo está congelado. Estorne o pagamento antes de "
                "acrescentar ou alterar vencimentos e descontos."
            ),
        )


def _compra_da_fazenda(session: Session, conta_id: int, fazenda_id: int | None) -> ContaGerencial:
    """A parcela do lançamento financeiro que o desconto está abatendo —
    filtrada por fazenda na própria consulta, pelo mesmo motivo de
    `_folha_da_fazenda`."""
    conta = session.exec(
        select(ContaGerencial).where(
            ContaGerencial.id == conta_id,
            ContaGerencial.fazenda_id == fazenda_id,
        )
    ).first()
    if not conta:
        raise HTTPException(status_code=404, detail="Compra não encontrada")
    return conta


def _validar_entrada(dados: RubricaFolhaIn) -> dict:
    """Devolve o verbete do catálogo — ou recusa. O enquadramento NUNCA vem do
    cliente: o frontend manda o código, o servidor decide a natureza e as
    incidências (senão bastaria um POST à mão para um reembolso entrar na base
    do INSS, ou uma bonificação sair dela)."""
    if dados.especie not in (rubrica_folha.ESPECIE_VENCIMENTO, rubrica_folha.ESPECIE_DESCONTO):
        raise HTTPException(status_code=400, detail="Espécie inválida (vencimento ou desconto)")
    catalogo = (
        rubrica_folha.CATALOGO_VENCIMENTOS if dados.especie == rubrica_folha.ESPECIE_VENCIMENTO
        else rubrica_folha.CATALOGO_DESCONTOS
    )
    verbete = catalogo.get(dados.codigo)
    if not verbete:
        raise HTTPException(status_code=400, detail="Rubrica desconhecida para esta espécie")
    _validar_valor(dados.valor)
    return verbete


def _validar_valor(valor: float) -> None:
    """
    Valor sempre POSITIVO: quem diz se soma ou subtrai é a espécie, não o
    sinal. Um desconto lançado com valor negativo viraria um vencimento
    disfarçado na coluna errada do documento — e o total das colunas do papel
    deixaria de fechar com o líquido.
    """
    if valor is None or valor <= 0:
        raise HTTPException(status_code=400, detail="Informe um valor maior que zero")


def _recalcular_folha(session: Session, folha: FolhaPagamento) -> list[FolhaRubrica]:
    """
    Reprocessa a folha depois de qualquer mudança nas rubricas: as duas somas
    em cache, as retenções sobre a base corrigida, o líquido e a conta a pagar.

    Ordem importa e é a do holerite de papel: primeiro a base (bruto + as
    rubricas SALARIAIS), depois as retenções sobre ela, e só então o líquido —
    do qual saem os descontos, que nunca entraram em base nenhuma.
    """
    rubricas = session.exec(select(FolhaRubrica).where(FolhaRubrica.folha_id == folha.id)).all()
    folha.valor_rubricas = rubrica_folha.valor_liquido_das_rubricas(rubricas)
    folha.valor_rubricas_tributaveis = rubrica_folha.base_tributavel_das_rubricas(rubricas)

    for campo, valor in rubrica_folha.retencoes_recalculadas(
        folha.valor_bruto, folha.percentual_inss, folha.percentual_ir, folha.percentual_fgts, rubricas,
    ).items():
        setattr(folha, campo, valor)

    # O vale vem sempre da SOMA das parcelas da competência (função de
    # rh_folha.py, não recopiada aqui): recalcular o líquido a partir de um
    # `valor_vale` desatualizado no registro é como a folha já nascia inflada
    # antes do self-heal da listagem.
    folha.valor_vale = _valor_vale(session, folha.pessoa_id, folha.competencia)
    folha.valor_liquido = _liquido_folha(
        folha.valor_bruto, folha.descontos, folha.valor_inss, folha.valor_ir, folha.valor_vale,
        folha.valor_rubricas,
    )
    session.add(folha)

    # A conta a pagar é o número que o dono efetivamente paga: sem isto, o
    # holerite mostraria a bonificação e o banco pagaria o valor antigo.
    # Conta já BAIXADA não é tocada (não se reescreve pagamento feito) — e ela
    # só existiria aqui numa folha paga, que `_exigir_folha_aberta` já barrou.
    if folha.numero_lancamento_gerado:
        conta = session.exec(
            select(ContaGerencial).where(
                ContaGerencial.numero_lancamento == folha.numero_lancamento_gerado,
                ContaGerencial.fazenda_id == folha.fazenda_id,
            )
        ).first()
        if conta and conta.valor_pago is None:
            conta.valor_total = folha.valor_liquido
            session.add(conta)
    return list(rubricas)


def _propagar_aumento(
    session: Session, folha: FolhaPagamento, valor: float, fazenda_id: int | None,
) -> dict:
    """
    A parte do "aumento na folha" que não cabe no mês em que ele é concedido:
    a partir da competência SEGUINTE o valor deixa de ser linha avulsa e passa
    a ser SALÁRIO-BASE (CLT, art. 468).

    Dois caminhos, porque a folha do mês seguinte nasce de dois lugares
    diferentes neste sistema:

    - a que AINDA NÃO EXISTE nasce da recorrência, e essa é resolvida em
      `_gerar_folha_recorrente` somando `aumento_incorporado` ao bruto do
      modelo (o valor não é copiado para lugar nenhum: é derivado das
      rubricas, então excluir o aumento desfaz a incorporação sozinho);
    - a que JÁ EXISTE (mês seguinte já lançado, ou vários meses já gerados
      antes de o aumento ser registrado) é corrigida aqui, uma a uma.

    E `Pessoa.salario_base`, que é o valor VIVO usado para sugerir o bruto de
    um lançamento novo: sem atualizá-lo, o dono daria o aumento e o formulário
    do mês seguinte continuaria sugerindo o salário antigo — o aumento
    "sumiria" no primeiro lançamento feito à mão.

    `valor` é positivo ao conceder e negativo ao excluir a rubrica: desfazer é
    o mesmo caminho ao contrário, e não uma segunda implementação.
    """
    pessoa = session.get(Pessoa, folha.pessoa_id)
    if pessoa and pessoa.fazenda_id == fazenda_id:
        pessoa.salario_base = round((pessoa.salario_base or 0.0) + valor, 2)
        session.add(pessoa)

    seguintes = session.exec(
        select(FolhaPagamento).where(
            FolhaPagamento.pessoa_id == folha.pessoa_id,
            FolhaPagamento.competencia > folha.competencia,
            FolhaPagamento.fazenda_id == fazenda_id,
        )
    ).all()
    ajustadas: list[str] = []
    for seguinte in seguintes:
        # Folha já paga fica como está: o salário daquele mês já foi pago com
        # a base que valia na época, e reescrevê-lo agora mudaria um recibo
        # emitido. O dono vê a diferença e decide (pagar a diferença é outro
        # lançamento, não uma correção silenciosa deste).
        if seguinte.status == "pago" or seguinte.discriminacao_congelada_em is not None:
            continue
        seguinte.valor_bruto = round(seguinte.valor_bruto + valor, 2)
        _recalcular_folha(session, seguinte)
        ajustadas.append(seguinte.competencia)
    return {"salario_base": pessoa.salario_base if pessoa else None, "competencias_ajustadas": ajustadas}


def _rubrica_resposta(rubrica: FolhaRubrica, compra: dict | None = None) -> dict:
    """A rubrica como a tela consome — os campos gravados mais a linha pronta
    do holerite, para a tela nunca ter de remontar rótulo/referência por
    conta própria (foi assim que a linha de vale virou regex no frontend)."""
    return {
        **rubrica.model_dump(),
        "rotulo": rubrica_folha.rotulo_rubrica(rubrica),
        "referencia": rubrica_folha.referencia_rubrica(rubrica, compra),
        "compra": compra,
    }


@router.get("/folha-pagamento/rubricas/catalogo")
def catalogo_rubricas(user: Usuario = Depends(get_current_user)) -> dict:
    """As escolhas do formulário JÁ com o enquadramento — a tela mostra a
    consequência tributária antes do lançamento, em vez de o dono descobrir
    depois no valor retido."""
    return rubrica_folha.catalogo_publico()


@router.get("/folha-pagamento/rubricas/compras")
def compras_para_desconto(
    busca: str | None = None,
    de: date | None = None,
    ate: date | None = None,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """
    A consulta detalhada de contas que a janela sobreposta abre para escolher
    a compra que vira desconto.

    É uma consulta PRÓPRIA, e não um link para a tela de Lançamentos, porque o
    dono pediu exatamente isso: escolher sem sair do holerite. Devolve só
    DESPESA — receita não é compra e descontar uma venda do salário de alguém
    não significa nada.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    # Filtro de fazenda INCONDICIONAL, na própria consulta: esta lista é o
    # cardápio de onde sai um vínculo gravado — se vazasse aqui, o desconto de
    # outra fazenda entraria por uma escolha "legítima" da tela.
    query = select(ContaGerencial).where(
        ContaGerencial.fazenda_id == fazenda_id,
        ContaGerencial.tipo == "despesa",
    )
    if de:
        query = query.where(ContaGerencial.data_vencimento >= de)
    if ate:
        query = query.where(ContaGerencial.data_vencimento <= ate)
    if busca:
        alvo = f"%{busca.strip()}%"
        query = query.where(or_(
            ContaGerencial.descricao.ilike(alvo),
            ContaGerencial.fornecedor_cliente.ilike(alvo),
            ContaGerencial.numero_nota.ilike(alvo),
            ContaGerencial.numero_lancamento.ilike(alvo),
        ))
    contas = session.exec(
        query.order_by(ContaGerencial.data_vencimento.desc()).limit(LIMITE_COMPRAS)
    ).all()
    return [rubrica_folha.resumo_compra(c) for c in contas]


@router.get("/folha-pagamento/{folha_id}/rubricas")
def listar_rubricas_folha(
    folha_id: int,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """As rubricas lançadas nesta folha, vencimentos primeiro."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    folha = _folha_da_fazenda(session, folha_id, fazenda_id)
    rubricas = session.exec(select(FolhaRubrica).where(FolhaRubrica.folha_id == folha.id)).all()
    compras = rubrica_folha.compras_das_rubricas(session, list(rubricas))
    ordenadas = sorted(
        rubricas, key=lambda r: (0 if r.especie == rubrica_folha.ESPECIE_VENCIMENTO else 1, r.id or 0),
    )
    return [
        _rubrica_resposta(r, compras.get(r.conta_gerencial_id) if r.conta_gerencial_id else None)
        for r in ordenadas
    ]


@router.post("/folha-pagamento/{folha_id}/rubricas")
def criar_rubrica_folha(
    folha_id: int,
    dados: RubricaFolhaIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Acrescenta um vencimento ou um desconto ao holerite da competência."""
    folha = _folha_da_fazenda(session, folha_id, fazenda_id)
    _exigir_folha_aberta(folha)
    verbete = _validar_entrada(dados)

    conta: ContaGerencial | None = None
    if dados.especie == rubrica_folha.ESPECIE_DESCONTO and verbete.get("exige_compra"):
        if not dados.conta_gerencial_id:
            raise HTTPException(status_code=400, detail="Escolha a compra que está sendo descontada")
        conta = _compra_da_fazenda(session, dados.conta_gerencial_id, fazenda_id)

    rubrica = FolhaRubrica(
        fazenda_id=fazenda_id,
        folha_id=folha.id,
        pessoa_id=folha.pessoa_id,
        competencia=folha.competencia,
        especie=dados.especie,
        codigo=dados.codigo,
        descricao=(dados.descricao or "").strip() or None,
        valor=round(dados.valor, 2),
        # Enquadramento COPIADO do catálogo (ver models/folha_rubrica.py): o
        # recibo já emitido não muda de conteúdo se a lei ou o entendimento
        # mudarem depois.
        natureza=verbete.get("natureza", rubrica_folha.NATUREZA_SALARIAL),
        incide_inss=bool(verbete.get("incide_inss")),
        incide_irrf=bool(verbete.get("incide_irrf")),
        incide_fgts=bool(verbete.get("incide_fgts")),
        incorpora_base=bool(verbete.get("incorpora_base")),
        # `conta_gerencial_id` só sobrevive no código que EXIGE compra: um
        # desconto de valor com uma FK pendurada mostraria no recibo uma
        # origem que não explica o valor.
        conta_gerencial_id=conta.id if conta else None,
        numero_lancamento=conta.numero_lancamento if conta else None,
        usuario_id=user.id,
    )
    # `flush` e NÃO `commit`: a rubrica precisa existir para `_recalcular_folha`
    # somá-la, mas tudo — linha, líquido, retenções, conta a pagar e a
    # incorporação do aumento — tem de cair junto se algo falhar no meio. Uma
    # rubrica commitada sozinha deixaria o holerite mostrando um valor que o
    # líquido não tem.
    session.add(rubrica)
    session.flush()

    _recalcular_folha(session, folha)
    incorporacao = (
        _propagar_aumento(session, folha, rubrica.valor, fazenda_id) if rubrica.incorpora_base else None
    )
    session.commit()
    session.refresh(rubrica)
    session.refresh(folha)
    return {
        **_rubrica_resposta(rubrica, rubrica_folha.resumo_compra(conta) if conta else None),
        "valor_liquido_folha": folha.valor_liquido,
        "incorporacao": incorporacao,
    }


@router.put("/folha-pagamento/rubricas/{rubrica_id}")
def atualizar_rubrica_folha(
    rubrica_id: int,
    dados: RubricaFolhaEditIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Corrige o valor (ou a descrição) de uma rubrica já lançada."""
    rubrica = _rubrica_da_fazenda(session, rubrica_id, fazenda_id)
    folha = _folha_da_fazenda(session, rubrica.folha_id, fazenda_id)
    _exigir_folha_aberta(folha)
    _validar_valor(dados.valor)

    # A DIFERENÇA é o que se propaga quando a rubrica é o aumento: corrigir de
    # R$ 300 para R$ 500 tem que mexer R$ 200 no salário-base, não R$ 500 (que
    # somaria o aumento inteiro uma segunda vez sobre uma base que já o tinha).
    diferenca = round(dados.valor - rubrica.valor, 2)
    rubrica.valor = round(dados.valor, 2)
    rubrica.descricao = (dados.descricao or "").strip() or None
    session.add(rubrica)
    session.flush()

    _recalcular_folha(session, folha)
    incorporacao = (
        _propagar_aumento(session, folha, diferenca, fazenda_id)
        if rubrica.incorpora_base and diferenca else None
    )
    session.commit()
    session.refresh(rubrica)
    session.refresh(folha)
    compras = rubrica_folha.compras_das_rubricas(session, [rubrica])
    return {
        **_rubrica_resposta(rubrica, compras.get(rubrica.conta_gerencial_id)),
        "valor_liquido_folha": folha.valor_liquido,
        "incorporacao": incorporacao,
    }


@router.delete("/folha-pagamento/rubricas/{rubrica_id}")
def excluir_rubrica_folha(
    rubrica_id: int,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Remove a linha do holerite e desfaz o efeito dela — inclusive a
    incorporação do aumento, que volta atrás pelo mesmo caminho (ver
    `_propagar_aumento`)."""
    rubrica = _rubrica_da_fazenda(session, rubrica_id, fazenda_id)
    folha = _folha_da_fazenda(session, rubrica.folha_id, fazenda_id)
    _exigir_folha_aberta(folha)

    incorporava = rubrica.incorpora_base
    valor = rubrica.valor
    session.delete(rubrica)
    session.flush()

    _recalcular_folha(session, folha)
    incorporacao = _propagar_aumento(session, folha, -valor, fazenda_id) if incorporava else None
    session.commit()
    session.refresh(folha)
    return {"ok": True, "valor_liquido_folha": folha.valor_liquido, "incorporacao": incorporacao}
