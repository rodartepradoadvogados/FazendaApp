"""
Comprovante de pagamento de vale (Frente D, sessão de ajustes de tela —
D7-D10): anexar/listar/excluir um arquivo em `ValeFuncionario` e
`ValeAvulso`, reaproveitando `LancamentoAnexo` (mesmo Storage usado no
anexo de lançamento) em vez de uma tabela nova — ver
fazenda/api/routers/cadastro/rh_folha.py, rotas
/cadastro/vales/{tipo}/{id}/comprovante e /cadastro/vales/comprovante/{id}.

O terceiro "vale" do sistema (item de lançamento marcado como vale) não
tem rota aqui — ele já herda o anexo da própria nota financeira (D9).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import (
    ContratoFazenda, ContratoFazendaModulo, Empreitada, Fazenda, Pessoa, ValeAvulso, ValeFuncionario,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        for fid, nome in ((1, "Fazenda 1"), (2, "Fazenda 2")):
            s.add(Fazenda(id=fid, nome=nome))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

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
        permissoes = ""

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    # Mesmo padrão de tests/test_pessoas_anexos.py: um "bucket" em memória no
    # lugar do Supabase Storage de verdade, para não depender de rede/config.
    import fazenda.api.routers.cadastro.rh_folha as rh_folha_mod
    bucket: dict[str, bytes] = {}
    monkeypatch.setattr(rh_folha_mod, "enviar_arquivo", lambda caminho, conteudo, *a, **k: bucket.__setitem__(caminho, conteudo))
    monkeypatch.setattr(rh_folha_mod, "baixar_arquivo", lambda caminho, *a, **k: bucket[caminho])
    monkeypatch.setattr(rh_folha_mod, "excluir_arquivo", lambda caminho, *a, **k: bucket.pop(caminho, None))

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def _criar_pessoa(engine, fazenda_id: int = 1) -> int:
    with Session(engine) as s:
        p = Pessoa(nome="Fulano", tipo="Funcionário", fazenda_id=fazenda_id)
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


def _criar_vale_funcionario(engine, pessoa_id: int, fazenda_id: int = 1) -> int:
    with Session(engine) as s:
        vale = ValeFuncionario(
            pessoa_id=pessoa_id, valor_total=500.0, forma_pagamento="desconto_integral_folha",
            data_pagamento=date(2026, 8, 1), parcelas=1, competencia_inicio="2026-08",
            fazenda_id=fazenda_id,
        )
        s.add(vale)
        s.commit()
        s.refresh(vale)
        return vale.id


def _criar_empreitada(engine, pessoa_id: int, fazenda_id: int = 1) -> int:
    with Session(engine) as s:
        e = Empreitada(pessoa_id=pessoa_id, descricao="Cerca nova", valor_total=1000.0, tipo_pagamento="por_etapa", fazenda_id=fazenda_id)
        s.add(e)
        s.commit()
        s.refresh(e)
        return e.id


def _criar_vale_avulso(engine, pessoa_id: int, origem_id: int, fazenda_id: int = 1) -> int:
    with Session(engine) as s:
        vale = ValeAvulso(
            origem_tipo="empreitada", origem_id=origem_id, pessoa_id=pessoa_id, valor=200.0,
            forma_pagamento="desconto_proximo_pagamento", data_pagamento=date(2026, 8, 1),
            fazenda_id=fazenda_id,
        )
        s.add(vale)
        s.commit()
        s.refresh(vale)
        return vale.id


def _pdf(nome="comprovante.pdf"):
    return {"file": (nome, b"%PDF-1.4 comprovante", "application/pdf")}


class TestComprovanteValeFuncionario:
    def test_anexa_e_lista(self, client):
        c, engine = client
        _como_fazenda(1)
        pessoa_id = _criar_pessoa(engine)
        vale_id = _criar_vale_funcionario(engine, pessoa_id)

        r = c.post(f"/cadastro/vales/funcionario/{vale_id}/comprovante", files=_pdf())
        assert r.status_code == 201, r.text
        corpo = r.json()
        assert corpo["nome_arquivo"] == "comprovante.pdf"
        assert isinstance(corpo["id"], int)

        r = c.get(f"/cadastro/vales/funcionario/{vale_id}/comprovante")
        assert r.status_code == 200, r.text
        lista = r.json()
        assert len(lista) == 1
        assert lista[0]["nome_arquivo"] == "comprovante.pdf"
        assert lista[0]["mime_type"] == "application/pdf"

    def test_baixa_o_conteudo_anexado(self, client):
        c, engine = client
        _como_fazenda(1)
        pessoa_id = _criar_pessoa(engine)
        vale_id = _criar_vale_funcionario(engine, pessoa_id)
        anexo_id = c.post(f"/cadastro/vales/funcionario/{vale_id}/comprovante", files=_pdf()).json()["id"]

        r = c.get(f"/cadastro/vales/comprovante/{anexo_id}")
        assert r.status_code == 200, r.text
        assert r.content == b"%PDF-1.4 comprovante"
        assert r.headers["content-type"] == "application/pdf"

    def test_exclui(self, client):
        c, engine = client
        _como_fazenda(1)
        pessoa_id = _criar_pessoa(engine)
        vale_id = _criar_vale_funcionario(engine, pessoa_id)
        anexo_id = c.post(f"/cadastro/vales/funcionario/{vale_id}/comprovante", files=_pdf()).json()["id"]

        r = c.delete(f"/cadastro/vales/comprovante/{anexo_id}")
        assert r.status_code == 200, r.text
        assert r.json()["excluido"] is True

        assert c.get(f"/cadastro/vales/funcionario/{vale_id}/comprovante").json() == []
        # Excluído — baixar/excluir de novo dá 404, não erro escondido.
        assert c.get(f"/cadastro/vales/comprovante/{anexo_id}").status_code == 404
        assert c.delete(f"/cadastro/vales/comprovante/{anexo_id}").status_code == 404

    def test_varios_comprovantes_no_mesmo_vale(self, client):
        c, engine = client
        _como_fazenda(1)
        pessoa_id = _criar_pessoa(engine)
        vale_id = _criar_vale_funcionario(engine, pessoa_id)

        c.post(f"/cadastro/vales/funcionario/{vale_id}/comprovante", files=_pdf("recibo1.pdf"))
        c.post(f"/cadastro/vales/funcionario/{vale_id}/comprovante", files=_pdf("recibo2.pdf"))

        lista = c.get(f"/cadastro/vales/funcionario/{vale_id}/comprovante").json()
        assert sorted(a["nome_arquivo"] for a in lista) == ["recibo1.pdf", "recibo2.pdf"]

    def test_vale_inexistente_da_404(self, client):
        c, engine = client
        _como_fazenda(1)
        r = c.post("/cadastro/vales/funcionario/999999/comprovante", files=_pdf())
        assert r.status_code == 404

    def test_tipo_invalido_da_400(self, client):
        c, engine = client
        _como_fazenda(1)
        pessoa_id = _criar_pessoa(engine)
        vale_id = _criar_vale_funcionario(engine, pessoa_id)
        r = c.post(f"/cadastro/vales/xyz/{vale_id}/comprovante", files=_pdf())
        assert r.status_code == 400


class TestComprovanteValeAvulso:
    def test_anexa_lista_e_exclui(self, client):
        c, engine = client
        _como_fazenda(1)
        pessoa_id = _criar_pessoa(engine)
        origem_id = _criar_empreitada(engine, pessoa_id)
        vale_id = _criar_vale_avulso(engine, pessoa_id, origem_id)

        r = c.post(f"/cadastro/vales/avulso/{vale_id}/comprovante", files=_pdf("vale_avulso.pdf"))
        assert r.status_code == 201, r.text
        anexo_id = r.json()["id"]

        lista = c.get(f"/cadastro/vales/avulso/{vale_id}/comprovante").json()
        assert len(lista) == 1 and lista[0]["id"] == anexo_id

        assert c.delete(f"/cadastro/vales/comprovante/{anexo_id}").status_code == 200
        assert c.get(f"/cadastro/vales/avulso/{vale_id}/comprovante").json() == []

    def test_comprovante_de_um_tipo_nao_aparece_no_outro(self, client):
        """Vale de funcionário e vale avulso podem ter o MESMO id numérico
        (tabelas diferentes) — a rota tem que respeitar o `tipo` da URL, não
        só o id, senão um comprovante vazaria pro vale errado."""
        c, engine = client
        _como_fazenda(1)
        pessoa_id = _criar_pessoa(engine)
        origem_id = _criar_empreitada(engine, pessoa_id)
        vale_func_id = _criar_vale_funcionario(engine, pessoa_id)
        vale_avulso_id = _criar_vale_avulso(engine, pessoa_id, origem_id)

        c.post(f"/cadastro/vales/funcionario/{vale_func_id}/comprovante", files=_pdf("func.pdf"))

        # Mesmo que os ids coincidissem, o comprovante do funcionário não
        # pode aparecer na listagem do avulso.
        lista_avulso = c.get(f"/cadastro/vales/avulso/{vale_avulso_id}/comprovante").json()
        assert all(a["nome_arquivo"] != "func.pdf" for a in lista_avulso)


class TestIsolamentoPorFazenda:
    def test_fazenda_2_nao_ve_nem_baixa_nem_exclui_comprovante_da_fazenda_1(self, client):
        c, engine = client
        _como_fazenda(1)
        pessoa_id = _criar_pessoa(engine, fazenda_id=1)
        vale_id = _criar_vale_funcionario(engine, pessoa_id, fazenda_id=1)
        anexo_id = c.post(f"/cadastro/vales/funcionario/{vale_id}/comprovante", files=_pdf()).json()["id"]

        _como_fazenda(2)
        assert c.get(f"/cadastro/vales/funcionario/{vale_id}/comprovante").status_code == 404
        assert c.get(f"/cadastro/vales/comprovante/{anexo_id}").status_code == 404
        assert c.delete(f"/cadastro/vales/comprovante/{anexo_id}").status_code == 404
        assert c.post(f"/cadastro/vales/funcionario/{vale_id}/comprovante", files=_pdf()).status_code == 404

        # A fazenda dona continua enxergando normalmente.
        _como_fazenda(1)
        assert c.get(f"/cadastro/vales/funcionario/{vale_id}/comprovante").status_code == 200
        assert c.get(f"/cadastro/vales/comprovante/{anexo_id}").status_code == 200

    def test_fazenda_2_nao_anexa_em_vale_da_fazenda_1(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine, fazenda_id=1)
        vale_id = _criar_vale_funcionario(engine, pessoa_id, fazenda_id=1)

        _como_fazenda(2)
        r = c.post(f"/cadastro/vales/funcionario/{vale_id}/comprovante", files=_pdf())
        assert r.status_code == 404
