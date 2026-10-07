"""
Regras do Caixa dos funcionários que são usadas FORA do router do caixa:

- `valor_da_retencao`: quanto a folha de uma competência retém, a partir do
  combinado (`CaixaRetencao`).
- `lancar_retencao_da_folha`: no pagamento da folha, grava no caixa o que foi
  retido (movimento + despesa baixada no Financeiro).
- `reverter_retencao_da_folha`: no estorno do pagamento da folha, desfaz isso.
- `estornar_movimento`: o estorno de um movimento (o mesmo do endpoint).

Contabilidade (mesma convenção do vale): a folha lança como despesa o LÍQUIDO que
sai do caixa; o valor retido vira, no pagamento, uma despesa de pessoal baixada
("Caixa do funcionário"), de modo que o gasto total continua sendo o bruto. A
retirada posterior do saldo não gera despesa nova.
"""
from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlmodel import Session, select

from fazenda.models import CaixaMovimento, CaixaRetencao, ContaGerencial, FolhaRubrica, Pessoa

CODIGO_RUBRICA = "retencao_caixa"
CATEGORIA_TERMO = "Termo de retenção do caixa"
TIPO_DOC_ENTRADA = "Caixa do funcionário"
TIPO_DOC_ESTORNO = "Estorno caixa do funcionário"


# Tipo de pessoa (CSV em Pessoa.tipo) → grupo mostrado nos filtros da tela.
_GRUPO_POR_TIPO = {
    "funcionário": "clt", "funcionario": "clt",
    "empreiteiro": "empreita",
    "prestador de serviços": "contrato", "prestador de servicos": "contrato",
    "diarista": "diaria",
}


def grupos_da_pessoa(pessoa: Pessoa) -> list[str]:
    grupos: list[str] = []
    for parte in (pessoa.tipo or "").split(","):
        g = _GRUPO_POR_TIPO.get(parte.strip().lower())
        if g and g not in grupos:
            grupos.append(g)
    return grupos


def _mes(d: date) -> int:
    return d.year * 12 + d.month - 1


def _mes_da_competencia(competencia: str) -> int:
    ano, mes = competencia.split("-")
    return int(ano) * 12 + int(mes) - 1


def retencao_vigente(cfg: CaixaRetencao | None, competencia: str) -> bool:
    """Autorizada, não pausada e a competência está dentro da vigência (início e fim por mês)."""
    if cfg is None or not cfg.autorizada or cfg.pausada:
        return False
    m = _mes_da_competencia(competencia)
    if m < _mes(cfg.inicio):
        return False
    fim = cfg.fim
    if cfg.revogada_em is not None and (fim is None or cfg.revogada_em < fim):
        fim = cfg.revogada_em
    return fim is None or m <= _mes(fim)


def acumulado_retido(session: Session, pessoa_id: int, fazenda_id: int | None) -> float:
    """Soma das retenções ainda de pé (não estornadas) da pessoa."""
    query = select(CaixaMovimento).where(CaixaMovimento.pessoa_id == pessoa_id, CaixaMovimento.tipo == "retencao")
    if fazenda_id is not None:
        query = query.where(CaixaMovimento.fazenda_id == fazenda_id)
    movs = list(session.exec(query).all())
    estornados = {
        m.estorna_id for m in session.exec(
            select(CaixaMovimento).where(CaixaMovimento.pessoa_id == pessoa_id, CaixaMovimento.tipo == "estorno")
        ).all() if m.estorna_id
    }
    total = sum(m.valor for m in movs if m.id not in estornados)
    # A parte que foi para um caixa do time também conta no teto do combinado.
    from fazenda.models import CaixaTimeMovimento, FolhaPagamento

    folhas = list(session.exec(select(FolhaPagamento.id).where(FolhaPagamento.pessoa_id == pessoa_id)).all())
    if folhas:
        tm = session.exec(select(CaixaTimeMovimento).where(
            CaixaTimeMovimento.folha_id.in_(folhas), CaixaTimeMovimento.tipo.in_(("retencao", "estorno")))).all()
        revertidos = {m.estorna_id for m in tm if m.tipo == "estorno" and m.estorna_id}
        total += sum(m.valor for m in tm if m.tipo == "retencao" and m.id not in revertidos)
    return round(total, 2)


def valor_da_retencao(
    cfg: CaixaRetencao | None, pessoa: Pessoa, competencia: str, acumulado: float,
) -> float:
    """Valor a reter na competência (0 se nada). Percentual incide sobre o salário-base."""
    if not retencao_vigente(cfg, competencia):
        return 0.0
    if cfg.forma == "percentual":
        base = float(getattr(pessoa, "salario_base", None) or 0)
        valor = round(base * float(cfg.valor or 0) / 100, 2)
    else:
        valor = round(float(cfg.valor or 0), 2)
    if cfg.teto is not None:
        valor = min(valor, round(cfg.teto - acumulado, 2))
    return max(valor, 0.0)


def retencao_da_pessoa(session: Session, pessoa_id: int, fazenda_id: int | None) -> CaixaRetencao | None:
    query = select(CaixaRetencao).where(CaixaRetencao.pessoa_id == pessoa_id)
    if fazenda_id is not None:
        query = query.where(CaixaRetencao.fazenda_id == fazenda_id)
    return session.exec(query).first()


def termo_anexado(session: Session, pessoa_id: int, fazenda_id: int | None) -> bool:
    from fazenda.models import PessoaAnexo
    query = select(PessoaAnexo).where(PessoaAnexo.pessoa_id == pessoa_id, PessoaAnexo.categoria == CATEGORIA_TERMO)
    if fazenda_id is not None:
        query = query.where(PessoaAnexo.fazenda_id == fazenda_id)
    return session.exec(query).first() is not None


def termo_pendente(cfg: CaixaRetencao | None, anexado: bool, hoje: date | None = None) -> bool:
    """Retenção ainda em vigor (autorizada, não revogada/expirada) e sem termo anexado."""
    if cfg is None or not cfg.autorizada or anexado:
        return False
    hoje = hoje or date.today()
    fim = cfg.fim
    if cfg.revogada_em is not None and (fim is None or cfg.revogada_em < fim):
        fim = cfg.revogada_em
    return fim is None or _mes(hoje) <= _mes(fim)


def _saldo_da_pessoa(session: Session, pessoa_id: int, fazenda_id: int | None) -> float:
    query = select(CaixaMovimento).where(CaixaMovimento.pessoa_id == pessoa_id)
    if fazenda_id is not None:
        query = query.where(CaixaMovimento.fazenda_id == fazenda_id)
    return round(sum(m.valor for m in session.exec(query).all()), 2)


def estornar_movimento(
    session: Session, original: CaixaMovimento, motivo: str, usuario_id: int | None, fazenda_id: int | None,
    *, exigir_saldo: bool = True,
) -> CaixaMovimento:
    """Cria o movimento contrário (data de HOJE). Entrada da fazenda devolve também a
    receita contrária no Financeiro. Não commita: quem chama decide a transação."""
    from fazenda.api.routers.financeiro import _proximo_numero_lancamento

    if original.tipo == "estorno":
        raise HTTPException(status_code=409, detail="Um estorno não pode ser estornado")
    ja = session.exec(select(CaixaMovimento).where(CaixaMovimento.estorna_id == original.id)).first()
    if ja is not None:
        raise HTTPException(status_code=409, detail="Este movimento já foi estornado")
    if exigir_saldo and original.valor > 0 and _saldo_da_pessoa(session, original.pessoa_id, fazenda_id) - original.valor < 0:
        raise HTTPException(
            status_code=409,
            detail="O saldo desta entrada já foi usado em retirada(s). Estorne a retirada primeiro.",
        )
    hoje = date.today()
    novo = CaixaMovimento(
        fazenda_id=fazenda_id, pessoa_id=original.pessoa_id, tipo="estorno", valor=-original.valor, data=hoje,
        motivo=f"Estorno de {original.numero_lancamento or original.numero_recibo or f'#{original.id}'}: {motivo}",
        estorna_id=original.id, usuario_id=usuario_id,
    )
    if original.lancamento_id:
        conta_original = session.get(ContaGerencial, original.lancamento_id)
        if conta_original is not None:
            numero = _proximo_numero_lancamento(session, hoje.year)
            contra = ContaGerencial(
                numero_lancamento=numero,
                descricao=f"Estorno de {conta_original.numero_lancamento} · {conta_original.fornecedor_cliente or ''} · {motivo}"[:500],
                data_vencimento=hoje, data_competencia=hoje.replace(day=1),
                fornecedor_cliente=conta_original.fornecedor_cliente, tipo_documento=TIPO_DOC_ESTORNO,
                centro_custo=conta_original.centro_custo, valor_total=conta_original.valor_total,
                parcela_num=1, parcela_total=1, tipo="receita", origem="auto",
                data_pagamento=hoje, valor_pago=conta_original.valor_total,
                conta_bancaria=conta_original.conta_bancaria, forma_pagamento="caixa_funcionario",
                fazenda_id=fazenda_id,
            )
            session.add(contra)
            session.flush()
            novo.lancamento_id = contra.id
            novo.numero_lancamento = numero
    session.add(novo)
    session.flush()
    return novo


def _partes_da_retencao(session: Session, folha, valor: float) -> tuple[float, float, int | None]:
    """(parte no caixa individual, parte no caixa do time, time_id). Destino "time"/"dividir"
    sem um caixa do time válido e ativo da fazenda volta ao individual — dinheiro retido
    nunca fica sem dono por causa de um combinado desatualizado."""
    from fazenda.models import CaixaTime

    cfg = retencao_da_pessoa(session, folha.pessoa_id, folha.fazenda_id)
    if cfg is None or cfg.destino not in ("time", "dividir") or not cfg.time_id:
        return valor, 0.0, None
    t = session.get(CaixaTime, cfg.time_id)
    if t is None or not t.ativo or t.fazenda_id != folha.fazenda_id:
        return valor, 0.0, None
    parte_time = valor if cfg.destino == "time" else round(valor * min(max(cfg.pct_time, 0.0), 100.0) / 100, 2)
    return round(valor - parte_time, 2), parte_time, t.id


def _conta_da_retencao(session: Session, folha, pessoa, valor: float, data: date, rotulo: str) -> tuple[ContaGerencial, str]:
    from fazenda.api.routers.financeiro import _proximo_numero_lancamento

    numero = _proximo_numero_lancamento(session, data.year)
    nome = pessoa.nome if pessoa else "—"
    conta = ContaGerencial(
        numero_lancamento=numero,
        descricao=f"Retenção em folha{rotulo} · {nome} · competência {folha.competencia}"[:500],
        data_vencimento=data, data_competencia=data.replace(day=1),
        fornecedor_cliente=nome, tipo_documento=TIPO_DOC_ENTRADA, centro_custo="Pecuária Leiteira",
        valor_total=valor, parcela_num=1, parcela_total=1, tipo="despesa", origem="auto",
        data_pagamento=data, valor_pago=valor, forma_pagamento="caixa_funcionario",
        fazenda_id=folha.fazenda_id,
    )
    session.add(conta)
    session.flush()
    return conta, numero


def lancar_retencao_da_folha(session: Session, folha) -> None:
    """No pagamento da folha: o que foi retido entra no caixa da pessoa (e/ou do time, conforme
    o combinado). Cada parte vira uma despesa baixada. Idempotente."""
    from fazenda.models import CaixaTimeMovimento

    if folha.id is None:
        session.flush()
    rubrica = session.exec(
        select(FolhaRubrica).where(FolhaRubrica.folha_id == folha.id, FolhaRubrica.codigo == CODIGO_RUBRICA)
    ).first()
    if rubrica is None or rubrica.valor <= 0:
        return
    existentes = session.exec(
        select(CaixaMovimento).where(CaixaMovimento.folha_id == folha.id, CaixaMovimento.tipo == "retencao")
    ).all()
    estornados = {m.estorna_id for m in session.exec(
        select(CaixaMovimento).where(CaixaMovimento.pessoa_id == folha.pessoa_id, CaixaMovimento.tipo == "estorno")
    ).all() if m.estorna_id}
    if any(m.id not in estornados for m in existentes):
        return
    time_existentes = session.exec(
        select(CaixaTimeMovimento).where(CaixaTimeMovimento.folha_id == folha.id, CaixaTimeMovimento.tipo == "retencao")
    ).all()
    time_estornados = {m.estorna_id for m in session.exec(
        select(CaixaTimeMovimento).where(CaixaTimeMovimento.tipo == "estorno", CaixaTimeMovimento.folha_id == folha.id)
    ).all() if m.estorna_id}
    if any(m.id not in time_estornados for m in time_existentes):
        return
    pessoa = session.get(Pessoa, folha.pessoa_id)
    data = folha.data_pagamento or date.today()
    ind, para_time, time_id = _partes_da_retencao(session, folha, round(rubrica.valor, 2))
    if ind > 0:
        conta, numero = _conta_da_retencao(session, folha, pessoa, ind, data, "")
        session.add(CaixaMovimento(
            fazenda_id=folha.fazenda_id, pessoa_id=folha.pessoa_id, tipo="retencao", valor=ind, data=data,
            motivo=f"Retenção em folha · competência {folha.competencia}",
            lancamento_id=conta.id, numero_lancamento=numero, folha_id=folha.id,
        ))
    if para_time > 0:
        conta, numero = _conta_da_retencao(session, folha, pessoa, para_time, data, " (caixa do time)")
        session.add(CaixaTimeMovimento(
            fazenda_id=folha.fazenda_id, time_id=time_id, tipo="retencao", valor=para_time, data=data,
            motivo=f"Retenção em folha · {pessoa.nome if pessoa else '—'} · competência {folha.competencia}",
            lancamento_id=conta.id, numero_lancamento=numero, folha_id=folha.id,
        ))
    session.flush()


def reverter_retencao_da_folha(session: Session, folha, usuario_id: int | None = None) -> None:
    """No estorno do pagamento da folha: estorna o que ela reteve (caixa da pessoa e do time).
    Recusa (409) se esse dinheiro já foi retirado do caixa individual ou repartido em rateio —
    quem usou o dinheiro precisa desfazer isso antes."""
    from fazenda.rules import caixa_time as regras_time

    estornados = {m.estorna_id for m in session.exec(
        select(CaixaMovimento).where(CaixaMovimento.pessoa_id == folha.pessoa_id, CaixaMovimento.tipo == "estorno")
    ).all() if m.estorna_id}
    for m in session.exec(
        select(CaixaMovimento).where(CaixaMovimento.folha_id == folha.id, CaixaMovimento.tipo == "retencao")
    ).all():
        if m.id in estornados:
            continue
        try:
            estornar_movimento(session, m, f"pagamento da folha {folha.competencia} estornado", usuario_id, folha.fazenda_id)
        except HTTPException as exc:
            if exc.status_code == 409 and "retirada" in str(exc.detail):
                raise HTTPException(
                    status_code=409,
                    detail="O valor retido nesta folha já foi retirado do caixa do funcionário. "
                           "Estorne a retirada antes de estornar o pagamento da folha.",
                ) from None
            raise
    regras_time.estornar_retencoes_do_time(session, folha, usuario_id)


def termos_pendentes(session: Session, fazenda_id: int | None) -> list[dict]:
    """Retenções autorizadas e em vigor, de pessoa ativa, SEM termo anexado: é o que a
    Agenda e o Fechamento da folha avisam."""
    from fazenda.models import PessoaAnexo

    query = select(CaixaRetencao).where(CaixaRetencao.autorizada == True)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(CaixaRetencao.fazenda_id == fazenda_id)
    configs = list(session.exec(query).all())
    if not configs:
        return []
    query_anexos = select(PessoaAnexo.pessoa_id).where(PessoaAnexo.categoria == CATEGORIA_TERMO)
    if fazenda_id is not None:
        query_anexos = query_anexos.where(PessoaAnexo.fazenda_id == fazenda_id)
    com_termo = set(session.exec(query_anexos).all())
    saida = []
    for cfg in configs:
        pessoa = session.get(Pessoa, cfg.pessoa_id)
        if pessoa is None or not pessoa.ativo:
            continue
        if termo_pendente(cfg, cfg.pessoa_id in com_termo):
            saida.append({"pessoa_id": pessoa.id, "nome": pessoa.nome, "desde": cfg.autorizada_em or cfg.inicio})
    return sorted(saida, key=lambda x: x["nome"])
