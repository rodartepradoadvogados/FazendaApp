"""
Contas do SISTEMA no plano de contas gerencial (Fase A, "Retenções" e "Vales
e adiantamentos"). Ver docs/financeiro-regras-v2.md §8.

O PROBLEMA. As origens automáticas `caixa_retencao` (o que a folha ou o
pagamento reteve para o caixa do funcionário) e `vale` (vale em dinheiro,
avulso, desconto de vale na folha) não tinham onde cair no plano: o plano de
contas da fazenda vem do CSV do Ideagri e não traz uma conta para elas.
Sem conta, o item gerado vira "(sem conta: ...)" na DRE e fica pendente até
alguém criar e configurar uma conta à mão.

A SOLUÇÃO. Duas contas folha sob 3.03.01 (Pessoal), com valores PRÓPRIOS de
`linha_dre` e `natureza_fin` (a herança por prefixo, em `rules/dre.py` e
`rules/natureza.py`, jogaria as duas na linha de gastos com pessoal):

    3.03.01.16  Retenções              NAO_ENTRA_NA_DRE  OBRIGACAO
    3.03.01.17  Vales e adiantamentos  NAO_ENTRA_NA_DRE  ADIANTAMENTO

O custo já está no bruto da folha/contrato: retenção é obrigação reconhecida
e vale é valor a receber da pessoa, os dois FORA do resultado.

QUEM GARANTE QUE AS CONTAS EXISTAM.
  - a migração `d8b3f6a1c294` (dados, aditiva): fazendas que já têm o plano;
  - esta função, chamada ao FINAL da importação do plano por CSV (que apaga e
    reinsere tudo: sem isto a reimportação levaria as contas embora) e ao
    ligar a flag `financeiro_regras_v2`.
Regra geral: conta do sistema tem de SOBREVIVER à reimportação do plano.

O QUE ELA NÃO FAZ. Não cria o grupo 3.03.01 (plano sem Pessoal não recebe as
contas), não sobrescreve conta que já exista com o mesmo código (mesmo com
outro nome: só devolve em `outro_nome` para o chamador registrar) e não faz
commit (quem chama decide a transação).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlmodel import Session, select

logger = logging.getLogger(__name__)

GRUPO_PESSOAL = "3.03.01"
CODIGO_RETENCOES = "3.03.01.16"
CODIGO_VALES = "3.03.01.17"

# Espelhos de rules.dre.NAO_ENTRA_NA_DRE / rules.natureza.OBRIGACAO e
# ADIANTAMENTO (evita importar o motor da DRE só por três strings).
_NAO_ENTRA_NA_DRE = "NAO_ENTRA_NA_DRE"
_OBRIGACAO = "OBRIGACAO"
_ADIANTAMENTO = "ADIANTAMENTO"


@dataclass(frozen=True)
class ContaDoSistema:
    codigo: str
    nome: str
    linha_dre: str
    natureza_fin: str
    tipo: str  # "despesa": o plano não guarda o tipo, ele vem do grupo 3 (despesas)
    ajuda: str


CONTAS_DO_SISTEMA: tuple[ContaDoSistema, ...] = (
    ContaDoSistema(
        CODIGO_RETENCOES, "Retenções", _NAO_ENTRA_NA_DRE, _OBRIGACAO, "despesa",
        "Retenção do caixa do funcionário: obrigação já reconhecida no custo bruto; fora da DRE.",
    ),
    ContaDoSistema(
        CODIGO_VALES, "Vales e adiantamentos", _NAO_ENTRA_NA_DRE, _ADIANTAMENTO, "despesa",
        "Vales e adiantamentos a funcionários: valor a receber da pessoa; fora da DRE.",
    ),
)

CODIGOS_DO_SISTEMA: frozenset[str] = frozenset(c.codigo for c in CONTAS_DO_SISTEMA)


@dataclass
class ResultadoGarantir:
    criadas: list[str] = field(default_factory=list)
    ja_existiam: list[str] = field(default_factory=list)
    # (codigo, nome que a conta já tem): existe com OUTRO nome, não foi tocada.
    outro_nome: list[tuple[str, str]] = field(default_factory=list)
    sem_grupo: bool = False


def _contas_da_fazenda(session: Session, fazenda_id: int | None):
    from fazenda.models import PlanoContaGerencial

    q = select(PlanoContaGerencial)
    q = q.where(PlanoContaGerencial.fazenda_id == fazenda_id) if fazenda_id is not None \
        else q.where(PlanoContaGerencial.fazenda_id.is_(None))
    return q


def garantir_contas_do_sistema(session: Session, fazenda_id: int | None) -> ResultadoGarantir:
    """Cria 3.03.01.16 e 3.03.01.17 no plano da fazenda, se faltarem — e só se
    o grupo 3.03.01 existir. Idempotente. Não faz commit."""
    from fazenda.models import PlanoContaGerencial

    resultado = ResultadoGarantir()
    base = _contas_da_fazenda(session, fazenda_id)
    existentes = {
        c.codigo: c for c in session.exec(base.where(
            PlanoContaGerencial.codigo.in_([GRUPO_PESSOAL, *sorted(CODIGOS_DO_SISTEMA)])
        )).all()
    }
    if GRUPO_PESSOAL not in existentes:
        resultado.sem_grupo = True
        return resultado
    for conta in CONTAS_DO_SISTEMA:
        atual = existentes.get(conta.codigo)
        if atual is not None:
            resultado.ja_existiam.append(conta.codigo)
            if (atual.nome or "").strip() != conta.nome:
                resultado.outro_nome.append((conta.codigo, atual.nome))
                logger.info("plano_padrao: %s já existe com outro nome na fazenda %s; não sobrescrevi",
                            conta.codigo, fazenda_id)
            continue
        session.add(PlanoContaGerencial(
            fazenda_id=fazenda_id, codigo=conta.codigo, nome=conta.nome, ativa=True,
            linha_dre=conta.linha_dre, natureza_fin=conta.natureza_fin,
        ))
        resultado.criadas.append(conta.codigo)
    if resultado.criadas:
        session.flush()
    return resultado


def contas_do_sistema_existentes(session: Session, fazenda_id: int | None) -> dict[str, str]:
    """{codigo: nome} das contas do sistema que existem E estão ativas no plano
    da fazenda (é o que libera o `codigo_preferido` dos papéis de retenção e
    vale em `rules/lancamento_automatico.py`)."""
    from fazenda.models import PlanoContaGerencial

    linhas = session.exec(_contas_da_fazenda(session, fazenda_id).where(
        PlanoContaGerencial.codigo.in_(sorted(CODIGOS_DO_SISTEMA)), PlanoContaGerencial.ativa.is_(True),
    )).all()
    return {c.codigo: c.nome for c in linhas}
