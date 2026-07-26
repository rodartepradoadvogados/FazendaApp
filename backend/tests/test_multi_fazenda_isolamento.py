"""
Isolamento por fazenda (piloto conservador de multi-fazenda) — garante que
ContaCorrente, CentroCusto, Pessoa e CalendarioSanitario de uma fazenda nunca
aparecem para outra, e que o provisionamento padrão de fazenda nova (Banco/
Carteira em branco + Pecuária Leiteira/Agricultura) funciona sem tocar nos
dados já existentes da fazenda #1.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

# Precisa ser setado ANTES de qualquer import de fazenda.* — vários módulos
# (main.py, push.py, portal.py, rules/parametros.py) fazem
# `from fazenda.database import engine` (bind direto, não afetado por
# monkeypatch em database.engine depois de importado) — só setar a env var
# antes do primeiro import garante que todos peguem SQLite (em vez do
# Postgres real configurado no ambiente) já na primeira vez que os módulos
# são carregados. O arquivo em si é descartável — cada teste troca por um
# banco próprio via monkeypatch (ver fixture `client` abaixo).
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, CalendarioSanitario, CentroCusto, ContaCorrente, ContratoFazenda, ContratoFazendaModulo, Doenca,
    EventoSanitario, Fazenda, MedicamentoComercial, MetodoServicoReprodutivo, Pessoa, PrincipioAtivo,
    TipoServicoReprodutivo, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    # Banco isolado por teste (arquivo novo a cada chamada) — evita que o
    # Fazenda(id=1) de um teste colida com o do próximo na mesma sessão de
    # processo (todos os módulos compartilham o MESMO objeto `engine` depois
    # de importados, então trocamos esse objeto a cada teste via monkeypatch).
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser"))
        s.add(Fazenda(id=2, nome="Fazenda Teste"))
        # Dados reais da fazenda #1 — nunca devem aparecer para a fazenda #2.
        s.add(ContaCorrente(banco="Banco do Brasil", agencia="3775-3", numero_conta="3.615-3", fazenda_id=1))
        s.add(CentroCusto(nome="Pecuária Leiteira", fazenda_id=1))
        s.add(CentroCusto(nome="Financiamento 2026", fazenda_id=1))
        s.add(Pessoa(nome="Leomir Bonfim", tipo="Funcionário", fazenda_id=1))
        ev = EventoSanitario(nome="Vermífugo", tipo="vacina", modo="epoca")
        s.add(ev)
        s.commit()
        s.refresh(ev)
        s.add(CalendarioSanitario(
            evento_sanitario_id=ev.id, fazenda_id=1, frequencia_valor=4, frequencia_unidade="meses",
            data_evento=date(2026, 1, 1),
        ))
        # Farmácia (Fase 4A) — PrincipioAtivo/MedicamentoComercial da fazenda #1.
        pa = PrincipioAtivo(nome="Meloxicam", fazenda_id=1)
        s.add(pa)
        s.commit()
        s.refresh(pa)
        s.add(MedicamentoComercial(principio_ativo_id=pa.id, nome_comercial="Maxicam 2%", fazenda_id=1))
        # Vocabulário de Serviço/Inseminação (Fase 4A) — tipo/método da fazenda #1.
        tipo = TipoServicoReprodutivo(nome="Cobertura", fazenda_id=1)
        s.add(tipo)
        s.commit()
        s.refresh(tipo)
        s.add(MetodoServicoReprodutivo(nome="Monta Natural", tipo_servico_id=tipo.id, fazenda_id=1))
        # Animal (Fase 4A) — ficha/busca por número.
        s.add(Animal(numero="9001", sexo="F", ativo=True, fazenda_id=1))
        # Contrato de planos (Fase 2A) — ortogonal ao isolamento de dados que
        # este arquivo testa; ambas as fazendas nascem com contrato ativo e
        # todos os módulos, pra nenhum teste aqui ser bloqueado pela trava de
        # módulo contratado (isso é testado à parte em test_planos_contrato.py).
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id
    # main.py faz `from fazenda.database import engine` — um bind próprio,
    # não afetado por monkeypatch em database.engine — então o lifespan
    # (que usa esse `main.engine` direto) precisa do patch aqui também.
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "outroadmin@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestIsolamentoEntreFazendas:
    def test_conta_corrente_isolada(self, client):
        c, engine = client
        _como_fazenda(2)
        r = c.get("/financeiro/contas-correntes")
        assert r.status_code == 200
        nomes = {item["banco"] for item in r.json()}
        assert "Banco do Brasil" not in nomes

    def test_centro_custo_isolado(self, client):
        c, engine = client
        _como_fazenda(2)
        r = c.get("/financeiro/centros-custo")
        assert r.status_code == 200
        nomes = {item["nome"] for item in r.json()}
        assert "Financiamento 2026" not in nomes

    def test_pessoa_isolada(self, client):
        c, engine = client
        _como_fazenda(2)
        r = c.get("/cadastro/pessoas")
        assert r.status_code == 200
        nomes = {item["nome"] for item in r.json()}
        assert "Leomir Bonfim" not in nomes

    def test_calendario_sanitario_isolado(self, client):
        c, engine = client
        _como_fazenda(2)
        r = c.get("/sanidade/calendario")
        assert r.status_code == 200
        assert r.json() == []

    def test_fazenda_1_continua_vendo_seus_dados(self, client):
        c, engine = client
        _como_fazenda(1)
        r = c.get("/financeiro/contas-correntes")
        nomes = {item["banco"] for item in r.json()}
        assert "Banco do Brasil" in nomes
        r = c.get("/cadastro/pessoas")
        assert "Leomir Bonfim" in {item["nome"] for item in r.json()}

    def test_sem_fazenda_no_token_ve_tudo_como_antes(self, client):
        """Token emitido antes do piloto (sem 'fid') — comportamento idêntico
        ao de sempre, sem filtro nenhum."""
        c, engine = client
        _como_fazenda(None)
        r = c.get("/financeiro/contas-correntes")
        assert "Banco do Brasil" in {item["banco"] for item in r.json()}

    def test_farmacia_principios_isolado(self, client):
        """Fase 4A — Farmácia (/farmacia/principios) não vazava princípios
        ativos/marcas entre fazendas (o router lia PrincipioAtivo/
        MedicamentoComercial sem filtrar, embora o modelo já tivesse
        fazenda_id desde a Fase de Sanidade)."""
        c, engine = client
        _como_fazenda(2)
        r = c.get("/farmacia/principios")
        assert r.status_code == 200
        nomes = {item["nome"] for item in r.json()}
        assert "Meloxicam" not in nomes
        _como_fazenda(1)
        r = c.get("/farmacia/principios")
        nomes = {item["nome"] for item in r.json()}
        assert "Meloxicam" in nomes

    def test_tipos_metodos_servico_isolados(self, client):
        """Fase 4A — vocabulário de Serviço/Inseminação (TipoServicoReprodutivo/
        MetodoServicoReprodutivo) não vazava entre fazendas."""
        c, engine = client
        _como_fazenda(2)
        assert "Cobertura" not in {t["nome"] for t in c.get("/cadastro/tipos-servico").json()}
        assert "Monta Natural" not in {m["nome"] for m in c.get("/cadastro/metodos-servico").json()}
        _como_fazenda(1)
        assert "Cobertura" in {t["nome"] for t in c.get("/cadastro/tipos-servico").json()}
        assert "Monta Natural" in {m["nome"] for m in c.get("/cadastro/metodos-servico").json()}

    def test_ficha_e_busca_animal_isoladas(self, client):
        """Fase 4A — GET /animais/{numero} e /animais/{numero}/ficha não
        deixavam consultar o animal de outra fazenda pelo número."""
        c, engine = client
        _como_fazenda(2)
        assert c.get("/animais/9001").status_code == 404
        assert c.get("/animais/9001/ficha").status_code == 404
        _como_fazenda(1)
        assert c.get("/animais/9001").status_code == 200
        assert c.get("/animais/9001/ficha").status_code == 200


class TestProvisionamentoFazendaNova:
    def test_criar_fazenda_provisiona_contas_e_centros_em_branco(self, client):
        c, engine = client
        from fazenda.auth import EMAIL_DONO
        import main
        main.app.dependency_overrides[main.get_current_user] = lambda: type(
            "U", (), {"id": 1, "papel": "admin", "ativo": True, "username": "dono", "email": EMAIL_DONO, "permissoes": ""},
        )()
        r = c.post("/fazendas/", json={"nome": "Fazenda Nova"})
        assert r.status_code == 200, r.text
        nova_id = r.json()["id"]

        with Session(engine) as s:
            contas = s.exec(select(ContaCorrente).where(ContaCorrente.fazenda_id == nova_id)).all()
            assert {c.banco for c in contas} == {"Banco", "Carteira"}
            assert all(c.agencia == "" and c.numero_conta == "" for c in contas)
            centros = s.exec(select(CentroCusto).where(CentroCusto.fazenda_id == nova_id)).all()
            assert {c.nome for c in centros} == {"Pecuária Leiteira", "Agricultura"}
            # Nada da fazenda #1 foi tocado.
            pessoas_novas = s.exec(select(Pessoa).where(Pessoa.fazenda_id == nova_id)).all()
            assert pessoas_novas == []
            # Fase 4A — vocabulário de Serviço/Inseminação também é semeado
            # para a fazenda nova (senão o lançamento de Serviço/Inseminação
            # nasce vazio, ver cadastro/servicos.py::seed_tipos_metodos_servico).
            tipos_novos = s.exec(select(TipoServicoReprodutivo).where(TipoServicoReprodutivo.fazenda_id == nova_id)).all()
            assert {t.nome for t in tipos_novos} == {"Cobertura", "IA"}
            metodos_novos = s.exec(select(MetodoServicoReprodutivo).where(MetodoServicoReprodutivo.fazenda_id == nova_id)).all()
            assert {m.nome for m in metodos_novos} == {"Monta Natural", "IA em cio natural", "IATF"}
