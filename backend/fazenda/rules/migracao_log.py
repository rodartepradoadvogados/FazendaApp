"""
Log auditável dos backfills do Financeiro (Fase A, R6) e a reversão por lote.

Contrato de todo backfill desta fase:
  - roda por COMANDO (nunca sozinho dentro de uma migração), em dry-run por
    padrão; só grava com `--aplicar`;
  - nunca reescreve `valor_total`/`valor_pago` histórico: só preenche colunas
    novas (ex.: `natureza_fin`) ou cria itens novos marcados com `gerado_por`;
  - linha CRIADA pelo backfill vira uma linha de log com `campo = "__criado__"`;
    a reversão APAGA a linha, só se ela ainda for a que o backfill criou. Duas
    formas de conferir: pela MARCA (`gerado_por`, os itens da folha do PR 2/3)
    ou pelo RETRATO dos campos (`{"retrato": ...}`, as notas do cartão do PR 5:
    a nota de uma fatura aberta que foi paga depois vira conflito e fica);
  - cada campo alterado vira UMA linha em `migracao_log_financeiro` com o
    valor de antes e o de depois (JSON), a fazenda, o lote e o motivo;
  - `reverter_lote` devolve o valor de antes, linha a linha, e só se o valor
    atual ainda for o que o backfill gravou (se alguém mudou à mão depois, a
    linha é reportada como conflito e NÃO é sobrescrita).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlmodel import Session, select

# tabela -> modelo; só o que os backfills desta fase podem tocar.
def _modelos() -> dict[str, Any]:
    from fazenda.models import (
        ContaGerencial, ContaPadraoOrigem, LancamentoCartao, LancamentoItem, Patrimonio, PlanoContaGerencial,
    )

    return {
        "conta_gerencial": ContaGerencial,
        "lancamento_item": LancamentoItem,
        "plano_conta_gerencial": PlanoContaGerencial,
        "patrimonio": Patrimonio,
        "lancamento_cartao": LancamentoCartao,
        "conta_padrao_origem": ContaPadraoOrigem,
    }


# Campos que um backfill pode alterar. valor_total/valor_pago NUNCA entram aqui.
CAMPOS_PERMITIDOS: dict[str, frozenset[str]] = {
    # conta_corrente_id: vínculo do pagamento com a conta (PR 6, backfill_conta_corrente).
    # codigo_conta: a conta de uma nota SEM itens, mudada pela tela Classificar (classificacao_manual_v1).
    "conta_gerencial": frozenset({"natureza_fin", "conta_corrente_id", "codigo_conta"}),
    # PR 2/3 (backfill dos itens automáticos): a conta de um item GERADO que
    # nasceu sem conta configurada. Item de gente nunca passa por aqui.
    "lancamento_item": frozenset({"natureza_fin", "codigo_conta_gerencial", "nome_conta_gerencial"}),
    # linha_dre: a linha da DRE da conta, mudada pela tela Classificar (classificacao_manual_v1).
    "plano_conta_gerencial": frozenset({"natureza_fin", "linha_dre"}),
    "patrimonio": frozenset({"centro_custo"}),
    # numero_lancamento: a nota criada para a compra (PR 5, backfill_cartao_por_item).
    "lancamento_cartao": frozenset({"numero_lancamento"}),
    # backfill_contas_origem: a conta padrão de `vale` e `caixa_retencao` onde
    # estava vazia (a linha da origem pode ser criada ou só preenchida).
    "conta_padrao_origem": frozenset({"codigo_conta_gerencial"}),
}

# Pseudocampo de uma linha de log que registra um REGISTRO NOVO criado pelo
# backfill (o item gerado de uma folha antiga — PR 2/3; a nota de uma compra no
# cartão — PR 5). Reverter = apagar a linha criada, só se ela ainda for o que o
# backfill criou: pela marca (`gerado_por`) ou pelo retrato dos campos abaixo.
CAMPO_CRIADO = "__criado__"
TABELAS_CRIAVEIS = frozenset({"lancamento_item", "conta_gerencial", "conta_padrao_origem"})
RETRATO_LINHA_CRIADA: dict[str, tuple[str, ...]] = {
    "conta_gerencial": ("numero_lancamento", "valor_total", "valor_pago", "data_pagamento", "conta_bancaria",
                        "conta_corrente_id", "fatura_cartao_id", "gerado_por"),
    "lancamento_item": ("numero_lancamento", "valor_total", "codigo_conta_gerencial"),
    "conta_padrao_origem": ("origem", "codigo_conta_gerencial"),
}


def novo_lote(prefixo: str = "lote") -> str:
    return f"{prefixo}-{datetime.utcnow():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8]}"


def _json(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, default=str)


def registrar_mudanca(
    session: Session, *, fazenda_id: int | None, lote: str, migracao: str,
    tabela: str, registro, campo: str, valor_depois: Any, motivo: str | None = None,
):
    """Aplica `registro.campo = valor_depois` e grava a linha de log. Não faz
    commit (quem chama decide a transação)."""
    from fazenda.models import MigracaoLogFinanceiro

    if campo not in CAMPOS_PERMITIDOS.get(tabela, frozenset()):
        raise ValueError(f"backfill não pode alterar {tabela}.{campo}")
    if getattr(registro, "fazenda_id", fazenda_id) != fazenda_id:
        raise ValueError(f"{tabela}#{registro.id} não pertence à fazenda {fazenda_id}")
    antes = getattr(registro, campo)
    setattr(registro, campo, valor_depois)
    session.add(registro)
    linha = MigracaoLogFinanceiro(
        fazenda_id=fazenda_id, lote=lote, migracao=migracao, tabela=tabela,
        registro_id=registro.id, campo=campo,
        valor_antes=_json(antes), valor_depois=_json(valor_depois), motivo=motivo,
    )
    session.add(linha)
    return linha


def _retrato(tabela: str, registro) -> dict:
    return json.loads(_json({c: getattr(registro, c) for c in RETRATO_LINHA_CRIADA[tabela]}))


def registrar_criacao(
    session: Session, *, fazenda_id: int | None, lote: str, migracao: str,
    tabela: str, registro, marca: str | None = None, motivo: str | None = None,
):
    """Grava a linha de log de um registro NOVO (já com id: quem chama dá o
    flush). `marca` identifica a linha como do backfill (para itens, o
    `gerado_por`); sem marca, guarda o retrato dos campos de
    RETRATO_LINHA_CRIADA. Não faz commit."""
    from fazenda.models import MigracaoLogFinanceiro

    if tabela not in TABELAS_CRIAVEIS or (marca is None and tabela not in RETRATO_LINHA_CRIADA):
        raise ValueError(f"backfill não pode criar linhas em {tabela}")
    if getattr(registro, "fazenda_id", fazenda_id) != fazenda_id:
        raise ValueError(f"{tabela}#{registro.id} não pertence à fazenda {fazenda_id}")
    linha = MigracaoLogFinanceiro(
        fazenda_id=fazenda_id, lote=lote, migracao=migracao, tabela=tabela,
        registro_id=registro.id, campo=CAMPO_CRIADO, valor_antes=_json(None),
        valor_depois=_json(marca) if marca is not None else _json({"retrato": _retrato(tabela, registro)}),
        motivo=motivo,
    )
    session.add(linha)
    return linha


@dataclass
class ResultadoReversao:
    lote: str
    revertidas: int = 0
    ja_revertidas: int = 0
    conflitos: list[dict] = field(default_factory=list)
    nao_encontradas: list[dict] = field(default_factory=list)


def reverter_lote(session: Session, lote: str, *, fazenda_id: int | None, aplicar: bool = False) -> ResultadoReversao:
    """Desfaz um lote (na ordem inversa). `fazenda_id` obrigatório e conferido
    linha a linha: um lote nunca reverte dado de outra fazenda. Em dry-run
    (padrão) só conta; com `aplicar=True` grava (sem commit)."""
    from fazenda.models import MigracaoLogFinanceiro

    if not isinstance(fazenda_id, int):
        raise ValueError("Informe a fazenda do lote a reverter.")
    linhas = session.exec(
        select(MigracaoLogFinanceiro)
        .where(MigracaoLogFinanceiro.lote == lote, MigracaoLogFinanceiro.fazenda_id == fazenda_id)
        .order_by(MigracaoLogFinanceiro.id.desc())
    ).all()
    resultado = ResultadoReversao(lote=lote)
    modelos = _modelos()
    agora = datetime.utcnow()
    for linha in linhas:
        if linha.revertido_em is not None:
            resultado.ja_revertidas += 1
            continue
        modelo = modelos.get(linha.tabela)
        registro = session.get(modelo, linha.registro_id) if modelo else None
        if registro is None or getattr(registro, "fazenda_id", None) != fazenda_id:
            resultado.nao_encontradas.append({"tabela": linha.tabela, "id": linha.registro_id})
            continue
        if linha.campo == CAMPO_CRIADO:
            # Registro criado pelo backfill: reverter = apagar, se ainda é o dele.
            gravado = json.loads(linha.valor_depois or "null")
            if isinstance(gravado, dict) and "retrato" in gravado:
                atual_criado, esperado = _retrato(linha.tabela, registro), gravado["retrato"]
            else:
                atual_criado, esperado = getattr(registro, "gerado_por", None), gravado
            if _json(atual_criado) != _json(esperado):
                resultado.conflitos.append({
                    "tabela": linha.tabela, "id": linha.registro_id, "campo": linha.campo,
                    "valor_atual": atual_criado,
                    "valor_gravado_pelo_backfill": json.loads(linha.valor_depois or "null"),
                })
                continue
            resultado.revertidas += 1
            if aplicar:
                session.delete(registro)
                linha.revertido_em = agora
                session.add(linha)
            continue
        atual = getattr(registro, linha.campo)
        if _json(atual) != linha.valor_depois:
            resultado.conflitos.append({
                "tabela": linha.tabela, "id": linha.registro_id, "campo": linha.campo,
                "valor_atual": atual, "valor_gravado_pelo_backfill": json.loads(linha.valor_depois or "null"),
            })
            continue
        resultado.revertidas += 1
        if aplicar:
            setattr(registro, linha.campo, json.loads(linha.valor_antes or "null"))
            session.add(registro)
            linha.revertido_em = agora
            session.add(linha)
    return resultado
