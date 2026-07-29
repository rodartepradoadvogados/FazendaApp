"""
Fotos do campo (app móvel) — ver fazenda/api/routers/fotos.py e
fazenda/models/fotos.py. Mesmo padrão de mock do Supabase Storage usado em
tests/test_arquivo_contador_desbloqueio.py para o Arquivo fiscal-contábil.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, ContratoFazenda, ContratoFazendaModulo, Fazenda, PortalMensagem, Usuario, UsuarioFazenda
from fazenda.models.planos import MODULOS_COMERCIAIS


class _FakeUser:
    id = 7
    papel = "operador"
    ativo = True
    username = "peao.teste"
    permissoes = "rebanho"


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Teste"))
        s.add(Fazenda(id=2, nome="Outra Fazenda"))
        s.add(Usuario(id=7, username=_FakeUser.username, senha_hash="x", papel="operador", ativo=True, permissoes="rebanho"))
        s.add(UsuarioFazenda(usuario_id=7, fazenda_id=1))
        # Destinatários possíveis do fan-out de avisos da foto: 8 e 9 na fazenda 1,
        # 10 desativado, 11 numa fazenda diferente (não deve receber nada da 1).
        s.add(Usuario(id=8, username="vet.teste", senha_hash="x", papel="operador", ativo=True, permissoes="rebanho"))
        s.add(Usuario(id=9, username="gerente.teste", senha_hash="x", papel="operador", ativo=True, permissoes="rebanho"))
        s.add(Usuario(id=10, username="desativado.teste", senha_hash="x", papel="operador", ativo=False, permissoes="rebanho"))
        s.add(Usuario(id=11, username="outrafazenda.teste", senha_hash="x", papel="operador", ativo=True, permissoes="rebanho"))
        s.add(UsuarioFazenda(usuario_id=8, fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=9, fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=10, fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=11, fazenda_id=2))
        s.add(Animal(id=1, numero="123", fazenda_id=1))
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
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    import fazenda.api.routers.fotos as fotos_mod
    monkeypatch.setattr(fotos_mod, "enviar_arquivo", lambda *a, **k: None)
    monkeypatch.setattr(fotos_mod, "baixar_arquivo", lambda *a, **k: b"bytes-da-foto-fake")
    monkeypatch.setattr(fotos_mod, "excluir_arquivo", lambda *a, **k: None)

    with TestClient(main.app) as c:
        yield c

    main.app.dependency_overrides.clear()


class TestUploadFoto:
    def test_upload_basico(self, client):
        r = client.post(
            "/fotos/upload",
            files={"file": ("vaca.jpg", b"conteudo-fake-da-foto", "image/jpeg")},
            data={"identificacao_animal": "123", "descricao": "Machucado na pata"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["identificacao_animal"] == "123"
        assert body["descricao"] == "Machucado na pata"
        assert body["tamanho_bytes"] == len(b"conteudo-fake-da-foto")

    def test_upload_sem_metadados_opcionais(self, client):
        r = client.post("/fotos/upload", files={"file": ("foto.jpg", b"abc", "image/jpeg")})
        assert r.status_code == 201, r.text
        assert r.json()["identificacao_animal"] is None

    def test_upload_arquivo_vazio_rejeitado(self, client):
        r = client.post("/fotos/upload", files={"file": ("vazio.jpg", b"", "image/jpeg")})
        assert r.status_code == 400

    def test_upload_maior_que_limite_rejeitado(self, client):
        conteudo_grande = b"x" * (15 * 1024 * 1024 + 1)
        r = client.post("/fotos/upload", files={"file": ("grande.jpg", conteudo_grande, "image/jpeg")})
        assert r.status_code == 400


class TestListarBaixarExcluirFoto:
    def _enviar(self, client, **extra):
        return client.post(
            "/fotos/upload", files={"file": ("foto.jpg", b"conteudo", "image/jpeg")}, data=extra,
        ).json()

    def test_listar_e_baixar(self, client):
        foto = self._enviar(client, identificacao_animal="55")
        r_lista = client.get("/fotos")
        assert r_lista.status_code == 200
        assert any(f["id"] == foto["id"] for f in r_lista.json())

        r_download = client.get(f"/fotos/{foto['id']}/arquivo")
        assert r_download.status_code == 200
        assert r_download.content == b"bytes-da-foto-fake"

    def test_filtro_por_identificacao_animal(self, client):
        self._enviar(client, identificacao_animal="10")
        self._enviar(client, identificacao_animal="20")
        r = client.get("/fotos", params={"identificacao_animal": "10"})
        assert r.status_code == 200
        assert all(f["identificacao_animal"] == "10" for f in r.json())
        assert len(r.json()) == 1

    def test_excluir(self, client):
        foto = self._enviar(client)
        r = client.delete(f"/fotos/{foto['id']}")
        assert r.status_code == 200
        assert r.json() == {"excluido": True}
        r_lista = client.get("/fotos")
        assert not any(f["id"] == foto["id"] for f in r_lista.json())

    def test_baixar_foto_inexistente_404(self, client):
        r = client.get("/fotos/99999/arquivo")
        assert r.status_code == 404

    def test_excluir_foto_inexistente_404(self, client):
        r = client.delete("/fotos/99999")
        assert r.status_code == 404


class TestAssuntoEDestinatarios:
    def _enviar(self, client, **extra):
        r = client.post(
            "/fotos/upload", files={"file": ("foto.jpg", b"conteudo", "image/jpeg")}, data=extra,
        )
        assert r.status_code == 201, r.text
        return r.json()

    def test_destinatarios_especificos(self, client, monkeypatch):
        import fazenda.database as database
        foto = self._enviar(client, destinatarios_usuario_id="8,9")
        assert foto["notificados"] == 2
        with Session(database.engine) as s:
            avisos = s.exec(select(PortalMensagem).where(PortalMensagem.foto_campo_id == foto["id"])).all()
        assert {a.destinatario_usuario_id for a in avisos} == {8, 9}
        assert all(a.tipo == "foto" for a in avisos)

    def test_sem_destinatarios_notifica_todos_da_fazenda_menos_remetente(self, client):
        import fazenda.database as database
        foto = self._enviar(client)
        with Session(database.engine) as s:
            avisos = s.exec(select(PortalMensagem).where(PortalMensagem.foto_campo_id == foto["id"])).all()
        # 8 e 9 (ativos, fazenda 1); 7 é o remetente (excluído); 10 desativado; 11 outra fazenda.
        assert {a.destinatario_usuario_id for a in avisos} == {8, 9}

    def test_destinatario_inexistente_ou_desativado_e_ignorado(self, client):
        import fazenda.database as database
        foto = self._enviar(client, destinatarios_usuario_id="8,10,99999")
        assert foto["notificados"] == 1
        with Session(database.engine) as s:
            avisos = s.exec(select(PortalMensagem).where(PortalMensagem.foto_campo_id == foto["id"])).all()
        assert {a.destinatario_usuario_id for a in avisos} == {8}

    def test_tipo_assunto_animal_resolve_animal_id(self, client):
        foto = self._enviar(client, tipo_assunto="animal", identificacao_animal="123")
        assert foto["tipo_assunto"] == "animal"
        assert foto["animal_id"] == 1

    def test_tipo_assunto_animal_numero_inexistente_so_grava_texto(self, client):
        foto = self._enviar(client, tipo_assunto="animal", identificacao_animal="999")
        assert foto["tipo_assunto"] == "animal"
        assert foto["animal_id"] is None
        assert foto["identificacao_animal"] == "999"

    def test_tipo_assunto_lote_persiste_csv(self, client):
        foto = self._enviar(client, tipo_assunto="lote", lotes="01,03")
        assert foto["tipo_assunto"] == "lote"
        assert foto["lotes"] == "01,03"

    def test_assunto_fixo_invalido_400(self, client):
        r = client.post(
            "/fotos/upload", files={"file": ("foto.jpg", b"conteudo", "image/jpeg")},
            data={"tipo_assunto": "outro", "assunto_fixo": "chutando"},
        )
        assert r.status_code == 400

    def test_falha_no_storage_nao_cria_portal_mensagem(self, client, monkeypatch):
        import fazenda.database as database
        import fazenda.api.routers.fotos as fotos_mod

        def _falha(*a, **k):
            raise RuntimeError("Storage indisponível")

        monkeypatch.setattr(fotos_mod, "enviar_arquivo", _falha)
        r = client.post(
            "/fotos/upload", files={"file": ("foto.jpg", b"conteudo", "image/jpeg")},
            data={"destinatarios_usuario_id": "8"},
        )
        assert r.status_code == 502
        with Session(database.engine) as s:
            assert s.exec(select(PortalMensagem)).all() == []


class TestIsolamentoPorFazenda:
    def test_foto_de_outra_fazenda_nao_aparece(self, client, monkeypatch):
        foto = self._enviar_helper(client)
        import main
        from fazenda.auth import get_fazenda_atual_id
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 2
        r = client.get(f"/fotos/{foto['id']}/arquivo")
        assert r.status_code == 404

    def _enviar_helper(self, client):
        return client.post(
            "/fotos/upload", files={"file": ("foto.jpg", b"conteudo", "image/jpeg")},
        ).json()
