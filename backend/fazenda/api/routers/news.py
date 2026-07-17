"""
Router de News — blog de importação de notícias de pecuária leiteira (botão
"News" no topo do site). Agrega manchete + resumo + link dos sites
cadastrados em Configurações > News (cadastro só de administrador), filtrando
por palavras-chave do setor (leite, produtor de leite, pecuária leiteira,
ordenha, Compost Barn, Free Stall). Mostra só os últimos 3 dias por site
(GET / com ver_tudo=true traz o histórico completo). Uma fonte com erro de
busca (site fora do ar, mudou de layout) nunca derruba as outras — o erro
fica visível para o administrador substituir/corrigir a URL.

POST /news/manual (robô agendado externo, ex.: /milknews) nunca publica
direto — cada item vira um LancamentoPendente (tipo "noticia_manual") na
mesma fila de aprovação do Telegram, aparece no sininho de notificações, e só
gera a NoticiaNews de verdade quando o administrador aprova em /aprovacoes
(ver fazenda.rules.telegram_fluxos.criar_registro).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_admin, get_current_user
from fazenda.database import get_session
from fazenda.models import FonteNews, LancamentoPendente, NoticiaNews, SeedFlag, Usuario
from fazenda.rules.news_fetch import buscar_noticias_fonte, filtrar_relevantes

RESUMO_MAX = 500

router = APIRouter(prefix="/news", tags=["news"])

JANELA_PADRAO_DIAS = 3
INTERVALO_MIN_BUSCA_HORAS = 1  # não rebusca a mesma fonte mais de 1x por hora


class FonteIn(BaseModel):
    nome: str
    url: str
    ativo: bool = True


class NoticiaManualIn(BaseModel):
    fonte_nome: str
    manchete: str
    resumo: str | None = None
    link: str
    data_publicacao: str | None = None  # "AAAA-MM-DD"


class NoticiasManualIn(BaseModel):
    itens: list[NoticiaManualIn]


FONTES_PADRAO = [
    ("MilkPoint", "https://www.milkpoint.com.br/"),
    ("Notícias Agrícolas", "https://www.noticiasagricolas.com.br/cotacoes/leite"),
    # Feed RSS direto (confirmado), não a home — evita a proteção anti-bot que
    # bloqueia a página HTML.
    ("Canal Rural", "https://www.canalrural.com.br/feed/"),
    ("DairyReporter", "https://www.dairyreporter.com/Info/DairyReporter-RSS"),
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


def desligar_fontes_rss_e_apagar_noticias_202607(session: Session) -> None:
    """Decisão do usuário (jul/2026): a aba News passa a ser alimentada só
    pelo robô agendado /milknews (POST /news/manual), não mais pelas 5 fontes
    RSS padrão. Desliga essas fontes e apaga o que já tinha sido importado
    delas. Roda uma única vez (SeedFlag) — depois disso o administrador pode
    reativar/editar qualquer uma delas normalmente em Configurações > News
    sem que essa migração volte a desligar."""
    chave = "news_rss_desligado_202607"
    if session.get(SeedFlag, chave):
        return
    nomes = [nome for nome, _ in FONTES_PADRAO]
    for fonte in session.exec(select(FonteNews).where(FonteNews.nome.in_(nomes))).all():  # noqa: E712
        for noticia in session.exec(select(NoticiaNews).where(NoticiaNews.fonte_id == fonte.id)).all():
            session.delete(noticia)
        fonte.ativo = False
        session.add(fonte)
    session.add(SeedFlag(chave=chave))
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


def _atualizar_fonte(session: Session, fonte: FonteNews) -> int:
    """Busca a fonte agora mesmo (sem checar o intervalo mínimo) e grava o
    resultado. Retorna a quantidade de matérias novas gravadas; levanta a
    exceção original em vez de engoli-la, para o chamador decidir o que fazer
    com a mensagem de erro (gravar em ultimo_erro e/ou devolver pro admin)."""
    agora = datetime.utcnow()
    fonte.ultima_busca_em = agora
    try:
        itens = filtrar_relevantes(buscar_noticias_fonte(fonte.url))
        novas = 0
        for item in itens:
            if session.exec(select(NoticiaNews).where(NoticiaNews.link == item["link"])).first():
                continue
            session.add(NoticiaNews(
                fonte_id=fonte.id, manchete=item["manchete"], resumo=item.get("resumo"),
                link=item["link"], data_publicacao=item.get("data"),
            ))
            novas += 1
        fonte.ultimo_erro = None
        fonte.ultima_busca_ok_em = agora
        session.add(fonte)
        session.commit()
        return novas
    except Exception as exc:  # nunca deixa uma fonte com defeito derrubar as outras
        fonte.ultimo_erro = str(exc)[:500]
        session.add(fonte)
        session.commit()
        raise


def _atualizar_fonte_se_necessario(session: Session, fonte: FonteNews) -> None:
    if fonte.manual:
        return  # alimentada via POST /news/manual — nunca busca RSS sozinha
    agora = datetime.utcnow()
    if fonte.ultima_busca_em and (agora - fonte.ultima_busca_em) < timedelta(hours=INTERVALO_MIN_BUSCA_HORAS):
        return
    try:
        _atualizar_fonte(session, fonte)
    except Exception:
        pass  # o erro já ficou gravado em fonte.ultimo_erro


@router.post("/fontes/{fonte_id}/testar")
def testar_fonte(fonte_id: int, session: Session = Depends(get_session), user: Usuario = Depends(exigir_admin)) -> dict:
    """Força uma busca imediata desta fonte, ignorando o intervalo mínimo de
    1h — para o administrador testar depois de corrigir a URL ou de uma
    correção no fetch, sem precisar esperar."""
    fonte = session.get(FonteNews, fonte_id)
    if not fonte:
        raise HTTPException(status_code=404, detail="Fonte não encontrada")
    if fonte.manual:
        return {"ok": True, "materias_novas": 0, "erro": None, "manual": True}
    try:
        novas = _atualizar_fonte(session, fonte)
        return {"ok": True, "materias_novas": novas, "erro": None}
    except Exception as exc:
        return {"ok": False, "materias_novas": 0, "erro": str(exc)[:500]}


@router.post("/manual")
def importar_noticias_manual(
    dados: NoticiasManualIn, session: Session = Depends(get_session), user: Usuario = Depends(exigir_admin),
) -> dict:
    """Recebe matérias já apuradas por fora (ex.: robô agendado /milknews) e
    coloca cada uma na fila de aprovação (LancamentoPendente, tipo
    "noticia_manual") — nunca publica direto. O administrador vê no sininho
    de notificações e decide aprovar/rejeitar em /aprovacoes; só na aprovação
    a matéria vira uma NoticiaNews de verdade (ver
    fazenda.rules.telegram_fluxos.criar_registro). Ignora itens já publicados
    (mesmo link) ou já pendentes de uma execução anterior do robô."""
    from fazenda.rules import telegram_fluxos as fx

    novas = 0
    duplicadas = 0
    invalidas = 0
    for item in dados.itens:
        nome = item.fonte_nome.strip()
        link = item.link.strip()
        manchete = item.manchete.strip()
        if not nome or not link or not manchete:
            invalidas += 1
            continue
        if session.exec(select(NoticiaNews).where(NoticiaNews.link == link)).first():
            duplicadas += 1
            continue
        if _existe_pendente_com_link(session, link):
            duplicadas += 1
            continue

        resumo_txt = (item.resumo or "").strip() or None
        if resumo_txt and len(resumo_txt) > RESUMO_MAX:
            resumo_txt = resumo_txt[: RESUMO_MAX - 1].rstrip() + "…"

        payload = {
            "fonte_nome": nome, "manchete": manchete, "resumo": resumo_txt,
            "link": link, "data_publicacao": item.data_publicacao,
        }
        session.add(LancamentoPendente(
            tipo="noticia_manual", payload=json.dumps(payload),
            resumo=fx.montar_resumo("noticia_manual", payload),
            solicitante_nome="Robô /milknews",
        ))
        novas += 1
    session.commit()
    return {"recebidas": len(dados.itens), "pendentes_criados": novas, "duplicadas": duplicadas, "invalidas": invalidas}


def _existe_pendente_com_link(session: Session, link: str) -> bool:
    pendentes = session.exec(
        select(LancamentoPendente).where(LancamentoPendente.tipo == "noticia_manual", LancamentoPendente.status == "pendente")
    ).all()
    return any(json.loads(p.payload or "{}").get("link") == link for p in pendentes)


def criar_noticia_a_partir_de_pendente(dados: dict, session: Session) -> dict:
    """Materializa um LancamentoPendente(tipo="noticia_manual") — chamado só
    quando o administrador aprova em /aprovacoes. Reaproveita o mesmo
    get-or-create de fonte (marcada manual) usado antes da fila existir."""
    nome = (dados.get("fonte_nome") or "").strip()
    link = (dados.get("link") or "").strip()
    manchete = (dados.get("manchete") or "").strip()
    if not nome or not link or not manchete:
        raise ValueError("Fonte, manchete e link são obrigatórios")
    if session.exec(select(NoticiaNews).where(NoticiaNews.link == link)).first():
        raise ValueError("Esta notícia já foi publicada (link duplicado)")

    fonte = session.exec(select(FonteNews).where(FonteNews.nome == nome)).first()
    if not fonte:
        dominio = urlparse(link).netloc or link
        fonte = FonteNews(nome=nome, url=f"https://{dominio}/", manual=True)
        session.add(fonte)
        session.commit()
        session.refresh(fonte)

    data_publicacao = None
    if dados.get("data_publicacao"):
        try:
            data_publicacao = datetime.strptime(str(dados["data_publicacao"]).strip(), "%Y-%m-%d")
        except ValueError:
            pass

    noticia = NoticiaNews(fonte_id=fonte.id, manchete=manchete, resumo=dados.get("resumo"), link=link, data_publicacao=data_publicacao)
    session.add(noticia)
    session.commit()
    session.refresh(noticia)
    return noticia.model_dump()


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
