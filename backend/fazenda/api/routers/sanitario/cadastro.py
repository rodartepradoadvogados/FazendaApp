"""
/sanitario — cadastro das caixas (wizard), catálogo da fazenda, parâmetros e
veterinários. Escrita de cadastro SÓ pelo administrador da fazenda (aceite
de carência inclusive); a prévia e a validação por etapa não gravam nada.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select

from fazenda.api.routers.sanitario._comum import da_fazenda, exigir_admin_fazenda, exigir_fazenda, traduzir_erros
from fazenda.api.routers.sanitario.schemas import (
    AceiteCarenciaIn, AtivarCatalogoIn, CaixaCriarIn, CaixasEstadoIn, CaixaValidarIn, CaixaVersaoIn, ParametrosIn,
    PreviaIn,
)
from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    SanitarioCaixa, SanitarioCaixaVersao, SanitarioCarenciaAceite, SanitarioCatalogo, SanitarioCatalogoVersao,
    SanitarioParametros, SanitarioSituacao, Usuario,
)
from fazenda.rules.datas import hoje_local
from fazenda.rules.sanitario import definicao as regras_def
from fazenda.rules.sanitario import wizard
from fazenda.rules.sanitario.dias import ficha_vazia
from fazenda.rules.sanitario.motor import recalcular
from fazenda.rules.sanitario.notas import resolver_notas
from fazenda.rules.sanitario.permissoes import eh_admin_fazenda, veterinarios_da_fazenda
from fazenda.rules.sanitario.registro import _log

router = APIRouter(tags=["sanitario-cadastro"])


# ── leitura ─────────────────────────────────────────────────────────────────
def _aceite_atual(session: Session, fazenda_id: int, versao_id: Optional[int]):
    if not versao_id:
        return None
    return session.exec(select(SanitarioCarenciaAceite).where(
        SanitarioCarenciaAceite.fazenda_id == fazenda_id, SanitarioCarenciaAceite.escopo == "caixa_versao",
        SanitarioCarenciaAceite.caixa_versao_id == versao_id).order_by(SanitarioCarenciaAceite.id.desc())).first()


def _resumo_caixa(session: Session, cx: SanitarioCaixa, na_caixa: dict, catalogos: dict) -> dict:
    v = session.get(SanitarioCaixaVersao, cx.versao_atual_id) if cx.versao_atual_id else None
    cat = catalogos.get(cx.catalogo_id) if cx.catalogo_id else None
    ac = _aceite_atual(session, cx.fazenda_id, cx.versao_atual_id)
    return {
        "id": cx.id, "nome": cx.nome, "nome_curto": cx.nome_curto, "tipo": cx.tipo, "estado": cx.estado,
        "obrigatoria": cx.obrigatoria, "padrao_fabrica": cx.padrao_fabrica,
        "versao_atual_id": cx.versao_atual_id, "versao_numero": v.numero if v else None,
        "vigente_desde": v.vigente_desde.isoformat() if v else None,
        "ativada_em": cx.ativada_em.isoformat() if cx.ativada_em else None,
        "arquivada_em": cx.arquivada_em.isoformat() if cx.arquivada_em else None,
        "arquivada_motivo": cx.arquivada_motivo,
        "na_caixa": na_caixa.get(cx.id, 0), "aglo_min": v.aglo_min if v else None,
        "carencia_aceita": ac is not None,
        "catalogo": {
            "id": cx.catalogo_id, "chave": cat.chave if cat else None, "versao": cx.catalogo_versao,
            "versao_central": cat.versao_atual if cat else None,
            "nova_versao": bool(cat and cx.catalogo_versao and cat.versao_atual > cx.catalogo_versao),
        } if cx.catalogo_id else None,
    }


def _na_caixa(session: Session, fazenda_id: int) -> dict[int, int]:
    rows = session.exec(select(SanitarioSituacao.caixa_id, func.count(func.distinct(SanitarioSituacao.animal_id))).where(
        SanitarioSituacao.fazenda_id == fazenda_id,
        SanitarioSituacao.estado.in_(("janela", "aviso", "atrasada"))).group_by(SanitarioSituacao.caixa_id)).all()
    return {cid: n for cid, n in rows}


def detalhe_caixa(session: Session, cx: SanitarioCaixa) -> dict:
    catalogos = {c.id: c for c in session.exec(select(SanitarioCatalogo)).all()} if cx.catalogo_id else {}
    out = _resumo_caixa(session, cx, _na_caixa(session, cx.fazenda_id), catalogos)
    v = session.get(SanitarioCaixaVersao, cx.versao_atual_id) if cx.versao_atual_id else None
    out["definicao"] = wizard.definicao_da_versao(session, cx, v)
    out["versoes"] = [{
        "id": x.id, "numero": x.numero, "vigente_desde": x.vigente_desde.isoformat(),
        "vigente_ate": x.vigente_ate.isoformat() if x.vigente_ate else None,
        "criado_em": x.criado_em.isoformat() if x.criado_em else None,
    } for x in session.exec(select(SanitarioCaixaVersao).where(
        SanitarioCaixaVersao.fazenda_id == cx.fazenda_id, SanitarioCaixaVersao.caixa_id == cx.id,
    ).order_by(SanitarioCaixaVersao.numero)).all()]
    ac = _aceite_atual(session, cx.fazenda_id, cx.versao_atual_id)
    out["aceite_carencia"] = {
        "modo_leite": ac.modo_leite, "leite_dias": ac.leite_dias, "carne_dias": ac.carne_dias,
        "aceito_por_usuario_id": ac.aceito_por_usuario_id, "aceito_em": ac.aceito_em.isoformat(),
    } if ac else None
    return out


@router.get("/caixas")
def listar_caixas(
    estado: Optional[str] = Query(default=None, description="ativa | inativa | arquivada | todas (padrão: não arquivadas)"),
    session: Session = Depends(get_session), fazenda_id: Optional[int] = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fid = exigir_fazenda(fazenda_id)
    q = select(SanitarioCaixa).where(SanitarioCaixa.fazenda_id == fid)
    if estado in ("ativa", "inativa", "arquivada"):
        q = q.where(SanitarioCaixa.estado == estado)
    elif estado != "todas":
        q = q.where(SanitarioCaixa.estado != "arquivada")
    caixas = session.exec(q.order_by(SanitarioCaixa.nome)).all()
    catalogos = {c.id: c for c in session.exec(select(SanitarioCatalogo)).all()}
    na = _na_caixa(session, fid)
    return [_resumo_caixa(session, cx, na, catalogos) for cx in caixas]


@router.get("/caixas/{caixa_id}")
def obter_caixa(caixa_id: int, session: Session = Depends(get_session),
                fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    return detalhe_caixa(session, da_fazenda(session, SanitarioCaixa, caixa_id, fid, "Vacina/exame"))


@router.get("/caixas/{caixa_id}/versoes/{versao_id}")
def obter_versao(caixa_id: int, versao_id: int, session: Session = Depends(get_session),
                 fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    """Uma versão antiga (o histórico aponta para ela)."""
    fid = exigir_fazenda(fazenda_id)
    cx = da_fazenda(session, SanitarioCaixa, caixa_id, fid, "Vacina/exame")
    v = da_fazenda(session, SanitarioCaixaVersao, versao_id, fid, "Versão")
    if v.caixa_id != cx.id:
        raise HTTPException(status_code=404, detail="Versão não encontrada.")
    return {"id": v.id, "numero": v.numero, "vigente_desde": v.vigente_desde.isoformat(),
            "vigente_ate": v.vigente_ate.isoformat() if v.vigente_ate else None,
            "definicao": wizard.definicao_da_versao(session, cx, v)}


@router.get("/caixas/{caixa_id}/ficha-vazia")
def ficha_vazia_caixa(caixa_id: int, linhas: int = Query(default=25, ge=1, le=200),
                      session: Session = Depends(get_session),
                      fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    return ficha_vazia(session, fid, [da_fazenda(session, SanitarioCaixa, caixa_id, fid, "Vacina/exame")], linhas)


@router.get("/ficha-vazia")
def ficha_vazia_varias(caixa_ids: str = Query(default="", description="ids separados por vírgula"),
                       linhas: int = Query(default=25, ge=1, le=200),
                       session: Session = Depends(get_session),
                       fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    ids = [int(x) for x in caixa_ids.split(",") if x.strip().isdigit()]
    return ficha_vazia(session, fid, [da_fazenda(session, SanitarioCaixa, i, fid, "Vacina/exame") for i in ids], linhas)


# ── escrita (admin) ─────────────────────────────────────────────────────────
def _validar_ou_422(session: Session, fid: int, d: dict, caixa_id: Optional[int] = None) -> None:
    erros = wizard.validar(session, fid, d, None, caixa_id=caixa_id)
    if erros:
        raise HTTPException(status_code=422, detail={"codigo": "validacao", "erros": erros})


def _aceitar(session: Session, fid: int, cx: SanitarioCaixa, usuario_id: Optional[int], modo: Optional[str],
             leite: Optional[int], carne: Optional[int], origem: str = "wizard"):
    ac = SanitarioCarenciaAceite(
        fazenda_id=fid, escopo="caixa_versao", caixa_versao_id=cx.versao_atual_id, modo_leite=modo,
        leite_dias=leite, carne_dias=carne, origem=origem, aceito_por_usuario_id=usuario_id,
    )
    session.add(ac)
    session.flush()
    _log(session, fid, "carencia.aceite", caixa_id=cx.id, usuario_id=usuario_id, decisao=modo,
         texto_livre=f"Carência de {cx.nome_curto or cx.nome} aceita (1 clique): {modo or 'sem modo'} · "
                     f"leite {leite} d · carne {carne} d.")
    resolver_notas(session, fid, chave=f"carencia:{cx.versao_atual_id}")
    return ac


@router.post("/caixas/validar")
def validar_etapa(dados: CaixaValidarIn, session: Session = Depends(get_session),
                  fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """Validação do wizard etapa a etapa (não grava)."""
    fid = exigir_fazenda(fazenda_id)
    erros = wizard.validar(session, fid, dados.definicao.para_definicao(), dados.etapa, caixa_id=dados.caixa_id)
    return {"ok": not erros, "erros": erros, "etapa": dados.etapa}


@router.post("/caixas/previa")
def previa_caixa(dados: PreviaIn, session: Session = Depends(get_session),
                 fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """Revisão do wizard: "entram / ficam de fora e por quê" na data-base, SEM GRAVAR."""
    fid = exigir_fazenda(fazenda_id)
    return wizard.previa(session, fid, dados.definicao.para_definicao(), dados.data_base or hoje_local())


@router.post("/caixas")
def criar_caixa(dados: CaixaCriarIn, session: Session = Depends(get_session),
                user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    exigir_admin_fazenda(session, user, fid)
    d = dados.definicao.para_definicao()
    _validar_ou_422(session, fid, d)
    with traduzir_erros(session):
        cx = regras_def.criar_caixa(session, fid, d, estado=dados.estado, usuario_id=user.id)
        if dados.aceitar_carencia:
            _aceitar(session, fid, cx, user.id, d.get("car_modo_leite"), d.get("car_leite_dias"), d.get("car_carne_dias"))
        if cx.estado == "ativa":
            recalcular(session, fid, caixa_ids=[cx.id], motivo="caixa.criada")
        session.commit()
    session.refresh(cx)
    return detalhe_caixa(session, cx)


@router.put("/caixas/{caixa_id}")
def nova_versao_caixa(caixa_id: int, dados: CaixaVersaoIn, session: Session = Depends(get_session),
                      user: Usuario = Depends(get_current_user),
                      fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """Editar = versão nova a partir de hoje (vale daqui para frente; o
    histórico continua apontando a versão antiga). Devolve o que foi gravado,
    lido do banco."""
    fid = exigir_fazenda(fazenda_id)
    exigir_admin_fazenda(session, user, fid)
    cx = da_fazenda(session, SanitarioCaixa, caixa_id, fid, "Vacina/exame")
    if cx.estado == "arquivada":
        raise HTTPException(status_code=400, detail="Reative a caixa antes de editar.")
    d = dados.definicao.para_definicao()
    _validar_ou_422(session, fid, d, caixa_id=cx.id)
    with traduzir_erros(session):
        regras_def.nova_versao(session, cx, d, usuario_id=user.id)
        if dados.aceitar_carencia:
            _aceitar(session, fid, cx, user.id, d.get("car_modo_leite"), d.get("car_leite_dias"), d.get("car_carne_dias"))
        if cx.estado == "ativa":
            recalcular(session, fid, caixa_ids=[cx.id], motivo="caixa.versao")
        session.commit()
    session.refresh(cx)
    return detalhe_caixa(session, cx)


@router.post("/caixas/estado")
def mudar_estado_em_massa(dados: CaixasEstadoIn, session: Session = Depends(get_session),
                          user: Usuario = Depends(get_current_user),
                          fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """Ativar / inativar / arquivar / reativar (tirar do arquivo) em massa.
    Arquivar = apagar com histórico, reversível."""
    fid = exigir_fazenda(fazenda_id)
    exigir_admin_fazenda(session, user, fid)
    hoje = hoje_local()
    resultados = []
    mexidas = []
    for cid in dict.fromkeys(dados.caixa_ids):
        cx = session.get(SanitarioCaixa, cid)
        if cx is None or cx.fazenda_id != fid:
            resultados.append({"caixa_id": cid, "ok": False, "erro": "não encontrado"})
            continue
        if dados.acao == "ativar":
            if cx.estado == "arquivada":
                resultados.append({"caixa_id": cid, "ok": False, "erro": "arquivada: reative antes"})
                continue
            cx.estado = "ativa"
            cx.ativada_em = cx.ativada_em or hoje
        elif dados.acao == "inativar":
            if cx.estado == "arquivada":
                resultados.append({"caixa_id": cid, "ok": False, "erro": "arquivada"})
                continue
            cx.estado = "inativa"
        elif dados.acao == "arquivar":
            cx.estado, cx.arquivada_em, cx.arquivada_motivo = "arquivada", datetime.utcnow(), dados.motivo
        else:  # reativar (sair do arquivo, volta inativa)
            if cx.estado != "arquivada":
                resultados.append({"caixa_id": cid, "ok": True, "erro": None})
                continue
            dup = session.exec(select(SanitarioCaixa).where(
                SanitarioCaixa.fazenda_id == fid, SanitarioCaixa.nome_normalizado == cx.nome_normalizado,
                SanitarioCaixa.estado != "arquivada", SanitarioCaixa.id != cx.id)).first()
            if dup is not None:
                resultados.append({"caixa_id": cid, "ok": False, "erro": f'já existe "{dup.nome}" ativo/inativo'})
                continue
            cx.estado, cx.arquivada_em, cx.arquivada_motivo = "inativa", None, None
        session.add(cx)
        _log(session, fid, "caixa.arquivada" if dados.acao == "arquivar" else "caixa.estado", caixa_id=cx.id,
             usuario_id=user.id, decisao=dados.acao,
             texto_livre=f"{cx.nome}: {dados.acao}{' · ' + dados.motivo if dados.motivo else ''}.")
        mexidas.append(cx.id)
        resultados.append({"caixa_id": cid, "ok": True, "erro": None})
    session.flush()
    if mexidas:
        recalcular(session, fid, caixa_ids=mexidas, motivo=f"caixa.{dados.acao}")
    session.commit()
    return {"acao": dados.acao, "resultados": resultados}


@router.post("/caixas/{caixa_id}/carencia/aceite")
def aceitar_carencia(caixa_id: int, dados: AceiteCarenciaIn, session: Session = Depends(get_session),
                     user: Usuario = Depends(get_current_user),
                     fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """Aceite de carência (só administrador, 1 clique, gravado no log)."""
    fid = exigir_fazenda(fazenda_id)
    exigir_admin_fazenda(session, user, fid)
    cx = da_fazenda(session, SanitarioCaixa, caixa_id, fid, "Vacina/exame")
    if not cx.versao_atual_id:
        raise HTTPException(status_code=400, detail="Caixa sem versão.")
    ac = _aceitar(session, fid, cx, user.id, dados.modo_leite, dados.leite_dias, dados.carne_dias)
    session.commit()
    return {"id": ac.id, "caixa_id": cx.id, "caixa_versao_id": cx.versao_atual_id, "modo_leite": ac.modo_leite,
            "leite_dias": ac.leite_dias, "carne_dias": ac.carne_dias, "aceito_em": ac.aceito_em.isoformat()}


# ── catálogo central visto pela fazenda ─────────────────────────────────────
@router.get("/catalogo")
def catalogo_da_fazenda(session: Session = Depends(get_session),
                        fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> list[dict]:
    """Itens do catálogo central (cockpit CowData) com o que a fazenda já
    ativou e o aviso de NOVA VERSÃO (nunca sobrescreve a caixa da fazenda)."""
    fid = exigir_fazenda(fazenda_id)
    caixas = session.exec(select(SanitarioCaixa).where(
        SanitarioCaixa.fazenda_id == fid, SanitarioCaixa.catalogo_id != None)).all()  # noqa: E711
    por_cat: dict[int, list] = {}
    for cx in caixas:
        por_cat.setdefault(cx.catalogo_id, []).append(cx)
    out = []
    for cat in session.exec(select(SanitarioCatalogo).where(SanitarioCatalogo.ativo == True)  # noqa: E712
                            .order_by(SanitarioCatalogo.nome)).all():
        cv = session.exec(select(SanitarioCatalogoVersao).where(
            SanitarioCatalogoVersao.catalogo_id == cat.id, SanitarioCatalogoVersao.versao == cat.versao_atual)).first()
        minhas = [{"caixa_id": c.id, "estado": c.estado, "catalogo_versao": c.catalogo_versao,
                   "nova_versao": bool(c.catalogo_versao and cat.versao_atual > c.catalogo_versao)}
                  for c in por_cat.get(cat.id, [])]
        out.append({
            "id": cat.id, "chave": cat.chave, "nome": cat.nome, "tipo": cat.tipo, "versao_atual": cat.versao_atual,
            "versao_id": cv.id if cv else None, "padrao_fabrica": cat.padrao_fabrica, "uf_sugerida": cat.uf_sugerida,
            "nota_mudanca": cv.nota_mudanca if cv else None, "base_legal": cv.base_legal if cv else None,
            "definicao": cv.definicao if cv else None, "caixas_da_fazenda": minhas,
            "nova_versao": any(m["nova_versao"] and m["estado"] != "arquivada" for m in minhas),
        })
    return out


@router.get("/catalogo/{versao_id}/previa-copia")
def previa_copia_do_catalogo(versao_id: int, session: Session = Depends(get_session),
                             fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    """A definição do item do catálogo como ficaria na fazenda (categorias e
    histórico resolvidos) — NÃO grava. O wizard abre isto e só cria a cópia
    ao concluir (POST /catalogo/{versao_id}/ativar com `definicao`)."""
    fid = exigir_fazenda(fazenda_id)
    cv = session.get(SanitarioCatalogoVersao, versao_id)
    if cv is None:
        raise HTTPException(status_code=404, detail="Versão de catálogo não encontrada.")
    d, avisos = regras_def.definicao_resolvida(session, fid, dict(cv.definicao or {}))
    return {"versao_id": cv.id, "versao": cv.versao, "definicao": d, "avisos": avisos}


@router.post("/catalogo/{versao_id}/ativar")
def ativar_do_catalogo(versao_id: int, dados: AtivarCatalogoIn, session: Session = Depends(get_session),
                       user: Usuario = Depends(get_current_user),
                       fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """Ativar = COPIAR a definição do catálogo para uma caixa da fazenda."""
    fid = exigir_fazenda(fazenda_id)
    exigir_admin_fazenda(session, user, fid)
    cv = session.get(SanitarioCatalogoVersao, versao_id)
    if cv is None:
        raise HTTPException(status_code=404, detail="Versão de catálogo não encontrada.")
    ajustada = dados.definicao.para_definicao() if dados.definicao is not None else None
    if ajustada is not None:
        _validar_ou_422(session, fid, ajustada)
    nome = (ajustada if ajustada is not None else (cv.definicao or {})).get("nome") or ""
    dup = session.exec(select(SanitarioCaixa).where(
        SanitarioCaixa.fazenda_id == fid, SanitarioCaixa.nome_normalizado == regras_def.normalizar(nome),
        SanitarioCaixa.estado != "arquivada")).first()
    if dup is not None:
        raise HTTPException(status_code=409, detail={"codigo": "nome_duplicado", "caixa_id": dup.id,
                                                     "mensagem": f'Já existe "{dup.nome}" nesta fazenda.'})
    try:
        cx = regras_def.ativar_do_catalogo(session, fid, cv.id, estado=dados.estado, usuario_id=user.id,
                                           definicao=ajustada)
        _log(session, fid, "catalogo.ativado", caixa_id=cx.id, usuario_id=user.id,
             texto_livre=f"{cx.nome} v{cv.versao} copiado do catálogo central ({dados.estado})"
                         f"{', com ajustes do cadastro' if ajustada is not None else ''}.")
        if dados.aceitar_carencia and ajustada is not None:
            _aceitar(session, fid, cx, user.id, ajustada.get("car_modo_leite"), ajustada.get("car_leite_dias"),
                     ajustada.get("car_carne_dias"))
        if cx.estado == "ativa":
            recalcular(session, fid, caixa_ids=[cx.id], motivo="catalogo.ativado")
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail={"codigo": "nome_duplicado", "mensagem": "Nome já usado."})
    session.refresh(cx)
    return detalhe_caixa(session, cx)


@router.post("/caixas/{caixa_id}/atualizar-do-catalogo")
def atualizar_do_catalogo(caixa_id: int, session: Session = Depends(get_session),
                          user: Usuario = Depends(get_current_user),
                          fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """Aceitar a nova versão do catálogo central: vira uma VERSÃO NOVA da
    caixa da fazenda, daqui para frente."""
    fid = exigir_fazenda(fazenda_id)
    exigir_admin_fazenda(session, user, fid)
    cx = da_fazenda(session, SanitarioCaixa, caixa_id, fid, "Vacina/exame")
    cat = session.get(SanitarioCatalogo, cx.catalogo_id) if cx.catalogo_id else None
    if cat is None:
        raise HTTPException(status_code=400, detail="Esta caixa não veio do catálogo central.")
    cv = session.exec(select(SanitarioCatalogoVersao).where(
        SanitarioCatalogoVersao.catalogo_id == cat.id, SanitarioCatalogoVersao.versao == cat.versao_atual)).first()
    if cv is None or (cx.catalogo_versao or 0) >= cat.versao_atual:
        raise HTTPException(status_code=400, detail="Já está na versão atual do catálogo.")
    with traduzir_erros(session):
        regras_def.nova_versao(session, cx, dict(cv.definicao or {}), usuario_id=user.id)
        cx.catalogo_versao = cv.versao
        session.add(cx)
        _log(session, fid, "catalogo.atualizado", caixa_id=cx.id, usuario_id=user.id,
             texto_livre=f"{cx.nome}: cópia atualizada para o catálogo v{cv.versao}.")
        resolver_notas(session, fid, chave=f"catalogo:{cx.id}:{cv.versao}")
        if cx.estado == "ativa":
            recalcular(session, fid, caixa_ids=[cx.id], motivo="catalogo.atualizado")
        session.commit()
    session.refresh(cx)
    return detalhe_caixa(session, cx)


# ── parâmetros e veterinários ───────────────────────────────────────────────
def _parametros_dict(p: SanitarioParametros) -> dict:
    return {k: getattr(p, k) for k in ("uf", "prazos_legais_ativo", "antecedencia_padrao_dias", "corrigir_ate",
                                       "dose_externa_sem_data", "peso_estimado", "modo_tuberculina",
                                       "aviso_offline_horas")} | {
        "atualizado_em": p.atualizado_em.isoformat() if p.atualizado_em else None}


@router.get("/parametros")
def obter_parametros(session: Session = Depends(get_session),
                     fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    p = session.exec(select(SanitarioParametros).where(SanitarioParametros.fazenda_id == fid)).first()
    if p is None:  # GET não grava: devolve os padrões sem criar a linha
        from fazenda.models import Fazenda
        faz = session.get(Fazenda, fid)
        p = SanitarioParametros(fazenda_id=fid, uf=faz.uf if faz else None)
    return _parametros_dict(p)


@router.put("/parametros")
def salvar_parametros(dados: ParametrosIn, session: Session = Depends(get_session),
                      user: Usuario = Depends(get_current_user),
                      fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    exigir_admin_fazenda(session, user, fid)
    p = regras_def.garantir_parametros(session, fid)
    for k, v in dados.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    p.atualizado_em, p.atualizado_por_usuario_id = datetime.utcnow(), user.id
    session.add(p)
    _log(session, fid, "parametros", usuario_id=user.id, texto_livre="Parâmetros do sanitário salvos.",
         payload=dados.model_dump(exclude_unset=True))
    session.commit()
    session.refresh(p)
    return _parametros_dict(p)


@router.get("/veterinarios")
def listar_veterinarios(session: Session = Depends(get_session),
                        fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    """Pessoas com a função Veterinário (Cadastros › Pessoas) + texto livre."""
    fid = exigir_fazenda(fazenda_id)
    return {"pessoas": [{"pessoa_id": p.id, "nome": p.nome, "crmv": p.crmv} for p in veterinarios_da_fazenda(session, fid)],
            "aceita_texto_livre": True}


@router.get("/eu")
def meu_papel(session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
              fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    """O que este usuário pode fazer no sanitário (o front esconde botões)."""
    from fazenda.rules.sanitario.permissoes import pessoa_veterinaria_do_usuario

    fid = exigir_fazenda(fazenda_id)
    adm = eh_admin_fazenda(session, user, fid)
    vet = pessoa_veterinaria_do_usuario(session, user, fid)
    return {"usuario_id": user.id, "administrador": adm, "veterinario_pessoa_id": vet.id if vet else None,
            "pode": {"cadastrar_caixa": adm, "aceitar_carencia": adm, "decidir_carencia": adm, "estornar": adm,
                     "lancar": True, "ler_exame": adm or vet is not None, "resolver_notas_admin": adm}}

