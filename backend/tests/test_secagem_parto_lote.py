"""
Testes de: lançamento de Secagem, sugestão automática de lote em eventos de
vida (nascimento/parto/secagem) e o novo endpoint real de Parto/nascimento.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, AplicacaoAgendada, Estoque, Lote, MovimentoEstoque, Parto, Sanidade, Secagem, Servico
from fazenda.api.routers.movimentacoes import seed_motivos_movimentacao


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
        with Session(engine) as s:
            seed_motivos_movimentacao(s)
        yield c, engine

    main.app.dependency_overrides.clear()


class TestSecagemInfo:
    def test_calcula_data_prevista_e_sugere_lote_das_secas(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="500", raca="Girolando", del_dias=220, grupo_primario="02 - Alta", ativo=True))
            s.add(Servico(numero_matriz="500", data_servico=date(2026, 1, 1), diagnostico="POSITIVO", ordem_parto=2))
            s.add(Lote(codigo="05", nome="SECAS", status_lactacao="seca"))
            s.commit()

        r = c.get("/producao/secagem-info", params={"numero_matriz": "500"})
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["del_atual"] == 220
        assert corpo["deve_secar"] is True
        assert corpo["lote_sugerido"] == {"codigo": "05", "nome": "SECAS", "rotulo": "05 - SECAS"}
        # Girolando = 287 dias de gestação; secagem = parto provável - 60 dias
        assert corpo["data_prevista_secagem"] == "2026-08-16"

    def test_novilha_1a_cria_nao_deve_secar(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="501", raca="Girolando", del_dias=100, ativo=True))
            s.add(Servico(numero_matriz="501", data_servico=date(2026, 1, 1), diagnostico="POSITIVO", ordem_parto=0))
            s.commit()

        r = c.get("/producao/secagem-info", params={"numero_matriz": "501"})
        assert r.json()["deve_secar"] is False

    def test_animal_inexistente_da_404(self, client):
        c, _ = client
        r = c.get("/producao/secagem-info", params={"numero_matriz": "nao-existe"})
        assert r.status_code == 404


class TestLoteDasSecasMotorDeCriterios:
    """`_lote_das_secas` passou a usar o motor real de critérios (`animal_atende_
    criterios`), em vez de só filtrar `status_lactacao == "seca"` e pegar o
    primeiro sem `order_by` — cobre desempate entre 2+ lotes concorrentes,
    `excluir_da_sugestao` e o filtro de lote ativo."""

    def test_dois_lotes_de_seca_concorrentes_escolhe_o_de_del_min_mais_proximo(self, client):
        c, engine = client
        with Session(engine) as s:
            # Vaca com 245 dias pós-parto (Parto real). Dois lotes de seca
            # concorrentes, ambos elegíveis pelo del_min/max — o desempate
            # escolhe o lote cujo del_min mais se aproxima do DEL atual do
            # animal (04: |200-245|=45; 05: |240-245|=5 -> vence o 05).
            s.add(Animal(numero="510", raca="Girolando", ativo=True))
            s.add(Parto(numero_matriz="510", data_parto=date.today() - timedelta(days=245)))
            s.add(Lote(codigo="04", nome="Secas recentes", status_lactacao="seca", del_min=200, del_max=300))
            s.add(Lote(codigo="05", nome="Secas longas", status_lactacao="seca", del_min=240, del_max=300))
            s.commit()

        r = c.get("/producao/secagem-info", params={"numero_matriz": "510"})
        assert r.status_code == 200
        assert r.json()["lote_sugerido"]["codigo"] == "05"

    def test_excluir_da_sugestao_tira_o_lote_de_seca_da_disputa(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="511", raca="Girolando", ativo=True))
            s.add(Lote(codigo="04", nome="Enfermaria", status_lactacao="seca", excluir_da_sugestao=True))
            s.commit()

        r = c.get("/producao/secagem-info", params={"numero_matriz": "511"})
        assert r.status_code == 200
        assert r.json()["lote_sugerido"] is None

    def test_lote_de_seca_inativo_nunca_e_sugerido(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="512", raca="Girolando", ativo=True))
            s.add(Lote(codigo="04", nome="Secas (desativado)", status_lactacao="seca", ativo=False))
            s.commit()

        r = c.get("/producao/secagem-info", params={"numero_matriz": "512"})
        assert r.status_code == 200
        assert r.json()["lote_sugerido"] is None


class TestRegistrarSecagem:
    def test_cria_registro_produtos_e_baixa_estoque(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="500", raca="Girolando", del_dias=220, ativo=True))
            s.add(Estoque(nome="Tetradelta", quantidade=20, unidade="dose"))
            s.add(Lote(codigo="05", nome="SECAS", status_lactacao="seca"))
            s.commit()

        r = c.post("/producao/secagem", json={
            "numero_matriz": "500", "data_secagem": "2026-07-08", "motivo": "rotina",
            "escore_condicao_corporal": 3.25,
            "produtos": [{"produto": "Tetradelta", "quantidade": 4, "unidade": "dose"}],
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["criado"] is True
        assert corpo["lote_sugerido"]["codigo"] == "05"

        with Session(engine) as s:
            from sqlmodel import select
            sec = s.exec(select(Secagem).where(Secagem.numero_matriz == "500")).first()
            assert sec.motivo == "rotina"
            assert sec.escore_condicao_corporal == 3.25
            aplicacao = s.exec(select(Sanidade).where(Sanidade.numero_matriz == "500")).first()
            assert aplicacao.produto == "Tetradelta"
            assert aplicacao.atividade == "Secagem"
            item = s.exec(select(Estoque).where(Estoque.nome == "Tetradelta")).first()
            assert item.quantidade == 16

    def test_data_futura_programa_produto_sem_baixar_estoque(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Tetradelta", quantidade=20, unidade="dose"))
            s.commit()

        futuro = (date.today() + timedelta(days=10)).isoformat()
        r = c.post("/producao/secagem", json={
            "numero_matriz": "500", "data_secagem": futuro, "motivo": "rotina",
            "produtos": [{"produto": "Tetradelta", "quantidade": 4, "unidade": "dose"}],
        })
        assert r.status_code == 200
        assert r.json()["programado"] is True

        with Session(engine) as s:
            from sqlmodel import select
            # Estoque intacto e nada de Sanidade — só uma aplicação programada.
            assert s.exec(select(Estoque).where(Estoque.nome == "Tetradelta")).first().quantidade == 20
            assert s.exec(select(Sanidade).where(Sanidade.numero_matriz == "500")).first() is None
            prog = s.exec(select(AplicacaoAgendada).where(AplicacaoAgendada.numero_matriz == "500")).first()
            assert prog is not None and prog.produto == "Tetradelta" and prog.aplicado is False

    def test_nao_aplicado_programa_mesmo_com_data_de_hoje(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Tetradelta", quantidade=20, unidade="dose"))
            s.commit()
        r = c.post("/producao/secagem", json={
            "numero_matriz": "500", "data_secagem": date.today().isoformat(), "motivo": "rotina", "aplicado": False,
            "produtos": [{"produto": "Tetradelta", "quantidade": 4, "unidade": "dose"}],
        })
        assert r.status_code == 200 and r.json()["programado"] is True
        with Session(engine) as s:
            from sqlmodel import select
            assert s.exec(select(Estoque).where(Estoque.nome == "Tetradelta")).first().quantidade == 20

    def test_motivo_invalido_da_400(self, client):
        c, _ = client
        r = c.post("/producao/secagem", json={"numero_matriz": "500", "data_secagem": "2026-07-08", "motivo": "invalido"})
        assert r.status_code == 400

    def test_ecc_fora_da_faixa_da_400(self, client):
        c, _ = client
        r = c.post("/producao/secagem", json={
            "numero_matriz": "500", "data_secagem": "2026-07-08", "motivo": "rotina", "escore_condicao_corporal": 6,
        })
        assert r.status_code == 400

    def test_baixa_do_medicamento_grava_movimento_de_estoque(self, client):
        # Antes, o medicamento de secagem baixava Estoque.quantidade sem gravar
        # MovimentoEstoque nenhum (ver auditoria em fazenda.rules.estoque_baixa).
        c, engine = client
        with Session(engine) as s:
            from sqlmodel import select
            s.add(Animal(numero="500", raca="Girolando", del_dias=220, ativo=True))
            s.add(Estoque(nome="Tetradelta", quantidade=20, unidade="dose"))
            s.commit()

        r = c.post("/producao/secagem", json={
            "numero_matriz": "500", "data_secagem": "2026-07-08", "motivo": "rotina",
            "produtos": [{"produto": "Tetradelta", "quantidade": 4, "unidade": "dose"}],
        })
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            from sqlmodel import select
            item = s.exec(select(Estoque).where(Estoque.nome == "Tetradelta")).first()
            mov = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.nome_item == "Tetradelta")).first()
            assert mov is not None
            assert mov.quantidade == 4
            assert mov.estoque_id == item.id
            assert mov.origem_tipo == "secagem"


class TestVacinaPreParto:
    """Mesmo evento (vacina pré-parto), dois caminhos de confirmação — pela
    Secagem (vacina_pre_parto_aplicada_agora=True) ou depois pela Agenda
    (POST /agenda/realizados). Antes, só o caminho da Secagem baixava o
    estoque; o da Agenda só marcava a pendência como feita (ver auditoria)."""

    def test_aplicada_na_hora_pela_secagem_baixa_estoque(self, client):
        c, engine = client
        with Session(engine) as s:
            from sqlmodel import select
            s.add(Animal(numero="500", raca="Girolando", del_dias=220, ativo=True))
            s.add(Estoque(nome="Bovilis", quantidade=10, unidade="dose"))
            s.commit()

        r = c.post("/producao/secagem", json={
            "numero_matriz": "500", "data_secagem": "2026-07-08", "motivo": "rotina",
            "vacinas_pre_parto": ["Bovilis"], "vacina_pre_parto_aplicada_agora": True,
        })
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            from sqlmodel import select
            item = s.exec(select(Estoque).where(Estoque.nome == "Bovilis")).first()
            assert item.quantidade == 9
            mov = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.nome_item == "Bovilis")).first()
            assert mov is not None
            assert mov.origem_tipo == "vacina_pre_parto"
            assert mov.estoque_id == item.id

    def test_confirmada_depois_pela_agenda_tambem_baixa_estoque(self, client):
        # Regressão do bug mais grave da auditoria: confirmar pela Agenda tinha
        # que baixar igual ao caminho da Secagem — antes não baixava nada.
        c, engine = client
        with Session(engine) as s:
            from sqlmodel import select
            s.add(Animal(numero="500", raca="Girolando", del_dias=220, ativo=True))
            s.add(Estoque(nome="Bovilis", quantidade=10, unidade="dose"))
            s.commit()

        c.post("/producao/secagem", json={
            "numero_matriz": "500", "data_secagem": "2026-07-08", "motivo": "rotina",
            "vacinas_pre_parto": ["Bovilis"], "vacina_pre_parto_aplicada_agora": False,
        })
        data_vacina = date(2026, 7, 8) + timedelta(days=1)
        evento_id = f"vacina_pre_parto_500_{data_vacina.isoformat()}"

        r = c.post("/agenda/realizados", json={"evento_id": evento_id})
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            from sqlmodel import select
            item = s.exec(select(Estoque).where(Estoque.nome == "Bovilis")).first()
            assert item.quantidade == 9  # baixou igual ao caminho da Secagem
            sanidade = s.exec(select(Sanidade).where(Sanidade.numero_matriz == "500", Sanidade.produto == "Bovilis")).first()
            assert sanidade is not None
            mov = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.nome_item == "Bovilis")).first()
            assert mov is not None
            assert mov.origem_tipo == "vacina_pre_parto"


class TestSugestaoLoteEvento:
    def test_sugere_lote_de_bezerras_ao_nascer(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Lote(codigo="01", nome="BEZ 1 (0 A 30)", categorias="bezerra,bezerro", idade_dias_max=30))
            s.add(Lote(codigo="03", nome="Média", categorias="vaca", del_min=61, del_max=200))
            s.commit()

        r = c.post("/producao/sugestao-lote-evento", json={
            "numero_matriz": "600", "categoria_abrev": "Bezerra", "data_nasc": "2026-07-08",
        })
        assert r.status_code == 200
        assert r.json()["lote_sugerido"]["codigo"] == "01"

    def test_sugere_lote_de_vaca_parida(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Lote(codigo="01", nome="BEZ 1 (0 A 30)", categorias="bezerra,bezerro", idade_dias_max=30))
            s.add(Lote(codigo="03", nome="Média", categorias="vaca", del_min=0, del_max=10))
            s.commit()

        r = c.post("/producao/sugestao-lote-evento", json={
            "numero_matriz": "500", "categoria_abrev": "Vaca", "del_dias": 0,
        })
        assert r.status_code == 200
        assert r.json()["lote_sugerido"]["codigo"] == "03"

    def test_sem_lote_configurado_retorna_nulo(self, client):
        c, _ = client
        r = c.post("/producao/sugestao-lote-evento", json={"numero_matriz": "700", "categoria_abrev": "Vaca"})
        assert r.json()["lote_sugerido"] is None

    def test_lote_inativo_nunca_e_sugerido_no_evento(self, client):
        c, engine = client
        with Session(engine) as s:
            # Único lote que bateria no critério está desativado — não pode
            # ser sugerido; sem outro candidato, a resposta é nula.
            s.add(Lote(codigo="01", nome="BEZ 1 (0 A 30)", categorias="bezerra,bezerro", idade_dias_max=30, ativo=False))
            s.commit()

        r = c.post("/producao/sugestao-lote-evento", json={
            "numero_matriz": "601", "categoria_abrev": "Bezerra", "data_nasc": "2026-07-08",
        })
        assert r.status_code == 200
        assert r.json()["lote_sugerido"] is None


class TestRegistrarParto:
    def test_cria_parto_e_crias_novas(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="500", raca="Girolando", del_dias=283, ativo=True))
            s.commit()

        r = c.post("/reproducao/parto", json={
            "numero_matriz": "500", "data_parto": "2026-07-08", "tipo_parto": "Normal",
            "crias": [{"numero": "601", "sexo": "F", "nasceu_viva": True}],
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["ordem_parto"] == 1
        assert corpo["crias_criadas"] == ["601"]

        with Session(engine) as s:
            from sqlmodel import select
            parto = s.exec(select(Parto).where(Parto.numero_matriz == "500")).first()
            assert parto.sexo_cria_1 == "F"
            assert parto.ordem_parto == 1
            cria = s.exec(select(Animal).where(Animal.numero == "601")).first()
            assert cria.mae_numero == "500"
            assert cria.raca == "Girolando"
            mae = s.exec(select(Animal).where(Animal.numero == "500")).first()
            assert mae.del_dias == 0

    def test_incrementa_ordem_parto_em_partos_subsequentes(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="500", raca="Girolando", ativo=True))
            s.add(Parto(numero_matriz="500", data_parto=date(2024, 1, 1), ordem_parto=1))
            s.commit()

        r = c.post("/reproducao/parto", json={"numero_matriz": "500", "data_parto": "2026-07-08", "crias": []})
        assert r.json()["ordem_parto"] == 2

    def test_cria_ja_cadastrada_nao_e_duplicada(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="500", raca="Girolando", ativo=True))
            s.add(Animal(numero="601", raca="Girolando", ativo=True))
            s.commit()

        r = c.post("/reproducao/parto", json={
            "numero_matriz": "500", "data_parto": "2026-07-08",
            "crias": [{"numero": "601", "sexo": "F"}],
        })
        assert r.json()["crias_criadas"] == []

        with Session(engine) as s:
            from sqlmodel import select
            animais = s.exec(select(Animal).where(Animal.numero == "601")).all()
            assert len(animais) == 1

    def test_matriz_inexistente_da_404(self, client):
        c, _ = client
        r = c.post("/reproducao/parto", json={"numero_matriz": "nao-existe", "data_parto": "2026-07-08", "crias": []})
        assert r.status_code == 404


class TestMotivosDeMovimentacaoIncluemSecagemENascimento:
    def test_secagem_e_nascimento_sao_motivos_validos(self, client):
        c, _ = client
        motivos = c.get("/movimentacoes/motivos").json()
        assert "Secagem" in motivos
        assert "Nascimento" in motivos


class TestProtocoloIatf:
    def test_agenda_quatro_eventos_por_animal(self, client):
        c, engine = client
        r = c.post("/reproducao/protocolo-iatf", json={
            "animais": ["500", "501"], "data_d0": "2026-07-08", "protocolo": "Protocolo padrão",
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["eventos_criados"] == 8
        assert corpo["animais"] == 2
        assert corpo["lancamento_id"]

        with Session(engine) as s:
            from sqlmodel import select
            from fazenda.models import ProtocoloIatfAplicacao
            eventos = s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == "500")).all()
            assert len(eventos) == 4
            datas = sorted(e.data_prevista for e in eventos)
            assert datas == [date(2026, 7, 8), date(2026, 7, 15), date(2026, 7, 17), date(2026, 7, 19)]
            assert all(e.realizada is False for e in eventos)

    def test_sem_animais_da_400(self, client):
        c, _ = client
        r = c.post("/reproducao/protocolo-iatf", json={"animais": [], "data_d0": "2026-07-08"})
        assert r.status_code == 400

    def test_lista_protocolos_ativos_mostra_etapa_atual(self, client):
        # D0 lançado hoje — "próxima etapa" ainda é D0 (o hormônio de hoje
        # ainda não foi confirmado), não pula direto para D7.
        c, engine = client
        c.post("/reproducao/protocolo-iatf", json={
            "animais": ["500"], "data_d0": date.today().isoformat(), "protocolo": "Protocolo padrão",
        })
        r = c.get("/reproducao/protocolo-iatf/ativos")
        assert r.status_code == 200
        ativos = r.json()
        assert len(ativos) == 1
        assert ativos[0]["nome_protocolo"] == "Protocolo padrão"
        assert ativos[0]["animais"][0]["numero_matriz"] == "500"
        assert ativos[0]["animais"][0]["etapa_atual"] == "D0"

    def test_lista_protocolos_ativos_etapa_avanca_por_data(self, client):
        # #reformular relatório gerencial de IATF atual: a "próxima etapa" é
        # calculada pela data de hoje em relação ao calendário do protocolo,
        # não por qual etapa foi manualmente marcada "realizada" — nenhuma
        # das 4 aplicações é marcada aqui, só a passagem do tempo já avança
        # D0 -> D7 -> D9 -> D11.
        c, engine = client
        d0 = date.today() - timedelta(days=8)  # D7 (dia+7) já ficou no passado
        c.post("/reproducao/protocolo-iatf", json={"animais": ["500"], "data_d0": d0.isoformat()})
        ativos = c.get("/reproducao/protocolo-iatf/ativos").json()
        assert len(ativos) == 1
        assert ativos[0]["concluido"] is False
        assert ativos[0]["animais"][0]["etapa_atual"] == "D9"
        assert ativos[0]["animais"][0]["data_etapa_atual"] == (d0 + timedelta(days=9)).isoformat()

    def test_protocolo_com_d11_no_passado_e_sem_baixa_vira_concluido(self, client):
        # #reformular relatório gerencial de IATF atual: um protocolo cujo
        # D11 já passou, mas ninguém marcou nenhuma etapa "realizada" (ex.:
        # a inseminação foi feita mas o checkbox nunca confirmado), não pode
        # ficar mostrando "D0" pra sempre no card IATF atual — some da lista
        # ativa e migra para "concluido" (última IATF), como se tivesse sido
        # baixado normalmente.
        c, engine = client
        d0 = date.today() - timedelta(days=30)
        c.post("/reproducao/protocolo-iatf", json={"animais": ["500"], "data_d0": d0.isoformat()})
        ativos = c.get("/reproducao/protocolo-iatf/ativos").json()
        assert len(ativos) == 1
        assert ativos[0]["concluido"] is True
        assert ativos[0]["animais"][0]["etapa_atual"] == "Concluído"
        assert ativos[0]["data_d11"] == (d0 + timedelta(days=11)).isoformat()

    def test_protocolo_concluido_mostra_proxima_visita_e_candidatas(self, client):
        # #369: ao concluir tudo (D11 com baixa), o protocolo não some da
        # lista — passa a aparecer com concluido=True, mostrando a data do
        # próximo serviço (D11 + intervalo_visita_reprodutiva, padrão 21
        # dias) e as candidatas herd-wide ao próximo repasse.
        c, engine = client
        c.post("/reproducao/protocolo-iatf", json={
            "animais": ["500"], "data_d0": "2026-07-08", "protocolo": "Protocolo padrão",
        })
        with Session(engine) as s:
            from sqlmodel import select
            from fazenda.models import ProtocoloIatfAplicacao
            for ap in s.exec(select(ProtocoloIatfAplicacao)).all():
                ap.realizada = True
                if ap.dia == 11:
                    ap.data_realizacao = date(2026, 7, 19)
                s.add(ap)
            s.commit()
        r = c.get("/reproducao/protocolo-iatf/ativos")
        ativos = r.json()
        assert len(ativos) == 1
        item = ativos[0]
        assert item["concluido"] is True
        assert item["data_d11"] == "2026-07-19"
        assert item["proxima_visita"] == "2026-08-09"
        assert "candidatas_proxima_visita" in item
        # #440: mesmo concluído, a lista de animais do protocolo continua
        # populada (para a Agenda poder mostrar "ÚLTIMA IATF — y animais"
        # com clique para ver quem foi inseminado nesse grupo).
        assert item["animais"] == [{"numero_matriz": "500", "etapa_atual": "Concluído", "data_etapa_atual": None, "d0_confirmado": True}]


class TestRegistrarServico:
    def test_cria_servico_cio_natural(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="500", raca="Girolando", del_dias=80, ativo=True))
            s.commit()

        r = c.post("/reproducao/servico", json={
            "numero_matriz": "500", "data_servico": "2026-07-08", "tipo_servico": "Monta natural", "reprodutor": "Touro X",
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["protocolo"] is None
        assert corpo["ordem_tentativa"] == 1
        assert corpo["ult_ocorrencia"] == 1
        assert corpo["reprodutor"] == "Touro X"

    def test_cria_servico_de_protocolo_iatf(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="500", raca="Girolando", ativo=True))
            s.commit()

        r = c.post("/reproducao/servico", json={
            "numero_matriz": "500", "data_servico": "2026-07-19", "tipo_servico": "IA", "protocolo": "Protocolo padrão",
        })
        assert r.json()["protocolo"] == "Protocolo padrão"

    def test_registrar_servico_resolve_aplicacao_d11_automaticamente(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="500", raca="Girolando", ativo=True))
            s.commit()
        c.post("/reproducao/protocolo-iatf", json={
            "animais": ["500"], "data_d0": "2026-07-08", "protocolo": "Protocolo padrão",
        })

        c.post("/reproducao/servico", json={
            "numero_matriz": "500", "data_servico": "2026-07-19", "tipo_servico": "IA", "protocolo": "Protocolo padrão",
        })

        with Session(engine) as s:
            from sqlmodel import select
            from fazenda.models import ProtocoloIatfAplicacao
            d11 = s.exec(
                select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == "500", ProtocoloIatfAplicacao.dia == 11)
            ).first()
            assert d11.realizada is True
            assert d11.data_realizacao == date(2026, 7, 19)
            # As demais etapas (D0/D7/D9) continuam intactas — só o D11 resolve.
            outras = s.exec(
                select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == "500", ProtocoloIatfAplicacao.dia != 11)
            ).all()
            assert all(not a.realizada for a in outras)

    def test_segundo_servico_incrementa_tentativa_e_desmarca_anterior(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="500", raca="Girolando", ativo=True))
            s.commit()

        c.post("/reproducao/servico", json={"numero_matriz": "500", "data_servico": "2026-06-01"})
        r2 = c.post("/reproducao/servico", json={"numero_matriz": "500", "data_servico": "2026-07-08"})
        assert r2.json()["ordem_tentativa"] == 2
        assert r2.json()["intervalo_tentativas"] == 37

        with Session(engine) as s:
            from sqlmodel import select
            servicos = s.exec(select(Servico).where(Servico.numero_matriz == "500")).all()
            assert len(servicos) == 2
            ativos = [sv for sv in servicos if sv.ult_ocorrencia == 1]
            assert len(ativos) == 1
            assert ativos[0].data_servico == date(2026, 7, 8)

    def test_matriz_inexistente_da_404(self, client):
        c, _ = client
        r = c.post("/reproducao/servico", json={"numero_matriz": "nao-existe", "data_servico": "2026-07-08"})
        assert r.status_code == 404
