"""
Testes dos critérios de seleção de animais por lote (cumulativos) e da
prévia de quantos/quais animais atendem.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, Lote, Parto, PesagemCorporal, Sanidade, Secagem, Servico


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


class TestPersistenciaCriterios(object):
    def test_cria_lote_com_criterios(self, client):
        c, _ = client
        r = c.post("/lotes/", json={
            "codigo": "05", "nome": "Novilhas aptas",
            "categorias": "novilha", "peso_min": 300, "novilhas_gestantes": False,
        })
        assert r.status_code == 200
        assert r.json()["categorias"] == "novilha"
        assert r.json()["peso_min"] == 300

    def test_edita_lote_atualiza_criterios(self, client):
        c, _ = client
        c.post("/lotes/", json={"codigo": "05", "nome": "X"})
        lote_id = next(l["id"] for l in c.get("/lotes/").json() if l["codigo"] == "05")
        r = c.put(f"/lotes/{lote_id}", json={"codigo": "05", "nome": "X", "em_tratamento": True, "idade_dias_min": 60})
        assert r.json()["em_tratamento"] is True
        assert r.json()["idade_dias_min"] == 60

    def test_rejeita_faixa_peso_invertida(self, client):
        c, _ = client
        r = c.post("/lotes/", json={"codigo": "06", "nome": "X", "peso_min": 400, "peso_max": 300})
        assert r.status_code == 400


class TestPreviewCriterios(object):
    def _seed(self, engine):
        hoje = date.today()
        with Session(engine) as s:
            # Vaca em lactação, DEL 50, produção 25L
            s.add(Animal(numero="1", categoria_completa="Vaca em lactação", categoria_abrev="Vaca",
                         del_dias=50, ult_cl_kg=25, sit_rep="Ins.", data_nasc=hoje - timedelta(days=1500), ativo=True))
            # Novilha apta vazia, sem serviço
            s.add(Animal(numero="2", categoria_completa="Novilha", categoria_abrev="Novilha",
                         sit_rep=None, data_nasc=hoje - timedelta(days=600), ativo=True))
            # Novilha gestante (diagnostico positivo)
            s.add(Animal(numero="3", categoria_completa="Novilha", categoria_abrev="Novilha",
                         sit_rep="Ges.", diagnostico="POSITIVO", data_nasc=hoje - timedelta(days=650), ativo=True))
            # Vaca seca
            s.add(Animal(numero="4", categoria_completa="Vaca seca", categoria_abrev="Vaca",
                         del_dias=None, data_nasc=hoje - timedelta(days=1800), ativo=True))
            s.commit()
            # peso 350kg para a novilha 3 (gestante)
            s.add(PesagemCorporal(numero_matriz="3", data_pesagem=hoje, peso_kg=350))
            # serviço positivo há 100 dias para a novilha 3 (gestante confirmada)
            s.add(Servico(numero_matriz="3", data_servico=hoje - timedelta(days=100), diagnostico="POSITIVO"))
            # aplicação de sanidade recente para o animal 1 (em tratamento)
            s.add(Sanidade(numero_matriz="1", produto="Antibiótico X", data_aplicacao=hoje - timedelta(days=3)))
            # secagem real para o animal 4 — situação produtiva agora é AO VIVO
            # (a partir do Secagem/Parto mais recente), não do texto congelado
            # de categoria_completa (ver fazenda.rules.lote_criterios).
            s.add(Secagem(numero_matriz="4", data_secagem=hoje - timedelta(days=20), motivo="rotina"))
            s.commit()

    def test_filtra_por_status_lactacao(self, client):
        c, engine = client
        self._seed(engine)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "status_lactacao": "seca"})
        assert r.json()["animais"] == ["4"]

    def test_filtra_por_categoria(self, client):
        c, engine = client
        self._seed(engine)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "categorias": "novilha"})
        assert set(r.json()["animais"]) == {"2", "3"}

    def test_filtra_por_producao(self, client):
        c, engine = client
        self._seed(engine)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "producao_min": 20, "producao_max": 30})
        assert r.json()["animais"] == ["1"]

    def test_filtra_por_peso(self, client):
        c, engine = client
        self._seed(engine)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "peso_min": 300})
        assert r.json()["animais"] == ["3"]

    def test_novilhas_gestantes(self, client):
        c, engine = client
        self._seed(engine)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "novilhas_gestantes": True})
        assert r.json()["animais"] == ["3"]

    def test_novilhas_inseminadas_exclui_gestantes(self, client):
        c, engine = client
        self._seed(engine)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "novilhas_inseminadas": True})
        # animal 3 já tem diagnóstico positivo (gestante) -> não entra em "inseminadas"
        assert r.json()["animais"] == []

    def test_em_tratamento(self, client):
        c, engine = client
        self._seed(engine)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "em_tratamento": True})
        assert r.json()["animais"] == ["1"]

    def test_idade_dias_min(self, client):
        c, engine = client
        self._seed(engine)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "idade_dias_min": 1700})
        assert r.json()["animais"] == ["4"]

    def test_cumulativo_e_logico(self, client):
        c, engine = client
        self._seed(engine)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "categorias": "novilha", "peso_min": 300})
        assert r.json()["animais"] == ["3"]

    def test_faltando_dias_para_o_parto(self, client):
        c, engine = client
        self._seed(engine)
        # gestação de 283 dias, serviço há 100 dias -> faltam 183 dias
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "dias_para_parto_min": 170, "dias_para_parto_max": 190})
        assert r.json()["animais"] == ["3"]


class TestParaJaResolvePreParto(object):
    """Vaca 3335 pariu, mas o serviço positivo antigo continuava contando
    "dias para o parto"/"Pré-parto" — no dia seguinte ao parto, o sistema
    sugeria "faltam 2 dias para o parto", o que é logicamente impossível
    (ver fazenda.rules.lote_criterios._ultimo_servico_positivo)."""

    def _seed(self, engine, dias_desde_o_parto: int):
        hoje = date.today()
        from fazenda.rules.gestation import dias_gestacao
        gestacao = round(dias_gestacao(None))
        # Serviço datado para que, SEM considerar o parto, "faltariam 2 dias
        # para o parto" hoje — exatamente o cenário relatado.
        data_servico = hoje - timedelta(days=gestacao - 2)
        with Session(engine) as s:
            s.add(Animal(numero="3335", categoria_completa="Vaca em lactação", categoria_abrev="Vaca",
                         sit_rep="Ges.", diagnostico="POSITIVO", data_nasc=hoje - timedelta(days=1500), ativo=True))
            s.commit()
            s.add(Servico(numero_matriz="3335", data_servico=data_servico, diagnostico="POSITIVO"))
            s.add(Parto(numero_matriz="3335", data_parto=hoje - timedelta(days=dias_desde_o_parto)))
            s.commit()

    def test_pre_parto_nao_bate_no_dia_seguinte_ao_parto_real(self, client):
        c, engine = client
        self._seed(engine, dias_desde_o_parto=1)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "pre_parto": True})
        assert r.json()["animais"] == []

    def test_faixa_dias_para_parto_nao_bate_apos_parto_real(self, client):
        c, engine = client
        self._seed(engine, dias_desde_o_parto=1)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "dias_para_parto_min": 0, "dias_para_parto_max": 10})
        assert r.json()["animais"] == []

    def test_sem_parto_o_pre_parto_continua_batendo_normalmente(self, client):
        c, engine = client
        hoje = date.today()
        from fazenda.rules.gestation import dias_gestacao
        gestacao = round(dias_gestacao(None))
        with Session(engine) as s:
            s.add(Animal(numero="3335", categoria_completa="Vaca em lactação", categoria_abrev="Vaca",
                         sit_rep="Ges.", diagnostico="POSITIVO", data_nasc=hoje - timedelta(days=1500), ativo=True))
            s.commit()
            s.add(Servico(numero_matriz="3335", data_servico=hoje - timedelta(days=gestacao - 2), diagnostico="POSITIVO"))
            s.commit()
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "pre_parto": True})
        assert r.json()["animais"] == ["3335"]


class TestCamposGeradoresVsRestritivos(object):
    """Só os campos "geradores" (faixas numéricas, situação produtiva/reprodutiva)
    fazem um lote entrar na sugestão automática (`GET /movimentacoes/sugestoes`).
    Campos "restritivos" (categoria, pré-parto, em tratamento, novilhas
    inseminadas/gestantes, categoria de manejo) continuam filtrando quando
    combinados com um gerador, mas sozinhos não geram sugestão nenhuma —
    evita sugerir o rebanho inteiro pra um lote que só tem "categoria: vaca"."""

    def _seed_vaca_fora_do_lote(self, engine):
        with Session(engine) as s:
            s.add(Animal(numero="900", categoria_completa="Vaca em lactação", categoria_abrev="Vaca",
                         del_dias=50, ult_cl_kg=25, sexo="F", grupo_primario="01 - Recém-chegadas", ativo=True))
            s.commit()

    def test_lote_so_com_categoria_nao_gera_sugestao(self, client):
        c, engine = client
        self._seed_vaca_fora_do_lote(engine)
        with Session(engine) as s:
            s.add(Lote(codigo="02", nome="Vacas", categorias="vaca"))
            s.commit()
        r = c.get("/movimentacoes/sugestoes")
        assert r.json()["sugestoes"] == []
        assert r.json()["lotes_com_criterio"] == 0

    def test_lote_so_com_flags_restritivas_nao_gera_sugestao(self, client):
        c, engine = client
        self._seed_vaca_fora_do_lote(engine)
        with Session(engine) as s:
            s.add(Lote(codigo="02", nome="Em tratamento", em_tratamento=True))
            s.commit()
        r = c.get("/movimentacoes/sugestoes")
        assert r.json()["sugestoes"] == []
        assert r.json()["lotes_com_criterio"] == 0

    def test_lote_so_com_categoria_manejo_nao_gera_sugestao(self, client):
        c, engine = client
        self._seed_vaca_fora_do_lote(engine)
        with Session(engine) as s:
            s.add(Lote(codigo="02", nome="Vinculado", categoria_manejo_ids="1"))
            s.commit()
        r = c.get("/movimentacoes/sugestoes")
        assert r.json()["sugestoes"] == []
        assert r.json()["lotes_com_criterio"] == 0

    def test_lote_com_gerador_gera_sugestao(self, client):
        c, engine = client
        self._seed_vaca_fora_do_lote(engine)
        with Session(engine) as s:
            s.add(Lote(codigo="02", nome="DEL alto", del_min=30))
            s.commit()
        r = c.get("/movimentacoes/sugestoes")
        assert r.json()["lotes_com_criterio"] == 1
        assert len(r.json()["sugestoes"]) == 1
        assert r.json()["sugestoes"][0]["numero_matriz"] == "900"

    def test_gerador_combinado_com_restritivo_continua_filtrando(self, client):
        c, engine = client
        self._seed_vaca_fora_do_lote(engine)
        with Session(engine) as s:
            # gera sugestão (del_min) mas exige categoria "novilha" — a vaca
            # semeada não atende, então não deve gerar sugestão nenhuma.
            s.add(Lote(codigo="02", nome="DEL alto novilhas", del_min=30, categorias="novilha"))
            s.commit()
        r = c.get("/movimentacoes/sugestoes")
        assert r.json()["lotes_com_criterio"] == 1
        assert r.json()["sugestoes"] == []

    def test_motivo_nao_menciona_campo_restritivo(self, client):
        c, engine = client
        self._seed_vaca_fora_do_lote(engine)
        with Session(engine) as s:
            s.add(Lote(codigo="02", nome="DEL alto vacas", del_min=30, categorias="vaca"))
            s.commit()
        r = c.get("/movimentacoes/sugestoes")
        motivo = r.json()["sugestoes"][0]["motivo"]
        assert "Dias pós-parto" in motivo
        assert "Categoria" not in motivo


class TestSituacaoReprodutivaAoVivo:
    """`lote.situacao_reprodutiva` (prenha/inseminada/vazia) seguia o
    `sit_rep` congelado do último GERAL.csv — corrigido para ler o estado
    reprodutivo AO VIVO (estado_reprodutivo.classificar_animal, dentro de
    recria._contexto_categoria), a mesma fonte usada nas listas de Rebanho,
    na Agenda e nos relatórios gerenciais."""

    def test_engravidou_pelo_app_csv_ainda_diz_vazia(self, client):
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            # sit_rep congelado ainda diz "vazia" (o CSV não foi reimportado
            # desde a inseminação), mas o serviço lançado pelo próprio app
            # já confirma a prenhez.
            s.add(Animal(numero="10", categoria_completa="Vaca", categoria_abrev="Vaca",
                         sit_rep="Vaz. atr.", data_nasc=hoje - timedelta(days=1800), ativo=True))
            s.add(Parto(numero_matriz="10", data_parto=hoje - timedelta(days=300)))
            s.add(Servico(numero_matriz="10", data_servico=hoje - timedelta(days=60), diagnostico="POSITIVO"))
            s.commit()
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "situacao_reprodutiva": "prenha"})
        assert r.json()["animais"] == ["10"]
        # E ela NÃO deve mais casar com "vazia" (o critério antigo, lendo
        # sit_rep, casaria — era exatamente esse o furo).
        r2 = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "situacao_reprodutiva": "vazia"})
        assert r2.json()["animais"] == []

    def test_pariu_pelo_app_csv_ainda_diz_gestante(self, client):
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            # sit_rep congelado ainda diz "Ges." — mas ela já pariu, e o
            # parto já passou do PEV padrão (45 dias): está livre pra novo
            # serviço, "vazia" ao vivo, não mais "prenha".
            s.add(Animal(numero="11", categoria_completa="Vaca", categoria_abrev="Vaca",
                         sit_rep="Ges.", data_nasc=hoje - timedelta(days=1800), ativo=True))
            s.add(Servico(numero_matriz="11", data_servico=hoje - timedelta(days=340), diagnostico="POSITIVO"))
            s.add(Parto(numero_matriz="11", data_parto=hoje - timedelta(days=60)))
            s.commit()
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "situacao_reprodutiva": "vazia"})
        assert r.json()["animais"] == ["11"]
        r2 = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "situacao_reprodutiva": "prenha"})
        assert r2.json()["animais"] == []
