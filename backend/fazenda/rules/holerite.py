"""
Discriminação do holerite — as QUATRO colunas do recibo de papel
(Descrição · Referência · Vencimentos · Descontos) montadas a partir de um
lançamento de `FolhaPagamento` e das `ValeParcela` da competência.

POR QUE ESTE MÓDULO EXISTE. Até aqui `_detalhe_folha` devolvia
`list[{label, valor}]`: a linha do vale era montada como TEXTO
(`f"Vale (parcela {k}/{n})"`) com o `ValeFuncionario` em mãos no loop, e
`data_pagamento`, `observacao`, `numero_documento_pagamento`,
`numero_lancamento_gerado` e a nota de origem eram descartados antes de sair
do servidor. Resultado no recibo do dono: sete linhas escritas só "Vale",
indistinguíveis, somando R$ 4.880,54 sem dizer a que se referiam. O frontend
tentava recuperar a identidade perdida com um regex no rótulo em português
(`/vale/i.test(d.label)`) — que nunca teve como desempatar dois vales com
parcela de mesmo valor no mesmo mês.

A regra que este módulo impõe: **nenhum valor aparece sem uma referência que
diga de onde ele veio** — e a referência de um desconto de vale carrega o
`vale_id`, não um texto. O clique na linha leva à origem porque a linha SABE
qual é a origem.

O que NÃO é inventado aqui (limite consciente, ver dossiê):
- `Cod.` da rubrica: não existe tabela de verbas no projeto — a coluna some.
- "30 Dias" do bruto: `_proporcional_admissao` calcula e nunca grava. Só é
  escrito o fato que o cadastro sustenta (a data de admissão), no mês de
  admissão; nos demais meses a referência é "Mensal".
- Bases fiscais (Sal. Cont. INSS, Base Calc. IRRF): não são armazenadas e a
  de IRRF é inderivável (falta dependentes em `Pessoa` e tabela progressiva).
  O rodapé só mostra o que o banco sustenta — ver `bases_holerite`.

Funções puras (sem I/O): quem chama carrega os objetos e passa. Ver
`backend/tests/test_holerite_discriminado.py`.
"""
from __future__ import annotations

from datetime import date

# Ordem FIXA das linhas — requisito de documento: dois meses seguidos
# precisam ser comparáveis linha a linha.
ORDEM_TIPOS = (
    "bruto", "inss", "ir", "vale", "outros", "vencimento_extra", "desconto_extra", "liquido",
)

# Tolerância da conferência "percentual × bruto bate com o valor retido?".
# Um centavo: o valor nasce de `arredonda2(bruto × percentual/100)` no
# formulário, mas continua editável à mão depois.
TOLERANCIA_CONFERENCIA = 0.01


def _brl(valor: float) -> str:
    """R$ 1.234,50 — formatação pt-BR sem depender de locale do sistema."""
    inteiro, centavos = f"{abs(valor):.2f}".split(".")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    sinal = "-" if valor < 0 else ""
    return f"{sinal}R$ {'.'.join(grupos)},{centavos}"


def _data_br(valor: date | None) -> str:
    return valor.strftime("%d/%m/%Y") if valor else "—"


def _percentual(valor: float) -> str:
    """7,78% — sem zeros à direita inúteis (8% e não 8,00%)."""
    texto = f"{valor:g}".replace(".", ",")
    return f"{texto}%"


def linha(
    tipo: str,
    label: str,
    valor: float,
    descricao: str,
    referencia: str,
    *,
    provento: float | None = None,
    desconto: float | None = None,
    origem: dict | None = None,
) -> dict:
    """
    Uma linha do discriminado. `label`/`valor` são os campos HISTÓRICOS (texto
    de uma linha só e valor com sinal) — mantidos intactos porque o PDF antigo,
    a tela de Ações e os testes de recibo dependem deles. Os demais campos são
    o que o holerite de quatro colunas consome.
    """
    return {
        "label": label,
        "valor": valor,
        "tipo": tipo,
        "descricao": descricao,
        "referencia": referencia,
        "provento": provento,
        "desconto": desconto,
        "origem": origem,
    }


def referencia_bruto(data_admissao: date | None, competencia: str, dias_mes: int | None) -> str:
    """
    Referência da linha de salário. NUNCA escreve "30 Dias" (o divisor usado
    não está gravado em lugar nenhum); no mês de admissão escreve o fato que o
    cadastro sustenta — a data de admissão e quantos dias do mês ela deixou.
    """
    if data_admissao and data_admissao.strftime("%Y-%m") == competencia and dias_mes:
        trabalhados = dias_mes - data_admissao.day + 1
        return f"Admissão em {data_admissao.strftime('%d/%m')} · {trabalhados} de {dias_mes} dias do mês"
    return "Mensal"


def referencia_retencao(valor: float, percentual: float, valor_bruto: float) -> tuple[str, dict]:
    """
    Referência da retenção (INSS/IR) e o cartão de origem que o clique abre.

    Três casos, e a diferença entre eles é o que faz o recibo fechar:
    - percentual gravado e `percentual × bruto` bate → "7,78% sobre R$ 2.000,00";
    - percentual gravado que NÃO bate (valor editado à mão depois) → o
      percentual continua sendo dito, mas a divergência é declarada em vez de
      escondida;
    - sem percentual (o formulário permite digitar só o valor) → "valor
      informado, sem percentual". Não se deduz percentual a partir do valor:
      sem base declarada pelo usuário, qualquer percentual aqui seria inventado.
    """
    if not percentual:
        return "Valor informado, sem percentual", {
            "tipo": "retencao", "percentual": None, "base": None,
            "confere": None, "diferenca": None,
        }
    esperado = round(valor_bruto * percentual / 100, 2)
    diferenca = round(valor - esperado, 2)
    confere = abs(diferenca) <= TOLERANCIA_CONFERENCIA
    texto = f"{_percentual(percentual)} sobre {_brl(valor_bruto)}"
    if not confere:
        texto = f"{texto} · valor ajustado à mão"
    return texto, {
        "tipo": "retencao", "percentual": percentual, "base": round(valor_bruto, 2),
        "confere": confere, "diferenca": diferenca,
    }


def descricao_vale(observacao: str | None, origem_lancamento: dict | None) -> str:
    """
    O que distingue sete linhas de vale num olhar humano: a observação do vale
    ("Vale — mercado") ou, quando o vale nasceu de um item de nota fiscal, a
    nota e o produto ("Vale — nota 4471 (kit embreagem)"). Sem nenhum dos dois,
    fica "Vale" — e aí a Referência sozinha (parcela + data) já desempata.
    """
    if origem_lancamento:
        nota = origem_lancamento.get("numero_documento")
        produto = origem_lancamento.get("produto")
        if nota and produto:
            return f"Vale — nota {nota} ({produto})"
        if nota:
            return f"Vale — nota {nota}"
        if produto:
            return f"Vale — {produto}"
    texto = (observacao or "").strip()
    return f"Vale — {texto}" if texto else "Vale"


def referencia_vale(parcela: int, total: int, data_pagamento: date | None) -> str:
    """
    "Parcela 3 de 13 · vale de 12/03/2026". O ordinal vem da POSIÇÃO da parcela
    na sequência ordenada do próprio vale, nunca de `ValeFuncionario.parcelas`
    (que `excluir_parcela_vale` não atualiza — "3/13" viraria "3/12" sozinho).
    """
    ordinal = f"Parcela {parcela} de {total}" if total > 1 else "Parcela única"
    if data_pagamento:
        return f"{ordinal} · vale de {_data_br(data_pagamento)}"
    return ordinal


def origem_vale(vale, parcela, k: int, n: int, origem_lancamento: dict | None) -> dict:
    """
    O cartão que o clique na linha abre: tudo o que o servidor tinha em mãos e
    descartava. `numero_lancamento_gerado` é NULL POR DESENHO quando a forma de
    pagamento é `desconto_integral_folha` (não houve saída de caixa) — por isso
    vai junto o motivo, para a tela poder explicar a ausência do link do
    extrato em vez de mostrar um link quebrado.
    """
    sem_caixa = vale.forma_pagamento == "desconto_integral_folha"
    return {
        "tipo": "vale",
        "vale_id": vale.id,
        "parcela_id": parcela.id,
        "parcela": k,
        "parcelas_total": n,
        "valor_total": round(vale.valor_total, 2),
        "data_pagamento": vale.data_pagamento.isoformat() if vale.data_pagamento else None,
        "forma_pagamento": vale.forma_pagamento,
        "observacao": vale.observacao,
        "numero_documento_pagamento": vale.numero_documento_pagamento,
        "numero_lancamento_gerado": vale.numero_lancamento_gerado,
        "sem_saida_de_caixa": sem_caixa,
        "origem_lancamento": origem_lancamento,
        "aplicada": bool(parcela.aplicada),
    }


def bases_holerite(registro) -> dict:
    """
    O rodapé HONESTO do holerite: só o que o banco sustenta.

    - `salario_base` vem de `FolhaPagamento.valor_bruto`, NUNCA de
      `Pessoa.salario_base` — este último é valor VIVO e reimprimir um holerite
      de 2024 mostraria o salário de hoje com cara de documento de época.
    - `base_inss`/`base_ir` só existem quando há percentual gravado: aí a base
      é o próprio bruto sobre o qual o percentual foi aplicado. Sem percentual,
      `None` — a tela omite o campo em vez de mostrar traço (num documento de
      aparência oficial, campo vazio lê como zero).
    - Base de cálculo do IRRF (a do holerite de papel) NÃO entra: é
      inderivável aqui — falta dependentes em `Pessoa` e a tabela progressiva.
    - FGTS é do EMPREGADOR (não é desconto do empregado), então fica fora das
      duas colunas e só aparece quando preenchido, rotulado como projeção.
    """
    tem_inss = bool(registro.percentual_inss and registro.valor_inss)
    tem_ir = bool(registro.percentual_ir and registro.valor_ir)
    # A base NÃO é o salário quando há rubrica salarial lançada: bonificação,
    # guelta e aumento entram nela; reembolso e indenização não (ver
    # rules/rubrica_folha.py). Mostrar o salário puro aqui faria o dono
    # conferir "9% sobre R$ 3.200,00" contra um valor retido que foi calculado
    # sobre R$ 3.700,00 e concluir que o sistema errou.
    acrescimo = round(registro.valor_rubricas_tributaveis or 0.0, 2)
    base = round(registro.valor_bruto + acrescimo, 2)
    return {
        "salario_base": round(registro.valor_bruto, 2),
        "base_inss": base if tem_inss else None,
        "base_ir": base if tem_ir else None,
        # Quanto das bases veio de rubrica salarial — 0.0 na folha comum, e é
        # o que a tela usa para explicar a diferença entre salário e base.
        "rubricas_tributaveis": acrescimo,
        "fgts_projetado": round(registro.valor_fgts, 2) if registro.valor_fgts else None,
        "percentual_fgts": registro.percentual_fgts or None,
        "dctf_projetado": round(registro.valor_dctf, 2) if registro.valor_dctf else None,
    }


def totais_holerite(linhas: list[dict]) -> dict:
    """
    Totais das duas colunas + líquido. `liquido_negativo` existe porque um
    recibo em que os descontos passam os vencimentos NÃO é um recibo: a tela
    troca "Líquido: −1.680,54" (que tem aparência de resultado válido) por
    "os descontos excedem os vencimentos em R$ 1.680,54", e a impressão fica
    bloqueada. Sem esta flag no payload, cada tela recalcularia por conta.
    """
    proventos = round(sum(l["provento"] or 0 for l in linhas if l["tipo"] != "liquido"), 2)
    descontos = round(sum(l["desconto"] or 0 for l in linhas if l["tipo"] != "liquido"), 2)
    liquido = round(proventos - descontos, 2)
    return {
        "total_proventos": proventos,
        "total_descontos": descontos,
        "liquido": liquido,
        "liquido_negativo": liquido < 0,
        "excedente": round(-liquido, 2) if liquido < 0 else 0.0,
    }
