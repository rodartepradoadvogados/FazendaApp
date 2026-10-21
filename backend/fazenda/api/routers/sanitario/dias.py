"""
/sanitario — dias marcados ("Vacina"/"Exame"), registros por animal, desfazer,
estorno (admin), leitura de exame, dispensa e conflitos entre aparelhos.

Toda escrita de registro passa por `rules.sanitario.registro.registrar` (o
serviço único). As decisões que o sistema pede (consentimento fora da regra,
riscos de data diferente) voltam como 409 `{"codigo": ...}` — nada é gravado
até a decisão chegar; os registros em lote respondem item a item.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from fazenda.api.routers.sanitario._comum import da_fazenda, exigir_admin_fazenda, exigir_fazenda, traduzir_erros
from fazenda.api.routers.sanitario.schemas import (
    CancelarDiaIn, ConflitoDecisaoIn, DesfazerIn, DiaAplicarIn, DiaCarenciaIn, DiaCriarIn, DiaEditarIn, DiaItensIn,
    DiaRegistrosIn, DispensarIn, EstornoIn, FecharDiaIn, ResultadoIn, SimularIn,
)
from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    SanitarioCaixa, SanitarioDia, SanitarioDiaCaixa, SanitarioDiaItem, SanitarioDispositivo, SanitarioLog,
    SanitarioRegistro, Usuario,
)
from fazenda.rules.datas import hoje_local
from fazenda.rules.sanitario import dias as regras_dias
from fazenda.rules.sanitario import registro as regras_reg
from fazenda.rules.sanitario.consulta import registro_dict
from fazenda.rules.sanitario.permissoes import eh_admin_fazenda, pessoa_veterinaria_do_usuario

router = APIRouter(tags=["sanitario-dias"])


def _dia(session: Session, dia_id: int, fid: int) -> SanitarioDia:
    return da_fazenda(session, SanitarioDia, dia_id, fid, "Dia")


def _log_dict(lg: SanitarioLog) -> dict:
    return {"id": lg.id, "tipo": lg.tipo, "dia_id": lg.dia_id, "caixa_id": lg.caixa_id, "animal_id": lg.animal_id,
            "registro_id": lg.registro_id, "motivo_exibido": lg.motivo_exibido, "decisao": lg.decisao,
            "texto": lg.texto_livre, "payload": lg.payload, "usuario_id": lg.usuario_id,
            "dispositivo_id": lg.dispositivo_id, "em": lg.em.isoformat() + "Z" if lg.em else None}


def dispositivo_por_uid(session: Session, fid: int, usuario_id: Optional[int], uid: Optional[str],
                        nome: Optional[str] = None) -> Optional[SanitarioDispositivo]:
    if not uid:
        return None
    d = session.exec(select(SanitarioDispositivo).where(
        SanitarioDispositivo.fazenda_id == fid, SanitarioDispositivo.usuario_id == usuario_id,
        SanitarioDispositivo.dispositivo_uid == uid)).first()
    if d is None:
        d = SanitarioDispositivo(fazenda_id=fid, usuario_id=usuario_id, dispositivo_uid=uid, nome=nome)
        session.add(d)
        session.flush()
    elif nome and d.nome != nome:
        d.nome = nome
        session.add(d)
    return d


# ── leitura ─────────────────────────────────────────────────────────────────
@router.get("/dias")
def listar_dias(estado: Optional[str] = None, de: Optional[date] = None, ate: Optional[date] = None,
                session: Session = Depends(get_session),
                fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> list[dict]:
    fid = exigir_fazenda(fazenda_id)
    q = select(SanitarioDia).where(SanitarioDia.fazenda_id == fid)
    if estado == "abertos":
        q = q.where(SanitarioDia.estado.in_(regras_dias.ESTADOS_ABERTOS))
    elif estado:
        q = q.where(SanitarioDia.estado == estado)
    if de:
        q = q.where(SanitarioDia.data >= de)
    if ate:
        q = q.where(SanitarioDia.data <= ate)
    return [regras_dias.dia_dict(session, d, com_itens=False)
            for d in session.exec(q.order_by(SanitarioDia.data, SanitarioDia.id)).all()]


@router.get("/dias/data-prevista")
def sugerir_data(caixa_ids: str = Query(..., description="ids separados por vírgula"),
                 session: Session = Depends(get_session),
                 fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    ids = [int(x) for x in caixa_ids.split(",") if x.strip().isdigit()]
    for i in ids:
        da_fazenda(session, SanitarioCaixa, i, fid, "Vacina/exame")
    return {"data_prevista": regras_dias.data_prevista(session, fid, ids).isoformat()}


@router.get("/dias/{dia_id}")
def obter_dia(dia_id: int, session: Session = Depends(get_session),
              fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    return regras_dias.dia_dict(session, _dia(session, dia_id, fid))


@router.get("/dias/{dia_id}/ficha")
def ficha_do_dia(dia_id: int, session: Session = Depends(get_session),
                 fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    """Ficha de campo PRÉ-PREENCHIDA (JSON para o front renderizar/imprimir)."""
    fid = exigir_fazenda(fazenda_id)
    return regras_dias.ficha_dia(session, fid, _dia(session, dia_id, fid))


@router.get("/dias/{dia_id}/log")
def log_do_dia(dia_id: int, session: Session = Depends(get_session),
               fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> list[dict]:
    fid = exigir_fazenda(fazenda_id)
    _dia(session, dia_id, fid)
    return [_log_dict(lg) for lg in session.exec(select(SanitarioLog).where(
        SanitarioLog.fazenda_id == fid, SanitarioLog.dia_id == dia_id).order_by(SanitarioLog.em.desc(), SanitarioLog.id.desc())).all()]


@router.get("/dias/{dia_id}/registros")
def registros_do_dia(dia_id: int, session: Session = Depends(get_session),
                     fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> list[dict]:
    fid = exigir_fazenda(fazenda_id)
    _dia(session, dia_id, fid)
    regs = session.exec(select(SanitarioRegistro).where(
        SanitarioRegistro.fazenda_id == fid, SanitarioRegistro.dia_id == dia_id).order_by(SanitarioRegistro.id)).all()
    caixas = {c.id: c for c in session.exec(select(SanitarioCaixa).where(SanitarioCaixa.fazenda_id == fid)).all()}
    return [registro_dict(r, caixas.get(r.caixa_id)) for r in regs]


# ── marcar / editar / animais ───────────────────────────────────────────────
@router.post("/dias/simular")
def simular_dia(dados: SimularIn, session: Session = Depends(get_session),
                fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """Riscos de marcar numa data diferente da prevista — SÓ SIMULA, não grava."""
    fid = exigir_fazenda(fazenda_id)
    caixas = [da_fazenda(session, SanitarioCaixa, i, fid, "Vacina/exame") for i in dados.caixa_ids]
    prev = dados.data_prevista or regras_dias.data_prevista(session, fid, dados.caixa_ids)
    sel = {aid: {c.id for c in caixas} for aid in dados.animal_ids} if dados.animal_ids is not None else None
    sim = regras_dias._riscos(session, fid, caixas, dados.data, prev, sel, hoje_local())
    return {"data": dados.data.isoformat(), "data_prevista": prev.isoformat(), **sim}


@router.post("/dias")
def marcar_dia(dados: DiaCriarIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
               fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    d = dados.model_dump()
    d["produtos"] = {k: v.model_dump(exclude_unset=True) for k, v in dados.produtos.items()}
    with traduzir_erros(session):
        dia, avisos = regras_dias.criar_dia(session, fid, d, usuario_id=user.id)
        session.commit()
    out = regras_dias.dia_dict(session, dia)
    out["avisos"] = avisos
    return out


@router.put("/dias/{dia_id}")
def editar_dia(dia_id: int, dados: DiaEditarIn, session: Session = Depends(get_session),
               user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    dia = _dia(session, dia_id, fid)
    d = dados.model_dump(exclude_unset=True)
    d["versao_lock"] = dados.versao_lock
    d["produtos"] = {k: v.model_dump(exclude_unset=True) for k, v in dados.produtos.items()}
    if dados.decisao_riscos is not None:
        d["decisao_riscos"] = dados.decisao_riscos.model_dump()
    if dados.veterinario is not None:
        d["veterinario"] = dados.veterinario.model_dump()
    with traduzir_erros(session):
        avisos = regras_dias.editar_dia(session, fid, dia, d, usuario_id=user.id)
        session.commit()
    out = regras_dias.dia_dict(session, dia)
    out["avisos"] = avisos
    return out


@router.post("/dias/{dia_id}/itens")
def adicionar_animais(dia_id: int, dados: DiaItensIn, session: Session = Depends(get_session),
                      user: Usuario = Depends(get_current_user),
                      fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """Adicionar animais (com consentimento para quem está fora da regra)."""
    fid = exigir_fazenda(fazenda_id)
    dia = _dia(session, dia_id, fid)
    d = dados.model_dump()
    with traduzir_erros(session):
        avisos = regras_dias.adicionar_itens(session, fid, dia, d["itens"], d["consentimentos"], usuario_id=user.id)
        session.commit()
    out = regras_dias.dia_dict(session, dia)
    out["avisos"] = avisos
    return out


@router.delete("/dias/{dia_id}/itens/{item_id}")
def remover_animal(dia_id: int, item_id: int, session: Session = Depends(get_session),
                   user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    dia = _dia(session, dia_id, fid)
    with traduzir_erros(session):
        regras_dias.remover_item(session, fid, dia, item_id, usuario_id=user.id)
        session.commit()
    return regras_dias.dia_dict(session, dia)


@router.post("/dias/{dia_id}/carencia")
def decidir_carencia_do_dia(dia_id: int, dados: DiaCarenciaIn, session: Session = Depends(get_session),
                            user: Usuario = Depends(get_current_user),
                            fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """Pop-up "Carência: o que fazer com o leite?" (só administrador): vale
    para o dia todo e fica no registro."""
    fid = exigir_fazenda(fazenda_id)
    exigir_admin_fazenda(session, user, fid)
    dia = _dia(session, dia_id, fid)
    dc = session.exec(select(SanitarioDiaCaixa).where(
        SanitarioDiaCaixa.fazenda_id == fid, SanitarioDiaCaixa.dia_id == dia.id,
        SanitarioDiaCaixa.caixa_id == dados.caixa_id)).first()
    if dc is None:
        raise HTTPException(status_code=404, detail="Esta vacina/exame não faz parte do dia.")
    ac = regras_reg.gravar_decisao_dia(session, fid, dc, dados.model_dump(), user.id)
    session.commit()
    return {"dia_id": dia.id, "caixa_id": dc.caixa_id, "aceite_id": ac.id, "modo": ac.modo_leite,
            "leite_dias": ac.leite_dias, "carne_dias": ac.carne_dias}


# ── registrar (um, grupo, app) ──────────────────────────────────────────────
def _decisoes_carencia(session: Session, fid: int, dia, decisoes: dict, usuario, adm: bool) -> None:
    if not decisoes:
        return
    if not adm:
        raise HTTPException(status_code=403, detail="Só o administrador decide o modo da carência.")
    for cid, dec in decisoes.items():
        dc = session.exec(select(SanitarioDiaCaixa).where(
            SanitarioDiaCaixa.fazenda_id == fid, SanitarioDiaCaixa.dia_id == dia.id,
            SanitarioDiaCaixa.caixa_id == int(cid))).first()
        if dc is None:
            raise HTTPException(status_code=404, detail=f"A caixa {cid} não faz parte do dia.")
        if dec.get("modo"):
            regras_reg.gravar_decisao_dia(session, fid, dc, dec, usuario.id)


@router.post("/dias/{dia_id}/registros")
def registrar_no_dia(dia_id: int, dados: DiaRegistrosIn, session: Session = Depends(get_session),
                     user: Usuario = Depends(get_current_user),
                     fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """Registra a aplicação/coleta por animal (um por vez ou o grupo). Item
    fora da regra sem consentimento, ou carência a decidir, volta "pendente"
    com `requer`; o resto grava. Idempotente por `chave_idempotencia`."""
    fid = exigir_fazenda(fazenda_id)
    dia = _dia(session, dia_id, fid)
    if dia.estado == "cancelado":
        raise HTTPException(status_code=400, detail="Dia cancelado.")
    adm = eh_admin_fazenda(session, user, fid)
    _decisoes_carencia(session, fid, dia, {k: v.model_dump() for k, v in dados.carencia.items()}, user, adm)
    disp = dispositivo_por_uid(session, fid, user.id, dados.dispositivo_uid)
    with traduzir_erros(session):
        res = regras_reg.registrar(
            session, fid, [r.model_dump() for r in dados.registros], origem="dia", canal=dados.canal,
            usuario_id=user.id, eh_admin=adm, dia=dia, dispositivo_id=disp.id if disp else None,
        )
        session.commit()
    return res


@router.post("/dias/{dia_id}/aplicar")
def aplicar_grupo(dia_id: int, dados: DiaAplicarIn, session: Session = Depends(get_session),
                  user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """"Aplicar no grupo todo" (ou nos itens escolhidos): registra cada
    animal × caixa pendente. O grupo não fecha — dá para incluir mais depois."""
    fid = exigir_fazenda(fazenda_id)
    dia = _dia(session, dia_id, fid)
    if dia.estado == "cancelado":
        raise HTTPException(status_code=400, detail="Dia cancelado.")
    adm = eh_admin_fazenda(session, user, fid)
    _decisoes_carencia(session, fid, dia, {k: v.model_dump() for k, v in dados.carencia.items()}, user, adm)
    q = select(SanitarioDiaItem).where(SanitarioDiaItem.fazenda_id == fid, SanitarioDiaItem.dia_id == dia.id,
                                       SanitarioDiaItem.estado == "pendente")
    if dados.item_ids is not None:
        q = q.where(SanitarioDiaItem.id.in_(dados.item_ids or [-1]))
    itens = session.exec(q.order_by(SanitarioDiaItem.id)).all()
    regs = [{"animal_id": it.animal_id, "caixa_id": it.caixa_id, "hora": dados.hora,
             "aplicador_pessoa_id": dados.aplicador_pessoa_id, "aplicador_texto": dados.aplicador_texto}
            for it in itens]
    with traduzir_erros(session):
        res = regras_reg.registrar(session, fid, regs, origem="dia", canal=dados.canal, usuario_id=user.id,
                                   eh_admin=adm, dia=dia)
        session.commit()
    return res


@router.post("/registros/desfazer")
def desfazer_registros(dados: DesfazerIn, session: Session = Depends(get_session),
                       user: Usuario = Depends(get_current_user),
                       fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """Desfazer em 10 s (quem gravou ou o administrador): devolve o estoque e
    nada fica no histórico."""
    fid = exigir_fazenda(fazenda_id)
    with traduzir_erros(session):
        res = regras_reg.desfazer(session, fid, dados.registro_ids, usuario_id=user.id,
                                  eh_admin=eh_admin_fazenda(session, user, fid))
        session.commit()
    return res


@router.post("/registros/{registro_id}/estornar")
def estornar_registro(registro_id: int, dados: EstornoIn, session: Session = Depends(get_session),
                      user: Usuario = Depends(get_current_user),
                      fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """Estorno (só administrador, com motivo): devolve estoque, tira a
    carência e a próxima dose não aplicada."""
    fid = exigir_fazenda(fazenda_id)
    exigir_admin_fazenda(session, user, fid)
    with traduzir_erros(session):
        res = regras_reg.estornar(session, fid, registro_id, dados.motivo, usuario_id=user.id)
        session.commit()
    return res


@router.post("/registros/{registro_id}/resultado")
def lancar_resultado(registro_id: int, dados: ResultadoIn, session: Session = Depends(get_session),
                     user: Usuario = Depends(get_current_user),
                     fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """Leitura/resultado de exame: veterinário, ou administrador informando o
    veterinário responsável. Reagente gera só aviso."""
    fid = exigir_fazenda(fazenda_id)
    with traduzir_erros(session):
        res = regras_reg.lancar_resultado(
            session, fid, registro_id, dados.model_dump(), usuario_id=user.id,
            eh_admin=eh_admin_fazenda(session, user, fid), pessoa_vet=pessoa_veterinaria_do_usuario(session, user, fid))
        session.commit()
    return res


# ── fechar / cancelar / dispensar ───────────────────────────────────────────
@router.post("/dias/{dia_id}/fechar")
def fechar_dia(dia_id: int, dados: FecharDiaIn, session: Session = Depends(get_session),
               user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    dia = _dia(session, dia_id, fid)
    with traduzir_erros(session):
        res = regras_dias.fechar_dia(session, fid, dia, dados.faltantes, dados.motivo, usuario_id=user.id)
        session.commit()
    return {**regras_dias.dia_dict(session, dia), "fechamento": res}


@router.post("/dias/{dia_id}/cancelar")
def cancelar_dia(dia_id: int, dados: CancelarDiaIn, session: Session = Depends(get_session),
                 user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    dia = _dia(session, dia_id, fid)
    with traduzir_erros(session):
        regras_dias.cancelar_dia(session, fid, dia, dados.motivo, usuario_id=user.id)
        session.commit()
    return regras_dias.dia_dict(session, dia)


@router.post("/situacoes/dispensar")
def dispensar_animais(dados: DispensarIn, session: Session = Depends(get_session),
                      user: Usuario = Depends(get_current_user),
                      fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """Dispensar (ou "descartar vacina") neste ciclo — motivo pulável."""
    fid = exigir_fazenda(fazenda_id)
    for it in dados.itens:
        da_fazenda(session, SanitarioCaixa, it.caixa_id, fid, "Vacina/exame")
    from fazenda.models import Animal
    for it in dados.itens:
        da_fazenda(session, Animal, it.animal_id, fid, "Animal")
    with traduzir_erros(session):
        n = regras_dias.dispensar(session, fid, [(i.caixa_id, i.animal_id, i.ciclo_chave, i.dose_num) for i in dados.itens],
                                  dados.motivo, usuario_id=user.id, acao=dados.acao)
        session.commit()
    return {"dispensados": n, "acao": dados.acao}


# ── conflitos entre aparelhos ───────────────────────────────────────────────
@router.get("/conflitos")
def listar_conflitos(session: Session = Depends(get_session),
                     fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> list[dict]:
    fid = exigir_fazenda(fazenda_id)
    out = []
    for lg in session.exec(select(SanitarioLog).where(
        SanitarioLog.fazenda_id == fid, SanitarioLog.tipo == "offline.conflito").order_by(SanitarioLog.id.desc())).all():
        if (lg.payload or {}).get("resolvido"):
            continue
        out.append(_log_dict(lg))
    return out


@router.post("/conflitos/{log_id}/decidir")
def decidir_conflito(log_id: int, dados: ConflitoDecisaoIn, session: Session = Depends(get_session),
                     user: Usuario = Depends(get_current_user),
                     fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """O aplicador (quem gravou um dos dois) ou o administrador decide."""
    fid = exigir_fazenda(fazenda_id)
    with traduzir_erros(session):
        res = regras_reg.decidir_conflito(session, fid, log_id, dados.manter, usuario_id=user.id,
                                          eh_admin=eh_admin_fazenda(session, user, fid))
        session.commit()
    return res
