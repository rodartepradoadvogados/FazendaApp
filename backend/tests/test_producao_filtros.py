"""
Filtros novos dos relatórios de Produção (Menu › Produção do app de campo,
espec aprovada pelo dono em out/2026): controle leiteiro, qualidade do leite,
secagens, BST e pesagens.

Cobre as decisões da espec que têm regra de servidor:
  * lote = lote do animal NAQUELA DATA — gravado no lançamento (`lote_no_dia`)
    ou reconstruído pelo MovimentoLote; sem histórico, o lote atual marcado
    `lote_fonte="atual"`;
  * "em lactação" = lactação aberta na data; vendida/morta fora;
  * DEL no dia da aplicação (BST), origem Rotina × Sanidade;
  * pesagens: o lote escolhe QUAIS animais, o GMD usa TODAS as pesagens;
  * período invertido (400), registro sem data fora de qualquer período;
  * sem parâmetro nenhum = resposta de antes (o site depende disso);
  * multi-tenant: nada da fazenda 2 aparece na fazenda 1 — nem registro, nem
    histórico de movimentação influenciando a reconstrução de lote.

Datas fixas em 2026 (julho a setembro). Nomes de fazenda fictícios.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mktemp(suffix='.db')}")

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, ContratoFazenda, ContratoFazendaModulo, ControleLeiteiro, Fazenda, Lactacao, Lote, MovimentoLote,
    PesagemCorporal, QualidadeLeite, Sanidade, Secagem,
)
from fazenda.models.planos import MODULOS_COMERCIAIS

A1, M2, S4 = "01 - Alta", "02 - Média", "04 - Secas"
D = date(2026, 8, 15)  # dia em que a vaca 10 da fazenda 1 muda do lote 01 para o 02


def _dia(n: int) -> date:
    """Dia relativo a D (D-10, D+5...)."""
    return D + timedelta(days=n)


@pytest.fixture
def ctx(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Teste A"))
        s.add(Fazenda(id=2, nome="Fazenda Teste B"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
            for cod, nome in (("01", "Alta"), ("02", "Média"), ("04", "Secas")):
                s.add(Lote(codigo=cod, nome=nome, fazenda_id=fid))
        # ── Fazenda 1 ──
        s.add(Animal(numero="10", grupo_primario=M2, ativo=True, fazenda_id=1))   # 01 → 02 em D
        s.add(Animal(numero="11", grupo_primario=A1, ativo=True, fazenda_id=1))   # sem histórico de lote
        s.add(Animal(numero="12", grupo_primario=A1, ativo=False, fazenda_id=1))  # vendida
        s.add(Animal(numero="110", grupo_primario=A1, ativo=True, fazenda_id=1))  # pega busca por substring "11"
        s.add(MovimentoLote(numero_matriz="10", lote_origem=A1, lote_destino=M2, data_movimento=D, fazenda_id=1))
        for n in ("10", "11", "12", "110"):
            s.add(Lactacao(numero_matriz=n, data_inicio=date(2026, 6, 1), origem="parto", fazenda_id=1))
        # ── Fazenda 2: MESMOS números, outro histórico ──
        s.add(Animal(numero="10", grupo_primario=A1, ativo=True, fazenda_id=2))
        s.add(Animal(numero="11", grupo_primario=M2, ativo=True, fazenda_id=2))
        # Movimento da vaca 11 na fazenda 2 — não pode mexer no lote da 11 da fazenda 1.
        s.add(MovimentoLote(numero_matriz="11", lote_origem=S4, lote_destino=M2, data_movimento=_dia(-30), fazenda_id=2))
        s.add(Lactacao(numero_matriz="10", data_inicio=date(2026, 5, 1), origem="parto", fazenda_id=2))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "teste@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como(fid: int):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fid


def _add(engine, *objs):
    with Session(engine) as s:
        for o in objs:
            s.add(o)
        s.commit()


def _ctrl(numero, dia, kg, fid=1, lote_no_dia=None):
    return ControleLeiteiro(numero_matriz=numero, data_controle=dia, producao_kg=kg, fazenda_id=fid, lote_no_dia=lote_no_dia)


# ─────────────────────────────────────────────────────────────────────────────
# Controle leiteiro
# ─────────────────────────────────────────────────────────────────────────────
class TestControles:
    def _base(self, engine):
        _add(
            engine,
            _ctrl("10", _dia(-10), 20.0), _ctrl("10", _dia(-5), 21.0), _ctrl("10", _dia(5), 22.0),
            _ctrl("11", _dia(-5), 30.0), _ctrl("11", _dia(5), 31.0), _ctrl("11", _dia(6), 32.0),
            _ctrl("12", _dia(-5), 15.0), _ctrl("110", _dia(-5), 18.0),
            _ctrl("11", None, 99.0),  # registro sem data (dado legado)
            _ctrl("10", _dia(-5), 50.0, fid=2),  # fazenda 2, mesmo número
        )

    def test_sem_parametro_responde_como_antes(self, ctx):
        c, engine = ctx
        self._base(engine)
        r = c.get("/producao/controles")
        assert r.status_code == 200
        dados = r.json()
        # Todos os da fazenda 1, inclusive o sem data; nada da fazenda 2.
        assert dados["total"] == 9
        assert all(x["producao_kg"] != 50.0 for x in dados["controles"])
        assert any(x["data"] is None for x in dados["controles"])
        # grupo_primario continua sendo o lote ATUAL (compat. com o site).
        assert {x["grupo_primario"] for x in dados["controles"] if x["numero"] == "10"} == {M2}

    def test_periodo_exclui_registro_sem_data(self, ctx):
        c, engine = ctx
        self._base(engine)
        r = c.get("/producao/controles", params={"data_inicio": str(_dia(-30)), "data_fim": str(_dia(30))})
        assert r.status_code == 200
        assert all(x["data"] is not None for x in r.json()["controles"])
        assert r.json()["total"] == 8

    def test_periodo_invertido_400(self, ctx):
        c, _ = ctx
        r = c.get("/producao/controles", params={"data_inicio": "2026-09-10", "data_fim": "2026-09-01"})
        assert r.status_code == 400
        assert "Período inválido" in r.json()["detail"]

    def test_animal_por_numero_exato(self, ctx):
        c, engine = ctx
        self._base(engine)
        r = c.get("/producao/controles", params={"numeros": "11", "data_inicio": str(_dia(-30))})
        assert {x["numero"] for x in r.json()["controles"]} == {"11"}  # nunca o 110
        r = c.get("/producao/controles", params=[("numeros", "11"), ("numeros", "110"), ("data_inicio", str(_dia(-30)))])
        assert {x["numero"] for x in r.json()["controles"]} == {"11", "110"}

    def test_lote_na_data_pela_reconstrucao(self, ctx):
        c, engine = ctx
        self._base(engine)
        r = c.get("/producao/controles", params={"lotes": "01", "data_inicio": str(_dia(-30))})
        linhas = r.json()["controles"]
        da_10 = [x for x in linhas if x["numero"] == "10"]
        # Só os controles de ANTES da mudança para o 02 (lote reconstruído).
        assert sorted(x["data"] for x in da_10) == [str(_dia(-10)), str(_dia(-5))]
        assert {x["lote"] for x in da_10} == {A1}
        assert {x["lote_fonte"] for x in da_10} == {"historico"}
        # 11 sem histórico: lote atual, marcado como tal.
        da_11 = [x for x in linhas if x["numero"] == "11"]
        assert da_11 and {x["lote_fonte"] for x in da_11} == {"atual"}

        r2 = c.get("/producao/controles", params={"lotes": "2", "data_inicio": str(_dia(-30))})  # "2" == "02"
        assert [(x["numero"], x["data"]) for x in r2.json()["controles"]] == [("10", str(_dia(5)))]

    def test_varios_lotes(self, ctx):
        c, engine = ctx
        self._base(engine)
        r = c.get("/producao/controles", params={"lotes": "01,02", "data_inicio": str(_dia(-30))})
        assert {x["lote"] for x in r.json()["controles"]} == {A1, M2}
        assert r.json()["total"] == 8

    def test_lote_gravado_tem_precedencia(self, ctx):
        c, engine = ctx
        _add(engine, _ctrl("11", _dia(-5), 30.0, lote_no_dia=S4))
        r = c.get("/producao/controles", params={"lotes": "04"})
        linha = r.json()["controles"][0]
        assert linha["lote"] == S4 and linha["lote_fonte"] == "dia"

    def test_data_anterior_ao_primeiro_movimento_usa_lote_origem(self, ctx):
        c, engine = ctx
        _add(engine, _ctrl("10", date(2026, 6, 10), 19.0))
        r = c.get("/producao/controles", params={"numeros": "10"})
        assert r.json()["controles"][0]["lote"] == A1

    def test_rebanho_em_lactacao_tira_vendida_e_sem_lactacao(self, ctx):
        c, engine = ctx
        self._base(engine)
        # Controle de antes do parto (lactação ainda não aberta) — dado inconsistente.
        _add(engine, _ctrl("11", date(2026, 5, 20), 10.0))
        r = c.get("/producao/controles", params={"rebanho_lactacao": "true", "data_inicio": "2026-05-01"})
        numeros = {x["numero"] for x in r.json()["controles"]}
        assert "12" not in numeros  # vendida
        assert all(x["data"] != "2026-05-20" for x in r.json()["controles"])

    def test_ultimos_n_por_vaca(self, ctx):
        c, engine = ctx
        self._base(engine)
        r = c.get("/producao/controles", params={"ultimos": 1, "numeros": "11", "data_inicio": str(_dia(-30))})
        assert [x["data"] for x in r.json()["controles"]] == [str(_dia(6))]
        r = c.get("/producao/controles", params={"ultimos": 2, "numeros": "11", "data_inicio": str(_dia(-30))})
        assert [x["data"] for x in r.json()["controles"]] == [str(_dia(6)), str(_dia(5))]

    def test_lancamento_grava_lote_do_dia(self, ctx):
        """Controle retroativo de antes da mudança de lote grava o lote da época."""
        c, engine = ctx
        r = c.post("/producao/controles", json={
            "data_controle": str(_dia(-3)), "entradas": [{"numero_matriz": "10", "total_kg": 20}],
        })
        assert r.status_code == 200, r.text
        r = c.post("/producao/controles", json={
            "data_controle": str(_dia(3)), "entradas": [{"numero_matriz": "10", "total_kg": 21}],
        })
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            regs = {x.data_controle: x.lote_no_dia for x in s.exec(select(ControleLeiteiro)).all()}
        assert regs == {_dia(-3): A1, _dia(3): M2}

    def test_multitenant_reconstrucao_nao_usa_movimento_de_outra_fazenda(self, ctx):
        c, engine = ctx
        _add(engine, _ctrl("11", _dia(-60), 30.0))  # antes do movimento da 11 na fazenda 2
        r = c.get("/producao/controles", params={"numeros": "11"})
        linha = r.json()["controles"][0]
        assert linha["lote"] == A1 and linha["lote_fonte"] == "atual"
        _como(2)
        _add(engine, _ctrl("11", _dia(-60), 7.0, fid=2))
        r = c.get("/producao/controles", params={"numeros": "11"})
        assert [(x["producao_kg"], x["lote"]) for x in r.json()["controles"]] == [(7.0, S4)]

    def test_multitenant_filtro_lote_nao_vaza(self, ctx):
        c, engine = ctx
        self._base(engine)
        _como(2)
        r = c.get("/producao/controles", params={"lotes": "01", "data_inicio": str(_dia(-30))})
        assert [x["producao_kg"] for x in r.json()["controles"]] == [50.0]


# ─────────────────────────────────────────────────────────────────────────────
# Qualidade do leite
# ─────────────────────────────────────────────────────────────────────────────
class TestQualidade:
    def _base(self, engine):
        _add(
            engine,
            QualidadeLeite(data_coleta=_dia(-5), ccs=200, fazenda_id=1),            # tanque
            QualidadeLeite(numero_matriz="10", data_coleta=_dia(-5), ccs=300, fazenda_id=1),
            QualidadeLeite(numero_matriz="10", data_coleta=_dia(5), ccs=310, fazenda_id=1),
            QualidadeLeite(numero_matriz="11", data_coleta=_dia(5), ccs=400, nul=12.0, lactose_pct=4.6, fazenda_id=1),
            QualidadeLeite(numero_matriz="10", data_coleta=_dia(-5), ccs=999, fazenda_id=2),
        )

    def test_sem_parametro_compat(self, ctx):
        c, engine = ctx
        self._base(engine)
        r = c.get("/producao/qualidade-leite")
        assert r.json()["total"] == 4
        assert "tem_faixas_bonificacao" in r.json()

    def test_tanque_e_individual_separados(self, ctx):
        c, engine = ctx
        self._base(engine)
        t = c.get("/producao/qualidade-leite", params={"tipo": "tanque"}).json()["registros"]
        assert [x["ccs"] for x in t] == [200] and t[0]["tipo"] == "tanque"
        i = c.get("/producao/qualidade-leite", params={"tipo": "individual"}).json()["registros"]
        assert sorted(x["ccs"] for x in i) == [300, 310, 400]
        assert c.get("/producao/qualidade-leite", params={"tipo": "xyz"}).status_code == 400

    def test_vaca_e_lote_na_data(self, ctx):
        c, engine = ctx
        self._base(engine)
        r = c.get("/producao/qualidade-leite", params={"numeros": "10"}).json()["registros"]
        assert sorted(x["ccs"] for x in r) == [300, 310]  # tanque nunca entra com filtro de vaca
        r = c.get("/producao/qualidade-leite", params={"lotes": "01"}).json()["registros"]
        assert sorted(x["ccs"] for x in r) == [300, 400]  # 10 antes de D (lote 01) + 11
        assert {x["lote"] for x in r} == {A1}
        # Indicadores novos chegam na resposta (sólidos/ESD/lactose/NUL).
        r = c.get("/producao/qualidade-leite", params={"numeros": "11"}).json()["registros"][0]
        assert r["nul"] == 12.0 and r["lactose_pct"] == 4.6

    def test_periodo(self, ctx):
        c, engine = ctx
        self._base(engine)
        r = c.get("/producao/qualidade-leite", params={"data_inicio": str(_dia(0))}).json()
        assert r["total"] == 2
        assert c.get("/producao/qualidade-leite", params={"data_inicio": "2026-09-02", "data_fim": "2026-09-01"}).status_code == 400

    def test_multitenant(self, ctx):
        c, engine = ctx
        self._base(engine)
        _como(2)
        r = c.get("/producao/qualidade-leite", params={"numeros": "10"}).json()["registros"]
        assert [x["ccs"] for x in r] == [999]


# ─────────────────────────────────────────────────────────────────────────────
# Secagens
# ─────────────────────────────────────────────────────────────────────────────
class TestSecagens:
    def _base(self, engine):
        _add(
            engine,
            # A 11 é seca em D+10 e movida para o lote de secas NO MESMO DIA.
            Secagem(numero_matriz="11", data_secagem=_dia(10), motivo="rotina", fazenda_id=1),
            MovimentoLote(numero_matriz="11", lote_origem=A1, lote_destino=S4, data_movimento=_dia(10), fazenda_id=1),
            Secagem(numero_matriz="10", data_secagem=_dia(-3), motivo="mastite", fazenda_id=1),
            Secagem(numero_matriz="110", data_secagem=_dia(20), motivo="baixa_producao", fazenda_id=1),
            Secagem(numero_matriz="10", data_secagem=_dia(-3), motivo="rotina", fazenda_id=2),
        )

    def test_sem_parametro_compat(self, ctx):
        c, engine = ctx
        self._base(engine)
        r = c.get("/reproducao/secagens").json()
        assert r["total"] == 3
        assert {"numero", "data", "ano", "mes", "motivo"} <= set(r["secagens"][0])

    def test_lote_e_o_de_onde_saiu_nao_o_de_secas(self, ctx):
        c, engine = ctx
        self._base(engine)
        r = c.get("/reproducao/secagens", params={"lotes": "01"}).json()["secagens"]
        assert sorted(x["numero"] for x in r) == ["10", "11", "110"]
        assert c.get("/reproducao/secagens", params={"lotes": "04"}).json()["total"] == 0

    def test_motivo_animal_periodo(self, ctx):
        c, engine = ctx
        self._base(engine)
        assert [x["numero"] for x in c.get("/reproducao/secagens", params={"motivos": "mastite"}).json()["secagens"]] == ["10"]
        r = c.get("/reproducao/secagens", params=[("motivos", "rotina"), ("motivos", "baixa_producao")]).json()
        assert sorted(x["numero"] for x in r["secagens"]) == ["11", "110"]
        assert [x["numero"] for x in c.get("/reproducao/secagens", params={"numeros": "11"}).json()["secagens"]] == ["11"]
        r = c.get("/reproducao/secagens", params={"data_inicio": str(_dia(0)), "data_fim": str(_dia(15))}).json()
        assert [x["numero"] for x in r["secagens"]] == ["11"]
        assert c.get("/reproducao/secagens", params={"data_inicio": "2026-09-02", "data_fim": "2026-09-01"}).status_code == 400

    def test_multitenant(self, ctx):
        c, engine = ctx
        self._base(engine)
        _como(2)
        r = c.get("/reproducao/secagens", params={"lotes": "01"}).json()["secagens"]
        assert [(x["numero"], x["motivo"]) for x in r] == [("10", "rotina")]


# ─────────────────────────────────────────────────────────────────────────────
# BST
# ─────────────────────────────────────────────────────────────────────────────
class TestBst:
    def _base(self, engine):
        _add(
            engine,
            # DEL na aplicação: lactação aberta em 01/06 → D-5 = 70; D+5 = 80.
            Sanidade(numero_matriz="10", data_aplicacao=_dia(-5), produto="Lactotropin", atividade="BST",
                     natureza="preventivo", fazenda_id=1),
            Sanidade(numero_matriz="10", data_aplicacao=_dia(5), produto="Lactotropin", atividade="BST",
                     natureza="preventivo", fazenda_id=1),
            # Curativo da Sanidade com produto BST.
            Sanidade(numero_matriz="11", data_aplicacao=_dia(5), produto="Boostin 500", natureza="curativo", fazenda_id=1),
            # Sem lactação aberta na data (antes do parto).
            Sanidade(numero_matriz="11", data_aplicacao=date(2026, 5, 20), produto="Lactotropin", atividade="BST",
                     fazenda_id=1),
            Sanidade(numero_matriz="11", data_aplicacao=_dia(5), produto="Ivermectina", natureza="curativo", fazenda_id=1),
            Sanidade(numero_matriz="10", data_aplicacao=_dia(-5), produto="Lactotropin", atividade="BST", fazenda_id=2),
        )

    def test_sem_parametro_compat_e_campos_novos(self, ctx):
        c, engine = ctx
        self._base(engine)
        r = c.get("/producao/relatorio-bst").json()
        assert r["total"] == 4  # Ivermectina fora; fazenda 2 fora
        linha = next(x for x in r["aplicacoes"] if x["numero_matriz"] == "10" and x["data_aplicacao"] == str(_dia(-5)))
        assert linha["del_aplicacao"] == 70
        assert linha["del_hoje"] == (date.today() - date(2026, 6, 1)).days
        assert linha["origem"] == "Rotina BST"
        assert linha["lote"] == A1 and linha["lote_fonte"] == "historico"

    def test_origem(self, ctx):
        c, engine = ctx
        self._base(engine)
        san = c.get("/producao/relatorio-bst", params={"origem": "sanidade"}).json()["aplicacoes"]
        assert [(x["numero_matriz"], x["produto"], x["origem"]) for x in san] == [("11", "Boostin 500", "Sanidade")]
        rot = c.get("/producao/relatorio-bst", params={"origem": "rotina"}).json()
        assert rot["total"] == 3  # atividade "BST" é rotina mesmo sem natureza (dado antigo)
        assert c.get("/producao/relatorio-bst", params={"origem": "x"}).status_code == 400

    def test_faixa_de_del_no_dia_da_aplicacao(self, ctx):
        c, engine = ctx
        self._base(engine)
        r = c.get("/producao/relatorio-bst", params={"del_min": 75, "del_max": 85}).json()["aplicacoes"]
        assert sorted((x["numero_matriz"], x["del_aplicacao"]) for x in r) == [("10", 80), ("11", 80)]
        # Sem lactação aberta na data não entra quando há faixa de DEL.
        r = c.get("/producao/relatorio-bst", params={"del_min": 0}).json()["aplicacoes"]
        assert all(x["data_aplicacao"] != "2026-05-20" for x in r)
        assert c.get("/producao/relatorio-bst", params={"del_min": 90, "del_max": 10}).status_code == 400

    def test_lotes_animais_periodo(self, ctx):
        c, engine = ctx
        self._base(engine)
        r = c.get("/producao/relatorio-bst", params={"lotes": "02"}).json()["aplicacoes"]
        assert [(x["numero_matriz"], x["data_aplicacao"]) for x in r] == [("10", str(_dia(5)))]
        r = c.get("/producao/relatorio-bst", params={"numeros": "11", "data_inicio": str(_dia(0))}).json()
        assert r["total"] == 1
        assert c.get("/producao/relatorio-bst", params={"data_inicio": "2026-09-02", "data_fim": "2026-09-01"}).status_code == 400

    def test_aplicar_bst_grava_lote_do_dia(self, ctx):
        c, engine = ctx
        r = c.post("/agenda/bst/aplicar", json={"numeros_matriz": ["10"], "data_aplicacao": str(_dia(-2))})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            reg = s.exec(select(Sanidade).where(Sanidade.numero_matriz == "10", Sanidade.fazenda_id == 1)).one()
        assert reg.lote_no_dia == A1
        linha = c.get("/producao/relatorio-bst").json()["aplicacoes"][0]
        assert linha["lote"] == A1 and linha["lote_fonte"] == "dia"

    def test_multitenant(self, ctx):
        c, engine = ctx
        self._base(engine)
        _como(2)
        r = c.get("/producao/relatorio-bst", params={"lotes": "01"}).json()["aplicacoes"]
        assert len(r) == 1 and r[0]["del_aplicacao"] == (_dia(-5) - date(2026, 5, 1)).days


def test_del_na_data_igual_del_vivo(ctx):
    """MapaLactacoes.del_na_data (em memória) segue a MESMA regra de del_vivo."""
    from fazenda.rules.lactacao import del_vivo
    from fazenda.rules.lote_historico import MapaLactacoes

    _, engine = ctx
    _add(
        engine,
        Lactacao(numero_matriz="11", data_inicio=date(2025, 6, 1), data_fim=date(2026, 4, 1), fazenda_id=1),
    )
    with Session(engine) as s:
        mapa = MapaLactacoes(s, 1)
        for dia in (date(2025, 5, 31), date(2025, 6, 1), date(2026, 3, 31), date(2026, 4, 1), date(2026, 6, 1), _dia(0)):
            for n in ("10", "11", "inexistente"):
                assert mapa.del_na_data(n, dia) == del_vivo(s, numero_matriz=n, data=dia, fazenda_id=1), (n, dia)


# ─────────────────────────────────────────────────────────────────────────────
# Pesagens
# ─────────────────────────────────────────────────────────────────────────────
class TestPesagens:
    def _base(self, engine):
        _add(
            engine,
            # A 10 pesou no lote 01 antes de D e no 02 depois.
            PesagemCorporal(numero_matriz="10", data_pesagem=_dia(-20), peso_kg=500, grupo_primario=A1, fazenda_id=1),
            PesagemCorporal(numero_matriz="10", data_pesagem=_dia(-10), peso_kg=510, grupo_primario=A1, fazenda_id=1),
            PesagemCorporal(numero_matriz="10", data_pesagem=_dia(10), peso_kg=530, grupo_primario=M2, fazenda_id=1),
            PesagemCorporal(numero_matriz="11", data_pesagem=_dia(-20), peso_kg=600, grupo_primario=A1, fazenda_id=1),
            PesagemCorporal(numero_matriz="11", data_pesagem=_dia(10), peso_kg=630, grupo_primario=A1, fazenda_id=1),
            PesagemCorporal(numero_matriz="10", data_pesagem=_dia(-20), peso_kg=100, grupo_primario=A1, fazenda_id=2),
        )

    def test_lote_escolhe_animais_e_gmd_usa_todas_as_pesagens(self, ctx):
        c, engine = ctx
        self._base(engine)
        r = c.get("/producao/pesagens/relatorio", params={"lotes": "02", "data_inicio": str(_dia(-30)), "data_fim": str(_dia(30))})
        linhas = r.json()["linhas"]
        assert [x["numero_matriz"] for x in linhas] == ["10"]
        assert linhas[0]["num_pesagens"] == 3  # inclusive as feitas no lote 01
        assert linhas[0]["gmd_kg_dia"] == round(30 / 30, 3)
        assert linhas[0]["lote"] == M2
        assert linhas[0]["lotes_no_periodo"] == [A1, M2]

    def test_lote_pelo_movimento_sem_pesagem_no_lote(self, ctx):
        """Estava no lote 02 no período (movimento em D) mas só pesou fora dele."""
        c, engine = ctx
        _add(
            engine,
            PesagemCorporal(numero_matriz="10", data_pesagem=_dia(-20), peso_kg=500, grupo_primario=A1, fazenda_id=1),
            PesagemCorporal(numero_matriz="10", data_pesagem=_dia(-10), peso_kg=510, grupo_primario=A1, fazenda_id=1),
        )
        r = c.get("/producao/pesagens/relatorio", params={"lotes": "02", "data_inicio": str(_dia(-30)), "data_fim": str(_dia(30))})
        assert [x["numero_matriz"] for x in r.json()["linhas"]] == ["10"]
        r = c.get("/producao/pesagens/relatorio", params={"lotes": "02", "data_inicio": str(_dia(-30)), "data_fim": str(_dia(-1))})
        assert r.json()["total"] == 0

    def test_grupo_antigo_continua_cortando_como_antes(self, ctx):
        c, engine = ctx
        self._base(engine)
        r = c.get("/producao/pesagens/relatorio", params={"grupo": A1}).json()["linhas"]
        da_10 = next(x for x in r if x["numero_matriz"] == "10")
        assert da_10["num_pesagens"] == 2

    def test_animais_todos_periodo(self, ctx):
        c, engine = ctx
        self._base(engine)
        r = c.get("/producao/pesagens/relatorio", params={"numeros": "11"}).json()["linhas"]
        assert [x["numero_matriz"] for x in r] == ["11"]
        assert c.get("/producao/pesagens/relatorio").json()["total"] == 2
        assert c.get("/producao/pesagens/relatorio", params={"data_inicio": "2026-09-02", "data_fim": "2026-09-01"}).status_code == 400

    def test_multitenant(self, ctx):
        c, engine = ctx
        self._base(engine)
        _como(2)
        r = c.get("/producao/pesagens/relatorio", params={"lotes": "01"}).json()["linhas"]
        assert [(x["numero_matriz"], x["primeira_peso"]) for x in r] == [("10", 100)]
