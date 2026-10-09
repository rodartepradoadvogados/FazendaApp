"""
Lançamentos automáticos com conta e itens — Fase A, PR 2 (contas automáticas)
e PR 3 (folha pelo bruto e encargos). Ver docs/financeiro-regras-v2.md §8.

O PROBLEMA (SOLUCOES.md, P0-2 e P0-8). Folha, férias, 13º, rescisão,
contratos, empreitas, diárias, vales em dinheiro e o caixa do funcionário
criavam a `ContaGerencial` sem `codigo_conta` e sem `LancamentoItem`: tudo
caía em "não classificado" na DRE e "Gastos com pessoal" nunca recebia a
folha. E a folha entrava pelo LÍQUIDO: o vale de item, o INSS e o IR retidos
sumiam do custo de pessoal.

O QUE ESTE MÓDULO FAZ (só com a flag `financeiro_regras_v2` da fazenda):
cada nota automática ganha UM `LancamentoItem` POR LINHA ECONÔMICA, marcado
com `gerado_por` = o PAPEL do item, na conta padrão da origem
(`ContaPadraoOrigem`, Configurações > Parâmetros financeiros > Contas
automáticas). A soma dos itens é sempre o `valor_total` da nota (o que se
paga): a nota fecha. Ex. da folha (bruto 3.000, INSS 240, vale 200, FGTS
projetado 240; líquido 2.560):

    Salário e verbas            +3.000  conta folha_salario  (Gastos com pessoal)
    (−) INSS e IRRF retidos       −240  OBRIGACAO            (fora da DRE)
    (−) Vale descontado           −200  ADIANTAMENTO         (fora da DRE)
    FGTS (provisão)               +240  conta encargo_fgts   (Gastos com pessoal)
    (−) FGTS a recolher           −240  OBRIGACAO            (fora da DRE)
                                 =2.560

Decisões do dono/contador aplicadas aqui: a folha entra pelo BRUTO na data do
líquido (DRE de caixa = data do pagamento da nota); encargo sem guia lançada
usa a PROVISÃO da folha (`valor_fgts`/`valor_dctf`) e a guia, quando entra,
quita o provisionado (OBRIGACAO) — só o excedente é encargo, multa e juros vão
para Outras; cota de VT e coparticipação descontadas REDUZEM o custo de
pessoal (item negativo na própria conta de salário); sem provisão mensal de
13º/férias (o 13º cai no mês em que é lançado).

COMO OS ITENS NASCEM E SE MANTÊM. Um único ponto: os listeners de sessão
`after_flush`/`after_flush_postexec` (registrados no import deste módulo,
que o router do Financeiro importa). Toda nota automática NOVA de uma fazenda
com a flag ligada ganha os itens no mesmo commit em que nasce, venha de qual
dos 15 pontos de criação vier — e quando o `valor_total` (ou a folha, a
rubrica, o vale, o caixa) muda depois, os itens são refeitos. É de propósito
um ponto só, e não uma chamada em cada rota: a folha tem pelo menos seis
caminhos que reescrevem o líquido da conta a pagar (edição, self-heal do vale,
do vale-alimentação, das retenções, das rubricas...), e um item esquecido num
deles deixaria a nota com itens que não fecham. Excluir a nota apaga os itens
gerados (o número do lançamento é reaproveitável).

O que NÃO é tocado: nota com qualquer item lançado por gente (o usuário
reclassificou no Financeiro — vale o dele); nota antiga sem itens (o
histórico só ganha itens pelo backfill, comando separado, ver
`rules/backfill_itens_automaticos.py`); nada de `valor_total`/`valor_pago`.
Com a flag desligada nada disto roda e as regras antigas dos relatórios
IGNORAM itens com `gerado_por` (a nota é lida como sempre foi).

LGPD: nenhum log deste módulo leva nome, CPF ou valor de pessoa — só o
número do lançamento.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy import event, inspect as sa_inspect
from sqlmodel import Session, select

from fazenda.rules.natureza import ADIANTAMENTO, NATUREZAS, OBRIGACAO, OPERACIONAL
from fazenda.rules.plano_padrao import CODIGO_RETENCOES, CODIGO_VALES, contas_do_sistema_existentes

logger = logging.getLogger(__name__)

OUTRAS_REC_DESP = "OUTRAS_REC_DESP"  # espelho de rules.dre (evita import circular)


# ---------------------------------------------------------------------------
# Origens (uma conta padrão por origem, configurável por fazenda)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Origem:
    chave: str
    rotulo: str
    ajuda: str
    natureza: str = OPERACIONAL
    palavras: tuple[str, ...] = ()
    # Origem cuja conta vale quando esta não estiver configurada (ex.: férias
    # sem conta própria caem na conta de salários) — None = vira pendência.
    reserva: str | None = None


ORIGENS: dict[str, Origem] = {o.chave: o for o in (
    Origem("folha_salario", "Salários e verbas da folha",
           "Bruto da folha (salário, verbas, vale-alimentação) e o que é descontado do funcionário sem ser "
           "retenção (cota do vale-transporte, coparticipação), que reduz o custo.",
           palavras=("salario", "salarios", "ordenado", "folha de pagamento", "folha")),
    Origem("folha_ferias", "Férias", "Férias com o terço constitucional e o abono.",
           palavras=("ferias",), reserva="folha_salario"),
    Origem("folha_13", "13º salário", "Parcelas do 13º, pelo bruto.",
           palavras=("13", "decimo terceiro", "13o"), reserva="folha_salario"),
    Origem("rescisao", "Rescisões", "Verbas rescisórias, pelo bruto.",
           palavras=("rescis", "verbas rescis"), reserva="folha_salario"),
    Origem("encargo_fgts", "FGTS (encargo do empregador)",
           "Provisão do FGTS da folha e o que a guia de FGTS cobrar além do provisionado.",
           palavras=("fgts",), reserva="folha_salario"),
    Origem("encargo_inss_patronal", "INSS patronal e encargos da DCTF",
           "Provisão de encargos da DCTF na folha e o que a guia cobrar além dos retidos e do provisionado.",
           palavras=("inss", "dctf", "previdenc", "encargos sociais", "encargo"), reserva="folha_salario"),
    Origem("obrigacao_inss_irrf_retidos", "Retidos e encargos a recolher",
           "INSS e IRRF retidos do funcionário e encargos provisionados a recolher. Não é custo de novo "
           "(o custo já está no bruto e na provisão): fica fora da DRE, como obrigação.",
           natureza=OBRIGACAO, palavras=("a recolher", "retid")),
    Origem("contrato", "Contratos de prestação de serviço", "Parcelas de contrato, pelo valor contratado.",
           palavras=("contrato", "prestador", "prestacao de servic", "terceiriz", "mao de obra")),
    Origem("empreita", "Empreitas", "Parcelas e etapas de empreita, pelo valor contratado.",
           palavras=("empreit",), reserva="contrato"),
    Origem("diaria", "Diárias", "Pagamentos e acertos de diária, pelo bruto.",
           palavras=("diaria", "diarias", "diarista"), reserva="contrato"),
    Origem("vale", "Vales e adiantamentos a funcionários",
           "Vale em dinheiro, vale avulso e o vale descontado na folha. É um valor a receber da pessoa: "
           "fica fora da DRE (o custo aparece pela folha bruta).",
           natureza=ADIANTAMENTO, palavras=("vale", "adiantamento")),
    Origem("caixa_entrada", "Prêmios e comissões (caixa do funcionário)",
           "Depósito, bonificação ou comissão lançados no caixa do funcionário ou do time.",
           palavras=("premio", "premios", "bonific", "comiss", "gratific"), reserva="folha_salario"),
    Origem("caixa_retencao", "Retenção do caixa do funcionário",
           "O que a folha ou o pagamento reteve para o caixa do funcionário. O custo já está no bruto: "
           "fica fora da DRE, como obrigação.",
           natureza=OBRIGACAO, palavras=("retenc", "caixa do funcionario")),
)}


@dataclass(frozen=True)
class Papel:
    origem: str | None
    rotulo: str
    natureza: str | None = None        # explícita no item; None = herda da conta/plano
    linha_forcada: str | None = None   # pseudoconta das regras v2 (multa/juros da guia)
    # Conta do SISTEMA (rules/plano_padrao.py) usada quando a origem não tem
    # conta configurada E a conta existe e está ativa no plano da fazenda.
    codigo_preferido: str | None = None


PAPEIS: dict[str, Papel] = {
    "folha_salario": Papel("folha_salario", "Salário e verbas"),
    "folha_outros_descontos": Papel("folha_salario", "(−) Outros descontos (VT, coparticipação, faltas)"),
    "folha_retidos": Papel("obrigacao_inss_irrf_retidos", "(−) INSS e IRRF retidos", OBRIGACAO),
    "folha_vale": Papel("vale", "(−) Vale descontado", ADIANTAMENTO, codigo_preferido=CODIGO_VALES),
    "folha_retencao_caixa": Papel("caixa_retencao", "(−) Retenção do caixa do funcionário", OBRIGACAO,
        codigo_preferido=CODIGO_RETENCOES),
    "folha_fgts_provisao": Papel("encargo_fgts", "FGTS (provisão)"),
    "folha_fgts_a_recolher": Papel("obrigacao_inss_irrf_retidos", "(−) FGTS a recolher", OBRIGACAO),
    "folha_dctf_provisao": Papel("encargo_inss_patronal", "Encargos da DCTF (provisão)"),
    "folha_dctf_a_recolher": Papel("obrigacao_inss_irrf_retidos", "(−) Encargos da DCTF a recolher", OBRIGACAO),
    "ferias_bruto": Papel("folha_ferias", "Férias (com 1/3 e abono)"),
    "decimo_bruto": Papel("folha_13", "13º salário (bruto)"),
    "decimo_retidos": Papel("obrigacao_inss_irrf_retidos", "(−) INSS e IRRF retidos", OBRIGACAO),
    "rescisao_verbas": Papel("rescisao", "Verbas rescisórias (bruto)"),
    "rescisao_retidos": Papel("obrigacao_inss_irrf_retidos", "(−) INSS e IRRF retidos", OBRIGACAO),
    "rescisao_vale": Papel("vale", "(−) Vale descontado", ADIANTAMENTO, codigo_preferido=CODIGO_VALES),
    "guia_retidos": Papel("obrigacao_inss_irrf_retidos", "Retidos na folha (quitação)", OBRIGACAO),
    "guia_provisionado": Papel("obrigacao_inss_irrf_retidos", "Encargo já provisionado na folha (quitação)", OBRIGACAO),
    "guia_encargo_fgts": Papel("encargo_fgts", "FGTS além do provisionado"),
    "guia_encargo_patronal": Papel("encargo_inss_patronal", "Encargo patronal além do provisionado"),
    "guia_multa_juros": Papel(None, "Multa e juros da guia", None, OUTRAS_REC_DESP),
    "contrato_bruto": Papel("contrato", "Contrato (valor contratado)"),
    "empreita_bruto": Papel("empreita", "Empreita (valor contratado)"),
    "diaria_bruto": Papel("diaria", "Diária (bruto)"),
    "contrato_vale": Papel("vale", "(−) Vale abatido", ADIANTAMENTO, codigo_preferido=CODIGO_VALES),
    "empreita_vale": Papel("vale", "(−) Vale abatido", ADIANTAMENTO, codigo_preferido=CODIGO_VALES),
    "diaria_vale": Papel("vale", "(−) Vale abatido", ADIANTAMENTO, codigo_preferido=CODIGO_VALES),
    "contrato_retencao": Papel("caixa_retencao", "(−) Retenção do caixa do funcionário", OBRIGACAO,
        codigo_preferido=CODIGO_RETENCOES),
    "empreita_retencao": Papel("caixa_retencao", "(−) Retenção do caixa do funcionário", OBRIGACAO,
        codigo_preferido=CODIGO_RETENCOES),
    "diaria_retencao": Papel("caixa_retencao", "(−) Retenção do caixa do funcionário", OBRIGACAO,
        codigo_preferido=CODIGO_RETENCOES),
    "vale": Papel("vale", "Vale (adiantamento)", ADIANTAMENTO, codigo_preferido=CODIGO_VALES),
    "vale_devolucao": Papel("vale", "Devolução de vale", ADIANTAMENTO, codigo_preferido=CODIGO_VALES),
    "vale_assumido": Papel("folha_salario", "Vale assumido pela fazenda"),
    "caixa_entrada": Papel("caixa_entrada", "Entrada no caixa do funcionário"),
    "caixa_retencao": Papel("caixa_retencao", "Retenção do caixa do funcionário", OBRIGACAO,
        codigo_preferido=CODIGO_RETENCOES),
}

# tipo_documento das notas que o sistema cria (ver os routers de RH/caixa).
DOC_FOLHA = "Folha de pagamento"
DOC_FERIAS = "Férias"
DOC_13 = "13º salário"
DOC_RESCISAO = "Rescisão"
DOC_GUIAS = ("Guia FGTS", "Guia DCTF")
DOC_CONTRATO = "Contrato"
DOC_EMPREITA = "Empreitada"
DOC_DIARIA = "Diária"
DOC_ACERTO_DIARIA = "Acerto de diária"
DOC_VALES = ("Vale de funcionário", "Vale avulso")
DOC_RECIBO = "Recibo"
DOCS_CAIXA = ("Caixa do funcionário", "Caixa do time")
DOCS_ESTORNO_CAIXA = ("Estorno caixa do funcionário", "Estorno caixa do time")
CODIGO_RUBRICA_RETENCAO = "retencao_caixa"  # espelho de rules.caixa_funcionario.CODIGO_RUBRICA

TIPOS_DOCUMENTO_AUTOMATICOS: frozenset[str] = frozenset((
    DOC_FOLHA, DOC_FERIAS, DOC_13, DOC_RESCISAO, *DOC_GUIAS, DOC_CONTRATO, DOC_EMPREITA, DOC_DIARIA,
    DOC_ACERTO_DIARIA, *DOC_VALES, DOC_RECIBO, *DOCS_CAIXA, *DOCS_ESTORNO_CAIXA,
))


def _r2(v: float | None) -> float:
    return round(float(v or 0.0), 2)


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def _norm(texto: str | None) -> str:
    return re.sub(r"\s+", " ", _sem_acento(texto or "").lower()).strip()


# ---------------------------------------------------------------------------
# Configuração (ContaPadraoOrigem) e sugestão pelo plano de contas
# ---------------------------------------------------------------------------
@dataclass
class ContaResolvida:
    codigo: str | None
    nome: str | None
    natureza: str | None
    origem_usada: str | None  # a própria ou a reserva que forneceu a conta


@dataclass
class Configuracao:
    linhas: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)  # origem -> (codigo, natureza)
    nomes_plano: dict[str, str] = field(default_factory=dict)
    # Contas do sistema (3.03.01.16/17) que existem e estão ativas no plano.
    contas_sistema: dict[str, str] = field(default_factory=dict)

    def conta(self, origem: str | None) -> ContaResolvida:
        if origem is None:
            return ContaResolvida(None, None, None, None)
        natureza_cfg = (self.linhas.get(origem) or (None, None))[1]
        atual, vistos = origem, set()
        while atual and atual not in vistos:
            vistos.add(atual)
            codigo = (self.linhas.get(atual) or (None, None))[0]
            if codigo:
                return ContaResolvida(codigo, self.nomes_plano.get(codigo), natureza_cfg, atual)
            atual = ORIGENS[atual].reserva if atual in ORIGENS else None
        return ContaResolvida(None, None, natureza_cfg, None)


def carregar_configuracao(session: Session, fazenda_id: int | None) -> Configuracao:
    from fazenda.models import ContaPadraoOrigem, PlanoContaGerencial

    cfg = Configuracao()
    if not isinstance(fazenda_id, int):
        return cfg
    for linha in session.exec(select(ContaPadraoOrigem).where(ContaPadraoOrigem.fazenda_id == fazenda_id)).all():
        cfg.linhas[linha.origem] = (linha.codigo_conta_gerencial or None, linha.natureza_fin or None)
    codigos = {c for c, _n in cfg.linhas.values() if c}
    if codigos:
        for p in session.exec(select(PlanoContaGerencial).where(
            PlanoContaGerencial.fazenda_id == fazenda_id, PlanoContaGerencial.codigo.in_(sorted(codigos)),
        )).all():
            cfg.nomes_plano[p.codigo] = p.nome
    cfg.contas_sistema = contas_do_sistema_existentes(session, fazenda_id)
    return cfg


def conta_do_sistema_da_origem(origem: str) -> str | None:
    """Código da conta do sistema (3.03.01.16/17) que os papéis desta origem
    usam quando ela não tem conta configurada — None para as demais origens."""
    return next((p.codigo_preferido for p in PAPEIS.values() if p.origem == origem and p.codigo_preferido), None)


def sugerir_conta(origem: str, plano: list) -> dict | None:
    """Conta do plano cujo NOME casa com a origem (ex.: "Salários" para a
    folha). Só SUGESTÃO para a tela — nunca é aplicada sozinha (a conta
    errada jogaria a folha inteira numa linha errada; o dono confirma)."""
    o = ORIGENS.get(origem)
    if o is None or not o.palavras:
        return None
    melhores: list[tuple[int, str, object]] = []
    for conta in plano:
        if getattr(conta, "ativa", True) is False:
            continue
        nome = _norm(getattr(conta, "nome", ""))
        if not nome:
            continue
        for peso, palavra in enumerate(o.palavras):
            if re.search(rf"(^|\W){re.escape(palavra)}", nome):
                # Mais específica (código mais longo) e palavra mais forte primeiro.
                melhores.append((peso, "~" * (10 - min(conta.codigo.count("."), 9)) + conta.codigo, conta))
                break
    if not melhores:
        return None
    _peso, _ordem, conta = sorted(melhores, key=lambda t: (t[0], t[1]))[0]
    return {"codigo": conta.codigo, "nome": conta.nome}


# ---------------------------------------------------------------------------
# Composição: que itens a nota deve ter
# ---------------------------------------------------------------------------
@dataclass
class ItemDesejado:
    papel: str
    valor: float
    codigo_preferido: str | None = None  # usado quando a origem não tem conta configurada


def _uma_linha(papel: str, total: float, codigo_preferido: str | None = None) -> list[ItemDesejado]:
    return [ItemDesejado(papel, _r2(total), codigo_preferido)]


def _fechar(itens: list[ItemDesejado], total: float, papel_residual: str) -> list[ItemDesejado]:
    """A soma dos itens tem de ser o total da nota: o arredondamento ou um
    desconto que não deu para identificar vai para o item principal (mesma
    conta de pessoal — o custo total não muda de lugar)."""
    soma = _r2(sum(i.valor for i in itens))
    residuo = _r2(total - soma)
    if residuo:
        alvo = next((i for i in itens if i.papel == papel_residual), None)
        if alvo is None:
            itens.insert(0, ItemDesejado(papel_residual, residuo))
        else:
            alvo.valor = _r2(alvo.valor + residuo)
    return [i for i in itens if i.valor]


def _primeiro(session: Session, modelo, coluna: str, numero: str, fazenda_id: int | None):
    q = select(modelo).where(getattr(modelo, coluna) == numero)
    if fazenda_id is not None:
        q = q.where(modelo.fazenda_id == fazenda_id)
    return session.exec(q).first()


def _compor_folha(session: Session, folha, total: float) -> list[ItemDesejado]:
    from fazenda.models import FolhaRubrica

    rubricas = list(session.exec(select(FolhaRubrica).where(FolhaRubrica.folha_id == folha.id)).all()) if folha.id else []
    venc_rub = sum(r.valor or 0 for r in rubricas if r.especie == "vencimento")
    retencao = sum(r.valor or 0 for r in rubricas if r.especie == "desconto" and r.codigo == CODIGO_RUBRICA_RETENCAO)
    outros_rub = sum(r.valor or 0 for r in rubricas if r.especie == "desconto" and r.codigo != CODIGO_RUBRICA_RETENCAO)
    fgts, dctf = _r2(folha.valor_fgts), _r2(folha.valor_dctf)
    itens = [
        ItemDesejado("folha_salario", _r2((folha.valor_bruto or 0) + venc_rub)),
        ItemDesejado("folha_outros_descontos", -_r2((folha.descontos or 0) + outros_rub)),
        ItemDesejado("folha_retidos", -_r2((folha.valor_inss or 0) + (folha.valor_ir or 0))),
        ItemDesejado("folha_vale", -_r2(folha.valor_vale)),
        ItemDesejado("folha_retencao_caixa", -_r2(retencao)),
    ]
    itens = _fechar(itens, total, "folha_salario")
    # A provisão (+) e a obrigação (−) do mesmo encargo se anulam na nota: a
    # soma continua sendo o líquido, e o custo do encargo entra em pessoal.
    if fgts > 0:
        itens += [ItemDesejado("folha_fgts_provisao", fgts), ItemDesejado("folha_fgts_a_recolher", -fgts)]
    if dctf > 0:
        itens += [ItemDesejado("folha_dctf_provisao", dctf), ItemDesejado("folha_dctf_a_recolher", -dctf)]
    return itens


def _retidos_e_provisoes_da_competencia(session: Session, fazenda_id: int | None, competencia: str) -> dict:
    """O que as folhas (e 13º/rescisões) da competência já reconheceram como
    custo e deixaram A RECOLHER — é o que a guia quita sem ser custo de novo."""
    from fazenda.models import DecimoTerceiro, FolhaPagamento, RescisaoFuncionario

    q = select(FolhaPagamento).where(FolhaPagamento.competencia == competencia)
    if fazenda_id is not None:
        q = q.where(FolhaPagamento.fazenda_id == fazenda_id)
    folhas = session.exec(q).all()
    retidos = sum((f.valor_inss or 0) + (f.valor_ir or 0) for f in folhas)
    fgts = sum(f.valor_fgts or 0 for f in folhas)
    dctf = sum(f.valor_dctf or 0 for f in folhas)
    try:
        ano, mes = (int(x) for x in competencia.split("-"))
    except ValueError:
        return {"retidos": _r2(retidos), "fgts": _r2(fgts), "dctf": _r2(dctf)}
    if mes == 12:
        q13 = select(DecimoTerceiro).where(DecimoTerceiro.ano == ano, DecimoTerceiro.status != "cancelado_rescisao")
        if fazenda_id is not None:
            q13 = q13.where(DecimoTerceiro.fazenda_id == fazenda_id)
        retidos += sum((d.valor_inss or 0) + (d.valor_ir or 0) for d in session.exec(q13).all())
    qr = select(RescisaoFuncionario).where(RescisaoFuncionario.status == "fechada")
    if fazenda_id is not None:
        qr = qr.where(RescisaoFuncionario.fazenda_id == fazenda_id)
    retidos += sum(
        (r.valor_inss or 0) + (r.valor_ir or 0) for r in session.exec(qr).all()
        if r.data_desligamento and (r.data_desligamento.year, r.data_desligamento.month) == (ano, mes)
    )
    return {"retidos": _r2(retidos), "fgts": _r2(fgts), "dctf": _r2(dctf)}


def _compor_guia(session: Session, guia, conta, total: float) -> list[ItemDesejado]:
    principal = _r2(guia.valor_principal)
    multa_juros = _r2((guia.valor_multa or 0) + (guia.valor_juros or 0))
    base = _retidos_e_provisoes_da_competencia(session, guia.fazenda_id, guia.competencia)
    codigo_guia = conta.codigo_conta  # o código fixo de sempre da guia (3.03.01.0x)
    if guia.tipo == "fgts":
        provisionado = min(principal, base["fgts"])
        itens = [
            ItemDesejado("guia_provisionado", _r2(provisionado)),
            ItemDesejado("guia_encargo_fgts", _r2(principal - provisionado), codigo_guia),
        ]
        papel_residual = "guia_encargo_fgts"
    else:
        retidos = min(principal, base["retidos"])
        provisionado = min(_r2(principal - retidos), base["dctf"])
        itens = [
            ItemDesejado("guia_retidos", _r2(retidos)),
            ItemDesejado("guia_provisionado", _r2(provisionado)),
            ItemDesejado("guia_encargo_patronal", _r2(principal - retidos - provisionado), codigo_guia),
        ]
        papel_residual = "guia_encargo_patronal"
    itens.append(ItemDesejado("guia_multa_juros", multa_juros))
    fechados = _fechar(itens, total, papel_residual)
    for i in fechados:  # o residual pode ter criado o item do encargo sem o código da guia
        if i.papel == papel_residual:
            i.codigo_preferido = codigo_guia
    return fechados


def _compor_bruto_vale_retencao(prefixo: str, bruto: float, a_pagar: float, total: float) -> list[ItemDesejado]:
    """Contrato/empreita/diária: o custo é o BRUTO contratado; o vale abatido
    da parcela é adiantamento que volta, e a retenção do caixa no pagamento é
    obrigação com o funcionário."""
    bruto, a_pagar = _r2(bruto), _r2(a_pagar)
    vale = _r2(bruto - a_pagar) if bruto - a_pagar > 0.005 else 0.0
    retencao = _r2(a_pagar - total) if a_pagar - total > 0.005 else 0.0
    itens = [
        ItemDesejado(f"{prefixo}_bruto", bruto if vale else a_pagar),
        ItemDesejado(f"{prefixo}_vale", -vale),
        ItemDesejado(f"{prefixo}_retencao", -retencao),
    ]
    return _fechar(itens, total, f"{prefixo}_bruto")


def _movimento_do_caixa(session: Session, contas):
    from fazenda.models import CaixaMovimento, CaixaTimeMovimento

    ids = [c.id for c in contas if c.id is not None]
    if not ids:
        return None
    for modelo in (CaixaMovimento, CaixaTimeMovimento):
        mov = session.exec(select(modelo).where(modelo.lancamento_id.in_(ids))).first()
        if mov is not None:
            return mov
    return None


def _papel_do_caixa(session: Session, contas) -> str:
    mov = _movimento_do_caixa(session, contas)
    if mov is not None:
        return "caixa_retencao" if mov.tipo == "retencao" else "caixa_entrada"
    descricao = _norm(contas[0].descricao)
    return "caixa_retencao" if descricao.startswith("retencao") else "caixa_entrada"


def _papel_do_estorno(session: Session, contas, fazenda_id: int | None) -> str:
    """O estorno do caixa espelha a natureza do movimento original: estorno de
    retenção é obrigação; estorno de prêmio/comissão abate pessoal."""
    from fazenda.models import CaixaMovimento, CaixaTimeMovimento, ContaGerencial

    mov = _movimento_do_caixa(session, contas)
    if mov is not None and mov.estorna_id:
        modelo = CaixaMovimento if isinstance(mov, CaixaMovimento) else CaixaTimeMovimento
        original = session.get(modelo, mov.estorna_id)
        if original is not None:
            return "caixa_retencao" if original.tipo == "retencao" else "caixa_entrada"
    achado = re.match(r"^Estorno de (\S+)", contas[0].descricao or "")
    if achado:
        q = select(ContaGerencial).where(ContaGerencial.numero_lancamento == achado.group(1))
        if fazenda_id is not None:
            q = q.where(ContaGerencial.fazenda_id == fazenda_id)
        originais = list(session.exec(q).all())
        if originais:
            return _papel_do_caixa(session, originais)
    return "caixa_entrada"


def compor_itens(session: Session, contas: list, fazenda_id: int | None) -> tuple[str, list[ItemDesejado]] | None:
    """(origem identificada, itens desejados) para uma nota automática, ou
    None quando a nota não é de origem automática conhecida. `contas` = todas
    as parcelas da nota (mesmo número, mesma fazenda). Os itens somam o total
    das parcelas."""
    from fazenda.models import (
        DecimoTerceiro, Diaria, DiariaPagamento, EmpreitadaEtapa, EmpreitadaParcela, ContratoParcela,
        FolhaPagamento, GuiaFolhaEncargo, RescisaoFuncionario, ValeFuncionario,
    )

    if not contas:
        return None
    contas = sorted(contas, key=lambda c: (c.parcela_num or 0, c.id or 0))
    c0 = contas[0]
    numero = c0.numero_lancamento
    doc = c0.tipo_documento
    total = _r2(sum(c.valor_total or 0 for c in contas))
    if not numero or doc not in TIPOS_DOCUMENTO_AUTOMATICOS:
        return None

    if doc in DOC_GUIAS:
        guia = _primeiro(session, GuiaFolhaEncargo, "numero_lancamento", numero, fazenda_id)
        if guia is None:
            return None
        return "guia", _compor_guia(session, guia, c0, total)
    if c0.origem != "auto":
        return None

    if doc == DOC_FOLHA:
        folha = _primeiro(session, FolhaPagamento, "numero_lancamento_gerado", numero, fazenda_id)
        return "folha", (_compor_folha(session, folha, total) if folha else _uma_linha("folha_salario", total))
    if doc == DOC_FERIAS:
        return "ferias", _uma_linha("ferias_bruto", total)
    if doc == DOC_13:
        d = _primeiro(session, DecimoTerceiro, "numero_lancamento_gerado", numero, fazenda_id)
        if d is None:
            return "decimo", _uma_linha("decimo_bruto", total)
        itens = [ItemDesejado("decimo_bruto", _r2(d.valor_bruto)),
                 ItemDesejado("decimo_retidos", -_r2((d.valor_inss or 0) + (d.valor_ir or 0)))]
        return "decimo", _fechar(itens, total, "decimo_bruto")
    if doc == DOC_RESCISAO:
        r = _primeiro(session, RescisaoFuncionario, "numero_lancamento_gerado", numero, fazenda_id)
        if r is None:
            return "rescisao", _uma_linha("rescisao_verbas", total)
        itens = [ItemDesejado("rescisao_verbas", _r2(r.valor_bruto)),
                 ItemDesejado("rescisao_retidos", -_r2((r.valor_inss or 0) + (r.valor_ir or 0))),
                 ItemDesejado("rescisao_vale", -_r2(r.valor_vale_em_aberto))]
        return "rescisao", _fechar(itens, total, "rescisao_verbas")
    if doc == DOC_CONTRATO:
        p = _primeiro(session, ContratoParcela, "numero_lancamento_gerado", numero, fazenda_id)
        if p is None:
            return "contrato", _uma_linha("contrato_bruto", total)
        return "contrato", _compor_bruto_vale_retencao("contrato", p.valor_contratado or p.valor, p.valor, total)
    if doc == DOC_EMPREITA:
        p = (_primeiro(session, EmpreitadaParcela, "numero_lancamento_gerado", numero, fazenda_id)
             or _primeiro(session, EmpreitadaEtapa, "numero_lancamento_gerado", numero, fazenda_id))
        if p is None:
            return "empreita", _uma_linha("empreita_bruto", total)
        bruto = getattr(p, "valor_contratado", None) or p.valor
        return "empreita", _compor_bruto_vale_retencao("empreita", bruto, p.valor, total)
    if doc == DOC_DIARIA:
        p = _primeiro(session, DiariaPagamento, "numero_lancamento_gerado", numero, fazenda_id)
        if p is None:
            return "diaria", _uma_linha("diaria_bruto", total)
        return "diaria", _compor_bruto_vale_retencao("diaria", p.valor, p.valor, total)
    if doc == DOC_ACERTO_DIARIA:
        _ = _primeiro(session, Diaria, "numero_lancamento_gerado", numero, fazenda_id)
        return "diaria", _uma_linha("diaria_bruto", total)
    if doc in DOC_VALES:
        return "vale", _uma_linha("vale", total)
    if doc == DOC_RECIBO:
        if _primeiro(session, ValeFuncionario, "numero_lancamento_gerado", numero, fazenda_id) is not None:
            return "vale_assumido", _uma_linha("vale_assumido", total)
        if c0.tipo == "receita" and _norm(c0.descricao).startswith("devolucao de vale"):
            return "vale_devolucao", _uma_linha("vale_devolucao", total)
        return None
    if doc in DOCS_CAIXA:
        return "caixa", _uma_linha(_papel_do_caixa(session, contas), total)
    if doc in DOCS_ESTORNO_CAIXA:
        return "caixa_estorno", _uma_linha(_papel_do_estorno(session, contas, fazenda_id), total)
    return None


# ---------------------------------------------------------------------------
# Escrita dos itens
# ---------------------------------------------------------------------------
@dataclass
class ItemFinal:
    papel: str
    valor: float
    codigo: str | None
    nome: str | None
    natureza: str | None
    produto: str


def resolver_itens(desejados: list[ItemDesejado], cfg: Configuracao) -> list[ItemFinal]:
    finais = []
    for d in desejados:
        papel = PAPEIS[d.papel]
        conta = cfg.conta(papel.origem)
        codigo, nome = conta.codigo, conta.nome
        if not codigo and d.codigo_preferido:
            codigo, nome = d.codigo_preferido, cfg.nomes_plano.get(d.codigo_preferido)
        elif not codigo and papel.codigo_preferido and papel.codigo_preferido in cfg.contas_sistema:
            # Retenção e vale: a conta do sistema, só se existir no plano desta
            # fazenda e a origem não tiver conta configurada à mão.
            codigo, nome = papel.codigo_preferido, cfg.contas_sistema[papel.codigo_preferido]
        natureza = conta.natureza if conta.natureza in NATUREZAS else papel.natureza
        finais.append(ItemFinal(d.papel, _r2(d.valor), codigo, nome or papel.rotulo, natureza, papel.rotulo))
    return finais


def _itens_da_nota(session: Session, numero: str, fazenda_id: int | None) -> list:
    from fazenda.models import LancamentoItem

    q = select(LancamentoItem).where(LancamentoItem.numero_lancamento == numero)
    q = q.where(LancamentoItem.fazenda_id == fazenda_id) if fazenda_id is not None else q.where(LancamentoItem.fazenda_id.is_(None))
    return list(session.exec(q).all())


def _contas_da_nota(session: Session, numero: str, fazenda_id: int | None) -> list:
    from fazenda.models import ContaGerencial

    q = select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)
    q = q.where(ContaGerencial.fazenda_id == fazenda_id) if fazenda_id is not None else q.where(ContaGerencial.fazenda_id.is_(None))
    return list(session.exec(q).all())


def novo_item(conta, final: ItemFinal):
    from fazenda.models import LancamentoItem

    return LancamentoItem(
        fazenda_id=conta.fazenda_id, numero_lancamento=conta.numero_lancamento, tipo=conta.tipo,
        data_competencia=conta.data_competencia, codigo_conta_gerencial=final.codigo,
        nome_conta_gerencial=final.nome, produto=final.produto, tipo_item="servico",
        valor_total=final.valor, natureza_fin=final.natureza, gerado_por=final.papel,
    )


def escrever_itens(session: Session, contas: list, existentes: list, finais: list[ItemFinal], *, nova: bool) -> bool:
    """Deixa os itens gerados da nota iguais a `finais`, reaproveitando a linha
    de cada papel (ids estáveis). Preserva a conta/natureza que já estavam
    no item (o usuário pode ter trocado só a conta pelo Financeiro). Devolve
    True se gravou algo."""
    contas = sorted(contas, key=lambda c: (c.parcela_num or 0, c.id or 0))
    c0 = contas[0]
    por_papel: dict[str, list] = {}
    for it in existentes:
        por_papel.setdefault(it.gerado_por, []).append(it)
    mudou = False
    for final in finais:
        lista = por_papel.get(final.papel) or []
        it = lista.pop(0) if lista else None
        if it is None:
            session.add(novo_item(c0, final))
            mudou = True
            continue
        codigo = it.codigo_conta_gerencial or final.codigo
        nome = it.nome_conta_gerencial if it.codigo_conta_gerencial else final.nome
        natureza = it.natureza_fin or final.natureza
        alvo = {"valor_total": final.valor, "codigo_conta_gerencial": codigo, "nome_conta_gerencial": nome,
                "natureza_fin": natureza, "tipo": c0.tipo, "data_competencia": c0.data_competencia,
                "produto": final.produto}
        item_mudou = False
        for campo, valor in alvo.items():
            if getattr(it, campo) != valor:
                setattr(it, campo, valor)
                item_mudou = True
        if item_mudou:
            session.add(it)
            mudou = True
    for sobras in por_papel.values():
        for it in sobras:
            session.delete(it)
            mudou = True
    if nova and finais and finais[0].codigo:
        for c in contas:
            if c.codigo_conta is None and finais[0].valor > 0:
                c.codigo_conta = finais[0].codigo
                session.add(c)
                mudou = True
    return mudou


def sincronizar_nota(session: Session, numero: str, fazenda_id: int | None, *, nova: bool,
                     cfg: Configuracao | None = None) -> str:
    """Refaz os itens gerados de UMA nota (todas as parcelas do número). Não
    checa a flag (quem chama checa). `nova=False` só refaz nota que JÁ tem
    itens gerados — nota antiga sem itens é assunto do backfill. Devolve o
    que aconteceu (para teste e log)."""
    contas = _contas_da_nota(session, numero, fazenda_id)
    existentes = _itens_da_nota(session, numero, fazenda_id)
    gerados = [it for it in existentes if it.gerado_por]
    if not contas:
        for it in gerados:
            session.delete(it)
        return "removidos" if gerados else "sem_nota"
    if any(not it.gerado_por for it in existentes):
        return "itens_do_usuario"
    if not gerados and not nova:
        return "sem_itens_gerados"
    composicao = compor_itens(session, contas, fazenda_id)
    if composicao is None:
        return "nao_automatica"
    _origem, desejados = composicao
    finais = resolver_itens(desejados, cfg or carregar_configuracao(session, fazenda_id))
    return "gravado" if escrever_itens(session, contas, gerados, finais, nova=nova) else "igual"


def lancar_automatico(session: Session, conta) -> str:
    """Helper explícito (o mesmo que os listeners usam): dá itens e conta à
    nota automática `conta` agora, se a fazenda tem a flag ligada. Útil para
    quem cria uma nota fora de uma rota (script, teste) e quer o resultado
    antes do commit."""
    from fazenda.rules.parametros import regras_v2_ativas

    if conta.id is None:
        session.flush()
    if not regras_v2_ativas(session, conta.fazenda_id):
        return "flag_desligada"
    return sincronizar_nota(session, conta.numero_lancamento, conta.fazenda_id, nova=True)


# ---------------------------------------------------------------------------
# Pendências ("Configure as contas automáticas")
# ---------------------------------------------------------------------------
def rotulo_sem_conta(papel: str) -> str:
    """Pseudocódigo de um item gerado sem conta configurada. Item fora da DRE
    (obrigação/adiantamento) só ganha nome; item de custo vira pendência."""
    info = PAPEIS.get(papel)
    if info is None:
        return "(sem conta)"
    if info.natureza and info.natureza != OPERACIONAL:
        return f"({info.rotulo.replace('(−) ', '')})"
    origem = ORIGENS.get(info.origem or "")
    return f"(sem conta: {origem.rotulo if origem else info.rotulo})"


def origem_do_papel(papel: str | None) -> str | None:
    info = PAPEIS.get(papel or "")
    return info.origem if info else None


# ---------------------------------------------------------------------------
# Listeners de sessão — o ponto único que mantém os itens
# ---------------------------------------------------------------------------
_CHAVE_PENDENTES = "_lancamento_automatico_pendentes"
_CHAVE_REENTRADA = "_lancamento_automatico_rodando"


def _historico_mudou(obj, *campos: str) -> bool:
    estado = sa_inspect(obj)
    return any(estado.attrs[c].history.has_changes() for c in campos if c in estado.attrs)


def _marcar(pendentes: dict, numero: str | None, fazenda_id: int | None, nova: bool, apagada: bool = False) -> None:
    if not numero:
        return
    chave = (numero, fazenda_id)
    nova_antes, apagada_antes = pendentes.get(chave, (False, False))
    pendentes[chave] = (nova_antes or nova, apagada_antes or apagada)


def _coletar(session: Session, flush_context) -> None:
    """after_flush: só COLETA (as listas new/dirty/deleted ainda têm o estado
    de antes do flush). Nada de consulta aqui."""
    if session.info.get(_CHAVE_REENTRADA):
        return
    from fazenda.models import (
        CaixaMovimento, CaixaTimeMovimento, ContaGerencial, ContratoParcela, DecimoTerceiro, DiariaPagamento,
        EmpreitadaEtapa, EmpreitadaParcela, FolhaPagamento, FolhaRubrica, GuiaFolhaEncargo, RescisaoFuncionario,
        ValeFuncionario,
    )

    pendentes: dict = session.info.setdefault(_CHAVE_PENDENTES, {})
    competencias: set = session.info.setdefault(_CHAVE_PENDENTES + "_comp", set())
    folhas_por_id: set = session.info.setdefault(_CHAVE_PENDENTES + "_folhas", set())
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        if isinstance(obj, ContaGerencial):
            doc_auto = obj.tipo_documento in TIPOS_DOCUMENTO_AUTOMATICOS
            if obj in session.deleted:
                _marcar(pendentes, obj.numero_lancamento, obj.fazenda_id, False, apagada=True)
            elif obj in session.new:
                if doc_auto:
                    _marcar(pendentes, obj.numero_lancamento, obj.fazenda_id, True)
            elif doc_auto and _historico_mudou(obj, "valor_total", "tipo_documento", "numero_lancamento"):
                _marcar(pendentes, obj.numero_lancamento, obj.fazenda_id, False)
        elif isinstance(obj, (FolhaPagamento, DecimoTerceiro, RescisaoFuncionario, ContratoParcela,
                              EmpreitadaParcela, EmpreitadaEtapa, DiariaPagamento, ValeFuncionario)):
            _marcar(pendentes, getattr(obj, "numero_lancamento_gerado", None), obj.fazenda_id, False)
            if isinstance(obj, FolhaPagamento) and obj.competencia:
                competencias.add((obj.competencia, obj.fazenda_id))
        elif isinstance(obj, GuiaFolhaEncargo):
            _marcar(pendentes, obj.numero_lancamento, obj.fazenda_id, False)
        elif isinstance(obj, FolhaRubrica) and obj.folha_id:
            folhas_por_id.add(obj.folha_id)
        elif isinstance(obj, (CaixaMovimento, CaixaTimeMovimento)):
            _marcar(pendentes, getattr(obj, "numero_lancamento", None), obj.fazenda_id, False)


def _processar(session: Session, flush_context) -> None:
    """after_flush_postexec: refaz os itens das notas coletadas. O que é
    gravado aqui sai no próximo flush do mesmo commit (o `commit()` do
    SQLAlchemy repete o flush enquanto houver mudança)."""
    if session.info.get(_CHAVE_REENTRADA):
        return
    pendentes: dict = session.info.pop(_CHAVE_PENDENTES, {}) or {}
    competencias: set = session.info.pop(_CHAVE_PENDENTES + "_comp", set()) or set()
    folhas_por_id: set = session.info.pop(_CHAVE_PENDENTES + "_folhas", set()) or set()
    if not (pendentes or competencias or folhas_por_id):
        return
    from fazenda.models import FolhaPagamento, GuiaFolhaEncargo
    from fazenda.rules.parametros import regras_v2_ativas

    session.info[_CHAVE_REENTRADA] = True
    try:
        with session.no_autoflush:
            for folha_id in folhas_por_id:
                folha = session.get(FolhaPagamento, folha_id)
                if folha is not None:
                    _marcar(pendentes, folha.numero_lancamento_gerado, folha.fazenda_id, False)
            for competencia, fazenda_id in competencias:
                q = select(GuiaFolhaEncargo).where(GuiaFolhaEncargo.competencia == competencia)
                if fazenda_id is not None:
                    q = q.where(GuiaFolhaEncargo.fazenda_id == fazenda_id)
                for guia in session.exec(q).all():
                    _marcar(pendentes, guia.numero_lancamento, guia.fazenda_id, False)
            flags: dict = {}
            configs: dict = {}
            for (numero, fazenda_id), (nova, apagada) in pendentes.items():
                try:
                    if fazenda_id not in flags:
                        flags[fazenda_id] = regras_v2_ativas(session, fazenda_id)
                    if not flags[fazenda_id]:
                        # Flag desligada: só a limpeza (nota apagada não pode
                        # deixar item gerado pendurado no número reaproveitável).
                        if apagada and not _contas_da_nota(session, numero, fazenda_id):
                            for it in _itens_da_nota(session, numero, fazenda_id):
                                if it.gerado_por:
                                    session.delete(it)
                        continue
                    if fazenda_id not in configs:
                        configs[fazenda_id] = carregar_configuracao(session, fazenda_id)
                    sincronizar_nota(session, numero, fazenda_id, nova=nova, cfg=configs[fazenda_id])
                except Exception:  # pragma: no cover - defensivo: nunca derruba a rota de RH
                    logger.exception("lancamento_automatico: falha ao sincronizar itens de %s", numero)
    finally:
        session.info.pop(_CHAVE_REENTRADA, None)


def _limpar(session: Session, *args) -> None:
    for chave in (_CHAVE_PENDENTES, _CHAVE_PENDENTES + "_comp", _CHAVE_PENDENTES + "_folhas"):
        session.info.pop(chave, None)


_REGISTRADO = False


def registrar_listeners() -> None:
    global _REGISTRADO
    if _REGISTRADO:
        return
    event.listen(Session, "after_flush", _coletar)
    event.listen(Session, "after_flush_postexec", _processar)
    event.listen(Session, "after_rollback", _limpar)
    _REGISTRADO = True


registrar_listeners()

