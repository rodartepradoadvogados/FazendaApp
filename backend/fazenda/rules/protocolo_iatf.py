"""
Cronograma do protocolo IATF — o único ponto do sistema que sabe calcular
"qual é o dia da inseminação" e "quais são os passos do protocolo".

Até 08/2026 isso era uma constante fixa (PASSOS_PROTOCOLO_IATF em
reproducao.py): D0/D7/D9 de hormônio + D11 de inseminação, sempre, para
qualquer lançamento. Um molde cadastrado com outro espaçamento (existe
protocolo de verdade D0/D8/D10/D12) tinha os dias das etapas simplesmente
IGNORADOS na hora de lançar — as ProtocoloIatfAplicacao nasciam sempre em
0/7/9/11, e o hormônio cadastrado num dia fora desses quatro nunca era
aplicado a etapa nenhuma.

A regra agora é: a inseminação acontece 2 dias depois da ÚLTIMA etapa de
hormônio do protocolo — D9 → D11 no clássico, D12 → D14 num D0/D8/D10/D12.
Esse "+2" é o mesmo intervalo que já existia entre D9 e D11; só deixou de
estar cravado em D9 especificamente.
"""
from __future__ import annotations

# Intervalo entre a última etapa de hormônio e a inseminação — mesmo gap do
# protocolo clássico (D9 → D11), agora aplicado à ÚLTIMA etapa de qualquer
# protocolo, não só quando ela cai em D9.
INTERVALO_ATE_INSEMINACAO_DIAS = 2

# Cronograma clássico (D0/D7/D9 de hormônio + D11 de inseminação) — usado
# quando o lançamento NÃO referencia um molde cadastrado (hormônios digitados
# na hora) e no lançamento retroativo automático (inseminação avulsa sem
# protocolo prévio). Estes dois caminhos não têm "etapas de um molde" para
# derivar o cronograma, então mantêm o padrão histórico.
PASSOS_PROTOCOLO_IATF_PADRAO = [
    (0, "Implante de progesterona + Benzoato de estradiol + Acetato de buserelina (D0)"),
    (7, "Cloprostenol (D7)"),
    (9, "Retirar implante + Cipionato de estradiol + Cloprostenol (D9)"),
    (11, "Inseminação (IATF) — D11"),
]
DIA_INSEMINACAO_PADRAO = 11


def dia_inseminacao(dias_hormonio: list[int]) -> int:
    """A inseminação acontece `INTERVALO_ATE_INSEMINACAO_DIAS` dias depois da
    última etapa de hormônio. Lista vazia cai no padrão clássico (D11) — não
    deveria acontecer (molde sem etapa não passa na validação do cadastro),
    mas não há por que quebrar se acontecer."""
    if not dias_hormonio:
        return DIA_INSEMINACAO_PADRAO
    return max(dias_hormonio) + INTERVALO_ATE_INSEMINACAO_DIAS
