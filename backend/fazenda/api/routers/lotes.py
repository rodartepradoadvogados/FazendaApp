"""
Router de lotes — cadastro de lotes de manejo, seus parâmetros (faixa de DEL,
produção etc.) e os critérios de seleção de animais (cumulativos), usados hoje
pela tela de Configurações > Cadastro e, no futuro, pelo motor de sugestão
automática de movimentação.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal, Lote, PesagemCorporal, Sanidade, Servico
from fazenda.rules.lote_criterios import animal_atende_criterios

router = APIRouter(prefix="/lotes", tags=["lotes"])


def _rotulo(codigo: str, nome: str) -> str:
    return f"{codigo} - {nome}"


class LoteIn(BaseModel):
    codigo: str
    nome: str
    del_min: int | None = None
    del_max: int | None = None
    producao_min: float | None = None
    producao_max: float | None = None
    # Critérios de seleção (cumulativos) — ver fazenda.rules.lote_criterios.
    status_lactacao: str | None = None
    categorias: str | None = None
    pre_parto: bool | None = None
    peso_min: float | None = None
    peso_max: float | None = None
    dias_para_parto_min: int | None = None
    dias_para_parto_max: int | None = None
    em_tratamento: bool | None = None
    idade_dias_min: int | None = None
    idade_dias_max: int | None = None
    novilhas_inseminadas: bool | None = None
    novilhas_gestantes: bool | None = None


def _validar_faixas(dados: LoteIn) -> None:
    pares = [
        (dados.del_min, dados.del_max, "DEL"),
        (dados.producao_min, dados.producao_max, "Produção"),
        (dados.peso_min, dados.peso_max, "Peso"),
        (dados.dias_para_parto_min, dados.dias_para_parto_max, "Dias para o parto"),
        (dados.idade_dias_min, dados.idade_dias_max, "Idade em dias"),
    ]
    for minimo, maximo, nome in pares:
        if minimo is not None and maximo is not None and minimo > maximo:
            raise HTTPException(status_code=400, detail=f"{nome} mínimo não pode ser maior que o máximo")


def _aplicar_campos(lote: Lote, dados: LoteIn) -> None:
    lote.del_min = dados.del_min
    lote.del_max = dados.del_max
    lote.producao_min = dados.producao_min
    lote.producao_max = dados.producao_max
    lote.status_lactacao = dados.status_lactacao
    lote.categorias = dados.categorias
    lote.pre_parto = dados.pre_parto
    lote.peso_min = dados.peso_min
    lote.peso_max = dados.peso_max
    lote.dias_para_parto_min = dados.dias_para_parto_min
    lote.dias_para_parto_max = dados.dias_para_parto_max
    lote.em_tratamento = dados.em_tratamento
    lote.idade_dias_min = dados.idade_dias_min
    lote.idade_dias_max = dados.idade_dias_max
    lote.novilhas_inseminadas = dados.novilhas_inseminadas
    lote.novilhas_gestantes = dados.novilhas_gestantes


@router.get("/")
def listar_lotes(session: Session = Depends(get_session)) -> list[dict]:
    lotes = session.exec(select(Lote).order_by(Lote.codigo)).all()
    animais = session.exec(select(Animal).where(Animal.ativo == True)).all()  # noqa: E712
    contagem: dict[str, int] = {}
    for a in animais:
        if a.eh_semen or a.sexo == "M" or not a.grupo_primario:
            continue
        codigo = a.grupo_primario[:2] if a.grupo_primario[:2].isdigit() else a.grupo_primario
        contagem[codigo] = contagem.get(codigo, 0) + 1

    saida = []
    for lote in lotes:
        d = lote.model_dump()
        d["rotulo"] = _rotulo(lote.codigo, lote.nome)
        d["qtd_animais"] = contagem.get(lote.codigo, 0)
        saida.append(d)
    return saida


@router.post("/")
def criar_lote(dados: LoteIn, session: Session = Depends(get_session)) -> dict:
    _validar_faixas(dados)
    codigo = dados.codigo.strip()
    if not codigo or not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Código e nome são obrigatórios")
    existente = session.exec(select(Lote).where(Lote.codigo == codigo)).first()
    if existente:
        raise HTTPException(status_code=400, detail=f"Já existe um lote com o código {codigo}")

    lote = Lote(codigo=codigo, nome=dados.nome.strip())
    _aplicar_campos(lote, dados)
    session.add(lote)
    session.commit()
    session.refresh(lote)
    return lote.model_dump()


@router.put("/{lote_id}")
def atualizar_lote(lote_id: int, dados: LoteIn, session: Session = Depends(get_session)) -> dict:
    _validar_faixas(dados)
    lote = session.get(Lote, lote_id)
    if not lote:
        raise HTTPException(status_code=404, detail="Lote não encontrado")

    nome_antigo = lote.nome
    lote.nome = dados.nome.strip() or lote.nome
    _aplicar_campos(lote, dados)
    lote.atualizado_em = datetime.utcnow()
    session.add(lote)

    # Renomeou o lote: atualiza o rótulo de todos os animais que estão nele hoje,
    # para o cadastro e o rebanho não ficarem com nomes divergentes.
    if lote.nome != nome_antigo:
        rotulo_novo = _rotulo(lote.codigo, lote.nome)
        animais = session.exec(select(Animal).where(Animal.grupo_primario != None)).all()  # noqa: E711
        for a in animais:
            if (a.grupo_primario or "")[:2] == lote.codigo:
                a.grupo_primario = rotulo_novo
                session.add(a)

    session.commit()
    session.refresh(lote)
    return lote.model_dump()


@router.post("/preview")
def preview_criterios(dados: LoteIn, session: Session = Depends(get_session)) -> dict:
    """
    Prévia de quantos e quais animais atendem aos critérios informados (sem
    precisar salvar o lote) — cumulativos, em E lógico.
    """
    _validar_faixas(dados)
    lote_temp = Lote(codigo=dados.codigo or "?", nome=dados.nome or "?")
    _aplicar_campos(lote_temp, dados)

    hoje = date.today()
    animais = [
        a for a in session.exec(select(Animal).where(Animal.ativo == True)).all()  # noqa: E712
        if not a.eh_semen and a.sexo != "M"
    ]

    servicos_por_animal: dict[str, list[dict]] = {}
    for s in session.exec(select(Servico)).all():
        servicos_por_animal.setdefault(s.numero_matriz, []).append(s.model_dump())

    sanidades_por_animal: dict[str, list[dict]] = {}
    for s in session.exec(select(Sanidade)).all():
        sanidades_por_animal.setdefault(s.numero_matriz, []).append(s.model_dump())

    peso_por_animal: dict[str, float] = {}
    pesagens = session.exec(select(PesagemCorporal)).all()
    ultima_data: dict[str, date] = {}
    for p in pesagens:
        atual = ultima_data.get(p.numero_matriz)
        if not atual or p.data_pesagem > atual:
            ultima_data[p.numero_matriz] = p.data_pesagem
            peso_por_animal[p.numero_matriz] = p.peso_kg

    atendem = [
        a.numero for a in animais
        if animal_atende_criterios(lote_temp, a.model_dump(), hoje, peso_por_animal, servicos_por_animal, sanidades_por_animal)
    ]
    return {"total": len(atendem), "animais": sorted(atendem)}
