"""Risco de uma exclusão e o que cada nível exige de quem confirma (Fase 1 do
"Excluir lançamentos").

Funções PURAS, sem sessão nem banco — o servidor recalcula o risco na hora de
confirmar (`POST /exclusoes/confirmar`, `aprovar`) e recusa com 422 quando a
confirmação não corresponde ao nível. A tela só mostra; não é ela que protege.

Níveis (espelham o mockup `fonte/app.js`):
- **baixo**: 1 registro, sem reversão, sem dinheiro em aberto. Botão basta.
- **medio**: tem reversão (estoque/lactação/DEL/saldo) OU dinheiro em aberto OU
  apaga de 2 a 9 registros. Exige motivo.
- **alto**: apaga 10+ registros, ou o tipo força (ficha de animal, cadastro em
  uso). Exige motivo E confirmação digitada (decisão do dono: o número do animal).

A agregação de lote (vários itens de uma vez) fica na Fase 3; aqui o risco é de
UM item.
"""
from __future__ import annotations

from fazenda.rules.exclusao_impacto import Impacto

ORDEM = {"baixo": 0, "medio": 1, "alto": 2}

TEXTOS = {
    "baixo": ("Risco baixo", "Um registro isolado. Nada mais muda."),
    "medio": ("Risco médio", "Mexe em outras coisas (estoque, contas, lactação) ou apaga mais de um. Diga o motivo."),
    "alto": ("Risco alto", "Apaga muita coisa, ou um cadastro em uso. Não dá para desfazer. Confirme digitando."),
}


def _totais(impacto: Impacto) -> tuple[int, int, bool]:
    n = sum((linha.qtd or 1) for linha in impacto.apagar)
    rev = len(impacto.reverter)
    dinheiro_aberto = any(linha.valor for linha in impacto.apagar)
    return n, rev, dinheiro_aberto


def calcular(impacto: Impacto) -> str:
    """Risco de um único item. Respeita um risco já forçado pelo tipo
    (`Impacto.risco` pré-preenchido com "medio"/"alto")."""
    if impacto.risco in ("medio", "alto"):
        return impacto.risco
    n, rev, dinheiro_aberto = _totais(impacto)
    if n >= 10:
        return "alto"
    if rev > 0 or dinheiro_aberto or n > 1:
        return "medio"
    return "baixo"


def porque(impacto: Impacto) -> list[str]:
    """Justificativas em frase curta (para o campo `porque` / a frase "Porque:")."""
    razoes: list[str] = list(impacto.porque)
    if impacto.risco in ("medio", "alto") and not razoes:
        # não duplicar: o tipo já deu a razão quando forçou o risco
        razoes.append("tipo de alto risco")
    n, rev, dinheiro_aberto = _totais(impacto)
    if dinheiro_aberto:
        razoes.append("tem dinheiro em aberto")
    if rev > 0:
        razoes.append("mexe em outros dados (estoque, lactação, saldos)")
    if n > 1:
        razoes.append(f"apaga {n} registros")
    return razoes


def exige_motivo(risco: str, eh_admin: bool) -> bool:
    """Decision #2: admin dá motivo no risco médio também; não-admin sempre."""
    if not eh_admin:
        return True
    return risco in ("medio", "alto")


def exige_confirmacao(risco: str) -> bool:
    """Risco alto exige confirmação digitada (o que digitar é decidido pelo
    tipo: número do animal para ficha, APAGAR para os demais)."""
    return risco == "alto"