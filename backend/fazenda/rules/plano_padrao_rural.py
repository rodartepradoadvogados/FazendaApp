"""
Plano de contas gerencial PADRÃO rural-leiteiro — o que uma fazenda nova
(ex.: plano "Financeiro", sem Ideagri) recebe para conseguir classificar o
primeiro lançamento. Plano Financeiro §1.8 / decisão P6(b).

############################################################################
# RASCUNHO — validar com o contador.                                       #
# Lista genérica escrita pela CowData a partir da estrutura do DRE         #
# (rules/dre.py) e da atividade rural leiteira. NÃO foi copiada do plano   #
# real de nenhuma fazenda (AGENTS.md: dados reais não vão para o código)   #
# e ainda NÃO passou pela revisão do contador externo. Códigos, nomes e    #
# a linha do DRE de cada grupo podem mudar depois dessa revisão.           #
############################################################################

POR QUE EXISTE. O plano de contas de uma fazenda hoje nasce do CSV do Ideagri
(rules/plano_padrao.py, upload.py). Um cliente que nunca usou o Ideagri
começava sem nenhuma conta e não conseguia classificar a primeira despesa.

COMO FOI DESENHADO.
  - Mesma convenção de códigos hierárquicos do resto do sistema (herança por
    prefixo em `rules.dre.resolver_linha_dre` e `rules.natureza`): a
    `linha_dre`/`natureza_fin` ficam nos GRUPOS e as folhas herdam; só vai
    valor próprio na folha quando ela difere do grupo.
  - Convenção de grupos (a mesma que o sistema já assume): 2.* receitas,
    3.* despesas; 3.01.01 = alimentação do rebanho (RMCA, custo de
    alimentação) e 3.03.01 = pessoal — é onde `plano_padrao.
    garantir_contas_do_sistema` penduram 3.03.01.16 (Retenções) e 3.03.01.17
    (Vales e adiantamentos), por isso o grupo existe aqui.
  - A conta de receita do leite (2.01.01.01) nasce marcada com
    `rmca_receita_leite=True`: sem isso "Resultado por litro" e o RMCA não
    acham a receita do leite numa fazenda sem estoque/Ideagri.
  - O que NÃO é resultado fica fora da DRE com a natureza certa: principal
    de financiamento (FINANCIAMENTO), compra de bem do imobilizado
    (INVESTIMENTO), retirada/aporte de sócio (CAPITAL). Só o JUROS é despesa
    (OUTRAS_REC_DESP). Ver o ADR no topo de rules/dre.py.
  - NÃO há conta de depreciação: a DRE soma a depreciação do patrimônio como
    pseudoconta própria (rules/depreciacao_periodo.py); uma conta manual na
    mesma linha duplicaria o valor.

O QUE ELA NÃO FAZ. Não sobrescreve plano existente (só carrega quando a
fazenda tem ZERO contas), não faz commit (quem chama decide a transação) e
não liga flag nenhuma (isso é de financeiro_preparar.py).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

# Valores de linha_dre (espelhos de rules.dre) e de natureza_fin (rules.natureza)
# — literais de propósito, no mesmo estilo de rules/plano_padrao.py; o teste
# tests/test_plano_financeiro_preparar.py confere que são todos válidos.
_RECEITA_VENDAS = "RECEITA_VENDAS"
_DEDUCAO_IMPOSTOS = "DEDUCAO_IMPOSTOS"
_CUSTO_VARIAVEL = "CUSTO_VARIAVEL"
_DESPESA_VARIAVEL = "DESPESA_VARIAVEL"
_GASTOS_PESSOAL = "GASTOS_PESSOAL"
_DESPESAS_OPERACIONAIS = "DESPESAS_OPERACIONAIS"
_OUTRAS_REC_DESP = "OUTRAS_REC_DESP"
_TRIBUTOS_IR_CSLL = "TRIBUTOS_IR_CSLL"
_NAO_ENTRA_NA_DRE = "NAO_ENTRA_NA_DRE"

_INVESTIMENTO = "INVESTIMENTO"
_FINANCIAMENTO = "FINANCIAMENTO"
_CAPITAL = "CAPITAL"


@dataclass(frozen=True)
class ContaPadrao:
    codigo: str
    nome: str
    linha_dre: str | None = None
    natureza_fin: str | None = None
    rmca_receita_leite: bool = False
    rmca_custo_alimentacao: bool = False
    pede_vinculo_sanitario_reprodutivo: bool = False


def _c(codigo: str, nome: str, linha: str | None = None, nat: str | None = None, **kw) -> ContaPadrao:
    return ContaPadrao(codigo, nome, linha, nat, **kw)


# RASCUNHO — validar com o contador (ver o topo do módulo).
PLANO_PADRAO_RURAL: tuple[ContaPadrao, ...] = (
    # ---- 2. RECEITAS ---------------------------------------------------------------
    _c("2", "Receitas"),
    _c("2.01", "Receitas da atividade leiteira", _RECEITA_VENDAS),
    _c("2.01.01", "Venda de leite"),
    _c("2.01.01.01", "Leite (laticínio / cooperativa)", rmca_receita_leite=True),
    _c("2.01.02", "Venda de animais"),
    _c("2.01.02.01", "Venda de bezerros e machos"),
    _c("2.01.02.02", "Venda de vacas e novilhas"),
    _c("2.01.02.03", "Venda de animais de descarte"),
    _c("2.01.03", "Outras vendas da atividade"),
    _c("2.01.03.01", "Venda de esterco e subprodutos"),
    _c("2.01.03.02", "Serviços prestados a terceiros"),
    _c("2.02", "Receitas não operacionais", _OUTRAS_REC_DESP),
    _c("2.02.01", "Receitas financeiras (rendimentos)"),
    _c("2.02.02", "Arrendamento e aluguéis recebidos"),
    _c("2.02.03", "Outras receitas"),
    _c("2.03", "Entradas que não são receita", _NAO_ENTRA_NA_DRE),
    _c("2.03.01", "Empréstimos e financiamentos recebidos", _NAO_ENTRA_NA_DRE, _FINANCIAMENTO),
    _c("2.03.02", "Aporte do produtor / sócio", _NAO_ENTRA_NA_DRE, _CAPITAL),
    # ---- 3. DESPESAS ---------------------------------------------------------------
    _c("3", "Despesas e custos"),
    # 3.01 Custo da produção de leite
    _c("3.01", "Custo da produção de leite", _CUSTO_VARIAVEL),
    _c("3.01.01", "Alimentação do rebanho", rmca_custo_alimentacao=True),
    _c("3.01.01.01", "Ração e concentrados", rmca_custo_alimentacao=True),
    _c("3.01.01.02", "Silagem e volumosos", rmca_custo_alimentacao=True),
    _c("3.01.01.03", "Sal mineral e suplementos", rmca_custo_alimentacao=True),
    _c("3.01.01.04", "Pastagem, adubação e sementes", rmca_custo_alimentacao=True),
    _c("3.01.02", "Sanidade do rebanho"),
    _c("3.01.02.01", "Medicamentos e vacinas"),
    _c("3.01.02.02", "Honorários veterinários", pede_vinculo_sanitario_reprodutivo=True),
    _c("3.01.02.03", "Exames e análises"),
    _c("3.01.03", "Reprodução e genética"),
    _c("3.01.03.01", "Sêmen e material genético"),
    _c("3.01.03.02", "Inseminação e protocolos hormonais"),
    _c("3.01.04", "Ordenha e qualidade do leite"),
    _c("3.01.04.01", "Produtos de limpeza e higiene da ordenha"),
    _c("3.01.04.02", "Reposição e manutenção do equipamento de ordenha"),
    # 3.02 Despesas variáveis de venda
    _c("3.02", "Despesas variáveis de venda", _DESPESA_VARIAVEL),
    _c("3.02.01", "Frete do leite e de animais"),
    _c("3.02.02", "Comissões e taxas de venda"),
    # 3.03 Pessoal e serviços
    _c("3.03", "Pessoal e serviços de terceiros"),
    _c("3.03.01", "Pessoal", _GASTOS_PESSOAL),
    _c("3.03.01.01", "Salários e ordenados"),
    _c("3.03.01.02", "13º salário e férias"),
    _c("3.03.01.03", "Encargos (INSS e FGTS)"),
    _c("3.03.01.04", "Diárias e empreitadas"),
    _c("3.03.01.05", "Alimentação e benefícios dos funcionários"),
    # (3.03.01.16 Retenções e 3.03.01.17 Vales e adiantamentos: criadas por
    # plano_padrao.garantir_contas_do_sistema, com valores próprios.)
    _c("3.03.02", "Serviços de terceiros", _DESPESAS_OPERACIONAIS),
    _c("3.03.02.01", "Contabilidade e assessoria"),
    _c("3.03.02.02", "Consultoria técnica (zootecnista / agrônomo)"),
    _c("3.03.02.03", "Serviços gerais e mão de obra terceirizada"),
    # 3.04 Despesas operacionais
    _c("3.04", "Despesas operacionais", _DESPESAS_OPERACIONAIS),
    _c("3.04.01", "Energia elétrica"),
    _c("3.04.02", "Combustíveis e lubrificantes"),
    _c("3.04.03", "Manutenção de máquinas e equipamentos"),
    _c("3.04.04", "Manutenção de benfeitorias, cercas e instalações"),
    _c("3.04.05", "Materiais de consumo e utilidades"),
    _c("3.04.06", "Arrendamento e aluguéis pagos"),
    _c("3.04.07", "Telefone e internet"),
    _c("3.04.08", "Seguros"),
    # 3.05 Impostos e taxas
    _c("3.05", "Impostos e taxas", _DESPESAS_OPERACIONAIS),
    _c("3.05.01", "Contribuição sobre a venda (Funrural)", _DEDUCAO_IMPOSTOS),
    _c("3.05.02", "ITR"),
    _c("3.05.03", "IPVA, licenciamento e outras taxas"),
    _c("3.05.04", "Imposto de renda da atividade rural", _TRIBUTOS_IR_CSLL),
    # 3.06 Financeiras (só o juros é despesa; o principal é FINANCIAMENTO, fora da DRE)
    _c("3.06", "Despesas financeiras", _OUTRAS_REC_DESP),
    _c("3.06.01", "Juros e encargos de empréstimos"),
    _c("3.06.02", "Tarifas bancárias"),
    _c("3.06.03", "Pagamento de principal de empréstimos e financiamentos", _NAO_ENTRA_NA_DRE, _FINANCIAMENTO),
    # 3.07 Investimentos (bens do imobilizado) — fora da DRE; o desgaste vem da depreciação do patrimônio
    _c("3.07", "Investimentos (bens do imobilizado)", _NAO_ENTRA_NA_DRE, _INVESTIMENTO),
    _c("3.07.01", "Máquinas e equipamentos"),
    _c("3.07.02", "Benfeitorias e construções"),
    _c("3.07.03", "Veículos"),
    # 3.08 Retiradas do produtor
    _c("3.08", "Retiradas do produtor / sócio", _NAO_ENTRA_NA_DRE, _CAPITAL),
    _c("3.08.01", "Retirada do produtor (pró-labore e distribuições)"),
)


def contas_do_plano_padrao_rural() -> tuple[ContaPadrao, ...]:
    return PLANO_PADRAO_RURAL


def fazenda_tem_plano_de_contas(session: Session, fazenda_id: int | None) -> bool:
    from fazenda.models import PlanoContaGerencial

    q = select(PlanoContaGerencial.id)
    q = q.where(PlanoContaGerencial.fazenda_id == fazenda_id) if fazenda_id is not None \
        else q.where(PlanoContaGerencial.fazenda_id.is_(None))
    return session.exec(q.limit(1)).first() is not None


def carregar_plano_padrao_rural(session: Session, fazenda_id: int | None) -> int:
    """Carrega o plano padrão rural-leiteiro (RASCUNHO — validar com o
    contador) SE a fazenda não tem nenhuma conta no plano. Devolve quantas
    contas criou (0 quando já havia plano: nunca mistura com o plano que veio
    do Ideagri nem sobrescreve nada). Idempotente. Não faz commit."""
    from fazenda.models import PlanoContaGerencial

    if fazenda_tem_plano_de_contas(session, fazenda_id):
        return 0
    for conta in PLANO_PADRAO_RURAL:
        session.add(PlanoContaGerencial(
            fazenda_id=fazenda_id, codigo=conta.codigo, nome=conta.nome, ativa=True,
            linha_dre=conta.linha_dre, natureza_fin=conta.natureza_fin,
            rmca_receita_leite=True if conta.rmca_receita_leite else None,
            rmca_custo_alimentacao=True if conta.rmca_custo_alimentacao else None,
            pede_vinculo_sanitario_reprodutivo=True if conta.pede_vinculo_sanitario_reprodutivo else None,
        ))
    session.flush()
    return len(PLANO_PADRAO_RURAL)
