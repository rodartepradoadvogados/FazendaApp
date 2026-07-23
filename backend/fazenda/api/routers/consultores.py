"""
Fase 2C — produto independente do consultor externo (veterinário, contador,
agrônomo, zootecnista): assinatura própria (fora do contrato de qualquer
fazenda), fazendas "gerenciadas" acompanhadas por importação de planilha (o
produtor NÃO precisa ser cliente do sistema), e o modo Simulação (projeto
fictício para aulas/estudos/projeção — calculado na hora, nunca gravado).

Não confundir com fazenda/api/routers/fazendas.py::vincular_usuario
(Fase 2B) — aquele vincula um consultor DENTRO de uma fazenda Diamond já
cliente do sistema. Este router é para o consultor atender produtores que
NÃO usam o sistema: os dados de fazenda_gerenciada/registro_importado
pertencem só a ele (`consultor_usuario_id`), nunca a uma Fazenda tenant.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import EMAIL_DONO, exigir_consultor_ativo, exigir_dono, get_current_user
from fazenda.database import get_session
from fazenda.models import ContratoConsultor, FazendaGerenciada, RegistroImportado, Usuario
from fazenda.models.consultores import CATEGORIAS_IMPORTACAO, PLANOS_CONSULTOR_CATALOGO
from fazenda.parsers.utils import iter_planilha_rows, parse_date

router = APIRouter(prefix="/consultor", tags=["consultor"])


def _publico_contrato(contrato: ContratoConsultor | None, usuario_id: int) -> dict:
    if not contrato:
        return {"usuario_id": usuario_id, "status": None, "plano": None, "limite_fazendas": None}
    return {
        "usuario_id": contrato.usuario_id,
        "status": contrato.status,
        "plano": contrato.plano,
        "limite_fazendas": contrato.limite_fazendas,
        "data_fechamento": contrato.data_fechamento.isoformat() if contrato.data_fechamento else None,
    }


def _meu_contrato(session: Session, usuario_id: int) -> ContratoConsultor | None:
    return session.exec(select(ContratoConsultor).where(ContratoConsultor.usuario_id == usuario_id)).first()


# ---------------------------------------------------------------------------
# Catálogo e assinatura (solicitar/aprovar/suspender) — mesmo ciclo de vida do
# contrato de fazenda (ver fazenda/api/routers/fazendas.py), só que por
# usuário-consultor em vez de fazenda-tenant.
# ---------------------------------------------------------------------------
@router.get("/catalogo/planos")
def listar_planos_consultor_catalogo(_: Usuario = Depends(get_current_user)) -> dict:
    return PLANOS_CONSULTOR_CATALOGO


class SolicitarPlanoIn(BaseModel):
    plano: str


@router.post("/solicitar")
def solicitar_plano_consultor(
    dados: SolicitarPlanoIn, user: Usuario = Depends(get_current_user), session: Session = Depends(get_session),
) -> dict:
    """O próprio usuário escolhe um plano de consultor — fica aguardando
    aprovação até você (dono) aprovar (POST /{usuario_id}/aprovar). Chamar de
    novo com outro plano (upgrade/downgrade) volta para aguardando_aprovacao,
    mesmo que já estivesse ativo — evita liberar um limite maior sem você
    revisar/fechar de novo."""
    if dados.plano not in PLANOS_CONSULTOR_CATALOGO:
        raise HTTPException(status_code=400, detail=f"Plano inválido: {dados.plano}")
    pacote = PLANOS_CONSULTOR_CATALOGO[dados.plano]
    contrato = _meu_contrato(session, user.id)
    if not contrato:
        contrato = ContratoConsultor(usuario_id=user.id, plano=dados.plano, limite_fazendas=pacote["limite_fazendas"])
    else:
        contrato.plano = dados.plano
        contrato.limite_fazendas = pacote["limite_fazendas"]
        contrato.status = "aguardando_aprovacao"
        contrato.atualizado_em = datetime.utcnow()
    session.add(contrato)
    session.commit()
    session.refresh(contrato)
    return _publico_contrato(contrato, user.id)


@router.get("/meu-contrato")
def meu_contrato_consultor(user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    return _publico_contrato(_meu_contrato(session, user.id), user.id)


@router.get("/todos")
def listar_contratos_consultor(_: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> list[dict]:
    contratos = session.exec(select(ContratoConsultor)).all()
    resultado = []
    for c in contratos:
        usuario = session.get(Usuario, c.usuario_id)
        resultado.append({**_publico_contrato(c, c.usuario_id), "username": usuario.username if usuario else None})
    return resultado


@router.post("/{usuario_id}/aprovar")
def aprovar_contrato_consultor(
    usuario_id: int, user: Usuario = Depends(exigir_dono), session: Session = Depends(get_session),
) -> dict:
    contrato = _meu_contrato(session, usuario_id)
    if not contrato:
        raise HTTPException(status_code=404, detail="Usuário não solicitou nenhum plano de consultor")
    contrato.status = "ativo"
    contrato.aprovado_por_usuario_id = user.id
    contrato.data_fechamento = datetime.utcnow()
    contrato.atualizado_em = datetime.utcnow()
    session.add(contrato)
    session.commit()
    return _publico_contrato(contrato, usuario_id)


@router.post("/{usuario_id}/suspender")
def suspender_contrato_consultor(
    usuario_id: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session),
) -> dict:
    contrato = _meu_contrato(session, usuario_id)
    if not contrato:
        raise HTTPException(status_code=404, detail="Usuário não tem contrato de consultor")
    contrato.status = "suspenso"
    contrato.atualizado_em = datetime.utcnow()
    session.add(contrato)
    session.commit()
    return _publico_contrato(contrato, usuario_id)


# ---------------------------------------------------------------------------
# Fazendas gerenciadas — cadastro simples do consultor, nunca uma Fazenda
# tenant real (ver fazenda/models/consultores.py).
# ---------------------------------------------------------------------------
class FazendaGerenciadaIn(BaseModel):
    nome: str
    produtor: str | None = None
    cidade: str | None = None
    uf: str | None = None
    observacoes: str | None = None


def _publica_fg(f: FazendaGerenciada) -> dict:
    return {
        "id": f.id, "nome": f.nome, "produtor": f.produtor, "cidade": f.cidade, "uf": f.uf,
        "observacoes": f.observacoes, "criado_em": f.criado_em.isoformat(),
    }


def _minha_fazenda_gerenciada(session: Session, user: Usuario, fazenda_gerenciada_id: int) -> FazendaGerenciada:
    f = session.get(FazendaGerenciada, fazenda_gerenciada_id)
    if not f:
        raise HTTPException(status_code=404, detail="Fazenda gerenciada não encontrada")
    eh_dono = (user.email or "").strip().lower() == EMAIL_DONO
    if not eh_dono and f.consultor_usuario_id != user.id:
        raise HTTPException(status_code=403, detail="Esta fazenda gerenciada não pertence a você")
    return f


@router.post("/fazendas")
def criar_fazenda_gerenciada(
    dados: FazendaGerenciadaIn, user: Usuario = Depends(exigir_consultor_ativo()), session: Session = Depends(get_session),
) -> dict:
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    contrato = _meu_contrato(session, user.id)
    ja_cadastradas = session.exec(
        select(FazendaGerenciada).where(FazendaGerenciada.consultor_usuario_id == user.id)
    ).all()
    if len(ja_cadastradas) >= contrato.limite_fazendas:
        raise HTTPException(
            status_code=403,
            detail=f"Limite de {contrato.limite_fazendas} fazenda(s) do seu plano atingido — contrate um plano maior",
        )
    fazenda = FazendaGerenciada(
        consultor_usuario_id=user.id, nome=nome, produtor=(dados.produtor or "").strip() or None,
        cidade=(dados.cidade or "").strip() or None, uf=(dados.uf or "").strip() or None,
        observacoes=(dados.observacoes or "").strip() or None,
    )
    session.add(fazenda)
    session.commit()
    session.refresh(fazenda)
    return _publica_fg(fazenda)


@router.get("/fazendas")
def listar_fazendas_gerenciadas(
    user: Usuario = Depends(exigir_consultor_ativo()), session: Session = Depends(get_session),
) -> list[dict]:
    fazendas = session.exec(
        select(FazendaGerenciada).where(FazendaGerenciada.consultor_usuario_id == user.id)
    ).all()
    return [_publica_fg(f) for f in fazendas]


@router.delete("/fazendas/{fazenda_gerenciada_id}")
def excluir_fazenda_gerenciada(
    fazenda_gerenciada_id: int, user: Usuario = Depends(exigir_consultor_ativo()), session: Session = Depends(get_session),
) -> dict:
    fazenda = _minha_fazenda_gerenciada(session, user, fazenda_gerenciada_id)
    registros = session.exec(
        select(RegistroImportado).where(RegistroImportado.fazenda_gerenciada_id == fazenda.id)
    ).all()
    for r in registros:
        session.delete(r)
    session.delete(fazenda)
    session.commit()
    return {"excluido": True}


# ---------------------------------------------------------------------------
# Importação de planilha — dados gerenciais de uma fazenda que não usa o
# sistema. Genérico de propósito: cada linha vira um RegistroImportado com
# o dict coluna→valor original (ver fazenda/models/consultores.py).
# ---------------------------------------------------------------------------
@router.get("/categorias-importacao")
def listar_categorias_importacao(_: Usuario = Depends(exigir_consultor_ativo())) -> list[str]:
    return CATEGORIAS_IMPORTACAO


@router.post("/fazendas/{fazenda_gerenciada_id}/importar")
async def importar_planilha_gerenciada(
    fazenda_gerenciada_id: int, file: UploadFile, categoria: str = Form(...),
    user: Usuario = Depends(exigir_consultor_ativo()), session: Session = Depends(get_session),
) -> dict:
    fazenda = _minha_fazenda_gerenciada(session, user, fazenda_gerenciada_id)
    if categoria not in CATEGORIAS_IMPORTACAO:
        raise HTTPException(status_code=400, detail=f"Categoria inválida: {categoria}")
    content = await file.read()
    try:
        linhas = list(iter_planilha_rows(file.filename or "", content))
    except Exception as e:  # noqa: BLE001 — arquivo ilegível vira erro amigável
        raise HTTPException(status_code=400, detail=f"Não consegui ler o arquivo: {e}")
    if not linhas:
        raise HTTPException(status_code=400, detail="Planilha vazia ou sem linhas reconhecíveis")

    # Aceita uma coluna de data com nomes usuais (data/data_referencia/período)
    # para permitir filtrar depois por período nos indicadores — opcional.
    CHAVES_DATA = {"data", "data_referencia", "data referencia", "periodo", "período"}
    criados = 0
    for row in linhas:
        data_referencia: date | None = None
        for chave, valor in row.items():
            if chave.strip().lower() in CHAVES_DATA:
                data_referencia = parse_date(valor)
                break
        session.add(RegistroImportado(
            fazenda_gerenciada_id=fazenda.id, categoria=categoria, data_referencia=data_referencia,
            dados_json=json.dumps(row, ensure_ascii=False), arquivo_origem=file.filename or "planilha",
        ))
        criados += 1
    session.commit()
    return {"categoria": categoria, "criados": criados}


@router.get("/fazendas/{fazenda_gerenciada_id}/indicadores")
def listar_indicadores_importados(
    fazenda_gerenciada_id: int, categoria: str | None = None,
    user: Usuario = Depends(exigir_consultor_ativo()), session: Session = Depends(get_session),
) -> list[dict]:
    fazenda = _minha_fazenda_gerenciada(session, user, fazenda_gerenciada_id)
    query = select(RegistroImportado).where(RegistroImportado.fazenda_gerenciada_id == fazenda.id)
    if categoria:
        query = query.where(RegistroImportado.categoria == categoria)
    registros = session.exec(query).all()
    return [
        {
            "id": r.id, "categoria": r.categoria,
            "data_referencia": r.data_referencia.isoformat() if r.data_referencia else None,
            "dados": json.loads(r.dados_json), "arquivo_origem": r.arquivo_origem,
            "criado_em": r.criado_em.isoformat(),
        }
        for r in registros
    ]


@router.delete("/fazendas/{fazenda_gerenciada_id}/importacoes/{registro_id}")
def excluir_registro_importado(
    fazenda_gerenciada_id: int, registro_id: int,
    user: Usuario = Depends(exigir_consultor_ativo()), session: Session = Depends(get_session),
) -> dict:
    fazenda = _minha_fazenda_gerenciada(session, user, fazenda_gerenciada_id)
    registro = session.get(RegistroImportado, registro_id)
    if not registro or registro.fazenda_gerenciada_id != fazenda.id:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    session.delete(registro)
    session.commit()
    return {"excluido": True}


# ---------------------------------------------------------------------------
# Modo Simulação — projeto fictício para aulas/estudos/projeção de
# resultados. Puro cálculo, NUNCA grava nada no banco (a "sessão" a que o
# usuário se referiu fica só na memória do navegador — ver frontend); aqui
# só devolvemos os indicadores calculados a partir do que foi informado.
# ---------------------------------------------------------------------------
class SimulacaoIn(BaseModel):
    vacas_lactacao: float
    producao_media_litro_vaca_dia: float
    preco_litro: float
    custo_alimentar_vaca_dia: float
    outros_custos_mensais: float = 0.0
    taxa_prenhez_pct: float | None = None


@router.post("/simulacao/calcular")
def calcular_simulacao(dados: SimulacaoIn, _: Usuario = Depends(exigir_consultor_ativo())) -> dict:
    if dados.vacas_lactacao < 0 or dados.producao_media_litro_vaca_dia < 0:
        raise HTTPException(status_code=400, detail="Valores não podem ser negativos")

    producao_total_dia = dados.vacas_lactacao * dados.producao_media_litro_vaca_dia
    producao_total_mes = producao_total_dia * 30
    receita_dia = producao_total_dia * dados.preco_litro
    receita_mes = receita_dia * 30
    custo_alimentar_mes = dados.vacas_lactacao * dados.custo_alimentar_vaca_dia * 30
    custo_total_mes = custo_alimentar_mes + dados.outros_custos_mensais
    margem_mes = receita_mes - custo_total_mes
    custo_por_litro = (custo_total_mes / producao_total_mes) if producao_total_mes else None
    margem_por_litro = (dados.preco_litro - custo_por_litro) if custo_por_litro is not None else None

    return {
        "producao_total_litro_dia": round(producao_total_dia, 2),
        "producao_total_litro_mes": round(producao_total_mes, 2),
        "receita_mes": round(receita_mes, 2),
        "custo_alimentar_mes": round(custo_alimentar_mes, 2),
        "custo_total_mes": round(custo_total_mes, 2),
        "margem_mes": round(margem_mes, 2),
        "custo_por_litro": round(custo_por_litro, 4) if custo_por_litro is not None else None,
        "margem_por_litro": round(margem_por_litro, 4) if margem_por_litro is not None else None,
        "taxa_prenhez_pct": dados.taxa_prenhez_pct,
    }
