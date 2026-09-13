"""Recorte por fazenda do envio semanal do Manual da Fazenda.

O laço de fundo (`main._loop_manual_fazenda_semanal`) chamava
`enviar_manual_semanal_se_necessario(session)` SEM fazenda nenhuma. Com
`fazenda_id = None`, `montar_manual` montava o PDF sem recorte (dados de todas
as fazendas juntos) e `emails_administradores_fazenda` devolvia TODOS os
admins ativos de TODAS as fazendas. Com uma segunda fazenda-cliente isso vira
vazamento por e-mail — sai do sistema e não se desfaz.

Estes testes fixam o comportamento novo: um manual POR fazenda-cliente, cada
um com os dados e os destinatários da sua; sandbox (`eh_teste`) e a fazenda
"lógica" da CowData (`eh_empresa_cowdata`) não disparam nada; instalação de
fazenda única (tabela `fazenda` vazia) segue global como sempre foi.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.rules.manual_fazenda as mf
import fazenda.rules.manual_fazenda_pdf as mf_pdf
from fazenda.models import (
    Animal, Fazenda, ParametroManualFazenda, Usuario, UsuarioFazenda,
)

SEGUNDA_7H = datetime(2026, 7, 27, 7, 0)  # 27/07/2026 é uma segunda-feira


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def envios(monkeypatch):
    """Captura os envios em vez de mandar e-mail de verdade. Cada item é
    (destinatario, manual) — o manual é o dict que virou PDF naquele envio,
    o que deixa conferir o RECORTE do conteúdo, não só o destinatário."""
    capturados: list[tuple[str, dict]] = []
    ultimo_manual: dict = {}

    def _pdf_falso(manual: dict) -> bytes:
        ultimo_manual.clear()
        ultimo_manual.update(manual)
        return b"%PDF-falso"

    def _email_falso(destino, assunto, corpo, nome_anexo=None, anexo=None):
        capturados.append((destino, dict(ultimo_manual)))

    monkeypatch.setattr(mf_pdf, "gerar_pdf_manual", _pdf_falso)
    monkeypatch.setattr(mf, "enviar_email", _email_falso)
    return capturados


def _fazenda(session: Session, nome: str, **flags) -> int:
    f = Fazenda(nome=nome, **flags)
    session.add(f)
    session.commit()
    session.refresh(f)
    return f.id


def _admin(session: Session, username: str, email: str, fazenda_id: int | None = None) -> int:
    u = Usuario(username=username, senha_hash="x", papel="admin", ativo=True, email=email)
    session.add(u)
    session.commit()
    session.refresh(u)
    if fazenda_id is not None:
        session.add(UsuarioFazenda(usuario_id=u.id, fazenda_id=fazenda_id))
        session.commit()
    return u.id


def _liga_envio(session: Session, fazenda_id: int | None) -> None:
    session.add(ParametroManualFazenda(fazenda_id=fazenda_id, email_semanal_ativo=True))
    session.commit()


def _cenario_duas_clientes(session: Session) -> tuple[int, int]:
    """Duas fazendas-cliente (A e B), com admin e rebanho próprios, mais a
    sandbox e a fazenda da CowData no mesmo banco — exatamente o desenho de
    produção descrito na migração a4f8c1d92e07."""
    a = _fazenda(session, "Fazenda A")
    b = _fazenda(session, "Fazenda B")
    _fazenda(session, "Fazenda Teste", eh_teste=True)
    _fazenda(session, "CowData (empresa)", eh_empresa_cowdata=True)

    _admin(session, "admin_a", "admin.a@exemplo.com", a)
    _admin(session, "admin_b", "admin.b@exemplo.com", b)

    # Rebanhos de tamanhos diferentes: é o que prova o recorte do CONTEÚDO.
    session.add(Animal(numero="a1", sexo="F", ativo=True, fazenda_id=a))
    session.add(Animal(numero="b1", sexo="F", ativo=True, fazenda_id=b))
    session.add(Animal(numero="b2", sexo="F", ativo=True, fazenda_id=b))
    session.commit()

    _liga_envio(session, a)
    _liga_envio(session, b)
    return a, b


class TestSelecaoDeFazendas:
    def test_so_fazendas_cliente(self, engine):
        with Session(engine) as s:
            a, b = _cenario_duas_clientes(s)
            assert mf.fazendas_do_envio_semanal(s) == [a, b]

    def test_sem_multi_fazenda_provisionado_devolve_none(self, engine):
        """Tabela `fazenda` vazia = instalação de fazenda única. Só aqui
        `fazenda_id = None` quer dizer "esta instalação"."""
        with Session(engine) as s:
            assert mf.fazendas_do_envio_semanal(s) == [None]

    def test_fazenda_desativada_nao_recebe_mais(self, engine):
        """Cliente que saiu (fazenda `ativa = False`) sai do envio semanal — a
        linha continua no cadastro pelo histórico, mas o PDF não pode mais
        chegar no e-mail dele. A fazenda ativa ao lado é a contraprova de que
        o filtro novo não derrubou quem ainda é cliente."""
        with Session(engine) as s:
            ativa = _fazenda(s, "Fazenda Ativa")
            desativada = _fazenda(s, "Ex-cliente", ativa=False)
            assert mf.fazendas_do_envio_semanal(s) == [ativa]
            assert desativada not in mf.fazendas_do_envio_semanal(s)

    def test_fazenda_desativada_com_envio_ligado_nao_dispara(self, engine, envios):
        """Mesmo com o parâmetro semanal ligado e admin vinculado, a fazenda
        desativada não manda nada — é o cenário real de quem saiu no meio do
        mês com o envio ainda marcado."""
        with Session(engine) as s:
            desativada = _fazenda(s, "Ex-cliente", ativa=False)
            _admin(s, "admin_ex", "ex@exemplo.com", desativada)
            _liga_envio(s, desativada)
            assert mf.enviar_manual_semanal_todas_fazendas(s, agora=SEGUNDA_7H) == []
        assert envios == []

    def test_so_sandbox_e_cowdata_nao_sobra_ninguem(self, engine):
        """Banco provisionado mas sem nenhuma fazenda-cliente NÃO pode cair no
        comportamento global — devolve lista vazia, não [None]."""
        with Session(engine) as s:
            _fazenda(s, "Fazenda Teste", eh_teste=True)
            _fazenda(s, "CowData (empresa)", eh_empresa_cowdata=True)
            assert mf.fazendas_do_envio_semanal(s) == []


class TestDestinatarios:
    def test_admin_so_recebe_da_fazenda_a_que_esta_vinculado(self, engine):
        with Session(engine) as s:
            a, b = _cenario_duas_clientes(s)
            assert mf.emails_administradores_fazenda(s, a) == ["admin.a@exemplo.com"]
            assert mf.emails_administradores_fazenda(s, b) == ["admin.b@exemplo.com"]

    def test_admin_sem_vinculo_nenhum_nao_entra_em_fazenda_alguma(self, engine):
        """Mudança de quem recebe: um admin ativo com e-mail mas SEM linha em
        UsuarioFazenda recebia o manual antes (o ramo sem fazenda pegava todo
        admin ativo) e deixa de receber agora."""
        with Session(engine) as s:
            a, b = _cenario_duas_clientes(s)
            _admin(s, "admin_solto", "solto@exemplo.com", None)
            assert "solto@exemplo.com" not in mf.emails_administradores_fazenda(s, a)
            assert "solto@exemplo.com" not in mf.emails_administradores_fazenda(s, b)


class TestEnvioPorFazenda:
    def test_duas_fazendas_cliente_recebem_manuais_separados(self, engine, envios):
        with Session(engine) as s:
            a, b = _cenario_duas_clientes(s)
            assert mf.enviar_manual_semanal_todas_fazendas(s, agora=SEGUNDA_7H) == [a, b]

        por_destino = {destino: manual for destino, manual in envios}
        assert set(por_destino) == {"admin.a@exemplo.com", "admin.b@exemplo.com"}
        # Cada PDF com o rebanho da SUA fazenda — não a soma das duas (3).
        assert por_destino["admin.a@exemplo.com"]["resultado"]["total_animais"] == 1
        assert por_destino["admin.b@exemplo.com"]["resultado"]["total_animais"] == 2

    def test_admin_da_fazenda_a_nao_recebe_o_manual_da_b(self, engine, envios):
        with Session(engine) as s:
            a, b = _cenario_duas_clientes(s)
            # Só a B tem envio ligado nesta passada: a A não pode aparecer.
            param_a = mf.parametro_manual(s, a)
            param_a.email_semanal_ativo = False
            s.add(param_a)
            s.commit()
            assert mf.enviar_manual_semanal_todas_fazendas(s, agora=SEGUNDA_7H) == [b]

        assert [destino for destino, _ in envios] == ["admin.b@exemplo.com"]

    def test_sandbox_e_cowdata_nao_disparam_envio(self, engine, envios):
        """Sandbox e fazenda da CowData com envio ligado e admin vinculado —
        mesmo assim nada sai. E-mail para a sandbox alcançaria gente de fora."""
        with Session(engine) as s:
            sandbox = _fazenda(s, "Fazenda Teste", eh_teste=True)
            cowdata = _fazenda(s, "CowData (empresa)", eh_empresa_cowdata=True)
            _admin(s, "admin_sandbox", "sandbox@exemplo.com", sandbox)
            _admin(s, "admin_cowdata", "cowdata@exemplo.com", cowdata)
            _liga_envio(s, sandbox)
            _liga_envio(s, cowdata)
            assert mf.enviar_manual_semanal_todas_fazendas(s, agora=SEGUNDA_7H) == []
        assert envios == []

    def test_instalacao_de_fazenda_unica_continua_global(self, engine, envios):
        """Sem multi-fazenda provisionado, o comportamento de hoje é mantido:
        um envio só, para os admins ativos com e-mail."""
        with Session(engine) as s:
            _admin(s, "admin_unico", "unico@exemplo.com", None)
            s.add(Animal(numero="1", sexo="F", ativo=True))
            s.commit()
            _liga_envio(s, None)
            assert mf.enviar_manual_semanal_todas_fazendas(s, agora=SEGUNDA_7H) == [None]
        assert [destino for destino, _ in envios] == ["unico@exemplo.com"]

    def test_fora_de_segunda_de_manha_nao_envia(self, engine, envios):
        with Session(engine) as s:
            _cenario_duas_clientes(s)
            terca = SEGUNDA_7H + timedelta(days=1)
            assert mf.enviar_manual_semanal_todas_fazendas(s, agora=terca) == []
        assert envios == []

    def test_uma_fazenda_que_falha_nao_impede_as_outras(self, engine, envios, monkeypatch):
        """A fazenda A explode ANTES do try interno de
        `enviar_manual_semanal_se_necessario` (na leitura do parâmetro) — a B
        tem que sair assim mesmo."""
        with Session(engine) as s:
            a, b = _cenario_duas_clientes(s)
            original = mf.parametro_manual

            def _quebra_na_a(session, fazenda_id):
                if fazenda_id == a:
                    raise RuntimeError("falha simulada na fazenda A")
                return original(session, fazenda_id)

            monkeypatch.setattr(mf, "parametro_manual", _quebra_na_a)
            assert mf.enviar_manual_semanal_todas_fazendas(s, agora=SEGUNDA_7H) == [b]

        assert [destino for destino, _ in envios] == ["admin.b@exemplo.com"]

    def test_nao_recria_a_linha_orfa_de_parametro(self, engine, envios):
        """Com multi-fazenda provisionado, nenhuma passada do laço cria
        `parametro_manual_fazenda` com fazenda_id NULO — era o get-or-create
        sem fazenda que fazia a linha órfã reaparecer depois de apagada."""
        with Session(engine) as s:
            _cenario_duas_clientes(s)
            mf.enviar_manual_semanal_todas_fazendas(s, agora=SEGUNDA_7H)
            orfas = s.exec(
                select(ParametroManualFazenda).where(ParametroManualFazenda.fazenda_id.is_(None))
            ).all()
            assert orfas == []

    def test_nao_reenvia_na_mesma_semana(self, engine, envios):
        with Session(engine) as s:
            a, b = _cenario_duas_clientes(s)
            assert mf.enviar_manual_semanal_todas_fazendas(s, agora=SEGUNDA_7H) == [a, b]
            assert mf.enviar_manual_semanal_todas_fazendas(s, agora=SEGUNDA_7H.replace(hour=10)) == []
            # Semana seguinte volta a enviar, por fazenda.
            assert mf.enviar_manual_semanal_todas_fazendas(
                s, agora=SEGUNDA_7H + timedelta(days=7)
            ) == [a, b]
        assert len(envios) == 4
