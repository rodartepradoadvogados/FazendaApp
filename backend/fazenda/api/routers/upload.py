"""
Router de upload de CSV — recebe arquivos do Ideagri e faz upsert no banco.
Endpoint: POST /upload/{tipo}

ISOLAMENTO POR FAZENDA (Fase 0): quase todo tipo de upload aqui é
"apaga tudo e reimporta" — o Ideagri sempre reenvia o histórico completo.
Sem filtro de fazenda, subir o CSV de UMA fazenda apagava os dados de TODAS
as outras (Servico, Sanidade, Estoque, Dieta, ControleLeiteiro,
ContaGerencial, CurvaABC, Patrimônio, PlanoContaGerencial). Agora todo
delete é escopado pela fazenda atual e toda linha inserida é carimbada com
ela — ver `_escopo` e `_carimbar` abaixo.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.models import (
    Animal,
    ContaGerencial,
    ControleLeiteiro,
    CurvaABC,
    Dieta,
    Estoque,
    Patrimonio,
    PlanoContaGerencial,
    Sanidade,
    Servico,
    Parto,
)
from fazenda.parsers.conta_gerencial import parse_conta_gerencial
from fazenda.parsers.controle_leiteiro import parse_controle_leiteiro
from fazenda.parsers.curva_abc import parse_curva_abc
from fazenda.parsers.dieta import parse_dieta
from fazenda.parsers.estoque import parse_estoque
from fazenda.parsers.geral import parse_geral
from fazenda.parsers.patrimonio import parse_patrimonio
from fazenda.parsers.plano_conta_gerencial import parse_plano_conta_gerencial
from fazenda.parsers.reprodutivo import parse_reprodutivo
from fazenda.parsers.sanidade import parse_sanidade

router = APIRouter(prefix="/upload", tags=["upload"])

TIPOS_VALIDOS = (
    "geral", "reprodutivo", "conta_gerencial", "estoque", "dieta", "controle_leiteiro",
    "sanidade", "curva_abc", "plano_conta_gerencial", "patrimonio",
)


def _escopo(query, modelo, fazenda_id: int | None):
    """Restringe a varredura de "apaga tudo antes de reimportar" à fazenda
    atual. `fazenda_id is None` = token legado sem fazenda selecionada: mantém
    o comportamento global de antes (não quebra instalação de fazenda única).

    Inclui as linhas com `fazenda_id IS NULL` (dados anteriores ao retrofit
    multi-fazenda) — senão cada upload deixaria para trás um histórico órfão
    que nunca mais seria substituído, duplicando tudo na tela.
    """
    if fazenda_id is None:
        return query
    return query.where(modelo.fazenda_id.in_((fazenda_id, None)))


def _carimbar(linhas, fazenda_id: int | None):
    """Carimba a fazenda atual em cada linha recém-parseada do CSV — sem isso
    a reimportação seguinte não acharia (nem substituiria) o que acabou de
    entrar, e o dado ficaria visível para as outras fazendas."""
    if fazenda_id is not None:
        for linha in linhas:
            linha.fazenda_id = fazenda_id
    return linhas


@router.post("/{tipo}")
async def upload_csv(
    tipo: str,
    file: UploadFile,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
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
    fazenda_id = fazenda_id_seguro(fazenda_id)

    try:
        if tipo == "geral":
            return await _upsert_geral(content, session, fazenda_id)
        elif tipo == "reprodutivo":
            return await _upsert_reprodutivo(content, session, fazenda_id)
        elif tipo == "conta_gerencial":
            return await _upsert_conta_gerencial(content, session, fazenda_id)
        elif tipo == "estoque":
            return await _upsert_estoque(content, session, fazenda_id)
        elif tipo == "dieta":
            return await _upsert_dieta(content, session, fazenda_id)
        elif tipo == "controle_leiteiro":
            return await _upsert_controle_leiteiro(content, session, fazenda_id)
        elif tipo == "sanidade":
            return await _upsert_sanidade(content, session, fazenda_id)
        elif tipo == "curva_abc":
            return await _upsert_curva_abc(content, session, fazenda_id)
        elif tipo == "plano_conta_gerencial":
            return await _upsert_plano_conta_gerencial(content, session, fazenda_id)
        elif tipo == "patrimonio":
            return await _upsert_patrimonio(content, session, fazenda_id)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _upsert_curva_abc(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    linhas = parse_curva_abc(content)
    for antigo in session.exec(_escopo(select(CurvaABC), CurvaABC, fazenda_id)).all():
        session.delete(antigo)
    for linha in _carimbar(linhas, fazenda_id):
        session.add(linha)
    session.commit()
    return {"tipo": "curva_abc", "registros": len(linhas)}


async def _upsert_plano_conta_gerencial(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    contas = parse_plano_conta_gerencial(content)
    for antigo in session.exec(_escopo(select(PlanoContaGerencial), PlanoContaGerencial, fazenda_id)).all():
        session.delete(antigo)
    session.commit()
    for conta in _carimbar(contas, fazenda_id):
        session.add(conta)
    session.commit()
    return {"tipo": "plano_conta_gerencial", "registros": len(contas)}


async def _upsert_patrimonio(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    itens = parse_patrimonio(content)
    for antigo in session.exec(_escopo(select(Patrimonio), Patrimonio, fazenda_id)).all():
        session.delete(antigo)
    session.commit()
    for item in _carimbar(itens, fazenda_id):
        session.add(item)
    session.commit()
    return {"tipo": "patrimonio", "registros": len(itens)}


async def _upsert_geral(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    animais = _carimbar(parse_geral(content), fazenda_id)
    inserted, updated = 0, 0

    for animal_novo in animais:
        # `numero` NÃO é único entre fazendas — a vaca "18" existe em várias.
        # Sem o escopo, o upload de uma fazenda sobrescrevia a ficha da vaca
        # de mesmo número de outra.
        existing = session.exec(
            _escopo(select(Animal).where(Animal.numero == animal_novo.numero), Animal, fazenda_id)
        ).first()

        if existing:
            # Atualiza campos — exceto o lote, se ele já foi definido manualmente
            # (ver Animal.grupo_manual): uma movimentação feita no site não pode
            # ser silenciosamente revertida pelo próximo upload do GERAL.csv.
            for field in animal_novo.model_fields_set:
                if field in ("grupo_primario", "grupo_raw") and existing.grupo_manual:
                    continue
                setattr(existing, field, getattr(animal_novo, field))
            session.add(existing)
            updated += 1
        else:
            session.add(animal_novo)
            inserted += 1

    session.commit()
    return {"tipo": "geral", "inseridos": inserted, "atualizados": updated, "total": len(animais)}


async def _upsert_reprodutivo(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    servicos, partos = parse_reprodutivo(content)
    _carimbar(servicos, fazenda_id)
    _carimbar(partos, fazenda_id)

    # Limpa e reinserere (sem chave natural complexa nos serviços — recria a cada upload)
    for s in session.exec(_escopo(select(Servico), Servico, fazenda_id)).all():
        session.delete(s)
    session.commit()

    for servico in servicos:
        # Vincula ao animal se existir — dentro da fazenda, senão pegaria o
        # animal de mesmo número de outra fazenda.
        animal = session.exec(
            _escopo(select(Animal).where(Animal.numero == servico.numero_matriz), Animal, fazenda_id)
        ).first()
        if animal:
            servico.animal_id = animal.id
        session.add(servico)

    # Partos: reimporta sem DUPLICAR. Antes só inseria — cada reenvio do CSV
    # empilhava os mesmos partos (uma vaca com 10 uploads ficava com 10 partos
    # iguais). Agora, para cada (matriz, data) que vem no CSV, apagamos os
    # partos já existentes daquela data antes de reinserir. Partos lançados à
    # mão em OUTRAS datas (pelo app/site) são preservados.
    datas_csv = {(p.numero_matriz, p.data_parto) for p in partos}
    # O CSV do reprodutivo não traz o número da cria nem o sexo do gemelar
    # (só sexo_cria_1/2, gemelar e retenção) — preserva o que já estava
    # lançado à mão ou preenchido pelo backfill (ver backfill_numero_cria_
    # partos em reproducao.py) para o reenvio do CSV não apagar esse vínculo.
    preservados: dict[tuple[str, object], dict] = {}
    if datas_csv:
        for antigo in session.exec(_escopo(select(Parto), Parto, fazenda_id)).all():
            chave_antigo = (antigo.numero_matriz, antigo.data_parto)
            if chave_antigo in datas_csv:
                if antigo.numero_cria_1 or antigo.numero_cria_2 or antigo.gemelar_sexo:
                    preservados[chave_antigo] = {
                        "numero_cria_1": antigo.numero_cria_1, "numero_cria_2": antigo.numero_cria_2,
                        "gemelar_sexo": antigo.gemelar_sexo,
                    }
                session.delete(antigo)
        session.commit()

    for parto in partos:
        animal = session.exec(
            _escopo(select(Animal).where(Animal.numero == parto.numero_matriz), Animal, fazenda_id)
        ).first()
        if animal:
            parto.animal_id = animal.id
        salvo = preservados.get((parto.numero_matriz, parto.data_parto))
        if salvo:
            parto.numero_cria_1 = parto.numero_cria_1 or salvo["numero_cria_1"]
            parto.numero_cria_2 = parto.numero_cria_2 or salvo["numero_cria_2"]
            parto.gemelar_sexo = parto.gemelar_sexo or salvo["gemelar_sexo"]
        session.add(parto)

    session.commit()
    return {
        "tipo": "reprodutivo",
        "servicos": len(servicos),
        "partos": len(partos),
    }


async def _upsert_conta_gerencial(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    contas = parse_conta_gerencial(content)

    # Limpa e reinserere (dados financeiros são sempre re-importados com janela completa)
    for c in session.exec(_escopo(select(ContaGerencial), ContaGerencial, fazenda_id)).all():
        session.delete(c)
    session.commit()

    for conta in _carimbar(contas, fazenda_id):
        session.add(conta)

    session.commit()
    return {"tipo": "conta_gerencial", "registros": len(contas)}


async def _upsert_estoque(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    items = parse_estoque(content)

    for c in session.exec(_escopo(select(Estoque), Estoque, fazenda_id)).all():
        session.delete(c)
    session.commit()

    for item in _carimbar(items, fazenda_id):
        session.add(item)

    session.commit()
    return {"tipo": "estoque", "registros": len(items)}


async def _upsert_dieta(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    itens = parse_dieta(content)

    for d in session.exec(_escopo(select(Dieta), Dieta, fazenda_id)).all():
        session.delete(d)
    session.commit()

    for item in _carimbar(itens, fazenda_id):
        session.add(item)

    session.commit()
    lotes = len({i.lote for i in itens if i.lote is not None})
    return {"tipo": "dieta", "registros": len(itens), "lotes": lotes}


async def _upsert_sanidade(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    registros = parse_sanidade(content)

    # Re-importação completa (histórico é sempre reenviado atualizado do Ideagri).
    for s in session.exec(_escopo(select(Sanidade), Sanidade, fazenda_id)).all():
        session.delete(s)
    session.commit()

    for reg in _carimbar(registros, fazenda_id):
        session.add(reg)

    session.commit()
    animais = len({r.numero_matriz for r in registros})
    return {"tipo": "sanidade", "registros": len(registros), "animais": animais}


async def _upsert_controle_leiteiro(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    registros = parse_controle_leiteiro(content)

    # Re-importação completa (histórico é sempre reenviado com a janela escolhida).
    for r in session.exec(_escopo(select(ControleLeiteiro), ControleLeiteiro, fazenda_id)).all():
        session.delete(r)
    session.commit()

    for reg in _carimbar(registros, fazenda_id):
        animal = session.exec(
            _escopo(select(Animal).where(Animal.numero == reg.numero_matriz), Animal, fazenda_id)
        ).first()
        if animal:
            reg.animal_id = animal.id
        session.add(reg)

    session.commit()
    vacas = len({r.numero_matriz for r in registros})
    return {"tipo": "controle_leiteiro", "registros": len(registros), "vacas": vacas}
