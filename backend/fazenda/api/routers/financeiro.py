"""
Router financeiro — DRE, fluxo de caixa, KPIs e lançamentos financeiros
(contas a pagar/a receber, com parcelamento, conta bancária e importação de XML).
"""
from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session, select

from fazenda.auth import exigir_admin, exigir_nao_consultor, get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fastapi.responses import Response
from fazenda.models import (
    CentroCusto, ClassificacaoLancamento, ContaCorrente, ContaGerencial, EntregaLeiteMensal, Estoque, ExameDefinicao, ExameResultado, FormaPagamentoCadastro, Fornecedor,
    FornecedorClienteApelido,
    LancamentoAnexo, LancamentoItem, LancamentoRecorrente, ManutencaoPatrimonio, MovimentoEstoque, Patrimonio, Pessoa, PlanoContaGerencial, Sanidade,
    SeedFlag, Servico, TipoDocumento, TransferenciaContas, Usuario, ValeAvulso, ValeFuncionario,
)
from fazenda.rules import estoque_baixa
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usuarios
from fazenda.rules.vale_item import ajuste_vale_por_conta, eh_item_de_vale, sem_itens_de_vale
from fazenda.rules.email import enviar_email
from fazenda.rules.centro_custo import CENTROS_CANONICOS, MAPA_CENTRO_CUSTO, mapear_centro_custo, valor_gerencial_por_centro_custo
from fazenda.rules.leitura_documento import MIME_ACEITOS, ler_documento
from fazenda.rules.nfe_xml import parse_nfe_xml
from fazenda.rules.casamento_cadastro import normalizar
from fazenda.rules.sugestao_documento import resolver_apelido_fornecedor, sugestoes_cadastro
from fazenda.rules.rmca import calcular_custo_fisico, calcular_rmca_gerencial
from fazenda.rules.custo_leite import calcular_custo_por_litro, litros_leite_no_periodo
from fazenda.rules.patrimonio import calcular_depreciacao, proxima_atualizacao_valor_mercado, somar_meses, status_manutencao
from fazenda.rules.parametros import meta_rmca, patrimonio_atualizacao_valor_mercado_meses
from fazenda.rules.supabase_storage import baixar_arquivo, enviar_arquivo, excluir_arquivo, nome_seguro_storage
from fazenda.config import settings

router = APIRouter(prefix="/financeiro", tags=["financeiro"])

# "Comprovante" e "Orçamento" (pra planejamento ou pedido) entraram junto com
# a Central de Documentos — antes só existiam via "Boleto"/"Ordem de
# serviço" (que já estavam em SEED_TIPOS_DOCUMENTO) e "Recibo" (parecido com
# comprovante, mas não o mesmo rótulo pedido).
TIPOS_DOCUMENTO = ["Nota fiscal", "Recibo", "Comprovante", "Folha de pagamento", "Fatura", "Orçamento", "Contrato"]

# Categorias do Arquivo fiscal-contábil (fazenda/api/routers/documentos.py) —
# documentos sem contrapartida em lançamento (CCIR, IRPF/IRPJ, inscrição
# estadual, matrículas, contratos de trabalho/prestação de serviço), somadas
# às já usadas em TIPOS_DOCUMENTO/SEED_TIPOS_DOCUMENTO acima.
CATEGORIAS_DOCUMENTO_ARQUIVO = [
    "CCIR", "IRPF", "IRPJ", "Inscrição estadual", "Matrícula",
    "Contrato de trabalho", "Contrato de prestação de serviço",
]

# Seed inicial — as duas contas correntes da fazenda no Banco do Brasil (antes
# uma lista fixa em Python; agora cadastráveis em Configurações > Parâmetros
# financeiros). Ver seed_parametros_financeiros, chamada uma vez no startup.
SEED_CONTAS_CORRENTES = [
    {"banco": "Banco do Brasil", "agencia": "3775-3", "numero_conta": "3.615-3"},
    {"banco": "Banco do Brasil", "agencia": "4057-6", "numero_conta": "3.615-3"},
]


def rotulo_conta_corrente(c: ContaCorrente) -> str:
    return f"{c.banco} · Agência {c.agencia} · Conta corrente {c.numero_conta}"


def calcular_saldos_contas_correntes(
    session: Session, contas: list[ContaCorrente], fazenda_id: int | None,
) -> dict[int, float]:
    """
    Saldo "entradas − saídas" de cada conta corrente — nunca persistido,
    sempre calculado (mesmo padrão do resto do sistema, ex. saldo de estoque
    em fazenda/rules/estoque.py), a partir de duas fontes:

    1. ContaGerencial já pago (valor_pago) cujo `conta_bancaria` (string
       livre, preenchida na baixa — ver pagar_lancamento/criar_lancamento)
       bate com o rótulo da conta: despesa subtrai, receita soma.
    2. TransferenciaContas onde a conta é origem (subtrai) ou destino (soma).
    """
    if not contas:
        return {}
    saldos: dict[int, float] = {c.id: 0.0 for c in contas}
    rotulo_por_id = {c.id: rotulo_conta_corrente(c) for c in contas}
    ids_por_rotulo: dict[str, list[int]] = {}
    for cid, rotulo in rotulo_por_id.items():
        ids_por_rotulo.setdefault(rotulo, []).append(cid)

    query = select(ContaGerencial.conta_bancaria, ContaGerencial.tipo, ContaGerencial.valor_pago).where(
        ContaGerencial.conta_bancaria.in_(list(ids_por_rotulo.keys())),
        ContaGerencial.data_pagamento != None,  # noqa: E711
    )
    if fazenda_id is not None:
        query = query.where(ContaGerencial.fazenda_id == fazenda_id)
    for rotulo, tipo, valor_pago in session.exec(query).all():
        if not valor_pago:
            continue
        sinal = 1.0 if tipo == "receita" else -1.0
        for cid in ids_por_rotulo.get(rotulo, []):
            saldos[cid] += sinal * valor_pago

    query_transf = select(TransferenciaContas)
    if fazenda_id is not None:
        query_transf = query_transf.where(TransferenciaContas.fazenda_id == fazenda_id)
    for t in session.exec(query_transf).all():
        if t.conta_origem_id in saldos:
            saldos[t.conta_origem_id] -= t.valor
        if t.conta_destino_id in saldos:
            saldos[t.conta_destino_id] += t.valor

    return {cid: round(v, 2) for cid, v in saldos.items()}


def seed_parametros_financeiros(session: Session) -> None:
    """Cria as contas correntes padrão se a tabela ainda estiver vazia (idempotente)."""
    if not session.exec(select(ContaCorrente)).first():
        for dados in SEED_CONTAS_CORRENTES:
            session.add(ContaCorrente(**dados))
        session.commit()


def normalizar_plano_contas(session: Session) -> None:
    """Normaliza o plano de contas gerenciais conforme o padrão pedido pelo
    usuário — roda UMA única vez (guardada por SeedFlag), para nunca
    sobrescrever ajustes manuais feitos depois em Configurações:

    - Toda conta gerencial fica ATIVA (o plano importado marcava os grupos/
      cabeçalhos como inativos; agora a seleção é feita só nas contas-folha).
    - Todo item de "3.01.01 - Alimentação do rebanho" já entra marcado como
      custo de alimentação para o indicador RMCA.
    """
    chave = "plano_contas_normalizado_v1"
    if session.get(SeedFlag, chave):
        return
    contas = session.exec(select(PlanoContaGerencial)).all()
    if contas:  # nada a fazer num banco ainda sem plano importado
        for c in contas:
            if not c.ativa:
                c.ativa = True
                session.add(c)
            if c.codigo.startswith("3.01.01") and c.rmca_custo_alimentacao is None:
                c.rmca_custo_alimentacao = True
                session.add(c)
    session.add(SeedFlag(chave=chave))
    session.commit()


# Heurística de classificação padrão da natureza (serviço/produto/ambos) de
# cada conta gerencial, por palavra-chave no nome — roda a CADA start (não
# precisa de SeedFlag: só preenche onde `natureza` ainda está vazio, então
# nunca sobrescreve uma classificação que o usuário já ajustou manualmente
# em Configurações > Parâmetros financeiros > Conta gerencial).
_PALAVRAS_PRODUTO = (
    "racao", "alimento", "concentrado", "mineral", "medicamento", "vacina", "farmaco",
    "semen", "insumo", "combustivel", "oleo", "peca", "material", "equipamento",
    "ferramenta", "animal", "fertilizante", "semente", "embalagem", "uniforme", "epi",
    "graxa", "pneu", "bateria", "lubrificante", "ensacado", "suplemento", "silagem",
    "feno", "sal mineral", "produto",
)
_PALAVRAS_SERVICO = (
    "salario", "honorario", "comissao", "mao de obra", "frete", "transporte",
    "consultoria", "assessoria", "contabilidade", "advocacia", "exame", "veterinario",
    "manutencao", "aluguel", "energia", "agua", "telefone", "internet", "seguro",
    "imposto", "taxa", "juros", "tarifa", "bancaria", "bancario", "corretagem",
    "servico", "mensalidade", "assinatura", "publicidade", "marketing", "inseminacao",
    "diaria", "deslocamento", "hospedagem", "cartorio", "auditoria",
)


def _sem_acento_nat(txt: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn")


def classificar_natureza_plano_contas(session: Session) -> None:
    contas = session.exec(select(PlanoContaGerencial)).all()
    for c in contas:
        if c.natureza is not None:
            continue
        nome = _sem_acento_nat((c.nome or "").lower())
        eh_produto = any(p in nome for p in _PALAVRAS_PRODUTO)
        eh_servico = any(p in nome for p in _PALAVRAS_SERVICO)
        if eh_produto and not eh_servico:
            c.natureza = "produto"
        elif eh_servico and not eh_produto:
            c.natureza = "servico"
        else:
            # Nem bateu com nenhuma palavra-chave, nem bateu com as duas —
            # "ambos" é o padrão mais seguro (nunca bloqueia um lançamento
            # legítimo); o usuário pode restringir manualmente depois.
            c.natureza = "ambos"
        session.add(c)
    if contas:
        session.commit()


def normalizar_centros_custo(session: Session) -> None:
    """Padroniza os centros de custo (uma vez, guardado por SeedFlag):
    PL → Pecuária Leiteira, C|26 → Financiamento 2026, ARR → Arrendamento.
    Renomeia nos lançamentos e no padrão do estoque, garante os três nomes
    canônicos no cadastro e remove os cadastros com as siglas antigas — para
    existir só o nome legível, selecionável em todos os lugares.
    """
    chave = "centros_custo_canonicos_v1"
    if session.get(SeedFlag, chave):
        return
    for c in session.exec(select(ContaGerencial)).all():
        novo = mapear_centro_custo(c.centro_custo)
        if novo != c.centro_custo:
            c.centro_custo = novo
            session.add(c)
    for e in session.exec(select(Estoque)).all():
        novo = mapear_centro_custo(e.centro_custo_padrao)
        if novo != e.centro_custo_padrao:
            e.centro_custo_padrao = novo
            session.add(e)
    existentes = {cc.nome.strip().upper(): cc for cc in session.exec(select(CentroCusto)).all()}
    for sigla, canonico in MAPA_CENTRO_CUSTO.items():
        antigo = existentes.get(sigla)
        if antigo:
            session.delete(antigo)
        if canonico.strip().upper() not in existentes:
            novo = CentroCusto(nome=canonico, ativo=True)
            session.add(novo)
            existentes[canonico.strip().upper()] = novo
    session.add(SeedFlag(chave=chave))
    session.commit()


def seed_centro_custo_agricultura(session: Session) -> None:
    """Garante o centro de custo "Agricultura" cadastrado (Opção A do plano
    de custo agrícola — ver models.Safra / relatorio_custo_safra.py).
    Idempotente por existência (não por SeedFlag), para nunca reaparecer se o
    usuário decidir inativá-lo depois em Configurações > Parâmetros financeiros."""
    if not session.exec(select(CentroCusto).where(CentroCusto.nome == "Agricultura")).first():
        session.add(CentroCusto(nome="Agricultura", ativo=True))
        session.commit()


class ParcelaIn(BaseModel):
    data_vencimento: date
    valor: float
    # Linha digitável/número do boleto DESTA parcela — opcional, preenchido
    # manualmente ou extraído automaticamente ao importar o boleto.
    numero_boleto: Optional[str] = None
    # Baixa já no nascimento da parcela — opcional; uma parcela sem esses
    # campos nasce em aberto (contas a pagar/receber), como hoje.
    data_pagamento: Optional[date] = None
    valor_pago: Optional[float] = None
    conta_bancaria: Optional[str] = None
    forma_pagamento: Optional[str] = None
    numero_documento_pagamento: Optional[str] = None


class ValeItemNovoIn(BaseModel):
    """Mesmos campos de ValeItemIn (fazenda/api/routers/cadastro/rh_vale_item.py)
    — declarado aqui (não importado) para financeiro.py não importar `cadastro`
    no topo do módulo (ciclo de import: rh_folha.py/rh_contratos.py já
    importam de financeiro.py — ver §0.8)."""
    pessoa_id: int
    modo: str  # "folha" | "avulso"
    parcelas: int = 1
    competencia_inicio: Optional[str] = None
    origem_tipo: Optional[str] = None
    origem_id: Optional[int] = None
    observacao: Optional[str] = None
    confirmar: bool = False


class ItemIn(BaseModel):
    codigo_conta_gerencial: Optional[str] = None
    nome_conta_gerencial: Optional[str] = None
    # Override do centro de custo da nota (dados.centro_custo, abaixo) só
    # para este item — None (a maioria) usa o centro de custo da nota inteira.
    centro_custo: Optional[str] = None
    produto: str
    tipo_item: Optional[str] = None  # "produto" | "servico"
    descricao: Optional[str] = None
    quantidade: Optional[float] = None
    valor_unitario: Optional[float] = None
    valor_total: float
    # Este item é gasto pessoal de um funcionário/empreiteiro/diarista — ao
    # salvar, gera o vale de verdade e o item sai dos relatórios gerenciais.
    # None (padrão) = item normal da fazenda.
    vale: Optional[ValeItemNovoIn] = None


class PatrimonioIn(BaseModel):
    tipo: Optional[str] = None
    nome: str
    numero: Optional[str] = None
    atividade_cultura: Optional[str] = None
    data_imobilizacao: Optional[date] = None
    quantidade: Optional[float] = None
    unidade: Optional[str] = None
    valor_total: Optional[float] = None
    # depreciavel=True (padrão): informe metodo_depreciacao/vida_util/valor_residual.
    # depreciavel=False (ex.: terra): informe valor_mercado_atual no lugar de
    # valor_total (se vazio, valor_total é usado como valor de mercado inicial)
    # e, opcionalmente, a frequência de atualização (None = usa o padrão do
    # sistema, 0 = nunca).
    depreciavel: bool = True
    metodo_depreciacao: Optional[str] = None
    vida_util: Optional[str] = None
    valor_residual: Optional[float] = None
    valor_mercado_atual: Optional[float] = None
    atualizacao_valor_mercado_frequencia_meses: Optional[int] = None


class LancamentoIn(BaseModel):
    tipo: str  # "receita" | "despesa"
    itens: list[ItemIn]  # um ou mais produtos/serviços da mesma nota
    centro_custo: Optional[str] = None
    classificacao: Optional[str] = None
    fornecedor_cliente: Optional[str] = None
    responsavel: Optional[str] = None
    tipo_documento: Optional[str] = None
    numero_documento: Optional[str] = None
    # Item de consulta À PARTE do número do documento — nº da ordem de
    # serviço (OS) ou do orçamento que originou a compra, quando houver.
    numero_os_orcamento: Optional[str] = None
    data_emissao: Optional[date] = None
    data_vencimento: Optional[date] = None  # vencimento do lançamento não-parcelado (vai p/ contas a pagar e agenda)
    data_competencia: Optional[date] = None
    data_prevista_entrada: Optional[date] = None
    data_pedido: Optional[date] = None
    entregue: Optional[bool] = None
    desconto: float = 0
    acrescimo: float = 0
    parcelas: list[ParcelaIn] = []
    # Só para o lançamento SEM parcelamento (parcela única) — nas parcelas,
    # cada uma tem o seu próprio ParcelaIn.numero_boleto.
    numero_boleto: Optional[str] = None
    # Preenchidos só quando o lançamento já nasce pago/recebido (sem parcelamento).
    data_pagamento: Optional[date] = None
    valor_pago: Optional[float] = None
    conta_bancaria: Optional[str] = None
    numero_documento_pagamento: Optional[str] = None
    forma_pagamento: Optional[str] = None
    # Vincula esta nota fiscal/recibo a um Pedido (Pedidos > módulo próprio) —
    # é só a partir deste vínculo que o pedido passa a refletir em Financeiro.
    pedido_id: Optional[int] = None
    # Preenchido = esta compra é a aquisição de um item de patrimônio novo —
    # cria o registro em Patrimônio e já vincula (patrimonio_id) ao lançamento,
    # numa única operação (ver Configurações > Cadastro > Itens de estoque,
    # flag "Patrimônio", e Controle Financeiro > Patrimônio > "+ Novo
    # patrimônio" > "É uma compra agora?"). None = lançamento comum, sem vínculo.
    criar_patrimonio: Optional[PatrimonioIn] = None


FORMAS_PAGAMENTO = ["pix", "transferencia", "boleto", "credito", "debito"]


class ParcelaDiferencaIn(BaseModel):
    data_vencimento: date
    valor: float


class PagamentoIn(BaseModel):
    data_pagamento: date
    valor_pago: float
    conta_bancaria: Optional[str] = None
    numero_documento_pagamento: Optional[str] = None
    forma_pagamento: Optional[str] = None
    data_vencimento_cartao: Optional[date] = None
    # Diferença entre valor_pago e o valor_total: por padrão vira
    # desconto_acrescimo, perdoada/cobrada de uma vez (comportamento de
    # sempre, quando este campo vem vazio). Se o usuário preferir não
    # resolver a diferença agora, `parcelas_diferenca` a divide em novas
    # parcelas do MESMO numero_lancamento (mesmo padrão de criar_lancamento)
    # — a baixa desta parcela grava desconto_acrescimo=0 (a diferença toda
    # vai para as novas parcelas, nada é perdoado nesta).
    parcelas_diferenca: Optional[list[ParcelaDiferencaIn]] = None


class BaixaLoteIn(BaseModel):
    lancamento_ids: list[int]
    data_pagamento: date
    conta_bancaria: Optional[str] = None
    forma_pagamento: Optional[str] = None
    data_vencimento_cartao: Optional[date] = None
    numero_documento_pagamento: Optional[str] = None


class BaixaLoteItemIn(BaseModel):
    """Pagamento de UMA nota dentro da baixa em lote — cada uma com sua própria
    data, valor, conta e forma."""
    lancamento_id: int
    data_pagamento: date
    valor_pago: float
    conta_bancaria: Optional[str] = None
    forma_pagamento: Optional[str] = None
    data_vencimento_cartao: Optional[date] = None
    numero_documento_pagamento: Optional[str] = None


class BaixaLoteDetalhadaIn(BaseModel):
    itens: list[BaixaLoteItemIn]


class XmlIn(BaseModel):
    xml: str


def _proximo_numero_lancamento(session: Session, ano: int) -> str:
    prefixo = f"LC-{ano}-"
    # Trava (advisory lock, só em Postgres — produção) presa à transação
    # atual: sem ela, duas requisições quase simultâneas liam o mesmo "maior
    # número existente" e geravam o MESMO numero_lancamento para notas
    # diferentes — a partir daí, excluir/estornar/detectar duplicado (que
    # agrupam por numero_lancamento) passavam a tratar as duas notas como se
    # fossem parcelas uma da outra. `pg_advisory_xact_lock` libera sozinho no
    # commit/rollback da transação que chamou esta função — não precisa de
    # unlock manual. SQLite (testes/dev local) não tem esse lock e os testes
    # não têm concorrência real entre conexões, então o no-op é seguro ali.
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:chave))"), {"chave": prefixo})
    existentes = session.exec(
        select(ContaGerencial.numero_lancamento).where(ContaGerencial.numero_lancamento.like(f"{prefixo}%"))
    ).all()
    maior = 0
    for n in existentes:
        if n and n.startswith(prefixo):
            try:
                maior = max(maior, int(n[len(prefixo):]))
            except ValueError:
                continue
    return f"{prefixo}{maior + 1:05d}"


@router.get("/dre")
def dre(
    data_inicio: date = Query(..., description="Data inicial (competência)"),
    data_fim: date = Query(..., description="Data final (competência)"),
    centro_custo: Optional[str] = Query(None),
    regime: str = Query("competencia", description="'competencia' ou 'caixa'"),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Retorna DRE (Demonstrativo de Resultado) por regime de competência ou caixa.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    campo_data = "data_competencia" if regime == "competencia" else "data_pagamento"

    query = select(ContaGerencial)
    if fazenda_id is not None:
        query = query.where(ContaGerencial.fazenda_id == fazenda_id)
    contas = session.exec(query).all()

    periodo = []
    for c in contas:
        data_ref = c.data_competencia if regime == "competencia" else c.data_pagamento
        if data_ref and data_inicio <= data_ref <= data_fim:
            periodo.append(c)

    # Vale de funcionário/empreiteiro lançado a partir de um item desta nota
    # não é despesa da fazenda (é adiantamento a receber da pessoa) — vale
    # nos DOIS regimes (competência e caixa), porque o DRE é resultado
    # gerencial e vale nunca é despesa em regime nenhum (ver rules/vale_item.py).
    ajustes = ajuste_vale_por_conta(session, periodo, fazenda_id)
    # Quando um item da nota tem centro de custo próprio (override, ver
    # Financeiro > lançamento), o valor daquela conta/parcela é rateado entre
    # os centros de custo dos itens em vez de cair inteiro no centro de custo
    # da nota — ver valor_gerencial_por_centro_custo.
    valores = valor_gerencial_por_centro_custo(session, periodo, centro_custo, ajustes)
    filtradas = periodo if centro_custo is None else [c for c in periodo if valores.get(c.id, 0.0) != 0]

    receitas = sum(valores.get(c.id, 0.0) for c in filtradas if c.tipo == "receita")
    despesas = sum(valores.get(c.id, 0.0) for c in filtradas if c.tipo == "despesa")
    resultado = receitas - despesas

    # Agrupa por código de conta
    por_conta: dict[str, dict] = {}
    for c in filtradas:
        codigo = c.codigo_conta or "Sem classificação"
        nivel1 = codigo.split(".")[0] if "." in codigo else codigo
        if nivel1 not in por_conta:
            por_conta[nivel1] = {"descricao": c.descricao or "", "receitas": 0.0, "despesas": 0.0}
        if c.tipo == "receita":
            por_conta[nivel1]["receitas"] += valores.get(c.id, 0.0)
        else:
            por_conta[nivel1]["despesas"] += valores.get(c.id, 0.0)

    return {
        "periodo": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()},
        "regime": regime,
        "centro_custo": centro_custo,
        "receitas_total": round(receitas, 2),
        "despesas_total": round(despesas, 2),
        "resultado": round(resultado, 2),
        "por_conta": por_conta,
    }


@router.get("/lancamentos")
def listar_lancamentos(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Movimentações achatadas para o dashboard financeiro interativo.
    O front filtra por regime (competência/caixa), ano e centro de custo.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    # NÃO aplicar sem_itens_de_vale aqui — ver rules/vale_item.py. Este é o
    # extrato: o item TEM que continuar aparecendo na nota (o caixa da
    # fazenda continua batendo). Em vez de filtrar, enriquecemos cada item
    # com os campos de vale logo abaixo.
    query_itens = select(LancamentoItem)
    query_contas = select(ContaGerencial)
    if fazenda_id is not None:
        query_itens = query_itens.where(LancamentoItem.fazenda_id == fazenda_id)
        query_contas = query_contas.where(ContaGerencial.fazenda_id == fazenda_id)

    itens_carregados = session.exec(query_itens).all()

    # Resolve os dados de vale em lote (duas queries batch) — nunca N+1.
    ids_vale_funcionario = {it.vale_funcionario_id for it in itens_carregados if it.vale_funcionario_id}
    ids_vale_avulso = {it.vale_avulso_id for it in itens_carregados if it.vale_avulso_id}
    vales_funcionario = {
        v.id: v for v in (
            session.exec(select(ValeFuncionario).where(ValeFuncionario.id.in_(ids_vale_funcionario))).all()
            if ids_vale_funcionario else []
        )
    }
    vales_avulso = {
        v.id: v for v in (
            session.exec(select(ValeAvulso).where(ValeAvulso.id.in_(ids_vale_avulso))).all()
            if ids_vale_avulso else []
        )
    }
    ids_pessoa = {v.pessoa_id for v in vales_funcionario.values()} | {v.pessoa_id for v in vales_avulso.values()}
    nomes_pessoa = {
        p.id: p.nome for p in (session.exec(select(Pessoa).where(Pessoa.id.in_(ids_pessoa))).all() if ids_pessoa else [])
    }

    itens_por_lancamento: dict[str, list[dict]] = {}
    for it in itens_carregados:
        vale_tipo = None
        vale_id = None
        vale_pessoa_id = None
        if it.vale_funcionario_id is not None:
            vale_tipo, vale_id = "funcionario", it.vale_funcionario_id
            vale = vales_funcionario.get(vale_id)
            vale_pessoa_id = vale.pessoa_id if vale else None
        elif it.vale_avulso_id is not None:
            vale_tipo, vale_id = "avulso", it.vale_avulso_id
            vale = vales_avulso.get(vale_id)
            vale_pessoa_id = vale.pessoa_id if vale else None
        itens_por_lancamento.setdefault(it.numero_lancamento, []).append({
            "id": it.id,
            "tipo_item": it.tipo_item,
            "codigo_conta_gerencial": it.codigo_conta_gerencial,
            "nome_conta_gerencial": it.nome_conta_gerencial,
            "centro_custo": it.centro_custo,
            "produto": it.produto,
            "descricao": it.descricao,
            "quantidade": it.quantidade,
            "valor_unitario": it.valor_unitario,
            "valor_total": it.valor_total,
            "eh_vale": vale_tipo is not None,
            "vale_tipo": vale_tipo,
            "vale_id": vale_id,
            "vale_pessoa_id": vale_pessoa_id,
            "vale_pessoa_nome": nomes_pessoa.get(vale_pessoa_id) if vale_pessoa_id else None,
        })

    contas = session.exec(query_contas).all()
    nomes_usuarios = mapa_usuarios(session, {c.usuario_id for c in contas})

    # Quais lançamentos têm comprovante/anexo — UMA query, não uma por linha
    # (o relatório de Contas pagas mostra a coluna para a lista inteira).
    query_anexos = select(LancamentoAnexo.numero_lancamento)
    if fazenda_id is not None:
        query_anexos = query_anexos.where(LancamentoAnexo.fazenda_id == fazenda_id)
    numeros_com_anexo = set(session.exec(query_anexos).all())

    registros = []
    for c in contas:
        dc = c.data_competencia
        dp = c.data_pagamento
        registros.append({
            "id": c.id,
            "numero_lancamento": c.numero_lancamento,
            "tipo": c.tipo,
            "usuario_nome": nomes_usuarios.get(c.usuario_id),
            "valor": c.valor_total or 0.0,
            "valor_pago": c.valor_pago,
            "desconto_acrescimo": c.desconto_acrescimo,
            "desconto_nota": c.desconto_nota,
            "acrescimo_nota": c.acrescimo_nota,
            "centro_custo": c.centro_custo or "Sem centro de custo",
            "classificacao": c.classificacao,
            "codigo_conta": (c.codigo_conta or "").split(".")[0] or "(sem conta)",
            "conta_completa": c.codigo_conta or "",
            "descricao": c.descricao or "",
            "fornecedor": c.fornecedor_cliente or "",
            "responsavel": c.responsavel,
            "tipo_documento": c.tipo_documento,
            "numero_documento": c.numero_nota,
            "numero_os_orcamento": c.numero_os_orcamento,
            "numero_boleto": c.numero_boleto,
            "numero_documento_pagamento": c.numero_documento_pagamento,
            # Serve à coluna "Comprovante" do relatório de Contas pagas — o
            # comprovante do pagamento em lote é o mesmo arquivo para todas as
            # notas da remessa (ver anexar_comprovante_em_lote).
            "tem_comprovante": bool(c.numero_lancamento) and c.numero_lancamento in numeros_com_anexo,
            "conta_bancaria": c.conta_bancaria,
            "forma_pagamento": c.forma_pagamento,
            "data_vencimento_cartao": c.data_vencimento_cartao.isoformat() if c.data_vencimento_cartao else None,
            "quantidade": c.quantidade,
            "valor_unitario": c.valor_unitario,
            "entregue": c.entregue,
            "parcela_num": c.parcela_num,
            "parcela_total": c.parcela_total,
            "origem": c.origem,
            "itens": itens_por_lancamento.get(c.numero_lancamento or "", []),
            "data_competencia": dc.isoformat() if dc else None,
            "data_pagamento": dp.isoformat() if dp else None,
            "data_vencimento": c.data_vencimento.isoformat() if c.data_vencimento else None,
            "data_emissao": c.data_emissao.isoformat() if c.data_emissao else None,
            "data_prevista_entrada": c.data_prevista_entrada.isoformat() if c.data_prevista_entrada else None,
            "data_pedido": c.data_pedido.isoformat() if c.data_pedido else None,
            "patrimonio_id": c.patrimonio_id,
            "mes_competencia": f"{dc.year}-{dc.month:02d}" if dc else None,
            "ano_competencia": dc.year if dc else None,
            "mes_caixa": f"{dp.year}-{dp.month:02d}" if dp else None,
            "ano_caixa": dp.year if dp else None,
        })
    return {"lancamentos": registros, "total": len(registros)}


@router.get("/resultado-mes-recente")
def resultado_mes_recente(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Resultado (receita − despesa) do mês de competência mais recente que tem
    lançamento — sustenta só o card "Resultado do mês" da Capa.

    Antes a Capa chamava GET /financeiro/lancamentos (o extrato COMPLETO: todo
    o histórico de ContaGerencial da fazenda, com itens, vale, anexo e nome de
    usuário resolvidos por lançamento) só para achar o mês mais recente e
    somar duas colunas — a rota mais pesada do sistema virava trabalho pago a
    cada abertura da Capa, crescendo sem limite junto com o histórico
    financeiro. Aqui lemos só (data_competencia, tipo, valor_total), sem os
    joins/enriquecimentos que o extrato completo existe para sustentar.

    Mantém a mesma soma "crua" de valor_total (sem o ajuste de vale de
    fazenda.rules.vale_item.valor_gerencial) que a Capa já fazia a partir do
    extrato — não é o resultado gerencial do DRE (GET /financeiro/dre), que
    deduz vale; comportamento inalterado de propósito.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(ContaGerencial.data_competencia, ContaGerencial.tipo, ContaGerencial.valor_total).where(
        ContaGerencial.data_competencia != None  # noqa: E711
    )
    if fazenda_id is not None:
        query = query.where(ContaGerencial.fazenda_id == fazenda_id)
    linhas = [(d, tipo, valor) for d, tipo, valor in session.exec(query).all() if d is not None]
    if not linhas:
        return {"mes": None, "resultado": None}
    mes_mais_recente = max(f"{d.year}-{d.month:02d}" for d, _tipo, _valor in linhas)
    do_mes = [(tipo, valor) for d, tipo, valor in linhas if f"{d.year}-{d.month:02d}" == mes_mais_recente]
    receitas = sum((valor or 0.0) for tipo, valor in do_mes if tipo == "receita")
    despesas = sum((valor or 0.0) for tipo, valor in do_mes if tipo == "despesa")
    return {"mes": mes_mais_recente, "resultado": round(receitas - despesas, 2)}


@router.get("/possiveis-duplicados")
def possiveis_duplicados(
    tipo: str, valor_total: float, fornecedor_cliente: str = "", data_emissao: date | None = None,
    excluir_numero_lancamento: str = "", session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """
    Lançamentos já existentes parecidos com o que está sendo digitado agora —
    mesmo tipo (receita/despesa), fornecedor/cliente igual, valor dentro de
    uma pequena tolerância e data próxima. Usado no formulário para avisar
    "possível duplicado" antes de salvar, com uma comparação lado a lado.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    fornecedor_norm = (fornecedor_cliente or "").strip().lower()
    tolerancia_valor = max(0.01, abs(valor_total) * 0.01)  # 1% do valor, ou 1 centavo — o que for maior
    janela_dias = 10

    query = select(ContaGerencial).where(ContaGerencial.tipo == tipo)
    if fazenda_id is not None:
        query = query.where(ContaGerencial.fazenda_id == fazenda_id)
    candidatos = session.exec(query).all()
    por_numero: dict[str, ContaGerencial] = {}
    for c in candidatos:
        if excluir_numero_lancamento and c.numero_lancamento == excluir_numero_lancamento:
            continue
        if fornecedor_norm and (c.fornecedor_cliente or "").strip().lower() != fornecedor_norm:
            continue
        if c.valor_total is None or abs(c.valor_total - valor_total) > tolerancia_valor:
            continue
        data_referencia = c.data_emissao or c.data_competencia
        if data_emissao and data_referencia and abs((data_referencia - data_emissao).days) > janela_dias:
            continue
        # Uma nota parcelada tem várias linhas com o mesmo numero_lancamento —
        # mostra só uma vez (a de menor id) por lançamento encontrado.
        chave = c.numero_lancamento or str(c.id)
        if chave not in por_numero or c.id < por_numero[chave].id:
            por_numero[chave] = c

    achados = [
        {
            "id": c.id, "numero_lancamento": c.numero_lancamento, "tipo": c.tipo,
            "fornecedor_cliente": c.fornecedor_cliente, "valor_total": c.valor_total,
            "numero_documento": c.numero_nota,
            "data_emissao": c.data_emissao.isoformat() if c.data_emissao else None,
            "data_competencia": c.data_competencia.isoformat() if c.data_competencia else None,
            "centro_custo": c.centro_custo, "origem": c.origem,
        }
        for c in por_numero.values()
    ]
    achados.sort(key=lambda a: a["numero_lancamento"] or "", reverse=True)
    return achados[:10]


@router.get("/itens-por-conta")
def itens_por_conta(
    data_inicio: date = Query(...),
    data_fim: date = Query(...),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """
    Produtos/serviços lançados no período (por competência), um por linha —
    usado no DRE para o detalhamento correto por conta gerencial quando uma
    nota tem vários produtos com contas diferentes.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = sem_itens_de_vale(select(LancamentoItem))
    if fazenda_id is not None:
        query = query.where(LancamentoItem.fazenda_id == fazenda_id)
    itens = session.exec(query).all()
    return [
        {
            "numero_lancamento": it.numero_lancamento,
            "tipo": it.tipo,
            "codigo_conta_gerencial": it.codigo_conta_gerencial,
            "nome_conta_gerencial": it.nome_conta_gerencial,
            "produto": it.produto,
            "valor_total": it.valor_total,
            "data_competencia": it.data_competencia.isoformat() if it.data_competencia else None,
        }
        for it in itens
        if it.data_competencia and data_inicio <= it.data_competencia <= data_fim
    ]


def _url_dashboard_supabase() -> str | None:
    """Deriva a URL do painel do Supabase (Table Editor) a partir do
    SUPABASE_URL já configurado (mesma conta usada pelo Storage) — evita
    precisar de uma segunda variável de ambiente só para o link do botão.
    ex.: https://abcdefgh.supabase.co -> https://supabase.com/dashboard/project/abcdefgh/editor"""
    if not settings.supabase_url:
        return None
    host = settings.supabase_url.rstrip("/").split("://")[-1]
    ref = host.split(".")[0]
    return f"https://supabase.com/dashboard/project/{ref}/editor" if ref else None


@router.get("/supabase-dashboard-url")
def supabase_dashboard_url(_: None = Depends(exigir_nao_consultor())) -> dict:
    """Link para o painel do Supabase (Table Editor) — Relatórios financeiros
    > botão de acesso ao banco de dados externo. Disponível para quem tem o
    módulo financeiro (o router inteiro já exige isso) ou é contador; bloqueado
    para consultor (ver fazenda.auth.exigir_nao_consultor). `url: None` quando
    o Supabase não está configurado (SUPABASE_URL vazio)."""
    return {"url": _url_dashboard_supabase()}


@router.get("/opcoes")
def opcoes(session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id)) -> dict:
    """Listas para os seletores do lançamento — plano de contas real + dados já importados."""
    query_plano = select(PlanoContaGerencial).where(PlanoContaGerencial.ativa == True)
    if fazenda_id is not None:
        query_plano = query_plano.where(PlanoContaGerencial.fazenda_id == fazenda_id)
    plano = session.exec(query_plano).all()
    # Só as contas-FOLHA são lançáveis (nível mais baixo da hierarquia): uma
    # conta é folha quando nenhuma outra tem o código dela como prefixo "X.".
    todos_codigos = [c.codigo for c in plano]
    def _eh_folha(codigo: str) -> bool:
        prefixo = codigo + "."
        return not any(outro.startswith(prefixo) for outro in todos_codigos)
    contas_gerenciais = sorted(
        [{"codigo": c.codigo, "nome": c.nome} for c in plano if _eh_folha(c.codigo)],
        key=lambda x: x["codigo"],
    )
    contas = session.exec(select(ContaGerencial)).all()
    # União com os valores já lançados como texto livre (antes do cadastro
    # formal existir) — nada que já foi usado deixa de aparecer no filtro.
    query_centros = select(CentroCusto).where(CentroCusto.ativo == True)
    if fazenda_id is not None:
        query_centros = query_centros.where(CentroCusto.fazenda_id == fazenda_id)
    centros_cadastrados = {c.nome for c in session.exec(query_centros).all()}
    # Os centros canônicos (Pecuária Leiteira / Financiamento 2026 / Arrendamento)
    # ficam sempre disponíveis para seleção, mesmo antes de aparecerem num lançamento.
    centros_custo = sorted(centros_cadastrados | set(CENTROS_CANONICOS) | {c.centro_custo for c in contas if c.centro_custo})
    fornecedores = sorted({c.fornecedor_cliente for c in contas if c.fornecedor_cliente})
    # NÃO aplicar sem_itens_de_vale aqui — é datalist de nomes de produto já
    # usados (autocomplete); excluir os itens de vale só empobreceria as
    # sugestões, sem nenhum ganho gerencial (ver rules/vale_item.py).
    produtos = sorted({it.produto for it in session.exec(select(LancamentoItem)).all() if it.produto})
    query_contas_correntes = select(ContaCorrente).where(ContaCorrente.ativo == True)
    if fazenda_id is not None:
        query_contas_correntes = query_contas_correntes.where(ContaCorrente.fazenda_id == fazenda_id)
    contas_correntes = session.exec(query_contas_correntes.order_by(ContaCorrente.banco)).all()
    query_tipos_doc = select(TipoDocumento).where(TipoDocumento.ativo == True)
    query_formas_pgto = select(FormaPagamentoCadastro).where(FormaPagamentoCadastro.ativo == True)
    query_classificacoes = select(ClassificacaoLancamento).where(ClassificacaoLancamento.ativo == True)
    if fazenda_id is not None:
        query_tipos_doc = query_tipos_doc.where(TipoDocumento.fazenda_id == fazenda_id)
        query_formas_pgto = query_formas_pgto.where(FormaPagamentoCadastro.fazenda_id == fazenda_id)
        query_classificacoes = query_classificacoes.where(ClassificacaoLancamento.fazenda_id == fazenda_id)
    tipos_doc_cadastrados = [t.nome for t in session.exec(query_tipos_doc.order_by(TipoDocumento.nome)).all()]
    formas_pgto_cadastradas = [f.nome for f in session.exec(query_formas_pgto.order_by(FormaPagamentoCadastro.nome)).all()]
    classificacoes_cadastradas = [c.nome for c in session.exec(query_classificacoes.order_by(ClassificacaoLancamento.nome)).all()]
    return {
        "contas_gerenciais": contas_gerenciais,
        "centros_custo": centros_custo,
        "fornecedores": fornecedores,
        "produtos": produtos,
        "contas_bancarias": [rotulo_conta_corrente(c) for c in contas_correntes],
        "tipos_documento": tipos_doc_cadastrados or TIPOS_DOCUMENTO,
        "formas_pagamento": formas_pgto_cadastradas or FORMAS_PAGAMENTO,
        "classificacoes": classificacoes_cadastradas,
    }


@router.get("/contexto-fornecedor")
def contexto_fornecedor(
    nome: str, tipo: str = "despesa", session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Histórico de um fornecedor/cliente para a coluna de contexto da tela
    de lançamento (ver FormFinanceiro): quanto está em aberto com ele, o
    último lançamento, os últimos lançamentos e os documentos já anexados a
    alguma nota dele — tudo só leitura, para decidir antes de lançar."""
    nome = (nome or "").strip()
    vazio = {"em_aberto": 0.0, "ultimo_lancamento": None, "ultimos_lancamentos": [], "documentos_anexados": []}
    if not nome:
        return vazio
    query = select(ContaGerencial).where(ContaGerencial.fornecedor_cliente == nome, ContaGerencial.tipo == tipo)
    if fazenda_id is not None:
        query = query.where(ContaGerencial.fazenda_id == fazenda_id)
    contas = session.exec(query.order_by(ContaGerencial.data_emissao.desc(), ContaGerencial.id.desc())).all()
    if not contas:
        return vazio

    em_aberto = round(sum(c.valor_total or 0 for c in contas if c.valor_pago is None), 2)
    ultimo = contas[0]

    numeros_lancamento = {c.numero_lancamento for c in contas if c.numero_lancamento}
    documentos_anexados: list[dict] = []
    if numeros_lancamento:
        query_anexos = select(LancamentoAnexo).where(LancamentoAnexo.numero_lancamento.in_(numeros_lancamento))
        if fazenda_id is not None:
            query_anexos = query_anexos.where(LancamentoAnexo.fazenda_id == fazenda_id)
        anexos = session.exec(query_anexos.order_by(LancamentoAnexo.criado_em.desc())).all()
        documentos_anexados = [
            {"nome_arquivo": a.nome_arquivo, "categoria": a.categoria, "criado_em": a.criado_em.isoformat()}
            for a in anexos[:8]
        ]

    return {
        "em_aberto": em_aberto,
        "ultimo_lancamento": ultimo.data_emissao.isoformat() if ultimo.data_emissao else None,
        "ultimos_lancamentos": [
            {
                "numero_lancamento": c.numero_lancamento,
                "numero_documento": c.numero_nota,
                "data": c.data_emissao.isoformat() if c.data_emissao else None,
                "valor": c.valor_total or 0.0,
                "pago": c.valor_pago is not None,
            }
            for c in contas[:6]
        ],
        "documentos_anexados": documentos_anexados,
    }


@router.get("/ultimo-preco")
def ultimo_preco_produto(
    produto: str, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Último valor unitário pago (ou recebido) num produto/serviço — mini-
    observação abaixo do item selecionado em Contas a pagar/receber (ver
    FormFinanceiro). Lê LancamentoItem.valor_unitario, gravado ao criar o
    lançamento (ver criar_lancamento acima, ~:1786), casando pelo NOME do
    produto/serviço (normalizado: sem espaços nas pontas, sem diferença de
    maiúscula) e pegando o mais recente por data_competencia. Sem histórico
    devolve vazio — nunca inventa 0,00; quem decide não mostrar a observação
    nesse caso é o front (ver fetchUltimoPrecoProduto em lib/api.ts)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    nome = (produto or "").strip()
    if not nome:
        return {}
    nome_norm = nome.lower()
    query = select(LancamentoItem).where(LancamentoItem.valor_unitario.is_not(None))
    if fazenda_id is not None:
        query = query.where(LancamentoItem.fazenda_id == fazenda_id)
    achados = [it for it in session.exec(query).all() if (it.produto or "").strip().lower() == nome_norm]
    if not achados:
        return {}
    achados.sort(key=lambda it: (it.data_competencia or date.min, it.id or 0))
    escolhido = achados[-1]
    return {
        "produto": escolhido.produto,
        "valor_unitario": escolhido.valor_unitario,
        "data": escolhido.data_competencia.isoformat() if escolhido.data_competencia else None,
        "numero_lancamento": escolhido.numero_lancamento,
    }


@router.get("/plano-contas")
def plano_contas(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """
    Plano de contas gerenciais COMPLETO (inclui os códigos de grupo/cabeçalho,
    que vêm com Ativa=Não e não aparecem em /opcoes — aqui servem só para dar
    nome à hierarquia nos relatórios, não para lançar diretamente neles).
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(PlanoContaGerencial)
    if fazenda_id is not None:
        query = query.where(PlanoContaGerencial.fazenda_id == fazenda_id)
    plano = session.exec(query).all()
    return sorted(
        [
            {
                "id": c.id, "codigo": c.codigo, "nome": c.nome, "ativa": c.ativa,
                "nivel": c.codigo.count(".") + 1,
                "fluxo": c.fluxo, "tipo_fixo_variavel": c.tipo_fixo_variavel,
                "rmca_receita_leite": c.rmca_receita_leite, "rmca_custo_alimentacao": c.rmca_custo_alimentacao,
                "natureza": c.natureza,
                "pede_vinculo_sanitario_reprodutivo": c.pede_vinculo_sanitario_reprodutivo,
            }
            for c in plano
        ],
        key=lambda x: x["codigo"],
    )


# ---------------------------------------------------------------------------
# Parâmetros financeiros (Configurações) — conta corrente, centro de custo e
# conta gerencial cadastráveis, além da importação de CSV do plano de contas.
# ---------------------------------------------------------------------------
class ContaCorrenteIn(BaseModel):
    banco: str
    agencia: str
    numero_conta: str
    ativo: bool = True


@router.get("/contas-correntes")
def listar_contas_correntes(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    query = select(ContaCorrente)
    if fazenda_id is not None:
        query = query.where(ContaCorrente.fazenda_id == fazenda_id)
    contas = session.exec(query.order_by(ContaCorrente.banco, ContaCorrente.agencia)).all()
    saldos = calcular_saldos_contas_correntes(session, contas, fazenda_id)
    return [{**c.model_dump(), "rotulo": rotulo_conta_corrente(c), "saldo": saldos.get(c.id, 0.0)} for c in contas]


@router.post("/contas-correntes")
def criar_conta_corrente(
    dados: ContaCorrenteIn, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    c = ContaCorrente(**dados.model_dump(), fazenda_id=fazenda_id)
    session.add(c)
    session.commit()
    session.refresh(c)
    return {**c.model_dump(), "rotulo": rotulo_conta_corrente(c), "saldo": 0.0}


@router.put("/contas-correntes/{conta_id}")
def atualizar_conta_corrente(
    conta_id: int, dados: ContaCorrenteIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    c = session.get(ContaCorrente, conta_id)
    if not c or (fazenda_id is not None and c.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Conta corrente não encontrada")
    for campo, valor in dados.model_dump().items():
        setattr(c, campo, valor)
    session.add(c)
    session.commit()
    session.refresh(c)
    saldo = calcular_saldos_contas_correntes(session, [c], fazenda_id).get(c.id, 0.0)
    return {**c.model_dump(), "rotulo": rotulo_conta_corrente(c), "saldo": saldo}


class TransferenciaContasIn(BaseModel):
    conta_origem_id: int
    conta_destino_id: int
    valor: float
    data: date
    observacao: Optional[str] = None


@router.get("/contas-correntes/transferencias")
def listar_transferencias_contas(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    query = select(TransferenciaContas)
    if fazenda_id is not None:
        query = query.where(TransferenciaContas.fazenda_id == fazenda_id)
    itens = session.exec(query.order_by(TransferenciaContas.data.desc(), TransferenciaContas.id.desc())).all()
    return [t.model_dump() for t in itens]


@router.post("/contas-correntes/transferencias", status_code=201)
def criar_transferencia_contas(
    dados: TransferenciaContasIn, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    Transferência entre contas correntes cadastradas (Configurações >
    Parâmetros financeiros > Conta corrente > "Transferir entre contas") —
    dinheiro sai de uma conta própria e entra em outra, não é despesa nem
    receita da fazenda: não gera ContaGerencial nenhum, então fica fora do
    DRE e dos relatórios gerenciais; só ajusta o saldo calculado das duas
    contas (ver calcular_saldos_contas_correntes).
    """
    if dados.conta_origem_id == dados.conta_destino_id:
        raise HTTPException(status_code=400, detail="Conta de origem e destino precisam ser diferentes")
    if dados.valor <= 0:
        raise HTTPException(status_code=400, detail="O valor da transferência deve ser positivo")

    origem = session.get(ContaCorrente, dados.conta_origem_id)
    destino = session.get(ContaCorrente, dados.conta_destino_id)
    if not origem or (fazenda_id is not None and origem.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Conta de origem não encontrada")
    if not destino or (fazenda_id is not None and destino.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Conta de destino não encontrada")

    t = TransferenciaContas(
        conta_origem_id=dados.conta_origem_id,
        conta_destino_id=dados.conta_destino_id,
        valor=round(dados.valor, 2),
        data=dados.data,
        observacao=(dados.observacao or None),
        usuario_id=user.id if isinstance(user, Usuario) else None,
        fazenda_id=fazenda_id,
    )
    session.add(t)
    session.commit()
    session.refresh(t)
    return t.model_dump()


class CentroCustoIn(BaseModel):
    nome: str
    ativo: bool = True
    # Centro de custo padrão do Lançamento simplificado (Lançamentos >
    # Financeiro) — no máximo 1 por fazenda. False (padrão do payload) nunca
    # desmarca um padrão já definido por OUTRO request; só True desencadeia a
    # troca (ver `_desmarcar_outros_centro_custo_padrao` abaixo).
    padrao: bool = False


def _desmarcar_outros_centro_custo_padrao(session: Session, fazenda_id: int | None, manter_id: int | None) -> None:
    """Regra de negócio: no máximo 1 centro de custo com padrao=True por
    fazenda. Chamado sempre que um centro é marcado como padrão, ANTES do
    commit que grava esse centro — fica na mesma transação (atômico)."""
    query = select(CentroCusto).where(CentroCusto.padrao == True, CentroCusto.fazenda_id == fazenda_id)  # noqa: E712
    if manter_id is not None:
        query = query.where(CentroCusto.id != manter_id)
    for outro in session.exec(query).all():
        outro.padrao = False
        session.add(outro)


@router.get("/centros-custo")
def listar_centros_custo(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    query = select(CentroCusto)
    if fazenda_id is not None:
        query = query.where(CentroCusto.fazenda_id == fazenda_id)
    return [c.model_dump() for c in session.exec(query.order_by(CentroCusto.nome)).all()]


@router.post("/centros-custo")
def criar_centro_custo(
    dados: CentroCustoIn, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    duplicado = select(CentroCusto).where(CentroCusto.nome == nome, CentroCusto.fazenda_id == fazenda_id)
    if session.exec(duplicado).first():
        raise HTTPException(status_code=409, detail="Já existe um centro de custo com esse nome")
    if dados.padrao:
        _desmarcar_outros_centro_custo_padrao(session, fazenda_id, manter_id=None)
    c = CentroCusto(nome=nome, ativo=dados.ativo, fazenda_id=fazenda_id, padrao=dados.padrao)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c.model_dump()


@router.put("/centros-custo/{centro_id}")
def atualizar_centro_custo(
    centro_id: int, dados: CentroCustoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    c = session.get(CentroCusto, centro_id)
    if not c or (fazenda_id is not None and c.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Centro de custo não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    c.nome = nome
    c.ativo = dados.ativo
    if dados.padrao:
        _desmarcar_outros_centro_custo_padrao(session, fazenda_id, manter_id=c.id)
    c.padrao = dados.padrao
    session.add(c)
    session.commit()
    session.refresh(c)
    return c.model_dump()


class NomeAtivoFinanceiroIn(BaseModel):
    nome: str
    ativo: bool = True


def _crud_nome_ativo_financeiro(model, rotulo: str):
    """Mesma fábrica de CRUD nome+ativo do cadastro/_comum.py (não reusada
    diretamente por import cruzado — cadastro/__init__.py já importa deste
    módulo via rh_contratos.py, então importar cadastro._comum aqui de volta
    criaria um import circular). Filtra a listagem e a checagem de duplicata
    pela fazenda atual, e carimba fazenda_id no registro criado (piloto
    conservador de multi-fazenda, Fase 3B)."""

    def listar(session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id)) -> list[dict]:
        fazenda_id = fazenda_id_seguro(fazenda_id)
        query = select(model).order_by(model.nome)
        if fazenda_id is not None:
            query = query.where(model.fazenda_id == fazenda_id)
        return [m.model_dump() for m in session.exec(query).all()]

    def criar(
        dados: NomeAtivoFinanceiroIn, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
    ) -> dict:
        fazenda_id = fazenda_id_seguro(fazenda_id)
        nome = dados.nome.strip()
        if not nome:
            raise HTTPException(status_code=400, detail="Nome é obrigatório")
        query_dup = select(model).where(model.nome == nome)
        if fazenda_id is not None:
            query_dup = query_dup.where(model.fazenda_id == fazenda_id)
        if session.exec(query_dup).first():
            raise HTTPException(status_code=409, detail=f"Já existe um(a) {rotulo} com esse nome")
        obj = model(nome=nome, ativo=dados.ativo, fazenda_id=fazenda_id)
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj.model_dump()

    def atualizar(
        item_id: int, dados: NomeAtivoFinanceiroIn, session: Session = Depends(get_session),
        fazenda_id: int | None = Depends(get_fazenda_atual_id),
    ) -> dict:
        fazenda_id = fazenda_id_seguro(fazenda_id)
        obj = session.get(model, item_id)
        if not obj or (fazenda_id is not None and obj.fazenda_id != fazenda_id):
            raise HTTPException(status_code=404, detail=f"{rotulo.capitalize()} não encontrado(a)")
        nome = dados.nome.strip()
        if not nome:
            raise HTTPException(status_code=400, detail="Nome é obrigatório")
        obj.nome = nome
        obj.ativo = dados.ativo
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj.model_dump()

    return listar, criar, atualizar


_listar_tipos_doc, _criar_tipo_doc, _atualizar_tipo_doc = _crud_nome_ativo_financeiro(TipoDocumento, "tipo de documento")
router.get("/tipos-documento")(_listar_tipos_doc)
router.post("/tipos-documento")(_criar_tipo_doc)
router.put("/tipos-documento/{item_id}")(_atualizar_tipo_doc)

_listar_formas_pgto, _criar_forma_pgto, _atualizar_forma_pgto = _crud_nome_ativo_financeiro(FormaPagamentoCadastro, "forma de pagamento")
router.get("/formas-pagamento-cadastro")(_listar_formas_pgto)
router.post("/formas-pagamento-cadastro")(_criar_forma_pgto)
router.put("/formas-pagamento-cadastro/{item_id}")(_atualizar_forma_pgto)

_listar_classificacoes, _criar_classificacao, _atualizar_classificacao = _crud_nome_ativo_financeiro(ClassificacaoLancamento, "classificação")
router.get("/classificacoes")(_listar_classificacoes)
router.post("/classificacoes")(_criar_classificacao)
router.put("/classificacoes/{item_id}")(_atualizar_classificacao)


# Seed inicial — migra as listas fixas que existiam antes (TIPOS_DOCUMENTO,
# FORMAS_PAGAMENTO) para os cadastros acima, mais os itens pedidos que ainda
# não existiam (Ordem de serviço/Outros; dinheiro/outros) — idempotente.
SEED_TIPOS_DOCUMENTO = [*TIPOS_DOCUMENTO, "Boleto", "Ordem de serviço", *CATEGORIAS_DOCUMENTO_ARQUIVO, "Outros"]
SEED_FORMAS_PAGAMENTO_CADASTRO = [*FORMAS_PAGAMENTO, "dinheiro", "outros"]


def seed_tipos_documento_formas_pagamento(session: Session) -> None:
    # Só acrescenta os nomes que ainda não existem — nunca duplica, e continua
    # funcionando em bancos que já tinham a lista antiga (ex.: sem "Boleto").
    existentes_doc = {t.nome for t in session.exec(select(TipoDocumento)).all()}
    for nome in SEED_TIPOS_DOCUMENTO:
        if nome not in existentes_doc:
            session.add(TipoDocumento(nome=nome))
    session.commit()
    existentes_forma = {f.nome for f in session.exec(select(FormaPagamentoCadastro)).all()}
    for nome in SEED_FORMAS_PAGAMENTO_CADASTRO:
        if nome not in existentes_forma:
            session.add(FormaPagamentoCadastro(nome=nome))
    session.commit()


class PlanoContaGerencialIn(BaseModel):
    codigo: str
    nome: str
    ativa: bool = True
    participa_atividade: bool | None = None
    fluxo: bool | None = None
    tipo_fixo_variavel: str | None = None
    # Marcação para o indicador RMCA (ver GET /financeiro/rmca).
    rmca_receita_leite: bool | None = None
    rmca_custo_alimentacao: bool | None = None
    # "servico" | "produto" | "ambos" — restringe o que pode ser lançado nesta
    # conta em Financeiro > Contas a pagar/a receber (ver FormFinanceiro).
    natureza: str | None = None
    # Quando marcado, lançar uma despesa nesta conta pergunta, ao salvar, se o
    # pagamento deve ser vinculado a uma vacina/exame/visita reprodutiva (ver
    # popup de vínculo sanitário/reprodutivo em FormFinanceiro).
    pede_vinculo_sanitario_reprodutivo: bool | None = None


@router.post("/plano-contas")
def criar_conta_gerencial(
    dados: PlanoContaGerencialIn, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    codigo = dados.codigo.strip()
    if not codigo or not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Código e nome são obrigatórios")
    query_dup = select(PlanoContaGerencial).where(PlanoContaGerencial.codigo == codigo)
    if fazenda_id is not None:
        query_dup = query_dup.where(PlanoContaGerencial.fazenda_id == fazenda_id)
    if session.exec(query_dup).first():
        raise HTTPException(status_code=409, detail="Já existe uma conta gerencial com esse código")
    campos = {**dados.model_dump(), "codigo": codigo, "fazenda_id": fazenda_id}
    # Item de "3.01.01 - Alimentação do rebanho" já nasce marcado para o RMCA
    # (custo de alimentação), a menos que o usuário tenha desmarcado no formulário.
    if codigo.startswith("3.01.01") and dados.rmca_custo_alimentacao is None:
        campos["rmca_custo_alimentacao"] = True
    conta = PlanoContaGerencial(**campos)
    session.add(conta)
    session.commit()
    session.refresh(conta)
    return conta.model_dump()


@router.put("/plano-contas/{conta_id}")
def atualizar_conta_gerencial(
    conta_id: int, dados: PlanoContaGerencialIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    conta = session.get(PlanoContaGerencial, conta_id)
    if not conta or (fazenda_id is not None and conta.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Conta gerencial não encontrada")
    for campo, valor in dados.model_dump().items():
        setattr(conta, campo, valor)
    session.add(conta)
    session.commit()
    session.refresh(conta)
    return conta.model_dump()


# ---------------------------------------------------------------------------
# Vínculo financeiro ↔ sanitário/reprodutivo — despesas em contas gerenciais
# marcadas (ex.: "3.03.02.11 - Veterinário/zootecnista", ver
# PlanoContaGerencial.pede_vinculo_sanitario_reprodutivo) podem ser associadas
# a uma aplicação de vacina, exame ou visita reprodutiva (diagnóstico de
# gestação) já lançados — ou o inverso: ao lançar a vacina/exame/diagnóstico,
# associá-lo a uma conta a pagar/paga já existente, ou gerar uma nova a partir
# dele. O vínculo é feito por `numero_lancamento_vinculado` (soft-join pelo
# número do lançamento, mesmo padrão de ManutencaoPatrimonio/FolhaPagamento),
# nunca por FK — garante rastreabilidade sem acoplar os módulos.
# ---------------------------------------------------------------------------
def _rotulo_exame(exame_definicao_id: int | None, session: Session) -> str:
    if exame_definicao_id is None:
        return "Exame"
    ed = session.get(ExameDefinicao, exame_definicao_id)
    return f"Exame de {ed.nome}" if ed else "Exame"


@router.get("/candidatos-vinculo-sanitario-reprodutivo")
def candidatos_vinculo_sanitario_reprodutivo(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Lista, para toda a fazenda (não filtrada por animal — o lançamento
    financeiro não guarda animal/matriz), os eventos sanitários/reprodutivos
    mais recentes ainda NÃO vinculados a um lançamento financeiro: os 3
    últimos serviços reprodutivos (diagnóstico de gestação), as 2 últimas
    vacinas aplicadas e os 2 últimos exames realizados — cada um agrupado por
    data (um lançamento em lote, com vários animais, vira um só candidato).
    Usado no popup de vínculo ao salvar uma despesa numa conta gerencial
    marcada (ver PlanoContaGerencial.pede_vinculo_sanitario_reprodutivo).
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    # Serviços reprodutivos com diagnóstico já lançado — agrupados por
    # (data do diagnóstico, método), que coincide com a data da visita/D0.
    query_servicos = select(Servico).where(
        Servico.numero_lancamento_vinculado.is_(None), Servico.data_diagnostico.is_not(None)
    )
    if fazenda_id is not None:
        query_servicos = query_servicos.where(Servico.fazenda_id == fazenda_id)
    servicos = session.exec(query_servicos.order_by(Servico.data_diagnostico.desc())).all()
    grupos_servico: dict[tuple, list[Servico]] = {}
    for s in servicos:
        grupos_servico.setdefault((s.data_diagnostico, s.metodo_diagnostico), []).append(s)
    candidatos_servico = [
        {
            "tipo": "servico",
            "ids": [g.id for g in grupo],
            "rotulo": f"Diagnóstico de gestação — {metodo or 'visita reprodutiva'} ({len(grupo)} animal(is))",
            "data": data.isoformat() if data else None,
            "responsavel": next((g.inseminador for g in grupo if g.inseminador), None),
        }
        for (data, metodo), grupo in list(grupos_servico.items())[:3]
    ]

    # Vacinas aplicadas (Sanidade, categoria "Vacina") — agrupadas por
    # (produto, data de aplicação).
    query_vacinas = select(Sanidade).where(
        Sanidade.numero_lancamento_vinculado.is_(None), Sanidade.categoria == "Vacina"
    )
    if fazenda_id is not None:
        query_vacinas = query_vacinas.where(Sanidade.fazenda_id == fazenda_id)
    vacinas = session.exec(query_vacinas.order_by(Sanidade.data_aplicacao.desc())).all()
    grupos_vacina: dict[tuple, list[Sanidade]] = {}
    for v in vacinas:
        grupos_vacina.setdefault((v.produto, v.data_aplicacao), []).append(v)
    candidatos_vacina = [
        {
            "tipo": "sanidade",
            "ids": [g.id for g in grupo],
            "rotulo": f"Vacina — {produto} ({len(grupo)} animal(is))",
            "data": data.isoformat() if data else None,
            "responsavel": next((g.responsavel for g in grupo if g.responsavel), None),
        }
        for (produto, data), grupo in list(grupos_vacina.items())[:2]
    ]

    # Exames realizados (ExameResultado) — agrupados por (exame, data).
    query_exames = select(ExameResultado).where(ExameResultado.numero_lancamento_vinculado.is_(None))
    if fazenda_id is not None:
        query_exames = query_exames.where(ExameResultado.fazenda_id == fazenda_id)
    exames = session.exec(query_exames.order_by(ExameResultado.data_exame.desc())).all()
    grupos_exame: dict[tuple, list[ExameResultado]] = {}
    for e in exames:
        grupos_exame.setdefault((e.exame_definicao_id, e.data_exame), []).append(e)
    candidatos_exame = [
        {
            "tipo": "exame",
            "ids": [g.id for g in grupo],
            "rotulo": f"{_rotulo_exame(exame_definicao_id, session)} ({len(grupo)} animal(is))",
            "data": data.isoformat() if data else None,
            "responsavel": next((g.veterinario for g in grupo if g.veterinario), None),
        }
        for (exame_definicao_id, data), grupo in list(grupos_exame.items())[:2]
    ]

    return {"servicos": candidatos_servico, "vacinas": candidatos_vacina, "exames": candidatos_exame}


class VincularEventoIn(BaseModel):
    tipo: str  # "sanidade" | "exame" | "servico"
    ids: list[int]
    numero_lancamento: str


@router.post("/vincular-evento-sanitario-reprodutivo")
def vincular_evento_sanitario_reprodutivo(dados: VincularEventoIn, session: Session = Depends(get_session)) -> dict:
    modelo = {"sanidade": Sanidade, "exame": ExameResultado, "servico": Servico}.get(dados.tipo)
    if modelo is None:
        raise HTTPException(status_code=400, detail="Tipo inválido (use: sanidade, exame, servico)")
    if not session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == dados.numero_lancamento)).first():
        raise HTTPException(status_code=404, detail="Lançamento financeiro não encontrado")
    atualizados = 0
    for item_id in dados.ids:
        obj = session.get(modelo, item_id)
        if obj:
            obj.numero_lancamento_vinculado = dados.numero_lancamento
            session.add(obj)
            atualizados += 1
    session.commit()
    return {"vinculados": atualizados}


@router.get("/lancamentos-por-data")
def lancamentos_por_data(
    data: date, tipo: str = "despesa", session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """
    Lançamentos (agrupados por numero_lancamento) com data de EMISSÃO igual à
    informada — usado no popup de vínculo do lado sanitário/reprodutivo,
    opção "associar este evento a uma conta paga/a pagar" (a data buscada é a
    da vacina/exame/diagnóstico, ver /calendario/cadastrar-preventivo e
    reprodução > diagnóstico de gestação).
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(ContaGerencial).where(ContaGerencial.data_emissao == data, ContaGerencial.tipo == tipo)
    if fazenda_id is not None:
        query = query.where(ContaGerencial.fazenda_id == fazenda_id)
    contas = session.exec(query).all()
    por_lancamento: dict[str, list[ContaGerencial]] = {}
    for c in contas:
        if c.numero_lancamento:
            por_lancamento.setdefault(c.numero_lancamento, []).append(c)
    return [
        {
            "numero_lancamento": numero,
            "fornecedor_cliente": grupo[0].fornecedor_cliente,
            "descricao": grupo[0].descricao,
            "valor_total": sum(c.valor_total or 0 for c in grupo),
            "status": "pago" if all(c.valor_pago is not None for c in grupo) else "em aberto",
        }
        for numero, grupo in por_lancamento.items()
    ]


@router.get("/rmca")
def rmca(
    data_inicio: date = Query(..., description="Data inicial (competência)"),
    data_fim: date = Query(..., description="Data final (competência)"),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Indicador RMCA (Receita Menos Custo com Alimentação), em duas versões
    lado a lado: "gerencial" (soma dos lançamentos financeiros pelas contas
    marcadas em Configurações > Parâmetros financeiros) e "físico" (receita
    igual, mas custo a partir do consumo real registrado pela Alimentação em
    MovimentoEstoque × valor unitário do item no Estoque).
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_plano = select(PlanoContaGerencial)
    if fazenda_id is not None:
        query_plano = query_plano.where(PlanoContaGerencial.fazenda_id == fazenda_id)
    plano = session.exec(query_plano).all()
    codigos_receita = {c.codigo for c in plano if c.rmca_receita_leite}
    codigos_custo = {c.codigo for c in plano if c.rmca_custo_alimentacao}

    query_itens = sem_itens_de_vale(select(LancamentoItem))
    if fazenda_id is not None:
        query_itens = query_itens.where(LancamentoItem.fazenda_id == fazenda_id)
    itens = [
        it.model_dump() for it in session.exec(query_itens).all()
        if it.data_competencia and data_inicio <= it.data_competencia <= data_fim
    ]
    gerencial = calcular_rmca_gerencial(itens, codigos_receita, codigos_custo)

    query_movimentos = select(MovimentoEstoque)
    if fazenda_id is not None:
        query_movimentos = query_movimentos.where(MovimentoEstoque.fazenda_id == fazenda_id)
    movimentos = [
        m.model_dump() for m in session.exec(query_movimentos).all()
        if m.movimento == "Saída de ajuste" and data_inicio <= m.data_movimento <= data_fim
    ]
    query_estoque = select(Estoque)
    if fazenda_id is not None:
        query_estoque = query_estoque.where(Estoque.fazenda_id == fazenda_id)
    estoque_por_nome = {e.nome: e.model_dump() for e in session.exec(query_estoque).all()}
    fisico = calcular_custo_fisico(movimentos, estoque_por_nome)

    return {
        "periodo": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()},
        "configurado": bool(codigos_receita) and bool(codigos_custo),
        "contas_receita": sorted(c.nome for c in plano if c.codigo in codigos_receita),
        "contas_custo": sorted(c.nome for c in plano if c.codigo in codigos_custo),
        "gerencial": gerencial,
        "fisico": {
            "receita_leite": gerencial["receita_leite"],
            "custo_alimentacao": fisico["custo_total"],
            "rmca": round(gerencial["receita_leite"] - fisico["custo_total"], 2),
            "itens": fisico["itens"],
        },
        "meta_rmca": meta_rmca(),
    }


@router.get("/custo-litro-leite")
def custo_litro_leite(
    data_inicio: date = Query(..., description="Data inicial (competência)"),
    data_fim: date = Query(..., description="Data final (competência)"),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Custo por litro de leite — total gasto com alimentação no período (as
    mesmas contas marcadas em Configurações > Parâmetros financeiros para o
    custo do RMCA) dividido pelos litros de leite entregues no período
    (Entrega mensal do leite), projetados proporcionalmente por dia quando o
    período não cobre o mês inteiro.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_plano = select(PlanoContaGerencial)
    if fazenda_id is not None:
        query_plano = query_plano.where(PlanoContaGerencial.fazenda_id == fazenda_id)
    plano = session.exec(query_plano).all()
    codigos_custo = {c.codigo for c in plano if c.rmca_custo_alimentacao}

    query_itens = sem_itens_de_vale(select(LancamentoItem))
    if fazenda_id is not None:
        query_itens = query_itens.where(LancamentoItem.fazenda_id == fazenda_id)
    itens = [
        it.model_dump() for it in session.exec(query_itens).all()
        if it.data_competencia and data_inicio <= it.data_competencia <= data_fim
    ]
    custo_total = round(sum(i["valor_total"] or 0 for i in itens if i["codigo_conta_gerencial"] in codigos_custo), 2)

    # Mesmo escopo de fazenda do custo, logo acima — sem este filtro o custo
    # saía dividido pelos litros entregues por TODAS as fazendas, e o custo por
    # litro do cliente vinha diluído pela entrega dos outros clientes.
    query_entregas = select(EntregaLeiteMensal)
    if fazenda_id is not None:
        query_entregas = query_entregas.where(EntregaLeiteMensal.fazenda_id == fazenda_id)
    entregas = {e.competencia: e.quantidade_litros for e in session.exec(query_entregas).all()}
    litros = litros_leite_no_periodo(entregas, data_inicio, data_fim)

    return {
        "periodo": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()},
        "configurado": bool(codigos_custo),
        "tem_entrega": bool(entregas),
        "contas_custo": sorted(c.nome for c in plano if c.codigo in codigos_custo),
        **calcular_custo_por_litro(custo_total, litros),
    }


@router.get("/patrimonio/lista-simples")
def listar_patrimonio_simples(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Id + nome de cada item de patrimônio (sem depreciação/manutenção) —
    para o seletor "Vincular a patrimônio" na edição de um lançamento
    (qualquer usuário com módulo financeiro, não só administrador; a aba
    Patrimônio em si continua admin-only, ver GET /financeiro/patrimonio)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Patrimonio).where(Patrimonio.data_baixa == None)  # noqa: E711
    if fazenda_id is not None:
        query = query.where(Patrimonio.fazenda_id == fazenda_id)
    return [{"id": p.id, "nome": p.nome, "tipo": p.tipo} for p in session.exec(query).all()]


@router.get("/patrimonio")
def listar_patrimonio(
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    _: Usuario = Depends(exigir_admin),
) -> dict:
    """Lista o patrimônio/imobilizado da fazenda, já com a depreciação linear
    calculada (valor atual = valor total menos a depreciação acumulada desde
    a imobilização) — ou, para patrimônio não depreciável (`depreciavel=False`,
    ex.: terra), o valor de mercado mais recente. Só administradores da
    fazenda têm acesso a esta aba."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    hoje = date.today()
    frequencia_padrao = patrimonio_atualizacao_valor_mercado_meses()
    query = select(Patrimonio)
    if fazenda_id is not None:
        query = query.where(Patrimonio.fazenda_id == fazenda_id)
    itens_raw = session.exec(query).all()
    itens: list[dict] = []
    inconsistencias: list[dict] = []
    valor_total_bruto = 0.0
    valor_atual_total = 0.0
    for i in itens_raw:
        d = i.model_dump()
        dep = calcular_depreciacao(d, hoje)
        d.update(dep)
        d.update(status_manutencao(d, hoje))
        prox_valor_mercado = proxima_atualizacao_valor_mercado(d, frequencia_padrao)
        d["proxima_atualizacao_valor_mercado"] = prox_valor_mercado.isoformat() if prox_valor_mercado else None
        itens.append(d)
        if not i.data_baixa:
            valor_total_bruto += i.valor_total or 0
            valor_atual_total += dep["valor_atual"] or 0
        if dep["inconsistencia"]:
            inconsistencias.append({"item": i.nome, "numero": i.numero, "motivo": dep["inconsistencia"]})
    return {
        "itens": itens, "total": len(itens_raw),
        "valor_total": round(valor_total_bruto, 2),
        "valor_atual_total": round(valor_atual_total, 2),
        "inconsistencias": inconsistencias,
    }


@router.post("/patrimonio", status_code=201)
def criar_patrimonio(
    dados: PatrimonioIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id), _: Usuario = Depends(exigir_admin),
) -> dict:
    """Cadastra um item de patrimônio já existente na fazenda (não uma
    compra nova — para isso, ver POST /financeiro/lancamentos com
    `criar_patrimonio` preenchido, que cria os dois registros vinculados de
    uma vez). Substitui o upload de CSV como forma de cadastro."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    item = Patrimonio(
        **dados.model_dump(exclude={"nome"}), nome=dados.nome.strip(), fazenda_id=fazenda_id,
    )
    if not item.depreciavel and item.valor_mercado_atual is None:
        item.valor_mercado_atual = item.valor_total
    session.add(item)
    session.commit()
    session.refresh(item)
    return item.model_dump()


@router.put("/patrimonio/{item_id}")
def atualizar_patrimonio(
    item_id: int, dados: PatrimonioIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id), _: Usuario = Depends(exigir_admin),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    item = session.get(Patrimonio, item_id)
    if not item or (fazenda_id is not None and item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Item de patrimônio não encontrado")
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    for campo, valor in dados.model_dump(exclude={"nome"}).items():
        setattr(item, campo, valor)
    item.nome = dados.nome.strip()
    session.add(item)
    session.commit()
    session.refresh(item)
    return item.model_dump()


class ValorMercadoIn(BaseModel):
    valor_mercado_atual: float
    data: Optional[date] = None


@router.put("/patrimonio/{item_id}/valor-mercado")
def atualizar_valor_mercado(
    item_id: int, dados: ValorMercadoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id), _: Usuario = Depends(exigir_admin),
) -> dict:
    """Registra uma nova avaliação de valor de mercado — só para patrimônio
    não depreciável (ver Patrimonio.depreciavel). Atualiza
    `data_ultima_atualizacao_valor_mercado`, que é a base do próximo cálculo
    de "quando cobrar de novo" (ver rules.patrimonio.proxima_atualizacao_valor_mercado)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    item = session.get(Patrimonio, item_id)
    if not item or (fazenda_id is not None and item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Item de patrimônio não encontrado")
    if item.depreciavel:
        raise HTTPException(status_code=400, detail="Este item deprecia normalmente — não usa valor de mercado")
    item.valor_mercado_atual = dados.valor_mercado_atual
    item.data_ultima_atualizacao_valor_mercado = dados.data or date.today()
    session.add(item)
    session.commit()
    session.refresh(item)
    return item.model_dump()


class VincularPatrimonioIn(BaseModel):
    patrimonio_id: Optional[int] = None  # None = desvincula


@router.put("/lancamentos/{numero_lancamento}/patrimonio")
def vincular_lancamento_patrimonio(
    numero_lancamento: str, dados: VincularPatrimonioIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Vincula (ou desvincula, com patrimonio_id=None) um lançamento já
    existente a um item de Patrimônio — FK de verdade (ContaGerencial.patrimonio_id),
    editável tanto por aqui (tela do lançamento) quanto pela tela de
    Patrimônio (mesmo endpoint, só troca qual lado abre o seletor)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_lancamento)
    if fazenda_id is not None:
        query = query.where(ContaGerencial.fazenda_id == fazenda_id)
    contas = session.exec(query).all()
    if not contas:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    if dados.patrimonio_id is not None:
        patrimonio = session.get(Patrimonio, dados.patrimonio_id)
        if not patrimonio or (fazenda_id is not None and patrimonio.fazenda_id != fazenda_id):
            raise HTTPException(status_code=404, detail="Item de patrimônio não encontrado")
    for conta in contas:
        conta.patrimonio_id = dados.patrimonio_id
        session.add(conta)
    session.commit()
    return {"numero_lancamento": numero_lancamento, "patrimonio_id": dados.patrimonio_id}


class PlanoManutencaoIn(BaseModel):
    frequencia_manutencao_meses: Optional[int] = None
    data_ultima_manutencao: Optional[date] = None
    # Editável manualmente — quando não vier, é recalculada a partir de
    # data_ultima_manutencao + frequência (se ambas vierem preenchidas).
    data_proxima_manutencao: Optional[date] = None
    observacao_manutencao: Optional[str] = None


@router.put("/patrimonio/{item_id}/manutencao-plano")
def atualizar_plano_manutencao(
    item_id: int,
    dados: PlanoManutencaoIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    _: Usuario = Depends(exigir_admin),
) -> dict:
    """Cadastra/edita o plano de manutenção preventiva (opcional) de um item de
    patrimônio — só periodicidade por data (ver rules/patrimonio.py). Sem
    frequência informada, `data_proxima_manutencao` só é aceita se vier
    explícita (não há como calculá-la)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    item = session.get(Patrimonio, item_id)
    if not item or (fazenda_id is not None and item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Item de patrimônio não encontrado")
    if dados.frequencia_manutencao_meses is not None and dados.frequencia_manutencao_meses <= 0:
        raise HTTPException(status_code=400, detail="Frequência da manutenção deve ser um número de meses maior que zero")

    item.frequencia_manutencao_meses = dados.frequencia_manutencao_meses
    item.data_ultima_manutencao = dados.data_ultima_manutencao
    item.observacao_manutencao = dados.observacao_manutencao
    if dados.data_proxima_manutencao:
        item.data_proxima_manutencao = dados.data_proxima_manutencao
    elif dados.data_ultima_manutencao and dados.frequencia_manutencao_meses:
        item.data_proxima_manutencao = somar_meses(dados.data_ultima_manutencao, dados.frequencia_manutencao_meses)
    else:
        item.data_proxima_manutencao = None
    session.add(item)
    session.commit()
    session.refresh(item)
    d = item.model_dump()
    d.update(status_manutencao(d))
    return d


@router.get("/patrimonio/{item_id}/manutencoes")
def listar_manutencoes(
    item_id: int,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    _: Usuario = Depends(exigir_admin),
) -> list[dict]:
    """Histórico de manutenções registradas para um item de patrimônio."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    item = session.get(Patrimonio, item_id)
    if not item or (fazenda_id is not None and item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Item de patrimônio não encontrado")
    registros = session.exec(
        select(ManutencaoPatrimonio)
        .where(ManutencaoPatrimonio.patrimonio_id == item_id)
        .order_by(ManutencaoPatrimonio.data_realizacao.desc())
    ).all()
    return [r.model_dump() for r in registros]


class ManutencaoRealizadaIn(BaseModel):
    data_realizacao: date
    descricao: Optional[str] = None
    fornecedor: Optional[str] = None
    valor: Optional[float] = None
    centro_custo: str = "Pecuária Leiteira"
    # Igual ao fluxo de Férias/13º: "pago" baixa a conta na hora; "pendente"
    # nasce em aberto (Contas a Pagar) e é quitada depois pela tela normal.
    status: str = "pago"
    data_pagamento: Optional[date] = None
    observacao: Optional[str] = None
    # Opt-out — por padrão toda manutenção paga/realizada gera o lançamento em
    # Contas a Pagar (mesmo padrão de Férias/13º/compra de animal); marque
    # False só quando a manutenção já foi paga por fora e não deve duplicar.
    gerar_conta_a_pagar: bool = True


@router.post("/patrimonio/{item_id}/manutencao", status_code=201)
def registrar_manutencao(
    item_id: int, dados: ManutencaoRealizadaIn,
    session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    _: Usuario = Depends(exigir_admin),
) -> dict:
    """
    Registra que a manutenção preventiva de um item foi paga/realizada:
    - opcionalmente gera o lançamento em Contas a Pagar (ContaGerencial),
      igual ao padrão de Férias/13º (rules/folha_rh via cadastro.py) e de
      compra/venda de animal;
    - atualiza `data_ultima_manutencao` para a data informada e recalcula
      `data_proxima_manutencao` a partir da frequência cadastrada no plano
      (quando houver) — sem frequência, a próxima data fica em aberto até o
      usuário cadastrar/editar o plano de novo.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    item = session.get(Patrimonio, item_id)
    if not item or (fazenda_id is not None and item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Item de patrimônio não encontrado")
    if dados.status not in ("pendente", "pago"):
        raise HTTPException(status_code=400, detail="Status inválido — use 'pendente' ou 'pago'")
    if dados.valor is not None and dados.valor < 0:
        raise HTTPException(status_code=400, detail="Valor da manutenção não pode ser negativo")
    if dados.gerar_conta_a_pagar and not dados.valor:
        raise HTTPException(status_code=400, detail="Informe o valor para gerar a conta a pagar (ou desmarque a opção)")

    numero_lancamento = None
    if dados.gerar_conta_a_pagar:
        numero_lancamento = _proximo_numero_lancamento(session, dados.data_realizacao.year)
        session.add(ContaGerencial(
            numero_lancamento=numero_lancamento,
            descricao=f"Manutenção preventiva — {item.nome}" + (f" ({dados.descricao})" if dados.descricao else ""),
            data_vencimento=dados.data_pagamento or dados.data_realizacao,
            data_competencia=dados.data_realizacao,
            fornecedor_cliente=dados.fornecedor,
            tipo_documento="Manutenção",
            centro_custo=mapear_centro_custo(dados.centro_custo) or dados.centro_custo,
            valor_total=dados.valor,
            parcela_num=1, parcela_total=1,
            tipo="despesa", origem="auto",
            data_pagamento=dados.data_pagamento if dados.status == "pago" else None,
            valor_pago=dados.valor if dados.status == "pago" else None,
            fazenda_id=fazenda_id,
        ))

    registro = ManutencaoPatrimonio(
        patrimonio_id=item_id, data_realizacao=dados.data_realizacao, descricao=dados.descricao,
        fornecedor=dados.fornecedor, valor=dados.valor, centro_custo=dados.centro_custo,
        status=dados.status, data_pagamento=dados.data_pagamento, observacao=dados.observacao,
        usuario_id=user.id, numero_lancamento_gerado=numero_lancamento,
        fazenda_id=fazenda_id,
    )
    session.add(registro)

    # Recalcula o plano: a manutenção realizada agora É a última; a próxima
    # só se move quando há frequência cadastrada (plano sem frequência fica
    # sem próxima data até o usuário editar o plano de novo).
    item.data_ultima_manutencao = dados.data_realizacao
    item.data_proxima_manutencao = (
        somar_meses(dados.data_realizacao, item.frequencia_manutencao_meses)
        if item.frequencia_manutencao_meses else None
    )
    session.add(item)
    session.commit()
    session.refresh(registro)
    session.refresh(item)

    d_item = item.model_dump()
    d_item.update(status_manutencao(d_item))
    return {"manutencao": registro.model_dump(), "item": d_item}


def _aprender_conta_gerencial_padrao(session: Session, fazenda_id: int | None, tipo: str, itens: list["ItemIn"]) -> None:
    """Primeira vez que um item de estoque SEM conta gerencial padrão recebe
    um lançamento, a conta escolhida na hora vira o padrão dele — do próximo
    lançamento em diante, o formulário já pré-preenche essa conta sozinho
    (ver FormFinanceiro.tsx::contaGerencialPadrao / Estoque.conta_gerencial_
    despesa_padrao|receita_padrao). Nunca sobrescreve um padrão já definido
    (manual, em Configurações > Cadastro > Estoque, ou aprendido antes)."""
    campo = "conta_gerencial_despesa_padrao" if tipo == "despesa" else "conta_gerencial_receita_padrao"
    for item in itens:
        if item.tipo_item == "servico" or not item.produto or not item.codigo_conta_gerencial:
            continue
        query = select(Estoque).where(Estoque.nome == item.produto)
        if fazenda_id is not None:
            query = query.where(Estoque.fazenda_id == fazenda_id)
        estoque_item = session.exec(query).first()
        if estoque_item is not None and getattr(estoque_item, campo) is None:
            setattr(estoque_item, campo, item.codigo_conta_gerencial)
            session.add(estoque_item)


@router.post("/lancamentos", status_code=201)
def criar_lancamento(
    dados: LancamentoIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    Cria um lançamento financeiro com um ou mais produtos/serviços (itens).
    Desconto/acréscimo ajustam o valor bruto dos itens para o valor líquido,
    que é o que efetivamente vira parcela(s). Sem data de pagamento, o
    lançamento nasce em aberto (contas a pagar/receber).
    """
    if dados.tipo not in ("receita", "despesa"):
        raise HTTPException(status_code=400, detail="tipo deve ser 'receita' ou 'despesa'")
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Informe ao menos um produto ou serviço")
    for item in dados.itens:
        if item.tipo_item is not None and item.tipo_item not in ("produto", "servico"):
            raise HTTPException(status_code=400, detail="tipo_item deve ser 'produto' ou 'servico'")

    itens_com_vale = [item for item in dados.itens if item.vale]
    if itens_com_vale:
        if dados.tipo == "receita":
            raise HTTPException(status_code=400, detail="Só item de despesa pode virar vale.")
        # Import local — cadastro pode importar financeiro, o contrário não
        # (ver §0.8: rh_folha.py/rh_contratos.py já importam deste módulo).
        # Valida TODOS os itens marcados ANTES de gravar qualquer coisa —
        # qualquer erro aqui aborta o lançamento inteiro sem criar nada.
        from fazenda.api.routers.cadastro.rh_vale_item import validar_vale_item
        item_data_vale = dados.data_emissao or dados.data_competencia or date.today()
        for item in itens_com_vale:
            validar_vale_item(session, item.valor_total, item_data_vale, item.vale, fazenda_id)

    valor_bruto = round(sum(i.valor_total for i in dados.itens), 2)
    valor_liquido = round(valor_bruto - (dados.desconto or 0) + (dados.acrescimo or 0), 2)
    if valor_liquido <= 0:
        raise HTTPException(status_code=400, detail="O valor líquido do lançamento deve ser positivo")

    ano = (dados.data_emissao or dados.data_competencia or date.today()).year
    numero_lancamento = _proximo_numero_lancamento(session, ano)
    data_competencia = dados.data_competencia or dados.data_emissao

    itens_criados = [
        LancamentoItem(
            numero_lancamento=numero_lancamento,
            tipo=dados.tipo,
            data_competencia=data_competencia,
            codigo_conta_gerencial=item.codigo_conta_gerencial,
            nome_conta_gerencial=item.nome_conta_gerencial,
            centro_custo=mapear_centro_custo(item.centro_custo) if item.centro_custo else None,
            produto=item.produto,
            tipo_item=item.tipo_item,
            descricao=item.descricao,
            quantidade=item.quantidade,
            valor_unitario=item.valor_unitario,
            valor_total=item.valor_total,
            fazenda_id=fazenda_id,
        )
        for item in dados.itens
    ]

    # Resumo p/ os relatórios legados que só olham 1 conta/descrição por linha.
    descricao_resumo = ", ".join(i.produto for i in dados.itens)[:500]
    codigo_resumo = dados.itens[0].codigo_conta_gerencial if len(dados.itens) == 1 else None

    campos_comuns = dict(
        numero_lancamento=numero_lancamento,
        codigo_conta=codigo_resumo,
        descricao=descricao_resumo,
        # Centro de custo é obrigatório em todo lançamento — quando não vier
        # preenchido (ex.: CSV/robô sem esse campo), assume "Pecuária Leiteira"
        # (perfil típico da fazenda) em vez de deixar a conta sem centro,
        # sempre editável depois em Financeiro.
        centro_custo=mapear_centro_custo(dados.centro_custo) or "Pecuária Leiteira",
        classificacao=dados.classificacao,
        fornecedor_cliente=dados.fornecedor_cliente,
        responsavel=dados.responsavel,
        tipo_documento=dados.tipo_documento,
        numero_nota=dados.numero_documento,
        numero_os_orcamento=dados.numero_os_orcamento,
        data_emissao=dados.data_emissao,
        data_competencia=data_competencia,
        data_prevista_entrada=dados.data_prevista_entrada,
        data_pedido=dados.data_pedido,
        entregue=dados.entregue,
        tipo=dados.tipo,
        origem="manual",
        desconto_nota=dados.desconto or None,
        acrescimo_nota=dados.acrescimo or None,
        pedido_id=dados.pedido_id,
        # Alguns fluxos (importação de CSV, lançamento via Telegram) chamam esta
        # função diretamente, fora do ciclo de requisição do FastAPI — nesses
        # casos `user` não é resolvido pela injeção de dependência e chega aqui
        # como o próprio sentinel Depends(...), não uma instância de Usuario.
        usuario_id=user.id if isinstance(user, Usuario) else None,
        fazenda_id=fazenda_id,
    )

    criados: list[ContaGerencial] = []
    if dados.parcelas:
        # A soma das parcelas precisa bater com o valor líquido da nota — sem
        # essa checagem, um valor digitado errado nas parcelas gera uma nota
        # onde o total por item (usado em DRE/RMCA) diverge permanentemente
        # do total em Contas a Pagar/fluxo de caixa (que soma as parcelas).
        # Mesmo padrão já usado em pagar_lancamento (parcelas_diferenca).
        soma_parcelas = round(sum(p.valor for p in dados.parcelas), 2)
        if round(soma_parcelas - valor_liquido, 2) != 0:
            raise HTTPException(status_code=400, detail="A soma das parcelas precisa bater com o valor líquido do lançamento")
        total_parcelas = len(dados.parcelas)
        for i, p in enumerate(dados.parcelas, start=1):
            # Regra do boleto no nível do lançamento (item 4): se o usuário
            # preencheu dados.numero_boleto E parcelou, ele vale como boleto
            # da 1ª parcela — nunca duplicado nas demais. Se a própria 1ª
            # parcela já veio com numero_boleto (o front já faz essa migração
            # antes de enviar), não sobrescreve.
            numero_boleto = p.numero_boleto
            if i == 1 and not numero_boleto and dados.numero_boleto:
                numero_boleto = dados.numero_boleto
            conta = ContaGerencial(
                **campos_comuns,
                data_vencimento=p.data_vencimento,
                valor_total=p.valor,
                parcela_num=i,
                parcela_total=total_parcelas,
                numero_boleto=numero_boleto,
            )
            if p.data_pagamento:
                conta.data_pagamento = p.data_pagamento
                conta.valor_pago = p.valor_pago
                conta.conta_bancaria = p.conta_bancaria
                conta.numero_documento_pagamento = p.numero_documento_pagamento
                conta.forma_pagamento = p.forma_pagamento
                conta.desconto_acrescimo = round((p.valor_pago or 0) - p.valor, 2)
            criados.append(conta)
    else:
        registro = ContaGerencial(
            **campos_comuns,
            # Vencimento explícito do lançamento; se não vier, cai na data
            # prevista de entrada (comportamento antigo) e, por fim, na emissão.
            data_vencimento=dados.data_vencimento or dados.data_prevista_entrada or dados.data_emissao,
            valor_total=valor_liquido,
            parcela_num=1,
            parcela_total=1,
            numero_boleto=dados.numero_boleto,
        )
        if dados.data_pagamento:
            registro.data_pagamento = dados.data_pagamento
            registro.valor_pago = dados.valor_pago
            registro.conta_bancaria = dados.conta_bancaria
            registro.numero_documento_pagamento = dados.numero_documento_pagamento
            registro.forma_pagamento = dados.forma_pagamento
            registro.desconto_acrescimo = round((dados.valor_pago or 0) - valor_liquido, 2)
        criados.append(registro)

    for it in itens_criados:
        session.add(it)
    for c in criados:
        session.add(c)
    session.commit()
    for c in criados:
        session.refresh(c)
    for it in itens_criados:
        session.refresh(it)

    _aprender_conta_gerencial_padrao(session, fazenda_id, dados.tipo, dados.itens)
    session.commit()

    if dados.pedido_id:
        from fazenda.api.routers.pedidos import atualizar_status_por_lancamento
        atualizar_status_por_lancamento(session, dados.pedido_id, valor_liquido)

    if dados.criar_patrimonio:
        pat = dados.criar_patrimonio
        item_patrimonio = Patrimonio(
            **pat.model_dump(exclude={"nome"}), nome=pat.nome.strip(), fazenda_id=fazenda_id,
        )
        if not item_patrimonio.depreciavel and item_patrimonio.valor_mercado_atual is None:
            item_patrimonio.valor_mercado_atual = item_patrimonio.valor_total
        session.add(item_patrimonio)
        session.commit()
        session.refresh(item_patrimonio)
        for c in criados:
            c.patrimonio_id = item_patrimonio.id
            session.add(c)
        session.commit()

    # Itens marcados como vale (checkbox "É vale de funcionário?") já
    # passaram por `validar_vale_item` acima, ANTES de gravar nada — aqui só
    # cria o vale de verdade (ValeFuncionario/ValeAvulso) reaproveitando
    # criar_vale/criar_vale_avulso e grava o vínculo no item (ver
    # fazenda/api/routers/cadastro/rh_vale_item.py).
    vales_criados: list[dict] = []
    if itens_com_vale:
        from fazenda.api.routers.cadastro.rh_vale_item import aplicar_vale_item
        try:
            for item_in, item_criado in zip(dados.itens, itens_criados):
                if not item_in.vale:
                    continue
                pessoa_vale = session.get(Pessoa, item_in.vale.pessoa_id)
                resultado = aplicar_vale_item(session, item_criado, item_in.vale, user, fazenda_id)
                vales_criados.append({
                    "item_id": item_criado.id,
                    "vale_tipo": resultado["vale_tipo"],
                    "vale_id": resultado["vale_id"],
                    "pessoa_nome": pessoa_vale.nome if pessoa_vale else None,
                    "valor": item_criado.valor_total,
                })
        except HTTPException:
            # Corrida rara (passou em validar_vale_item mas falhou de
            # verdade ao aplicar — ex.: 40% do salário estourado por outro
            # vale lançado nesse meio-tempo). A nota já foi commitada acima
            # — desfaz por completo em vez de deixar uma nota "meio vale".
            for it in itens_criados:
                session.delete(it)
            for c in criados:
                session.delete(c)
            session.commit()
            raise

    # Compra de produto estocável dá entrada automática no estoque — só para
    # despesa e só quando NÃO está vinculada a um Pedido (nesse caso a
    # entrada física já é lançada manualmente via POST /estoque/movimentar
    # quando a mercadoria chega; dar entrada aqui também duplicaria a
    # contagem). Item não-estocável (financeiro puro): melhor esforço, segue
    # sem aviso (comportamento intencional). Item NÃO encontrado no estoque
    # cadastrado (nome digitado em "texto livre" ou fora do cadastro): antes
    # o `continue` abaixo pulava em silêncio — a nota fiscal salvava normal e
    # ninguém percebia que o produto nunca deu entrada no estoque (foi o que
    # aconteceu com sêmen comprado por nome de touro ainda não cadastrado).
    # Agora sempre passa por `movimentar()`, que já sabe gerar o aviso
    # "não está no estoque desta fazenda" quando `item` vem None.
    avisos_estoque: list[str] = []
    if dados.tipo == "despesa" and dados.pedido_id is None:
        data_movimento = dados.data_emissao or data_competencia or date.today()
        usuario_id = user.id if isinstance(user, Usuario) else None
        for item_in, item_criado in zip(dados.itens, itens_criados):
            if item_in.vale:
                # Ração do cachorro do funcionário não é estoque da fazenda.
                continue
            if item_in.tipo_item != "produto" or not item_in.quantidade or item_in.quantidade <= 0:
                continue
            estoque_item = estoque_baixa.resolver_item(session, fazenda_id=fazenda_id, produto=item_in.produto)
            if estoque_item is not None and estoque_item.estocavel is False:
                continue
            avisos_estoque += estoque_baixa.movimentar(
                session, item=estoque_item, quantidade=item_in.quantidade,
                unidade=estoque_item.unidade if estoque_item else None,
                data=data_movimento, fazenda_id=fazenda_id, movimento="Entrada de compra",
                observacao=f"Entrada por compra — lançamento {numero_lancamento}",
                usuario_id=usuario_id, origem_tipo="compra_financeiro", origem_id=item_criado.id, sinal=+1,
                produto=item_in.produto,
            )
        session.commit()

    return {
        "numero_lancamento": numero_lancamento,
        "ids": [c.id for c in criados],
        "valor_bruto": valor_bruto,
        "valor_liquido": valor_liquido,
        "avisos_estoque": avisos_estoque,
        "vales_criados": vales_criados,
    }


# ---------------------------------------------------------------------------
# Lançamentos recorrentes (Financeiro > Ações > Lançamentos recorrentes) —
# "modelo" com os dados FIXOS de uma conta que se repete todo período (ex.:
# energia, internet, telefone, assinatura, aluguel): fornecedor, conta
# gerencial, centro de custo, forma de pagamento/conta bancária padrão e dia
# de vencimento típico (ver LancamentoRecorrente em models/financeiro.py).
#
# A cada período, o usuário só entra com os dados VARIÁVEIS (valor da fatura,
# data de emissão real, boleto daquele mês) em POST .../gerar, que MONTA um
# LancamentoIn a partir do modelo + desses dados variáveis e chama
# `criar_lancamento` de novo — a mesma função usada pelo formulário manual,
# pelo XML e pelo Telegram — para não duplicar nada da regra de criação
# (numeração, item, entrada de estoque etc.). O lançamento gerado nasce em
# aberto (contas a pagar/receber), a menos que o usuário marque `ja_pago`.
#
# FORA de escopo desta feature (proposital — ver tarefa original): nenhuma
# geração automática por agendador/cron todo mês, nem lembrete "hora de
# gerar" — o usuário sempre aciona "Gerar lançamento deste período" na tela.
# ---------------------------------------------------------------------------
PERIODICIDADES_ACEITAS = ["mensal"]


class LancamentoRecorrenteIn(BaseModel):
    descricao: str
    tipo: str  # "receita" | "despesa"
    fornecedor_cliente: Optional[str] = None
    centro_custo: Optional[str] = None
    codigo_conta_gerencial: Optional[str] = None
    nome_conta_gerencial: Optional[str] = None
    tipo_item: Optional[str] = None  # "produto" | "servico"
    responsavel_padrao: Optional[str] = None
    tipo_documento_padrao: Optional[str] = None
    forma_pagamento_padrao: Optional[str] = None
    conta_bancaria_padrao: Optional[str] = None
    dia_vencimento: Optional[int] = None
    periodicidade: str = "mensal"
    observacao: Optional[str] = None
    ativo: bool = True


def _validar_lancamento_recorrente(dados: LancamentoRecorrenteIn) -> None:
    if not dados.descricao.strip():
        raise HTTPException(status_code=400, detail="Descrição é obrigatória")
    if dados.tipo not in ("receita", "despesa"):
        raise HTTPException(status_code=400, detail="tipo deve ser 'receita' ou 'despesa'")
    if dados.periodicidade not in PERIODICIDADES_ACEITAS:
        raise HTTPException(status_code=400, detail=f"periodicidade deve ser uma de: {', '.join(PERIODICIDADES_ACEITAS)}")
    if dados.dia_vencimento is not None and not (1 <= dados.dia_vencimento <= 31):
        raise HTTPException(status_code=400, detail="dia_vencimento deve estar entre 1 e 31")
    if dados.tipo_item is not None and dados.tipo_item not in ("produto", "servico"):
        raise HTTPException(status_code=400, detail="tipo_item deve ser 'produto' ou 'servico'")


@router.get("/recorrentes")
def listar_lancamentos_recorrentes(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(LancamentoRecorrente)
    if fazenda_id is not None:
        query = query.where(LancamentoRecorrente.fazenda_id == fazenda_id)
    itens = session.exec(query.order_by(LancamentoRecorrente.descricao)).all()
    return [i.model_dump() for i in itens]


@router.post("/recorrentes", status_code=201)
def criar_lancamento_recorrente(
    dados: LancamentoRecorrenteIn, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    _validar_lancamento_recorrente(dados)
    modelo = LancamentoRecorrente(
        **dados.model_dump(),
        fazenda_id=fazenda_id,
        usuario_id=user.id if isinstance(user, Usuario) else None,
    )
    session.add(modelo)
    session.commit()
    session.refresh(modelo)
    return modelo.model_dump()


@router.put("/recorrentes/{modelo_id}")
def atualizar_lancamento_recorrente(
    modelo_id: int, dados: LancamentoRecorrenteIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    modelo = session.get(LancamentoRecorrente, modelo_id)
    if not modelo or (fazenda_id is not None and modelo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Lançamento recorrente não encontrado")
    _validar_lancamento_recorrente(dados)
    for campo, valor in dados.model_dump().items():
        setattr(modelo, campo, valor)
    modelo.atualizado_em = datetime.utcnow()
    session.add(modelo)
    session.commit()
    session.refresh(modelo)
    return modelo.model_dump()


def _vencimento_do_periodo(dia_vencimento: int | None, referencia: date) -> date | None:
    """Vencimento típico do modelo no mês/ano de `referencia` — dia além do
    fim do mês é ajustado para o último dia (ex.: 31 em fevereiro vira 28/29)."""
    if not dia_vencimento:
        return None
    ultimo_dia = calendar.monthrange(referencia.year, referencia.month)[1]
    return date(referencia.year, referencia.month, min(dia_vencimento, ultimo_dia))


class GerarLancamentoRecorrenteIn(BaseModel):
    """Só os dados VARIÁVEIS de um período — todo o resto (fornecedor, conta
    gerencial, centro de custo, forma de pagamento/conta bancária padrão)
    vem do modelo (LancamentoRecorrente) indicado na URL."""
    valor: float
    data_emissao: Optional[date] = None
    # Se não vier, calculado a partir de dia_vencimento do modelo + o mês de
    # data_emissao (ou de hoje, sem data_emissao).
    data_vencimento: Optional[date] = None
    numero_boleto: Optional[str] = None
    numero_documento: Optional[str] = None
    # Observação específica deste período (ex.: "leitura 1234 kWh").
    observacao: Optional[str] = None
    # Nasce já pago/recebido (ex.: assinatura debitada automaticamente no
    # cartão) — usa forma/conta padrão do modelo quando não vier override.
    ja_pago: bool = False
    data_pagamento: Optional[date] = None
    valor_pago: Optional[float] = None
    conta_bancaria: Optional[str] = None
    forma_pagamento: Optional[str] = None
    numero_documento_pagamento: Optional[str] = None


@router.post("/recorrentes/{modelo_id}/gerar", status_code=201)
def gerar_lancamento_recorrente(
    modelo_id: int, dados: GerarLancamentoRecorrenteIn, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Gera um lançamento financeiro de verdade (ContaGerencial + LancamentoItem,
    igual a qualquer outro) a partir de um modelo recorrente + os dados
    variáveis deste período — reaproveita `criar_lancamento`, sem duplicar
    nenhuma regra de criação (numeração, estoque, etc.)."""
    modelo = session.get(LancamentoRecorrente, modelo_id)
    if not modelo or (fazenda_id is not None and modelo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Lançamento recorrente não encontrado")
    if dados.valor <= 0:
        raise HTTPException(status_code=400, detail="O valor deve ser positivo")

    data_emissao = dados.data_emissao or date.today()
    data_vencimento = dados.data_vencimento or _vencimento_do_periodo(modelo.dia_vencimento, data_emissao)

    item = ItemIn(
        codigo_conta_gerencial=modelo.codigo_conta_gerencial,
        nome_conta_gerencial=modelo.nome_conta_gerencial,
        produto=modelo.descricao,
        tipo_item=modelo.tipo_item,
        descricao=dados.observacao,
        valor_total=dados.valor,
    )
    ja_pago = dados.ja_pago or dados.data_pagamento is not None
    lanc = LancamentoIn(
        tipo=modelo.tipo,
        itens=[item],
        centro_custo=modelo.centro_custo,
        fornecedor_cliente=modelo.fornecedor_cliente,
        responsavel=modelo.responsavel_padrao,
        tipo_documento=modelo.tipo_documento_padrao,
        numero_documento=dados.numero_documento,
        data_emissao=data_emissao,
        data_vencimento=data_vencimento,
        numero_boleto=dados.numero_boleto,
        data_pagamento=dados.data_pagamento if ja_pago else None,
        valor_pago=(dados.valor_pago if dados.valor_pago is not None else dados.valor) if ja_pago else None,
        conta_bancaria=(dados.conta_bancaria or modelo.conta_bancaria_padrao) if ja_pago else None,
        forma_pagamento=(dados.forma_pagamento or modelo.forma_pagamento_padrao) if ja_pago else None,
        numero_documento_pagamento=dados.numero_documento_pagamento if ja_pago else None,
    )
    resultado = criar_lancamento(dados=lanc, session=session, user=user, fazenda_id=fazenda_id)

    modelo.ultimo_numero_lancamento = resultado["numero_lancamento"]
    modelo.ultima_geracao_em = date.today()
    modelo.atualizado_em = datetime.utcnow()
    session.add(modelo)
    session.commit()

    return resultado


class LancamentoEditIn(BaseModel):
    """Edição dos campos descritivos/de valor de UMA conta gerencial (parcela).

    Todos os campos são opcionais — só os enviados são atualizados. Campos de
    pagamento (data_pagamento/valor_pago) não entram aqui: editar é
    independente de dar baixa, e uma conta já paga/recebida pode ser editada.
    """
    descricao: Optional[str] = None
    codigo_conta: Optional[str] = None
    centro_custo: Optional[str] = None
    classificacao: Optional[str] = None
    fornecedor_cliente: Optional[str] = None
    numero_nota: Optional[str] = None
    numero_os_orcamento: Optional[str] = None
    numero_boleto: Optional[str] = None
    numero_documento_pagamento: Optional[str] = None
    tipo_documento: Optional[str] = None
    data_emissao: Optional[date] = None
    data_vencimento: Optional[date] = None
    data_competencia: Optional[date] = None
    data_prevista_entrada: Optional[date] = None
    data_pedido: Optional[date] = None
    quantidade: Optional[float] = None
    valor_unitario: Optional[float] = None
    valor_total: Optional[float] = None
    desconto_acrescimo: Optional[float] = None
    responsavel: Optional[str] = None
    # Produto/serviço do item — não é campo da conta gerencial em si, é
    # espelhado no(s) LancamentoItem abaixo (ver editar_lancamento).
    produto: Optional[str] = None


@router.put("/lancamentos/{lancamento_id}/pagar")
def pagar_lancamento(
    lancamento_id: int, dados: PagamentoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Dá baixa (marca como pago/recebido) numa conta a pagar/a receber."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    registro = session.get(ContaGerencial, lancamento_id)
    if not registro or (fazenda_id is not None and registro.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")

    if dados.forma_pagamento == "credito" and not dados.data_vencimento_cartao:
        raise HTTPException(status_code=400, detail="Informe a data de vencimento do cartão")

    diferenca = round(dados.valor_pago - (registro.valor_total or 0), 2)
    if dados.parcelas_diferenca:
        if not registro.numero_lancamento:
            raise HTTPException(
                status_code=400,
                detail="Este lançamento não tem um número de lançamento válido para parcelar a diferença — use desconto/acréscimo.",
            )
        soma_parcelas = round(sum(p.valor for p in dados.parcelas_diferenca), 2)
        if round(soma_parcelas - abs(diferenca), 2) != 0:
            raise HTTPException(status_code=400, detail="A soma das parcelas precisa bater com a diferença a parcelar")

    registro.data_pagamento = dados.data_pagamento
    registro.valor_pago = dados.valor_pago
    registro.conta_bancaria = dados.conta_bancaria
    registro.numero_documento_pagamento = dados.numero_documento_pagamento
    registro.forma_pagamento = dados.forma_pagamento
    registro.data_vencimento_cartao = dados.data_vencimento_cartao if dados.forma_pagamento == "credito" else None
    # Com parcelas_diferenca, a diferença inteira migra para as novas
    # parcelas abaixo — esta baixa não perdoa nem cobra nada sozinha.
    registro.desconto_acrescimo = 0 if dados.parcelas_diferenca else diferenca
    session.add(registro)

    novas: list[ContaGerencial] = []
    if dados.parcelas_diferenca:
        parcela_total_atual = registro.parcela_total or 1
        novo_total = parcela_total_atual + len(dados.parcelas_diferenca)
        # Reabre a contagem de parcelas do lançamento inteiro — todas as
        # linhas (já existentes e novas) passam a refletir o novo total.
        query_irmas = select(ContaGerencial).where(ContaGerencial.numero_lancamento == registro.numero_lancamento)
        if registro.fazenda_id is not None:
            query_irmas = query_irmas.where(ContaGerencial.fazenda_id == registro.fazenda_id)
        for irma in session.exec(query_irmas).all():
            irma.parcela_total = novo_total
            session.add(irma)
        for i, p in enumerate(dados.parcelas_diferenca, start=parcela_total_atual + 1):
            nova = ContaGerencial(
                fazenda_id=registro.fazenda_id,
                numero_lancamento=registro.numero_lancamento,
                codigo_conta=registro.codigo_conta,
                descricao=registro.descricao,
                data_vencimento=p.data_vencimento,
                data_competencia=registro.data_competencia,
                data_emissao=registro.data_emissao,
                fornecedor_cliente=registro.fornecedor_cliente,
                numero_nota=registro.numero_nota,
                tipo_documento=registro.tipo_documento,
                numero_os_orcamento=registro.numero_os_orcamento,
                valor_total=p.valor,
                parcela_num=i,
                parcela_total=novo_total,
                responsavel=registro.responsavel,
                centro_custo=registro.centro_custo,
                tipo=registro.tipo,
                origem="manual",
                usuario_id=registro.usuario_id,
            )
            novas.append(nova)
            session.add(nova)

    session.commit()
    session.refresh(registro)
    for nova in novas:
        session.refresh(nova)
    return {**registro.model_dump(), "parcelas_diferenca_criadas": [n.model_dump() for n in novas]}


@router.put("/lancamentos/baixa-lote")
def baixa_lote(
    dados: BaixaLoteIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Dá baixa em vários lançamentos de uma vez, todos com o mesmo pagamento
    (data, conta corrente, forma de pagamento e nº de comprovante único) —
    cada lançamento é pago pelo próprio valor_total (sem desconto/acréscimo
    na baixa em lote; use a baixa individual para isso).
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not dados.lancamento_ids:
        raise HTTPException(status_code=400, detail="Selecione ao menos um lançamento")
    if dados.forma_pagamento == "credito" and not dados.data_vencimento_cartao:
        raise HTTPException(status_code=400, detail="Informe a data de vencimento do cartão")

    baixados = []
    nao_encontrados = []
    for lancamento_id in dados.lancamento_ids:
        registro = session.get(ContaGerencial, lancamento_id)
        if not registro or (fazenda_id is not None and registro.fazenda_id != fazenda_id):
            nao_encontrados.append(lancamento_id)
            continue
        registro.data_pagamento = dados.data_pagamento
        registro.valor_pago = registro.valor_total
        registro.desconto_acrescimo = 0.0
        registro.conta_bancaria = dados.conta_bancaria
        registro.forma_pagamento = dados.forma_pagamento
        registro.data_vencimento_cartao = dados.data_vencimento_cartao if dados.forma_pagamento == "credito" else None
        registro.numero_documento_pagamento = dados.numero_documento_pagamento
        session.add(registro)
        baixados.append(lancamento_id)

    session.commit()
    return {"baixados": len(baixados), "nao_encontrados": nao_encontrados}


@router.put("/lancamentos/baixa-lote-detalhada")
def baixa_lote_detalhada(
    dados: BaixaLoteDetalhadaIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Dá baixa em várias notas de uma vez, mas cada uma com o SEU próprio
    pagamento (data, valor, conta, forma e comprovante) — permite pagar cada
    conta de forma diferente numa única operação. Valor diferente do total vira
    desconto/acréscimo (como na baixa individual).
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Selecione ao menos um lançamento")
    for it in dados.itens:
        if it.forma_pagamento == "credito" and not it.data_vencimento_cartao:
            raise HTTPException(status_code=400, detail=f"Informe o vencimento do cartão do lançamento {it.lancamento_id}")

    baixados = []
    nao_encontrados = []
    for it in dados.itens:
        registro = session.get(ContaGerencial, it.lancamento_id)
        if not registro or (fazenda_id is not None and registro.fazenda_id != fazenda_id):
            nao_encontrados.append(it.lancamento_id)
            continue
        registro.data_pagamento = it.data_pagamento
        registro.valor_pago = it.valor_pago
        registro.desconto_acrescimo = round(it.valor_pago - (registro.valor_total or 0), 2)
        registro.conta_bancaria = it.conta_bancaria
        registro.forma_pagamento = it.forma_pagamento
        registro.data_vencimento_cartao = it.data_vencimento_cartao if it.forma_pagamento == "credito" else None
        registro.numero_documento_pagamento = it.numero_documento_pagamento
        session.add(registro)
        baixados.append(it.lancamento_id)

    session.commit()
    return {"baixados": len(baixados), "nao_encontrados": nao_encontrados}


# Definido DEPOIS de /baixa-lote de propósito: uma rota de segmento único como
# /lancamentos/{lancamento_id} capturaria "baixa-lote" e quebraria aquela rota.
@router.put("/lancamentos/{lancamento_id}")
def editar_lancamento(
    lancamento_id: int, dados: LancamentoEditIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Edita os campos descritivos/de valor de UMA conta gerencial (uma parcela),
    identificada pelo seu id. Não mexe no pagamento — uma conta já paga/recebida
    também pode ser editada. Quando o lançamento é de parcela única e tem
    exatamente um item, espelha as mudanças no LancamentoItem para manter os
    relatórios por item (DRE/RMCA) coerentes.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    registro = session.get(ContaGerencial, lancamento_id)
    if not registro or (fazenda_id is not None and registro.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")

    enviados = dados.model_dump(exclude_unset=True)
    produto_novo = enviados.pop("produto", None)
    for campo, valor in enviados.items():
        if campo == "centro_custo":
            registro.centro_custo = mapear_centro_custo(valor)
        else:
            setattr(registro, campo, valor)
    registro.atualizado_em = datetime.utcnow()
    session.add(registro)

    # Espelha no item quando é seguro (parcela única + 1 item), para relatórios
    # baseados em LancamentoItem (DRE/RMCA) ficarem consistentes.
    if registro.parcela_total == 1 and registro.numero_lancamento:
        itens = session.exec(
            select(LancamentoItem).where(LancamentoItem.numero_lancamento == registro.numero_lancamento)
        ).all()
        if len(itens) == 1:
            item = itens[0]
            # Este item já virou um vale de verdade (ValeFuncionario/ValeAvulso)
            # com valor próprio — mudar o valor da nota por aqui deixaria o
            # item e o vale divergentes em silêncio. O usuário precisa
            # desmarcar o vale primeiro (ver /cadastro/vale-item/{item_id}).
            if "valor_total" in enviados and eh_item_de_vale(item):
                raise HTTPException(
                    status_code=400,
                    detail=f"Este item gerou um vale de R$ {item.valor_total:.2f} — desmarque o vale antes de alterar o valor da nota.",
                )
            if "descricao" in enviados:
                item.descricao = registro.descricao
            if "valor_total" in enviados:
                item.valor_total = registro.valor_total
            if "quantidade" in enviados:
                quantidade_antiga = item.quantidade
                item.quantidade = registro.quantidade
                # Este item deu entrada automática no Estoque na criação (ver
                # criar_lancamento) — mudar só o número aqui deixava o Estoque
                # com a quantidade ANTIGA pra sempre. Estorna a entrada velha e
                # aplica a nova, mesmo padrão de sanidade.py::editar_aplicacao.
                if (
                    registro.tipo == "despesa" and registro.pedido_id is None
                    and item.tipo_item == "produto" and not eh_item_de_vale(item)
                    and quantidade_antiga != registro.quantidade
                ):
                    entrada_existente = session.exec(
                        select(MovimentoEstoque).where(
                            MovimentoEstoque.origem_tipo == "compra_financeiro",
                            MovimentoEstoque.origem_id == item.id,
                        )
                    ).first()
                    if entrada_existente is not None:
                        estoque_item = estoque_baixa.resolver_item(session, fazenda_id=fazenda_id, produto=item.produto)
                        unidade_item = estoque_item.unidade if estoque_item else entrada_existente.unidade
                        estoque_baixa.movimentar(
                            session, item=estoque_item, quantidade=quantidade_antiga or 0, unidade=unidade_item,
                            data=date.today(), fazenda_id=fazenda_id, movimento="Saída de ajuste",
                            observacao=f"Estorno por edição de quantidade — lançamento {registro.numero_lancamento}",
                            origem_tipo="compra_financeiro", origem_id=item.id, sinal=-1, produto=item.produto,
                        )
                        estoque_baixa.movimentar(
                            session, item=estoque_item, quantidade=registro.quantidade or 0, unidade=unidade_item,
                            data=date.today(), fazenda_id=fazenda_id, movimento="Entrada de ajuste",
                            observacao=f"Ajuste de quantidade editada — lançamento {registro.numero_lancamento}",
                            origem_tipo="compra_financeiro", origem_id=item.id, sinal=+1, produto=item.produto,
                        )
            if "valor_unitario" in enviados:
                item.valor_unitario = registro.valor_unitario
            if "codigo_conta" in enviados:
                item.codigo_conta_gerencial = registro.codigo_conta
            session.add(item)

    # Produto/serviço vinculado — independe de parcela_total, já que os itens
    # de um lançamento são compartilhados por todas as parcelas (mesmo
    # numero_lancamento). Lançamentos importados sem nenhum item (o caso mais
    # comum de "falta produto") ganham um item novo aqui; lançamentos com
    # exatamente 1 item têm o produto desse item trocado. Notas com múltiplos
    # itens não são tratadas aqui — o vínculo é ambíguo (qual item mudar?).
    if produto_novo is not None and registro.numero_lancamento:
        itens_produto = session.exec(
            select(LancamentoItem).where(LancamentoItem.numero_lancamento == registro.numero_lancamento)
        ).all()
        if len(itens_produto) == 1:
            itens_produto[0].produto = produto_novo
            session.add(itens_produto[0])
        elif len(itens_produto) == 0:
            session.add(LancamentoItem(
                numero_lancamento=registro.numero_lancamento,
                tipo=registro.tipo,
                data_competencia=registro.data_competencia,
                codigo_conta_gerencial=registro.codigo_conta,
                produto=produto_novo,
                quantidade=registro.quantidade,
                valor_unitario=registro.valor_unitario,
                valor_total=registro.valor_total or 0,
            ))
        else:
            raise HTTPException(
                status_code=400,
                detail="Este lançamento tem múltiplos produtos/serviços — não é possível trocar por aqui.",
            )

    session.commit()
    session.refresh(registro)
    return registro.model_dump()


class ItemVincularIn(BaseModel):
    produto: str


@router.put("/itens/{item_id}/vincular-produto")
def vincular_produto_item(
    item_id: int, dados: ItemVincularIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id), user=Depends(get_current_user),
) -> dict:
    """
    Renomeia/associa o produto/serviço de UM item já lançado (LancamentoItem)
    a um nome do catálogo — usado tanto para "associar a produto já
    existente" quanto para o passo seguinte a "cadastrar produto novo" na
    tela de edição (ver FormEditarLancamento). Diferente de PUT
    /lancamentos/{id} (que só edita o produto quando a nota tem exatamente 1
    item), este mexe no item certo mesmo em notas com vários itens.

    Quando o item é um PRODUTO de estoque, não é vale, tem quantidade > 0 e
    ainda não gerou nenhuma entrada de estoque (o caso comum: item veio de
    XML/OCR sem bater com nada do cadastro — na criação do lançamento
    `estoque_baixa.movimentar` não achou o item e só avisou, sem baixar) —
    dá entrada retroativa agora que o produto finalmente tem um Estoque
    correspondente. Mesma regra "só quando NÃO vinculado a Pedido" da
    criação (ver criar_lancamento), pra não duplicar a entrada física.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    item = session.get(LancamentoItem, item_id)
    if not item or (fazenda_id is not None and item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Item não encontrado")

    nome = dados.produto.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    item.produto = nome
    item.atualizado_em = datetime.utcnow()
    session.add(item)

    avisos_estoque: list[str] = []
    ja_deu_entrada = session.exec(
        select(MovimentoEstoque).where(
            MovimentoEstoque.origem_tipo == "compra_financeiro", MovimentoEstoque.origem_id == item.id,
        )
    ).first() is not None
    if item.tipo_item == "produto" and not eh_item_de_vale(item) and item.quantidade and item.quantidade > 0 and not ja_deu_entrada:
        query_conta = select(ContaGerencial).where(ContaGerencial.numero_lancamento == item.numero_lancamento)
        if fazenda_id is not None:
            query_conta = query_conta.where(ContaGerencial.fazenda_id == fazenda_id)
        conta = session.exec(query_conta).first()
        if conta is not None and conta.tipo == "despesa" and conta.pedido_id is None:
            estoque_item = estoque_baixa.resolver_item(session, fazenda_id=fazenda_id, produto=nome)
            if estoque_item is not None and estoque_item.estocavel is not False:
                data_movimento = conta.data_emissao or conta.data_competencia or date.today()
                avisos_estoque += estoque_baixa.movimentar(
                    session, item=estoque_item, quantidade=item.quantidade,
                    unidade=estoque_item.unidade, data=data_movimento, fazenda_id=fazenda_id,
                    movimento="Entrada de compra", observacao=f"Entrada por compra — lançamento {item.numero_lancamento}",
                    usuario_id=user.id if isinstance(user, Usuario) else None,
                    origem_tipo="compra_financeiro", origem_id=item.id, sinal=+1, produto=nome,
                )

    session.commit()
    session.refresh(item)
    return {**item.model_dump(), "avisos_estoque": avisos_estoque}


# G2 — `ContaGerencial` que NASCEM já pagas, espelhando a baixa de outro
# módulo (RH). Estorná-las por aqui deixaria as duas pontas divergentes —
# desfazer precisa ser feito no módulo de origem. Ver
# `rh_folha._sincronizar_conta_vale` (Vale de funcionário),
# `rh_contratos.registrar_pagamento_diaria` (Diária) e o lançamento de Vale
# avulso (também rh_contratos).
TIPOS_DOCUMENTO_BAIXA_ESPELHADA = {"Vale de funcionário", "Vale avulso", "Diária"}


class EstornoIn(BaseModel):
    motivo: str | None = None
    # Sem isso, uma baixa que criou parcela(s) para cobrir a diferença de
    # valor pago (ver `pagar_lancamento` acima) é bloqueada com 409 — o
    # chamador precisa confirmar explicitamente que quer removê-las também.
    confirmar_parcelas_diferenca: bool = False


@router.post("/lancamentos/{lancamento_id}/estornar")
def estornar_lancamento(
    lancamento_id: int, dados: EstornoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Reverte a baixa (pagamento/recebimento) de um lançamento — o lançamento
    CONTINUA existindo, só volta para "em aberto" (contas a pagar/receber).
    Não é exclusão: para excluir o lançamento em si, use o motor genérico
    (`POST /exclusoes/...`, tipo "financeiro").
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    registro = session.get(ContaGerencial, lancamento_id)
    if not registro or (fazenda_id is not None and registro.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")

    if registro.data_pagamento is None and registro.valor_pago is None:
        raise HTTPException(status_code=400, detail="Este lançamento não está baixado — não há pagamento a estornar.")

    if registro.tipo_documento in TIPOS_DOCUMENTO_BAIXA_ESPELHADA:
        raise HTTPException(
            status_code=400,
            detail=f"Este lançamento é o espelho de um {registro.tipo_documento} — desfaça no próprio módulo "
            "(Financeiro › Folha › Vales / Pessoal › Diárias), senão os dois ficam divergentes.",
        )

    # Parcelas geradas pela diferença de valor pago (`pagar_lancamento`,
    # `dados.parcelas_diferenca`) — mesmo `numero_lancamento`, número maior
    # que a parcela baixada, ainda em aberto, lançadas manualmente. Não há
    # `criado_em` em `ContaGerencial` (só `atualizado_em`) para distinguir
    # com certeza dessas parcelas "de diferença" de parcelas futuras comuns
    # do mesmo lançamento que só ainda não foram pagas — usamos
    # `atualizado_em >= registro.atualizado_em` como aproximação: as
    # parcelas de diferença são criadas no momento da baixa, estritamente
    # depois da criação da parcela que está sendo baixada agora.
    irmas_diferenca: list[ContaGerencial] = []
    if registro.numero_lancamento and registro.parcela_num is not None:
        query_irmas = select(ContaGerencial).where(
            ContaGerencial.numero_lancamento == registro.numero_lancamento,
            ContaGerencial.parcela_num > registro.parcela_num,
            ContaGerencial.valor_pago.is_(None),
            ContaGerencial.origem == "manual",
        )
        if registro.fazenda_id is not None:
            query_irmas = query_irmas.where(ContaGerencial.fazenda_id == registro.fazenda_id)
        irmas_diferenca = [
            c for c in session.exec(query_irmas).all()
            if c.atualizado_em is not None and registro.atualizado_em is not None
            and c.atualizado_em >= registro.atualizado_em
        ]

    if irmas_diferenca and not dados.confirmar_parcelas_diferenca:
        raise HTTPException(
            status_code=409,
            detail={
                "mensagem": f"Esta baixa criou {len(irmas_diferenca)} parcela(s) para a diferença. "
                "Estornar sem removê-las deixa o lançamento com valor duplicado.",
                # `mode="json"` — o `detail` de HTTPException não passa pelo
                # `jsonable_encoder` de resposta normal do FastAPI, então
                # `date`/`datetime` cru quebrariam o `json.dumps` da resposta.
                "parcelas": [c.model_dump(mode="json") for c in irmas_diferenca],
            },
        )

    avisos: list[str] = []
    if registro.forma_pagamento == "credito":
        avisos.append("O pagamento estornado era em cartão de crédito — confira/ajuste a fatura manualmente.")

    parcelas_diferenca_removidas = 0
    if irmas_diferenca:
        ids_removidas = {c.id for c in irmas_diferenca}
        for c in irmas_diferenca:
            session.delete(c)
        parcelas_diferenca_removidas = len(irmas_diferenca)

        query_restantes = select(ContaGerencial).where(ContaGerencial.numero_lancamento == registro.numero_lancamento)
        if registro.fazenda_id is not None:
            query_restantes = query_restantes.where(ContaGerencial.fazenda_id == registro.fazenda_id)
        remanescentes = [c for c in session.exec(query_restantes).all() if c.id not in ids_removidas]
        novo_total = len(remanescentes)
        for r in remanescentes:
            r.parcela_total = novo_total
            session.add(r)

    # Reversão do que a baixa fez (`pagar_lancamento`/`baixa_lote`/
    # `baixa_lote_detalhada`), ao contrário.
    registro.data_pagamento = None
    registro.valor_pago = None
    registro.conta_bancaria = None
    registro.numero_documento_pagamento = None
    registro.forma_pagamento = None
    registro.data_vencimento_cartao = None
    registro.desconto_acrescimo = None
    registro.atualizado_em = datetime.utcnow()
    session.add(registro)

    session.commit()
    session.refresh(registro)

    return {
        **registro.model_dump(),
        "estornado": True,
        "parcelas_diferenca_removidas": parcelas_diferenca_removidas,
        "avisos": avisos,
    }


@router.post("/importar-xml")
def importar_xml(
    dados: XmlIn, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Extrai os campos de um XML de NF-e/NFS-e para pré-preencher o
    lançamento, e já sugere (em `sugestoes_cadastro`) o fornecedor/produto/
    serviço do cadastro mais parecido com o texto da nota, quando houver
    semelhança mas não certeza — ver fazenda.rules.sugestao_documento."""
    try:
        extraido = parse_nfe_xml(dados.xml)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Não foi possível ler o XML: {e}")
    # Apelido aprendido (ver FornecedorClienteApelido) resolve o nome bruto
    # da nota pro nome do cadastro ANTES da sugestão de casamento — assim
    # sugestoes_cadastro já enxerga o nome certo, sem precisar saber que veio
    # de um apelido salvo em lançamento anterior.
    apelido = resolver_apelido_fornecedor(session, fazenda_id, extraido.get("fornecedor_cliente"))
    if apelido:
        extraido["fornecedor_cliente"] = apelido
        extraido["fornecedor_resolvido_por_apelido"] = True
    extraido["sugestoes_cadastro"] = sugestoes_cadastro(session, fazenda_id, extraido)
    return extraido


@router.post("/ler-documento")
async def ler_documento_anexado(
    file: UploadFile, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Lê um PDF/JPEG/PNG anexado (nota fiscal ou recibo) via IA e devolve os
    campos extraídos para pré-preencher o lançamento — tudo editável no front
    — junto das mesmas sugestões de cadastro de `importar_xml` acima."""
    if file.content_type not in MIME_ACEITOS:
        raise HTTPException(status_code=400, detail=f"Tipo de arquivo não suportado: {file.content_type} (aceitos: PDF, JPEG, PNG)")
    conteudo = await file.read()
    try:
        extraido = ler_documento(conteudo, file.content_type)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Não foi possível ler o documento: {e}")
    apelido = resolver_apelido_fornecedor(session, fazenda_id, extraido.get("fornecedor_cliente"))
    if apelido:
        extraido["fornecedor_cliente"] = apelido
        extraido["fornecedor_resolvido_por_apelido"] = True
    extraido["sugestoes_cadastro"] = sugestoes_cadastro(session, fazenda_id, extraido)
    return extraido


class FornecedorApelidoIn(BaseModel):
    nome_bruto: str
    nome_canonico: str


@router.post("/fornecedor-apelidos", status_code=201)
def criar_fornecedor_apelido(
    dados: FornecedorApelidoIn, session: Session = Depends(get_session), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Ensina o sistema a reconhecer `nome_bruto` (como aparece na nota, ex.:
    "COOP.AGRO.PROD.R.S.GOIANO - COMIGO") como `nome_canonico` (o nome do
    cadastro, ex.: "COMIGO") NESTA fazenda — oferecido pelo front quando a
    leitura automática de documento não bate com nada do cadastro (ver
    sugestao_documento.py, campo `fornecedor_confianca` != "exato"). Chamar
    de novo com o mesmo nome_bruto ATUALIZA o apelido em vez de duplicar —
    o usuário pode corrigir o que ensinou antes."""
    norm = normalizar(dados.nome_bruto)
    if not norm:
        raise HTTPException(status_code=400, detail="nome_bruto vazio")
    if not dados.nome_canonico.strip():
        raise HTTPException(status_code=400, detail="nome_canonico vazio")
    existente = session.exec(
        select(FornecedorClienteApelido).where(
            FornecedorClienteApelido.nome_bruto == norm, FornecedorClienteApelido.fazenda_id == fazenda_id,
        )
    ).first()
    if existente:
        existente.nome_canonico = dados.nome_canonico.strip()
        registro = existente
    else:
        registro = FornecedorClienteApelido(nome_bruto=norm, nome_canonico=dados.nome_canonico.strip(), fazenda_id=fazenda_id)
    session.add(registro)
    session.commit()
    session.refresh(registro)
    return {"id": registro.id, "nome_bruto": registro.nome_bruto, "nome_canonico": registro.nome_canonico}


# Tamanho máximo por anexo (boleto, contrato etc.) — sobe pro Supabase Storage,
# mas o limite continua generoso o bastante sem travar upload de PDF grande.
TAMANHO_MAXIMO_ANEXO = 15 * 1024 * 1024  # 15 MB


def _caminho_anexo_lancamento(session: Session, fazenda_id: int | None, numero_lancamento: str, nome_arquivo: str) -> str:
    """fazenda-X/numero_lancamento/0001_nome.ext — sequencial dentro do
    lançamento, mesmo espírito de _proximo_caminho em routers/documentos.py."""
    pasta = f"fazenda-{fazenda_id if fazenda_id is not None else 'geral'}/{numero_lancamento}"
    existentes = session.exec(
        select(LancamentoAnexo).where(LancamentoAnexo.numero_lancamento == numero_lancamento)
    ).all()
    seq = 1 + len(existentes)
    return f"{pasta}/{seq:04d}_{nome_seguro_storage(nome_arquivo)}"


@router.post("/lancamentos/{numero_lancamento}/anexos", status_code=201)
async def anexar_arquivo_lancamento(
    numero_lancamento: str, file: UploadFile, categoria: str | None = Form(None),
    # Número/data impressos no PRÓPRIO documento (nº do boleto, da nota
    # fiscal, da OS, do orçamento...) — diferente de `criado_em` (quando foi
    # enviado). É por aqui que a Central de Documentos acha, por exemplo,
    # "o boleto número X" mesmo sabendo só esse dado, sem saber o lançamento.
    numero_documento: str | None = Form(None), data_documento: date | None = Form(None),
    session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Anexa um arquivo (ex.: boleto, nota fiscal) a um lançamento já criado —
    várias chamadas para vários arquivos do mesmo lançamento (um boleto por
    parcela, por exemplo), cada um com sua própria categoria (ver
    TIPOS_DOCUMENTO). Sobe para o Supabase Storage — não faz nenhuma
    leitura/OCR aqui; isso já aconteceu, se foi o caso, em /ler-documento
    antes de o lançamento ser salvo."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_conta = select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_lancamento)
    if fazenda_id is not None:
        query_conta = query_conta.where(ContaGerencial.fazenda_id == fazenda_id)
    conta = session.exec(query_conta).first()
    if not conta:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    conteudo = await file.read()
    if len(conteudo) > TAMANHO_MAXIMO_ANEXO:
        raise HTTPException(status_code=400, detail="Arquivo maior que 15 MB — não é possível anexar")
    nome_arquivo = file.filename or "arquivo"
    caminho = _caminho_anexo_lancamento(session, fazenda_id, numero_lancamento, nome_arquivo)
    try:
        enviar_arquivo(caminho, conteudo, file.content_type or "application/octet-stream", bucket=settings.supabase_bucket_financeiro)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    anexo = LancamentoAnexo(
        numero_lancamento=numero_lancamento,
        nome_arquivo=nome_arquivo,
        mime_type=file.content_type or "application/octet-stream",
        tamanho_bytes=len(conteudo),
        categoria=categoria or conta.tipo_documento,
        numero_documento=numero_documento,
        data_documento=data_documento,
        caminho_storage=caminho,
        usuario_id=user.id if isinstance(user, Usuario) else None,
        fazenda_id=fazenda_id,
    )
    session.add(anexo)
    session.commit()
    session.refresh(anexo)
    return {
        "id": anexo.id, "nome_arquivo": anexo.nome_arquivo, "mime_type": anexo.mime_type,
        "tamanho_bytes": anexo.tamanho_bytes, "categoria": anexo.categoria,
        "numero_documento": anexo.numero_documento,
        "data_documento": anexo.data_documento.isoformat() if anexo.data_documento else None,
    }


def _garantir_numero_lancamento(session: Session, fazenda_id: int | None, lancamento_id: int) -> ContaGerencial:
    """Devolve a conta pelo id, garantindo que ela tenha `numero_lancamento`.

    Lançamento importado da planilha Ideagri (ver parsers/conta_gerencial.py)
    nasce SEM numero_lancamento — e como todo o mecanismo de anexo é ancorado
    nessa string, esses lançamentos históricos simplesmente não aceitavam
    comprovante: a área de arrastar aparecia desabilitada, sem explicar nada.
    Aqui a numeração é emitida sob demanda, na primeira vez que se anexa algo,
    e a partir daí o lançamento se comporta como qualquer outro (anexo,
    recibo, vínculo com patrimônio).
    """
    conta = session.get(ContaGerencial, lancamento_id)
    if not conta or (fazenda_id is not None and conta.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    if not conta.numero_lancamento:
        base = conta.data_competencia or conta.data_vencimento or conta.data_emissao or date.today()
        conta.numero_lancamento = _proximo_numero_lancamento(session, base.year)
        session.add(conta)
        session.commit()
        session.refresh(conta)
    return conta


@router.post("/lancamentos/por-id/{lancamento_id}/anexos", status_code=201)
async def anexar_arquivo_lancamento_por_id(
    lancamento_id: int, file: UploadFile, categoria: str | None = Form(None),
    numero_documento: str | None = Form(None), data_documento: date | None = Form(None),
    session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Mesma coisa que anexar por numero_lancamento, só que achando o
    lançamento pelo id — é o caminho usado pelas telas que já têm o registro
    na mão (baixa de pagamento, edição) e que precisam funcionar mesmo para
    lançamento importado, que ainda não tem numeração."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    conta = _garantir_numero_lancamento(session, fazenda_id, lancamento_id)
    return await anexar_arquivo_lancamento(
        conta.numero_lancamento, file, categoria, numero_documento, data_documento,
        session=session, user=user, fazenda_id=fazenda_id,
    )


@router.post("/lancamentos/anexos-lote", status_code=201)
async def anexar_comprovante_em_lote(
    file: UploadFile,
    # Default "" em vez de obrigatório: uma lista vazia chega aqui como campo
    # ausente no multipart, e o 422 genérico do FastAPI não diria o que fazer.
    lancamento_ids: str = Form(""),
    categoria: str | None = Form(None),
    session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Um comprovante ÚNICO para vários lançamentos pagos de uma vez (ver a
    aba "Pagamento em lote" em app/financeiro/page.tsx): o banco emite um
    comprovante só para a remessa inteira, e cada nota daquela remessa precisa
    exibi-lo no relatório de Contas pagas.

    O arquivo sobe UMA vez para o Storage e as N linhas de LancamentoAnexo
    apontam para o MESMO `caminho_storage` — anexar por lançamento, um a um,
    duplicaria o mesmo PDF N vezes no bucket. Quem paga o preço dessa escolha
    é `excluir_anexo`, que por isso só apaga o objeto do Storage quando a
    linha excluída é a última que o referencia.

    `lancamento_ids` vem como CSV porque a requisição é multipart (o mesmo
    motivo de `categoria` ser Form): não dá para mandar JSON junto do arquivo.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    try:
        ids = [int(p) for p in lancamento_ids.split(",") if p.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="lancamento_ids inválido — esperado uma lista de ids separados por vírgula")
    if not ids:
        raise HTTPException(status_code=400, detail="Selecione ao menos um lançamento para anexar o comprovante")

    conteudo = await file.read()
    if len(conteudo) > TAMANHO_MAXIMO_ANEXO:
        raise HTTPException(status_code=400, detail="Arquivo maior que 15 MB — não é possível anexar")
    nome_arquivo = file.filename or "comprovante"
    mime = file.content_type or "application/octet-stream"

    # Emite a numeração de todos ANTES de subir o arquivo: se algum id for de
    # outra fazenda (404), nada foi enviado ao Storage ainda.
    contas = [_garantir_numero_lancamento(session, fazenda_id, lid) for lid in ids]

    # O caminho fica ancorado no primeiro lançamento da remessa, seguindo a
    # convenção de _caminho_anexo_lancamento; os demais só referenciam.
    caminho = _caminho_anexo_lancamento(session, fazenda_id, contas[0].numero_lancamento, nome_arquivo)
    try:
        enviar_arquivo(caminho, conteudo, mime, bucket=settings.supabase_bucket_financeiro)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    criados = []
    for conta in contas:
        anexo = LancamentoAnexo(
            numero_lancamento=conta.numero_lancamento,
            nome_arquivo=nome_arquivo,
            mime_type=mime,
            tamanho_bytes=len(conteudo),
            categoria=categoria or conta.tipo_documento,
            caminho_storage=caminho,
            usuario_id=user.id if isinstance(user, Usuario) else None,
            fazenda_id=fazenda_id,
        )
        session.add(anexo)
        criados.append(anexo)
    session.commit()
    for anexo in criados:
        session.refresh(anexo)
    return {
        "anexados": len(criados),
        "nome_arquivo": nome_arquivo,
        "anexo_ids": [a.id for a in criados],
        "numeros_lancamento": [c.numero_lancamento for c in contas],
    }


@router.get("/lancamentos/por-id/{lancamento_id}/anexos")
def listar_anexos_lancamento_por_id(
    lancamento_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Anexos do lançamento pelo id. Ao contrário do POST, aqui NÃO se emite
    numeração: só de abrir a tela não se altera o lançamento — sem número,
    não há anexo mesmo, e a lista vazia é a resposta certa."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    conta = session.get(ContaGerencial, lancamento_id)
    if not conta or (fazenda_id is not None and conta.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    if not conta.numero_lancamento:
        return []
    return listar_anexos_lancamento(conta.numero_lancamento, session=session, fazenda_id=fazenda_id)


@router.get("/lancamentos/{numero_lancamento}/anexos")
def listar_anexos_lancamento(
    numero_lancamento: str, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Metadados dos anexos do lançamento — sem o conteúdo (ver /anexos/{id} p/ baixar)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(LancamentoAnexo).where(LancamentoAnexo.numero_lancamento == numero_lancamento)
    if fazenda_id is not None:
        query = query.where(LancamentoAnexo.fazenda_id == fazenda_id)
    anexos = session.exec(query).all()
    return [
        {"id": a.id, "nome_arquivo": a.nome_arquivo, "mime_type": a.mime_type, "tamanho_bytes": a.tamanho_bytes,
         "categoria": a.categoria, "numero_documento": a.numero_documento,
         "data_documento": a.data_documento.isoformat() if a.data_documento else None,
         "criado_em": a.criado_em.isoformat()}
        for a in anexos
    ]


@router.get("/anexos/{anexo_id}")
def baixar_anexo(
    anexo_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> Response:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    anexo = session.get(LancamentoAnexo, anexo_id)
    if not anexo or (fazenda_id is not None and anexo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    if anexo.caminho_storage:
        try:
            conteudo = baixar_arquivo(anexo.caminho_storage, bucket=settings.supabase_bucket_financeiro)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    else:
        conteudo = anexo.conteudo  # formato antigo (legado) — ver docstring do model
    return Response(
        content=conteudo, media_type=anexo.mime_type,
        headers={"Content-Disposition": f'inline; filename="{anexo.nome_arquivo}"'},
    )


@router.delete("/anexos/{anexo_id}")
def excluir_anexo(
    anexo_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    anexo = session.get(LancamentoAnexo, anexo_id)
    if not anexo or (fazenda_id is not None and anexo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    if anexo.caminho_storage:
        # Um comprovante de pagamento em lote é UM arquivo no Storage
        # referenciado por várias linhas (ver anexar_comprovante_em_lote), uma
        # por lançamento da remessa. Apagar o objeto ao excluir a primeira
        # linha deixaria as outras apontando para o vazio — o download delas
        # passaria a falhar. Só remove do Storage quando esta é a última
        # referência; caso contrário, some apenas o vínculo deste lançamento.
        outras = session.exec(
            select(LancamentoAnexo).where(
                LancamentoAnexo.caminho_storage == anexo.caminho_storage,
                LancamentoAnexo.id != anexo.id,
            )
        ).first()
        if not outras:
            try:
                excluir_arquivo(anexo.caminho_storage, bucket=settings.supabase_bucket_financeiro)
            except RuntimeError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
    session.delete(anexo)
    session.commit()
    return {"excluido": True}


@router.get("/lancamentos/{numero_lancamento}/destinatario-recibo")
def destinatario_recibo(numero_lancamento: str, session: Session = Depends(get_session)) -> dict:
    """
    Resolve o destinatário contextual do recibo a partir do lançamento: folha
    de pagamento busca o e-mail em Pessoa; os demais tipos buscam em
    Fornecedor (compra/despesa) ou Cliente (venda/receita) — ambos cadastrados
    na mesma tabela Fornecedor, distinguidos pelo campo `tipo`. Como
    `fornecedor_cliente` é só o nome (texto), a busca é por nome; se houver
    mais de um cadastro com o mesmo nome ou nenhum, devolve email vazio — o
    campo no modal continua editável para o usuário preencher à mão.
    """
    conta = session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_lancamento)).first()
    if not conta:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    nome = (conta.fornecedor_cliente or "").strip()
    if not nome:
        return {"nome": None, "email": None}
    if conta.tipo_documento == "Folha de pagamento":
        pessoa = session.exec(select(Pessoa).where(Pessoa.nome == nome)).first()
        return {"nome": nome, "email": pessoa.email if pessoa else None}
    fornecedor = session.exec(select(Fornecedor).where(Fornecedor.nome == nome)).first()
    return {"nome": nome, "email": fornecedor.email if fornecedor else None}


@router.post("/lancamentos/{numero_lancamento}/recibo/enviar")
async def enviar_recibo(
    numero_lancamento: str, destinatario: str = Form(...), arquivo: UploadFile = None,
    session: Session = Depends(get_session),
) -> dict:
    """Envia por e-mail o PDF do recibo (gerado no navegador) para o
    destinatário informado — editável no modal, independente do que a
    resolução contextual sugeriu."""
    conta = session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_lancamento)).first()
    if not conta:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    if not (destinatario or "").strip():
        raise HTTPException(status_code=400, detail="Informe o e-mail do destinatário")
    if not arquivo:
        raise HTTPException(status_code=400, detail="Anexe o PDF do recibo")
    conteudo = await arquivo.read()
    corpo_html = (
        f"<p>Segue em anexo o recibo do lançamento <b>{numero_lancamento}</b> "
        f"({conta.fornecedor_cliente or '—'}, R$ {conta.valor_total or 0:.2f}).</p>"
        "<p>Fazenda Estreito Ponte de Pedra</p>"
    )
    try:
        enviar_email(destinatario.strip(), f"Recibo — {numero_lancamento}", corpo_html, arquivo.filename or "recibo.pdf", conteudo)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"enviado": True}


@router.get("/contas-a-pagar")
def contas_a_pagar(
    dias: int = Query(10, description="Janela em dias"),
    data_referencia: date | None = Query(None, description="Data de referência para calcular a janela (default: hoje)"),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Retorna contas com vencimento nos próximos N dias (não quitadas).
    `data_referencia` segue a mesma convenção de calcular_pev
    (fazenda/rules/scratch_pev.py) — sem ela, mesmo comportamento de sempre
    (janela a partir de hoje); com ela, permite fixar o "hoje" da consulta.
    Existe para que um teste comparando essa janela contra uma data possa
    fixar as duas pontas em vez de depender do dia real em que a suíte
    roda — mesmo defeito que já quebrou 7 testes deste repositório (ver
    PR #492): asserção com data absoluta escrita à mão, comparada contra
    `date.today()` real, passa em alguns dias do mês e falha em outros."""
    hoje = data_referencia or date.today()
    limite = hoje + __import__("datetime").timedelta(days=dias)

    query = select(ContaGerencial)
    if fazenda_id is not None:
        query = query.where(ContaGerencial.fazenda_id == fazenda_id)
    contas = session.exec(query).all()
    nomes_usuarios = mapa_usuarios(session, {c.usuario_id for c in contas})
    resultado = []
    for c in contas:
        if (
            c.data_vencimento
            and hoje <= c.data_vencimento <= limite
            and (c.valor_pago or 0) < (c.valor_total or 0)
            and c.tipo == "despesa"
        ):
            resultado.append({**c.model_dump(), "usuario_nome": nomes_usuarios.get(c.usuario_id)})

    return sorted(resultado, key=lambda x: x["data_vencimento"])


# ---------------------------------------------------------------------------
# Recálculo de juros/multa por atraso — calculadora pura (não persiste
# nada sozinha): o contador usa o valor sugerido para lançar o ajuste como um
# lançamento extraordinário normal (POST /lancamentos), já com o cadeado
# destravado (ver fazenda/auth.py::bloquear_escrita_contador). Percentuais
# default seguem a convenção civil comum (multa de 2%, juros de mora de 1%
# ao mês pro-rata dia) — sempre ajustáveis, pois a regra real varia por
# tributo/contrato.
# ---------------------------------------------------------------------------
class CalculoJurosIn(BaseModel):
    valor_original: float
    data_vencimento: date
    data_referencia: date | None = None
    percentual_multa: float = 2.0
    percentual_juros_mes: float = 1.0


@router.post("/calcular-juros")
def calcular_juros(dados: CalculoJurosIn) -> dict:
    referencia = dados.data_referencia or date.today()
    dias_atraso = max(0, (referencia - dados.data_vencimento).days)
    if dias_atraso == 0:
        return {
            "dias_atraso": 0, "valor_multa": 0.0, "valor_juros": 0.0,
            "valor_atualizado": round(dados.valor_original, 2),
        }
    valor_multa = round(dados.valor_original * dados.percentual_multa / 100, 2)
    valor_juros = round(dados.valor_original * (dados.percentual_juros_mes / 100) * (dias_atraso / 30), 2)
    return {
        "dias_atraso": dias_atraso, "valor_multa": valor_multa, "valor_juros": valor_juros,
        "valor_atualizado": round(dados.valor_original + valor_multa + valor_juros, 2),
    }
