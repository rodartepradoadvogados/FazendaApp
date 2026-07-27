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

POST /news/materias (exige a permissão pode_publicar_materias_blog —
"Adicionar matéria ao blog", em Configurações > News) publica DIRETO:
manchete, corpo do texto (materia) e 0-N fontes/URLs de referência, todas
guardadas em NoticiaNews sob a fonte fixa "Blog CowData". A tela News em si
(botão do topo + Configurações > News) só aparece para administradores, mas
publicar/excluir/revisar exige a permissão específica.

Toda matéria "de gente" nasce com revisado_final=False (aba "Revisão de
publicação definitiva" em Configurações > News) — não importa quem/o que a
publicou (robô /milknews, "Adicionar matéria ao blog" ou aprovação de
pendente). É uma etapa humana que o robô nunca realiza; ver POST
/news/materias/{id}/revisar-final. ENQUANTO não revisada, a matéria NÃO
aparece em GET / (nem na página pública, nem na aba "Matérias publicadas") —
só em GET /news/materias, que lista tudo. Notícias agregadas via RSS
(_atualizar_fonte) nascem já revisado_final=True: são filtradas por palavra-
chave automaticamente, sem etapa editorial humana.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_dono, get_current_user, get_current_user_opcional
from fazenda.database import get_session
from fazenda.models import FonteNews, LancamentoPendente, NotaCapa, NoticiaNews, SeedFlag, Usuario
from fazenda.rules.news_fetch import buscar_noticias_fonte, filtrar_relevantes

RESUMO_MAX = 800

router = APIRouter(prefix="/news", tags=["news"])

JANELA_PADRAO_DIAS = 7  # "última semana" — ver_tudo=false filtra para essa janela
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


class MateriaBlogIn(BaseModel):
    manchete: str
    materia: str
    fontes: list[str] = []
    imagem: str | None = None
    categoria: str | None = None


NOME_FONTE_BLOG_PROPRIO = "Blog CowData"


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


def seed_nota_capa_202607(session: Session) -> None:
    """Nota inicial exibida na Capa para o produtor (jul/2026) — resumo do PL
    913/26 (piso de R$2,50/litro), a mesma pauta já publicada em News. Roda
    uma única vez (SeedFlag); depois disso o dono da plataforma controla o
    conteúdo via PUT /news/nota-capa, inclusive desativando-a."""
    chave = "nota_capa_pl91326_202607"
    if session.get(SeedFlag, chave):
        return
    session.add(NotaCapa(
        titulo="Projeto de lei propõe piso de R$ 2,50/litro para o leite",
        texto=(
            "O PL 913/26, em tramitação na Câmara dos Deputados, propõe um preço "
            "mínimo nacional de R$ 2,50 por litro do leite pago ao produtor. "
            "Acompanhe a matéria completa na aba News."
        ),
    ))
    session.add(SeedFlag(chave=chave))
    session.commit()


NOME_FONTE_MILKNEWS = "robô Milknews"

# Lotes de matérias próprias do robô agendado /milknews — cada lote é um
# arquivo JSON em seed_data/milknews_lotes/<chave>.json (lista de itens:
# manchete, resumo, materia, link, data_publicacao, fontes). Publicar uma
# matéria nova = criar um arquivo novo, nunca editar um já existente — assim
# duas publicações em paralelo nunca conflitam no merge, e um branch antigo
# mergeado não consegue mais apagar lotes que ele não conhece (era o que
# acontecia quando tudo vivia num único dict gigante aqui no código; ver
# docs/milknews-rotina-publicacao.md). Cada lote roda uma única vez (SeedFlag
# em publicar_lotes_milknews, chave = nome do arquivo sem ".json"). `resumo`
# aceita até RESUMO_MAX (800) caracteres; `materia` é o corpo completo
# (título/lide/parágrafos) — se ausente, a matéria fica só com o resumo.
def _carregar_lotes_milknews(pasta: Path | None = None) -> dict[str, list[dict]]:
    """Lê cada <chave>.json de seed_data/milknews_lotes/ como um lote — a
    chave do lote é o nome do arquivo sem a extensão."""
    if pasta is None:
        pasta = Path(__file__).resolve().parent.parent.parent / "seed_data" / "milknews_lotes"
    if not pasta.is_dir():
        return {}
    return {
        arquivo.stem: json.loads(arquivo.read_text(encoding="utf-8"))
        for arquivo in sorted(pasta.glob("*.json"))
    }


MILKNEWS_LOTES: dict[str, list[dict]] = _carregar_lotes_milknews()


def _fonte_milknews(session: Session) -> FonteNews:
    """Get-or-create a fonte fixa do robô Milknews (manual — nunca busca RSS)."""
    fonte = session.exec(select(FonteNews).where(FonteNews.nome == NOME_FONTE_MILKNEWS)).first()
    if fonte:
        return fonte
    fonte = FonteNews(nome=NOME_FONTE_MILKNEWS, url="", manual=True, ativo=True)
    session.add(fonte)
    session.commit()
    session.refresh(fonte)
    return fonte


def publicar_lotes_milknews(session: Session) -> None:
    """Publica cada lote de MILKNEWS_LOTES como matérias já aprovadas (sem
    passar pela fila de aprovação), sob a fonte manual "robô Milknews". Cada
    lote roda uma única vez, guardado por SeedFlag — a rotina agendada só
    precisa acrescentar uma chave nova ao dict; lotes antigos nunca são
    reaplicados nem sobrescrevem edição manual. Como qualquer outra matéria,
    nasce com revisado_final=False (o robô nunca faz essa revisão).

    Também faz um backfill idempotente de `fontes` (links oficiais clicáveis)
    em matérias JÁ publicadas — se o dict for editado depois (ex.: para
    acrescentar as fontes numa matéria de um lote antigo), a próxima
    inicialização preenche o campo sem sobrescrever nada que já esteja lá."""
    for lote_chave, itens in MILKNEWS_LOTES.items():
        chave = f"milknews_lote_{lote_chave}"
        ja_publicado = session.get(SeedFlag, chave) is not None
        fonte = None
        for item in itens:
            link = (item.get("link") or "").strip()
            manchete = (item.get("manchete") or "").strip()
            if not link or not manchete:
                continue
            urls = [u.strip() for u in item.get("fontes", []) if u and u.strip()]

            existente = session.exec(select(NoticiaNews).where(NoticiaNews.link == link)).first()
            if existente:
                if urls and not existente.fontes:
                    existente.fontes = json.dumps(urls)
                    session.add(existente)
                continue
            if ja_publicado:
                continue

            data_publicacao = None
            if item.get("data_publicacao"):
                try:
                    data_publicacao = datetime.strptime(str(item["data_publicacao"]).strip(), "%Y-%m-%d")
                except ValueError:
                    pass
            resumo = (item.get("resumo") or "").strip() or None
            if resumo and len(resumo) > RESUMO_MAX:
                resumo = resumo[: RESUMO_MAX - 1].rstrip() + "…"
            materia = (item.get("materia") or "").strip() or None
            imagem = (item.get("imagem") or "").strip() or None
            categoria = (item.get("categoria") or "").strip() or None
            fonte = fonte or _fonte_milknews(session)
            session.add(NoticiaNews(
                fonte_id=fonte.id, manchete=manchete, resumo=resumo, materia=materia,
                link=link, data_publicacao=data_publicacao,
                fontes=json.dumps(urls) if urls else None,
                imagem=imagem, categoria=categoria,
            ))
        if not ja_publicado:
            session.add(SeedFlag(chave=chave))
        session.commit()


@router.get("/fontes")
def listar_fontes(session: Session = Depends(get_session), user: Usuario = Depends(exigir_dono)) -> list[dict]:
    return [f.model_dump() for f in session.exec(select(FonteNews).order_by(FonteNews.nome)).all()]


@router.post("/fontes")
def criar_fonte(dados: FonteIn, session: Session = Depends(get_session), user: Usuario = Depends(exigir_dono)) -> dict:
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
    fonte_id: int, dados: FonteIn, session: Session = Depends(get_session), user: Usuario = Depends(exigir_dono),
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
def excluir_fonte(fonte_id: int, session: Session = Depends(get_session), user: Usuario = Depends(exigir_dono)) -> dict:
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
                # Agregador RSS automático (filtrado por palavra-chave) — não passa
                # pela etapa humana de "revisão de publicação definitiva", que é
                # exclusiva das matérias controladas por gente (robô /milknews,
                # "Adicionar matéria ao blog", aprovação de pendente).
                revisado_final=True,
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
def testar_fonte(fonte_id: int, session: Session = Depends(get_session), user: Usuario = Depends(exigir_dono)) -> dict:
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
    dados: NoticiasManualIn, session: Session = Depends(get_session), user: Usuario = Depends(exigir_dono),
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


def _fonte_blog_propria(session: Session) -> FonteNews:
    """Get-or-create a fonte fixa que representa o nosso próprio blog (matérias
    escritas por nós via 'Adicionar matéria ao blog', não importadas de RSS
    externo). Marcada manual — nunca busca RSS sozinha."""
    fonte = session.exec(select(FonteNews).where(FonteNews.nome == NOME_FONTE_BLOG_PROPRIO)).first()
    if fonte:
        return fonte
    fonte = FonteNews(nome=NOME_FONTE_BLOG_PROPRIO, url="", manual=True, ativo=True)
    session.add(fonte)
    session.commit()
    session.refresh(fonte)
    return fonte


def _serializar_noticia(n: NoticiaNews) -> dict:
    dados = n.model_dump()
    dados["fontes"] = json.loads(n.fontes) if n.fontes else []
    return dados


@router.post("/materias")
def criar_materia_blog(
    dados: MateriaBlogIn, session: Session = Depends(get_session), user: Usuario = Depends(exigir_dono),
) -> dict:
    """Publica direto uma matéria escrita por nós em Configurações > News >
    Adicionar matéria ao blog — sem passar pela fila de aprovação (exige a
    permissão pode_publicar_materias_blog). A data de publicação exibida é
    sempre a de agora (quando publicamos no nosso blog), não a de nenhuma
    fonte externa. Nasce com revisado_final=False (ver /revisar-final)."""
    manchete = dados.manchete.strip()
    materia = dados.materia.strip()
    if not manchete or not materia:
        raise HTTPException(status_code=400, detail="Manchete e matéria são obrigatórias")

    urls = [u.strip() for u in dados.fontes if u.strip()]
    fonte = _fonte_blog_propria(session)
    noticia = NoticiaNews(
        fonte_id=fonte.id, manchete=manchete, materia=materia,
        fontes=json.dumps(urls) if urls else None,
        link=urls[0] if urls else f"blog://{uuid4().hex}",
        data_publicacao=datetime.utcnow(),
        imagem=(dados.imagem or "").strip() or None,
        categoria=(dados.categoria or "").strip() or None,
    )
    session.add(noticia)
    session.commit()
    session.refresh(noticia)
    return _serializar_noticia(noticia)


@router.delete("/materias/{noticia_id}")
def excluir_materia_blog(noticia_id: int, session: Session = Depends(get_session), user: Usuario = Depends(exigir_dono)) -> dict:
    noticia = session.get(NoticiaNews, noticia_id)
    if not noticia:
        raise HTTPException(status_code=404, detail="Matéria não encontrada")
    session.delete(noticia)
    session.commit()
    return {"excluido": True, "id": noticia_id}


@router.post("/materias/{noticia_id}/revisar-final")
def revisar_publicacao_final(
    noticia_id: int, session: Session = Depends(get_session), user: Usuario = Depends(exigir_dono),
) -> dict:
    """Confirma a revisão de publicação definitiva de UMA matéria (aba própria
    em Configurações > News) — vale para qualquer matéria já publicada,
    não importa a origem (robô /milknews, "Adicionar matéria ao blog" ou
    aprovação de pendente). Etapa exclusivamente humana: o robô nunca chama
    este endpoint."""
    noticia = session.get(NoticiaNews, noticia_id)
    if not noticia:
        raise HTTPException(status_code=404, detail="Matéria não encontrada")
    noticia.revisado_final = True
    noticia.revisado_final_em = datetime.utcnow()
    noticia.revisado_final_por = user.username
    session.add(noticia)
    session.commit()
    session.refresh(noticia)
    return _serializar_noticia(noticia)


class MateriaBlogEditIn(BaseModel):
    manchete: str
    materia: str | None = None
    resumo: str | None = None
    fontes: list[str] = []
    imagem: str | None = None
    categoria: str | None = None


@router.get("/materias")
def listar_todas_materias(session: Session = Depends(get_session), user: Usuario = Depends(exigir_dono)) -> list[dict]:
    """Lista TODAS as matérias — publicadas e aguardando revisão — para a tela
    Configurações > News (abas "Matérias publicadas" e "Revisão de publicação
    definitiva"). Diferente de GET /, que só devolve matérias já revisadas
    (visão pública)."""
    todas = session.exec(select(NoticiaNews)).all()
    todas_ordenadas = sorted(todas, key=lambda n: (n.data_publicacao or n.capturado_em), reverse=True)
    return [_serializar_noticia(n) for n in todas_ordenadas]


@router.put("/materias/{noticia_id}")
def atualizar_materia_blog(
    noticia_id: int, dados: MateriaBlogEditIn, session: Session = Depends(get_session), user: Usuario = Depends(exigir_dono),
) -> dict:
    """Edita manchete/corpo/fontes de uma matéria já publicada — usado no
    botão "Editar matéria" da aba Revisão de publicação definitiva, para
    corrigir o texto ou as referências antes de confirmar a revisão."""
    noticia = session.get(NoticiaNews, noticia_id)
    if not noticia:
        raise HTTPException(status_code=404, detail="Matéria não encontrada")
    manchete = dados.manchete.strip()
    if not manchete:
        raise HTTPException(status_code=400, detail="Manchete é obrigatória")
    urls = [u.strip() for u in dados.fontes if u.strip()]
    noticia.manchete = manchete
    if dados.materia is not None:
        noticia.materia = dados.materia.strip() or None
    if dados.resumo is not None:
        noticia.resumo = dados.resumo.strip() or None
    if dados.imagem is not None:
        noticia.imagem = dados.imagem.strip() or None
    if dados.categoria is not None:
        noticia.categoria = dados.categoria.strip() or None
    noticia.fontes = json.dumps(urls) if urls else None
    session.add(noticia)
    session.commit()
    session.refresh(noticia)
    return _serializar_noticia(noticia)


@router.get("/")
def listar_noticias(ver_tudo: bool = False, session: Session = Depends(get_session), user: Usuario | None = Depends(get_current_user_opcional)) -> dict:
    """Leitura pública — qualquer visitante (mesmo sem login) pode ler as
    matérias do blog. Só devolve matérias já revisadas (revisado_final=True):
    antes da revisão de publicação definitiva, a matéria existe no banco mas
    fica visível só em Configurações > News > Revisão de publicação
    definitiva (ver GET /materias) — nunca aqui nem na página pública."""
    fontes = session.exec(select(FonteNews).where(FonteNews.ativo == True).order_by(FonteNews.nome)).all()  # noqa: E712
    corte = datetime.utcnow() - timedelta(days=JANELA_PADRAO_DIAS)
    saida = []
    for fonte in fontes:
        _atualizar_fonte_se_necessario(session, fonte)
        todas = session.exec(
            select(NoticiaNews)
            .where(NoticiaNews.fonte_id == fonte.id, NoticiaNews.revisado_final == True)  # noqa: E712
            .order_by(NoticiaNews.capturado_em.desc())
        ).all()
        noticias = todas if ver_tudo else [n for n in todas if (n.data_publicacao or n.capturado_em) >= corte]
        saida.append({
            "fonte": {"id": fonte.id, "nome": fonte.nome, "url": fonte.url, "erro": fonte.ultimo_erro},
            "noticias": [_serializar_noticia(n) for n in noticias],
        })
    return {"janela_dias": JANELA_PADRAO_DIAS, "fontes": saida}


class NotaCapaIn(BaseModel):
    titulo: str
    texto: str
    ativa: bool = True


@router.get("/nota-capa")
def obter_nota_capa(session: Session = Depends(get_session)) -> dict | None:
    """Leitura pública — a nota ativa mais recente para exibir na Capa
    (aparece pra qualquer usuário logado da fazenda, é conteúdo único e
    compartilhado, não por tenant)."""
    nota = session.exec(
        select(NotaCapa).where(NotaCapa.ativa == True).order_by(NotaCapa.atualizado_em.desc())  # noqa: E712
    ).first()
    if not nota:
        return None
    return {"id": nota.id, "titulo": nota.titulo, "texto": nota.texto, "atualizado_em": nota.atualizado_em.isoformat()}


@router.put("/nota-capa")
def atualizar_nota_capa(
    dados: NotaCapaIn, session: Session = Depends(get_session), user: Usuario = Depends(exigir_dono),
) -> dict:
    """Só o dono da plataforma edita a nota da Capa — desativa a nota ativa
    anterior (se houver) e cria uma nova, mantendo histórico."""
    for nota in session.exec(select(NotaCapa).where(NotaCapa.ativa == True)).all():  # noqa: E712
        nota.ativa = False
        session.add(nota)
    nova = NotaCapa(titulo=dados.titulo.strip(), texto=dados.texto.strip(), ativa=dados.ativa)
    session.add(nova)
    session.commit()
    session.refresh(nova)
    return {"id": nova.id, "titulo": nova.titulo, "texto": nova.texto}
