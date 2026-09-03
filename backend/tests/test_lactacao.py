"""
A entidade `Lactacao` — abertura, fechamento, DEL ao vivo, backfill — e as
duas travas que dependem dela: o controle leiteiro e o endpoint único de
encerramento de gestação.

O bug que tudo isto fecha: o sistema não tinha lactação. Cada tela inferia
"está em lactação" do seu jeito (existir `Parto`, `Animal.del_dias > 0`, o
código do lote ser 01/02/03), e as inferências discordavam. O sintoma
relatado: a matriz 14 continuou aparecendo como "novilha gestante, sem parto"
DEPOIS de o usuário lançar o aborto, mandar abrir a lactação, o animal entrar
no lote de lactação e já ter controle leiteiro lançado — porque o aborto não
criava `Parto` nenhum e "abrir lactação" só gravava `del_dias = 0`.
"""
from __future__ import annotations

import threading
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, ControleLeiteiro, Lactacao, Parto, Secagem, Servico
from fazenda.rules import lactacao as regras
from fazenda.rules.parto import TIPO_PARTO_ABORTO, eh_parto_produtivo, proxima_ordem_parto

HOJE = date.today()


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def client(engine):
    lock = threading.Lock()

    def _get_session_override():
        with lock, Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_id_escrita] = lambda: None
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: None

    with TestClient(main.app) as c:
        yield c

    main.app.dependency_overrides.clear()


def _add(engine, *objs):
    with Session(engine) as s:
        for o in objs:
            s.add(o)
        s.commit()


# ---------------------------------------------------------------------------
# eh_parto_produtivo / proxima_ordem_parto
# ---------------------------------------------------------------------------
def test_aborto_nao_e_parto_produtivo():
    assert not eh_parto_produtivo({"tipo_parto": "Aborto"})
    assert not eh_parto_produtivo({"tipo_parto": "  aborto "})   # caixa/espaço
    assert not eh_parto_produtivo({"tipo_parto": "ABÔRTO"})      # acento (o texto chega de 3 origens)
    assert eh_parto_produtivo({"tipo_parto": "Natimorto"})       # pariu: conta como cria
    assert eh_parto_produtivo({"tipo_parto": None})


def test_proxima_ordem_ignora_aborto():
    """Sem isso, o aborto no meio do histórico empurrava a ordem de parto: a
    3ª cria de verdade viraria a 4ª."""
    partos = [
        {"tipo_parto": "Parto normal", "ordem_parto": 1},
        {"tipo_parto": TIPO_PARTO_ABORTO, "ordem_parto": None},
        {"tipo_parto": "Parto normal", "ordem_parto": 2},
    ]
    assert proxima_ordem_parto(partos) == 3


def test_proxima_ordem_sem_ordem_gravada_usa_contagem():
    """Histórico importado sem a coluna: `(ordem or 0) + 1` devolvia 1 para
    uma vaca de três crias."""
    partos = [{"tipo_parto": None, "ordem_parto": None}] * 3
    assert proxima_ordem_parto(partos) == 4


def test_proxima_ordem_nunca_confia_no_max_gravado():
    """Regressão do bug real relatado pelo usuário (matriz 432 e outras): o
    1º parto veio da importação de planilha do Ideagri com `ordem_parto=0`
    (a planilha usa convenção base 0 — 0 = 1ª cria —, diferente da deste app,
    que é base 1). A versão ANTIGA de `proxima_ordem_parto` fazia
    `max(ordens) + 1` sobre os produtivos: com `ordens=[0]`, devolvia
    `max([0]) + 1 = 1` para o SEGUNDO parto — o mesmo número do primeiro,
    errado. A versão corrigida NUNCA olha o valor gravado: conta os
    produtivos do zero, sempre, e por isso devolve `2`, o certo,
    independente de o histórico trazer `ordem_parto=0`, `5` ou qualquer outra
    coisa."""
    partos = [{"tipo_parto": "Parto normal", "ordem_parto": 0}]   # 1º parto "importado", ordem errada
    assert proxima_ordem_parto(partos) == 2   # não 1 — é aqui que o bug antigo propagava o erro


def test_abriu_lactacao_no_aborto_conta_como_produtivo():
    """Aborto COM abertura de lactação é produtivo (pedido explícito do
    usuário) — funcionalmente equivalente a uma cria para fins de ordem de
    parto. Aborto SEM abertura de lactação continua fora da contagem."""
    assert eh_parto_produtivo({"tipo_parto": "Aborto", "abriu_lactacao": True})
    assert not eh_parto_produtivo({"tipo_parto": "Aborto", "abriu_lactacao": False})
    assert not eh_parto_produtivo({"tipo_parto": "Aborto"})           # campo ausente = False


# ---------------------------------------------------------------------------
# lactacao_aberta / del_vivo
# ---------------------------------------------------------------------------
def test_lactacao_aberta_e_del_vivo(engine):
    _add(engine, Animal(numero="14", sexo="F", ativo=True))
    with Session(engine) as s:
        regras.abrir_lactacao(
            s, numero_matriz="14", data_inicio=HOJE - timedelta(days=40), origem=regras.ORIGEM_ABORTO,
        )
        s.commit()
        assert regras.del_vivo(s, numero_matriz="14", data=HOJE) == 40
        # Dia do próprio evento: DEL 0, não `None` — pariu hoje.
        assert regras.del_vivo(s, numero_matriz="14", data=HOJE - timedelta(days=40)) == 0
        # Antes do evento: não estava em lactação.
        assert regras.del_vivo(s, numero_matriz="14", data=HOJE - timedelta(days=41)) is None


def test_quem_nunca_lactou_tem_del_none_e_nao_zero(engine):
    """`None` e `0` são coisas diferentes: 0 é "pariu hoje"."""
    _add(engine, Animal(numero="99", sexo="F", ativo=True))
    with Session(engine) as s:
        assert regras.del_vivo(s, numero_matriz="99") is None


def test_secagem_fecha_a_lactacao_e_o_dia_da_secagem_ja_conta_como_fechada(engine):
    _add(engine, Animal(numero="14", sexo="F", ativo=True))
    inicio, fim = HOJE - timedelta(days=300), HOJE - timedelta(days=30)
    with Session(engine) as s:
        regras.abrir_lactacao(s, numero_matriz="14", data_inicio=inicio, origem=regras.ORIGEM_PARTO)
        s.commit()
        regras.fechar_lactacao_por_secagem(s, numero_matriz="14", data_secagem=fim)
        s.commit()
        assert regras.lactacao_aberta(s, numero_matriz="14", data=HOJE) is None
        assert regras.lactacao_aberta(s, numero_matriz="14", data=fim) is None          # dia da secagem: fechada
        assert regras.lactacao_aberta(s, numero_matriz="14", data=fim - timedelta(days=1)) is not None


def test_abrir_lactacao_e_idempotente(engine):
    """Duplo clique / retry da fila offline não pode abrir duas lactações no
    mesmo dia — o DEL passaria a depender de qual delas a consulta pegasse."""
    _add(engine, Animal(numero="14", sexo="F", ativo=True))
    with Session(engine) as s:
        regras.abrir_lactacao(s, numero_matriz="14", data_inicio=HOJE, origem=regras.ORIGEM_PARTO)
        s.commit()
        regras.abrir_lactacao(s, numero_matriz="14", data_inicio=HOJE, origem=regras.ORIGEM_PARTO)
        s.commit()
        assert len(s.exec(select(Lactacao)).all()) == 1


def test_novo_parto_fecha_a_lactacao_anterior_sem_secagem(engine):
    """Vaca que pariu de novo sem passar pelo lote de secas: a lactação
    anterior encerra na data do novo parto, com `secagem_id` NULL — não se
    inventa uma secagem que não aconteceu."""
    _add(engine, Animal(numero="14", sexo="F", ativo=True))
    antes, agora = HOJE - timedelta(days=400), HOJE
    with Session(engine) as s:
        regras.abrir_lactacao(s, numero_matriz="14", data_inicio=antes, origem=regras.ORIGEM_PARTO)
        s.commit()
        regras.abrir_lactacao(s, numero_matriz="14", data_inicio=agora, origem=regras.ORIGEM_PARTO)
        s.commit()
        anteriores = sorted(s.exec(select(Lactacao)).all(), key=lambda l: l.data_inicio)
        assert anteriores[0].data_fim == agora
        assert anteriores[0].secagem_id is None
        assert anteriores[1].data_fim is None
        assert anteriores[1].numero_lactacao == 2


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------
def test_backfill_fecha_com_a_secagem_seguinte(engine):
    """(d) do plano de verificação: uma Lactacao por parto produtivo, fechada
    pela Secagem seguinte daquele animal ou pelo parto seguinte, o que vier
    primeiro. Determinístico — nenhuma data inventada."""
    p1, sec1, p2 = date(2024, 1, 10), date(2024, 10, 5), date(2025, 1, 20)
    _add(
        engine,
        Animal(numero="14", sexo="F", ativo=True),
        Parto(numero_matriz="14", data_parto=p1, ordem_parto=1, tipo_parto="Parto normal"),
        Parto(numero_matriz="14", data_parto=p2, ordem_parto=2, tipo_parto="Parto normal"),
        Secagem(numero_matriz="14", data_secagem=sec1, motivo="rotina"),
        # Aborto importado NÃO gera lactação: no histórico não há como saber se
        # a fazenda ordenhou a vaca depois dele.
        Parto(numero_matriz="14", data_parto=date(2023, 6, 1), tipo_parto=TIPO_PARTO_ABORTO, ordem_parto=None),
    )
    with Session(engine) as s:
        resultado = regras.backfill_lactacoes(s)
        s.commit()
        assert resultado["criadas"] == 2
        lactacoes = sorted(s.exec(select(Lactacao)).all(), key=lambda l: l.data_inicio)
        assert [l.data_inicio for l in lactacoes] == [p1, p2]
        assert lactacoes[0].data_fim == sec1          # fechada pela secagem, não pelo parto seguinte
        assert lactacoes[0].secagem_id is not None
        assert lactacoes[1].data_fim is None          # a última segue aberta
        assert all(l.origem == regras.ORIGEM_IMPORTACAO for l in lactacoes)


def test_backfill_fecha_com_o_parto_seguinte_quando_nao_houve_secagem(engine):
    p1, p2 = date(2024, 1, 10), date(2025, 1, 20)
    _add(
        engine,
        Animal(numero="15", sexo="F", ativo=True),
        Parto(numero_matriz="15", data_parto=p1, ordem_parto=1),
        Parto(numero_matriz="15", data_parto=p2, ordem_parto=2),
    )
    with Session(engine) as s:
        regras.backfill_lactacoes(s)
        s.commit()
        primeira = sorted(s.exec(select(Lactacao)).all(), key=lambda l: l.data_inicio)[0]
        assert primeira.data_fim == p2
        assert primeira.secagem_id is None


def test_backfill_e_idempotente(engine):
    _add(
        engine,
        Animal(numero="16", sexo="F", ativo=True),
        Parto(numero_matriz="16", data_parto=date(2024, 3, 1), ordem_parto=1),
    )
    with Session(engine) as s:
        regras.backfill_lactacoes(s)
        s.commit()
        regras.backfill_lactacoes(s)
        s.commit()
        assert len(s.exec(select(Lactacao)).all()) == 1


# ---------------------------------------------------------------------------
# Controle leiteiro (Peça 4)
# ---------------------------------------------------------------------------
def test_controle_leiteiro_sem_lactacao_aberta_e_recusado(client, engine):
    """(b) do plano: a rota aceitava QUALQUER COISA — vaca seca, novilha,
    bezerra e até animal inexistente."""
    _add(engine, Animal(numero="500", sexo="F", ativo=True))
    r = client.post("/producao/controles", json={
        "data_controle": HOJE.isoformat(),
        "entradas": [{"numero_matriz": "500", "ordenhas": [12.0, 10.0]}],
    })
    assert r.status_code == 409
    detalhe = r.json()["detail"]
    assert detalhe["erro"] == "sem_lactacao_aberta"
    assert "500" in detalhe["msg"] and "lance o parto/aborto" in detalhe["msg"]
    with Session(engine) as s:
        assert s.exec(select(ControleLeiteiro)).first() is None


def test_controle_leiteiro_grava_del_vivo_e_nao_o_campo_congelado(client, engine):
    """O DEL do controle vinha de `Animal.del_dias`, zerado no instante do
    parto e nunca mais atualizado — toda vaca que pariu pelo app entrava na
    curva de lactação com DEL 0."""
    _add(engine, Animal(numero="501", sexo="F", ativo=True, del_dias=0))
    with Session(engine) as s:
        regras.abrir_lactacao(
            s, numero_matriz="501", data_inicio=HOJE - timedelta(days=75), origem=regras.ORIGEM_PARTO,
        )
        s.commit()

    r = client.post("/producao/controles", json={
        "data_controle": HOJE.isoformat(),
        "entradas": [{"numero_matriz": "501", "ordenhas": [12.0, 10.0]}],
    })
    assert r.status_code == 200
    with Session(engine) as s:
        registro = s.exec(select(ControleLeiteiro)).one()
        assert registro.del_no_controle == 75
        assert registro.producao_kg == 22.0


def test_controle_retroativo_vale_pela_lactacao_daquele_dia(client, engine):
    """Lançar hoje o controle de uma vaca que já secou desde então: o
    controle pertence à lactação que estava de pé NAQUELE dia."""
    inicio, secagem, controle = HOJE - timedelta(days=300), HOJE - timedelta(days=30), HOJE - timedelta(days=100)
    _add(engine, Animal(numero="502", sexo="F", ativo=True))
    with Session(engine) as s:
        regras.abrir_lactacao(s, numero_matriz="502", data_inicio=inicio, origem=regras.ORIGEM_PARTO)
        s.commit()
        regras.fechar_lactacao_por_secagem(s, numero_matriz="502", data_secagem=secagem)
        s.commit()

    r = client.post("/producao/controles", json={
        "data_controle": controle.isoformat(),
        "entradas": [{"numero_matriz": "502", "ordenhas": [15.0]}],
    })
    assert r.status_code == 200
    with Session(engine) as s:
        assert s.exec(select(ControleLeiteiro)).one().del_no_controle == (controle - inicio).days


def test_listagem_de_animais_expoe_em_lactacao(client, engine):
    """A flag que passa a ser a fonte única dos filtros de "só quem está em
    lactação" no site e no app de campo."""
    _add(
        engine,
        Animal(numero="600", sexo="F", ativo=True),
        Animal(numero="601", sexo="F", ativo=True),
    )
    with Session(engine) as s:
        regras.abrir_lactacao(
            s, numero_matriz="600", data_inicio=HOJE - timedelta(days=10), origem=regras.ORIGEM_PARTO,
        )
        s.commit()

    linhas = {a["numero"]: a for a in client.get("/animais/").json()}
    assert linhas["600"]["em_lactacao"] is True
    assert linhas["600"]["del_dias"] == 10
    assert linhas["601"]["em_lactacao"] is False


# ---------------------------------------------------------------------------
# Encerramento de gestação (Peça 2)
# ---------------------------------------------------------------------------
def test_aborto_cria_parto_lactacao_e_perda_de_prenhez(client, engine):
    """(c) do plano — o caso da matriz 14 do relatório, ponta a ponta, com
    data RETROATIVA para provar que o DEL sai do evento e não do dia do
    lançamento.

    Aborto COM abertura de lactação é produtivo (pedido explícito do
    usuário, 27/08/2026): a vaca entrou em lactação de verdade, o que conta
    como uma cria para fins de ordem de parto — ver
    `fazenda.rules.parto.eh_parto_produtivo`."""
    data_aborto = HOJE - timedelta(days=25)
    _add(
        engine,
        Animal(numero="14", sexo="F", ativo=True, data_nasc=HOJE - timedelta(days=900)),
        # O serviço que originou a gestação perdida…
        Servico(numero_matriz="14", data_servico=HOJE - timedelta(days=200), diagnostico="POSITIVO", ult_ocorrencia=1),
        # …e um serviço ANTIGO, já resolvido, que o caminho errado poderia pegar.
        Servico(numero_matriz="14", data_servico=HOJE - timedelta(days=400), diagnostico="NEGATIVO"),
    )

    r = client.post("/reproducao/encerramento-gestacao", json={
        "numero_matriz": "14", "data": data_aborto.isoformat(), "tipo": "aborto",
        "abrir_lactacao": True, "motivo": "aborto",
    })
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["ordem_parto"] == 1              # aborto COM lactação avança a ordem de parto
    assert corpo["lactacao_aberta"] is True
    assert corpo["del_dias"] == 25               # data REAL do evento, não o dia do lançamento
    assert corpo["sugerir_lote"] is True

    with Session(engine) as s:
        parto = s.exec(select(Parto)).one()
        assert parto.tipo_parto == TIPO_PARTO_ABORTO
        assert parto.ordem_parto == 1
        assert parto.abriu_lactacao is True
        assert parto.data_parto == data_aborto

        lact = s.exec(select(Lactacao)).one()
        assert lact.data_inicio == data_aborto
        assert lact.origem == regras.ORIGEM_ABORTO
        assert lact.parto_id == parto.id
        assert lact.data_fim is None

        # A perda foi carimbada no serviço VIGENTE POSITIVO, não no mais antigo.
        servicos = {s_.data_servico: s_ for s_ in s.exec(select(Servico)).all()}
        assert servicos[HOJE - timedelta(days=200)].data_perda_prenhez == data_aborto
        assert servicos[HOJE - timedelta(days=200)].motivo_perda_prenhez == "aborto"
        assert servicos[HOJE - timedelta(days=400)].data_perda_prenhez is None

        # Campo congelado sincronizado, para as telas que ainda o leem.
        assert s.exec(select(Animal).where(Animal.numero == "14")).one().del_dias == 25


def test_aborto_reescreve_categoria_de_gestante_para_vazia(client, engine):
    """Caso relatado da novilha "14" (segunda rodada): mesmo com o Parto
    criado, a Lactacao aberta e o DEL sincronizado, `Animal.categoria_completa/
    categoria_abrev` continuavam dizendo "Novilha gestante" — campos escritos
    só pelo GERAL.csv, nunca por este endpoint. Só troca a palavra "gestante"
    por "vazia", preservando o resto do texto do Ideagri."""
    _add(engine, Animal(
        numero="14", sexo="F", ativo=True,
        categoria_completa="Novilha gestante", categoria_abrev="Novilha gestante",
    ))
    r = client.post("/reproducao/encerramento-gestacao", json={
        "numero_matriz": "14", "data": HOJE.isoformat(), "tipo": "aborto", "abrir_lactacao": True,
    })
    assert r.status_code == 200
    with Session(engine) as s:
        animal = s.exec(select(Animal).where(Animal.numero == "14")).one()
        assert animal.categoria_completa == "Novilha vazia"
        assert animal.categoria_abrev == "Novilha vazia"


def test_categoria_sem_a_palavra_gestante_fica_intacta(client, engine):
    """Texto que já não diz "gestante" (ex.: veio de um GERAL.csv mais
    recente, ou é de uma vaca que já tinha outro estado) não é mexido — a
    troca é conservadora de propósito, só a palavra exata."""
    _add(engine, Animal(
        numero="16", sexo="F", ativo=True,
        categoria_completa="Vaca em lactação", categoria_abrev="Vaca",
    ))
    r = client.post("/reproducao/encerramento-gestacao", json={
        "numero_matriz": "16", "data": HOJE.isoformat(), "tipo": "aborto", "abrir_lactacao": False,
    })
    assert r.status_code == 200
    with Session(engine) as s:
        animal = s.exec(select(Animal).where(Animal.numero == "16")).one()
        assert animal.categoria_completa == "Vaca em lactação"
        assert animal.categoria_abrev == "Vaca"


def test_parto_normal_tambem_reescreve_categoria_de_gestante_para_vazia(client, engine):
    """Não é exclusivo do aborto: qualquer encerramento de gestação apaga a
    palavra "gestante" do texto congelado — ela deixou de ser verdade."""
    _add(engine, Animal(numero="17", sexo="F", ativo=True, categoria_completa="Vaca gestante"))
    r = client.post("/reproducao/encerramento-gestacao", json={
        "numero_matriz": "17", "data": HOJE.isoformat(), "tipo": "parto", "crias": [],
    })
    assert r.status_code == 200
    with Session(engine) as s:
        assert s.exec(select(Animal).where(Animal.numero == "17")).one().categoria_completa == "Vaca vazia"


def test_aborto_sem_abrir_lactacao_ainda_cria_o_parto(client, engine):
    """Responder "não" no popup registra o aborto do mesmo jeito — é o `Parto`
    que tira a matriz do estado "gestante" na Ficha."""
    _add(engine, Animal(numero="15", sexo="F", ativo=True))
    r = client.post("/reproducao/encerramento-gestacao", json={
        "numero_matriz": "15", "data": HOJE.isoformat(), "tipo": "aborto", "abrir_lactacao": False,
    })
    assert r.status_code == 200
    assert r.json()["lactacao_aberta"] is False
    assert r.json()["ordem_parto"] is None        # sem lactação, aborto continua fora da contagem
    with Session(engine) as s:
        parto = s.exec(select(Parto)).one()
        assert parto.tipo_parto == TIPO_PARTO_ABORTO
        assert parto.ordem_parto is None
        assert parto.abriu_lactacao is False
        assert s.exec(select(Lactacao)).first() is None


def test_encerramento_tipo_parto_nao_carimba_perda_de_prenhez(client, engine):
    """Um parto normal resolveu a gestação do jeito certo. Marcar perda ali
    corromperia a taxa de perda de prenhez do rebanho."""
    _add(
        engine,
        Animal(numero="16", sexo="F", ativo=True),
        Servico(numero_matriz="16", data_servico=HOJE - timedelta(days=283), diagnostico="POSITIVO", ult_ocorrencia=1),
    )
    r = client.post("/reproducao/encerramento-gestacao", json={
        "numero_matriz": "16", "data": HOJE.isoformat(), "tipo": "parto", "abrir_lactacao": True,
        "crias": [{"numero": "16A", "sexo": "F", "nasceu_viva": True}],
    })
    assert r.status_code == 200
    assert r.json()["ordem_parto"] == 1
    assert r.json()["crias_criadas"] == ["16A"]
    with Session(engine) as s:
        assert s.exec(select(Servico)).one().data_perda_prenhez is None


# ---------------------------------------------------------------------------
# Regressão do bug real relatado pelo usuário — matriz com 1º parto vindo da
# importação do Ideagri (ordem_parto=0, convenção base 0 da planilha) e 2º
# parto lançado ao vivo pelo app.
# ---------------------------------------------------------------------------
def test_matriz_432_parto_importado_com_ordem_zero_nao_contamina_o_proximo(client, engine):
    """Simula exatamente o cenário relatado: o 1º parto foi inserido como um
    import faria (`Parto.ordem_parto=0`, direto no banco, sem passar pelo
    endpoint). O 2º parto é lançado ao vivo via
    POST /reproducao/encerramento-gestacao (tipo="parto") e precisa sair com
    `ordem_parto=2` — não `1`, que é o que a versão antiga do bug (confiando
    em `max(ordem gravada) + 1`) devolvia."""
    _add(
        engine,
        Animal(numero="432", sexo="F", ativo=True, data_nasc=HOJE - timedelta(days=1200)),
        Parto(numero_matriz="432", data_parto=HOJE - timedelta(days=300), ordem_parto=0, tipo_parto="Parto normal"),
    )
    r = client.post("/reproducao/encerramento-gestacao", json={
        "numero_matriz": "432", "data": HOJE.isoformat(), "tipo": "parto",
        "crias": [{"numero": "432A", "sexo": "F", "nasceu_viva": True}],
    })
    assert r.status_code == 200
    assert r.json()["ordem_parto"] == 2   # não 1 — é aqui que o bug antigo propagava o erro

    with Session(engine) as s:
        ordens = sorted(
            p.ordem_parto for p in s.exec(select(Parto).where(Parto.numero_matriz == "432")).all()
        )
        # O 1º parto (importado) continua gravado como 0 — dado histórico sujo,
        # corrigido pela ferramenta administrativa de reconstrução (ver
        # test_ordem_parto_partos_reconstrucao.py), não retroativamente aqui.
        assert ordens == [0, 2]


def test_aborto_com_lactacao_depois_parto_de_verdade_ordem_correta(client, engine):
    """Aborto COM abertura de lactação conta como 1ª cria; o parto de verdade
    que vem depois é a 2ª — não a 1ª, que seria o resultado se o aborto
    continuasse fora da contagem."""
    _add(engine, Animal(numero="700", sexo="F", ativo=True))
    r1 = client.post("/reproducao/encerramento-gestacao", json={
        "numero_matriz": "700", "data": (HOJE - timedelta(days=200)).isoformat(), "tipo": "aborto",
        "abrir_lactacao": True, "motivo": "aborto",
    })
    assert r1.json()["ordem_parto"] == 1

    r2 = client.post("/reproducao/encerramento-gestacao", json={
        "numero_matriz": "700", "data": HOJE.isoformat(), "tipo": "parto",
        "crias": [{"numero": "700A", "sexo": "F", "nasceu_viva": True}],
    })
    assert r2.status_code == 200
    assert r2.json()["ordem_parto"] == 2

    with Session(engine) as s:
        partos = sorted(s.exec(select(Parto).where(Parto.numero_matriz == "700")).all(), key=lambda p: p.data_parto)
        assert [p.ordem_parto for p in partos] == [1, 2]
        assert partos[0].abriu_lactacao is True
        assert partos[1].abriu_lactacao is False


def test_aborto_sem_lactacao_depois_parto_de_verdade_fica_fora_da_contagem(client, engine):
    """Contraste com o teste acima: aborto SEM abertura de lactação não
    conta — o parto de verdade que vem depois é a 1ª cria."""
    _add(engine, Animal(numero="701", sexo="F", ativo=True))
    r1 = client.post("/reproducao/encerramento-gestacao", json={
        "numero_matriz": "701", "data": (HOJE - timedelta(days=200)).isoformat(), "tipo": "aborto",
        "abrir_lactacao": False, "motivo": "aborto",
    })
    assert r1.json()["ordem_parto"] is None

    r2 = client.post("/reproducao/encerramento-gestacao", json={
        "numero_matriz": "701", "data": HOJE.isoformat(), "tipo": "parto",
        "crias": [{"numero": "701A", "sexo": "F", "nasceu_viva": True}],
    })
    assert r2.json()["ordem_parto"] == 1


def test_parto_normal_tambem_abre_lactacao(client, engine):
    """O endpoint antigo continua existindo, e precisa abrir lactação também —
    senão a trava do controle leiteiro barraria toda vaca recém-parida."""
    _add(engine, Animal(numero="17", sexo="F", ativo=True))
    r = client.post("/reproducao/parto", json={
        "numero_matriz": "17", "data_parto": (HOJE - timedelta(days=5)).isoformat(), "crias": [],
    })
    assert r.status_code == 200
    with Session(engine) as s:
        lact = s.exec(select(Lactacao)).one()
        assert lact.data_inicio == HOJE - timedelta(days=5)
        # DEL do campo congelado agora é o DEL ao vivo, não `0`.
        assert s.exec(select(Animal).where(Animal.numero == "17")).one().del_dias == 5


def test_secagem_pelo_endpoint_fecha_a_lactacao(client, engine):
    _add(engine, Animal(numero="18", sexo="F", ativo=True))
    with Session(engine) as s:
        regras.abrir_lactacao(
            s, numero_matriz="18", data_inicio=HOJE - timedelta(days=280), origem=regras.ORIGEM_PARTO,
        )
        s.commit()
    r = client.post("/producao/secagem", json={
        "numero_matriz": "18", "data_secagem": HOJE.isoformat(), "motivo": "rotina", "produtos": [],
    })
    assert r.status_code == 200
    with Session(engine) as s:
        assert s.exec(select(Lactacao)).one().data_fim == HOJE
        assert regras.lactacao_aberta(s, numero_matriz="18", data=HOJE) is None


def test_segunda_secagem_sem_lactacao_aberta_e_recusada_com_409(client, engine):
    """Caso relatado: secagem lançada em lote por engano em 04/07 fechou a
    lactação de vacas que na verdade só secariam semanas depois — e o
    sistema deixou lançar uma "segunda secagem" mais tarde sem avisar nada.
    Agora recusa com 409 e devolve a secagem que já fechou a lactação, pra a
    tela oferecer "substituir ou cancelar"."""
    _add(engine, Animal(numero="429", sexo="F", ativo=True))
    with Session(engine) as s:
        regras.abrir_lactacao(s, numero_matriz="429", data_inicio=HOJE - timedelta(days=295), origem=regras.ORIGEM_PARTO)
        s.commit()
    data_errada = (HOJE - timedelta(days=26)).isoformat()
    r1 = client.post("/producao/secagem", json={
        "numero_matriz": "429", "data_secagem": data_errada, "motivo": "rotina", "produtos": [],
    })
    assert r1.status_code == 200

    data_certa = (HOJE - timedelta(days=10)).isoformat()
    r2 = client.post("/producao/secagem", json={
        "numero_matriz": "429", "data_secagem": data_certa, "motivo": "rotina", "produtos": [],
    })
    assert r2.status_code == 409
    detalhe = r2.json()["detail"]
    assert detalhe["erro"] == "sem_lactacao_aberta"
    assert detalhe["secagem_anterior"]["data_secagem"] == data_errada

    with Session(engine) as s:
        # A segunda tentativa não criou NADA — nem uma segunda Secagem.
        assert len(s.exec(select(Secagem)).all()) == 1


def test_substituir_secagem_reabre_a_lactacao_e_fecha_na_data_nova(client, engine):
    _add(engine, Animal(numero="430", sexo="F", ativo=True))
    with Session(engine) as s:
        regras.abrir_lactacao(s, numero_matriz="430", data_inicio=HOJE - timedelta(days=295), origem=regras.ORIGEM_PARTO)
        s.commit()
    data_errada = (HOJE - timedelta(days=26)).isoformat()
    r1 = client.post("/producao/secagem", json={
        "numero_matriz": "430", "data_secagem": data_errada, "motivo": "rotina", "produtos": [],
    })
    assert r1.status_code == 200
    with Session(engine) as s:
        secagem_errada_id = s.exec(select(Secagem)).one().id

    data_certa = (HOJE - timedelta(days=10)).isoformat()
    r2 = client.post("/producao/secagem", json={
        "numero_matriz": "430", "data_secagem": data_certa, "motivo": "rotina", "produtos": [],
        "substituir_secagem_id": secagem_errada_id,
    })
    assert r2.status_code == 200, r2.text

    with Session(engine) as s:
        secagens = s.exec(select(Secagem)).all()
        assert len(secagens) == 1  # a errada foi substituída, não duplicada
        assert secagens[0].data_secagem.isoformat() == data_certa
        lact = s.exec(select(Lactacao)).one()
        assert lact.data_fim.isoformat() == data_certa
        assert lact.secagem_id == secagens[0].id


def test_excluir_secagem_reabre_a_lactacao_que_ela_fechou(client, engine):
    """Mesmo cuidado que excluir um Parto já tem
    (`_remover_lactacao_dos_partos_excluidos`) — excluir a Secagem também
    precisa desfazer o fechamento que ela causou."""
    _add(engine, Animal(numero="431", sexo="F", ativo=True))
    with Session(engine) as s:
        regras.abrir_lactacao(s, numero_matriz="431", data_inicio=HOJE - timedelta(days=295), origem=regras.ORIGEM_PARTO)
        s.commit()
    r = client.post("/producao/secagem", json={
        "numero_matriz": "431", "data_secagem": HOJE.isoformat(), "motivo": "rotina", "produtos": [],
    })
    assert r.status_code == 200
    with Session(engine) as s:
        secagem_id = s.exec(select(Secagem)).one().id
        assert s.exec(select(Lactacao)).one().data_fim == HOJE

    r2 = client.post("/exclusoes/confirmar", json={"tipo": "secagem", "id": str(secagem_id)})
    assert r2.status_code == 200, r2.text

    with Session(engine) as s:
        assert s.exec(select(Secagem)).first() is None
        lact = s.exec(select(Lactacao)).one()
        assert lact.data_fim is None
        assert lact.secagem_id is None
        assert regras.lactacao_aberta(s, numero_matriz="431", data=HOJE) is not None
