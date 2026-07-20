"""
Testes do canal de push (Web Push API) — fazenda/api/routers/push.py.

Cobre: POST/DELETE /push/subscribe (endpoint HTTP) e a função utilitária
enviar_push (mockando pywebpush.webpush — nunca bate na rede de verdade).
Também cobre a deduplicação diária (notificar_push_para_itens) usada pelo
rewire em notificacoes.py, para garantir que o mesmo alerta não reenvia push
a cada poll do sino.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
import fazenda.api.routers.push as push_module
from fazenda.models import PushNotificacaoEnviada, PushSubscription, Usuario


class _FakeUsuario:
    id = 1
    papel = "operador"
    permissoes = "agenda"
    ativo = True
    username = "usuario_teste"


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def app(engine):
    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override
    yield main.app
    main.app.dependency_overrides.clear()


def _client_as(app, user):
    from fazenda.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


# ---------------------------------------------------------------------------
# Endpoint HTTP: subscribe / unsubscribe
# ---------------------------------------------------------------------------
class TestSubscribeEndpoint:
    def test_subscribe_salva_a_subscription_do_usuario_logado(self, app, engine):
        c = _client_as(app, _FakeUsuario())
        r = c.post("/push/subscribe", json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
            "keys": {"p256dh": "chave-p256dh", "auth": "chave-auth"},
            "user_agent": "TesteBrowser/1.0",
        })
        assert r.status_code == 200
        assert r.json() == {"ok": True}

        with Session(engine) as session:
            subs = session.exec(select(PushSubscription).where(PushSubscription.usuario_id == 1)).all()
            assert len(subs) == 1
            assert subs[0].endpoint == "https://fcm.googleapis.com/fcm/send/abc123"
            assert subs[0].p256dh == "chave-p256dh"
            assert subs[0].auth == "chave-auth"

    def test_subscribe_com_mesmo_endpoint_atualiza_em_vez_de_duplicar(self, app, engine):
        c = _client_as(app, _FakeUsuario())
        payload = {"endpoint": "https://push.exemplo/1", "keys": {"p256dh": "p1", "auth": "a1"}}
        c.post("/push/subscribe", json=payload)
        payload2 = {"endpoint": "https://push.exemplo/1", "keys": {"p256dh": "p2", "auth": "a2"}}
        r = c.post("/push/subscribe", json=payload2)
        assert r.status_code == 200

        with Session(engine) as session:
            subs = session.exec(select(PushSubscription).where(PushSubscription.usuario_id == 1)).all()
            assert len(subs) == 1
            assert subs[0].p256dh == "p2"
            assert subs[0].auth == "a2"

    def test_subscribe_incompleta_retorna_422(self, app):
        c = _client_as(app, _FakeUsuario())
        r = c.post("/push/subscribe", json={"endpoint": "https://push.exemplo/1", "keys": {"p256dh": "so-isso"}})
        assert r.status_code == 422

    def test_unsubscribe_remove_todas_as_subscriptions_do_usuario(self, app, engine):
        c = _client_as(app, _FakeUsuario())
        c.post("/push/subscribe", json={"endpoint": "https://push.exemplo/1", "keys": {"p256dh": "p1", "auth": "a1"}})
        c.post("/push/subscribe", json={"endpoint": "https://push.exemplo/2", "keys": {"p256dh": "p2", "auth": "a2"}})

        r = c.request("DELETE", "/push/subscribe", json={})
        assert r.status_code == 200
        assert r.json()["removidas"] == 2

        with Session(engine) as session:
            subs = session.exec(select(PushSubscription).where(PushSubscription.usuario_id == 1)).all()
            assert subs == []

    def test_unsubscribe_com_endpoint_remove_so_aquela_subscription(self, app, engine):
        c = _client_as(app, _FakeUsuario())
        c.post("/push/subscribe", json={"endpoint": "https://push.exemplo/1", "keys": {"p256dh": "p1", "auth": "a1"}})
        c.post("/push/subscribe", json={"endpoint": "https://push.exemplo/2", "keys": {"p256dh": "p2", "auth": "a2"}})

        r = c.request("DELETE", "/push/subscribe", json={"endpoint": "https://push.exemplo/1"})
        assert r.status_code == 200
        assert r.json()["removidas"] == 1

        with Session(engine) as session:
            subs = session.exec(select(PushSubscription).where(PushSubscription.usuario_id == 1)).all()
            assert len(subs) == 1
            assert subs[0].endpoint == "https://push.exemplo/2"

    def test_chave_publica_nao_exige_login(self, app):
        c = TestClient(app)  # sem dependency_override de get_current_user
        r = c.get("/push/chave-publica")
        assert r.status_code == 200
        assert r.json()["chave_publica"] == push_module.VAPID_PUBLIC_KEY


# ---------------------------------------------------------------------------
# enviar_push: mocka pywebpush.webpush — nunca bate na rede de verdade
# ---------------------------------------------------------------------------
class TestEnviarPush:
    def test_enviar_push_chama_webpush_para_cada_subscription_do_usuario(self, engine, monkeypatch):
        chamadas = []
        monkeypatch.setattr(push_module, "webpush", lambda **kwargs: chamadas.append(kwargs))

        with Session(engine) as session:
            session.add(PushSubscription(usuario_id=1, endpoint="https://push.exemplo/1", p256dh="p1", auth="a1"))
            session.add(PushSubscription(usuario_id=1, endpoint="https://push.exemplo/2", p256dh="p2", auth="a2"))
            session.add(PushSubscription(usuario_id=2, endpoint="https://push.exemplo/outro-usuario", p256dh="px", auth="ax"))
            session.commit()

            push_module.enviar_push(1, "Financeiro", "Conta vence hoje", "/financeiro", session=session)

        assert len(chamadas) == 2
        endpoints_chamados = {c["subscription_info"]["endpoint"] for c in chamadas}
        assert endpoints_chamados == {"https://push.exemplo/1", "https://push.exemplo/2"}
        # Usa as chaves VAPID do módulo (não bate na rede de verdade).
        for c in chamadas:
            assert c["vapid_private_key"] == push_module.VAPID_PRIVATE_KEY
            assert "Financeiro" in c["data"]
            assert "Conta vence hoje" in c["data"]
            assert "/financeiro" in c["data"]

    def test_enviar_push_sem_subscription_nao_chama_webpush(self, engine, monkeypatch):
        chamadas = []
        monkeypatch.setattr(push_module, "webpush", lambda **kwargs: chamadas.append(kwargs))

        with Session(engine) as session:
            push_module.enviar_push(999, "Título", "Corpo", "/agenda", session=session)

        assert chamadas == []

    def test_enviar_push_remove_subscription_expirada_em_404_410(self, engine, monkeypatch):
        from pywebpush import WebPushException

        class _RespFalsa:
            status_code = 410

        def _webpush_falha(**kwargs):
            raise WebPushException("gone", response=_RespFalsa())

        monkeypatch.setattr(push_module, "webpush", _webpush_falha)

        with Session(engine) as session:
            session.add(PushSubscription(usuario_id=1, endpoint="https://push.exemplo/expirada", p256dh="p1", auth="a1"))
            session.commit()

            push_module.enviar_push(1, "Título", "Corpo", "/agenda", session=session)

            restantes = session.exec(select(PushSubscription).where(PushSubscription.usuario_id == 1)).all()
            assert restantes == []

    def test_enviar_push_nao_propaga_erro_inesperado_do_webpush(self, engine, monkeypatch):
        def _explode(**kwargs):
            raise RuntimeError("falha de rede qualquer")

        monkeypatch.setattr(push_module, "webpush", _explode)

        with Session(engine) as session:
            session.add(PushSubscription(usuario_id=1, endpoint="https://push.exemplo/1", p256dh="p1", auth="a1"))
            session.commit()

            # Não deve levantar — um push que falha não pode derrubar quem chamou.
            push_module.enviar_push(1, "Título", "Corpo", "/agenda", session=session)


# ---------------------------------------------------------------------------
# Deduplicação diária (notificar_push_para_itens) — usada pelo rewire em
# notificacoes.py e pela varredura periódica (despachar_push_pendentes).
# ---------------------------------------------------------------------------
class TestNotificarPushParaItens:
    def test_nao_envia_push_se_usuario_nao_tem_subscription(self, engine, monkeypatch):
        chamadas = []
        monkeypatch.setattr(push_module, "enviar_push", lambda **kwargs: chamadas.append(kwargs))

        with Session(engine) as session:
            push_module.notificar_push_para_itens(
                1, [{"tipo": "agenda", "categoria": "Gestão/Financeiro", "descricao": "Conta a pagar: Luz"}], session,
            )
        assert chamadas == []

    def test_envia_push_uma_vez_para_item_novo_e_registra_dedup(self, engine, monkeypatch):
        chamadas = []
        monkeypatch.setattr(push_module, "enviar_push", lambda **kwargs: chamadas.append(kwargs))

        with Session(engine) as session:
            session.add(PushSubscription(usuario_id=1, endpoint="https://push.exemplo/1", p256dh="p1", auth="a1"))
            session.commit()

            itens = [{"tipo": "agenda", "categoria": "Gestão/Financeiro", "descricao": "Conta a pagar: Luz — R$ 100,00"}]
            push_module.notificar_push_para_itens(1, itens, session)

            assert len(chamadas) == 1
            assert chamadas[0]["url"] == "/financeiro"

            registros = session.exec(select(PushNotificacaoEnviada).where(PushNotificacaoEnviada.usuario_id == 1)).all()
            assert len(registros) == 1
            assert registros[0].data_referencia == date.today()

    def test_nao_reenvia_push_para_o_mesmo_item_no_mesmo_dia(self, engine, monkeypatch):
        chamadas = []
        monkeypatch.setattr(push_module, "enviar_push", lambda **kwargs: chamadas.append(kwargs))

        with Session(engine) as session:
            session.add(PushSubscription(usuario_id=1, endpoint="https://push.exemplo/1", p256dh="p1", auth="a1"))
            session.commit()

            itens = [{"tipo": "agenda", "categoria": "Gestão/Financeiro", "descricao": "Conta a pagar: Luz — R$ 100,00"}]
            # Simula duas checagens (ex.: dois polls do sino, ou a varredura periódica).
            push_module.notificar_push_para_itens(1, itens, session)
            push_module.notificar_push_para_itens(1, itens, session)

        assert len(chamadas) == 1  # só a primeira gerou push de verdade

    def test_item_diferente_gera_novo_push(self, engine, monkeypatch):
        chamadas = []
        monkeypatch.setattr(push_module, "enviar_push", lambda **kwargs: chamadas.append(kwargs))

        with Session(engine) as session:
            session.add(PushSubscription(usuario_id=1, endpoint="https://push.exemplo/1", p256dh="p1", auth="a1"))
            session.commit()

            push_module.notificar_push_para_itens(1, [{"tipo": "agenda", "categoria": "Gestão/Financeiro", "descricao": "Conta A"}], session)
            push_module.notificar_push_para_itens(1, [{"tipo": "agenda", "categoria": "Gestão/Financeiro", "descricao": "Conta B"}], session)

        assert len(chamadas) == 2


class TestUrlDestino:
    def test_financeiro(self):
        assert push_module.url_destino({"categoria": "Gestão/Financeiro", "tipo": "agenda"}) == "/financeiro"

    def test_estoque(self):
        assert push_module.url_destino({"categoria": "Estoque", "tipo": "agenda"}) == "/estoque"

    def test_portal(self):
        assert push_module.url_destino({"categoria": "Portal", "tipo": "portal_mensagem"}) == "/portal"

    def test_aprovacao(self):
        assert push_module.url_destino({"categoria": "Aprovações", "tipo": "aprovacao"}) == "/aprovacoes"

    def test_default_agenda(self):
        assert push_module.url_destino({"categoria": "Reprodutivo", "tipo": "agenda"}) == "/agenda"


# ---------------------------------------------------------------------------
# Rewire: GET /notificacoes/ também despacha push (mockando enviar_push).
# ---------------------------------------------------------------------------
class TestRewireNotificacoes:
    def test_get_notificacoes_dispara_push_deduplicado_para_quem_tem_subscription(self, app, engine, monkeypatch):
        from fazenda.models import AgendaManual

        chamadas = []
        monkeypatch.setattr(push_module, "enviar_push", lambda **kwargs: chamadas.append(kwargs))

        with Session(engine) as session:
            session.add(AgendaManual(data_evento=date.today(), descricao="Reunião com veterinário", categoria="Atividades"))
            session.add(PushSubscription(usuario_id=1, endpoint="https://push.exemplo/1", p256dh="p1", auth="a1"))
            session.commit()

        c = _client_as(app, _FakeUsuario())
        r = c.get("/notificacoes/")
        assert r.status_code == 200
        assert r.json()["total"] >= 1
        assert len(chamadas) >= 1

        # Um segundo poll (comportamento normal do sino, a cada 5 min) não deve
        # reenviar push para o mesmo evento de hoje.
        chamadas.clear()
        r2 = c.get("/notificacoes/")
        assert r2.status_code == 200
        assert chamadas == []
