"""
Router de Cadastro (Configurações > Cadastro) — dados mestres que antes viviam
misturados em Lançamentos: ficha do animal, fornecedores/fabricantes/clientes
e metadados de itens de estoque (ensacado/kg por saco/fornecedor) usados pela
Alimentação. Lotes já tinham seu próprio router (lotes.py); Fornecedor e a
ficha do animal gravam nas MESMAS tabelas (Animal, Estoque) usadas em todo o
site — não há tabela paralela/inerte.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user
from fazenda.database import get_session
from fazenda.models import (
    AgendamentoPesagem, Animal, CalendarioSanitario, ContaGerencial, Doenca, Estoque, EstoqueSemen, EventoSanitario, FolhaPagamento, Fornecedor,
    Lote, MotivoBaixa, Pessoa, PrincipioAtivo, ProtocoloInducaoLactacao, ProtocoloInducaoLactacaoEtapa, ProtocoloSanitario, ProtocoloSanitarioEtapa,
    SeedFlag, ServicoCadastro, Touro, Usuario, ValeFuncionario, ValeParcela,
)
from fazenda.api.routers.estoque import _validar_embalagem
from fazenda.api.routers.financeiro import _proximo_numero_lancamento
from fazenda.rules.auditoria import mapa_usuarios
from fazenda.rules.calendario_sanitario import proxima_ocorrencia

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

    # Data de vencimento da folha (mês de pagamento) — vem da conta a pagar
    # gerada. Mapeia numero_lancamento_gerado → data_vencimento.
    numeros = [r.numero_lancamento_gerado for r in registros if r.numero_lancamento_gerado]
    venc_por_numero: dict[str, object] = {}
    if numeros:
        for c in session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros))).all():
            if c.numero_lancamento and c.numero_lancamento not in venc_por_numero:
                venc_por_numero[c.numero_lancamento] = c.data_vencimento

    nomes_usuarios = mapa_usuarios(session, {r.usuario_id for r in registros})

    return [
        {
            **r.model_dump(),
            "pessoa_nome": pessoas.get(r.pessoa_id, "—"),
            "data_vencimento": venc_por_numero.get(r.numero_lancamento_gerado),
            "detalhe": _detalhe_folha(session, r),
            "usuario_nome": nomes_usuarios.get(r.usuario_id),
        }
        for r in registros
    ]


@router.post("/folha-pagamento")
def criar_folha_pagamento(dados: FolhaPagamentoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
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
        usuario_id=user.id,
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
    nomes_usuarios = mapa_usuarios(session, {v.usuario_id for v in vales})
    saida = []
    for v in vales:
        parcelas = session.exec(select(ValeParcela).where(ValeParcela.vale_id == v.id)).all()
        saida.append({
            **v.model_dump(), "pessoa_nome": pessoas.get(v.pessoa_id, "—"),
            "usuario_nome": nomes_usuarios.get(v.usuario_id),
            "parcelas_detalhe": sorted(({**p.model_dump()} for p in parcelas), key=lambda p: p["competencia"]),
        })
    return saida


@router.post("/vales")
def criar_vale(dados: ValeIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
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
        observacao=dados.observacao, usuario_id=user.id,
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
    grau_sangue: str | None = None
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
    excluir_bst: bool = False


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
    principio_ativo: str | None = None
    classificacao_medicamento: str | None = None


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
    item.principio_ativo = dados.principio_ativo
    item.classificacao_medicamento = dados.classificacao_medicamento
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


def seed_cadastro_sanitario(session: Session) -> None:
    """Cria os cadastros sanitários padrão se as tabelas ainda estiverem vazias (idempotente).
    Princípios ativos não entram aqui: o catálogo completo (documento base) é
    responsabilidade de bootstrap_farmacia, que roda em todo start."""
    if not session.exec(select(EventoSanitario)).first():
        for nome in SEED_EVENTOS_SANITARIOS:
            session.add(EventoSanitario(nome=nome))
    if not session.exec(select(Doenca)).first():
        for nome in SEED_DOENCAS:
            session.add(Doenca(nome=nome))
    session.commit()


# ---------------------------------------------------------------------------
# Calendário sanitário padrão da fazenda — carregado das planilhas enviadas
# (calendário fixo anual + protocolo por fase fisiológica). Roda em todo
# start, idempotente: só cria o que ainda não existe (não sobrescreve
# edição do usuário — dosagem/frequência/produto continuam 100% editáveis
# nas telas de Cadastro > Sanitário e Lançamentos > Sanitário > Calendário).
# Valores de dose/idade/gatilho vindos das planilhas em faixa (ex.: "2 mL a
# 5 mL", "4 a 8 meses") foram fixados num ponto do meio — ajuste à vontade.
# ---------------------------------------------------------------------------
SEED_PRINCIPIOS_CALENDARIO = [
    # (nome, categoria, doença vinculada)
    ("Botulismo (Toxoide)", "Biológicos (Vacinas e Diagnósticos)", "Botulismo"),
    ("Tifopasteurina", "Biológicos (Vacinas e Diagnósticos)", "Pasteurelose"),
    ("Febre Aftosa (Vacina)", "Biológicos (Vacinas e Diagnósticos)", "Febre Aftosa"),
    ("Raiva (Vacina)", "Biológicos (Vacinas e Diagnósticos)", "Raiva"),
]

# Eventos "por fase fisiológica" (protocolo por estágio) — configura o
# EventoSanitario para gerar a pendência sozinho, disparado pelo gatilho
# (nascimento, novilha apta, entrada no pré-parto), sem depender de uma
# regra do calendário. Só aplica se o evento ainda estiver no padrão
# "nenhum" (nunca configurado manualmente).
SEED_EVENTOS_POR_ESTAGIO = [
    # nome, doença, gatilho, idade/offset, dose, unidade, via
    {"nome": "Brucelose B19", "doenca": "Brucelose", "gatilho": "nascimento", "offset_dias": 150,
     "dose": 2, "unidade": "ml", "via": "Subcutânea"},
    {"nome": "Brucelose RB51", "doenca": "Brucelose", "gatilho": "novilha_apta", "idade_meses": 13,
     "dose": 2, "unidade": "ml", "via": "Subcutânea"},
    {"nome": "Reprodutiva (Primovacinação)", "doenca": None, "gatilho": "novilha_apta", "idade_meses": 13,
     "dose": 5, "unidade": "ml", "via": "Intramuscular"},
    {"nome": "Clostridiose", "doenca": "Clostridiose", "gatilho": "entrada_lote",
     "dose": 3, "unidade": "ml", "via": "Subcutânea"},
    {"nome": "Diarreia Neonatal", "doenca": "Diarreia Neonatal", "gatilho": "entrada_lote",
     "dose": 2, "unidade": "ml", "via": "Subcutânea"},
    {"nome": "Botulismo", "doenca": "Botulismo", "gatilho": "entrada_lote",
     "dose": 3, "unidade": "ml", "via": "Subcutânea"},
    {"nome": "Tifopasteurina", "doenca": "Pasteurelose", "gatilho": "entrada_lote",
     "dose": 3, "unidade": "ml", "via": "Subcutânea"},
]

# Regras do calendário fixo anual — época/rebanho (não por animal). Datas
# ancoradas em 2026 (ano corrente); a recorrência projeta as próximas
# ocorrências sozinha (não precisa estar no futuro).
SEED_CALENDARIO_FIXO = [
    {"evento": "Vermífugo", "categoria_alvo": "Bezerras até Novilhas", "freq_valor": 4, "freq_unidade": "meses",
     "data": date(2026, 1, 15), "dosagem": "Conforme o peso (ex.: 1 mL/50 kg)", "categoria_preventiva": "tratamento"},
    {"evento": "Reprodutiva (Reforço)", "categoria_alvo": "Novilhas IA até Vacas", "freq_valor": 12, "freq_unidade": "meses",
     "data": date(2026, 1, 15), "dosagem": "5 mL (depende do fabricante)", "categoria_preventiva": "vacina"},
    {"evento": "Reprodutiva (Reforço)", "categoria_alvo": "Novilhas IA até Vacas", "freq_valor": 12, "freq_unidade": "meses",
     "data": date(2026, 6, 15), "dosagem": "5 mL (depende do fabricante)", "categoria_preventiva": "vacina"},
    {"evento": "Reprodutiva (Reforço)", "categoria_alvo": "Novilhas IA até Vacas", "freq_valor": 12, "freq_unidade": "meses",
     "data": date(2026, 12, 15), "dosagem": "5 mL (depende do fabricante)", "categoria_preventiva": "vacina"},
    {"evento": "Leptospirose", "categoria_alvo": "Novilhas IA até Vacas", "freq_valor": 12, "freq_unidade": "meses",
     "data": date(2026, 3, 15), "dosagem": "2 mL a 5 mL (conforme bula)", "categoria_preventiva": "vacina"},
    {"evento": "Leptospirose", "categoria_alvo": "Bezerras até Novilhas", "freq_valor": 12, "freq_unidade": "meses",
     "data": date(2026, 9, 15), "dosagem": "Conforme o peso", "categoria_preventiva": "vacina"},
    {"evento": "Exames de Tuberculose e Brucelose", "categoria_alvo": "Rebanho Geral", "freq_valor": 1, "freq_unidade": "anos",
     "data": date(2027, 4, 15), "dosagem": "Coleta de sangue / Aplicação PPD", "categoria_preventiva": "exame",
     "observacao": "Retomado em 2027 — já foi feito recentemente."},
    {"evento": "Febre Aftosa", "categoria_alvo": "Vacas", "freq_valor": 1, "freq_unidade": "anos",
     "data": date(2026, 5, 15), "dosagem": "2 mL", "categoria_preventiva": "vacina",
     "observacao": "Calendário do Governo."},
    {"evento": "Brucelose RB51", "categoria_alvo": "Vacas Adultas", "freq_valor": 4, "freq_unidade": "anos",
     "data": date(2026, 7, 15), "dosagem": "2 mL", "categoria_preventiva": "vacina",
     "observacao": "Reforço a cada 4 anos — estratégia: fazer em anos de Copa do Mundo, para não esquecer."},
    {"evento": "Raiva", "categoria_alvo": "Vacas", "freq_valor": 1, "freq_unidade": "anos",
     "data": date(2026, 11, 15), "dosagem": "2 mL", "categoria_preventiva": "vacina",
     "observacao": "Calendário do Governo."},
]

# Princípio ativo a vincular por evento (quando existe correspondência clara
# no catálogo da farmácia) — só informativo/rastreio, dosagem real continua
# sendo escolhida no lançamento.
PRINCIPIO_POR_EVENTO_CALENDARIO = {
    "Reprodutiva (Reforço)": "Reprodutiva (IBR, BVD, Leptospirose)",
    "Leptospirose": "Reprodutiva (IBR, BVD, Leptospirose)",
    "Brucelose RB51": "Brucelose Bovina (Cepa 19 ou RB51)",
    "Vermífugo": "Albendazol",
    "Febre Aftosa": "Febre Aftosa (Vacina)",
    "Raiva": "Raiva (Vacina)",
}


def configurar_calendario_sanitario_padrao(session: Session) -> None:
    """Compatibiliza e cadastra o calendário sanitário padrão da fazenda
    (planilhas "calendário por mês" e "protocolo por estágio"). Roda em todo
    start, idempotente:
      - só cria princípio ativo/regra do calendário que ainda não existir;
      - só configura um EventoSanitario "por estágio" se ele ainda estiver
        no padrão "nenhum" (nunca foi configurado manualmente).
    Os 13 eventos e as 10 doenças usados aqui já vêm do seed_cadastro_sanitario
    — nenhum evento/doença novo precisou ser criado, só compatibilizado.
    """
    doencas = {d.nome: d for d in session.exec(select(Doenca)).all()}
    eventos = {e.nome: e for e in session.exec(select(EventoSanitario)).all()}
    principios = {p.nome: p for p in session.exec(select(PrincipioAtivo)).all()}

    # 1) Princípios ativos que faltam no catálogo (Botulismo, Tifopasteurina,
    # Febre Aftosa e Raiva não têm biológico próprio hoje — a farmácia só
    # tinha os combos de Clostridiose/Brucelose/Reprodutiva/Tuberculina).
    for nome, categoria, doenca_nome in SEED_PRINCIPIOS_CALENDARIO:
        if nome in principios:
            continue
        novo = PrincipioAtivo(nome=nome, categoria=categoria, categoria_software="Biológico (Vacina)")
        session.add(novo)
        principios[nome] = novo
    session.commit()
    for nome in principios:
        session.refresh(principios[nome])

    # 2) Eventos "por fase fisiológica" — configura gatilho automático.
    # Entrada em lote (pré-parto) exige um lote já marcado pre_parto=True;
    # sem isso, não dá pra saber qual lote dispara o evento — fica pendente
    # de configuração manual (Configurações > Cadastro > Sanitário > Eventos).
    lote_pre_parto = session.exec(select(Lote).where(Lote.pre_parto == True)).first()  # noqa: E712
    for cfg in SEED_EVENTOS_POR_ESTAGIO:
        ev = eventos.get(cfg["nome"])
        if not ev or ev.tipo_agendamento != "nenhum":
            continue  # não existe, ou já foi configurado manualmente — não mexe
        if cfg["gatilho"] == "entrada_lote" and not lote_pre_parto:
            continue  # falta um lote pré-parto cadastrado — configurar depois
        ev.tipo_agendamento = "evento"
        ev.gatilho = cfg["gatilho"]
        if cfg["gatilho"] == "entrada_lote":
            ev.gatilho_lote = lote_pre_parto.codigo
            ev.categoria_alvo = ev.categoria_alvo or "Novilhas e vacas prenhes (pré-parto)"
        if cfg["gatilho"] == "novilha_apta":
            ev.gatilho_idade_meses = cfg.get("idade_meses")
        if cfg["gatilho"] == "nascimento":
            ev.offset_dias = cfg.get("offset_dias")
        if cfg.get("doenca") and doencas.get(cfg["doenca"]):
            ev.doenca_id = ev.doenca_id or doencas[cfg["doenca"]].id
        ev.categoria_preventiva = ev.categoria_preventiva or "vacina"
        ev.dose_padrao = ev.dose_padrao if ev.dose_padrao is not None else cfg["dose"]
        ev.unidade_padrao = ev.unidade_padrao or cfg["unidade"]
        ev.via_padrao = ev.via_padrao or cfg["via"]
        session.add(ev)
    session.commit()

    # 3) Regras do calendário fixo anual — época/rebanho. Evita duplicar se já
    # existir uma regra igual (mesmo evento + mesma categoria-alvo + mesmo mês
    # de âncora — "Reprodutiva (Reforço)" tem 3 aplicações/ano na mesma
    # categoria, diferenciadas só pelo mês; sem o mês na chave, a 2ª e a 3ª
    # seriam descartadas como "duplicata" da 1ª).
    existentes = {
        (c.evento_sanitario_id, (c.categoria_alvo or "").strip().lower(), c.data_evento.month)
        for c in session.exec(select(CalendarioSanitario)).all()
    }
    for cfg in SEED_CALENDARIO_FIXO:
        ev = eventos.get(cfg["evento"])
        if not ev:
            continue
        chave = (ev.id, cfg["categoria_alvo"].strip().lower(), cfg["data"].month)
        if chave in existentes:
            continue
        # Mantém a categoria_preventiva do evento se já foi definida manualmente.
        if not ev.categoria_preventiva:
            ev.categoria_preventiva = cfg["categoria_preventiva"]
            session.add(ev)
        principio_nome = PRINCIPIO_POR_EVENTO_CALENDARIO.get(cfg["evento"])
        principio = principios.get(principio_nome) if principio_nome else None
        session.add(CalendarioSanitario(
            evento_sanitario_id=ev.id,
            categoria_alvo=cfg["categoria_alvo"],
            doenca_id=ev.doenca_id,
            principio_ativo_id=principio.id if principio else None,
            dosagem=cfg["dosagem"],
            frequencia_valor=cfg["freq_valor"],
            frequencia_unidade=cfg["freq_unidade"],
            data_evento=cfg["data"],
            observacao=cfg.get("observacao"),
        ))
        existentes.add(chave)
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

# Serviços de exames — usados no botão "lançar financeiro" do calendário
# sanitário (exames não têm baixa de estoque, viram despesa/serviço). O
# guarda-chuva "Exames" mais as 3 categorias pedidas.
SEED_SERVICOS_EXAMES = [
    "Exames", "Exame de tuberculose", "Exame de brucelose", "Outros exames",
]


def seed_servicos(session: Session) -> None:
    """Cria os serviços padrão (se a tabela estiver vazia) e garante, sempre,
    os serviços de exames — estes por checagem nome a nome, para também
    aparecerem em bancos que já foram semeados antes."""
    if not session.exec(select(ServicoCadastro)).first():
        for nome in SEED_SERVICOS:
            session.add(ServicoCadastro(nome=nome))
        session.commit()
    existentes = {s.nome for s in session.exec(select(ServicoCadastro)).all()}
    novos = [nome for nome in SEED_SERVICOS_EXAMES if nome not in existentes]
    if novos:
        for nome in novos:
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


@router.post("/principios-ativos/restaurar-catalogo")
def restaurar_catalogo_principios(session: Session = Depends(get_session)) -> dict:
    """(Re)semeia o catálogo base de princípios ativos (documento base da farmácia)
    — add-missing e idempotente: só cria os que faltam e não sobrescreve edições.
    Útil quando o banco foi criado antes do catálogo completo existir."""
    from fazenda.rules.farmacia import seed_farmacia
    antes = len(session.exec(select(PrincipioAtivo)).all())
    seed_farmacia(session)
    total = len(session.exec(select(PrincipioAtivo)).all())
    return {"criados": total - antes, "total": total}

_listar_doencas, _criar_doenca, _atualizar_doenca = _crud_nome_ativo(Doenca)
router.get("/doencas")(_listar_doencas)
router.post("/doencas")(_criar_doenca)
router.put("/doencas/{item_id}")(_atualizar_doenca)


# ---------------------------------------------------------------------------
# Agendamento de pesagem do rebanho (acompanhamento da evolução de peso) —
# periodicidade por fase + dia da semana, que alimenta a Agenda.
# ---------------------------------------------------------------------------
class AgendamentoPesagemIn(BaseModel):
    nome: str
    ativo: bool = True
    idade_min_dias: int | None = None
    idade_max_dias: int | None = None
    categoria_alvo: str | None = None
    frequencia_valor: int = 15
    frequencia_unidade: str = "dias"  # "dias" | "meses"
    dia_semana: int = 1  # 0=segunda … 6=domingo
    data_referencia: date


@router.get("/agendamentos-pesagem")
def listar_agendamentos_pesagem(session: Session = Depends(get_session)) -> list[dict]:
    return [a.model_dump() for a in session.exec(select(AgendamentoPesagem).order_by(AgendamentoPesagem.nome)).all()]


def _valida_pesagem(dados: AgendamentoPesagemIn) -> None:
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Informe o nome da fase (ex.: Bezerras até desmama)")
    if dados.frequencia_unidade not in ("dias", "meses"):
        raise HTTPException(status_code=400, detail="Frequência inválida (dias ou meses)")
    if dados.frequencia_valor <= 0:
        raise HTTPException(status_code=400, detail="A periodicidade deve ser maior que zero")
    if not (0 <= dados.dia_semana <= 6):
        raise HTTPException(status_code=400, detail="Dia da semana inválido")


@router.post("/agendamentos-pesagem", status_code=201)
def criar_agendamento_pesagem(dados: AgendamentoPesagemIn, session: Session = Depends(get_session)) -> dict:
    _valida_pesagem(dados)
    obj = AgendamentoPesagem(**{**dados.model_dump(), "nome": dados.nome.strip()})
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj.model_dump()


@router.put("/agendamentos-pesagem/{item_id}")
def atualizar_agendamento_pesagem(item_id: int, dados: AgendamentoPesagemIn, session: Session = Depends(get_session)) -> dict:
    obj = session.get(AgendamentoPesagem, item_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    _valida_pesagem(dados)
    for k, v in {**dados.model_dump(), "nome": dados.nome.strip()}.items():
        setattr(obj, k, v)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj.model_dump()


@router.delete("/agendamentos-pesagem/{item_id}")
def excluir_agendamento_pesagem(item_id: int, session: Session = Depends(get_session)) -> dict:
    obj = session.get(AgendamentoPesagem, item_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    session.delete(obj)
    session.commit()
    return {"ok": True}

# Evento sanitário — cadastro RICO (nome + agendamento por época/evento +
# medicamento padrão). Alimenta o calendário sanitário e a Agenda.
FREQUENCIAS_EVENTO = ["dias", "meses", "anos"]
TIPOS_AGENDAMENTO = ["nenhum", "epoca", "evento"]
GATILHOS_EVENTO = ["nascimento", "entrada_lote", "novilha_apta", "secagem", "parto"]


class EventoSanitarioIn(BaseModel):
    nome: str
    ativo: bool = True
    tipo_agendamento: str = "nenhum"
    categoria_alvo: str | None = None
    categoria_preventiva: str | None = None  # "vacina" | "exame" | "tratamento"
    doenca_id: int | None = None
    data_primeiro: date | None = None
    frequencia_valor: int | None = None
    frequencia_unidade: str | None = None
    gatilho: str | None = None
    gatilho_lote: str | None = None
    gatilho_idade_meses: int | None = None
    offset_dias: int | None = None
    produto_padrao: str | None = None
    dose_padrao: float | None = None
    unidade_padrao: str | None = None
    via_padrao: str | None = None
    # Só para exame: avisa na Agenda N dias antes, para confirmar com o veterinário.
    agenda_dias_antes: int | None = None


def _dto_evento_sanitario(session: Session, ev: EventoSanitario) -> dict:
    d = ev.model_dump()
    d["doenca_nome"] = None
    if ev.doenca_id:
        doenca = session.get(Doenca, ev.doenca_id)
        d["doenca_nome"] = doenca.nome if doenca else None
    if ev.tipo_agendamento == "epoca" and ev.data_primeiro and ev.frequencia_valor and ev.frequencia_unidade:
        d["proxima_ocorrencia"] = proxima_ocorrencia(ev.data_primeiro, ev.frequencia_valor, ev.frequencia_unidade).isoformat()
    else:
        d["proxima_ocorrencia"] = None
    return d


def _validar_evento_sanitario(dados: EventoSanitarioIn, session: Session) -> None:
    if dados.tipo_agendamento not in TIPOS_AGENDAMENTO:
        raise HTTPException(status_code=400, detail=f"Tipo de agendamento inválido (use: {', '.join(TIPOS_AGENDAMENTO)})")
    if dados.doenca_id is not None and not session.get(Doenca, dados.doenca_id):
        raise HTTPException(status_code=400, detail="Doença não encontrada")
    if dados.tipo_agendamento == "epoca":
        if not dados.data_primeiro:
            raise HTTPException(status_code=400, detail="Informe a data do primeiro evento (agendamento por época)")
        if not dados.frequencia_valor or dados.frequencia_valor <= 0:
            raise HTTPException(status_code=400, detail="Informe uma frequência maior que zero")
        if dados.frequencia_unidade not in FREQUENCIAS_EVENTO:
            raise HTTPException(status_code=400, detail=f"Frequência inválida (use: {', '.join(FREQUENCIAS_EVENTO)})")
    if dados.tipo_agendamento == "evento":
        if dados.gatilho not in GATILHOS_EVENTO:
            raise HTTPException(status_code=400, detail=f"Gatilho inválido (use: {', '.join(GATILHOS_EVENTO)})")
        if dados.gatilho == "entrada_lote" and not (dados.gatilho_lote or "").strip():
            raise HTTPException(status_code=400, detail="Informe o lote do gatilho (entrada no lote)")
        if dados.gatilho == "novilha_apta" and not dados.gatilho_idade_meses:
            raise HTTPException(status_code=400, detail="Informe a idade-alvo em meses (aptidão de novilha)")


@router.get("/eventos-sanitarios")
def listar_eventos_sanitarios(session: Session = Depends(get_session)) -> list[dict]:
    eventos = session.exec(select(EventoSanitario).order_by(EventoSanitario.nome)).all()
    return [_dto_evento_sanitario(session, ev) for ev in eventos]


@router.post("/eventos-sanitarios")
def criar_evento_sanitario(dados: EventoSanitarioIn, session: Session = Depends(get_session)) -> dict:
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    if session.exec(select(EventoSanitario).where(EventoSanitario.nome == nome)).first():
        raise HTTPException(status_code=409, detail=f"Já existe um evento sanitário com o nome '{nome}'")
    _validar_evento_sanitario(dados, session)
    ev = EventoSanitario(**{**dados.model_dump(), "nome": nome})
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return _dto_evento_sanitario(session, ev)


@router.put("/eventos-sanitarios/{item_id}")
def atualizar_evento_sanitario(item_id: int, dados: EventoSanitarioIn, session: Session = Depends(get_session)) -> dict:
    ev = session.get(EventoSanitario, item_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Evento sanitário não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    _validar_evento_sanitario(dados, session)
    for campo, valor in {**dados.model_dump(), "nome": nome}.items():
        setattr(ev, campo, valor)
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return _dto_evento_sanitario(session, ev)

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
CRITERIOS_MEDICAMENTO = ["medicamento", "principio_ativo", "classificacao", "doenca"]
CLASSIFICACOES_MEDICAMENTO = ["Antimicrobiano", "Anti-inflamatório", "Antibiótico", "Antiparasitário", "Vacina", "Hormônio", "Outro"]


class ProtocoloEtapaIn(BaseModel):
    dia: int
    criterio_tipo: str = "medicamento"  # medicamento | principio_ativo | classificacao
    produto: str  # medicamento OU o valor do critério (princípio ativo / classificação)
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
        if e.criterio_tipo not in CRITERIOS_MEDICAMENTO:
            raise HTTPException(status_code=400, detail=f"Critério inválido — use um de: {', '.join(CRITERIOS_MEDICAMENTO)}")
        if not (e.produto or "").strip():
            raise HTTPException(status_code=400, detail="Informe o medicamento, princípio ativo ou classificação de cada etapa")


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
TIPOS_SEMEN = ["convencional", "sexado", "fazenda"]
# Estoque mínimo de sêmen POR CATEGORIA (não por touro). Abaixo disso, gera
# alerta nas notificações e um evento diário na agenda até a NF suprir.
MINIMO_SEMEN = {"convencional": 20, "sexado": 5}
# Touros da fazenda (monta natural) — sempre disponíveis na inseminação.
TOUROS_FAZENDA = ["Sevaverde", "Frederico"]


def seed_semen_categorias(session: Session) -> None:
    """Garante os touros da fazenda (Sevaverde, Frederico) como categoria
    'fazenda' e classifica o Hagen como sexado. Idempotente (SeedFlag)."""
    chave = "semen_categorias_v1"
    if session.get(SeedFlag, chave):
        return
    existentes = {i.touro_nome.strip().lower(): i for i in session.exec(select(EstoqueSemen)).all()}
    for nome in TOUROS_FAZENDA:
        atual = existentes.get(nome.lower())
        if atual:
            atual.tipo = "fazenda"
            session.add(atual)
        else:
            session.add(EstoqueSemen(touro_nome=nome, tipo="fazenda", doses=0))
    hagen = existentes.get("hagen")
    if hagen:
        hagen.tipo = "sexado"
        session.add(hagen)
    session.add(SeedFlag(chave=chave))
    session.commit()


# Carga inicial do estoque de sêmen (planilha "estoque_de_semen.csv"): touro,
# categoria, doses, valor unitário e local. Roda UMA vez (SeedFlag); depois o
# usuário edita pela tela sem ser sobrescrito.
SEED_ESTOQUE_SEMEN = [
    # (touro, tipo, doses, valor_unitario, local)
    ("COORS", "convencional", 2, 4.19, "Caneca 1"),
    ("GUINESS", "convencional", 1, 22.67, "Caneca 1"),
    ("HAGEN", "sexado", 2, 125.00, "Caneca 1"),
    ("JAG", "convencional", 1, 0.0, "Caneca 1"),
    ("MOSAIC", "convencional", 1, 0.0, "Caneca 1"),
    ("PRAFESS", "convencional", 1, 0.0, "Caneca 1"),
    ("STORMY", "convencional", 1, 0.0, "Caneca 1"),
]


def seed_estoque_semen_inicial(session: Session) -> None:
    """Lança o estoque de sêmen da planilha (upsert por touro). Idempotente
    (SeedFlag) — não sobrescreve edições posteriores do usuário."""
    chave = "estoque_semen_inicial_v1"
    if session.get(SeedFlag, chave):
        return
    existentes = {i.touro_nome.strip().lower(): i for i in session.exec(select(EstoqueSemen)).all()}
    for touro, tipo, doses, valor, local in SEED_ESTOQUE_SEMEN:
        atual = existentes.get(touro.lower())
        if atual:
            atual.tipo = tipo
            atual.doses = doses
            atual.valor_unitario = valor
            atual.local_armazenamento = local
            atual.atualizado_em = datetime.utcnow()
            session.add(atual)
        else:
            session.add(EstoqueSemen(
                touro_nome=touro, codigo=touro, tipo=tipo, doses=doses,
                valor_unitario=valor, local_armazenamento=local,
            ))
    session.add(SeedFlag(chave=chave))
    session.commit()


# Atualização do estoque de sêmen a partir do print enviado (contagem mais
# recente, por touro). Roda UMA vez (SeedFlag próprio, distinto do inicial —
# esse já foi consumido em produção): casa pelo nome curto já cadastrado
# (upsert, renomeando para o nome completo do pedigree) e cria os touros
# ainda não lançados. A linha "TOURO" (sem pedigree, código genérico) foi
# excluída a pedido — nunca cadastrada. Frederico, Sevaverde e ABS Newman-ET
# entram com a quantidade do print DESCONSIDERADA (mantém/zera), conforme
# instrução — os dois primeiros já são touros de monta natural sempre
# disponíveis (tipo "fazenda", doses irrelevantes).
SEED_ESTOQUE_SEMEN_202607 = [
    # (nome curto já cadastrado OU None se for novo, nome completo, código/naab, central, tipo, doses, local)
    ("hagen", "DENOVO 22094 HAGEN-ET", "29HO21643", "ABS", "sexado", 6, "Caneca 1"),
    ("stormy", "STORMY", "029HO19829", "ABS", "convencional", 1, "Caneca 1"),
    ("prafess", "SIEMERS OUT PRAFESS-ET", "3272850936", "ABS", "convencional", 1, "Caneca 1"),
    ("mosaic", "MOSAIC", "029HO18803", "ABS", "convencional", 1, "Caneca 1"),
    ("jag", "T-SPRUCE DENOVO JAG-ET", "29HO21688", "ABS", "convencional", 0, "Caneca 1"),
    ("guiness", "A.R.KK. MYTYME GUINESS 763", "29HO22747", "ABS", "convencional", 6, "Caneca 1"),
    ("coors", "A.R.K. ESQUIRE COORS 758", "29HO22744", "ABS", "convencional", 0, "Caneca 1"),
    (None, "A.R.K. MYTYME HILLUX 70", "29HO21898", "ABS", "convencional", 0, "Caneca 1"),
    (None, "A.R.K. STARGAZER MESSI", "29HO21627", "ABS", "convencional", 0, "Caneca 1"),
    (None, "DELEGADO HOMESTEAD FIV GRF", "1800D", "ABS", "convencional", 1, "Caneca 2"),
    (None, "WV-OAKWOOD SHOTTLE ALDO-ET", "001HO09218", "ABS", "convencional", 0, "Caneca 1"),
    (None, "ABS NEWMAN-ET", "029HO18586", "ABS", "convencional", 0, "Caneca 1"),  # quantidade do print (2) desconsiderada
    (None, "SUCESSOR", "6000BD", "ABS", "sexado", 0, "Caneca 1"),
    (None, "ROBO", "9300AN", "ABS", "convencional", 0, "Caneca 1"),
    (None, "METEORO", "5890BJ", "ABS", "sexado", 0, "Caneca 1"),
    (None, "NABIL", "1956AO", "ABS", "sexado", 0, "Caneca 1"),
    (None, "CAMPEAO FIV RIO DO LEITE", "6555AK", "ABS", "convencional", 0, "Caneca 1"),
]


def atualizar_estoque_semen_202607(session: Session) -> None:
    """Aplica a contagem de estoque de sêmen do print enviado em jul/2026
    (upsert por touro). Roda uma vez (SeedFlag)."""
    chave = "estoque_semen_202607_v1"
    if session.get(SeedFlag, chave):
        return
    existentes = {i.touro_nome.strip().lower(): i for i in session.exec(select(EstoqueSemen)).all()}
    for nome_curto, nome_completo, codigo, central, tipo, doses, local in SEED_ESTOQUE_SEMEN_202607:
        atual = existentes.get(nome_curto) if nome_curto else None
        if atual:
            atual.touro_nome = nome_completo
            atual.codigo = codigo
            atual.naab = codigo
            atual.central = central
            atual.tipo = tipo
            atual.doses = doses
            atual.local_armazenamento = local
            atual.atualizado_em = datetime.utcnow()
            session.add(atual)
        elif nome_completo.strip().lower() not in existentes:
            session.add(EstoqueSemen(
                touro_nome=nome_completo, codigo=codigo, naab=codigo, central=central,
                tipo=tipo, doses=doses, local_armazenamento=local,
            ))
    session.add(SeedFlag(chave=chave))
    session.commit()


class EstoqueSemenIn(BaseModel):
    touro_nome: str
    codigo: str | None = None
    naab: str | None = None
    central: str | None = None
    tipo: str = "convencional"
    doses: int = 0
    valor_unitario: float | None = None
    local_armazenamento: str | None = None
    observacao: str | None = None
    ativo: bool = True


@router.get("/estoque-semen")
def listar_estoque_semen(session: Session = Depends(get_session)) -> list[dict]:
    itens = session.exec(select(EstoqueSemen).order_by(EstoqueSemen.touro_nome)).all()
    return [i.model_dump() for i in itens]


@router.get("/estoque-semen/disponivel")
def semen_disponivel(session: Session = Depends(get_session)) -> dict:
    """
    Para a inseminação: touros por categoria (convencional/sexado/fazenda) e o
    status do estoque mínimo POR CATEGORIA. Convencional/sexado só entram na
    lista se tiverem dose em estoque; touros da fazenda (monta natural) sempre.
    """
    itens = [i for i in session.exec(select(EstoqueSemen).order_by(EstoqueSemen.touro_nome)).all() if i.ativo]
    totais = {"convencional": 0, "sexado": 0}
    for i in itens:
        if i.tipo in totais:
            totais[i.tipo] += i.doses or 0
    touros = []
    for i in itens:
        # Fazenda sempre aparece; sêmen (conv/sexado) só com dose.
        if i.tipo == "fazenda" or (i.doses or 0) > 0:
            touros.append({"nome": i.touro_nome, "tipo": i.tipo, "doses": i.doses or 0})
    abaixo = {cat: totais[cat] < minimo for cat, minimo in MINIMO_SEMEN.items()}
    return {"touros": touros, "totais": totais, "minimos": MINIMO_SEMEN, "abaixo_minimo": abaixo}


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


# ── Catálogo genético de touros (NAAB/provas) ───────────────────────────────
@router.get("/touros")
def listar_touros(session: Session = Depends(get_session)) -> list[dict]:
    """Banco de touros importado do catálogo do fornecedor, ordenado por TPI
    (maior primeiro) e depois por nome."""
    touros = session.exec(select(Touro)).all()
    touros.sort(key=lambda t: (-(t.tpi if t.tpi is not None else -1e9), (t.nome or t.naab)))
    return [t.model_dump() for t in touros]


@router.post("/touros/recarregar-catalogo")
def recarregar_catalogo_touros(session: Session = Depends(get_session)) -> dict:
    """Reimporta o catálogo NAAB completo empacotado no servidor (upsert por
    NAAB — nunca apaga touros existentes). Serve de botão de autoatendimento
    caso a carga automática na inicialização não tenha rodado por algum
    motivo (ex.: banco criado antes deste recurso existir)."""
    from fazenda.rules.touros import bootstrap_touros_naab
    antes = len(session.exec(select(Touro)).all())
    bootstrap_touros_naab(session, forcar=True)
    depois = len(session.exec(select(Touro)).all())
    return {"touros_antes": antes, "touros_depois": depois}


@router.get("/touros/campos-planilha")
def campos_planilha_touros() -> list[str]:
    """Rótulos originais das colunas do catálogo completo (Alta Genetics),
    para o cadastro manual oferecer "preencher com os campos da planilha"
    sem o usuário ter que lembrar/digitar cada nome."""
    from fazenda.rules.touros import CURADOS_POR_CABECALHO
    return [cabecalho for _campo, cabecalho, _num in CURADOS_POR_CABECALHO if _campo != "naab"]


class TouroIn(BaseModel):
    naab: str
    nome: str
    nome_completo: Optional[str] = None
    raca: Optional[str] = None
    central: Optional[str] = None
    leite_kg: Optional[float] = None
    gordura_kg: Optional[float] = None
    gordura_pct: Optional[float] = None
    proteina_kg: Optional[float] = None
    proteina_pct: Optional[float] = None
    tpi: Optional[float] = None
    nm_dolar: Optional[float] = None
    tipo_composto: Optional[float] = None
    ubere_composto: Optional[float] = None
    pernas_composto: Optional[float] = None
    ccs_score: Optional[float] = None
    fertilidade_filhas: Optional[float] = None
    facilidade_parto: Optional[float] = None
    fonte: Optional[str] = None
    rodada_prova: Optional[str] = None
    observacao: Optional[str] = None
    dados_extra: Optional[list[list[str]]] = None  # [[rótulo, valor], ...] — demais dados da planilha


@router.post("/touros")
def criar_touro(dados: TouroIn, session: Session = Depends(get_session)) -> dict:
    """Cadastro manual de um touro. Só o código NAAB e o nome são
    obrigatórios — todo o resto (inclusive campos extras da planilha do
    fornecedor) é opcional."""
    naab = dados.naab.strip().upper()
    if not naab:
        raise HTTPException(status_code=400, detail="Informe o código NAAB")
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Informe o nome do touro")
    if session.exec(select(Touro).where(Touro.naab == naab)).first():
        raise HTTPException(status_code=400, detail=f"Já existe um touro cadastrado com o NAAB {naab}")
    from fazenda.rules.naab import central_por_codigo_naab

    campos = dados.model_dump(exclude={"naab", "dados_extra"})
    touro = Touro(naab=naab, **campos)
    if not touro.central:
        touro.central = central_por_codigo_naab(naab)
    if dados.dados_extra:
        touro.dados_extra = json.dumps(dados.dados_extra, ensure_ascii=False)
    session.add(touro)
    session.commit()
    session.refresh(touro)
    return touro.model_dump()


@router.put("/touros/{touro_id}")
def atualizar_touro(touro_id: int, dados: TouroIn, session: Session = Depends(get_session)) -> dict:
    t = session.get(Touro, touro_id)
    if not t:
        raise HTTPException(status_code=404, detail="Touro não encontrado")
    naab = dados.naab.strip().upper()
    if not naab:
        raise HTTPException(status_code=400, detail="Informe o código NAAB")
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Informe o nome do touro")
    outro = session.exec(select(Touro).where(Touro.naab == naab)).first()
    if outro and outro.id != touro_id:
        raise HTTPException(status_code=400, detail=f"Já existe outro touro cadastrado com o NAAB {naab}")
    for campo, valor in dados.model_dump(exclude={"dados_extra"}).items():
        setattr(t, campo, valor)
    t.naab = naab
    if dados.dados_extra is not None:
        t.dados_extra = json.dumps(dados.dados_extra, ensure_ascii=False) if dados.dados_extra else None
    from datetime import datetime
    t.atualizado_em = datetime.utcnow()
    session.add(t)
    session.commit()
    session.refresh(t)
    return t.model_dump()


@router.delete("/touros/{touro_id}")
def excluir_touro(touro_id: int, session: Session = Depends(get_session)) -> dict:
    t = session.get(Touro, touro_id)
    if not t:
        raise HTTPException(status_code=404, detail="Touro não encontrado")
    session.delete(t)
    session.commit()
    return {"excluido": True}


# ---------------------------------------------------------------------------
# Protocolo de indução de lactação — cadastro do cronograma-molde (dias,
# medicamentos por princípio ativo, implante de progesterona, manejo de
# adaptação à ordenha). O lançamento em animais vive em /producao (ver
# fazenda.api.routers.producao).
# ---------------------------------------------------------------------------
TIPOS_ETAPA_INDUCAO = ["medicamento", "dispositivo", "manejo"]
ACOES_DISPOSITIVO_INDUCAO = ["colocar", "retirar"]


class EtapaInducaoIn(BaseModel):
    dia: int
    tipo: str = "medicamento"  # medicamento | dispositivo | manejo
    principio_ativo_id: int | None = None
    produto: str
    acao_dispositivo: str | None = None  # colocar | retirar (só tipo=dispositivo)
    dose: float | None = None
    unidade: str | None = None
    via: str | None = None


class ProtocoloInducaoIn(BaseModel):
    nome: str
    dia_inicial: int = 0
    observacao: str | None = None
    ativo: bool = True
    etapas: list[EtapaInducaoIn]


def _validar_etapas_inducao(etapas: list[EtapaInducaoIn]) -> None:
    if not etapas:
        raise HTTPException(status_code=400, detail="Informe ao menos uma etapa do protocolo")
    for e in etapas:
        if e.tipo not in TIPOS_ETAPA_INDUCAO:
            raise HTTPException(status_code=400, detail=f"Tipo de etapa inválido — use um de: {', '.join(TIPOS_ETAPA_INDUCAO)}")
        if not (e.produto or "").strip():
            raise HTTPException(status_code=400, detail="Informe o produto/princípio ativo ou a ação de cada etapa")
        if e.tipo == "dispositivo" and e.acao_dispositivo not in ACOES_DISPOSITIVO_INDUCAO:
            raise HTTPException(status_code=400, detail="Etapa de dispositivo precisa de acao_dispositivo: colocar | retirar")
        if e.tipo == "medicamento" and (e.dose is not None and e.dose <= 0):
            raise HTTPException(status_code=400, detail="A dose de uma etapa de medicamento deve ser positiva")


def _serializar_protocolo_inducao(session: Session, p: ProtocoloInducaoLactacao) -> dict:
    etapas = session.exec(
        select(ProtocoloInducaoLactacaoEtapa)
        .where(ProtocoloInducaoLactacaoEtapa.protocolo_id == p.id)
        .order_by(ProtocoloInducaoLactacaoEtapa.dia)
    ).all()
    return {**p.model_dump(), "etapas": [e.model_dump() for e in etapas]}


@router.get("/protocolos-inducao-lactacao")
def listar_protocolos_inducao(session: Session = Depends(get_session)) -> list[dict]:
    protocolos = session.exec(select(ProtocoloInducaoLactacao).order_by(ProtocoloInducaoLactacao.nome)).all()
    return [_serializar_protocolo_inducao(session, p) for p in protocolos]


@router.post("/protocolos-inducao-lactacao")
def criar_protocolo_inducao(dados: ProtocoloInducaoIn, session: Session = Depends(get_session)) -> dict:
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    if session.exec(select(ProtocoloInducaoLactacao).where(ProtocoloInducaoLactacao.nome == nome)).first():
        raise HTTPException(status_code=409, detail=f"Já existe um protocolo com o nome '{nome}'")
    _validar_etapas_inducao(dados.etapas)

    protocolo = ProtocoloInducaoLactacao(
        nome=nome, dia_inicial=dados.dia_inicial, observacao=dados.observacao, ativo=dados.ativo,
    )
    session.add(protocolo)
    session.commit()
    session.refresh(protocolo)
    for etapa in dados.etapas:
        session.add(ProtocoloInducaoLactacaoEtapa(protocolo_id=protocolo.id, **etapa.model_dump()))
    session.commit()
    return _serializar_protocolo_inducao(session, protocolo)


@router.put("/protocolos-inducao-lactacao/{protocolo_id}")
def atualizar_protocolo_inducao(protocolo_id: int, dados: ProtocoloInducaoIn, session: Session = Depends(get_session)) -> dict:
    protocolo = session.get(ProtocoloInducaoLactacao, protocolo_id)
    if not protocolo:
        raise HTTPException(status_code=404, detail="Protocolo não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    _validar_etapas_inducao(dados.etapas)

    protocolo.nome = nome
    protocolo.dia_inicial = dados.dia_inicial
    protocolo.observacao = dados.observacao
    protocolo.ativo = dados.ativo
    session.add(protocolo)

    etapas_antigas = session.exec(
        select(ProtocoloInducaoLactacaoEtapa).where(ProtocoloInducaoLactacaoEtapa.protocolo_id == protocolo_id)
    ).all()
    for e in etapas_antigas:
        session.delete(e)
    session.commit()
    for etapa in dados.etapas:
        session.add(ProtocoloInducaoLactacaoEtapa(protocolo_id=protocolo.id, **etapa.model_dump()))
    session.commit()
    return _serializar_protocolo_inducao(session, protocolo)


# Cronograma das duas planilhas do produtor ("Protocolo Ativos 1" — 28 dias,
# D1 a D28, e manutenção da bST depois disso — e "Protocolo Ativos 2" — 18
# dias, D0 a D18). Doses/unidades e dias vêm literalmente das planilhas
# anexadas; "Somatotropina Bovina (bST)" não tinha princípio ativo cadastrado
# — foi criado aqui para compatibilizar com o restante do sistema (mesmo
# grupo/categoria dos demais hormônios reprodutivos).
SEED_PRINCIPIOS_INDUCAO = ["Somatotropina Bovina (bST)"]

# (dia, tipo, produto/principio, acao_dispositivo, dose, unidade, via)
SEED_ETAPAS_INDUCAO_1 = [
    (1, "medicamento", "Somatotropina Bovina (bST)", None, None, "dose", None),
    (1, "medicamento", "Benzoato de Estradiol", None, 30, "ml", None),
    (1, "dispositivo", "Implante de Progesterona", "colocar", None, None, None),
    (2, "medicamento", "Benzoato de Estradiol", None, 30, "ml", None),
    (3, "medicamento", "Benzoato de Estradiol", None, 30, "ml", None),
    (4, "medicamento", "Benzoato de Estradiol", None, 30, "ml", None),
    (5, "medicamento", "Benzoato de Estradiol", None, 30, "ml", None),
    (6, "medicamento", "Benzoato de Estradiol", None, 30, "ml", None),
    (7, "medicamento", "Benzoato de Estradiol", None, 30, "ml", None),
    (8, "medicamento", "Somatotropina Bovina (bST)", None, None, "dose", None),
    (8, "medicamento", "Benzoato de Estradiol", None, 20, "ml", None),
    (8, "dispositivo", "Implante de Progesterona", "retirar", None, None, None),
    (9, "medicamento", "Benzoato de Estradiol", None, 20, "ml", None),
    (10, "medicamento", "Benzoato de Estradiol", None, 20, "ml", None),
    (11, "medicamento", "Benzoato de Estradiol", None, 20, "ml", None),
    (12, "medicamento", "Benzoato de Estradiol", None, 20, "ml", None),
    (13, "medicamento", "Benzoato de Estradiol", None, 20, "ml", None),
    (14, "medicamento", "Benzoato de Estradiol", None, 20, "ml", None),
    (15, "medicamento", "Somatotropina Bovina (bST)", None, None, "dose", None),
    (15, "medicamento", "Benzoato de Estradiol", None, 20, "ml", None),
    (16, "medicamento", "Cloprostenol Sódico / D-Cloprostenol", None, 3, "ml", None),
    (17, "manejo", "Adaptação na ordenha", None, None, None, None),
    (18, "manejo", "Adaptação na ordenha", None, None, None, None),
    (19, "medicamento", "Dexametasona", None, 20, "ml", None),
    (19, "manejo", "Adaptação na ordenha", None, None, None, None),
    (20, "medicamento", "Dexametasona", None, 20, "ml", None),
    (20, "manejo", "Adaptação na ordenha", None, None, None, None),
    (21, "medicamento", "Somatotropina Bovina (bST)", None, None, "dose", None),
    (21, "medicamento", "Dexametasona", None, 20, "ml", None),
    (21, "manejo", "Adaptação na ordenha", None, None, None, None),
    (22, "manejo", "COMEÇAR A ORDENHA", None, None, None, None),
    (28, "medicamento", "Somatotropina Bovina (bST)", None, None, "dose", None),
]

SEED_ETAPAS_INDUCAO_2 = [
    (0, "medicamento", "Somatotropina Bovina (bST)", None, None, "dose", None),
    (0, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (0, "dispositivo", "Implante de Progesterona", "colocar", None, None, None),
    (2, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (4, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (6, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (8, "medicamento", "Somatotropina Bovina (bST)", None, None, "dose", None),
    (8, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (10, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (12, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (14, "medicamento", "Somatotropina Bovina (bST)", None, None, "dose", None),
    (14, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (15, "medicamento", "Cloprostenol Sódico / D-Cloprostenol", None, None, "dose", None),
    (15, "medicamento", "Dexametasona", None, 10, "ml", None),
    (15, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (15, "dispositivo", "Implante de Progesterona", "retirar", None, None, None),
    (16, "medicamento", "Dexametasona", None, 10, "ml", None),
    (16, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (17, "medicamento", "Dexametasona", None, 10, "ml", None),
    (17, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (18, "manejo", "INICIAR A ORDENHA", None, None, None, None),
]


def seed_protocolos_inducao_lactacao(session: Session) -> None:
    """
    Cadastra os dois protocolos de indução de lactação (18 e 28 dias) a partir
    das planilhas do produtor, por princípio ativo. Roda UMA vez (SeedFlag) —
    depois disso os dois protocolos ficam livres para o usuário editar/excluir
    em Configurações > Cadastro, sem que reinicializações apaguem as edições.
    """
    chave = "protocolos_inducao_lactacao_v1"
    if session.get(SeedFlag, chave):
        return

    for nome_pa in SEED_PRINCIPIOS_INDUCAO:
        if not session.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == nome_pa)).first():
            session.add(PrincipioAtivo(nome=nome_pa, categoria="Fármacos Reprodutivos e Hormônios"))
    session.commit()

    principios_por_nome = {p.nome: p.id for p in session.exec(select(PrincipioAtivo)).all()}

    def _criar(nome: str, dia_inicial: int, observacao: str, etapas: list[tuple]) -> None:
        if session.exec(select(ProtocoloInducaoLactacao).where(ProtocoloInducaoLactacao.nome == nome)).first():
            return
        protocolo = ProtocoloInducaoLactacao(nome=nome, dia_inicial=dia_inicial, observacao=observacao)
        session.add(protocolo)
        session.commit()
        session.refresh(protocolo)
        for dia, tipo, produto, acao, dose, unidade, via in etapas:
            session.add(ProtocoloInducaoLactacaoEtapa(
                protocolo_id=protocolo.id, dia=dia, tipo=tipo, produto=produto,
                principio_ativo_id=principios_por_nome.get(produto) if tipo == "medicamento" else None,
                acao_dispositivo=acao, dose=dose, unidade=unidade, via=via,
            ))
        session.commit()

    _criar(
        "Protocolo de Indução de Lactação — 28 dias (Ativos 1)", 1,
        "Manter a bST (Somatotropina Bovina) a cada 12 dias até o final da lactação — "
        "a partir do D28 a vaca entra no ciclo normal de aplicação de bST do rebanho (Sanidade > Preventiva > BST).",
        SEED_ETAPAS_INDUCAO_1,
    )
    _criar(
        "Protocolo de Indução de Lactação — 18 dias (Ativos 2)", 0,
        "Protocolo intensivo (63 animais) — aplicações em dias alternados; nos dias de INTERVALO não há nenhuma etapa.",
        SEED_ETAPAS_INDUCAO_2,
    )

    session.add(SeedFlag(chave=chave))
    session.commit()
