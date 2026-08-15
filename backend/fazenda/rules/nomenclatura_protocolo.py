"""
Nome automático de um lançamento de protocolo (IATF, Indução de Lactação,
Sanitário, Customizado, Lida) — o usuário não digita mais nome na hora de
lançar; o sistema monta a partir do nome cadastrado (molde) + a data do
primeiro dia + a data do último dia:

    {NOME CADASTRADO} - {D0} A {último dia} (D{inicial} A D{final} - {n} DIAS)

Ex.: "PROTOCOLO DE MASTITE 1 - 05/08/26 A 09/08/26 (D0 A D4 - 5 DIAS)"

IMPORTANTE — gerado UMA VEZ, na hora de lançar, e GRAVADO em
`nome_protocolo`/`nome_protocolo` do lançamento (ver ProtocoloIatfLancamento,
ProtocoloInducaoLancamento, ProtocoloCustomizadoLancamento, LidaLancamento —
todos chamam `gerar_nome_lancamento()` uma única vez dentro da rota de
lançar, ex. `producao.lancar_inducao_lactacao`). NUNCA é recalculado depois:
não há um "trigger" que reprocesse lançamentos antigos quando este módulo
muda, nem uma migração que percorra a tabela renomeando em lote. Isso é
proposital (o nome é um retrato do lançamento no instante em que foi feito),
mas tem uma consequência que precisa ficar clara para quem for investigar um
sintoma "dois nomes diferentes para o que parece a mesma coisa": um
lançamento feito ANTES desta nomenclatura existir, ou renomeado manualmente
depois via `PATCH /central-protocolos/{origem}/{id}/renomear` (ver
central_protocolos.py — fora do escopo deste módulo), fica com o nome antigo
para sempre. Isso NÃO é, por si só, evidência de duas linhas geradas por uma
única ação de lançar — pode ser exatamente isso (nome "cru" do molde,
sem o sufixo de datas abaixo), mas também pode ser um lançamento diferente
de fato, ou uma renomeação manual. Quem for diagnosticar duplicata precisa
olhar o `id`/`criado_em`/animais/dia a dia — nome sozinho não prova nada.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

# Sufixo que gerar_nome_lancamento acrescenta ao nome cadastrado. Usado por
# nome_curto() para desfazer só o que este módulo mesmo montou — nome antigo,
# digitado à mão antes da nomenclatura automática, não casa e fica intacto.
_SUFIXO = re.compile(
    r"\s+-\s+\d{2}/\d{2}/\d{2}\s+A\s+\d{2}/\d{2}/\d{2}\s+\(D\d+\s+A\s+D\d+\s+-\s+\d+\s+DIAS\)\s*$"
)


def gerar_nome_lancamento(nome_base: str, data_d0: date, dia_inicial: int, dia_final: int) -> str:
    data_ultimo = data_d0 + timedelta(days=(dia_final - dia_inicial))
    n_dias = dia_final - dia_inicial + 1
    base = (nome_base or "").strip().upper()
    return (
        f"{base} - {data_d0.strftime('%d/%m/%y')} A {data_ultimo.strftime('%d/%m/%y')} "
        f"(D{dia_inicial} A D{dia_final} - {n_dias} DIAS)"
    )


def nome_curto(nome_protocolo: str) -> str:
    """
    Só o nome cadastrado, sem o intervalo de datas — para o cartão da AGENDA.

    Na Agenda o intervalo é redundante (o cartão já está numa data, e o rótulo
    já termina em "— D7") e ainda entra duas vezes quando dois lançamentos caem
    no mesmo grupo e os nomes são unidos por " + ". O nome completo continua
    gravado e é o que aparece na Central de Protocolos, na ficha do animal e
    nos relatórios.

    Nome antigo (anterior à nomenclatura automática) não tem o sufixo e volta
    inalterado.
    """
    return _SUFIXO.sub("", (nome_protocolo or "").strip()) or nome_protocolo
