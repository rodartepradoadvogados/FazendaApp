"""
Saldo das contas correntes e data de caixa — Fase A, PR 6 (P0-6 da auditoria;
ver docs/financeiro-regras-v2.md §9). Só vale com a flag `financeiro_regras_v2`.

O SALDO DE HOJE, com as regras novas:

    saldo = saldo_abertura
          + Σ pagamentos/recebimentos da conta com  data_saldo_abertura < data de caixa ≤ hoje
          ± transferências entre contas com         data_saldo_abertura < data ≤ hoje

O que muda em relação ao saldo antigo (`calcular_saldos_contas_correntes` sem a
flag), e por quê:

  1. Parte do SALDO DE ABERTURA conferido com o extrato (campo na conta, decisão
     Q12). Sem abertura informada o número é só a soma dos movimentos — a tela
     mostra a pendência "informe o saldo de abertura" em vez de fingir um saldo.
  2. Pagamento com data FUTURA é AGENDADO (decisão do dono, Q13): não entra no
     saldo de hoje; aparece no Caixa Real na data dele. O saldo antigo somava um
     pagamento datado em 2031 no saldo de 2026.
  3. Casa a conta pela FK `conta_corrente_id`; só quando ela está vazia (histórico
     ainda não ligado pelo backfill) cai no texto exato do rótulo, como antes.
  4. Pago sem `valor_pago` (dado legado: o L6 da auditoria) vale o valor da
     parcela — o mesmo que o Livro do front já mostrava (`valorRealizado`). O
     banco NÃO é reescrito: é leitura.
  5. Cartão avulso (`forma_pagamento="credito"`): o dinheiro sai do banco no
     vencimento do cartão (`data_vencimento_cartao`), não na compra (R3).
  6. Nota gerada pelo backfill do cartão já pago (`gerado_por="backfill_cartao"`)
     NÃO entra: o dinheiro daquela fatura já está contado na nota genérica.

Funções puras (recebem a linha já lida); a consulta ao banco fica no router.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

GERADO_POR_RETIRADA_CAIXA = "caixa_retirada"
GERADO_POR_BACKFILL_CARTAO = "backfill_cartao"
GERADO_POR_BACKFILL_CARTAO_ABERTA = "backfill_cartao_aberta"

AVISO_SEM_SALDO_ABERTURA = (
    "Informe o saldo de abertura desta conta (o saldo do extrato numa data) para o saldo de hoje "
    "valer o do banco. Sem ele, o número é só a soma dos lançamentos."
)


def data_caixa(conta) -> date | None:
    """Data em que o dinheiro sai/entra do banco (R3): a do pagamento; no cartão
    avulso, o vencimento do cartão. None = ainda não pago."""
    if getattr(conta, "data_pagamento", None) is None:
        return None
    if (getattr(conta, "forma_pagamento", None) or "") == "credito" and getattr(conta, "data_vencimento_cartao", None):
        return conta.data_vencimento_cartao
    return conta.data_pagamento


def valor_pago_efetivo(conta) -> float:
    """O que de fato saiu/entrou: `valor_pago`; pago sem ele (legado) = o valor
    da parcela (nunca 0 — era o que fazia o saldo do back divergir do Livro)."""
    if getattr(conta, "valor_pago", None) is not None:
        return float(conta.valor_pago)
    return float(getattr(conta, "valor_total", None) or 0.0)


def conta_entra_no_caixa(conta) -> bool:
    """Nota de classificação do backfill do cartão já pago não move dinheiro."""
    return getattr(conta, "gerado_por", None) != GERADO_POR_BACKFILL_CARTAO


def eh_agendado(conta, hoje: date) -> bool:
    """Pago com data de caixa depois de hoje = agendado (não entra no saldo de hoje)."""
    dc = data_caixa(conta)
    return dc is not None and dc > hoje


@dataclass
class SaldoConta:
    conta_id: int
    saldo_abertura: float | None
    data_saldo_abertura: date | None
    ate: date
    saldo: float = 0.0
    # Pagamentos/recebimentos já baixados com data de caixa depois de `ate`.
    agendados: list[dict] = field(default_factory=list)

    @property
    def pendente_abertura(self) -> bool:
        return self.saldo_abertura is None or self.data_saldo_abertura is None

    @property
    def agendado_liquido(self) -> float:
        return round(sum(a["valor"] if a["tipo"] == "receita" else -a["valor"] for a in self.agendados), 2)


def novo_saldo(conta_id: int, saldo_abertura: float | None, data_abertura: date | None, ate: date) -> SaldoConta:
    tem_abertura = saldo_abertura is not None and data_abertura is not None
    return SaldoConta(
        conta_id=conta_id,
        saldo_abertura=round(float(saldo_abertura), 2) if tem_abertura else None,
        data_saldo_abertura=data_abertura if tem_abertura else None,
        ate=ate,
        saldo=round(float(saldo_abertura), 2) if tem_abertura else 0.0,
    )


def aplicar_lancamento(s: SaldoConta, conta) -> None:
    """Soma (receita) ou subtrai (despesa) um lançamento PAGO no saldo `s`,
    respeitando a abertura e o "hoje" (`s.ate`)."""
    if not conta_entra_no_caixa(conta):
        return
    dc = data_caixa(conta)
    if dc is None:
        return
    if s.data_saldo_abertura is not None and dc <= s.data_saldo_abertura:
        return  # já está dentro do saldo de abertura conferido
    valor = valor_pago_efetivo(conta)
    if not valor:
        return
    if dc > s.ate:
        s.agendados.append({
            "conta_id": getattr(conta, "id", None), "data": dc, "valor": round(abs(valor), 2),
            "tipo": "receita" if conta.tipo == "receita" else "despesa",
            "descricao": getattr(conta, "descricao", None) or getattr(conta, "numero_lancamento", None),
            "numero_lancamento": getattr(conta, "numero_lancamento", None),
        })
        return
    s.saldo = round(s.saldo + (valor if conta.tipo == "receita" else -valor), 2)


def aplicar_transferencia(s: SaldoConta, data_transf: date, valor: float, entrada: bool) -> None:
    if data_transf is None or data_transf > s.ate:
        return
    if s.data_saldo_abertura is not None and data_transf <= s.data_saldo_abertura:
        return
    s.saldo = round(s.saldo + (valor if entrada else -valor), 2)


# ── Casamento do texto livre `conta_bancaria` com a conta cadastrada ─────────
def _sem_acento(texto: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(ch))


def normalizar_texto(texto: str | None) -> str:
    """Minúsculas, sem acento e só letras/dígitos (espaço, ponto, hífen e "·" somem)."""
    return re.sub(r"[^a-z0-9]", "", _sem_acento(texto or "").lower())


def digitos(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")


@dataclass(frozen=True)
class ContaRef:
    id: int
    banco: str
    agencia: str
    numero_conta: str
    rotulo: str


def casar_conta_corrente(texto: str | None, contas: list[ContaRef]) -> tuple[int | None, str]:
    """(id da conta, regra) para o rótulo livre `texto`. Regras, na ordem:
    "exato" (rótulo igual), "normalizado" (o banco aparece no texto e os dígitos da
    agência seguidos dos da conta aparecem em sequência, ignorando
    acento/espaço/pontuação), "banco_unico" (o texto
    é do banco e a fazenda só tem uma conta nele). Sem casamento único devolve
    (None, "ambiguo" | "nao_encontrado") — vai para a lista de revisão."""
    if not texto or not contas:
        return None, "nao_encontrado"
    exatos = [c for c in contas if c.rotulo == texto]
    if len(exatos) == 1:
        return exatos[0].id, "exato"
    if len(exatos) > 1:
        return None, "ambiguo"
    alvo, alvo_dig = normalizar_texto(texto), digitos(texto)
    normalizados = [
        c for c in contas
        if normalizar_texto(c.banco) and normalizar_texto(c.banco) in alvo
        and digitos(c.agencia) and digitos(c.numero_conta)
        and (digitos(c.agencia) + digitos(c.numero_conta)) in alvo_dig
    ]
    if len(normalizados) == 1:
        return normalizados[0].id, "normalizado"
    if len(normalizados) > 1:
        return None, "ambiguo"
    do_banco = [c for c in contas if normalizar_texto(c.banco) and normalizar_texto(c.banco) in alvo]
    # Sem dígito nenhum no texto (só o nome do banco) e uma conta só nesse banco.
    if len(do_banco) == 1 and not alvo_dig:
        return do_banco[0].id, "banco_unico"
    if len(do_banco) > 1:
        return None, "ambiguo"
    return None, "nao_encontrado"
