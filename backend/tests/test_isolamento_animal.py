"""
Isolamento por fazenda — Fase 4D (domínio Animal/Rebanho): garante que Animal,
Lote, MotivoBaixa, MotivoVenda, Raca, GrauSangue, MotivoMovimentacao,
CompraAnimal, VendaAnimal e BaixaAnimal de uma fazenda nunca aparecem (nem são
editáveis) para outra, apesar de todos os modelos já terem `fazenda_id`
wireado desde fases anteriores.

Arquivo autocontido (não edita test_multi_fazenda_isolamento.py — outros
agentes trabalham em paralelo em arquivos irmãos) — mesma fixture `client` e
helper `_como_fazenda`, adaptados para semear dados do domínio Animal.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

# Precisa ser setado ANTES de qualquer import de fazenda.* — ver comentário
# equivalente em test_multi_fazenda_isolamento.py.
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, BaixaAnimal, CompraAnimal, ContratoFazenda, ContratoFazendaModulo, Fazenda, GrauSangue, Lote,
    MotivoBaixa, MotivoMovimentacao, MotivoVenda, Raca, VendaAnimal,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    # Banco isolado por teste — ver comentário equivalente em
    # test_multi_fazenda_isolamento.py (mesmo motivo: `engine` é compartilhado
    # entre módulos depois de importado).
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser"))
        s.add(Fazenda(id=2, nome="Fazenda Teste"))
        # Dados reais da fazenda #1 — nunca devem aparecer para a fazenda #2.
        s.add(Animal(numero="9001", sexo="F", ativo=True, fazenda_id=1))
        s.add(Lote(codigo="01", nome="Lactação", fazenda_id=1))
        s.add(MotivoBaixa(nome="Mastite", fazenda_id=1))
        s.add(MotivoVenda(nome="Descarte", fazenda_id=1))
        s.add(Raca(nome="Girolando", fazenda_id=1))
        s.add(GrauSangue(nome="PO Holandês", fracao_holandes=1.0, fazenda_id=1))
        mot_mov = MotivoMovimentacao(nome="Crescimento", fazenda_id=1)
        s.add(mot_mov)
        s.add(CompraAnimal(
            numero_animal="9001", vendedor="Fazenda Vizinha", valor=3000.0, tipo_valor="por_animal",
            data_compra=date(2026, 1, 5), fazenda_id=1,
        ))
        s.add(VendaAnimal(
            numero_animal="9002", comprador="Frigorífico Central", valor=3500.0, tipo_valor="por_animal",
            data_venda=date(2026, 1, 10), fazenda_id=1,
        ))
        s.add(BaixaAnimal(
            numero_animal="9003", tipo_baixa="morte", motivo="doenca", motivo_doenca="Mastite",
            data_baixa=date(2026, 1, 15), fazenda_id=1,
        ))
        # Contrato de planos (Fase 2A) — ortogonal ao isolamento testado aqui;
        # ambas as fazendas nascem com contrato ativo e todos os módulos, pra
        # nenhum teste ser bloqueado pela trava de módulo contratado.
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()
        s.refresh(mot_mov)
        mot_mov_id = mot_mov.id

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
        email = "outroadmin@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine, mot_mov_id

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestIsolamentoAnimalListagens:
    """GET de listagem — fazenda #2 não deve ver nada da fazenda #1."""

    def test_animais_isolados(self, client):
        c, engine, mot_mov_id = client
        _como_fazenda(2)
        r = c.get("/animais/")
        assert r.status_code == 200
        assert r.json() == []
        _como_fazenda(1)
        r = c.get("/animais/")
        assert "9001" in {a["numero"] for a in r.json()}

    def test_lotes_isolados(self, client):
        c, engine, mot_mov_id = client
        _como_fazenda(2)
        r = c.get("/lotes/")
        assert r.status_code == 200
        assert r.json() == []
        _como_fazenda(1)
        r = c.get("/lotes/")
        assert "Lactação" in {l["nome"] for l in r.json()}

    def test_motivos_movimentacao_isolados(self, client):
        c, engine, mot_mov_id = client
        _como_fazenda(2)
        r = c.get("/movimentacoes/motivos")
        assert r.status_code == 200
        assert r.json() == []
        _como_fazenda(1)
        r = c.get("/movimentacoes/motivos")
        assert "Crescimento" in r.json()

    def test_baixas_e_motivos_isolados(self, client):
        c, engine, mot_mov_id = client
        _como_fazenda(2)
        r = c.get("/baixas/")
        assert r.status_code == 200
        assert r.json() == []
        r = c.get("/baixas/motivos")
        assert r.status_code == 200
        assert "Mastite" not in r.json()["motivos_doenca"]
        _como_fazenda(1)
        r = c.get("/baixas/")
        assert "9003" in {b["numero_animal"] for b in r.json()}
        r = c.get("/baixas/motivos")
        assert "Mastite" in r.json()["motivos_doenca"]

    def test_compras_animais_isoladas(self, client):
        c, engine, mot_mov_id = client
        _como_fazenda(2)
        r = c.get("/compras-animais/")
        assert r.status_code == 200
        assert r.json() == []
        _como_fazenda(1)
        r = c.get("/compras-animais/")
        assert "9001" in {v["numero_animal"] for v in r.json()}

    def test_vendas_animais_isoladas(self, client):
        c, engine, mot_mov_id = client
        _como_fazenda(2)
        r = c.get("/vendas-animais/")
        assert r.status_code == 200
        assert r.json() == []
        _como_fazenda(1)
        r = c.get("/vendas-animais/")
        assert "9002" in {v["numero_animal"] for v in r.json()}

    def test_graus_sangue_isolados(self, client):
        c, engine, mot_mov_id = client
        _como_fazenda(2)
        r = c.get("/cadastro/graus-sangue")
        assert r.status_code == 200
        assert "PO Holandês" not in {g["nome"] for g in r.json()}
        _como_fazenda(1)
        r = c.get("/cadastro/graus-sangue")
        assert "PO Holandês" in {g["nome"] for g in r.json()}


class TestOwnershipEscritaEntreFazendas:
    """Endpoints de escrita (POST/PUT) — fazenda #2 não pode ler/editar/criar
    duplicata em cima de dados da fazenda #1."""

    def test_atualizar_motivo_movimentacao_fazenda2_recebe_404(self, client):
        """Ownership check: PUT /movimentacoes/motivos/{id} não pode deixar a
        fazenda #2 editar o motivo cadastrado pela fazenda #1."""
        c, engine, mot_mov_id = client
        _como_fazenda(2)
        r = c.put(f"/movimentacoes/motivos/{mot_mov_id}", json={"nome": "Sequestrado", "ativo": True})
        assert r.status_code == 404
        _como_fazenda(1)
        r = c.put(f"/movimentacoes/motivos/{mot_mov_id}", json={"nome": "Crescimento renomeado", "ativo": True})
        assert r.status_code == 200
        assert r.json()["nome"] == "Crescimento renomeado"

    def test_criar_lote_mesmo_codigo_outra_fazenda_nao_colide(self, client):
        """POST /lotes/ com o mesmo código "01" já usado pela fazenda #1 deve
        ser aceito para a fazenda #2 (unique constraint é por fazenda, não
        global) — e não deve poluir/duplicar o lote da fazenda #1."""
        c, engine, mot_mov_id = client
        _como_fazenda(2)
        r = c.post("/lotes/", json={"codigo": "01", "nome": "Lote da Fazenda 2"})
        assert r.status_code == 200, r.text
        novo_id = r.json()["id"]

        with Session(engine) as s:
            lotes_codigo_01 = s.exec(select(Lote).where(Lote.codigo == "01")).all()
            assert len(lotes_codigo_01) == 2
            assert {l.fazenda_id for l in lotes_codigo_01} == {1, 2}

        # Fazenda #1 continua vendo só o seu próprio lote "01".
        _como_fazenda(1)
        r = c.get("/lotes/")
        nomes_f1 = {l["nome"] for l in r.json()}
        assert "Lactação" in nomes_f1
        assert "Lote da Fazenda 2" not in nomes_f1

        # Fazenda #2 não pode editar o lote da fazenda #1 (ownership check).
        with Session(engine) as s:
            lote_f1 = s.exec(select(Lote).where(Lote.fazenda_id == 1)).first()
        _como_fazenda(2)
        r = c.put(f"/lotes/{lote_f1.id}", json={"codigo": "01", "nome": "Sequestrado"})
        assert r.status_code == 404
        # ... mas edita o próprio sem problema.
        r = c.put(f"/lotes/{novo_id}", json={"codigo": "01", "nome": "Lote da Fazenda 2 renomeado"})
        assert r.status_code == 200
        assert r.json()["nome"] == "Lote da Fazenda 2 renomeado"

    def test_criar_grau_sangue_fazenda2_nao_ve_nem_edita_o_da_fazenda1(self, client):
        c, engine, mot_mov_id = client
        with Session(engine) as s:
            grau_f1 = s.exec(select(GrauSangue).where(GrauSangue.fazenda_id == 1)).first()
            grau_f1_id = grau_f1.id

        _como_fazenda(2)
        # Mesmo nome já usado pela fazenda #1 — não é duplicata para a #2
        # (unique é por fazenda).
        r = c.post("/cadastro/graus-sangue", json={"nome": "PO Holandês", "fracao_holandes": 1.0})
        assert r.status_code == 200, r.text
        # Ownership check: fazenda #2 não pode editar o grau de sangue da #1.
        r = c.put(f"/cadastro/graus-sangue/{grau_f1_id}", json={"nome": "Sequestrado"})
        assert r.status_code == 404

    def test_registrar_baixa_fazenda2_nao_afeta_animal_da_fazenda1(self, client):
        """POST /baixas/ com o número de um animal que só existe na fazenda
        #1 deve ser tratado como "não encontrado" pela fazenda #2 — nunca dar
        baixa num animal de outra fazenda."""
        c, engine, mot_mov_id = client
        _como_fazenda(2)
        r = c.post("/baixas/", json={
            "animais": ["9001"],
            "tipo_baixa": "morte",
            "motivo": "acidente",
            "data_baixa": "2026-02-01",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["baixados"] == 0
        assert body["nao_encontrados"] == ["9001"]

        # O animal da fazenda #1 continua ativo — a fazenda #2 não conseguiu
        # dar baixa nele.
        with Session(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "9001")).first()
            assert animal.ativo is True

    def test_fazenda_1_continua_operando_normalmente(self, client):
        """Sanity check final: depois de todas as tentativas de acesso cruzado
        acima, a fazenda #1 continua enxergando e conseguindo escrever nos
        próprios dados sem qualquer interferência."""
        c, engine, mot_mov_id = client
        _como_fazenda(1)
        assert "9001" in {a["numero"] for a in c.get("/animais/").json()}
        assert "Lactação" in {l["nome"] for l in c.get("/lotes/").json()}
        assert "Mastite" in {m["nome"] for m in c.get("/cadastro/motivos-baixa").json()}
