"""
Garante que os modelos de CSV baixáveis em Configurações > Importar dados
(colunas_csv + exemplo) realmente funcionam quando reenviados — monta um CSV
de verdade com essas colunas/valores e roda pelo MESMO caminho real (upload
de arquivo) usado pelo usuário, tanto para as 5 categorias novas quanto para
as 10 que reaproveitam o parser rico do Ideagri.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.api.routers.importar import CATEGORIAS_EXISTENTES, CATEGORIAS_NOVAS
from fazenda.models import Animal, Fornecedor


def _csv_de_modelo(colunas_csv: list[str], exemplo: list[str]) -> bytes:
    texto = ";".join(colunas_csv) + "\r\n" + ";".join(exemplo) + "\r\n"
    return texto.encode("windows-1252")


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


class TestModelosCategoriasNovas:
    @pytest.mark.parametrize("categoria", list(CATEGORIAS_NOVAS.keys()))
    def test_modelo_e_aceito_pelo_endpoint_real(self, client, categoria):
        c, engine = client
        cfg = CATEGORIAS_NOVAS[categoria]

        # produtos_estoque/estoque_movimento e fornecedores dependem de
        # cadastro prévio para "casar" plenamente — aqui só garantimos que o
        # arquivo é bem formado e não quebra o parser (erros de negócio, como
        # "fornecedor não encontrado", não invalidam o modelo de colunas).
        if categoria == "fornecedores":
            # Fornecedores não depende de nada prévio — roda limpo.
            content = _csv_de_modelo(cfg["colunas_csv"], cfg["exemplo"])
            r = c.post(f"/importar/{categoria}", files={"file": ("modelo.csv", content, "text/csv")})
            assert r.status_code == 200
            assert r.json()["criados"] == 1
            return

        if categoria == "estoque_movimento":
            with Session(engine) as s:
                from fazenda.models import Estoque
                s.add(Estoque(nome=cfg["exemplo"][0], categoria="alimento", quantidade=1000))
                s.commit()

        content = _csv_de_modelo(cfg["colunas_csv"], cfg["exemplo"])
        r = c.post(f"/importar/{categoria}", files={"file": ("modelo.csv", content, "text/csv")})
        assert r.status_code == 200
        d = r.json()
        assert not d.get("erros"), f"{categoria}: modelo gerou erro(s): {d.get('erros')}"


class TestModelosCategoriasExistentes:
    @pytest.mark.parametrize("categoria", list(CATEGORIAS_EXISTENTES.keys()))
    def test_modelo_e_aceito_pelo_upload_real(self, client, categoria):
        c, engine = client
        cfg = CATEGORIAS_EXISTENTES[categoria]
        content = _csv_de_modelo(cfg["colunas_csv"], cfg["exemplo"])
        r = c.post(f"/upload/{cfg['tipo_upload']}", files={"file": ("modelo.csv", content, "text/csv")})
        assert r.status_code == 200, f"{categoria} ({cfg['tipo_upload']}): {r.text}"


class TestPlanoContaGerencialReal:
    def test_arquivo_real_do_usuario_e_aceito(self, client):
        """Regressão com uma amostra real do arquivo anexado pelo usuário."""
        c, engine = client
        linhas = [
            "N° ct. ger.;Nome ct. ger.;Ativa;Part. ativ.;Fluxo;Tipo F/V;",
            "2;Receita;Não;Não;Não;;",
            "2.01;Pecuária;Não;Não;Não;;",
            "2.01.01.01;Leite indústria;Sim;Sim;Sim;;",
            "3;Despesa;Não;Não;Não;;",
            "3.01.01.01;Concentrado protéico;Sim;Sim;Sim;Variável;",
        ]
        content = ("\r\n".join(linhas) + "\r\n").encode("windows-1252")
        r = c.post("/upload/plano_conta_gerencial", files={"file": ("plano.csv", content, "text/csv")})
        assert r.status_code == 200
        assert r.json()["registros"] == 5

        # A conta postável (Sim/ativa) aparece nas opções do lançamento financeiro.
        opcoes = c.get("/financeiro/opcoes").json()
        codigos = {x["codigo"] for x in opcoes["contas_gerenciais"]}
        assert "3.01.01.01" in codigos
        assert "2.01.01.01" in codigos
        # O grupo "2.01 - Pecuária" é inativo (não postável) e não deve aparecer.
        assert "2.01" not in codigos
