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
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_admin, exigir_pode_publicar, get_current_user, get_current_user_opcional
from fazenda.database import get_session
from fazenda.models import FonteNews, LancamentoPendente, NoticiaNews, SeedFlag, Usuario
from fazenda.rules.news_fetch import buscar_noticias_fonte, filtrar_relevantes

RESUMO_MAX = 800

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


class MateriaBlogIn(BaseModel):
    manchete: str
    materia: str
    fontes: list[str] = []


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


NOME_FONTE_MILKNEWS = "robô Milknews"

# Lotes de matérias próprias do robô agendado /milknews — cada chave roda uma
# única vez (SeedFlag em publicar_lotes_milknews), sob a fonte manual
# "robô Milknews". A rotina agendada só precisa acrescentar uma chave nova
# "milknews_<AAAAMMDD>" com uma lista de 1 matéria (manchete, resumo, link,
# data_publicacao); nunca altera lotes já existentes. `resumo` aceita até
# RESUMO_MAX (800) caracteres. `materia` é opcional — corpo completo do texto
# (título/lide/parágrafos), usado quando o post do /milknews é mais longo que
# cabe no resumo; se ausente, a matéria fica só com o resumo mesmo (igual ao
# comportamento anterior).
MILKNEWS_LOTES: dict[str, list[dict]] = {
    "milknews_20260718": [{
        "manchete": "Preço do leite recua em junho após alta do 1º semestre, aponta Cepea",
        "resumo": (
            "A Média Brasil do leite ao produtor, calculada pelo Cepea/Esalq, fechou junho em "
            "R$ 2,6474 por litro, leve recuo frente aos meses anteriores após a forte recuperação "
            "do início de 2026 — que havia levado o indicador a R$ 2,6584/L em abril, maior patamar "
            "do ano. A pressão agora vem do aumento das importações, 28% acima do mesmo período de "
            "2025, e da retomada da oferta interna no Sul do país. Dados: Cepea/Esalq (30/06/2026)."
        ),
        "link": "/news#milknews-2026-07-18-01",
        "data_publicacao": "2026-07-18",
        "fontes": [
            "https://www.cepea.org.br/br/indicador/leite.aspx",
            "https://opresenterural.com.br/preco-do-leite-recua-para-r-266-por-litro-enquanto-importacoes-crescem-28/",
        ],
    }],
    "milknews_20260718b": [{
        "manchete": "Preço-base do leite Classe I recua nos EUA em julho, aponta USDA",
        "resumo": (
            "Segundo o USDA (Agricultural Marketing Service), o preço-base do leite Classe I nos "
            "Estados Unidos caiu para US$ 21,33 por quintal (cwt) em julho, queda de US$ 0,85 frente "
            "a junho. O recuo ocorre em meio à expansão da produção americana, prevista 1,2% maior "
            "em 2026, com rebanhos crescendo para suprir a capacidade extra de processamento. O USDA "
            "também revisou para baixo a projeção do all-milk price de 2026. "
            "Dados: USDA/AMS (17/07/2026)."
        ),
        "link": "/news#milknews-2026-07-18-02",
        "data_publicacao": "2026-07-18",
        "fontes": [
            "https://www.ams.usda.gov/mnreports/dymadvancedprices.pdf",
            "https://www.ers.usda.gov/topics/animal-products/dairy/market-outlook",
        ],
    }],
    "milknews_20260718c": [{
        "manchete": "Venda de sêmen bovino para leite cresce 5,9% no 1º trimestre de 2026, aponta Asbia",
        "resumo": (
            "Segundo a Asbia (Associação Brasileira de Inseminação Artificial), em parceria com o "
            "Cepea/Esalq, as vendas de sêmen bovino para pecuária leiteira somaram 1.526.970 doses "
            "no 1º trimestre de 2026, alta de 5,9% frente ao mesmo período de 2025. O mercado total "
            "de sêmen bovino (leite e corte) cresceu 17,7% no trimestre, para 5,07 milhões de doses, "
            "puxado principalmente pelo corte (+26,1%). As importações de sêmen subiram 54,7% no "
            "período. Dados: Asbia/Cepea (1º trimestre de 2026)."
        ),
        "link": "/news#milknews-2026-07-18-03",
        "data_publicacao": "2026-07-18",
        "fontes": [
            "https://beefpoint.com.br/asbia-venda-de-semen-cresce-177-no-1o-tri-26-para-507-milhoes-de-doses/",
            "https://girodoboi.canalrural.com.br/pecuaria/comercializacao-de-semen-bovino-cresce-177-no-primeiro-trimestre-de-2026",
        ],
    }],
    "milknews_20260720_aprovadas": [
        {
            "manchete": "Leite spot avança na primeira quinzena de julho com oferta mais restrita",
            "resumo": (
                "O preço do leite spot subiu em todos os estados pesquisados na primeira quinzena "
                "de julho, impulsionado por demanda mais firme por derivados e uma oferta mais "
                "enxuta no campo. Dados: MilkPoint (17/07/2026)."
            ),
            "materia": (
                "O preço do leite spot subiu em todos os estados pesquisados na primeira quinzena de "
                "julho, impulsionado por demanda mais firme por derivados e uma oferta mais enxuta no "
                "campo.\n\n"
                "Segundo o MilkPoint, a média nacional do leite spot chegou a R$ 3,229 por litro, alta "
                "de R$ 0,170 frente ao levantamento anterior. São Paulo registrou a maior média entre "
                "os estados pesquisados, R$ 3,460 (+R$ 0,185), seguido por Minas Gerais (R$ 3,361), "
                "Santa Catarina (R$ 3,240), Paraná (R$ 3,235), Goiás (R$ 3,222) e Rio Grande do Sul "
                "(R$ 2,981).\n\n"
                "De acordo com a publicação, o movimento de alta reflete vendas de derivados lácteos "
                "em níveis considerados confortáveis e a preços melhores, o que aumentou a procura por "
                "leite in natura por parte da indústria. Essa demanda mais aquecida, somada a uma "
                "oferta mais restrita de leite no campo, explica o reajuste generalizado observado nos "
                "estados acompanhados.\n\n"
                "O movimento também aparece de forma mais ampla no acompanhamento do Cepea/Esalq, que "
                "vem registrando reação nos preços pagos ao produtor ao longo de 2026, após um período "
                "prolongado de queda — conforme detalhado no Boletim do Leite de julho, divulgado pela "
                "instituição."
            ),
            "link": "/news#milknews-2026-07-20-01",
            "data_publicacao": "2026-07-20",
            "fontes": [
                "https://www.milkpoint.com.br/noticias-e-mercado/panorama-mercado/leite-spot-registra-novo-ajuste-positivo-na-1-quinzena-de-julho-241420/",
                "https://www.cepea.org.br/br/releases/o-boletim-do-leite-de-julho-ja-esta-disponivel-2.aspx",
            ],
        },
        {
            "manchete": "Interleite Brasil 2026 reúne gestores para debater bastidores da gestão leiteira",
            "resumo": (
                "O MilkPoint promoveu uma live reunindo gestores de operações leiteiras de destaque no "
                "país para compartilhar lições práticas de gestão, no embalo do Fórum MilkPoint Mercado "
                "e do Interleite Brasil 2026. Dados: MilkPoint (2026)."
            ),
            "materia": (
                "O MilkPoint promoveu uma live reunindo gestores de operações leiteiras de destaque no "
                "país para compartilhar lições práticas de gestão, no embalo do Fórum MilkPoint Mercado "
                "e do Interleite Brasil 2026.\n\n"
                "O encontro trouxe três gestores à frente de operações leiteiras reconhecidas no "
                "Brasil, discutindo decisões do dia a dia da produção — de planejamento financeiro a "
                "organização de equipe — em um formato de troca direta de experiência entre pares do "
                "setor.\n\n"
                "O Fórum MilkPoint Mercado, citado como pano de fundo do debate, também trouxe à tona "
                "tendências para os \"bastidores\" do setor leiteiro, sinalizando um momento de "
                "transição na forma como produtores encaram a gestão do negócio, e não só a produção "
                "em si.\n\n"
                "Esse tipo de discussão ganha peso justamente num momento em que os preços do leite "
                "mostram recuperação — o que reforça, segundo o próprio debate, a importância de uma "
                "gestão eficiente para efetivamente captar essa margem, em vez de apenas repassá-la a "
                "custos operacionais mais altos."
            ),
            "link": "/news#milknews-2026-07-20-02",
            "data_publicacao": "2026-07-20",
            "fontes": [
                "https://www.milkpoint.com.br/noticias-e-mercado/giro-noticias/tres-gestores-uma-live-e-muitas-licoes-sobre-gestao-na-producao-de-leite-241467/",
                "https://www.milkpoint.com.br/noticias-e-mercado/giro-noticias/um-setor-em-virada-os-bastidores-e-tendencias-revelados-no-forum-milkpoint-mercado-240647/",
            ],
        },
        {
            "manchete": "Genética Semex ganha espaço na Expogrande 2026 com foco em heterose",
            "resumo": (
                "A genética bovina da Semex esteve entre os destaques da Expogrande 2026, com "
                "produtores cada vez mais atentos ao impacto direto da escolha genética sobre "
                "produtividade, carcaça e rentabilidade do rebanho. Dados: cobertura do evento (2026)."
            ),
            "materia": (
                "A genética bovina da Semex esteve entre os destaques da Expogrande 2026, com "
                "produtores cada vez mais atentos ao impacto direto da escolha genética sobre "
                "produtividade, carcaça e rentabilidade do rebanho.\n\n"
                "De acordo com cobertura do evento, o tema da heterose — o ganho de desempenho obtido "
                "pelo cruzamento estratégico entre raças — e da avaliação técnica dos animais entraram "
                "no centro das conversas durante a feira, reforçando uma tendência de produtores "
                "buscarem decisões genéticas mais embasadas, e não apenas guiadas por preferência "
                "racial.\n\n"
                "A Semex opera no Brasil desde 1995 como distribuidora exclusiva da Semex Alliance "
                "canadense, comercializando genética bovina com foco em ganhos de produtividade e "
                "eficiência para o produtor. O movimento acompanha um ano ativo para o mercado de "
                "genética leiteira no país como um todo: tanto a Alta Genetics quanto a ABS têm "
                "reforçado portfólio de touros, avaliações genéticas e serviços de manejo reprodutivo "
                "voltados a elevar a rentabilidade do rebanho — sinal de que a discussão sobre "
                "genética aplicada segue ganhando espaço entre os pecuaristas de leite brasileiros."
            ),
            "link": "/news#milknews-2026-07-20-03",
            "data_publicacao": "2026-07-20",
            "fontes": [
                "https://www.rcn67.com.br/agronegocio/genetica-bovina-da-semex-ganha-forca-na-expogrande-2026/",
                "https://semex.com.br/sobre",
                "https://altagenetics.com.br/",
            ],
        },
    ],
    "milknews_20260720b": [
        {
            "manchete": "Leite spot fecha julho estável após alta na primeira quinzena",
            "resumo": (
                "O leite spot encerrou a segunda quinzena de julho praticamente estável (média nacional "
                "a R$ 3,216/L, -R$ 0,013), após a alta generalizada da primeira quinzena, que levou a "
                "média a R$ 3,229/L (+R$ 0,170). O movimento acompanha o reajuste de 2% aprovado pelo "
                "Conseleite/MT no leite pago em julho. Dados: Cepea/Esalq via MilkPoint (07/2026)."
            ),
            "materia": (
                "O mercado de leite spot no Brasil encerrou a segunda quinzena de julho com preços "
                "praticamente estáveis, depois de uma valorização generalizada no início do mês, segundo "
                "dados do Cepea/Esalq divulgados pelo MilkPoint.\n\n"
                "Na primeira quinzena de julho, a média nacional do leite spot subiu para R$ 3,229 por "
                "litro, avanço de R$ 0,170 puxado pela maior demanda por leite fresco em meio a uma oferta "
                "mais restrita no campo. São Paulo liderou as cotações, a R$ 3,460, seguido por Minas "
                "Gerais (R$ 3,361), Santa Catarina, Paraná, Goiás e Rio Grande do Sul, todos em alta no "
                "período.\n\n"
                "Na segunda quinzena, o ritmo mudou: a média nacional recuou levemente para R$ 3,216, uma "
                "acomodação de R$ 0,013, com oferta e demanda mais equilibradas. Santa Catarina e Paraná "
                "tiveram pequenas altas, enquanto Goiás, Rio Grande do Sul, São Paulo e Minas Gerais "
                "registraram recuos discretos.\n\n"
                "O movimento acompanha o reajuste divulgado pelo Conseleite/Mato Grosso, que aprovou alta "
                "de 2% nos valores de referência do leite entregue em junho e pago em julho, válida em "
                "todas as faixas de volume e qualidade monitoradas pelo colegiado."
            ),
            "link": "/news#milknews-2026-07-20b-01",
            "data_publicacao": "2026-07-20",
            "fontes": [
                "https://www.milkpoint.com.br/noticias-e-mercado/panorama-mercado/leite-spot-registra-novo-ajuste-positivo-na-1-quinzena-de-julho-241420/",
                "https://www.milkpoint.com.br/noticias-e-mercado/panorama-mercado/leite-spot-sinaliza-relativa-estabilidade-na-segunda-quinzena-de-julho-241559/",
                "https://www.milkpoint.com.br/noticias-e-mercado/giro-noticias/conseleitemt-registra-ajuste-positivo-de-2-no-leite-pago-em-julho-de-2026-241555/",
                "https://cepea.org.br/br/indicador/leite.aspx",
            ],
        },
        {
            "manchete": "Antidumping do leite em pó fica suspenso e divide o setor",
            "resumo": (
                "O governo suspendeu, em caráter cautelar, as tarifas antidumping sobre o leite em pó "
                "importado da Argentina e do Uruguai. O Gecex/Camex reconheceu o dumping (preço até 53% "
                "menor), mas adiou a cobrança para avaliar efeitos na inflação; a FPA critica e a CNA "
                "rebate. O tema volta à próxima reunião do colegiado. Dados: MilkPoint (07/2026)."
            ),
            "materia": (
                "O governo federal suspendeu, em caráter cautelar, a aplicação de tarifas antidumping "
                "sobre o leite em pó importado da Argentina e do Uruguai, decisão que gerou reação imediata "
                "da bancada ruralista e contraponto técnico da CNA.\n\n"
                "Segundo o MilkPoint, o Gecex/Camex reconheceu a existência de dumping nas importações — "
                "com preço até 53% inferior ao praticado no Brasil, conforme apuração da Confederação da "
                "Agricultura e Pecuária do Brasil (CNA) — mas decidiu suspender a cobrança para avaliar "
                "possíveis efeitos sobre a inflação de alimentos e sobre a relação com o Mercosul. A Frente "
                "Parlamentar da Agropecuária (FPA) criticou a decisão, citando queda de cerca de 20% no "
                "preço recebido pelo produtor em estados como Minas Gerais, Paraná, Goiás, Rio Grande do "
                "Sul e Santa Catarina.\n\n"
                "Já a CNA argumenta, em nota técnica citada pelo MilkPoint, que a medida recairia apenas "
                "sobre o leite em pó de uso industrial — presente majoritariamente em produtos "
                "ultraprocessados, com peso de apenas 0,26% no IPCA — e não afetaria o leite consumido "
                "diretamente pelas famílias. A entidade também destaca que, sem o antidumping vigente entre "
                "2001 e 2017, o crescimento do setor caiu de 4,2% para 0,7% ao ano.\n\n"
                "O tema deve voltar à pauta na próxima reunião do Gecex-Camex, que decidirá se as tarifas "
                "serão restabelecidas."
            ),
            "link": "/news#milknews-2026-07-20b-02",
            "data_publicacao": "2026-07-20",
            "fontes": [
                "https://www.milkpoint.com.br/noticias-e-mercado/giro-noticias/fpa-cobra-governo-pela-suspensao-de-medida-antidumping-contra-leite-da-argentina-e-do-uruguai-241516/",
            ],
        },
        {
            "manchete": "Preço do soro de leite dispara no mundo e chega sem referência ao Brasil",
            "resumo": (
                "O concentrado proteico de soro (WPC) acumulou alta de mais de 100% em 12 meses na Europa, "
                "chegando a €22 mil/t na faixa de 80% de proteína, puxado em parte pela demanda ligada aos "
                "medicamentos GLP-1. No Brasil ainda não há referência de preço consolidada para o produto. "
                "Dados: StoneX/USDA via MilkPoint (06-07/2026)."
            ),
            "materia": (
                "O concentrado proteico de soro de leite (WPC), insumo antes tratado como subproduto do "
                "queijo, acumulou alta superior a 100% em doze meses na Europa e hoje é descrito como um "
                "dos ingredientes mais disputados da indústria global de alimentos, segundo reportagem do "
                "MilkPoint.\n\n"
                "De acordo com levantamento da StoneX citado pela publicação, o WPC com 80% de proteína "
                "chegou a 22 mil euros por tonelada na União Europeia, enquanto dados semanais do USDA "
                "mostram o produto negociado perto de treze dólares por libra nos Estados Unidos em meados "
                "de junho — um patamar elevado e sustentado, não um pico isolado. Um dos fatores por trás "
                "da demanda, segundo a reportagem, é a popularização de medicamentos da classe GLP-1, que "
                "estimula maior consumo de proteína para preservar massa magra durante o emagrecimento.\n\n"
                "No Brasil, ainda não existe uma referência de preço consolidada para o WPC, o que "
                "dificulta tanto o planejamento de quem compra o insumo quanto a captura de margem por quem "
                "tem capacidade de processá-lo. O MilkPoint informou que passará a mapear periodicamente os "
                "preços do produto no mercado nacional para suprir essa lacuna de dado."
            ),
            "link": "/news#milknews-2026-07-20b-03",
            "data_publicacao": "2026-07-20",
            "fontes": [
                "https://www.milkpoint.com.br/noticias-e-mercado/panorama-mercado/wpc-2026-o-que-a-crise-global-do-soro-de-leite-pode-significar-para-os-laticinios-no-brasil-241483/",
            ],
        },
        {
            "manchete": "Calor reduz produção de leite nos EUA e mercado global se reajusta",
            "resumo": (
                "O calor do verão americano reduz produção e componentes do leite em várias regiões dos "
                "EUA, segundo o USDA/AMS. Na semana de 13 a 17/07, a manteiga Grade AA caiu a US$ 1,59/lb, "
                "enquanto cheddar e dry whey subiram. No exterior, a Austrália produziu +5,4% em maio e a "
                "Nova Zelândia exportou US$ 2,3 bi (+6,9%). Dados: USDA/AMS (17/07/2026)."
            ),
            "materia": (
                "O relatório semanal do USDA/AMS Dairy Market News aponta queda na produção de leite em "
                "várias regiões dos Estados Unidos por causa do calor intenso do verão americano, com "
                "reflexos mistos nos preços das commodities lácteas.\n\n"
                "Segundo o USDA, o calor persistente na região Central do país segue reduzindo o volume e "
                "os componentes do leite, e Idaho registrou o fim de semana mais quente de 2026, afetando "
                "o conforto térmico, a produção e a composição do leite das vacas. Ao mesmo tempo, a "
                "demanda por leite fluido está mais fraca por causa do período de férias escolares, o que "
                "tem direcionado parte do volume antes destinado ao envase para as classes de uso II e "
                "IV.\n\n"
                "Na semana de 13 a 17 de julho, a manteiga Grade AA fechou em queda, a US$ 1,59 por libra, "
                "enquanto o queijo cheddar (blocos e barris) e o soro de leite seco (dry whey) subiram. No "
                "cenário internacional, a produção de leite da Austrália em maio cresceu 5,4% frente ao "
                "mesmo mês do ano anterior, e as exportações neozelandesas de leite em pó, manteiga e "
                "queijo somaram US$ 2,3 bilhões, alta de 6,9%."
            ),
            "link": "/news#milknews-2026-07-20b-04",
            "data_publicacao": "2026-07-20",
            "fontes": [
                "https://www.indexbox.io/blog/usda-dairy-market-report-mixed-cme-prices-and-summer-heat-impact-july-2026/",
                "https://www.ams.usda.gov/mnreports/dywweeklyreport.pdf",
            ],
        },
        {
            "manchete": "Antes do verão: como preparar o rebanho para o estresse térmico",
            "resumo": (
                "Ainda no inverno, especialistas já recomendam planejar o conforto térmico do rebanho "
                "antes do verão. O estresse térmico começa com ITU acima de 68 e atinge antes as vacas de "
                "alta produção (conforto ideal entre 8°C e 18°C), reduzindo produção, fertilidade e "
                "imunidade. Ventilação, aspersão, sombra e água fresca são as medidas-chave. Dados: "
                "Gadolando via Feed&Food (2026)."
            ),
            "materia": (
                "Embora o Brasil esteja em pleno inverno, especialistas em bovinocultura leiteira já "
                "alertam para a necessidade de planejar o manejo de conforto térmico do rebanho antes da "
                "chegada do verão, quando o calor pode comprometer produção, fertilidade e saúde das vacas "
                "de alta produção.\n\n"
                "De acordo com a Associação dos Criadores de Gado Holandês do Rio Grande do Sul "
                "(Gadolando), em reportagem da Feed&Food, o estresse térmico começa quando o Índice de "
                "Temperatura e Umidade (ITU) ultrapassa a marca de 68 — patamar bem inferior ao que "
                "normalmente se imagina como \"calor\". Vacas de alta produção, como as da raça Holandesa, "
                "geram mais calor metabólico e por isso sentem o efeito da temperatura e da umidade antes "
                "de outros animais, com conforto térmico ideal situado entre 8°C e 18°C.\n\n"
                "Os sinais de estresse térmico aparecem no comportamento do rebanho: respiração ofegante, "
                "salivação intensa e mais tempo em pé em vez de ruminando. Além da queda na produção de "
                "leite pela redução no consumo de matéria seca, o calor também compromete a fertilidade e "
                "enfraquece o sistema imunológico, aumentando a suscetibilidade a doenças.\n\n"
                "Entre as medidas recomendadas estão ventiladores, exaustores e aspersão de água em "
                "sistemas confinados, além de telhados com isolamento térmico e áreas sombreadas. A campo, "
                "recomenda-se sombra natural ou artificial, acesso constante a água fresca e o ajuste dos "
                "horários de manejo e alimentação para os períodos mais amenos do dia. O planejamento da "
                "infraestrutura de resfriamento deve começar antes do pico do calor para evitar perdas na "
                "safra de verão."
            ),
            "link": "/news#milknews-2026-07-20b-05",
            "data_publicacao": "2026-07-20",
            "fontes": [
                "https://feedfood.com.br/estresse-termico-desafia-pecuaria-leiteira-e-exige-manejo-especifico-no-verao/",
            ],
        },
    ],
}


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
            fonte = fonte or _fonte_milknews(session)
            session.add(NoticiaNews(
                fonte_id=fonte.id, manchete=manchete, resumo=resumo, materia=materia,
                link=link, data_publicacao=data_publicacao,
                fontes=json.dumps(urls) if urls else None,
            ))
        if not ja_publicado:
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
    dados: MateriaBlogIn, session: Session = Depends(get_session), user: Usuario = Depends(exigir_pode_publicar),
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
    )
    session.add(noticia)
    session.commit()
    session.refresh(noticia)
    return _serializar_noticia(noticia)


@router.delete("/materias/{noticia_id}")
def excluir_materia_blog(noticia_id: int, session: Session = Depends(get_session), user: Usuario = Depends(exigir_pode_publicar)) -> dict:
    noticia = session.get(NoticiaNews, noticia_id)
    if not noticia:
        raise HTTPException(status_code=404, detail="Matéria não encontrada")
    session.delete(noticia)
    session.commit()
    return {"excluido": True, "id": noticia_id}


@router.post("/materias/{noticia_id}/revisar-final")
def revisar_publicacao_final(
    noticia_id: int, session: Session = Depends(get_session), user: Usuario = Depends(exigir_pode_publicar),
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


@router.get("/materias")
def listar_todas_materias(session: Session = Depends(get_session), user: Usuario = Depends(exigir_admin)) -> list[dict]:
    """Lista TODAS as matérias — publicadas e aguardando revisão — para a tela
    Configurações > News (abas "Matérias publicadas" e "Revisão de publicação
    definitiva"). Diferente de GET /, que só devolve matérias já revisadas
    (visão pública)."""
    todas = session.exec(select(NoticiaNews)).all()
    todas_ordenadas = sorted(todas, key=lambda n: (n.data_publicacao or n.capturado_em), reverse=True)
    return [_serializar_noticia(n) for n in todas_ordenadas]


@router.put("/materias/{noticia_id}")
def atualizar_materia_blog(
    noticia_id: int, dados: MateriaBlogEditIn, session: Session = Depends(get_session), user: Usuario = Depends(exigir_pode_publicar),
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
