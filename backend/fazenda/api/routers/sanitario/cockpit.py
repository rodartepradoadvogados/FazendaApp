"""
/painel-cowdata/sanitario — catálogo central de vacinas/exames (cockpit
CowData). Mesma guarda do Painel CowData > Farmácia (área "farmacia"; escrita
exige a permissão de edição), sessão de manutenção (tabelas GLOBAIS, sem
fazenda selecionada). Publicar uma versão nova NUNCA mexe nas caixas das
fazendas: cada fazenda vê o aviso "nova versão" e decide atualizar.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from fazenda.api.routers.sanitario.schemas import CatalogoCriarIn, CatalogoEditarIn, CatalogoVersaoIn
from fazenda.auth import exigir_area_painel_cowdata, exigir_permissao_painel_cowdata
from fazenda.database import get_session_manutencao
from fazenda.models import SanitarioCaixa, SanitarioCatalogo, SanitarioCatalogoVersao, Usuario
from fazenda.rules.sanitario.notas import upsert_nota

router = APIRouter(prefix="/painel-cowdata/sanitario", tags=["painel-cowdata-sanitario"])

_dep_leitura = Depends(exigir_area_painel_cowdata("farmacia"))
_dep_edicao = exigir_permissao_painel_cowdata("farmacia", "pode_editar_farmacia")


def _json(v):
    if isinstance(v, dict):
        return {k: _json(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_json(x) for x in v]
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _item(session: Session, cat: SanitarioCatalogo, com_versoes: bool = False) -> dict:
    cv = session.exec(select(SanitarioCatalogoVersao).where(
        SanitarioCatalogoVersao.catalogo_id == cat.id, SanitarioCatalogoVersao.versao == cat.versao_atual)).first()
    copias = session.exec(select(SanitarioCaixa).where(SanitarioCaixa.catalogo_id == cat.id,
                                                       SanitarioCaixa.estado != "arquivada")).all()
    out = {
        "id": cat.id, "chave": cat.chave, "nome": cat.nome, "tipo": cat.tipo, "versao_atual": cat.versao_atual,
        "padrao_fabrica": cat.padrao_fabrica, "ativo": cat.ativo, "uf_sugerida": cat.uf_sugerida,
        "versao_id": cv.id if cv else None, "definicao": cv.definicao if cv else None,
        "nota_mudanca": cv.nota_mudanca if cv else None, "base_legal": cv.base_legal if cv else None,
        "fazendas_com_copia": len({c.fazenda_id for c in copias}),
        "copias_desatualizadas": len([c for c in copias if (c.catalogo_versao or 0) < cat.versao_atual]),
    }
    if com_versoes:
        out["versoes"] = [{"id": v.id, "versao": v.versao, "nota_mudanca": v.nota_mudanca, "base_legal": v.base_legal,
                           "publicado_em": v.publicado_em.isoformat() if v.publicado_em else None}
                          for v in session.exec(select(SanitarioCatalogoVersao).where(
                              SanitarioCatalogoVersao.catalogo_id == cat.id).order_by(SanitarioCatalogoVersao.versao)).all()]
    return out


@router.get("/catalogo", dependencies=[_dep_leitura])
def listar(session: Session = Depends(get_session_manutencao)) -> list[dict]:
    return [_item(session, c) for c in session.exec(select(SanitarioCatalogo).order_by(SanitarioCatalogo.nome)).all()]


@router.get("/catalogo/{catalogo_id}", dependencies=[_dep_leitura])
def obter(catalogo_id: int, session: Session = Depends(get_session_manutencao)) -> dict:
    cat = session.get(SanitarioCatalogo, catalogo_id)
    if cat is None:
        raise HTTPException(status_code=404, detail="Item do catálogo não encontrado.")
    return _item(session, cat, com_versoes=True)


@router.post("/catalogo")
def criar(dados: CatalogoCriarIn, session: Session = Depends(get_session_manutencao),
          user: Usuario = Depends(_dep_edicao)) -> dict:
    if session.exec(select(SanitarioCatalogo).where(SanitarioCatalogo.chave == dados.chave)).first() is not None:
        raise HTTPException(status_code=409, detail="Já existe um item com essa chave.")
    definicao = _json(dados.definicao.para_definicao())
    definicao.setdefault("nome", dados.nome)
    definicao["tipo"] = dados.tipo
    cat = SanitarioCatalogo(chave=dados.chave, nome=dados.nome, tipo=dados.tipo, versao_atual=1,
                            padrao_fabrica=dados.padrao_fabrica, ativo=dados.ativo, uf_sugerida=dados.uf_sugerida)
    session.add(cat)
    session.flush()
    session.add(SanitarioCatalogoVersao(catalogo_id=cat.id, versao=1, definicao=definicao,
                                        nota_mudanca=dados.nota_mudanca or "Versão inicial.", base_legal=dados.base_legal,
                                        publicado_por_usuario_id=user.id))
    session.commit()
    session.refresh(cat)
    return _item(session, cat, com_versoes=True)


@router.put("/catalogo/{catalogo_id}")
def editar(catalogo_id: int, dados: CatalogoEditarIn, session: Session = Depends(get_session_manutencao),
           user: Usuario = Depends(_dep_edicao)) -> dict:
    cat = session.get(SanitarioCatalogo, catalogo_id)
    if cat is None:
        raise HTTPException(status_code=404, detail="Item do catálogo não encontrado.")
    for k, v in dados.model_dump(exclude_unset=True).items():
        setattr(cat, k, v)
    session.add(cat)
    session.commit()
    session.refresh(cat)
    return _item(session, cat, com_versoes=True)


@router.post("/catalogo/{catalogo_id}/versoes")
def publicar_versao(catalogo_id: int, dados: CatalogoVersaoIn, session: Session = Depends(get_session_manutencao),
                    user: Usuario = Depends(_dep_edicao)) -> dict:
    """Publica a versão N+1 (imutável). As fazendas com cópia recebem uma nota
    "catálogo mudou" (só administradores) — a caixa delas não muda sozinha."""
    cat = session.get(SanitarioCatalogo, catalogo_id)
    if cat is None:
        raise HTTPException(status_code=404, detail="Item do catálogo não encontrado.")
    definicao = _json(dados.definicao.para_definicao())
    definicao.setdefault("nome", cat.nome)
    nova = cat.versao_atual + 1
    session.add(SanitarioCatalogoVersao(catalogo_id=cat.id, versao=nova, definicao=definicao,
                                        nota_mudanca=dados.nota_mudanca, base_legal=dados.base_legal,
                                        publicado_por_usuario_id=user.id))
    cat.versao_atual = nova
    session.add(cat)
    session.flush()
    for cx in session.exec(select(SanitarioCaixa).where(SanitarioCaixa.catalogo_id == cat.id,
                                                        SanitarioCaixa.estado != "arquivada")).all():
        upsert_nota(session, cx.fazenda_id, f"catalogo:{cx.id}:{nova}", tipo="catalogo_mudou", caixa_id=cx.id,
                    titulo=f"Catálogo CowData: {cat.nome} tem a versão {nova}",
                    texto=(dados.nota_mudanca or "Ajuste publicado no catálogo central.")
                    + " A sua caixa não muda sozinha: abra o cadastro para atualizar.",
                    dados={"catalogo_id": cat.id, "versao": nova}, so_admin=True)
    session.commit()
    session.refresh(cat)
    return _item(session, cat, com_versoes=True)
