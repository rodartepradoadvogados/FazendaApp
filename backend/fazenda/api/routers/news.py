"""
Router de News — blog de importação de notícias de pecuária leiteira (botão
"News" no topo do site). Agrega manchete + resumo + link dos sites
cadastrados em Configurações > News (cadastro só de administrador), filtrando
por palavras-chave do setor (leite, produtor de leite, pecuária leiteira,
ordenha, Compost Barn, Free Stall). Mostra só os últimos 3 dias por site
(GET / com ver_tudo=true traz o histórico completo). Uma fonte com erro de
busca (site fora do ar, mudou de layout) nunca derruba as outras — o erro
fica visível para o administrador substituir/corrigir a URL.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_admin, get_current_user
from fazenda.database import get_session
from fazenda.models import FonteNews, NoticiaNews, Usuario
from fazenda.rules.news_fetch import buscar_noticias_fonte, filtrar_relevantes

router = APIRouter(prefix="/news", tags=["news"])

JANELA_PADRAO_DIAS = 3
INTERVALO_MIN_BUSCA_HORAS = 1  # não rebusca a mesma fonte mais de 1x por hora


class FonteIn(BaseModel):
    nome: str
    url: str
    ativo: bool = True


FONTES_PADRAO = [
    ("MilkPoint", "https://www.milkpoint.com.br/"),
    ("Notícias Agrícolas", "https://www.noticiasagricolas.com.br/cotacoes/leite"),
    ("Canal Rural", "https://www.canalrural.com.br/pecuaria/"),
    ("DairyReporter", "https://www.dairyreporter.com/"),
    ("DairyNews.today", "https://dairynews.today/"),
]


def seed_fontes_news(session: Session) -> None:
    """Cadastra as 5 fontes indicadas (3 nacionais + 2 internacionais) na
    primeira vez — nunca sobrescreve o que o administrador já editou depois."""
    for nome, url in FONTES_PADRAO:
        if session.exec(select(FonteNews).where(FonteNews.nome == nome)).first():
            continue
        session.add(FonteNews(nome=nome, url=url))
    session.commit()


@router.get("/fontes")
def listar_fontes(session: Session = Depends(get_session), user: Usuario = Depends(exigir_admin)) -> list[dict]:
    return [f.model_dump() for f in session.exec(select(FonteNews).order_by(FonteNews.nome)).all()]


@router.post("/fontes")
def criar_fonte(dados: FonteIn, session: Session = Depends(get_session), user: Usuario = Depends(exigir_admin)) -> dict:
    nome = dados.nome.strip()
    url = dados.url.strip()
    if not nome or not url:
        raise HTTPException(status_code=400, detail="Nome e URL são obrigatórios")
    if session.exec(select(FonteNews).where(FonteNews.nome == nome)).first():
        raise HTTPException(status_code=409, detail=f'Já existe uma fonte chamada "{nome}"')
    fonte = FonteNews(nome=nome, url=url, ativo=dados.ativo)
    session.add(fonte)
    session.commit()
    session.refresh(fonte)
    return fonte.model_dump()


@router.put("/fontes/{fonte_id}")
def atualizar_fonte(
    fonte_id: int, dados: FonteIn, session: Session = Depends(get_session), user: Usuario = Depends(exigir_admin),
) -> dict:
    fonte = session.get(FonteNews, fonte_id)
    if not fonte:
        raise HTTPException(status_code=404, detail="Fonte não encontrada")
    nome = dados.nome.strip()
    url = dados.url.strip()
    if not nome or not url:
        raise HTTPException(status_code=400, detail="Nome e URL são obrigatórios")
    fonte.nome = nome
    fonte.url = url
    fonte.ativo = dados.ativo
    # Trocar a URL é o próprio conserto de "site não funciona" — limpa o erro
    # anterior para a próxima busca partir zerada, em vez de continuar preso.
    fonte.ultimo_erro = None
    fonte.ultima_busca_em = None
    session.add(fonte)
    session.commit()
    session.refresh(fonte)
    return fonte.model_dump()


@router.delete("/fontes/{fonte_id}")
def excluir_fonte(fonte_id: int, session: Session = Depends(get_session), user: Usuario = Depends(exigir_admin)) -> dict:
    fonte = session.get(FonteNews, fonte_id)
    if not fonte:
        raise HTTPException(status_code=404, detail="Fonte não encontrada")
    for noticia in session.exec(select(NoticiaNews).where(NoticiaNews.fonte_id == fonte_id)).all():
        session.delete(noticia)
    session.delete(fonte)
    session.commit()
    return {"excluido": True, "id": fonte_id}


def _atualizar_fonte_se_necessario(session: Session, fonte: FonteNews) -> None:
    agora = datetime.utcnow()
    if fonte.ultima_busca_em and (agora - fonte.ultima_busca_em) < timedelta(hours=INTERVALO_MIN_BUSCA_HORAS):
        return
    fonte.ultima_busca_em = agora
    try:
        itens = filtrar_relevantes(buscar_noticias_fonte(fonte.url))
        for item in itens:
            if session.exec(select(NoticiaNews).where(NoticiaNews.link == item["link"])).first():
                continue
            session.add(NoticiaNews(
                fonte_id=fonte.id, manchete=item["manchete"], resumo=item.get("resumo"),
                link=item["link"], data_publicacao=item.get("data"),
            ))
        fonte.ultimo_erro = None
        fonte.ultima_busca_ok_em = agora
    except Exception as exc:  # nunca deixa uma fonte com defeito derrubar as outras
        fonte.ultimo_erro = str(exc)[:500]
    session.add(fonte)
    session.commit()


@router.get("/")
def listar_noticias(ver_tudo: bool = False, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    fontes = session.exec(select(FonteNews).where(FonteNews.ativo == True).order_by(FonteNews.nome)).all()  # noqa: E712
    corte = datetime.utcnow() - timedelta(days=JANELA_PADRAO_DIAS)
    saida = []
    for fonte in fontes:
        _atualizar_fonte_se_necessario(session, fonte)
        todas = session.exec(
            select(NoticiaNews).where(NoticiaNews.fonte_id == fonte.id).order_by(NoticiaNews.capturado_em.desc())
        ).all()
        noticias = todas if ver_tudo else [n for n in todas if (n.data_publicacao or n.capturado_em) >= corte]
        saida.append({
            "fonte": {"id": fonte.id, "nome": fonte.nome, "url": fonte.url, "erro": fonte.ultimo_erro},
            "noticias": [n.model_dump() for n in noticias],
        })
    return {"janela_dias": JANELA_PADRAO_DIAS, "fontes": saida}
