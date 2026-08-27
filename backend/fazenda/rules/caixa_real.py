"""
Caixa Real — motor puro da projeção de liquidez (Onda 4).

===========================================================================
ADR — POR QUE O CAIXA REAL NÃO É A DRE (e nunca vai bater com ela)

A DRE (fazenda/rules/dre.py) responde "a fazenda deu lucro?". O Caixa Real
responde "a fazenda tem dinheiro?". São perguntas diferentes e as duas
respostas podem ter SINAIS OPOSTOS no mesmo mês — fazenda lucrativa que
quebra por falta de caixa é o caso clássico, e é exatamente o que esta tela
existe para antecipar.

As duas divergem em quatro pontos, e cada um é uma inversão exata do outro
lado (ver o ADR gêmeo no topo de rules/dre.py):

  ┌────────────────────────────┬──────────────┬──────────────┐
  │                            │ DRE          │ Caixa Real   │
  ├────────────────────────────┼──────────────┼──────────────┤
  │ Depreciação/amortização    │ ENTRA        │ não entra    │
  │   (despesa que não é caixa)│ (linha 11)   │              │
  │ Principal de financiamento │ NÃO entra    │ ENTRA        │
  │   (caixa que não é despesa)│              │ (saída)      │
  │ Nota a prazo               │ na competênc.│ no vencimento│
  │ Investimento (compra de bem)│ não entra   │ ENTRA        │
  │   — vira ativo, não despesa│ (vira ativo) │ (saída)      │
  └────────────────────────────┴──────────────┴──────────────┘

Por isso NÃO existe (e não deve existir) nenhuma conferência do tipo "o
resultado da DRE tem que fechar com a variação do caixa". Elas medem coisas
diferentes de propósito.
===========================================================================

O motor é puro no mesmo espírito de rules/dre.py e rules/rmca.py: recebe o
saldo de partida e a lista de compromissos já achatada, devolve a linha do
tempo pronta. Quem busca no banco é o router.
"""
from __future__ import annotations

from datetime import date, timedelta

# Abaixo deste piso o saldo projetado está "no vermelho de verdade": não é
# alerta de reserva, é falta de dinheiro para honrar o compromisso.
SALDO_CRITICO = 0.0


def _dia(valor) -> date | None:
    """Aceita date ou ISO string — o router passa o que vier do banco."""
    if valor is None or isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except (ValueError, TypeError):
        return None


def projetar_caixa(
    saldo_inicial: float,
    compromissos: list[dict],
    inicio: date,
    dias: int,
    fundo_reserva: float = 0.0,
) -> dict:
    """Linha do tempo diária do saldo de caixa.

    `compromissos`: dicts com `data` (vencimento previsto), `valor` (sempre
    POSITIVO — a magnitude) e `tipo` ("receita" soma, qualquer outro
    subtrai). O sinal é decidido aqui pelo tipo, nunca por um valor negativo
    escondido — mesma regra do operador de linha em rules/dre.py, pela mesma
    razão: valor com sinal embutido é impossível de somar sem ambiguidade.

    Compromisso ANTERIOR a `inicio` (conta vencida e ainda não paga) não é
    descartado: entra no primeiro dia da projeção. Ele é dívida real e já
    está pesando no caixa — jogá-lo fora faria a projeção parecer mais
    saudável do que é, que é o erro mais perigoso possível nesta tela.

    Devolve a série dia a dia e os dois marcos que a tela destaca:
      - `primeiro_dia_abaixo_da_reserva`: quando o saldo fura o fundo de
        reserva (aviso — ainda há dinheiro, mas a folga acabou);
      - `primeiro_dia_negativo`: quando falta dinheiro de fato.
    """
    fim = inicio + timedelta(days=max(dias, 0))

    por_dia: dict[date, dict] = {}
    for c in compromissos:
        data = _dia(c.get("data"))
        valor = c.get("valor") or 0.0
        if data is None or not valor:
            continue
        if data > fim:
            continue
        # Vencido antes do início da janela: puxa para o primeiro dia.
        dia = max(data, inicio)
        bucket = por_dia.setdefault(dia, {"entradas": 0.0, "saidas": 0.0, "itens": []})
        if c.get("tipo") == "receita":
            bucket["entradas"] += abs(valor)
        else:
            bucket["saidas"] += abs(valor)
        bucket["itens"].append({
            "descricao": c.get("descricao"),
            "valor": abs(valor),
            "tipo": c.get("tipo"),
            "vencido": data < inicio,
            "data_original": data.isoformat(),
        })

    serie: list[dict] = []
    saldo = round(saldo_inicial, 2)
    primeiro_negativo: str | None = None
    primeiro_abaixo_reserva: str | None = None

    dia = inicio
    while dia <= fim:
        movimento = por_dia.get(dia, {"entradas": 0.0, "saidas": 0.0, "itens": []})
        saldo = round(saldo + movimento["entradas"] - movimento["saidas"], 2)
        if primeiro_negativo is None and saldo < SALDO_CRITICO:
            primeiro_negativo = dia.isoformat()
        if primeiro_abaixo_reserva is None and fundo_reserva > 0 and saldo < fundo_reserva:
            primeiro_abaixo_reserva = dia.isoformat()
        serie.append({
            "data": dia.isoformat(),
            "entradas": round(movimento["entradas"], 2),
            "saidas": round(movimento["saidas"], 2),
            "saldo": saldo,
            "itens": movimento["itens"],
        })
        dia += timedelta(days=1)

    total_entradas = round(sum(p["entradas"] for p in serie), 2)
    total_saidas = round(sum(p["saidas"] for p in serie), 2)
    return {
        "saldo_inicial": round(saldo_inicial, 2),
        "saldo_final": saldo,
        "total_entradas": total_entradas,
        "total_saidas": total_saidas,
        "variacao": round(total_entradas - total_saidas, 2),
        "fundo_reserva": round(fundo_reserva, 2),
        "primeiro_dia_negativo": primeiro_negativo,
        "primeiro_dia_abaixo_da_reserva": primeiro_abaixo_reserva,
        # Folga = quanto o saldo mais baixo da projeção fica ACIMA da reserva.
        # Negativo significa que em algum momento a reserva é furada — é o
        # número que responde "posso comprar isso agora?" sem ler o gráfico.
        "folga_minima": round(min((p["saldo"] for p in serie), default=saldo) - fundo_reserva, 2),
        "serie": serie,
    }


def sugerir_fundo_reserva(saidas_por_mes: list[float], meses_de_folga: float = 3.0) -> float:
    """Fundo de reserva sugerido = custo mensal médio x meses de folga.

    A média usa os meses INFORMADOS (o router manda os últimos fechados);
    fazenda tem sazonalidade forte, então a média de poucos meses num pico
    de safra superestima e num vale subestima — por isso o valor é uma
    SUGESTÃO que o usuário confirma no parâmetro, nunca algo aplicado
    sozinho."""
    meses_validos = [v for v in saidas_por_mes if v and v > 0]
    if not meses_validos:
        return 0.0
    media = sum(meses_validos) / len(meses_validos)
    return round(media * meses_de_folga, 2)
