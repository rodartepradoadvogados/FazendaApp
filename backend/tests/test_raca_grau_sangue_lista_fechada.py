"""
Raça/Grau de sangue: lista fechada de verdade (não mais texto livre) + notas
didáticas por entrada (31/08/2026).

Cobre duas coisas que não existiam antes deste conserto:
1. `seed_racas_grau_sangue` v2 — backfill de nota em quem já existia (sem
   mexer em fracao_holandes/ativo), inserção do que é novo, e desativação
   (não exclusão) da antiga raça-curinga "Outra".
2. Validação no backend (`criar_animal`/`atualizar_ficha_animal`) que agora
   recusa um valor de raça/grau de sangue fora do cadastro ativo — mas só
   quando o valor está MUDANDO e a fazenda já tem pelo menos 1 opção ativa
   cadastrada (ver `_validar_raca_grau_sangue`).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.api.routers.cadastro.animais import seed_racas_grau_sangue
from fazenda.models import GrauSangue, Raca, SeedFlag


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
        c._engine = engine  # type: ignore[attr-defined]
        yield c

    main.app.dependency_overrides.clear()


class TestSeedRacasGrauSangueV2:
    def test_seed_cria_racas_e_graus_com_nota(self, client):
        engine = client._engine  # type: ignore[attr-defined]
        with Session(engine) as s:
            seed_racas_grau_sangue(s, fazenda_id=None)

        with Session(engine) as s:
            racas = s.exec(select(Raca)).all()
            graus = s.exec(select(GrauSangue)).all()
            assert any(r.nome == "Girolando" and r.nota for r in racas)
            assert any(g.nome == "1/2 Holandês x Gir" and g.nota and g.fracao_holandes == 0.5 for g in graus)

    def test_seed_e_idempotente(self, client):
        engine = client._engine  # type: ignore[attr-defined]
        with Session(engine) as s:
            seed_racas_grau_sangue(s, fazenda_id=None)
        with Session(engine) as s:
            n_racas_antes = len(s.exec(select(Raca)).all())
            n_graus_antes = len(s.exec(select(GrauSangue)).all())
        with Session(engine) as s:
            seed_racas_grau_sangue(s, fazenda_id=None)
        with Session(engine) as s:
            assert len(s.exec(select(Raca)).all()) == n_racas_antes
            assert len(s.exec(select(GrauSangue)).all()) == n_graus_antes

    def test_seed_backfilla_nota_de_quem_ja_existia_sem_mexer_em_fracao_ou_ativo(self, client):
        """Simula uma fazenda que já tinha rodado a v1 (sem nota nenhuma) —
        rodar a v2 preenche a nota mas não pode tocar em fracao_holandes/ativo."""
        engine = client._engine  # type: ignore[attr-defined]
        with Session(engine) as s:
            s.add(Raca(nome="Girolando", nota=None, ativo=False))
            s.add(GrauSangue(nome="1/2 Holandês x Gir", fracao_holandes=0.5, nota=None, ativo=False))
            s.commit()

        with Session(engine) as s:
            seed_racas_grau_sangue(s, fazenda_id=None)

        with Session(engine) as s:
            raca = s.exec(select(Raca).where(Raca.nome == "Girolando")).one()
            grau = s.exec(select(GrauSangue).where(GrauSangue.nome == "1/2 Holandês x Gir")).one()
            assert raca.nota  # backfillado
            assert raca.ativo is False  # não sobrescrito
            assert grau.nota  # backfillado
            assert grau.fracao_holandes == 0.5  # não sobrescrito
            assert grau.ativo is False  # não sobrescrito

    def test_seed_desativa_outra_sem_excluir(self, client):
        engine = client._engine  # type: ignore[attr-defined]
        with Session(engine) as s:
            s.add(Raca(nome="Outra", ativo=True))
            s.commit()

        with Session(engine) as s:
            seed_racas_grau_sangue(s, fazenda_id=None)

        with Session(engine) as s:
            outra = s.exec(select(Raca).where(Raca.nome == "Outra")).one()
            assert outra.ativo is False


class TestValidacaoListaFechada:
    def test_cadastro_vazio_nao_bloqueia_lancamento(self, client):
        """Sem nenhuma raça/grau ativo cadastrado (fazenda que nunca rodou o
        seed), o valor passa livre — não dá pra fechar uma lista vazia."""
        c = client
        r = c.post("/cadastro/animais", json={"numero": "9001", "sexo": "F", "raca": "Qualquer Coisa"})
        assert r.status_code == 200, r.text

    def test_valor_fora_da_lista_e_recusado_quando_cadastro_existe(self, client):
        engine = client._engine  # type: ignore[attr-defined]
        with Session(engine) as s:
            s.add(Raca(nome="Girolando", ativo=True))
            s.commit()

        r = client.post("/cadastro/animais", json={"numero": "9002", "sexo": "F", "raca": "Raça Inventada"})
        assert r.status_code == 400
        assert "não é uma opção válida" in r.json()["detail"]

    def test_valor_da_lista_e_aceito(self, client):
        engine = client._engine  # type: ignore[attr-defined]
        with Session(engine) as s:
            s.add(Raca(nome="Girolando", ativo=True))
            s.commit()

        r = client.post("/cadastro/animais", json={"numero": "9003", "sexo": "F", "raca": "Girolando"})
        assert r.status_code == 200, r.text

    def test_valor_legado_inalterado_continua_passando_mesmo_fora_da_lista_atual(self, client):
        """Cláusula do avô: editar outro campo da ficha sem MUDAR a raça não
        pode quebrar por causa de um valor legado que não está mais na lista."""
        engine = client._engine  # type: ignore[attr-defined]
        # Cadastro fechado só tem Girolando — mas o animal já tem uma raça
        # legada ("Mestiço") de antes da lista fechada existir.
        with Session(engine) as s:
            s.add(Raca(nome="Girolando", ativo=True))
            s.commit()
        r = client.post("/cadastro/animais", json={"numero": "9004", "sexo": "F", "raca": "Girolando"})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            from fazenda.models import Animal
            a = s.exec(select(Animal).where(Animal.numero == "9004")).one()
            a.raca = "Mestiço"  # simula dado legado gravado antes da lista fechada
            s.add(a)
            s.commit()

        r = client.put("/cadastro/animais/9004", json={"numero": "9004", "sexo": "F", "raca": "Mestiço", "nome": "Editada"})
        assert r.status_code == 200, r.text
        assert r.json()["nome"] == "Editada"

    def test_editar_para_valor_novo_fora_da_lista_e_recusado(self, client):
        engine = client._engine  # type: ignore[attr-defined]
        with Session(engine) as s:
            s.add(Raca(nome="Girolando", ativo=True))
            s.commit()
        client.post("/cadastro/animais", json={"numero": "9005", "sexo": "F", "raca": "Girolando"})

        r = client.put("/cadastro/animais/9005", json={"numero": "9005", "sexo": "F", "raca": "Raça Inventada"})
        assert r.status_code == 400

    def test_valor_vazio_sempre_aceito(self, client):
        engine = client._engine  # type: ignore[attr-defined]
        with Session(engine) as s:
            s.add(Raca(nome="Girolando", ativo=True))
            s.commit()
        r = client.post("/cadastro/animais", json={"numero": "9006", "sexo": "F"})
        assert r.status_code == 200, r.text
