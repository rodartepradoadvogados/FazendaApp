"""
Router de reprodução — dados achatados para o dashboard interativo de análise
e lançamento de diagnóstico de gestação.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal, Parto, PesagemCorporal, Servico
from fazenda.rules.agenda_veterinario import classificar_rebanho
from fazenda.rules.reproducao_analise import analisar_servicos

router = APIRouter(prefix="/reproducao", tags=["reproducao"])


@router.get("/agenda-veterinario")
def agenda_veterinario(session: Session = Depends(get_session)) -> dict:
    """
    Roteiro do veterinário do serviço: classifica o rebanho fêmea em 9 listas
    (ver fazenda.rules.agenda_veterinario para os critérios de cada uma).
    """
    hoje = date.today()
    animais = [
        a.model_dump() for a in session.exec(select(Animal).where(Animal.ativo == True)).all()  # noqa: E712
    ]

    servico_por_animal: dict[str, dict] = {}
    for s in session.exec(select(Servico)).all():
        atual = servico_por_animal.get(s.numero_matriz)
        if not atual or (s.data_servico and (not atual.get("data_servico") or s.data_servico > atual["data_servico"])):
            servico_por_animal[s.numero_matriz] = s.model_dump()

    peso_por_animal: dict[str, float] = {}
    ultima_data: dict[str, date] = {}
    for p in session.exec(select(PesagemCorporal)).all():
        atual = ultima_data.get(p.numero_matriz)
        if not atual or p.data_pesagem > atual:
            ultima_data[p.numero_matriz] = p.data_pesagem
            peso_por_animal[p.numero_matriz] = p.peso_kg

    listas = classificar_rebanho(animais, servico_por_animal, peso_por_animal, hoje)
    return {"data_referencia": hoje.isoformat(), "listas": listas, "totais": {k: len(v) for k, v in listas.items()}}


@router.get("/servicos")
def listar_servicos_analise(session: Session = Depends(get_session)) -> dict:
    """
    Todos os serviços achatados com as dimensões da análise reprodutiva
    (concepção/perda por categoria, raça, ordem de parto/tentativa, condição
    de IA, inseminador, mês, DEL). O front filtra/agrega no cliente.
    """
    servicos = [s.model_dump() for s in session.exec(select(Servico)).all()]
    registros = analisar_servicos(servicos)
    return {"servicos": registros, "total": len(registros)}


class DiagnosticoIn(BaseModel):
    numero_matriz: str
    data_diagnostico: date
    resultado: str  # "retoque" | "reconfirmada" | "negativo"
    metodo: str | None = None


@router.post("/diagnostico")
def registrar_diagnostico(dados: DiagnosticoIn, session: Session = Depends(get_session)) -> dict:
    """
    Registra o resultado do diagnóstico de gestação no serviço mais recente da
    matriz. Se marcado "retoque", o lembrete de reconfirmação entra na agenda
    na data do próximo serviço (agenda_engine.py).
    """
    if dados.resultado not in ("retoque", "reconfirmada", "negativo"):
        raise HTTPException(status_code=400, detail="Resultado inválido")

    servico = session.exec(
        select(Servico)
        .where(Servico.numero_matriz == dados.numero_matriz)
        .order_by(Servico.data_servico.desc())
    ).first()
    if not servico:
        raise HTTPException(status_code=404, detail=f"Nenhum serviço encontrado para a matriz {dados.numero_matriz}")

    servico.data_diagnostico = dados.data_diagnostico
    if dados.resultado == "retoque":
        servico.diagnostico = "POSITIVO"
        servico.retoque = True
    elif dados.resultado == "reconfirmada":
        servico.diagnostico = "POSITIVO"
        servico.retoque = False
    else:
        servico.diagnostico = "NEGATIVO"
        servico.retoque = False

    session.add(servico)
    session.commit()
    session.refresh(servico)
    return servico.model_dump()


class ReconfirmacaoIn(BaseModel):
    numero_matriz: str
    data_reconfirmacao: date
    resultado: str  # "positivo" | "negativo"


@router.post("/reconfirmacao")
def registrar_reconfirmacao(dados: ReconfirmacaoIn, session: Session = Depends(get_session)) -> dict:
    """
    Segundo exame (reconfirmação, ~60 dias do serviço) — distinto do primeiro
    toque. Usado pela agenda do veterinário para tirar o animal de "atrasada
    para reconfirmação" e classificá-lo como gestante confirmada.
    """
    if dados.resultado not in ("positivo", "negativo"):
        raise HTTPException(status_code=400, detail="Resultado inválido")

    servico = session.exec(
        select(Servico)
        .where(Servico.numero_matriz == dados.numero_matriz)
        .order_by(Servico.data_servico.desc())
    ).first()
    if not servico:
        raise HTTPException(status_code=404, detail=f"Nenhum serviço encontrado para a matriz {dados.numero_matriz}")

    servico.data_reconfirmacao = dados.data_reconfirmacao
    servico.diagnostico_reconfirmacao = "POSITIVO" if dados.resultado == "positivo" else "NEGATIVO"
    servico.retoque = False

    session.add(servico)
    session.commit()
    session.refresh(servico)
    return servico.model_dump()


class CriaIn(BaseModel):
    numero: str
    sexo: str  # "F" | "M"
    nasceu_viva: bool = True


class PartoIn(BaseModel):
    numero_matriz: str
    data_parto: date
    tipo_parto: str | None = None
    crias: list[CriaIn] = []
    retencao_placenta: bool | None = None
    gemelar: bool | None = None
    observacao: str | None = None


@router.post("/parto")
def registrar_parto(dados: PartoIn, session: Session = Depends(get_session)) -> dict:
    """
    Registra o parto e cria a ficha de cada cria nascida viva ainda não
    cadastrada. Não move ninguém de lote sozinho — o front sugere o lote via
    /producao/sugestao-lote-evento e só move (POST /movimentacoes/mover) com
    confirmação explícita do usuário.
    """
    mae = session.exec(select(Animal).where(Animal.numero == dados.numero_matriz)).first()
    if not mae:
        raise HTTPException(status_code=404, detail="Matriz não encontrada")

    ultimo_parto = session.exec(
        select(Parto).where(Parto.numero_matriz == dados.numero_matriz).order_by(Parto.ordem_parto.desc())
    ).first()
    ordem_parto = (ultimo_parto.ordem_parto or 0) + 1 if ultimo_parto else 1

    parto = Parto(
        animal_id=mae.id,
        numero_matriz=dados.numero_matriz,
        data_parto=dados.data_parto,
        ordem_parto=ordem_parto,
        tipo_parto=dados.tipo_parto,
        sexo_cria_1=dados.crias[0].sexo if len(dados.crias) > 0 else None,
        sexo_cria_2=dados.crias[1].sexo if len(dados.crias) > 1 else None,
        gemelar=dados.gemelar if dados.gemelar is not None else len(dados.crias) > 1,
        retencao_placenta=dados.retencao_placenta,
    )
    session.add(parto)

    crias_criadas = []
    for cria in dados.crias:
        if not cria.nasceu_viva:
            continue
        if session.exec(select(Animal).where(Animal.numero == cria.numero)).first():
            continue  # já cadastrada — não sobrescreve
        session.add(Animal(
            numero=cria.numero, sexo=cria.sexo, raca=mae.raca, data_nasc=dados.data_parto,
            mae_numero=mae.numero, mae_nome=mae.nome, ativo=True,
        ))
        crias_criadas.append(cria.numero)

    # DEL reseta ao parir — o resto da ficha (categoria, produção etc.) só é
    # atualizado de fato no próximo upload do GERAL.csv.
    mae.del_dias = 0
    mae.atualizado_em = datetime.utcnow()
    session.add(mae)

    session.commit()
    return {"criado": True, "ordem_parto": ordem_parto, "crias_criadas": crias_criadas}
