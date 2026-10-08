"""
Natureza econômica do lançamento financeiro — Fase A, regra R1 (PR 1).
Ver docs/financeiro-regras-v2.md.

NÃO CONFUNDIR com `PlanoContaGerencial.natureza` (que já existia e diz só se a
conta aceita item de SERVIÇO ou de PRODUTO). `natureza_fin` responde outra
pergunta: "este dinheiro é custo/receita da atividade, ou é outra coisa?"

| natureza       | DRE                               | Caixa/Fluxo     | Custos (ha/vaca/safra) |
|----------------|-----------------------------------|-----------------|------------------------|
| OPERACIONAL    | entra pela linha_dre (padrão)     | entra           | entra                  |
| INVESTIMENTO   | fora; só a depreciação entra      | entra           | fora (depreciação no COT) |
| FINANCIAMENTO  | fora (entrada de empréstimo/principal) | entra      | fora                   |
| CAPITAL        | fora (aporte/retirada de sócio)   | entra           | fora                   |
| TRANSFERENCIA  | fora                              | só move contas  | fora                   |
| ADIANTAMENTO   | fora (vale: valor a receber)      | entra           | fora                   |
| OBRIGACAO      | fora (quita algo já reconhecido)  | entra           | fora                   |

A natureza só MUDA NÚMERO quando a fazenda tem a flag `financeiro_regras_v2`
ligada (ver `rules/parametros.py::regras_v2_ativas`). Com a flag desligada os
campos são gravados e exibidos, mas nenhum relatório os lê.

Ordem de resolução (`resolver_natureza`, função pura):
  1. `LancamentoItem.natureza_fin` explícita (sobrepõe a da nota — usada pela
     folha no PR 3 para os itens redutores);
  2. `ContaGerencial.natureza_fin` explícita (formulário, criação com
     patrimônio, compra de matriz/reprodutor, backfill);
  3. receita ligada a um bem BAIXADO COM VENDA → INVESTIMENTO (desinvestimento:
     o ganho/perda entra em Outras pela baixa, a receita cheia não pode entrar
     de novo como "receita de vendas");
  4. `PlanoContaGerencial.natureza_fin` por herança de prefixo (igual
     `resolver_linha_dre`);
  5. `linha_dre == NAO_ENTRA_NA_DRE` → `NAO_INFORMADA` ("fora, motivo não
     informado" — continua fora, como sempre esteve);
  6. OPERACIONAL.

Desvio consciente do SOLUCOES.md (§R1, passo 2): a regra "despesa com
patrimonio_id vira INVESTIMENTO" NÃO roda em tempo de leitura. Em leitura não
há como distinguir a compra do bem de uma manutenção ligada à mão ao mesmo bem
(falso positivo que tiraria custo real da DRE). Ela roda (a) na CRIAÇÃO, com
`criar_patrimonio`, gravando a natureza explícita, e (b) no backfill
conservador (`rules/backfill_natureza.py`: valor ±10% do bem e competência a
até 60 dias da imobilização), que também gera a lista de revisão.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

OPERACIONAL = "OPERACIONAL"
INVESTIMENTO = "INVESTIMENTO"
FINANCIAMENTO = "FINANCIAMENTO"
CAPITAL = "CAPITAL"
TRANSFERENCIA = "TRANSFERENCIA"
ADIANTAMENTO = "ADIANTAMENTO"
OBRIGACAO = "OBRIGACAO"

# Valores que podem ser GRAVADOS em natureza_fin (conta, item ou plano).
NATUREZAS: tuple[str, ...] = (
    OPERACIONAL, INVESTIMENTO, FINANCIAMENTO, CAPITAL, TRANSFERENCIA, ADIANTAMENTO, OBRIGACAO,
)

# Pseudo-natureza, NUNCA gravada: conta com linha_dre = NAO_ENTRA_NA_DRE e sem
# natureza informada. Continua fora da DRE (como sempre esteve), agrupada à
# parte para o usuário dizer o motivo.
NAO_INFORMADA = "NAO_INFORMADA"

NATUREZAS_FORA_DA_DRE: frozenset[str] = frozenset(set(NATUREZAS) - {OPERACIONAL} | {NAO_INFORMADA})

ROTULOS: dict[str, str] = {
    OPERACIONAL: "Operacional",
    INVESTIMENTO: "Investimentos (bens do imobilizado)",
    FINANCIAMENTO: "Financiamentos (empréstimo e principal)",
    CAPITAL: "Capital (aporte e retirada de sócio)",
    TRANSFERENCIA: "Transferências entre contas",
    ADIANTAMENTO: "Adiantamentos (vales a receber)",
    OBRIGACAO: "Obrigações (quitação de valor já reconhecido)",
    NAO_INFORMADA: "Fora da DRE, motivo não informado",
}

# Ordem de exibição dos grupos no bloco "fora da DRE".
ORDEM_EXIBICAO: tuple[str, ...] = (
    INVESTIMENTO, FINANCIAMENTO, CAPITAL, TRANSFERENCIA, ADIANTAMENTO, OBRIGACAO, NAO_INFORMADA,
)

_NAO_ENTRA_NA_DRE = "NAO_ENTRA_NA_DRE"  # espelho de rules.dre.NAO_ENTRA_NA_DRE (evita import circular)


def normalizar_natureza(valor: str | None) -> str | None:
    """'investimento ' → 'INVESTIMENTO'; None/'' → None. Valor fora da lista
    levanta ValueError (o router transforma em 400)."""
    if valor is None:
        return None
    texto = str(valor).strip().upper()
    if not texto:
        return None
    texto = _sem_acento(texto).replace(" ", "_")
    if texto not in NATUREZAS:
        raise ValueError(f"natureza_fin inválida: {valor!r}. Use uma destas: {', '.join(NATUREZAS)}.")
    return texto


def resolver_natureza_plano(codigo: str | None, mapa_natureza_plano: dict[str, str]) -> str | None:
    """Herança por prefixo, igual `rules.dre.resolver_linha_dre`: "3.10.02"
    sem natureza própria herda a de "3.10"."""
    if not codigo:
        return None
    partes = codigo.split(".")
    for fim in range(len(partes), 0, -1):
        natureza = mapa_natureza_plano.get(".".join(partes[:fim]))
        if natureza:
            return natureza
    return None


def resolver_natureza(
    *,
    natureza_item: str | None = None,
    natureza_conta: str | None = None,
    tipo: str | None = None,
    patrimonio_id: int | None = None,
    patrimonios_vendidos: frozenset[int] | set[int] = frozenset(),
    codigo_conta: str | None = None,
    mapa_natureza_plano: dict[str, str] | None = None,
    linha_dre: str | None = None,
) -> str:
    """Natureza efetiva de um registro (item ou nota sem item). Pura — quem
    chama monta os mapas. Ver a ordem no docstring do módulo."""
    if natureza_item in NATUREZAS:
        return natureza_item
    if natureza_conta in NATUREZAS:
        return natureza_conta
    if tipo == "receita" and patrimonio_id is not None and patrimonio_id in patrimonios_vendidos:
        return INVESTIMENTO
    do_plano = resolver_natureza_plano(codigo_conta, mapa_natureza_plano or {})
    if do_plano in NATUREZAS:
        return do_plano
    if linha_dre == _NAO_ENTRA_NA_DRE:
        return NAO_INFORMADA
    return OPERACIONAL


def entra_na_dre(natureza: str | None) -> bool:
    return natureza in (None, OPERACIONAL)


def entra_nos_custos(natureza: str | None) -> bool:
    """Custos por ha/vaca/safra (e o futuro COE): só o OPERACIONAL."""
    return natureza in (None, OPERACIONAL)


@dataclass
class ContextoNatureza:
    """Tudo que `resolver_natureza` precisa além do próprio registro — montado
    UMA vez por consulta (ver financeiro.py::_contexto_natureza).

    `sobrepor_conta`/`sobrepor_item`: naturezas simuladas por id, usadas pelo
    script de impacto para medir um backfill ANTES de gravá-lo (nada é
    escrito no banco)."""

    mapa_natureza_plano: dict[str, str] = field(default_factory=dict)
    mapa_linha_dre: dict[str, str] = field(default_factory=dict)
    patrimonios_vendidos: frozenset[int] = frozenset()
    sobrepor_conta: dict[int, str] = field(default_factory=dict)
    sobrepor_item: dict[int, str] = field(default_factory=dict)

    def natureza(self, *, item=None, conta=None, codigo_conta: str | None = None, tipo: str | None = None) -> str:
        from fazenda.rules.dre import resolver_linha_dre

        natureza_item = None
        if item is not None:
            natureza_item = self.sobrepor_item.get(getattr(item, "id", None)) or getattr(item, "natureza_fin", None)
        natureza_conta = None
        patrimonio_id = None
        if conta is not None:
            natureza_conta = self.sobrepor_conta.get(getattr(conta, "id", None)) or getattr(conta, "natureza_fin", None)
            patrimonio_id = getattr(conta, "patrimonio_id", None)
            tipo = tipo or getattr(conta, "tipo", None)
        return resolver_natureza(
            natureza_item=natureza_item,
            natureza_conta=natureza_conta,
            tipo=tipo,
            patrimonio_id=patrimonio_id,
            patrimonios_vendidos=self.patrimonios_vendidos,
            codigo_conta=codigo_conta,
            mapa_natureza_plano=self.mapa_natureza_plano,
            linha_dre=resolver_linha_dre(codigo_conta, self.mapa_linha_dre),
        )


# ---------------------------------------------------------------------------
# Inferência pelo NOME (plano de contas, descrição) — só SUGERE. Quem aplica é
# o backfill, e só onde não muda número (conta já NAO_ENTRA_NA_DRE) ou onde a
# regra é conservadora; o resto vira lista de revisão.
# ---------------------------------------------------------------------------
def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def _normalizar_nome(nome: str | None) -> str:
    return re.sub(r"\s+", " ", _sem_acento(nome or "").lower()).strip()


# Despesa financeira de verdade (juros, IOF, tarifa) NÃO é principal: nunca
# pode virar FINANCIAMENTO só porque o nome menciona "financiamento".
_EH_DESPESA_FINANCEIRA = re.compile(r"\b(juro|juros|encargo|encargos|iof|tarifa|tarifas|multa|multas|mora)\b")
_EH_MANUTENCAO = re.compile(r"\b(manutenc|conserto|reparo|revisao|peca|pecas|combustiv|diesel|oleo|pneu|aluguel|locacao)")

_PADROES: tuple[tuple[str, re.Pattern, str], ...] = (
    (FINANCIAMENTO, re.compile(r"\bprincipal\b"), "nome indica principal de financiamento"),
    (FINANCIAMENTO, re.compile(r"\bamortiza\w*\s+(de\s+|do\s+|da\s+)?(financ|emprest|divid)"), "nome indica amortização de dívida"),
    (FINANCIAMENTO, re.compile(r"\b(emprestimo|emprestimos|financiamento|financiamentos)\b"), "nome indica empréstimo/financiamento"),
    (CAPITAL, re.compile(r"\b(aporte|aportes|integralizacao|capital social|retirada de socio|retiradas de socio|distribuicao de lucro)"), "nome indica movimento de capital do sócio"),
    (TRANSFERENCIA, re.compile(r"\btransferencia"), "nome indica transferência entre contas"),
    (INVESTIMENTO, re.compile(r"\b(matriz|matrizes|reprodutor|reprodutores|touro|touros)\b"), "nome indica compra de matriz/reprodutor (ativo biológico)"),
    (INVESTIMENTO, re.compile(r"\b(investimento|investimentos|imobilizado|imobilizacao|benfeitoria|benfeitorias)\b"), "nome indica investimento/imobilizado"),
    (INVESTIMENTO, re.compile(r"\baquisic\w*\s+de\s+(maquina|equipamento|veiculo|implemento|terra|imovel|benfeitoria)"), "nome indica aquisição de bem"),
    (INVESTIMENTO, re.compile(r"^(maquinas|maquinas e equipamentos|veiculos|implementos|instalacoes|construcoes)$"), "nome é de grupo do imobilizado"),
)


def inferir_natureza_por_nome(nome: str | None) -> tuple[str | None, str | None]:
    """(natureza sugerida, motivo) a partir do nome de uma conta do plano ou
    da descrição de um lançamento. (None, None) quando nada casa. Nunca grava
    nada — é insumo do backfill e da tela de conferência."""
    texto = _normalizar_nome(nome)
    if not texto:
        return None, None
    for natureza, padrao, motivo in _PADROES:
        if not padrao.search(texto):
            continue
        if natureza == FINANCIAMENTO and _EH_DESPESA_FINANCEIRA.search(texto):
            continue
        if natureza == INVESTIMENTO and _EH_MANUTENCAO.search(texto):
            continue
        return natureza, motivo
    return None, None


def eh_matriz_ou_reprodutor(*textos: str | None) -> bool:
    """Compra de animal de matriz/reprodutor = INVESTIMENTO (recomendação do
    contador, Q10). Animal para recria/venda continua OPERACIONAL."""
    padrao = re.compile(r"\b(matriz|matrizes|reprodutor|reprodutores|touro|touros)\b")
    return any(padrao.search(_normalizar_nome(t)) for t in textos if t)
