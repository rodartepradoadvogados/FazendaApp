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
    Animal, BaixaAnimal, CalendarioSanitario, CentroCusto, CompraAnimal, ContaCorrente, ContratoFazenda,
    ContratoFazendaModulo, Doenca, EventoSanitario, Fazenda, MedicamentoComercial, MetodoServicoReprodutivo,
    MovimentoLote, OcorrenciaClinica, Pessoa, PrincipioAtivo, TipoServicoReprodutivo, UsuarioFazenda,
    VendaAnimal,
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
        # NOME PROPOSITALMENTE INVENTADO: o catálogo global da CowData
        # (rules/farmacia_seed.py) semeia princípios reais — "Meloxicam" entre
        # eles — com fazenda_id nulo, e linha global é visível a TODA fazenda
        # por definição (ver rules/visibilidade.py). Usando um nome real, o
        # teste passava ou falhava conforme a semeadura tivesse rodado antes,
        # e o que ele reprovava era o catálogo global funcionando, não um
        # vazamento. Com um nome que só pode existir aqui, a asserção volta a
        # medir o que interessa: a linha DA FAZENDA 1 não aparece para a 2.
        pa = PrincipioAtivo(nome="Zzmeloxitest-F1", fazenda_id=1)
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

    def test_sessao_sem_fazenda_e_recusada(self, client):
        """A auditoria encontrou este teste afirmando o próprio furo — o
        docstring antigo dizia, com todas as letras, "sem filtro nenhum".

        Era a regra do piloto de multi-fazenda: com uma fazenda só, "token
        sem fid" queria dizer "emitido antes da migração", e não havia
        retroatividade. Com mais de um cliente no mesmo banco, "sem filtro
        nenhum" deixou de ser compatibilidade e virou vazamento entre
        clientes (F-A-01/F-B-01/F-B-02).

        Agora a regra é a oposta e vale na porta: ou o token diz em qual
        fazenda a requisição acontece, ou ela não entra (fazenda/auth.py::
        exigir_fazenda_selecionada)."""
        c, engine = client
        _como_fazenda(None)
        r = c.get("/financeiro/contas-correntes")
        assert r.status_code == 409, (
            f"as contas correntes das duas fazendas saíram juntas para uma sessão sem fazenda "
            f"selecionada: {r.status_code} {r.text[:200]}"
        )

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
        assert "Zzmeloxitest-F1" not in nomes
        _como_fazenda(1)
        r = c.get("/farmacia/principios")
        nomes = {item["nome"] for item in r.json()}
        assert "Zzmeloxitest-F1" in nomes

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

    def test_ficha_animal_nao_mistura_historico_de_numero_colidente(self, client):
        """FURO DE MULTI-TENANT CORRIGIDO: `animal.numero` deixou de ser
        único no banco inteiro (migração c24befa94c1b — unicidade composta
        (fazenda_id, numero), feita para permitir a Fazenda Teste replicar
        uma fazenda real com os MESMOS números) — duas fazendas podem ter
        cada uma um animal "9500". A ficha de UM deles não pode mostrar
        MovimentoLote/BaixaAnimal/CompraAnimal/VendaAnimal/OcorrenciaClinica
        do OUTRO (essas 5 tabelas já têm fazenda_id, mas a ficha não
        filtrava por ele antes desta correção)."""
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="9500", sexo="F", ativo=True, fazenda_id=1, nome="Fazenda 1"))
            s.add(Animal(numero="9500", sexo="F", ativo=True, fazenda_id=2, nome="Fazenda 2"))
            s.add(MovimentoLote(
                numero_matriz="9500", data_movimento=date(2026, 1, 1),
                lote_origem="01", lote_destino="02", fazenda_id=1,
            ))
            s.add(BaixaAnimal(numero_animal="9500", data_baixa=date(2026, 1, 1), tipo_baixa="morte", motivo="morte", fazenda_id=1))
            s.add(CompraAnimal(
                numero_animal="9500", vendedor="Fulano", valor=1000.0, tipo_valor="por_animal",
                data_compra=date(2026, 1, 1), fazenda_id=1,
            ))
            s.add(VendaAnimal(
                numero_animal="9500", comprador="Beltrano", valor=2000.0, tipo_valor="por_animal",
                data_venda=date(2026, 1, 1), fazenda_id=1,
            ))
            s.add(OcorrenciaClinica(numero_matriz="9500", doenca="Diarreia", data_ocorrencia=date(2026, 1, 1), fazenda_id=1))
            s.commit()

        _como_fazenda(2)
        r = c.get("/animais/9500/ficha")
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["movimentos_lote"] == []
        assert corpo["baixa"] is None
        assert corpo["compras"] == []
        assert corpo["vendas"] == []
        assert corpo["ocorrencias_clinicas"] == []


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
