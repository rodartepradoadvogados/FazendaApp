"""
BST "Reverter (voltar a apta)" não deve tornar o animal apto imediatamente —
ele vai para "Incluir no próximo BST" (bst_reanalise/bst_nunca_aplicados) e só
volta a bst_elegiveis depois que uma NOVA aplicação de BST é de fato lançada.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        with Session(engine) as s:
            # Vaca em lactação, DEL 70 (>= 60 padrão), sem previsão de secagem
            # — elegível para BST assim que não estiver excluída/revertida.
            s.add(Animal(numero="300", grupo_primario="01 - Alta", del_dias=70, sexo="F", ativo=True))
            s.commit()
        yield c, engine

    main.app.dependency_overrides.clear()


def _numeros(lista):
    return {item["numero_matriz"] for item in lista}


class TestReverterBst:
    def test_animal_apto_aparece_em_elegiveis_por_padrao(self, client):
        c, _ = client
        r = c.get("/agenda/")
        assert "300" in _numeros(r.json()["bst_elegiveis"])

    def test_reverter_nao_torna_apta_imediatamente(self, client):
        c, engine = client
        # Marca como inapta e depois reverte — fluxo real do botão "Reverter".
        c.post("/agenda/bst/marcar-inapta", json={"numeros_matriz": ["300"], "inapta": True})
        r = c.post("/agenda/bst/marcar-inapta", json={"numeros_matriz": ["300"], "inapta": False})
        assert r.status_code == 200

        with Session(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "300")).first()
            assert animal.excluir_bst is False
            assert animal.aguardando_nova_aplicacao_bst is True

        r = c.get("/agenda/")
        dados = r.json()
        assert "300" not in _numeros(dados["bst_elegiveis"])
        assert "300" in _numeros(dados["bst_nunca_aplicados"])

    def test_nova_aplicacao_fecha_o_ciclo_e_volta_a_elegivel(self, client):
        c, engine = client
        c.post("/agenda/bst/marcar-inapta", json={"numeros_matriz": ["300"], "inapta": True})
        c.post("/agenda/bst/marcar-inapta", json={"numeros_matriz": ["300"], "inapta": False})

        r = c.post("/agenda/bst/aplicar", json={
            "numeros_matriz": ["300"], "data_aplicacao": date.today().isoformat(),
            "produto": "Lactotropin", "aplicado": True,
        })
        assert r.status_code == 200

        with Session(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "300")).first()
            assert animal.aguardando_nova_aplicacao_bst is False

        r = c.get("/agenda/")
        dados = r.json()
        assert "300" in _numeros(dados["bst_elegiveis"])
        assert "300" not in _numeros(dados["bst_nunca_aplicados"])

    def test_marcar_inapta_true_limpa_flag_de_reversao(self, client):
        c, engine = client
        c.post("/agenda/bst/marcar-inapta", json={"numeros_matriz": ["300"], "inapta": True})
        c.post("/agenda/bst/marcar-inapta", json={"numeros_matriz": ["300"], "inapta": False})
        # Marcar como inapta de novo deve limpar o "aguardando_nova_aplicacao_bst"
        # (evita os dois estados coexistindo com sentidos conflitantes).
        c.post("/agenda/bst/marcar-inapta", json={"numeros_matriz": ["300"], "inapta": True})

        with Session(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "300")).first()
            assert animal.excluir_bst is True
            assert animal.aguardando_nova_aplicacao_bst is False
