"""
Router de upload de CSV — recebe arquivos do Ideagri e faz upsert no banco.
Endpoint: POST /upload/{tipo}
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal, ContaGerencial, ControleLeiteiro, Dieta, Estoque, Sanidade, Servico, Parto
from fazenda.parsers.conta_gerencial import parse_conta_gerencial
from fazenda.parsers.controle_leiteiro import parse_controle_leiteiro
from fazenda.parsers.dieta import parse_dieta
from fazenda.parsers.estoque import parse_estoque
from fazenda.parsers.geral import parse_geral
from fazenda.parsers.reprodutivo import parse_reprodutivo
from fazenda.parsers.sanidade import parse_sanidade

router = APIRouter(prefix="/upload", tags=["upload"])

TIPOS_VALIDOS = ("geral", "reprodutivo", "conta_gerencial", "estoque", "dieta", "controle_leiteiro", "sanidade")


@router.post("/{tipo}")
async def upload_csv(
    tipo: str,
    file: UploadFile,
    session: Session = Depends(get_session),
):
    """
    Recebe um arquivo CSV do Ideagri e realiza o upsert no banco.

    Tipos suportados:
    - geral: GERAL.csv
    - reprodutivo: Consulta_SQL_Dados_Reprodutivos_e_Produtivos_Versao_8.csv
    - conta_gerencial: CONTA_GERENCIAL.csv
    - estoque: ESTOQUE.csv
    """
    if tipo not in TIPOS_VALIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo '{tipo}' inválido. Use: {', '.join(TIPOS_VALIDOS)}",
        )

    content = await file.read()

    try:
        if tipo == "geral":
            return await _upsert_geral(content, session)
        elif tipo == "reprodutivo":
            return await _upsert_reprodutivo(content, session)
        elif tipo == "conta_gerencial":
            return await _upsert_conta_gerencial(content, session)
        elif tipo == "estoque":
            return await _upsert_estoque(content, session)
        elif tipo == "dieta":
            return await _upsert_dieta(content, session)
        elif tipo == "controle_leiteiro":
            return await _upsert_controle_leiteiro(content, session)
        elif tipo == "sanidade":
            return await _upsert_sanidade(content, session)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _upsert_geral(content: bytes, session: Session) -> dict:
    animais = parse_geral(content)
    inserted, updated = 0, 0

    for animal_novo in animais:
        existing = session.exec(
            select(Animal).where(Animal.numero == animal_novo.numero)
        ).first()

        if existing:
            # Atualiza campos
            for field in animal_novo.model_fields_set:
                setattr(existing, field, getattr(animal_novo, field))
            session.add(existing)
            updated += 1
        else:
            session.add(animal_novo)
            inserted += 1

    session.commit()
    return {"tipo": "geral", "inseridos": inserted, "atualizados": updated, "total": len(animais)}


async def _upsert_reprodutivo(content: bytes, session: Session) -> dict:
    servicos, partos = parse_reprodutivo(content)

    # Limpa e reinserere (sem chave natural complexa nos serviços — recria a cada upload)
    session.exec(select(Servico)).all()  # warmup
    for s in session.exec(select(Servico)).all():
        session.delete(s)
    session.commit()

    for servico in servicos:
        # Vincula ao animal se existir
        animal = session.exec(
            select(Animal).where(Animal.numero == servico.numero_matriz)
        ).first()
        if animal:
            servico.animal_id = animal.id
        session.add(servico)

    for parto in partos:
        animal = session.exec(
            select(Animal).where(Animal.numero == parto.numero_matriz)
        ).first()
        if animal:
            parto.animal_id = animal.id
        session.add(parto)

    session.commit()
    return {
        "tipo": "reprodutivo",
        "servicos": len(servicos),
        "partos": len(partos),
    }


async def _upsert_conta_gerencial(content: bytes, session: Session) -> dict:
    contas = parse_conta_gerencial(content)

    # Limpa e reinserere (dados financeiros são sempre re-importados com janela completa)
    for c in session.exec(select(ContaGerencial)).all():
        session.delete(c)
    session.commit()

    for conta in contas:
        session.add(conta)

    session.commit()
    return {"tipo": "conta_gerencial", "registros": len(contas)}


async def _upsert_estoque(content: bytes, session: Session) -> dict:
    items = parse_estoque(content)

    for c in session.exec(select(Estoque)).all():
        session.delete(c)
    session.commit()

    for item in items:
        session.add(item)

    session.commit()
    return {"tipo": "estoque", "registros": len(items)}


async def _upsert_dieta(content: bytes, session: Session) -> dict:
    itens = parse_dieta(content)

    for d in session.exec(select(Dieta)).all():
        session.delete(d)
    session.commit()

    for item in itens:
        session.add(item)

    session.commit()
    lotes = len({i.lote for i in itens if i.lote is not None})
    return {"tipo": "dieta", "registros": len(itens), "lotes": lotes}


async def _upsert_sanidade(content: bytes, session: Session) -> dict:
    registros = parse_sanidade(content)

    # Re-importação completa (histórico é sempre reenviado atualizado do Ideagri).
    for s in session.exec(select(Sanidade)).all():
        session.delete(s)
    session.commit()

    for reg in registros:
        session.add(reg)

    session.commit()
    animais = len({r.numero_matriz for r in registros})
    return {"tipo": "sanidade", "registros": len(registros), "animais": animais}


async def _upsert_controle_leiteiro(content: bytes, session: Session) -> dict:
    registros = parse_controle_leiteiro(content)

    # Re-importação completa (histórico é sempre reenviado com a janela escolhida).
    for r in session.exec(select(ControleLeiteiro)).all():
        session.delete(r)
    session.commit()

    for reg in registros:
        animal = session.exec(
            select(Animal).where(Animal.numero == reg.numero_matriz)
        ).first()
        if animal:
            reg.animal_id = animal.id
        session.add(reg)

    session.commit()
    vacas = len({r.numero_matriz for r in registros})
    return {"tipo": "controle_leiteiro", "registros": len(registros), "vacas": vacas}
