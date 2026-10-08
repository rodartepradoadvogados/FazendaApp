"""
Log auditável dos backfills do Financeiro (Fase A, R6) e a reversão por lote.

Contrato de todo backfill desta fase:
  - roda por COMANDO (nunca sozinho dentro de uma migração), em dry-run por
    padrão; só grava com `--aplicar`;
  - nunca reescreve `valor_total`/`valor_pago` histórico: só preenche colunas
    novas (ex.: `natureza_fin`) ou cria itens novos marcados com `gerado_por`;
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
    from fazenda.models import ContaGerencial, LancamentoItem, Patrimonio, PlanoContaGerencial

    return {
        "conta_gerencial": ContaGerencial,
        "lancamento_item": LancamentoItem,
        "plano_conta_gerencial": PlanoContaGerencial,
        "patrimonio": Patrimonio,
    }


# Campos que um backfill pode alterar. valor_total/valor_pago NUNCA entram aqui.
CAMPOS_PERMITIDOS: dict[str, frozenset[str]] = {
    "conta_gerencial": frozenset({"natureza_fin"}),
    "lancamento_item": frozenset({"natureza_fin"}),
    "plano_conta_gerencial": frozenset({"natureza_fin"}),
    "patrimonio": frozenset({"centro_custo"}),
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
