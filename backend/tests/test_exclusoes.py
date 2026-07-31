"""
Testes do router de exclusões: prévia de impacto e exclusão em cascata.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal,
    CalendarioSanitario,
    ContaGerencial,
    ControleLeiteiro,
    Doenca,
    Estoque,
    EstoqueSemen,
    EventoSanitario,
    FolhaPagamento,
    Fornecedor,
    Lote,
    MotivoMovimentacao,
    MovimentoEstoque,
    Parto,
    Pessoa,
    PrincipioAtivo,
    ProtocoloSanitario,
    ProtocoloSanitarioAplicacao,
    ProtocoloSanitarioEtapa,
    ProtocoloSanitarioLancamento,
    Sanidade,
    Servico,
    SolicitacaoExclusao,
)


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    # Admin fake: sobrescreve as dependências de autenticação usadas pelo router.
    from fazenda.auth import exigir_admin, get_current_user

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    main.app.dependency_overrides[exigir_admin] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _sessao(engine) -> Session:
    return Session(engine)


class TestExclusaoAnimal:
    def test_impacto_lista_registros_relacionados(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Animal(numero="123", ativo=True))
            s.add(Servico(numero_matriz="123", data_servico=date(2026, 1, 1)))
            s.add(Parto(numero_matriz="123", data_parto=date(2026, 2, 1)))
            s.add(ControleLeiteiro(numero_matriz="123", data_controle=date(2026, 3, 1)))
            s.add(Sanidade(numero_matriz="123", produto="Vacina X", data_aplicacao=date(2026, 1, 5)))
            s.commit()

        r = c.post("/exclusoes/impacto", json={"tipo": "animal", "id": "123"})
        assert r.status_code == 200
        impacto = r.json()["impacto"]
        assert any("Ficha do animal 123" in i for i in impacto)
        assert any("1 serviço" in i for i in impacto)
        assert any("1 parto" in i for i in impacto)
        assert any("1 registro" in i for i in impacto)
        assert any("1 aplicação" in i for i in impacto)

    def test_confirmar_apaga_animal_e_relacionados(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Animal(numero="999", ativo=True))
            s.add(Servico(numero_matriz="999", data_servico=date(2026, 1, 1)))
            s.commit()

        r = c.post("/exclusoes/confirmar", json={"tipo": "animal", "id": "999"})
        assert r.status_code == 200
        assert r.json()["status"] == "excluido"

        with _sessao(engine) as s:
            from sqlmodel import select
            assert s.exec(select(Animal).where(Animal.numero == "999")).first() is None
            assert s.exec(select(Servico).where(Servico.numero_matriz == "999")).first() is None

    def test_animal_inexistente_da_404(self, client):
        c, _ = client
        r = c.post("/exclusoes/impacto", json={"tipo": "animal", "id": "nope"})
        assert r.status_code == 404


class TestExclusaoFinanceiro:
    def test_impacto_de_parcela_lista_todas_as_irmas(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(ContaGerencial(numero_lancamento="LC-2026-00001", parcela_num=1, parcela_total=2, valor_total=100, descricao="Sal mineral"))
            s.add(ContaGerencial(numero_lancamento="LC-2026-00001", parcela_num=2, parcela_total=2, valor_total=100, descricao="Sal mineral"))
            s.commit()
            ids = [row.id for row in s.exec(__import__("sqlmodel").select(ContaGerencial)).all()]

        r = c.post("/exclusoes/impacto", json={"tipo": "financeiro", "id": str(ids[0])})
        assert r.status_code == 200
        impacto = r.json()["impacto"]
        assert any("2 parcela" in i for i in impacto)

    def test_confirmar_apaga_todas_as_parcelas(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(ContaGerencial(numero_lancamento="LC-2026-00002", parcela_num=1, parcela_total=2, valor_total=50))
            s.add(ContaGerencial(numero_lancamento="LC-2026-00002", parcela_num=2, parcela_total=2, valor_total=50))
            s.commit()
            ids = [row.id for row in s.exec(__import__("sqlmodel").select(ContaGerencial)).all()]

        r = c.post("/exclusoes/confirmar", json={"tipo": "financeiro", "id": str(ids[0])})
        assert r.status_code == 200

        with _sessao(engine) as s:
            from sqlmodel import select
            restantes = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == "LC-2026-00002")).all()
            assert restantes == []

    def test_confirmar_lancamento_sem_parcela_apaga_so_ele(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(ContaGerencial(numero_lancamento="LC-2026-00003", parcela_num=1, parcela_total=1, valor_total=300))
            s.commit()
            id_ = s.exec(__import__("sqlmodel").select(ContaGerencial)).first().id

        r = c.post("/exclusoes/confirmar", json={"tipo": "financeiro", "id": str(id_)})
        assert r.status_code == 200
        assert r.json()["status"] == "excluido"


class TestBusca:
    def test_buscar_animal_filtra_por_termo(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Animal(numero="111", ativo=True))
            s.add(Animal(numero="222", ativo=True))
            s.commit()

        r = c.get("/exclusoes/buscar", params={"tipo": "animal", "termo": "111"})
        assert r.status_code == 200
        resultados = r.json()
        assert len(resultados) == 1
        assert resultados[0]["id"] == "111"

    def test_tipo_invalido_da_400(self, client):
        c, _ = client
        r = c.get("/exclusoes/buscar", params={"tipo": "invalido"})
        assert r.status_code == 400


class TestBuscaComFiltroDeData:
    def test_filtra_servico_por_periodo(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Servico(numero_matriz="111", data_servico=date(2026, 1, 10)))
            s.add(Servico(numero_matriz="222", data_servico=date(2026, 3, 10)))
            s.commit()

        r = c.get("/exclusoes/buscar", params={"tipo": "servico", "data_inicio": "2026-02-01", "data_fim": "2026-04-01"})
        assert r.status_code == 200
        numeros = {row["titulo"].split(" — ")[0] for row in r.json()}
        assert numeros == {"222"}

    def test_sem_filtro_de_data_traz_tudo(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Servico(numero_matriz="111", data_servico=date(2026, 1, 10)))
            s.add(Servico(numero_matriz="222", data_servico=date(2026, 3, 10)))
            s.commit()

        r = c.get("/exclusoes/buscar", params={"tipo": "servico"})
        assert len(r.json()) == 2

    def test_registro_sem_data_some_quando_ha_filtro_de_periodo(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Servico(numero_matriz="333", data_servico=None))
            s.commit()

        r = c.get("/exclusoes/buscar", params={"tipo": "servico", "data_inicio": "2026-01-01", "data_fim": "2026-12-31"})
        assert r.json() == []

    def test_tipo_estoque_ignora_filtro_de_data(self, client):
        c, engine = client
        from fazenda.models import Estoque
        with _sessao(engine) as s:
            s.add(Estoque(nome="Ração"))
            s.commit()

        r = c.get("/exclusoes/buscar", params={"tipo": "estoque", "data_inicio": "2026-01-01", "data_fim": "2026-12-31"})
        assert len(r.json()) == 1


class TestFormatoDeDataNoTitulo:
    """O título mostrado na lista (campo 'Registro') usa dd/mm/aaaa com barra,
    não o formato ISO com hífen que o backend usava antes."""

    def test_titulo_do_servico_usa_barra_em_vez_de_hifen(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Servico(numero_matriz="111", data_servico=date(2026, 3, 5)))
            s.commit()

        r = c.get("/exclusoes/buscar", params={"tipo": "servico"})
        titulo = r.json()[0]["titulo"]
        assert titulo == "111 — 05/03/2026"
        assert "2026-03-05" not in titulo

    def test_titulo_do_evento_manual_usa_barra(self, client):
        c, engine = client
        from fazenda.models import AgendaManual
        with _sessao(engine) as s:
            s.add(AgendaManual(data_evento=date(2026, 6, 15), descricao="Visita técnica", categoria="outro"))
            s.commit()

        r = c.get("/exclusoes/buscar", params={"tipo": "evento_manual"})
        titulo = r.json()[0]["titulo"]
        assert titulo.startswith("15/06/2026")
        assert "2026-06-15" not in titulo


class TestNovosTiposDeCadastro:
    def test_exclui_lote_sem_bloqueio(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Lote(codigo="09", nome="Teste"))
            s.commit()
        lote_id = c.get("/exclusoes/buscar", params={"tipo": "lote", "termo": "Teste"}).json()[0]["id"]
        r = c.post("/exclusoes/confirmar", json={"tipo": "lote", "id": str(lote_id)})
        assert r.status_code == 200
        assert r.json()["status"] == "excluido"
        with _sessao(engine) as s:
            assert s.get(Lote, lote_id) is None

    def test_exclui_fornecedor_e_desvincula_estoque(self, client):
        c, engine = client
        with _sessao(engine) as s:
            f = Fornecedor(nome="Casa da Ração", tipo="fornecedor")
            s.add(f)
            s.commit()
            s.refresh(f)
            s.add(Estoque(nome="Ração X", fornecedor_id=f.id))
            s.commit()
            fid = f.id

        r = c.post("/exclusoes/impacto", json={"tipo": "fornecedor", "id": str(fid)})
        assert any("1 item" in i for i in r.json()["impacto"])

        r2 = c.post("/exclusoes/confirmar", json={"tipo": "fornecedor", "id": str(fid)})
        assert r2.status_code == 200
        with _sessao(engine) as s:
            assert s.get(Fornecedor, fid) is None
            item = s.exec(select(Estoque).where(Estoque.nome == "Ração X")).first()
            assert item.fornecedor_id is None

    def test_exclui_motivo_movimentacao(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(MotivoMovimentacao(nome="Reagrupamento teste"))
            s.commit()
        mid = c.get("/exclusoes/buscar", params={"tipo": "motivo_movimentacao", "termo": "Reagrupamento"}).json()[0]["id"]
        r = c.post("/exclusoes/confirmar", json={"tipo": "motivo_movimentacao", "id": str(mid)})
        assert r.status_code == 200

    def test_bloqueia_exclusao_de_pessoa_com_folha(self, client):
        c, engine = client
        with _sessao(engine) as s:
            p = Pessoa(nome="Carlos Vet", tipo="Veterinário")
            s.add(p)
            s.commit()
            s.refresh(p)
            s.add(FolhaPagamento(pessoa_id=p.id, competencia="2026-07", valor_bruto=1000, valor_liquido=1000))
            s.commit()
            pid = p.id

        r = c.post("/exclusoes/confirmar", json={"tipo": "pessoa", "id": str(pid)})
        assert r.status_code == 400

    def test_exclui_pessoa_sem_vinculos(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Pessoa(nome="Sem vínculo", tipo="Diarista"))
            s.commit()
        pid = c.get("/exclusoes/buscar", params={"tipo": "pessoa", "termo": "Sem vínculo"}).json()[0]["id"]
        r = c.post("/exclusoes/confirmar", json={"tipo": "pessoa", "id": str(pid)})
        assert r.status_code == 200

    def test_exclui_principio_ativo_e_desvincula_calendario(self, client):
        c, engine = client
        with _sessao(engine) as s:
            pa = PrincipioAtivo(nome="Ivermectina")
            s.add(pa)
            s.commit()
            s.refresh(pa)
            s.add(EventoSanitario(nome="Vermífugo teste"))
            s.commit()
            evento = s.exec(select(EventoSanitario).where(EventoSanitario.nome == "Vermífugo teste")).first()
            s.add(CalendarioSanitario(
                evento_sanitario_id=evento.id, principio_ativo_id=pa.id,
                frequencia_valor=4, frequencia_unidade="meses", data_evento=date(2026, 1, 1),
            ))
            s.commit()
            pa_id = pa.id

        r = c.post("/exclusoes/confirmar", json={"tipo": "principio_ativo", "id": str(pa_id)})
        assert r.status_code == 200
        with _sessao(engine) as s:
            regra = s.exec(select(CalendarioSanitario)).first()
            assert regra.principio_ativo_id is None

    def test_bloqueia_exclusao_de_evento_sanitario_com_calendario(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(EventoSanitario(nome="Brucelose teste"))
            s.commit()
            evento = s.exec(select(EventoSanitario).where(EventoSanitario.nome == "Brucelose teste")).first()
            s.add(CalendarioSanitario(
                evento_sanitario_id=evento.id, frequencia_valor=12, frequencia_unidade="meses", data_evento=date(2026, 1, 1),
            ))
            s.commit()
            eid = evento.id

        r = c.post("/exclusoes/confirmar", json={"tipo": "evento_sanitario", "id": str(eid)})
        assert r.status_code == 400

    def test_bloqueia_exclusao_de_protocolo_com_lancamento(self, client):
        c, engine = client
        with _sessao(engine) as s:
            protocolo = ProtocoloSanitario(nome="Mastite teste")
            s.add(protocolo)
            s.commit()
            s.refresh(protocolo)
            s.add(ProtocoloSanitarioEtapa(protocolo_id=protocolo.id, dia=1, produto="X", dosagem=1.0, unidade="ml"))
            s.add(ProtocoloSanitarioLancamento(protocolo_id=protocolo.id, numero_matriz="700", data_inicio=date(2026, 1, 1)))
            s.commit()
            pid = protocolo.id

        r = c.post("/exclusoes/confirmar", json={"tipo": "protocolo_sanitario", "id": str(pid)})
        assert r.status_code == 400

    def test_exclui_protocolo_sem_lancamento_cascade_etapas(self, client):
        c, engine = client
        with _sessao(engine) as s:
            protocolo = ProtocoloSanitario(nome="Vermifugação teste")
            s.add(protocolo)
            s.commit()
            s.refresh(protocolo)
            s.add(ProtocoloSanitarioEtapa(protocolo_id=protocolo.id, dia=1, produto="X", dosagem=1.0, unidade="ml"))
            s.commit()
            pid = protocolo.id

        r = c.post("/exclusoes/confirmar", json={"tipo": "protocolo_sanitario", "id": str(pid)})
        assert r.status_code == 200
        with _sessao(engine) as s:
            assert s.get(ProtocoloSanitario, pid) is None
            assert s.exec(select(ProtocoloSanitarioEtapa).where(ProtocoloSanitarioEtapa.protocolo_id == pid)).first() is None

    def test_tipos_exclusao_incluem_novos(self, client):
        c, engine = client
        r = c.get("/exclusoes/tipos")
        ids = {t["id"] for t in r.json()}
        assert {"lote", "fornecedor", "motivo_movimentacao", "pessoa", "principio_ativo", "doenca", "evento_sanitario", "protocolo_sanitario"} <= ids


class TestFluxoAprovacaoOperador:
    """Operador (não-admin) não apaga nada direto — POST /confirmar só cria uma
    SolicitacaoExclusao pendente. Só um admin, via /pendentes/{id}/aprovar ou
    /rejeitar, decide se a exclusão é executada de fato ou descartada. Este é
    o caminho não coberto pelos demais testes do arquivo, que sempre fakeiam
    um usuário admin (e por isso caem direto no ramo "excluido" do /confirmar)."""

    def _solicitar_como_operador(self, c, tipo: str, id_: str):
        """Chama POST /exclusoes/confirmar fazendo o get_current_user devolver
        um operador (papel != admin) só durante esta chamada — restaura a
        sobreposição de admin da fixture logo em seguida, já que /pendentes,
        /aprovar e /rejeitar (via exigir_admin) continuam exigindo o admin."""
        import main
        from fazenda.auth import get_current_user

        class _FakeOperador:
            id = 2
            papel = "operador"
            ativo = True
            username = "operador1"

        anterior = main.app.dependency_overrides[get_current_user]
        main.app.dependency_overrides[get_current_user] = lambda: _FakeOperador()
        try:
            return c.post("/exclusoes/confirmar", json={"tipo": tipo, "id": id_})
        finally:
            main.app.dependency_overrides[get_current_user] = anterior

    def test_operador_solicita_em_vez_de_apagar_na_hora(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(MotivoMovimentacao(nome="Motivo do operador"))
            s.commit()
        mid = c.get("/exclusoes/buscar", params={"tipo": "motivo_movimentacao", "termo": "Motivo do operador"}).json()[0]["id"]

        r = self._solicitar_como_operador(c, "motivo_movimentacao", str(mid))
        assert r.status_code == 200
        assert r.json()["status"] == "solicitado"

        with _sessao(engine) as s:
            sol = s.exec(select(SolicitacaoExclusao)).first()
            assert sol is not None
            assert sol.status == "pendente"
            assert sol.tipo == "motivo_movimentacao"
            assert sol.id_alvo == str(mid)
            assert sol.solicitado_por == "operador1"
            # Nada foi apagado ainda — só o pedido foi registrado.
            assert s.get(MotivoMovimentacao, mid) is not None

    def test_admin_lista_pendentes_criados_pelo_operador(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(MotivoMovimentacao(nome="Pendente teste"))
            s.commit()
        mid = c.get("/exclusoes/buscar", params={"tipo": "motivo_movimentacao", "termo": "Pendente teste"}).json()[0]["id"]
        self._solicitar_como_operador(c, "motivo_movimentacao", str(mid))

        r = c.get("/exclusoes/pendentes")
        assert r.status_code == 200
        pendentes = r.json()
        assert any(
            p["id_alvo"] == str(mid) and p["status"] == "pendente" and p["solicitado_por"] == "operador1"
            for p in pendentes
        )

    def test_admin_aprova_solicitacao_executa_a_exclusao_de_fato(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(MotivoMovimentacao(nome="Aprovar teste"))
            s.commit()
        mid = c.get("/exclusoes/buscar", params={"tipo": "motivo_movimentacao", "termo": "Aprovar teste"}).json()[0]["id"]
        self._solicitar_como_operador(c, "motivo_movimentacao", str(mid))
        with _sessao(engine) as s:
            sol_id = s.exec(select(SolicitacaoExclusao)).first().id

        r = c.post(f"/exclusoes/pendentes/{sol_id}/aprovar")
        assert r.status_code == 200
        assert r.json()["aprovado"] is True

        with _sessao(engine) as s:
            assert s.get(MotivoMovimentacao, mid) is None  # realmente apagado
            sol = s.get(SolicitacaoExclusao, sol_id)
            assert sol.status == "aprovada"
            assert sol.decidido_por == "teste"
            assert sol.decidido_em is not None

    def test_admin_rejeita_solicitacao_nao_apaga_nada(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(MotivoMovimentacao(nome="Rejeitar teste"))
            s.commit()
        mid = c.get("/exclusoes/buscar", params={"tipo": "motivo_movimentacao", "termo": "Rejeitar teste"}).json()[0]["id"]
        self._solicitar_como_operador(c, "motivo_movimentacao", str(mid))
        with _sessao(engine) as s:
            sol_id = s.exec(select(SolicitacaoExclusao)).first().id

        r = c.post(f"/exclusoes/pendentes/{sol_id}/rejeitar", json={"motivo": "Não procede"})
        assert r.status_code == 200
        assert r.json()["rejeitado"] is True

        with _sessao(engine) as s:
            assert s.get(MotivoMovimentacao, mid) is not None  # nada foi apagado
            sol = s.get(SolicitacaoExclusao, sol_id)
            assert sol.status == "rejeitada"
            assert sol.motivo_rejeicao == "Não procede"
            assert sol.decidido_por == "teste"

        # Some da lista de pendentes depois de decidida.
        pendentes = c.get("/exclusoes/pendentes").json()
        assert not any(p["id"] == sol_id for p in pendentes)

    def test_aprovar_solicitacao_ja_decidida_da_404(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(MotivoMovimentacao(nome="Ja decidida"))
            s.commit()
        mid = c.get("/exclusoes/buscar", params={"tipo": "motivo_movimentacao", "termo": "Ja decidida"}).json()[0]["id"]
        self._solicitar_como_operador(c, "motivo_movimentacao", str(mid))
        with _sessao(engine) as s:
            sol_id = s.exec(select(SolicitacaoExclusao)).first().id

        r_rejeita = c.post(f"/exclusoes/pendentes/{sol_id}/rejeitar", json={})
        assert r_rejeita.status_code == 200

        r = c.post(f"/exclusoes/pendentes/{sol_id}/aprovar")
        assert r.status_code == 404
        with _sessao(engine) as s:
            # Continua rejeitada — a segunda decisão não altera nada.
            assert s.get(SolicitacaoExclusao, sol_id).status == "rejeitada"
            assert s.get(MotivoMovimentacao, mid) is not None

    def test_rejeitar_solicitacao_inexistente_da_404(self, client):
        c, _ = client
        r = c.post("/exclusoes/pendentes/9999/rejeitar", json={})
        assert r.status_code == 404


class TestEstornoDeEstoqueNaExclusao:
    """A exclusão (fluxo admin de /exclusoes/confirmar) apagava o registro que
    deu baixa em estoque sem nunca devolver nada — o estoque ficava "fantasma
    a menos". Estes testes provam que a exclusão agora estorna, usando os
    fluxos reais de baixa (protocolo sanitário, protocolo IATF, inseminação e
    aplicação avulsa de Sanidade) em vez de fabricar MovimentoEstoque na mão."""

    def _etapa(self, dia=1, produto="Vacina X", dosagem=10.0, unidade="ml"):
        return {"dia": dia, "produto": produto, "dosagem": dosagem, "unidade": unidade, "via": "Intramuscular"}

    def test_exclui_protocolo_sanitario_lancamento_devolve_estoque(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Estoque(nome="Vacina X", quantidade=100.0, unidade="ml"))
            s.commit()

        protocolo_id = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Protocolo teste", "etapas": [self._etapa()],
        }).json()["id"]
        lanc = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": protocolo_id, "numeros_matriz": ["700"], "data_inicio": "2026-01-01",
        }).json()
        lancamento_id = lanc["lancamentos"][0]["id"]

        eventos = c.get("/agenda/", params={"data": "2025-12-01", "dias": 60}).json()["eventos"]
        alvo = next(e for e in eventos if e["id"].startswith("protocolo_sanitario_"))
        c.post("/agenda/realizados", json={"evento_id": alvo["id"]})

        with _sessao(engine) as s:
            assert s.exec(select(Estoque).where(Estoque.nome == "Vacina X")).first().quantidade == 90.0
            assert s.exec(select(ProtocoloSanitarioAplicacao)).first().realizada is True

        r = c.post("/exclusoes/confirmar", json={"tipo": "protocolo_sanitario_lancamento", "id": str(lancamento_id)})
        assert r.status_code == 200, r.text
        assert r.json()["avisos"] == []

        with _sessao(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Vacina X")).first()
            assert item.quantidade == 100.0
            assert s.exec(select(ProtocoloSanitarioLancamento)).first() is None
            assert s.exec(select(ProtocoloSanitarioAplicacao)).first() is None
            assert s.exec(select(Sanidade)).first() is None
            # Não duplo-estorna: uma baixa (10ml) revertida uma única vez —
            # não duas (o mirror de Sanidade também estava na lista de alvos).
            estornos = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.movimento == "Entrada de ajuste")).all()
            assert len(estornos) == 1
            assert estornos[0].quantidade == 10.0

    def test_exclui_protocolo_iatf_lancamento_devolve_hormonio(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Estoque(nome="SincroCP", quantidade=100.0, unidade="ml"))
            s.commit()

        r_lanc = c.post("/reproducao/protocolo-iatf", json={
            "animais": ["700"], "data_d0": "2026-07-08", "protocolo": "IATF teste",
            "hormonios": [{"dia": 0, "produto": "SincroCP", "dose": 1, "unidade": "ml", "via": "Intramuscular"}],
        })
        lancamento_id = r_lanc.json()["lancamento_id"]

        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)
        c.post("/agenda/realizados", json={"evento_id": d0["id"]})

        with _sessao(engine) as s:
            assert s.exec(select(Estoque).where(Estoque.nome == "SincroCP")).first().quantidade == 99.0

        r = c.post("/exclusoes/confirmar", json={"tipo": "protocolo_iatf_lancamento", "id": str(lancamento_id)})
        assert r.status_code == 200, r.text
        assert r.json()["avisos"] == []

        with _sessao(engine) as s:
            assert s.exec(select(Estoque).where(Estoque.nome == "SincroCP")).first().quantidade == 100.0

    def test_exclui_servico_devolve_dose_de_semen(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Animal(numero="700", ativo=True))
            s.add(EstoqueSemen(touro_nome="Coors", tipo="convencional", doses=30))
            s.commit()

        r = c.post("/reproducao/servico", json={
            "numero_matriz": "700", "data_servico": "2026-07-08", "tipo_servico": "IA", "reprodutor": "Coors",
        })
        assert r.status_code == 200, r.text
        servico_id = r.json()["id"]

        with _sessao(engine) as s:
            assert s.exec(select(EstoqueSemen).where(EstoqueSemen.touro_nome == "Coors")).first().doses == 29

        r2 = c.post("/exclusoes/confirmar", json={"tipo": "servico", "id": str(servico_id)})
        assert r2.status_code == 200, r2.text
        assert r2.json()["avisos"] == []

        with _sessao(engine) as s:
            assert s.exec(select(EstoqueSemen).where(EstoqueSemen.touro_nome == "Coors")).first().doses == 30
            assert s.exec(select(Servico).where(Servico.id == servico_id)).first() is None

    def test_exclui_sanidade_direto_pelo_painel_de_exclusoes_devolve_estoque(self, client):
        """Bypass fechado: antes, só o DELETE /sanidade/aplicacoes/{id} estornava —
        excluir a mesma Sanidade pelo painel de Exclusões (/exclusoes/confirmar)
        apagava sem devolver nada ao estoque."""
        c, engine = client
        with _sessao(engine) as s:
            s.add(Estoque(nome="Antibiótico avulso", quantidade=50.0, unidade="ml"))
            s.commit()

        r = c.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-01-01", "animais": ["700"],
            "itens": [{"produto": "Antibiótico avulso", "quantidade": 10.0, "unidade": "ml"}],
        })
        assert r.status_code == 200, r.text
        sanidade_id = r.json()["sanidade_ids"][0]

        with _sessao(engine) as s:
            assert s.exec(select(Estoque).where(Estoque.nome == "Antibiótico avulso")).first().quantidade == 40.0

        r2 = c.post("/exclusoes/confirmar", json={"tipo": "sanidade", "id": str(sanidade_id)})
        assert r2.status_code == 200, r2.text
        assert r2.json()["avisos"] == []

        with _sessao(engine) as s:
            assert s.exec(select(Estoque).where(Estoque.nome == "Antibiótico avulso")).first().quantidade == 50.0
            assert s.get(Sanidade, sanidade_id) is None

    def test_exclui_registro_sem_baixa_nao_quebra_nem_gera_aviso(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Sanidade(numero_matriz="700", produto="Produto nunca cadastrado no estoque", data_aplicacao=date(2026, 1, 1)))
            s.commit()
            sanidade_id = s.exec(select(Sanidade)).first().id

        r = c.post("/exclusoes/confirmar", json={"tipo": "sanidade", "id": str(sanidade_id)})
        assert r.status_code == 200
        assert r.json()["avisos"] == []
        with _sessao(engine) as s:
            assert s.get(Sanidade, sanidade_id) is None
