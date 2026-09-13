"""
Testes de regressão dos achados P1 (crítica/alta) da auditoria de segurança
de 02/09/2026 — confirma que uma fazenda-cliente não consegue mais ler,
confirmar, encerrar ou apagar dados de outra fazenda por meio dos bugs de
isolamento corrigidos em agenda.py, producao.py, alimentacao.py, importar.py,
exclusoes.py e cobranca.py. Ver docs/security-audit/achados.json.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, ContratoFazenda, ContratoFazendaModulo, Fazenda, ParametroFazenda, Parto, Sanidade, Servico,
)
from fazenda.models.alimentacao import DietaLancamento
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.models.reprodutivo import ProtocoloIatfAplicacao, ProtocoloIatfLancamento


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda A"))
        s.add(Fazenda(id=2, nome="Fazenda B"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))

        # Protocolo IATF da fazenda A, com D0/dia coincidindo com o que a
        # fazenda B vai tentar confirmar (D0/D7/D9/D11 são fixos no sistema —
        # colisão de (data_prevista, dia) entre tenants é o cenário real).
        lanc_a = ProtocoloIatfLancamento(nome_protocolo="Ovsynch", data_d0=date(2026, 6, 1))
        s.add(lanc_a)
        s.commit()
        s.refresh(lanc_a)
        s.add(ProtocoloIatfAplicacao(
            lancamento_id=lanc_a.id, numero_matriz="A100", dia=0, descricao="D0",
            data_prevista=date(2026, 6, 1), realizada=False, fazenda_id=1,
        ))

        # Parâmetro de intervalo de BST específico da fazenda A.
        s.add(ParametroFazenda(chave="intervalo_bst", fazenda_id=None, valor="12", tipo="int", grupo="bst", label="Intervalo BST"))

        # Dieta ativa da fazenda A.
        s.add(DietaLancamento(fazenda_id=1, lote=1, data_abertura=date(2026, 6, 1)))

        # `animal.numero` é único no banco inteiro (constraint real, não só
        # regra de aplicação) — duas fazendas nunca têm um Animal "9006" AO
        # MESMO TEMPO. O cenário real e reprodutível é outro: a fazenda A tem
        # registros HISTÓRICOS (Servico/Parto/Sanidade, sem FK pra Animal,
        # só numero_matriz em texto) de um animal "9006" que ela já
        # renumerou/baixou — o número ficou livre — e a fazenda B cadastra um
        # animal novo com esse mesmo número "9006". Sem o filtro de
        # fazenda_id, excluir o animal "9006" da fazenda B apagava também o
        # histórico da fazenda A.
        s.add(Servico(numero_matriz="9006", data_servico=date(2026, 5, 1), tipo="IA", fazenda_id=1))
        s.add(Parto(numero_matriz="9006", data_parto=date(2026, 5, 2), fazenda_id=1))
        s.add(Sanidade(numero_matriz="9006", data_aplicacao=date(2026, 5, 3), produto="Vacina X", fazenda_id=1))
        an_b = Animal(numero="9006", ativo=True, fazenda_id=2)
        s.add(an_b)
        # Animal "7001" pertence de verdade à fazenda A — usado pra provar
        # que a fazenda B não consegue sobrescrever/tomar posse dele via
        # importação de planilha só por saber o número.
        s.add(Animal(numero="7001", nome="Original da Fazenda A", ativo=True, fazenda_id=1))
        s.commit()

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
        email = "admin@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestAgendaProtocoloIatfIsolado:
    def test_fazenda_b_nao_confirma_protocolo_iatf_da_fazenda_a(self, client):
        c, engine = client
        _como_fazenda(2)
        r = c.post("/agenda/realizados", json={"evento_id": "protocolo_iatf_2026-06-01_0"})
        assert r.status_code == 200
        with Session(engine) as s:
            ap = s.exec(select(ProtocoloIatfAplicacao)).first()
            assert ap.realizada is False, "fazenda B não pode confirmar aplicação da fazenda A"

    def test_fazenda_b_nao_ve_protocolo_iatf_concluido_da_fazenda_a(self, client):
        c, engine = client
        with Session(engine) as s:
            ap = s.exec(select(ProtocoloIatfAplicacao)).first()
            ap.realizada = True
            ap.data_realizacao = date(2026, 6, 1)
            s.add(ap)
            s.commit()
        _como_fazenda(2)
        r = c.get("/agenda/protocolo-iatf/concluidos")
        assert r.status_code == 200
        assert r.json() == []

    def test_fazenda_a_continua_confirmando_seu_proprio_protocolo(self, client):
        c, engine = client
        _como_fazenda(1)
        r = c.post("/agenda/realizados", json={"evento_id": "protocolo_iatf_2026-06-01_0"})
        assert r.status_code == 200
        with Session(engine) as s:
            ap = s.exec(select(ProtocoloIatfAplicacao)).first()
            assert ap.realizada is True


class TestBstAjustarProximaAplicacaoIsolado:
    def test_fazenda_b_ajuste_nao_atinge_sanidade_da_fazenda_a(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Sanidade(numero_matriz="9006", data_aplicacao=date(2026, 5, 1), produto="Lactotropin", atividade="BST", fazenda_id=1))
            s.commit()
        _como_fazenda(2)
        r = c.post("/producao/bst/ajustar-proxima-aplicacao", json={"nova_data": "2026-07-01", "modo": "intervalo"})
        # Sem nenhuma aplicação de BST NA FAZENDA B, o cálculo deve recusar —
        # não pode "enxergar" a aplicação da fazenda A para calcular em cima dela.
        assert r.status_code == 400

    def test_ajuste_da_fazenda_a_nao_sobrescreve_padrao_global_para_fazenda_b(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Sanidade(numero_matriz="9006", data_aplicacao=date(2026, 5, 1), produto="Lactotropin", atividade="BST", fazenda_id=1))
            s.commit()
        _como_fazenda(1)
        r = c.post("/producao/bst/ajustar-proxima-aplicacao", json={"nova_data": "2026-07-01", "modo": "intervalo"})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            linhas = s.exec(select(ParametroFazenda).where(ParametroFazenda.chave == "intervalo_bst")).all()
            globais = [l for l in linhas if l.fazenda_id is None]
            da_fazenda_a = [l for l in linhas if l.fazenda_id == 1]
            assert len(da_fazenda_a) == 1, "deve clonar uma linha específica da fazenda A, não editar a global"
            assert globais[0].valor == "12", "o padrão global (visto por todas as outras fazendas) não pode mudar"


class TestDietaIsolada:
    def test_fazenda_b_nao_encerra_dieta_da_fazenda_a(self, client):
        c, engine = client
        with Session(engine) as s:
            dieta_id = s.exec(select(DietaLancamento)).first().id
        _como_fazenda(2)
        r = c.put(f"/alimentacao/dietas/{dieta_id}/encerrar", json={"data_efetivo_encerramento": "2026-06-10"})
        assert r.status_code == 404
        with Session(engine) as s:
            assert s.get(DietaLancamento, dieta_id).data_efetivo_encerramento is None

    def test_fazenda_a_encerra_sua_propria_dieta(self, client):
        c, engine = client
        with Session(engine) as s:
            dieta_id = s.exec(select(DietaLancamento)).first().id
        _como_fazenda(1)
        r = c.put(f"/alimentacao/dietas/{dieta_id}/encerrar", json={"data_efetivo_encerramento": "2026-06-10"})
        assert r.status_code == 200, r.text


class TestExclusaoAnimalIsolada:
    def test_excluir_animal_9006_da_fazenda_b_nao_apaga_historico_da_fazenda_a(self, client):
        c, engine = client
        _como_fazenda(2)
        r = c.post("/exclusoes/confirmar", json={"tipo": "animal", "id": "9006"})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            # O animal "9006" da fazenda B foi de fato excluído...
            assert s.exec(select(Animal).where(Animal.fazenda_id == 2)).first() is None
            # ...mas o histórico da fazenda A (mesmo numero_matriz "9006",
            # sem Animal correspondente) continua intacto.
            assert s.exec(select(Servico).where(Servico.fazenda_id == 1)).first() is not None
            assert s.exec(select(Parto).where(Parto.fazenda_id == 1)).first() is not None
            assert s.exec(select(Sanidade).where(Sanidade.fazenda_id == 1)).first() is not None


class TestImportarAnimaisCadastroIsolado:
    def test_numero_coincidente_com_outra_fazenda_nao_sobrescreve(self, client):
        c, engine = client
        _como_fazenda(2)
        csv = "numero,nome\n7001,Sobrescrita Maliciosa\n"
        r = c.post(
            "/importar/animais_cadastro",
            files={"file": ("animais.csv", csv.encode("utf-8"), "text/csv")},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["criados"] == 0
        assert body["atualizados"] == 0
        assert len(body["erros"]) == 1
        with Session(engine) as s:
            animal_a = s.exec(select(Animal).where(Animal.numero == "7001")).first()
            assert animal_a.fazenda_id == 1
            assert animal_a.nome != "Sobrescrita Maliciosa"


class TestPortalExportacaoIsolada:
    def test_executar_exportacao_filtra_por_fazenda(self, client):
        c, engine = client
        from fazenda.api.routers.portal import _executar_exportacao

        # Serviço da PRÓPRIA fazenda B, criado aqui e não na fixture (que é
        # compartilhada por todos os testes deste arquivo): é o controle
        # positivo do assert lá embaixo.
        with Session(engine) as s:
            s.add(Servico(numero_matriz="7001", data_servico=date(2026, 5, 4), tipo="IA", fazenda_id=2))
            s.commit()

        capturado = {}

        def _fake_enviar_email(destinatario, assunto, corpo, anexo_nome, anexo_bytes):
            capturado["zip_bytes"] = anexo_bytes

        import fazenda.api.routers.portal as portal_mod
        original = portal_mod.enviar_email
        # O engine TAMBÉM precisa ser trocado AQUI, no módulo portal, e não só
        # em `fazenda.database` (o que a fixture faz). `portal.py` importa
        # `from fazenda.database import engine` no topo, então guarda a
        # REFERÊNCIA do engine global do import — `monkeypatch.setattr(
        # database, "engine", ...)` reaponta o nome em `fazenda.database` e
        # não encosta na cópia que o portal já tem. `_executar_exportacao`
        # roda fora do ciclo de request (BackgroundTask com sessão própria),
        # então não passa por `Depends(get_session)` e é essa cópia que ele usa.
        #
        # Sem esta linha o teste era falso nos DOIS sentidos, e as duas formas
        # já aconteceram:
        #  - rodando sozinho, a exportação lia o banco global VAZIO; o ZIP saía
        #    sem linha nenhuma e o `"9006" not in conteudo` passava por
        #    ausência de dado, não por isolamento — verde sem testar nada;
        #  - rodando junto com os outros arquivos, esse mesmo banco global já
        #    tinha sido populado por outro teste, o "9006" aparecia e a falha
        #    apontava para um furo de isolamento que não existe (a consulta de
        #    `_executar_exportacao` filtra por fazenda incondicionalmente).
        original_engine = portal_mod.engine
        portal_mod.engine = engine
        portal_mod.enviar_email = _fake_enviar_email
        try:
            _executar_exportacao([{"chave": "reprodutivo_servicos"}], "destino@example.com", 2)
        finally:
            portal_mod.enviar_email = original
            portal_mod.engine = original_engine

        import io
        import zipfile
        zf = zipfile.ZipFile(io.BytesIO(capturado["zip_bytes"]))
        conteudo = zf.read("reprodutivo_servicos.csv").decode("utf-8-sig")
        assert "9006" not in conteudo, "exportação da fazenda B não pode conter o serviço da fazenda A"
        # CONTROLE POSITIVO: sem ele, uma exportação que devolvesse SEMPRE um
        # CSV vazio passaria neste teste — foi exatamente assim que ele passou
        # durante todo o tempo em que lia o banco errado (ver o comentário do
        # engine acima). A fazenda B tem que continuar exportando o que é dela.
        assert "7001" in conteudo, (
            "a exportação da fazenda B perdeu o próprio serviço dela — filtrar não é bloquear tudo"
        )


class TestWebhookBbExigeSegredo:
    def test_webhook_sem_segredo_configurado_e_rejeitado(self, client):
        c, engine = client
        from fazenda.config import settings
        settings.bb_client_id = "algum-client-id"
        settings.bb_webhook_secret = ""
        try:
            r = c.post("/cobranca/webhook/bb/qualquer-coisa", json={"txid": "abc"})
            assert r.status_code == 403
        finally:
            settings.bb_client_id = ""

    def test_webhook_com_segredo_errado_e_rejeitado(self, client):
        c, engine = client
        from fazenda.config import settings
        settings.bb_client_id = "algum-client-id"
        settings.bb_webhook_secret = "segredo-correto"
        try:
            r = c.post("/cobranca/webhook/bb/segredo-errado", json={"txid": "abc"})
            assert r.status_code == 403
        finally:
            settings.bb_client_id = ""
            settings.bb_webhook_secret = ""

    def test_webhook_com_segredo_correto_e_aceito(self, client):
        c, engine = client
        from fazenda.config import settings
        settings.bb_client_id = "algum-client-id"
        settings.bb_webhook_secret = "segredo-correto"
        try:
            r = c.post("/cobranca/webhook/bb/segredo-correto", json={"txid": "abc"})
            assert r.status_code == 200
        finally:
            settings.bb_client_id = ""
            settings.bb_webhook_secret = ""
