"""
Router de Cadastro (Configurações > Cadastro) — dados mestres que antes viviam
misturados em Lançamentos: ficha do animal, fornecedores/fabricantes/clientes
e metadados de itens de estoque (ensacado/kg por saco/fornecedor) usados pela
Alimentação. Lotes já tinham seu próprio router (lotes.py); Fornecedor e a
ficha do animal gravam nas MESMAS tabelas (Animal, Estoque) usadas em todo o
site — não há tabela paralela/inerte.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import (
    Animal, ContaGerencial, Doenca, Estoque, EstoqueSemen, EventoSanitario, FolhaPagamento, Fornecedor, MotivoBaixa,
    Pessoa, PrincipioAtivo, ProtocoloSanitario, ProtocoloSanitarioEtapa, ServicoCadastro, ValeFuncionario, ValeParcela,
)
from fazenda.api.routers.estoque import _validar_embalagem
from fazenda.api.routers.financeiro import _proximo_numero_lancamento

FORMAS_PAGAMENTO_VALE = ["dinheiro", "pix", "transferencia", "desconto_integral_folha"]

router = APIRouter(prefix="/cadastro", tags=["cadastro"])

TIPOS_PESSOA = ["Funcionário", "Veterinário", "Zootecnista", "Vet/Zootec.", "Diarista", "Prestador de serviços"]

# Seed inicial — funcionários já conhecidos da fazenda (ver seed_pessoas,
# chamada uma vez no startup, mesmo padrão de seed_motivos_movimentacao).
SEED_PESSOAS = [
    {"nome": "Leomir Bonfim", "tipo": "Funcionário"},
    {"nome": "Alane dos Santos", "tipo": "Funcionário"},
    {"nome": "Jorbeson Nunes", "tipo": "Funcionário"},
    {"nome": "Valéria Bonfim", "tipo": "Funcionário"},
    {"nome": "Alexandre Scarpa", "tipo": "Funcionário"},
]


def seed_pessoas(session: Session) -> None:
    """Cria as pessoas padrão se a tabela ainda estiver vazia (idempotente)."""
    if session.exec(select(Pessoa)).first():
        return
    for dados in SEED_PESSOAS:
        session.add(Pessoa(**dados))
    session.commit()


# ---------------------------------------------------------------------------
# Fornecedores / fabricantes / clientes
# ---------------------------------------------------------------------------
TIPOS_FORNECEDOR = ("fornecedor", "fabricante", "cliente", "corretor")


class FornecedorIn(BaseModel):
    nome: str
    tipo: str  # "fornecedor" | "fabricante" | "cliente" | "corretor"
    categoria: str | None = None
    cnpj_cpf: str | None = None
    telefone: str | None = None
    email: str | None = None
    observacoes: str | None = None
    ativo: bool = True


@router.get("/fornecedores")
def listar_fornecedores(session: Session = Depends(get_session)) -> list[dict]:
    return [f.model_dump() for f in session.exec(select(Fornecedor).order_by(Fornecedor.nome)).all()]


@router.post("/fornecedores")
def criar_fornecedor(dados: FornecedorIn, session: Session = Depends(get_session)) -> dict:
    if dados.tipo not in TIPOS_FORNECEDOR:
        raise HTTPException(status_code=400, detail="Tipo inválido")
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    f = Fornecedor(**dados.model_dump())
    session.add(f)
    session.commit()
    session.refresh(f)
    return f.model_dump()


@router.put("/fornecedores/{fornecedor_id}")
def atualizar_fornecedor(fornecedor_id: int, dados: FornecedorIn, session: Session = Depends(get_session)) -> dict:
    if dados.tipo not in TIPOS_FORNECEDOR:
        raise HTTPException(status_code=400, detail="Tipo inválido")
    f = session.get(Fornecedor, fornecedor_id)
    if not f:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado")
    for campo, valor in dados.model_dump().items():
        setattr(f, campo, valor)
    session.add(f)
    session.commit()
    session.refresh(f)
    return f.model_dump()


# ---------------------------------------------------------------------------
# Pessoas — funcionário, veterinário, zootecnista, diarista, prestador de
# serviços. Distinto de Fornecedor: usado na folha de pagamento, não em notas.
# ---------------------------------------------------------------------------
class PessoaIn(BaseModel):
    nome: str
    tipo: str
    telefone: str | None = None
    email: str | None = None
    observacoes: str | None = None
    ativo: bool = True
    salario_base: float | None = None


@router.get("/pessoas")
def listar_pessoas(session: Session = Depends(get_session)) -> list[dict]:
    return [p.model_dump() for p in session.exec(select(Pessoa).order_by(Pessoa.nome)).all()]


@router.post("/pessoas")
def criar_pessoa(dados: PessoaIn, session: Session = Depends(get_session)) -> dict:
    if dados.tipo not in TIPOS_PESSOA:
        raise HTTPException(status_code=400, detail="Tipo inválido")
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    p = Pessoa(**dados.model_dump())
    session.add(p)
    session.commit()
    session.refresh(p)
    return p.model_dump()


@router.put("/pessoas/{pessoa_id}")
def atualizar_pessoa(pessoa_id: int, dados: PessoaIn, session: Session = Depends(get_session)) -> dict:
    if dados.tipo not in TIPOS_PESSOA:
        raise HTTPException(status_code=400, detail="Tipo inválido")
    p = session.get(Pessoa, pessoa_id)
    if not p:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    for campo, valor in dados.model_dump().items():
        setattr(p, campo, valor)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p.model_dump()


# ---------------------------------------------------------------------------
# Folha de pagamento — lançamento e acompanhamento por pessoa/competência.
# ---------------------------------------------------------------------------
class FolhaPagamentoIn(BaseModel):
    pessoa_id: int
    competencia: str  # "AAAA-MM"
    valor_bruto: float
    descontos: float = 0.0
    percentual_inss: float = 0.0
    percentual_ir: float = 0.0
    valor_inss: float = 0.0
    valor_ir: float = 0.0
    data_pagamento: date | None = None
    status: str = "pendente"
    observacao: str | None = None
    recorrente: bool = False
    dia_vencimento: int | None = None  # obrigatório quando recorrente=True (1-28)


def _competencia_seguinte(competencia: str) -> str:
    ano, mes = (int(x) for x in competencia.split("-"))
    ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return f"{ano:04d}-{mes:02d}"


def _valor_vale(session: Session, pessoa_id: int, competencia: str) -> float:
    """
    Soma o valor de TODAS as parcelas de vale da pessoa nesta competência —
    esse é o "desconto de vale" da folha (coluna separada dos "descontos de
    folha" manuais). Uma parcela pertence a exatamente uma competência e a
    pessoa tem no máximo uma folha por competência, então somar todas é
    correto e idempotente (não acumula em recomputações sucessivas).
    """
    parcelas = session.exec(
        select(ValeParcela).where(
            ValeParcela.pessoa_id == pessoa_id,
            ValeParcela.competencia == competencia,
        )
    ).all()
    return round(sum(p.valor for p in parcelas), 2)


def _marcar_vale_aplicado(session: Session, pessoa_id: int, competencia: str) -> None:
    """Marca como aplicadas as parcelas de vale absorvidas por uma folha desta
    competência — só bookkeeping; o valor_vale vem sempre da SOMA, não daqui."""
    pendentes = session.exec(
        select(ValeParcela).where(
            ValeParcela.pessoa_id == pessoa_id,
            ValeParcela.competencia == competencia,
            ValeParcela.aplicada == False,  # noqa: E712
        )
    ).all()
    for p in pendentes:
        p.aplicada = True
        session.add(p)


def _gerar_folha_recorrente(session: Session) -> None:
    """
    Para cada lançamento de folha marcado como recorrente (o "modelo"), gera
    automaticamente os lançamentos das competências seguintes até o mês atual
    — tanto o registro de acompanhamento (FolhaPagamento) quanto a conta a
    pagar correspondente (ContaGerencial) — sem exigir relançamento manual
    todo mês. Mesmo padrão "lazy pull" da baixa automática de Alimentação.
    """
    competencia_atual = date.today().strftime("%Y-%m")
    modelos = session.exec(select(FolhaPagamento).where(FolhaPagamento.recorrente == True)).all()  # noqa: E712
    for modelo in modelos:
        pessoa = session.get(Pessoa, modelo.pessoa_id)
        if not pessoa:
            continue
        competencia = _competencia_seguinte(modelo.competencia)
        while competencia <= competencia_atual:
            existe = session.exec(
                select(FolhaPagamento).where(
                    FolhaPagamento.pessoa_id == modelo.pessoa_id,
                    FolhaPagamento.competencia == competencia,
                )
            ).first()
            if not existe:
                ano, mes = (int(x) for x in competencia.split("-"))
                dia = min(max(modelo.dia_vencimento or 5, 1), 28)
                descontos = round(modelo.descontos, 2)
                valor_vale = _valor_vale(session, modelo.pessoa_id, competencia)
                _marcar_vale_aplicado(session, modelo.pessoa_id, competencia)
                valor_liquido = round(modelo.valor_bruto - descontos - valor_vale, 2)
                numero_lancamento = _proximo_numero_lancamento(session, ano)
                nova = FolhaPagamento(
                    pessoa_id=modelo.pessoa_id, competencia=competencia, valor_bruto=modelo.valor_bruto,
                    descontos=descontos, valor_vale=valor_vale, valor_liquido=valor_liquido, status="pendente",
                    observacao=modelo.observacao, origem_recorrencia_id=modelo.id,
                    numero_lancamento_gerado=numero_lancamento,
                )
                session.add(nova)
                session.add(ContaGerencial(
                    numero_lancamento=numero_lancamento,
                    descricao=f"Folha de pagamento — {pessoa.nome} ({competencia})",
                    data_vencimento=date(ano, mes, dia),
                    data_competencia=date(ano, mes, 1),
                    fornecedor_cliente=pessoa.nome,
                    tipo_documento="Folha de pagamento",
                    valor_total=valor_liquido,
                    parcela_num=1, parcela_total=1,
                    tipo="despesa", origem="auto",
                ))
                session.commit()
            competencia = _competencia_seguinte(competencia)


def _detalhe_folha(session: Session, registro: FolhaPagamento) -> list[dict]:
    """
    Discriminação completa do lançamento — bruto, INSS, IR, cada parcela de
    vale aplicada nesta competência e o líquido. É essa lista que vira a
    expansão da linha da folha no frontend (em vez da antiga lista de vales
    solta abaixo do lançamento de vale).
    """
    parcelas_vale = sorted(
        session.exec(
            select(ValeParcela).where(
                ValeParcela.pessoa_id == registro.pessoa_id, ValeParcela.competencia == registro.competencia
            )
        ).all(),
        key=lambda p: (p.vale_id, p.id or 0),
    )
    detalhe = [{"label": "Salário bruto", "valor": registro.valor_bruto}]
    if registro.percentual_inss:
        detalhe.append({"label": f"INSS ({registro.percentual_inss:g}%)", "valor": -registro.valor_inss})
    if registro.percentual_ir:
        detalhe.append({"label": f"IR ({registro.percentual_ir:g}%)", "valor": -registro.valor_ir})
    # Uma linha por parcela de vale, com o valor REAL da parcela (descontos de
    # vale). Numera a parcela na sequência do PRÓPRIO vale (k/n, ex.: 1/2, 2/2),
    # ordenando todas as parcelas do vale por competência — não só as deste mês.
    for p in parcelas_vale:
        irmas = sorted(
            session.exec(select(ValeParcela).where(ValeParcela.vale_id == p.vale_id)).all(),
            key=lambda x: (x.competencia, x.id or 0),
        )
        n = len(irmas)
        k = next((i + 1 for i, x in enumerate(irmas) if x.id == p.id), 1)
        detalhe.append({"label": f"Vale (parcela {k}/{n})", "valor": -p.valor})
    # "Descontos de folha" manuais — vêm de registro.descontos, SEM misturar vale.
    if abs(registro.descontos) > 0.001:
        detalhe.append({"label": "Outros descontos", "valor": -registro.descontos})
    detalhe.append({"label": "Valor líquido", "valor": registro.valor_liquido})
    return detalhe


@router.get("/folha-pagamento")
def listar_folha_pagamento(session: Session = Depends(get_session)) -> list[dict]:
    _gerar_folha_recorrente(session)
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    registros = session.exec(select(FolhaPagamento).order_by(FolhaPagamento.competencia.desc())).all()

    # Self-heal: um vale lançado DEPOIS da folha (ainda não paga) não estava
    # sendo refletido. Recomputa o valor_vale a partir da SOMA das parcelas e,
    # se mudou, atualiza o líquido e a conta a pagar vinculada.
    houve_mudanca = False
    for registro in registros:
        if registro.status == "pago":
            continue
        vv = _valor_vale(session, registro.pessoa_id, registro.competencia)
        if abs(vv - (registro.valor_vale or 0)) > 0.001:
            registro.valor_vale = vv
            registro.valor_liquido = round(
                registro.valor_bruto - registro.descontos - registro.valor_inss - registro.valor_ir - vv, 2
            )
            _marcar_vale_aplicado(session, registro.pessoa_id, registro.competencia)
            session.add(registro)
            if registro.numero_lancamento_gerado:
                conta = session.exec(
                    select(ContaGerencial).where(
                        ContaGerencial.numero_lancamento == registro.numero_lancamento_gerado
                    )
                ).first()
                if conta and conta.valor_pago is None:
                    conta.valor_total = registro.valor_liquido
                    session.add(conta)
            houve_mudanca = True
    if houve_mudanca:
        session.commit()
        # O commit expira os objetos já carregados; recarrega para o model_dump.
        registros = session.exec(select(FolhaPagamento).order_by(FolhaPagamento.competencia.desc())).all()

    return [
        {**r.model_dump(), "pessoa_nome": pessoas.get(r.pessoa_id, "—"), "detalhe": _detalhe_folha(session, r)}
        for r in registros
    ]


@router.post("/folha-pagamento")
def criar_folha_pagamento(dados: FolhaPagamentoIn, session: Session = Depends(get_session)) -> dict:
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if dados.status not in ("pendente", "pago"):
        raise HTTPException(status_code=400, detail="Status inválido")
    if dados.recorrente and not (dados.dia_vencimento and 1 <= dados.dia_vencimento <= 28):
        raise HTTPException(status_code=400, detail="Informe o dia de vencimento (1 a 28) para lançamentos recorrentes")
    descontos = round(dados.descontos, 2)  # "descontos de folha" manuais, sem vale
    valor_vale = _valor_vale(session, dados.pessoa_id, dados.competencia)
    _marcar_vale_aplicado(session, dados.pessoa_id, dados.competencia)
    valor_inss = round(dados.valor_inss, 2)
    valor_ir = round(dados.valor_ir, 2)
    valor_liquido = round(dados.valor_bruto - descontos - valor_inss - valor_ir - valor_vale, 2)
    if valor_liquido <= 0:
        raise HTTPException(status_code=400, detail="Valor líquido deve ser positivo")

    # Gera também a conta a pagar correspondente — sem isso, a folha nunca
    # aparecia em Contas a Pagar nem na Agenda (só as competências seguintes,
    # geradas por _gerar_folha_recorrente, tinham essa conta criada).
    ano, mes = (int(x) for x in dados.competencia.split("-"))
    dia = min(max(dados.dia_vencimento or 5, 1), 28)
    numero_lancamento = _proximo_numero_lancamento(session, ano)

    registro = FolhaPagamento(
        pessoa_id=dados.pessoa_id, competencia=dados.competencia, valor_bruto=dados.valor_bruto,
        descontos=descontos, percentual_inss=dados.percentual_inss, percentual_ir=dados.percentual_ir,
        valor_inss=valor_inss, valor_ir=valor_ir, valor_vale=valor_vale, valor_liquido=valor_liquido,
        data_pagamento=dados.data_pagamento, status=dados.status, observacao=dados.observacao,
        recorrente=dados.recorrente, dia_vencimento=dados.dia_vencimento if dados.recorrente else None,
        numero_lancamento_gerado=numero_lancamento,
    )
    session.add(registro)
    session.add(ContaGerencial(
        numero_lancamento=numero_lancamento,
        descricao=f"Folha de pagamento — {pessoa.nome} ({dados.competencia})",
        data_vencimento=date(ano, mes, dia),
        data_competencia=date(ano, mes, 1),
        fornecedor_cliente=pessoa.nome,
        tipo_documento="Folha de pagamento",
        valor_total=valor_liquido,
        parcela_num=1, parcela_total=1,
        tipo="despesa", origem="auto",
        data_pagamento=dados.data_pagamento if dados.status == "pago" else None,
        valor_pago=valor_liquido if dados.status == "pago" else None,
    ))
    session.commit()
    session.refresh(registro)
    return registro.model_dump()


@router.put("/folha-pagamento/{registro_id}")
def atualizar_folha_pagamento(registro_id: int, dados: FolhaPagamentoIn, session: Session = Depends(get_session)) -> dict:
    registro = session.get(FolhaPagamento, registro_id)
    if not registro:
        raise HTTPException(status_code=404, detail="Registro de folha não encontrado")
    if registro.status == "pago":
        raise HTTPException(status_code=400, detail="Lançamento de folha já pago não pode ser editado.")
    if not session.get(Pessoa, dados.pessoa_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if dados.status not in ("pendente", "pago"):
        raise HTTPException(status_code=400, detail="Status inválido")
    valor_inss = round(dados.valor_inss, 2)
    valor_ir = round(dados.valor_ir, 2)
    descontos = round(dados.descontos, 2)  # "descontos de folha" manuais, sem vale
    valor_vale = _valor_vale(session, dados.pessoa_id, dados.competencia)
    _marcar_vale_aplicado(session, dados.pessoa_id, dados.competencia)
    valor_liquido = round(dados.valor_bruto - descontos - valor_inss - valor_ir - valor_vale, 2)
    if valor_liquido <= 0:
        raise HTTPException(status_code=400, detail="Valor líquido deve ser positivo")
    if dados.recorrente and not (dados.dia_vencimento and 1 <= dados.dia_vencimento <= 28):
        raise HTTPException(status_code=400, detail="Informe o dia de vencimento (1 a 28) para lançamentos recorrentes")
    registro.pessoa_id = dados.pessoa_id
    registro.competencia = dados.competencia
    registro.valor_bruto = dados.valor_bruto
    registro.descontos = descontos
    registro.percentual_inss = dados.percentual_inss
    registro.percentual_ir = dados.percentual_ir
    registro.valor_inss = valor_inss
    registro.valor_ir = valor_ir
    registro.valor_vale = valor_vale
    registro.valor_liquido = valor_liquido
    registro.data_pagamento = dados.data_pagamento
    registro.status = dados.status
    registro.observacao = dados.observacao
    registro.recorrente = dados.recorrente
    registro.dia_vencimento = dados.dia_vencimento if dados.recorrente else None
    session.add(registro)

    # Mantém a conta a pagar gerada automaticamente em sincronia com a edição.
    if registro.numero_lancamento_gerado:
        conta = session.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == registro.numero_lancamento_gerado)
        ).first()
        if conta and conta.valor_pago is None:
            pessoa = session.get(Pessoa, dados.pessoa_id)
            ano, mes = (int(x) for x in dados.competencia.split("-"))
            dia = min(max(dados.dia_vencimento or 5, 1), 28)
            conta.descricao = f"Folha de pagamento — {pessoa.nome} ({dados.competencia})"
            conta.fornecedor_cliente = pessoa.nome
            conta.data_vencimento = date(ano, mes, dia)
            conta.data_competencia = date(ano, mes, 1)
            conta.valor_total = valor_liquido
            if dados.status == "pago":
                conta.data_pagamento = dados.data_pagamento
                conta.valor_pago = valor_liquido
            session.add(conta)

    session.commit()
    session.refresh(registro)
    return registro.model_dump()


# ---------------------------------------------------------------------------
# Vale de funcionário — adiantamento com desconto parcelado na folha. Se a
# soma das parcelas de vale de uma competência ultrapassar 40% do salário
# base da pessoa, é preciso confirmar explicitamente antes de lançar.
# ---------------------------------------------------------------------------
class ValeIn(BaseModel):
    pessoa_id: int
    valor_total: float
    forma_pagamento: str
    data_pagamento: date
    parcelas: int = 1
    competencia_inicio: str  # "AAAA-MM"
    observacao: str | None = None
    confirmar: bool = False  # true para prosseguir mesmo ultrapassando 40% do salário


def _competencias_do_vale(competencia_inicio: str, parcelas: int) -> list[str]:
    competencias = [competencia_inicio]
    for _ in range(parcelas - 1):
        competencias.append(_competencia_seguinte(competencias[-1]))
    return competencias


@router.get("/vales")
def listar_vales(session: Session = Depends(get_session)) -> list[dict]:
    pessoas = {p.id: p.nome for p in session.exec(select(Pessoa)).all()}
    vales = session.exec(select(ValeFuncionario).order_by(ValeFuncionario.data_pagamento.desc())).all()
    saida = []
    for v in vales:
        parcelas = session.exec(select(ValeParcela).where(ValeParcela.vale_id == v.id)).all()
        saida.append({
            **v.model_dump(), "pessoa_nome": pessoas.get(v.pessoa_id, "—"),
            "parcelas_detalhe": sorted(({**p.model_dump()} for p in parcelas), key=lambda p: p["competencia"]),
        })
    return saida


@router.post("/vales")
def criar_vale(dados: ValeIn, session: Session = Depends(get_session)) -> dict:
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    if dados.forma_pagamento not in FORMAS_PAGAMENTO_VALE:
        raise HTTPException(status_code=400, detail="Forma de pagamento inválida")
    if dados.valor_total <= 0:
        raise HTTPException(status_code=400, detail="Valor do vale deve ser positivo")
    if dados.parcelas < 1:
        raise HTTPException(status_code=400, detail="Informe ao menos 1 parcela")

    competencias = _competencias_do_vale(dados.competencia_inicio, dados.parcelas)
    valor_parcela = round(dados.valor_total / dados.parcelas, 2)
    # a última parcela absorve o arredondamento, para a soma bater com valor_total
    valores_parcela = [valor_parcela] * (dados.parcelas - 1)
    valores_parcela.append(round(dados.valor_total - valor_parcela * (dados.parcelas - 1), 2))

    if not pessoa.salario_base:
        raise HTTPException(
            status_code=400,
            detail="Cadastre o salário base da pessoa (Configurações > Cadastro > Pessoas) antes de lançar um vale.",
        )

    limite = round(pessoa.salario_base * 0.4, 2)
    competencias_excedidas = []
    for competencia, valor in zip(competencias, valores_parcela):
        ja_lancado = session.exec(
            select(ValeParcela).where(ValeParcela.pessoa_id == dados.pessoa_id, ValeParcela.competencia == competencia)
        ).all()
        total_competencia = round(sum(p.valor for p in ja_lancado) + valor, 2)
        if total_competencia > limite:
            competencias_excedidas.append({"competencia": competencia, "total": total_competencia, "limite": limite})

    if competencias_excedidas and not dados.confirmar:
        raise HTTPException(status_code=409, detail={
            "mensagem": (
                f"O desconto de vale ultrapassa 40% do salário (limite de R$ {limite:.2f}) em "
                f"{len(competencias_excedidas)} competência(s). Confirme para lançar mesmo assim."
            ),
            "competencias_excedidas": competencias_excedidas,
        })

    vale = ValeFuncionario(
        pessoa_id=dados.pessoa_id, valor_total=dados.valor_total, forma_pagamento=dados.forma_pagamento,
        data_pagamento=dados.data_pagamento, parcelas=dados.parcelas, competencia_inicio=dados.competencia_inicio,
        observacao=dados.observacao,
    )
    session.add(vale)
    session.commit()
    session.refresh(vale)
    for competencia, valor in zip(competencias, valores_parcela):
        session.add(ValeParcela(vale_id=vale.id, pessoa_id=dados.pessoa_id, competencia=competencia, valor=valor))
    session.commit()

    # Efeito imediato: se já existir uma folha (não paga) para alguma das
    # competências afetadas, recomputa o valor_vale/líquido e sincroniza a
    # conta a pagar vinculada — sem depender do self-heal no próximo GET.
    for competencia in competencias:
        folha = session.exec(
            select(FolhaPagamento).where(
                FolhaPagamento.pessoa_id == dados.pessoa_id,
                FolhaPagamento.competencia == competencia,
                FolhaPagamento.status != "pago",
            )
        ).first()
        if not folha:
            continue
        folha.valor_vale = _valor_vale(session, dados.pessoa_id, competencia)
        folha.valor_liquido = round(
            folha.valor_bruto - folha.descontos - folha.valor_inss - folha.valor_ir - folha.valor_vale, 2
        )
        _marcar_vale_aplicado(session, dados.pessoa_id, competencia)
        session.add(folha)
        if folha.numero_lancamento_gerado:
            conta = session.exec(
                select(ContaGerencial).where(
                    ContaGerencial.numero_lancamento == folha.numero_lancamento_gerado
                )
            ).first()
            if conta and conta.valor_pago is None:
                conta.valor_total = folha.valor_liquido
                session.add(conta)
    session.commit()

    return {**vale.model_dump(), "parcelas_detalhe": [
        {"competencia": c, "valor": v} for c, v in zip(competencias, valores_parcela)
    ]}


# ---------------------------------------------------------------------------
# Ficha do animal — grava direto na tabela Animal usada em todo o site.
# ---------------------------------------------------------------------------
class AnimalFichaIn(BaseModel):
    numero: str
    nome: str | None = None
    sisbov: str | None = None
    sexo: str | None = None  # "F" | "M"
    raca: str | None = None
    categoria_abrev: str | None = None
    grupo_primario: str | None = None
    data_nasc: date | None = None
    data_entrada: date | None = None
    proprietario: str | None = None
    valor: float | None = None
    motivo_baixa: str | None = None
    data_baixa: date | None = None
    mae_numero: str | None = None
    mae_nome: str | None = None
    observacoes: str | None = None


@router.post("/animais")
def criar_animal(dados: AnimalFichaIn, session: Session = Depends(get_session)) -> dict:
    numero = dados.numero.strip()
    if not numero:
        raise HTTPException(status_code=400, detail="Número/brinco é obrigatório")
    existente = session.exec(select(Animal).where(Animal.numero == numero)).first()
    if existente:
        raise HTTPException(status_code=400, detail=f"Já existe um animal com o número {numero}")

    animal = Animal(numero=numero, ativo=dados.data_baixa is None)
    for campo, valor in dados.model_dump(exclude={"numero"}).items():
        setattr(animal, campo, valor)
    session.add(animal)
    session.commit()
    session.refresh(animal)
    return animal.model_dump()


@router.put("/animais/{numero}")
def atualizar_ficha_animal(numero: str, dados: AnimalFichaIn, session: Session = Depends(get_session)) -> dict:
    animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    for campo, valor in dados.model_dump(exclude={"numero"}).items():
        setattr(animal, campo, valor)
    if dados.data_baixa is not None:
        animal.ativo = False
    animal.atualizado_em = datetime.utcnow()
    session.add(animal)
    session.commit()
    session.refresh(animal)
    return animal.model_dump()


# ---------------------------------------------------------------------------
# Metadados de itens de estoque — embalagem (usada pela Alimentação para
# converter kg necessários em sacos/potes/fardos) e fornecedor principal do
# item. A quantidade em si continua vindo do ESTOQUE.csv / movimentações;
# aqui só descrevemos o item.
# ---------------------------------------------------------------------------
class EstoqueMetaIn(BaseModel):
    unidade_embalagem: str | None = None
    medida_embalagem: str | None = None
    quantidade_embalagem: float | None = None
    fornecedor_id: int | None = None
    estocavel: bool | None = None
    considerar_rmca: bool | None = None


@router.get("/estoque-itens")
def listar_itens_estoque(session: Session = Depends(get_session)) -> list[dict]:
    fornecedores = {f.id: f.nome for f in session.exec(select(Fornecedor)).all()}
    return [
        {**e.model_dump(), "fornecedor_nome": fornecedores.get(e.fornecedor_id)}
        for e in session.exec(select(Estoque).order_by(Estoque.nome)).all()
    ]


@router.put("/estoque-itens/{item_id}")
def atualizar_meta_estoque(item_id: int, dados: EstoqueMetaIn, session: Session = Depends(get_session)) -> dict:
    item = session.get(Estoque, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item de estoque não encontrado")
    if dados.fornecedor_id is not None and not session.get(Fornecedor, dados.fornecedor_id):
        raise HTTPException(status_code=400, detail="Fornecedor não encontrado")
    _validar_embalagem(dados.unidade_embalagem, dados.medida_embalagem)
    item.unidade_embalagem = dados.unidade_embalagem
    item.medida_embalagem = dados.medida_embalagem
    item.quantidade_embalagem = dados.quantidade_embalagem
    item.fornecedor_id = dados.fornecedor_id
    item.estocavel = dados.estocavel
    item.considerar_rmca = dados.considerar_rmca
    session.add(item)
    session.commit()
    session.refresh(item)
    return item.model_dump()


# ---------------------------------------------------------------------------
# Princípio ativo / Doença / Evento sanitário — cadastros de apoio ao
# Calendário sanitário (Sanidade). Seed inicial com os nomes já usados no
# protocolo padrão da fazenda (manejo sazonal + vacinas por fase fisiológica).
# ---------------------------------------------------------------------------
SEED_EVENTOS_SANITARIOS = [
    "Vermífugo", "Reprodutiva (Primovacinação)", "Reprodutiva (Reforço)", "Clostridiose",
    "Diarreia Neonatal", "Botulismo", "Tifopasteurina", "Leptospirose",
    "Exames de Tuberculose e Brucelose", "Febre Aftosa", "Raiva", "Brucelose B19", "Brucelose RB51",
]
SEED_DOENCAS = [
    "Brucelose", "Clostridiose", "Diarreia Neonatal", "Botulismo", "Pasteurelose", "Verminose",
    "Leptospirose", "Tuberculose", "Febre Aftosa", "Raiva",
]
# Pequeno exemplo — só para ilustrar o vínculo com produtos já no Estoque.
SEED_PRINCIPIOS_ATIVOS = ["Ivermectina", "Cepa B19 (Brucella abortus atenuada)"]


def seed_cadastro_sanitario(session: Session) -> None:
    """Cria os cadastros sanitários padrão se as tabelas ainda estiverem vazias (idempotente)."""
    if not session.exec(select(EventoSanitario)).first():
        for nome in SEED_EVENTOS_SANITARIOS:
            session.add(EventoSanitario(nome=nome))
    if not session.exec(select(Doenca)).first():
        for nome in SEED_DOENCAS:
            session.add(Doenca(nome=nome))
    if not session.exec(select(PrincipioAtivo)).first():
        for nome in SEED_PRINCIPIOS_ATIVOS:
            session.add(PrincipioAtivo(nome=nome))
    session.commit()


# ---------------------------------------------------------------------------
# Motivo de baixa (Rebanho > Baixar animal) — causa específica da baixa (usada
# quando o motivo geral é "doença", mas também cobre outras causas comuns:
# acidente, roubo, idade avançada etc.). Cadastrável em Configurações, para
# não ficar limitado à lista fixa que havia antes só no código.
# ---------------------------------------------------------------------------
SEED_MOTIVOS_BAIXA = [
    "Botulismo", "Brucelose", "Tuberculose", "Babesia", "Casco", "Choque anafilático",
    "Afogada", "Complicações pós-parto", "Clostridiose", "Descarga elétrica", "Descarte",
    "Deslocamento de abomaso", "Desconhecido", "Diarréia", "Doação", "Doenças a vírus",
    "Doenças bacterianas", "Doenças", "Fratura", "Hemorragia interna", "Hipocalcemia",
    "Idade avançada", "Infarto", "Ingestão de corpo estranho", "Intoxicação", "Leptospirose",
    "Má formação", "Mastite", "Metrite", "Morte natural", "Nascimento prematuro", "Natimorto",
    "Pneumonia", "Retenção de placenta", "Roubo", "Tripanossoma", "Trombose",
]


def seed_motivos_baixa(session: Session) -> None:
    """Cria os motivos de baixa padrão se a tabela ainda estiver vazia (idempotente)."""
    if session.exec(select(MotivoBaixa)).first():
        return
    for nome in SEED_MOTIVOS_BAIXA:
        session.add(MotivoBaixa(nome=nome))
    session.commit()


# ---------------------------------------------------------------------------
# Cadastro de Serviços (lançamento financeiro > produto OU serviço) — ex.:
# manutenção de trator, frete, quilometragem. Lista aberta/extensível.
# ---------------------------------------------------------------------------
SEED_SERVICOS = [
    "Manutenção em tratores", "Manutenção em câmeras", "Frete", "Quilometragem (km)",
    "Manutenção periódica programada de ordenha", "Manutenção extraordinária de ordenha",
    "Revisão em máquinas", "Revisão em equipamentos", "Revisão em implementos",
]


def seed_servicos(session: Session) -> None:
    """Cria os serviços padrão se a tabela ainda estiver vazia (idempotente)."""
    if session.exec(select(ServicoCadastro)).first():
        return
    for nome in SEED_SERVICOS:
        session.add(ServicoCadastro(nome=nome))
    session.commit()


class NomeAtivoIn(BaseModel):
    nome: str
    ativo: bool = True


def _crud_nome_ativo(model):
    """Fábrica de CRUD idêntico para os 3 cadastros simples (nome + ativo)."""

    def listar(session: Session = Depends(get_session)) -> list[dict]:
        return [m.model_dump() for m in session.exec(select(model).order_by(model.nome)).all()]

    def criar(dados: NomeAtivoIn, session: Session = Depends(get_session)) -> dict:
        nome = dados.nome.strip()
        if not nome:
            raise HTTPException(status_code=400, detail="Nome é obrigatório")
        if session.exec(select(model).where(model.nome == nome)).first():
            raise HTTPException(status_code=409, detail=f"Já existe um registro com o nome '{nome}'")
        obj = model(nome=nome, ativo=dados.ativo)
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj.model_dump()

    def atualizar(item_id: int, dados: NomeAtivoIn, session: Session = Depends(get_session)) -> dict:
        obj = session.get(model, item_id)
        if not obj:
            raise HTTPException(status_code=404, detail="Registro não encontrado")
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


_listar_principios, _criar_principio, _atualizar_principio = _crud_nome_ativo(PrincipioAtivo)
router.get("/principios-ativos")(_listar_principios)
router.post("/principios-ativos")(_criar_principio)
router.put("/principios-ativos/{item_id}")(_atualizar_principio)

_listar_doencas, _criar_doenca, _atualizar_doenca = _crud_nome_ativo(Doenca)
router.get("/doencas")(_listar_doencas)
router.post("/doencas")(_criar_doenca)
router.put("/doencas/{item_id}")(_atualizar_doenca)

_listar_eventos, _criar_evento, _atualizar_evento = _crud_nome_ativo(EventoSanitario)
router.get("/eventos-sanitarios")(_listar_eventos)
router.post("/eventos-sanitarios")(_criar_evento)
router.put("/eventos-sanitarios/{item_id}")(_atualizar_evento)

_listar_motivos_baixa, _criar_motivo_baixa, _atualizar_motivo_baixa = _crud_nome_ativo(MotivoBaixa)
router.get("/motivos-baixa")(_listar_motivos_baixa)
router.post("/motivos-baixa")(_criar_motivo_baixa)
router.put("/motivos-baixa/{item_id}")(_atualizar_motivo_baixa)

_listar_servicos, _criar_servico, _atualizar_servico = _crud_nome_ativo(ServicoCadastro)
router.get("/servicos")(_listar_servicos)
router.post("/servicos")(_criar_servico)
router.put("/servicos/{item_id}")(_atualizar_servico)


# ---------------------------------------------------------------------------
# Protocolo sanitário — cadastro com múltiplas etapas (produto/dosagem/via por
# dia), a exemplo do tratamento de mastite. Etapas começam em D1 — protocolos
# sanitários não têm D0 (isso é exclusivo do protocolo hormonal IATF).
# ---------------------------------------------------------------------------
VIAS_APLICACAO = ["Intramamária", "Intramuscular", "Intravenosa", "Subdérmica", "Oral"]


class ProtocoloEtapaIn(BaseModel):
    dia: int
    produto: str
    dosagem: float
    unidade: str
    via: str | None = None


class ProtocoloSanitarioIn(BaseModel):
    nome: str
    doenca_id: int | None = None
    eh_mastite: bool = False
    ativo: bool = True
    etapas: list[ProtocoloEtapaIn]


def _validar_etapas(etapas: list[ProtocoloEtapaIn]) -> None:
    if not etapas:
        raise HTTPException(status_code=400, detail="Informe ao menos uma etapa do protocolo")
    for e in etapas:
        if e.dia < 1:
            raise HTTPException(
                status_code=400,
                detail="Protocolos sanitários não têm D0 — os dias começam em D1 (D0 é exclusivo do protocolo hormonal)",
            )
        if e.dosagem <= 0:
            raise HTTPException(status_code=400, detail="A dosagem de cada etapa deve ser positiva")
        if e.via and e.via not in VIAS_APLICACAO:
            raise HTTPException(status_code=400, detail=f"Via inválida — use uma de: {', '.join(VIAS_APLICACAO)}")


def _serializar_protocolo(session: Session, p: ProtocoloSanitario, doencas: dict[int, str]) -> dict:
    etapas = session.exec(
        select(ProtocoloSanitarioEtapa).where(ProtocoloSanitarioEtapa.protocolo_id == p.id).order_by(ProtocoloSanitarioEtapa.dia)
    ).all()
    return {
        **p.model_dump(),
        "doenca_nome": doencas.get(p.doenca_id) if p.doenca_id else None,
        "etapas": [e.model_dump() for e in etapas],
    }


@router.get("/protocolos-sanitarios")
def listar_protocolos_sanitarios(session: Session = Depends(get_session)) -> list[dict]:
    doencas = {d.id: d.nome for d in session.exec(select(Doenca)).all()}
    protocolos = session.exec(select(ProtocoloSanitario).order_by(ProtocoloSanitario.nome)).all()
    return [_serializar_protocolo(session, p, doencas) for p in protocolos]


@router.post("/protocolos-sanitarios")
def criar_protocolo_sanitario(dados: ProtocoloSanitarioIn, session: Session = Depends(get_session)) -> dict:
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    if session.exec(select(ProtocoloSanitario).where(ProtocoloSanitario.nome == nome)).first():
        raise HTTPException(status_code=409, detail=f"Já existe um protocolo com o nome '{nome}'")
    _validar_etapas(dados.etapas)

    protocolo = ProtocoloSanitario(nome=nome, doenca_id=dados.doenca_id, eh_mastite=dados.eh_mastite, ativo=dados.ativo)
    session.add(protocolo)
    session.commit()
    session.refresh(protocolo)
    for etapa in dados.etapas:
        session.add(ProtocoloSanitarioEtapa(protocolo_id=protocolo.id, **etapa.model_dump()))
    session.commit()

    doencas = {d.id: d.nome for d in session.exec(select(Doenca)).all()}
    return _serializar_protocolo(session, protocolo, doencas)


@router.put("/protocolos-sanitarios/{protocolo_id}")
def atualizar_protocolo_sanitario(protocolo_id: int, dados: ProtocoloSanitarioIn, session: Session = Depends(get_session)) -> dict:
    protocolo = session.get(ProtocoloSanitario, protocolo_id)
    if not protocolo:
        raise HTTPException(status_code=404, detail="Protocolo não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    _validar_etapas(dados.etapas)

    protocolo.nome = nome
    protocolo.doenca_id = dados.doenca_id
    protocolo.eh_mastite = dados.eh_mastite
    protocolo.ativo = dados.ativo
    session.add(protocolo)

    etapas_antigas = session.exec(select(ProtocoloSanitarioEtapa).where(ProtocoloSanitarioEtapa.protocolo_id == protocolo_id)).all()
    for e in etapas_antigas:
        session.delete(e)
    session.commit()
    for etapa in dados.etapas:
        session.add(ProtocoloSanitarioEtapa(protocolo_id=protocolo.id, **etapa.model_dump()))
    session.commit()

    doencas = {d.id: d.nome for d in session.exec(select(Doenca)).all()}
    return _serializar_protocolo(session, protocolo, doencas)


# ---------------------------------------------------------------------------
# Estoque de sêmen — doses por touro (usado no relatório de manejo).
# ---------------------------------------------------------------------------
TIPOS_SEMEN = ["convencional", "sexado"]


class EstoqueSemenIn(BaseModel):
    touro_nome: str
    codigo: str | None = None
    central: str | None = None
    tipo: str = "convencional"
    doses: int = 0
    observacao: str | None = None
    ativo: bool = True


@router.get("/estoque-semen")
def listar_estoque_semen(session: Session = Depends(get_session)) -> list[dict]:
    itens = session.exec(select(EstoqueSemen).order_by(EstoqueSemen.touro_nome)).all()
    return [i.model_dump() for i in itens]


@router.post("/estoque-semen")
def criar_estoque_semen(dados: EstoqueSemenIn, session: Session = Depends(get_session)) -> dict:
    if not dados.touro_nome.strip():
        raise HTTPException(status_code=400, detail="Informe o nome do touro")
    if dados.tipo not in TIPOS_SEMEN:
        raise HTTPException(status_code=400, detail=f"Tipo inválido (aceitos: {', '.join(TIPOS_SEMEN)})")
    if dados.doses < 0:
        raise HTTPException(status_code=400, detail="Doses não pode ser negativo")
    item = EstoqueSemen(**dados.model_dump())
    session.add(item)
    session.commit()
    session.refresh(item)
    return item.model_dump()


@router.put("/estoque-semen/{item_id}")
def atualizar_estoque_semen(item_id: int, dados: EstoqueSemenIn, session: Session = Depends(get_session)) -> dict:
    item = session.get(EstoqueSemen, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Registro de sêmen não encontrado")
    if dados.tipo not in TIPOS_SEMEN:
        raise HTTPException(status_code=400, detail=f"Tipo inválido (aceitos: {', '.join(TIPOS_SEMEN)})")
    if dados.doses < 0:
        raise HTTPException(status_code=400, detail="Doses não pode ser negativo")
    for campo, valor in dados.model_dump().items():
        setattr(item, campo, valor)
    item.atualizado_em = datetime.utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    return item.model_dump()


@router.delete("/estoque-semen/{item_id}")
def excluir_estoque_semen(item_id: int, session: Session = Depends(get_session)) -> dict:
    item = session.get(EstoqueSemen, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Registro de sêmen não encontrado")
    session.delete(item)
    session.commit()
    return {"excluido": True}
