"""
Formulação de Dietas — endpoints HTTP: controle de acesso (só dono-equivalente
e Consultor CowData vinculado a esta fazenda passam — ver backlog #127;
admin comum, contratante da fazenda, consultor EXTERNO, operador comum e
contador não passam), isolamento entre fazendas, CRUD de simulações,
`/calcular` stateless, e `aplicar` gerando um DietaLancamento real (com
`dieta_simulacao_id` de volta) a partir do resultado do motor.
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
    Alimento, Animal, ContratoFazenda, ContratoFazendaModulo, ControleLeiteiro, DietaLancamento, Fazenda, Lote, Pessoa, Usuario,
    UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS

DIETA_MINIMA = {
    "animal": {
        "estado_fisiologico": "vaca_lactante", "raca": "Holandes", "peso_vivo_kg": 650.0, "peso_maturo_kg": 680.0,
        "ecc": 3.0, "paridade": 2.0, "del_dias": 150, "eq_cms": 8,
        "producao_leite_kg_dia": 35.0, "gordura_leite_pct": 3.8, "proteina_leite_pct": 3.2,
    },
    "itens": [
        {"nome": "Silagem de milho", "categoria_nasem": "Forragem", "conc_pct": 0.0, "proporcao_ms_pct": 60.0, "origem": "manual"},
        {"nome": "Farelo de soja", "categoria_nasem": "Concentrado proteico", "conc_pct": 100.0, "proporcao_ms_pct": 40.0, "origem": "manual"},
    ],
}


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(Fazenda(id=2, nome="Fazenda 2"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.add(Lote(codigo="01", nome="Lactação Alta", fazenda_id=1))
        s.add(Animal(numero="A1", sexo="F", ativo=True, grupo_primario="01 - Lactação Alta", fazenda_id=1))
        s.add(Animal(numero="A2", sexo="F", ativo=True, grupo_primario="01 - Lactação Alta", fazenda_id=1))
        s.add(Alimento(nome="Silagem de milho", fazenda_id=1))
        s.add(Alimento(nome="Farelo de soja", fazenda_id=1))

        # Fazenda lógica da CowData + o membro da Equipe com cargo Consultor
        # — é isso que faz o usuário 13 ser um CONSULTOR COWDATA (e não um
        # consultor externo convidado pelo cliente, que é o usuário 16).
        s.add(Fazenda(id=99, nome="CowData (empresa)", eh_empresa_cowdata=True))
        s.commit()
        s.add(Pessoa(id=990, nome="Consultor CowData", tipo="Consultor", fazenda_id=99, ativo=True))
        # Segundo Consultor CowData, de propósito SEM vínculo com a fazenda 1 —
        # prova que ser da Equipe não basta, precisa do vínculo na fazenda.
        s.add(Pessoa(id=991, nome="Consultor CowData 2", tipo="Consultor", fazenda_id=99, ativo=True))
        s.commit()

        s.add(Usuario(id=10, username="dono", nome="Dono", senha_hash="x", papel="admin", email="jairodarte@gmail.com"))
        s.add(Usuario(id=11, username="admin1", nome="Admin", senha_hash="x", papel="admin", email="admin1@example.com"))
        s.add(Usuario(id=12, username="contratante1", nome="Contratante", senha_hash="x", papel="operador", email="contratante@example.com"))
        s.add(Usuario(id=13, username="consultor1", nome="Consultor CowData", senha_hash="x", papel="operador", email="consultor@example.com", pessoa_id=990))
        s.add(Usuario(id=14, username="operador1", nome="Operador", senha_hash="x", papel="operador", email="operador@example.com", permissoes="alimentacao"))
        s.add(Usuario(id=15, username="contador1", nome="Contador", senha_hash="x", papel="operador", email="contador@example.com"))
        s.add(Usuario(id=16, username="vet_externo", nome="Vet externo", senha_hash="x", papel="operador", email="vet@example.com"))
        s.add(Usuario(id=17, username="consultor2", nome="Consultor CowData 2", senha_hash="x", papel="operador", email="consultor2@example.com", pessoa_id=991))
        s.commit()
        s.add(UsuarioFazenda(usuario_id=12, fazenda_id=1, contratante=True))
        # O mesmo Consultor CowData atende as duas fazendas — é assim que o
        # teste de isolamento prova separação de DADOS (e não de acesso).
        s.add(UsuarioFazenda(usuario_id=13, fazenda_id=1, consultor=True))
        s.add(UsuarioFazenda(usuario_id=13, fazenda_id=2, consultor=True))
        s.add(UsuarioFazenda(usuario_id=15, fazenda_id=1, contador=True))
        s.add(UsuarioFazenda(usuario_id=16, fazenda_id=1, consultor=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como(usuario_id: int | None):
    import main
    from fazenda.auth import get_current_user

    if usuario_id is None:
        main.app.dependency_overrides.pop(get_current_user, None)
        return

    with Session(main.engine) as s:
        user = s.get(Usuario, usuario_id)
    main.app.dependency_overrides[get_current_user] = lambda: user


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestControleDeAcesso:
    # 10 = dono-equivalente; 13 = Consultor CowData vinculado a esta fazenda.
    @pytest.mark.parametrize("usuario_id", [10, 13])
    def test_passam(self, client, usuario_id):
        c, _ = client
        _como(usuario_id)
        r = c.get("/formulacao/simulacoes")
        assert r.status_code == 200

    # Backlog #127: quem passava antes e não passa mais — a Formulação de
    # Dietas é serviço prestado pela CowData, não autoatendimento do cliente.
    def test_admin_comum_nao_passa_mais(self, client):
        c, _ = client
        _como(11)
        assert c.get("/formulacao/simulacoes").status_code == 403

    def test_contratante_da_fazenda_nao_passa_mais(self, client):
        c, _ = client
        _como(12)
        assert c.get("/formulacao/simulacoes").status_code == 403

    def test_consultor_externo_do_cliente_nao_passa(self, client):
        """Vínculo `consultor` sozinho não basta: o veterinário convidado pelo
        próprio cliente não é Consultor CowData (não é Pessoa da Equipe)."""
        c, _ = client
        _como(16)
        assert c.get("/formulacao/simulacoes").status_code == 403

    def test_consultor_cowdata_sem_vinculo_nesta_fazenda_nao_passa(self, client):
        """Ser Consultor CowData não dá acesso a qualquer fazenda — só àquelas
        em que ele está vinculado (o 17 não está vinculado a nenhuma)."""
        c, _ = client
        _como(17)
        assert c.get("/formulacao/simulacoes").status_code == 403

    def test_operador_comum_nao_passa(self, client):
        c, _ = client
        _como(14)
        r = c.get("/formulacao/simulacoes")
        assert r.status_code == 403

    def test_contador_nao_passa(self, client):
        c, _ = client
        _como(15)
        r = c.get("/formulacao/simulacoes")
        assert r.status_code == 403

    def test_sem_token_nao_passa(self, client):
        c, _ = client
        _como(None)
        r = c.get("/formulacao/simulacoes")
        assert r.status_code == 401

    def test_sem_fazenda_selecionada_403(self, client):
        c, _ = client
        _como(13)
        _como_fazenda(None)
        r = c.get("/formulacao/simulacoes")
        assert r.status_code == 403


class TestCalcularStateless:
    def test_calcular_nao_grava_nada(self, client):
        c, engine = client
        _como(13)
        r = c.post("/formulacao/calcular", json=DIETA_MINIMA)
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["consumo"]["cms_kg_dia"] > 0
        assert any(linha["nutriente"].startswith("ELl") for linha in corpo["balanco"])
        with Session(engine) as s:
            from fazenda.models import DietaSimulacao
            assert s.exec(select(DietaSimulacao)).all() == []


class TestCrudSimulacao:
    def test_criar_listar_obter_salvar(self, client):
        c, _ = client
        _como(13)
        r = c.post("/formulacao/simulacoes", json={"nome": "Lote 01 - agosto", "lote": 1})
        assert r.status_code == 201, r.text
        sim_id = r.json()["id"]
        assert r.json()["status"] == "rascunho"

        r = c.get("/formulacao/simulacoes")
        assert any(s["id"] == sim_id for s in r.json())

        r = c.put(f"/formulacao/simulacoes/{sim_id}", json={**DIETA_MINIMA, "etapa_atual": 4})
        assert r.status_code == 200, r.text
        assert r.json()["cabecalho"]["status"] == "concluida"
        assert len(r.json()["itens"]) == 2
        assert r.json()["resultado"]["consumo"]["cms_kg_dia"] > 0

        r = c.get(f"/formulacao/simulacoes/{sim_id}")
        assert r.status_code == 200
        assert r.json()["resultado"] is not None

    def test_duplicar(self, client):
        c, _ = client
        _como(13)
        sim_id = c.post("/formulacao/simulacoes", json={"nome": "Original", "lote": 1}).json()["id"]
        c.put(f"/formulacao/simulacoes/{sim_id}", json=DIETA_MINIMA)
        r = c.post(f"/formulacao/simulacoes/{sim_id}/duplicar", json={"nome": "Cópia"})
        assert r.status_code == 201, r.text
        assert len(r.json()["itens"]) == 2
        assert r.json()["cabecalho"]["status"] == "rascunho"

    def test_excluir(self, client):
        c, _ = client
        _como(13)
        sim_id = c.post("/formulacao/simulacoes", json={"nome": "Descartável"}).json()["id"]
        r = c.delete(f"/formulacao/simulacoes/{sim_id}")
        assert r.status_code == 200
        assert c.get(f"/formulacao/simulacoes/{sim_id}").status_code == 404


class TestIsolamentoEntreFazendas:
    def test_simulacao_da_fazenda_1_invisivel_na_2(self, client):
        c, _ = client
        _como(13)
        sim_id = c.post("/formulacao/simulacoes", json={"nome": "Só da 1"}).json()["id"]

        _como_fazenda(2)
        assert all(s["id"] != sim_id for s in c.get("/formulacao/simulacoes").json())
        assert c.get(f"/formulacao/simulacoes/{sim_id}").status_code == 404
        assert c.put(f"/formulacao/simulacoes/{sim_id}", json=DIETA_MINIMA).status_code == 404
        assert c.delete(f"/formulacao/simulacoes/{sim_id}").status_code == 404


class TestContextoLote:
    """GET /formulacao/contexto/{lote} — pré-preenchimento da Etapa 2.

    `dias_gestacao` precisa vir estimado do rebanho pelo mesmo motivo que
    `del_dias`/`producao_leite_kg_dia` já vêm: sem isso, um lote de vaca seca
    nunca consegue calcular a estimativa de CMS (eq_cms 10/11 exige
    `dias_gestacao` — ver `fazenda.rules.nutricao.tipos.validar_entrada`),
    porque nada preenche o campo sozinho e a Etapa 3 fica presa mostrando só
    o campo de digitação manual, nunca as duas estimativas lado a lado."""

    def test_dias_gestacao_estimado_de_servico_vigente_do_lote(self, client):
        c, engine = client
        from fazenda.models import Lote, Servico

        with Session(engine) as s:
            s.add(Lote(codigo="02", nome="Vacas secas", fazenda_id=1))
            s.add(Animal(numero="S1", sexo="F", ativo=True, grupo_primario="02 - Vacas secas", fazenda_id=1))
            s.add(Animal(numero="S2", sexo="F", ativo=True, grupo_primario="02 - Vacas secas", fazenda_id=1))
            # S1: 60 dias de gestação; S2: 40 — média esperada 50.
            s.add(Servico(
                numero_matriz="S1", data_servico=date.today() - timedelta(days=60),
                diagnostico="POSITIVO", fazenda_id=1,
            ))
            s.add(Servico(
                numero_matriz="S2", data_servico=date.today() - timedelta(days=40),
                diagnostico="POSITIVO", fazenda_id=1,
            ))
            # Serviço de outro lote/fazenda não deve entrar na média.
            s.add(Servico(
                numero_matriz="A1", data_servico=date.today() - timedelta(days=200),
                diagnostico="POSITIVO", fazenda_id=1,
            ))
            s.commit()

        _como(13)
        r = c.get("/formulacao/contexto/2")
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["dias_gestacao"] == 50
        assert "dias_gestacao" in corpo["campos_estimados"]

    def test_sem_servico_vigente_dias_gestacao_fica_nulo(self, client):
        c, _ = client
        _como(13)
        r = c.get("/formulacao/contexto/1")
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["dias_gestacao"] is None
        assert "dias_gestacao" not in corpo["campos_estimados"]

    def test_producao_estimada_vem_do_controle_leiteiro_ao_vivo(self, client):
        """Mesmo bug/fix de Alimentação > Nova dieta (ver
        test_alimentacao.py): Animal.ult_cl_kg sozinho fica congelado na
        data do último CSV importado — precisa refletir o controle leiteiro
        mais recente de verdade, lançado pelo próprio app."""
        c, engine = client
        with Session(engine) as s:
            s.add(Lote(codigo="03", nome="Lactação", fazenda_id=1))
            s.add(Animal(numero="L1", sexo="F", ativo=True, grupo_primario="03 - Lactação",
                          fazenda_id=1, ult_cl_kg=20.0, data_ult_leite=date(2026, 7, 8)))
            s.add(Animal(numero="L2", sexo="F", ativo=True, grupo_primario="03 - Lactação",
                          fazenda_id=1, ult_cl_kg=18.0, data_ult_leite=date(2026, 7, 8)))
            # Controle leiteiro lançado pelo app, bem mais recente.
            s.add(ControleLeiteiro(numero_matriz="L1", data_controle=date(2026, 8, 13), producao_kg=36.0, fazenda_id=1))
            s.add(ControleLeiteiro(numero_matriz="L2", data_controle=date(2026, 8, 13), producao_kg=28.0, fazenda_id=1))
            s.commit()

        _como(13)
        r = c.get("/formulacao/contexto/3")
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["producao_leite_kg_dia"] == 32.0  # (36+28)/2, não (20+18)/2


class TestAplicarNaDieta:
    def test_aplicar_cria_lancamento_com_vinculo(self, client):
        c, engine = client
        _como(13)
        sim_id = c.post("/formulacao/simulacoes", json={"nome": "Para aplicar", "lote": 1}).json()["id"]
        c.put(f"/formulacao/simulacoes/{sim_id}", json=DIETA_MINIMA)

        r = c.post(f"/formulacao/simulacoes/{sim_id}/aplicar", json={
            "lote": 1, "data_abertura": "2026-08-08", "base_quantidade": "total",
        })
        assert r.status_code == 201, r.text
        dieta_id = r.json()["dieta_lancamento_id"]
        assert r.json()["itens_criados"] == 2
        assert r.json()["qtd_animais"] == 2

        with Session(engine) as s:
            dieta = s.get(DietaLancamento, dieta_id)
            assert dieta.dieta_simulacao_id == sim_id
            assert dieta.lote == 1

        r = c.get(f"/formulacao/simulacoes/{sim_id}")
        assert r.json()["cabecalho"]["status"] == "aplicada"
        assert r.json()["cabecalho"]["dieta_lancamento_id"] == dieta_id

    def test_aplicar_com_dieta_ativa_sem_encerrar_409(self, client):
        c, _ = client
        _como(13)
        sim1 = c.post("/formulacao/simulacoes", json={"nome": "Primeira", "lote": 1}).json()["id"]
        c.put(f"/formulacao/simulacoes/{sim1}", json=DIETA_MINIMA)
        c.post(f"/formulacao/simulacoes/{sim1}/aplicar", json={"lote": 1, "data_abertura": "2026-08-01"})

        sim2 = c.post("/formulacao/simulacoes", json={"nome": "Segunda", "lote": 1}).json()["id"]
        c.put(f"/formulacao/simulacoes/{sim2}", json=DIETA_MINIMA)
        r = c.post(f"/formulacao/simulacoes/{sim2}/aplicar", json={"lote": 1, "data_abertura": "2026-08-08"})
        assert r.status_code == 409

        r = c.post(f"/formulacao/simulacoes/{sim2}/aplicar", json={
            "lote": 1, "data_abertura": "2026-08-08", "encerrar_anterior": True,
        })
        assert r.status_code == 201, r.text

    def test_excluir_simulacao_aplicada_409(self, client):
        c, _ = client
        _como(13)
        sim_id = c.post("/formulacao/simulacoes", json={"nome": "Aplicada", "lote": 1}).json()["id"]
        c.put(f"/formulacao/simulacoes/{sim_id}", json=DIETA_MINIMA)
        c.post(f"/formulacao/simulacoes/{sim_id}/aplicar", json={"lote": 1, "data_abertura": "2026-08-08"})
        assert c.delete(f"/formulacao/simulacoes/{sim_id}").status_code == 409
        assert c.put(f"/formulacao/simulacoes/{sim_id}", json=DIETA_MINIMA).status_code == 409


class TestBibliotecaDeAlimentos:
    def test_listar_alimentos_marca_sem_composicao(self, client):
        c, _ = client
        _como(13)
        r = c.get("/formulacao/alimentos")
        assert r.status_code == 200
        nomes = {a["nome"]: a["sem_composicao"] for a in r.json()["cadastrados"]}
        assert nomes.get("Silagem de milho") is True

    def test_resolver_sem_biblioteca_nem_laudo_cai_no_template(self, client):
        c, engine = client
        _como(13)
        with Session(engine) as s:
            alimento_id = s.exec(select(Alimento).where(Alimento.nome == "Silagem de milho")).first().id
        r = c.get(f"/formulacao/alimentos/{alimento_id}/resolver")
        assert r.status_code == 200
        assert r.json()["origem"] == "template"
        assert r.json()["valores"]["fdn_pct"] is not None

    def test_templates_e_biblioteca_semente(self, client):
        c, _ = client
        _como(13)
        r = c.get("/formulacao/templates")
        assert r.status_code == 200
        assert len(r.json()["categorias"]) == 11
        assert len(r.json()["biblioteca_semente"]) == 12


class TestBibliotecaMestreCowData:
    """Biblioteca mestre CowData (fazenda_id=None) + cópia por fazenda
    (copy-on-write) — ver fazenda.rules.biblioteca_alimentos e docstring de
    AlimentoNutricional em fazenda/models/formulacao.py."""

    def _por_nome(self, c, nome: str) -> dict | None:
        r = c.get("/formulacao/alimentos")
        assert r.status_code == 200
        return next((a for a in r.json()["biblioteca"] if a["nome"] == nome), None)

    def test_mestre_aparece_para_qualquer_fazenda_recem_semeada(self, client):
        c, _ = client
        _como(13)
        _como_fazenda(1)
        item1 = self._por_nome(c, "Milho moído")
        _como_fazenda(2)
        item2 = self._por_nome(c, "Milho moído")
        assert item1 is not None and item2 is not None
        assert item1["eh_mestre"] is True and item2["eh_mestre"] is True
        assert item1["valores"]["pb_pct"] == item2["valores"]["pb_pct"] == 9.5

    def test_editar_item_mestre_nao_afeta_outra_fazenda(self, client):
        c, _ = client
        _como(13)
        _como_fazenda(1)
        mestre = self._por_nome(c, "Milho moído")
        payload = {
            "alimento_id": None, "nome": mestre["nome"], "categoria_nasem": mestre["categoria_nasem"],
            "conc_pct": mestre["conc_pct"], "fonte": mestre["fonte"], "observacao": None,
            "inclusao_min_pct": None, "inclusao_max_pct": None, "valores": {**mestre["valores"], "pb_pct": 99.0},
        }
        r = c.put(f"/formulacao/alimentos/{mestre['id']}", json=payload)
        assert r.status_code == 200
        copia = r.json()
        assert copia["id"] != mestre["id"]
        assert copia["eh_mestre"] is False and copia["eh_copia_editada"] is True
        assert copia["valores"]["pb_pct"] == 99.0

        # A fazenda 1 agora enxerga a CÓPIA (editada); a mestre original some
        # da listagem dela (foi sobrescrita).
        item1 = self._por_nome(c, "Milho moído")
        assert item1["id"] == copia["id"]
        assert item1["valores"]["pb_pct"] == 99.0

        # A fazenda 2 nunca editou nada — continua vendo a mestre intocada.
        _como_fazenda(2)
        item2 = self._por_nome(c, "Milho moído")
        assert item2["eh_mestre"] is True
        assert item2["valores"]["pb_pct"] == 9.5

    def test_excluir_copia_editada_restaura_padrao_cowdata(self, client):
        c, _ = client
        _como(13)
        _como_fazenda(1)
        mestre = self._por_nome(c, "Farelo de soja")
        payload = {
            "alimento_id": None, "nome": mestre["nome"], "categoria_nasem": mestre["categoria_nasem"],
            "conc_pct": mestre["conc_pct"], "fonte": mestre["fonte"], "observacao": None,
            "inclusao_min_pct": None, "inclusao_max_pct": None, "valores": {**mestre["valores"], "pb_pct": 50.0},
        }
        copia = c.put(f"/formulacao/alimentos/{mestre['id']}", json=payload).json()
        assert self._por_nome(c, "Farelo de soja")["valores"]["pb_pct"] == 50.0

        r = c.delete(f"/formulacao/alimentos/{copia['id']}")
        assert r.status_code == 200
        assert r.json()["acao"] == "restaurado"

        restaurado = self._por_nome(c, "Farelo de soja")
        assert restaurado["eh_mestre"] is True
        assert restaurado["valores"]["pb_pct"] == 48.0  # valor original da mestre, nunca alterado

    def test_excluir_item_mestre_nunca_editado_oculta_so_para_esta_fazenda(self, client):
        c, _ = client
        _como(13)
        _como_fazenda(1)
        mestre = self._por_nome(c, "Ureia pecuária")
        r = c.delete(f"/formulacao/alimentos/{mestre['id']}")
        assert r.status_code == 200
        assert r.json()["acao"] == "oculto"
        assert self._por_nome(c, "Ureia pecuária") is None  # sumiu só da fazenda 1

        _como_fazenda(2)
        assert self._por_nome(c, "Ureia pecuária") is not None  # continua na fazenda 2

    def test_excluir_item_proprio_da_fazenda_remove_de_vez(self, client):
        c, _ = client
        _como(13)
        _como_fazenda(1)
        criado = c.post("/formulacao/alimentos", json={
            "alimento_id": None, "nome": "Alimento exclusivo da fazenda 1", "categoria_nasem": "Outros",
            "conc_pct": 0.0, "fonte": None, "observacao": None, "valores": {},
        }).json()
        assert criado["eh_mestre"] is False and criado["eh_copia_editada"] is False

        r = c.delete(f"/formulacao/alimentos/{criado['id']}")
        assert r.status_code == 200
        assert r.json()["acao"] == "excluido"
        assert self._por_nome(c, "Alimento exclusivo da fazenda 1") is None

    def test_item_proprio_de_uma_fazenda_invisivel_na_outra(self, client):
        c, _ = client
        _como(13)
        _como_fazenda(1)
        c.post("/formulacao/alimentos", json={
            "alimento_id": None, "nome": "Só da fazenda 1", "categoria_nasem": "Outros",
            "conc_pct": 0.0, "fonte": None, "observacao": None, "valores": {},
        })
        _como_fazenda(2)
        assert self._por_nome(c, "Só da fazenda 1") is None

    def test_baixar_modelo_planilha(self, client):
        c, _ = client
        _como(13)
        r = c.get("/formulacao/alimentos/modelo")
        assert r.status_code == 200
        assert "spreadsheetml" in r.headers["content-type"]
        assert "biblioteca_alimentos_modelo" in r.headers["content-disposition"]

    def test_importar_planilha_csv(self, client):
        c, _ = client
        _como(13)
        _como_fazenda(1)
        csv_conteudo = (
            "Nome do alimento,Categoria NASEM,MS - matéria seca (% da matéria NATURAL),PB - proteína bruta (% da MS)\n"
            "Silagem de capivara,Forragem,30,10\n"
            "Milho moído,Concentrado energetico,90,999\n"  # PB fora de faixa (>300) -> ignorado, vira aviso
            ",Outros,50,10\n"  # sem nome -> erro
        ).encode("utf-8")
        r = c.post(
            "/formulacao/alimentos/importar",
            files={"file": ("alimentos.csv", csv_conteudo, "text/csv")},
        )
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["criados"] == 1  # Silagem de capivara
        assert corpo["atualizados"] == 1  # Milho moído -> copy-on-write da mestre
        assert len(corpo["erros"]) == 1
        assert any("fora da faixa" in a for a in corpo["avisos"])

        nova = self._por_nome(c, "Silagem de capivara")
        assert nova is not None and nova["valores"]["ms_pct"] == 30.0

        milho = self._por_nome(c, "Milho moído")
        assert milho["eh_copia_editada"] is True
        assert milho["valores"]["pb_pct"] == 9.5  # valor fora de faixa foi ignorado, manteve o da mestre


class TestExigenciaEditadaEtapa4:
    """Coluna "Exigência" do balanço ao vivo (Etapa 4) — puxa da Etapa 3 e é
    editável, mesma convenção cinza/preto do resto do wizard (ver
    PainelBalanco.tsx e docstring de DietaSimulacao.exigencias_editadas_json)."""

    _NUTRIENTE = "ELl (energia líquida de lactação)"

    def test_calcular_sem_override_usa_exigencia_do_motor(self, client):
        c, _ = client
        _como(13)
        r = c.post("/formulacao/calcular", json=DIETA_MINIMA)
        assert r.status_code == 200
        linha = next(l for l in r.json()["balanco"] if l["nutriente"] == self._NUTRIENTE)
        assert linha["exigencia"] > 0

    def test_calcular_com_override_recalcula_balanco_e_situacao(self, client):
        c, _ = client
        _como(13)
        base = c.post("/formulacao/calcular", json=DIETA_MINIMA).json()
        linha_base = next(l for l in base["balanco"] if l["nutriente"] == self._NUTRIENTE)
        fornecido = linha_base["fornecido"]
        exigencia_absurda = fornecido + 1000.0  # força déficit visível

        payload = {**DIETA_MINIMA, "exigencias_editadas": {self._NUTRIENTE: exigencia_absurda}}
        r = c.post("/formulacao/calcular", json=payload)
        assert r.status_code == 200
        linha = next(l for l in r.json()["balanco"] if l["nutriente"] == self._NUTRIENTE)
        assert linha["exigencia"] == exigencia_absurda
        assert linha["balanco"] == pytest.approx(fornecido - exigencia_absurda)
        assert linha["situacao"] == "deficit"

    def test_override_persiste_no_salvar_e_volta_no_get(self, client):
        c, _ = client
        _como(13)
        sim_id = c.post("/formulacao/simulacoes", json={"nome": "Com override"}).json()["id"]
        base = c.post("/formulacao/calcular", json=DIETA_MINIMA).json()
        fornecido = next(l for l in base["balanco"] if l["nutriente"] == self._NUTRIENTE)["fornecido"]
        override = {self._NUTRIENTE: fornecido - 1.0}  # excesso pequeno e proposital

        r = c.put(f"/formulacao/simulacoes/{sim_id}", json={**DIETA_MINIMA, "etapa_atual": 4, "exigencias_editadas": override})
        assert r.status_code == 200
        linha_salva = next(l for l in r.json()["resultado"]["balanco"] if l["nutriente"] == self._NUTRIENTE)
        assert linha_salva["exigencia"] == override[self._NUTRIENTE]

        g = c.get(f"/formulacao/simulacoes/{sim_id}")
        assert g.status_code == 200
        assert g.json()["cabecalho"]["exigencias_editadas"] == override
        linha = next(l for l in g.json()["resultado"]["balanco"] if l["nutriente"] == self._NUTRIENTE)
        assert linha["exigencia"] == override[self._NUTRIENTE]

    def test_duplicar_carrega_override_junto(self, client):
        c, _ = client
        _como(13)
        sim_id = c.post("/formulacao/simulacoes", json={"nome": "Original"}).json()["id"]
        override = {self._NUTRIENTE: 12.3}
        c.put(f"/formulacao/simulacoes/{sim_id}", json={**DIETA_MINIMA, "etapa_atual": 4, "exigencias_editadas": override})

        r = c.post(f"/formulacao/simulacoes/{sim_id}/duplicar", json={"nome": "Cópia"})
        assert r.status_code == 201
        assert r.json()["cabecalho"]["exigencias_editadas"] == override
