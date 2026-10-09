"""
DRE Gerencial em cascata — motor puro (sem Session), no mesmo espírito de
fazenda/rules/rmca.py e fazenda/rules/custo_safra.py: recebe listas já
achatadas + um mapa conta→linha e devolve a cascata pronta. Quem busca no
banco, aplica o ajuste de vale (rules/vale_item.py) e o rateio por centro de
custo (rules/centro_custo.py) é o router (fazenda/api/routers/financeiro.py)
— este módulo não sabe nada disso, só soma e monta a cascata.

===========================================================================
ATENÇÃO — dois conceitos parecidos no nome e OPOSTOS na natureza (pedido
explícito do dono do produto: nunca confundir os dois).

  • Depreciação / Amortização / Exaustão (CONTÁBIL) — desgaste de um bem:
    Depreciação = bem tangível; Amortização = intangível; Exaustão =
    recurso natural/cultura permanente. É DESPESA que NÃO é saída de caixa
    — por isso tem linha própria aqui (DEPRECIACAO_AMORT_EXAUSTAO, ver
    fazenda/rules/depreciacao_periodo.py para o cálculo do período).

  • Principal de financiamento — saída de caixa que NÃO É despesa (é
    redução de um passivo: o capital já entrou como receita/empréstimo
    antes; devolvê-lo não é gasto novo). NÃO ENTRA NA DRE em linha
    nenhuma. Só o JUROS do financiamento é despesa de verdade, e vai em
    OUTRAS_REC_DESP — nunca junto do principal.

  Qualquer conta gerencial que represente pagamento de PRINCIPAL de
  financiamento deve ser classificada como NAO_ENTRA_NA_DRE (ver abaixo) —
  jamais como DEPRECIACAO_AMORT_EXAUSTAO nem em nenhuma outra linha de
  despesa. O nome parecido ("amortização" de bem vs. "amortização" de
  dívida) é coincidência de vocabulário contábil, não parentesco de
  conceito — são operações contrárias (uma é despesa sem caixa, a outra é
  caixa sem despesa).
===========================================================================
"""
from __future__ import annotations

from fazenda.rules.natureza import NAO_INFORMADA, OPERACIONAL
from fazenda.rules.natureza import ORDEM_EXIBICAO as ORDEM_NATUREZAS
from fazenda.rules.natureza import ROTULOS as ROTULOS_NATUREZA

# ---------------------------------------------------------------------------
# As 15 linhas da DRE Gerencial em cascata (estrutura definida pelo dono do
# produto) — 9 ATRIBUÍVEIS (uma conta gerencial pode apontar pra elas, ver
# PlanoContaGerencial.linha_dre) + 6 SUBTOTAIS (sempre calculados a partir
# das atribuíveis, nunca atribuídos a conta nenhuma).
# ---------------------------------------------------------------------------
RECEITA_VENDAS = "RECEITA_VENDAS"
DEDUCAO_IMPOSTOS = "DEDUCAO_IMPOSTOS"
RECEITA_LIQUIDA = "RECEITA_LIQUIDA"                    # subtotal
CUSTO_VARIAVEL = "CUSTO_VARIAVEL"
MARGEM_BRUTA = "MARGEM_BRUTA"                          # subtotal
DESPESA_VARIAVEL = "DESPESA_VARIAVEL"
MARGEM_CONTRIBUICAO = "MARGEM_CONTRIBUICAO"            # subtotal
GASTOS_PESSOAL = "GASTOS_PESSOAL"
DESPESAS_OPERACIONAIS = "DESPESAS_OPERACIONAIS"
EBITDA = "EBITDA"                                      # subtotal
DEPRECIACAO_AMORT_EXAUSTAO = "DEPRECIACAO_AMORT_EXAUSTAO"
OUTRAS_REC_DESP = "OUTRAS_REC_DESP"
RESULTADO_OPERACIONAL = "RESULTADO_OPERACIONAL"        # subtotal (EBIT)
TRIBUTOS_IR_CSLL = "TRIBUTOS_IR_CSLL"
RESULTADO_LIQUIDO = "RESULTADO_LIQUIDO"                # subtotal

# Valor especial de PlanoContaGerencial.linha_dre para conta que
# LEGITIMAMENTE fica fora do resultado — não é "falta classificar" (isso é o
# balde `nao_classificado`, ver `montar_cascata_dre`), é uma decisão
# consciente do usuário. Ex.: principal de financiamento (ver ADR no topo
# deste módulo), transferência entre contas próprias, aporte de sócio.
NAO_ENTRA_NA_DRE = "NAO_ENTRA_NA_DRE"

# (chave, rótulo, operador, é_subtotal) — a ORDEM da tupla é a ordem de
# exibição da cascata inteira, subtotal incluso.
#
# Operador:
#   "+"  a linha soma no acumulado (ex.: receita de vendas).
#   "-"  a linha subtrai (ex.: custo, despesa) — o VALOR guardado/exibido da
#        linha é sempre a magnitude positiva ("despesa entra positiva na sua
#        linha"), quem decide que ela subtrai é o operador, nunca um sinal
#        negativo escondido no valor.
#   "±"  só OUTRAS_REC_DESP: mistura receita e despesa de propósito (ex.:
#        juros pago x desconto recebido); o valor exibido é o LÍQUIDO
#        (pode ser negativo) e entra somado — o próprio sinal já resolve.
#   "="  subtotal: valor = acumulado até aqui, nunca tem conta associada.
ESPECIFICACAO_LINHAS: tuple[tuple[str, str, str, bool], ...] = (
    (RECEITA_VENDAS, "Receita de vendas", "+", False),
    (DEDUCAO_IMPOSTOS, "Deduções de impostos", "-", False),
    (RECEITA_LIQUIDA, "Receita líquida", "=", True),
    (CUSTO_VARIAVEL, "Custo variável (CPV/CMV)", "-", False),
    (MARGEM_BRUTA, "Margem bruta", "=", True),
    (DESPESA_VARIAVEL, "Despesas variáveis", "-", False),
    (MARGEM_CONTRIBUICAO, "Margem de contribuição", "=", True),
    (GASTOS_PESSOAL, "Gastos com pessoal", "-", False),
    (DESPESAS_OPERACIONAIS, "Despesas operacionais", "-", False),
    (EBITDA, "EBITDA", "=", True),
    (DEPRECIACAO_AMORT_EXAUSTAO, "Depreciação, amortização e exaustão", "-", False),
    (OUTRAS_REC_DESP, "Outras receitas e despesas", "±", False),
    (RESULTADO_OPERACIONAL, "Resultado operacional (EBIT)", "=", True),
    (TRIBUTOS_IR_CSLL, "Tributos (IRPJ e CSLL)", "-", False),
    (RESULTADO_LIQUIDO, "Resultado líquido", "=", True),
)

# Só as 9 linhas não-subtotal são atribuíveis a uma conta gerencial.
CODIGOS_ATRIBUIVEIS: tuple[str, ...] = tuple(
    chave for chave, _rotulo, _operador, eh_subtotal in ESPECIFICACAO_LINHAS if not eh_subtotal
)

# Todo valor aceito em PlanoContaGerencial.linha_dre — as 9 linhas +
# o "escape hatch" consciente NAO_ENTRA_NA_DRE (ver acima).
LINHAS_DRE_VALIDAS: tuple[str, ...] = CODIGOS_ATRIBUIVEIS + (NAO_ENTRA_NA_DRE,)


def resolver_linha_dre(codigo: str | None, mapa_linha_por_codigo: dict[str, str]) -> str | None:
    """Herança por prefixo de código (mesma convenção hierárquica de
    `_eh_folha` em fazenda/api/routers/financeiro.py e `ehFolha` em
    frontend/lib/contaGerencial.ts: "3.01.01" é filho de "3.01", que é filho
    de "3"): uma conta filha sem `linha_dre` própria herda a do ancestral
    mais próximo que tiver uma. Ex.: mapa = {"3.04": DESPESAS_OPERACIONAIS} e
    codigo = "3.04.04.02" (sem entrada própria) -> resolve para
    DESPESAS_OPERACIONAIS, olhando "3.04.04.02", depois "3.04.04", depois
    "3.04" (achou).

    `mapa_linha_por_codigo` só precisa ter as atribuições EXPLÍCITAS (uma por
    código que o usuário de fato classificou, ver PUT
    /financeiro/plano-contas/{codigo}/linha-dre) — a herança é resolvida
    aqui, nunca precisa ser "achatada" no banco.

    None quando nem o código nem nenhum ancestral tem linha_dre — a conta
    está NÃO CLASSIFICADA (ver balde `nao_classificado` em
    `montar_cascata_dre` e GET /financeiro/dre/conferencia)."""
    if not codigo:
        return None
    partes = codigo.split(".")
    for fim in range(len(partes), 0, -1):
        prefixo = ".".join(partes[:fim])
        linha = mapa_linha_por_codigo.get(prefixo)
        if linha:
            return linha
    return None


def _valor_exibido(receita: float, despesa: float, operador: str) -> float:
    """Sinal ÚNICO do módulo (ver comentário de ESPECIFICACAO_LINHAS):
    receita entra positiva, despesa entra positiva NA SUA LINHA — o operador
    é quem decide se ela soma ou subtrai na cascata, nunca um sinal
    negativo escondido no valor guardado.

    Linha "-" bem classificada (só despesa dentro dela): despesa - receita
    (normalmente = despesa, positivo). Linha "+" (só receita): receita -
    despesa (normalmente = receita, positivo). Linha "±" (só
    OUTRAS_REC_DESP): devolve o líquido tal qual — pode ser negativo, e é
    exatamente esse líquido (com sinal) que soma na cascata."""
    liquido = round(receita - despesa, 2)
    valor = round(-liquido, 2) if operador == "-" else liquido
    # `+ 0.0` normaliza o zero negativo: em IEEE 754, negar 0.0 dá -0.0, e a
    # linha vazia (ex.: "Tributos" numa fazenda que não apura IRPJ) chegava
    # na tela como "-0,00" — que o usuário lê como defeito, não como zero.
    return valor + 0.0


def montar_cascata_dre(
    registros: list[dict],
    mapa_linha_por_codigo: dict[str, str],
    depreciacao_periodo: float = 0.0,
    *,
    regras_v2: bool = False,
    resultado_baixas: float = 0.0,
) -> dict:
    """
    Motor puro da DRE Gerencial em cascata.

    `registros`: uma entrada por item/conta já achatado, com o AJUSTE
    GERENCIAL JÁ APLICADO por quem chama (vale descontado, rateio de centro
    de custo já feito, item de vale já excluído — ver rules/vale_item.py e
    rules/centro_custo.py; este módulo não sabe nada disso, só soma). Cada
    dict:
        {"codigo_conta": str | None, "tipo": "receita" | "despesa",
         "valor": float, "descricao": str | None,
         "origem": "item" | "fallback_conta"}
    `valor` é sempre a MAGNITUDE (>= 0) — o sinal final é resolvido pelo par
    (`tipo`, linha) em `_valor_exibido`. `origem` é só informativo para quem
    monta `registros` (nota antiga sem LancamentoItem, ver docstring do
    router) — este motor não distingue por ela.

    `mapa_linha_por_codigo`: {codigo_exato: linha_dre}, só com as
    atribuições EXPLÍCITAS (sem herança resolvida — resolvida aqui dentro,
    por registro, via `resolver_linha_dre`).

    `depreciacao_periodo`: magnitude (despesa) já calculada por
    fazenda.rules.depreciacao_periodo.calcular_depreciacao_periodo — somada
    à linha DEPRECIACAO_AMORT_EXAUSTAO como mais uma "pseudoconta"
    ("(depreciação do patrimônio)"), além de qualquer lançamento manual que
    porventura já esteja classificado nessa linha via `registros`. ATENÇÃO:
    isto é depreciação contábil, NUNCA principal de financiamento — ver o
    ADR no topo do módulo.

    Devolve:
        {
          "linhas": [
              {"chave", "rotulo", "operador", "eh_subtotal", "valor",
               "contas": [{"codigo", "nome", "valor"}, ...]},
              ...  # 15 entradas, na ordem de ESPECIFICACAO_LINHAS
          ],
          "nao_classificado": {"total": float, "contas": [...]},
          "fora_da_dre": {"total": float, "contas": [...]},
        }
    A DRE NUNCA finge que fecha: `nao_classificado` (falta classificar) e
    `fora_da_dre` (classificada como NAO_ENTRA_NA_DRE de propósito) NUNCA
    entram em nenhum subtotal — são devolvidos à parte, cada um com seu
    total e a lista de contas, para o usuário decidir o que fazer.

    REGRAS V2 (Fase A, flag `financeiro_regras_v2` da fazenda — ver
    rules/natureza.py). Com `regras_v2=False` (padrão) TUDO acima vale tal
    qual e as chaves novas abaixo não aparecem — os números são idênticos aos
    de antes (teste de regressão em tests/test_relatorios_cenario_auditoria.py).
    Com `regras_v2=True`:
      • registro com `natureza` ≠ OPERACIONAL vai para `fora_da_dre`, agrupado
        por natureza (`fora_da_dre["por_natureza"]` = {natureza: total} e
        `fora_da_dre["grupos"]` = lista para a tela), qualquer que seja a
        linha da conta. NAO_ENTRA_NA_DRE sem natureza vira o grupo
        NAO_INFORMADA. A depreciação continua entrando;
      • `resultado_baixas` (ganho > 0 / perda < 0 de capital na baixa de bem,
        ver rules/patrimonio.py::resultado_baixa) entra em OUTRAS_REC_DESP
        como a pseudoconta "(resultado de baixa de patrimônio)";
      • registro com `linha_forcada` (uma das 9 linhas atribuíveis) entra
        nessa linha, sem passar pelo plano de contas: são as pseudocontas de
        rules/juros_descontos.py — juros/desconto da baixa em OUTRAS_REC_DESP
        (PR 7) e desconto da nota de receita em DEDUCAO_IMPOSTOS (PR 4) — e a
        multa/juros da guia de FGTS/DCTF (PR 3);
      • `nao_classificado` e `fora_da_dre` (e cada grupo) trazem também
        `total_receita`, `total_despesa`, `liquido` e, por conta, `receita`,
        `despesa` e `liquido` (PR 2);
      • `por_conta` (PR 8): o campo legado da DRE derivado só do que entrou
        nas linhas (depreciação e baixa como pseudocontas) — Σ receitas −
        Σ despesas = resultado líquido. Ver `resumo_da_cascata`.
    O `valor` continua sendo MAGNITUDE (>= 0) também com as regras v2: o
    item redutor de uma nota (ex.: "(−) INSS retido" da folha pelo bruto,
    PR 3) chega aqui com o `tipo` INVERTIDO (despesa → receita), nunca com
    valor negativo — é o par (tipo, linha) que dá o sinal. Na linha de
    pessoal, o "(−) Outros descontos" da folha abate o bruto; fora da DRE, o
    retido entra no lado receita da obrigação e a guia que o quita no lado
    despesa (o `liquido` da obrigação mostra o que ainda falta recolher).
    """
    por_linha: dict[str, dict] = {
        chave: {"receita": 0.0, "despesa": 0.0, "contas": {}} for chave in CODIGOS_ATRIBUIVEIS
    }
    nao_classificado_contas: dict[str, dict] = {}
    fora_da_dre_contas: dict[str, dict] = {}
    # Só com regras_v2: {natureza: {codigo: {...}}} para o agrupamento.
    fora_por_natureza: dict[str, dict[str, dict]] = {}
    # Só com regras_v2 (PR 8): o legado `por_conta` derivado do que ENTROU na
    # cascata — {nível 1 do código: {descricao, receitas, despesas}}.
    por_conta: dict[str, dict] = {}

    def _acumular(bucket_contas: dict, codigo: str | None, nome: str | None, tipo: str, valor: float) -> None:
        chave_conta = codigo or "(sem código)"
        entrada = bucket_contas.setdefault(chave_conta, {"nome": nome or chave_conta, "receita": 0.0, "despesa": 0.0})
        campo = "receita" if tipo == "receita" else "despesa"
        entrada[campo] = round(entrada[campo] + valor, 2)

    def _acumular_por_conta(codigo: str | None, nome: str | None, tipo: str, valor: float) -> None:
        if not regras_v2:
            return
        chave_conta = codigo or "Sem classificação"
        nivel1 = chave_conta.split(".")[0] if "." in chave_conta and not chave_conta.startswith("(") else chave_conta
        entrada = por_conta.setdefault(nivel1, {"descricao": nome or "", "receitas": 0.0, "despesas": 0.0})
        campo = "receitas" if tipo == "receita" else "despesas"
        entrada[campo] = round(entrada[campo] + valor, 2)

    for registro in registros:
        valor = registro.get("valor") or 0.0
        if valor == 0:
            continue
        tipo = registro.get("tipo") or "despesa"
        codigo = registro.get("codigo_conta")
        nome = registro.get("descricao")
        linha = resolver_linha_dre(codigo, mapa_linha_por_codigo)
        if regras_v2 and registro.get("linha_forcada") in por_linha:
            # Pseudoconta das regras v2 (juros/desconto da baixa → Outras;
            # desconto da nota de receita → Deduções): não existe no plano,
            # a linha vem pronta de quem montou o registro.
            linha = registro["linha_forcada"]

        if regras_v2:
            natureza = registro.get("natureza") or OPERACIONAL
            if natureza == OPERACIONAL and linha == NAO_ENTRA_NA_DRE:
                natureza = NAO_INFORMADA
            if natureza != OPERACIONAL:
                _acumular(fora_da_dre_contas, codigo, nome, tipo, valor)
                _acumular(fora_por_natureza.setdefault(natureza, {}), codigo, nome, tipo, valor)
                continue

        if linha == NAO_ENTRA_NA_DRE:
            _acumular(fora_da_dre_contas, codigo, nome, tipo, valor)
            continue
        if linha is None or linha not in por_linha:
            # None = não classificada; fora do enum (dado inconsistente) cai
            # no mesmo balde — nunca quebra a resposta por causa de um valor
            # esquisito salvo por engano.
            _acumular(nao_classificado_contas, codigo, nome, tipo, valor)
            continue

        bucket = por_linha[linha]
        campo = "receita" if tipo == "receita" else "despesa"
        bucket[campo] = round(bucket[campo] + valor, 2)
        _acumular(bucket["contas"], codigo, nome, tipo, valor)
        _acumular_por_conta(codigo, nome, tipo, valor)

    # Depreciação do período entra como despesa "extra" da sua linha, com
    # pseudoconta própria de detalhamento — ver ADR no topo do módulo sobre
    # por que ISTO (depreciação contábil) é o oposto de principal de
    # financiamento (que nunca entra em linha nenhuma).
    if depreciacao_periodo:
        bucket = por_linha[DEPRECIACAO_AMORT_EXAUSTAO]
        bucket["despesa"] = round(bucket["despesa"] + depreciacao_periodo, 2)
        _acumular(
            bucket["contas"], "(depreciação do patrimônio)",
            "Depreciação do período (patrimônio)", "despesa", depreciacao_periodo,
        )
        _acumular_por_conta("(depreciação do patrimônio)", "Depreciação do período (patrimônio)",
                            "despesa", depreciacao_periodo)

    # Ganho/perda de capital na baixa de bem (só regras v2): resultado do
    # exercício, linha OUTRAS_REC_DESP — nunca receita de vendas.
    if regras_v2 and resultado_baixas:
        bucket = por_linha[OUTRAS_REC_DESP]
        tipo_baixa = "receita" if resultado_baixas > 0 else "despesa"
        magnitude = round(abs(resultado_baixas), 2)
        bucket[tipo_baixa] = round(bucket[tipo_baixa] + magnitude, 2)
        _acumular(
            bucket["contas"], "(resultado de baixa de patrimônio)",
            "Ganho ou perda na baixa de patrimônio", tipo_baixa, magnitude,
        )
        _acumular_por_conta("(resultado de baixa de patrimônio)", "Ganho ou perda na baixa de patrimônio",
                            tipo_baixa, magnitude)

    linhas_resultado: list[dict] = []
    saldo = 0.0
    for chave, rotulo, operador, eh_subtotal in ESPECIFICACAO_LINHAS:
        if eh_subtotal:
            linhas_resultado.append({
                "chave": chave, "rotulo": rotulo, "operador": operador,
                "eh_subtotal": True, "valor": round(saldo, 2), "contas": [],
            })
            continue

        bucket = por_linha[chave]
        valor_linha = _valor_exibido(bucket["receita"], bucket["despesa"], operador)
        saldo = round(saldo - valor_linha, 2) if operador == "-" else round(saldo + valor_linha, 2)

        contas = sorted(
            (
                {"codigo": codigo, "nome": info["nome"], "valor": _valor_exibido(info["receita"], info["despesa"], operador)}
                for codigo, info in bucket["contas"].items()
            ),
            key=lambda c: -abs(c["valor"]),
        )
        linhas_resultado.append({
            "chave": chave, "rotulo": rotulo, "operador": operador,
            "eh_subtotal": False, "valor": valor_linha, "contas": contas,
        })

    def _bucket_a_parte(bucket_contas: dict) -> dict:
        """`nao_classificado`/`fora_da_dre` não têm operador de linha (não
        somam nem subtraem em nada) — o valor mostrado é a MAGNITUDE do
        movimento parado naquela conta (receita + despesa; uma conta
        gerencial é, por convenção, exclusivamente receita OU despesa —
        prefixoDoTipo em frontend/lib/contaGerencial.ts —, então na prática
        só um dos dois lados é não-zero). Sempre positivo: é "quanto está
        parado ali", não um saldo com sinal de cascata."""
        contas = sorted(
            (
                {"codigo": codigo, "nome": info["nome"], "valor": round(info["receita"] + info["despesa"], 2),
                 **({"receita": info["receita"], "despesa": info["despesa"],
                     "liquido": round(info["receita"] - info["despesa"], 2)} if regras_v2 else {})}
                for codigo, info in bucket_contas.items()
            ),
            key=lambda c: -abs(c["valor"]),
        )
        resultado = {"total": round(sum(c["valor"] for c in contas), 2), "contas": contas}
        if regras_v2:
            # Regras v2 (PR 2, P1 "não classificado soma receita e despesa"):
            # os dois lados separados — o total continua a magnitude parada
            # (compatível), mas a tela mostra "R$ X de receita e R$ Y de
            # despesa sem classificação" e o líquido de cada conta.
            resultado["total_receita"] = round(sum(c["receita"] for c in contas), 2)
            resultado["total_despesa"] = round(sum(c["despesa"] for c in contas), 2)
            resultado["liquido"] = round(resultado["total_receita"] - resultado["total_despesa"], 2)
        return resultado

    fora_da_dre = _bucket_a_parte(fora_da_dre_contas)
    if regras_v2:
        grupos = []
        for natureza in ORDEM_NATUREZAS:
            if natureza not in fora_por_natureza:
                continue
            bucket_nat = _bucket_a_parte(fora_por_natureza[natureza])
            grupos.append({"natureza": natureza, "rotulo": ROTULOS_NATUREZA[natureza], **bucket_nat})
        fora_da_dre["por_natureza"] = {g["natureza"]: g["total"] for g in grupos}
        fora_da_dre["grupos"] = grupos

    resultado_final = {
        "linhas": linhas_resultado,
        "nao_classificado": _bucket_a_parte(nao_classificado_contas),
        "fora_da_dre": fora_da_dre,
    }
    if regras_v2:
        resultado_final["por_conta"] = {
            k: {"descricao": v["descricao"], "receitas": round(v["receitas"], 2), "despesas": round(v["despesas"], 2)}
            for k, v in por_conta.items()
        }
    return resultado_final


def resumo_da_cascata(cascata: dict) -> dict:
    """Regras v2, PR 8 (DRE única — R4): o resumo que TODA tela mostra
    (KPIs da aba DRE, gráfico, card da Capa, CSV/e-mail do Portal), tirado da
    cascata e de mais nada. `cascata` é o retorno de `montar_cascata_dre`.

    - `receita_liquida`, `ebitda`, `resultado_operacional` e
      `resultado_liquido` são as linhas-subtotal da cascata;
    - `despesas` = receita líquida − resultado líquido (tudo o que a cascata
      subtraiu depois das deduções, depreciação e Outras inclusas): é o par
      que os KPIs "Receita × Despesa × Resultado" mostram, e fecha por
      construção (receita − despesa = resultado);
    - `margem_liquida_pct` só com receita líquida positiva;
    - `fora_da_dre_total` e `nao_classificado` NUNCA entram no resultado —
      vêm à parte, para a tela avisar."""
    linhas = {linha["chave"]: linha["valor"] for linha in cascata["linhas"]}
    receita_liquida = round(linhas.get(RECEITA_LIQUIDA, 0.0), 2)
    resultado_liquido = round(linhas.get(RESULTADO_LIQUIDO, 0.0), 2)
    nao = cascata["nao_classificado"]
    return {
        "receita_bruta": round(linhas.get(RECEITA_VENDAS, 0.0), 2),
        "receita_liquida": receita_liquida,
        "despesas": round(receita_liquida - resultado_liquido, 2) + 0.0,
        "ebitda": round(linhas.get(EBITDA, 0.0), 2),
        "resultado_operacional": round(linhas.get(RESULTADO_OPERACIONAL, 0.0), 2),
        "resultado_liquido": resultado_liquido,
        "margem_liquida_pct": round(100 * resultado_liquido / receita_liquida, 1) if receita_liquida > 0 else None,
        "fora_da_dre_total": cascata["fora_da_dre"]["total"],
        "nao_classificado": nao["total"],
        "nao_classificado_receita": nao.get("total_receita", 0.0),
        "nao_classificado_despesa": nao.get("total_despesa", 0.0),
    }
