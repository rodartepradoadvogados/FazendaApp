"""
Testes da ficha única do animal (GET /animais/{numero}/ficha) — reúne
absolutamente todos os lançamentos já registrados para um animal.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import (
    Animal, BaixaAnimal, ColostragemBezerra, CompraAnimal, ControleLeiteiro, EventoSanitario, ExameResultado,
    MovimentoLote, OcorrenciaClinica, Parto, PesagemCorporal,
    ProtocoloSanitario, ProtocoloSanitarioLancamento, Sanidade, Secagem, Servico, VendaAnimal,
)


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


class TestFichaAnimal:
    def test_animal_inexistente_404(self, client):
        c, engine = client
        r = c.get("/animais/999/ficha")
        assert r.status_code == 404

    def test_reune_todos_os_lancamentos_do_animal(self, client):
        c, engine = client
        with Session(engine) as s:
            animal = Animal(numero="500", sexo="F", data_nasc=date(2023, 1, 1))
            s.add(animal)
            s.commit()
            s.refresh(animal)

            s.add(Parto(animal_id=animal.id, numero_matriz="500", data_parto=date(2025, 1, 10), ordem_parto=1))
            s.add(Servico(animal_id=animal.id, numero_matriz="500", data_servico=date(2024, 4, 1), tipo_servico="IA", diagnostico="POSITIVO"))
            s.add(MovimentoLote(numero_matriz="500", lote_destino="Lote 2", data_movimento=date(2025, 1, 11)))
            s.add(ColostragemBezerra(animal_id=animal.id, numero_animal="500", brix_colostro=22.0))
            s.add(ControleLeiteiro(animal_id=animal.id, numero_matriz="500", data_controle=date(2025, 2, 1), producao_kg=25.0))
            s.add(PesagemCorporal(numero_matriz="500", data_pesagem=date(2025, 2, 1), peso_kg=450.0))
            s.add(Sanidade(numero_matriz="500", produto="Vacina X", data_aplicacao=date(2025, 1, 15)))
            s.add(Secagem(numero_matriz="500", data_secagem=date(2025, 11, 1), motivo="rotina"))
            s.add(BaixaAnimal(numero_animal="500", tipo_baixa="descarte_voluntario", motivo="venda", valor=3000.0, data_baixa=date(2026, 1, 1)))

            protocolo = ProtocoloSanitario(nome="Vermifugação padrão")
            s.add(protocolo)
            s.commit()
            s.refresh(protocolo)
            s.add(ProtocoloSanitarioLancamento(protocolo_id=protocolo.id, numero_matriz="500", data_inicio=date(2025, 3, 1)))
            s.commit()

        r = c.get("/animais/500/ficha")
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["animal"]["numero"] == "500"
        assert len(corpo["partos"]) == 1
        assert len(corpo["servicos"]) == 1
        assert len(corpo["movimentos_lote"]) == 1
        assert corpo["colostragem"]["brix_colostro"] == 22.0
        assert len(corpo["controles_leiteiros"]) == 1
        assert len(corpo["pesagens_corporais"]) == 1
        assert len(corpo["aplicacoes_sanitarias"]) == 1
        assert len(corpo["secagens"]) == 1
        assert corpo["baixa"]["valor"] == 3000.0
        assert len(corpo["protocolos_sanitarios"]) == 1
        assert corpo["protocolos_sanitarios"][0]["protocolo_nome"] == "Vermifugação padrão"

    def test_animal_sem_lancamentos_retorna_listas_vazias(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="501", sexo="F"))
            s.commit()
        r = c.get("/animais/501/ficha")
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["partos"] == []
        assert corpo["colostragem"] is None
        assert corpo["baixa"] is None
        assert corpo["compras"] == []
        assert corpo["vendas"] == []
        assert corpo["gtas"] == []
        assert corpo["ocorrencias_clinicas"] == []
        assert corpo["exames_resultados"] == []
        assert corpo["linha_tempo_sanitaria"] == []

    def test_rastreabilidade_sanitaria_reune_gtas_exames_e_doencas(self, client):
        """Um animal comprado e depois vendido (duas GTAs) com exame e doença
        registrados deve aparecer na ficha com a cadeia sanitária completa:
        GTAs, exames, doenças e a linha do tempo cronológica unificada."""
        c, engine = client
        with Session(engine) as s:
            animal = Animal(numero="600", sexo="F", data_nasc=date(2023, 1, 1))
            s.add(animal)
            s.commit()
            s.refresh(animal)

            s.add(CompraAnimal(numero_animal="600", vendedor="Fazenda Boa Vista", valor=3000.0,
                                tipo_valor="por_animal", data_compra=date(2024, 1, 10), gta="GTA-0001"))
            s.add(VendaAnimal(numero_animal="600", comprador="Frigorífico Central", valor=4000.0,
                               tipo_valor="por_animal", data_venda=date(2025, 6, 1), gta="GTA-0002"))
            s.add(OcorrenciaClinica(numero_matriz="600", doenca="Mastite", data_ocorrencia=date(2024, 5, 1)))

            evento = EventoSanitario(nome="Brucelose")
            s.add(evento)
            s.commit()
            s.refresh(evento)
            s.add(ExameResultado(numero_matriz="600", evento_sanitario_id=evento.id,
                                  data_exame=date(2024, 3, 1), resultado="negativo"))
            s.commit()

        r = c.get("/animais/600/ficha")
        assert r.status_code == 200
        corpo = r.json()

        assert len(corpo["compras"]) == 1
        assert corpo["compras"][0]["gta"] == "GTA-0001"
        assert len(corpo["vendas"]) == 1
        assert corpo["vendas"][0]["gta"] == "GTA-0002"
        assert corpo["gtas"] == ["GTA-0001", "GTA-0002"]

        assert len(corpo["ocorrencias_clinicas"]) == 1
        assert corpo["ocorrencias_clinicas"][0]["doenca"] == "Mastite"

        assert len(corpo["exames_resultados"]) == 1
        assert corpo["exames_resultados"][0]["resultado"] == "negativo"
        assert corpo["exames_resultados"][0]["evento_sanitario_nome"] == "Brucelose"

        # Linha do tempo cronológica: compra (jan/24) -> exame (mar/24) ->
        # doença (mai/24) -> venda (jun/25).
        tipos_em_ordem = [e["tipo_evento"] for e in corpo["linha_tempo_sanitaria"]]
        assert tipos_em_ordem == ["Compra", "Exame", "Doença (ocorrência clínica)", "Venda"]
        assert corpo["linha_tempo_sanitaria"][0]["gta"] == "GTA-0001"
        assert corpo["linha_tempo_sanitaria"][-1]["gta"] == "GTA-0002"

    def test_precisao_parto_com_gestacao_em_aberto(self, client):
        """Serviço com diagnóstico positivo, sem perda e sem parto posterior:
        card "Precisão de parto" preenchido — data da IA e data da confirmação
        do diagnóstico são campos DISTINTOS (a confirmação normalmente vem
        semanas depois da inseminação, num exame separado)."""
        c, engine = client
        hoje = date.today()
        data_ia = hoje - timedelta(days=100)
        data_confirmacao = data_ia + timedelta(days=35)
        with Session(engine) as s:
            animal = Animal(numero="700", sexo="F", data_nasc=date(2022, 1, 1))
            s.add(animal)
            s.commit()
            s.refresh(animal)
            s.add(Servico(
                animal_id=animal.id, numero_matriz="700", data_servico=data_ia, tipo_servico="IA",
                diagnostico="POSITIVO", data_diagnostico=data_confirmacao,
            ))
            s.commit()

        r = c.get("/animais/700/ficha")
        assert r.status_code == 200
        pp = r.json()["precisao_parto"]
        assert pp is not None
        assert pp["data_ultima_ia_positiva"] == data_ia.isoformat()
        assert pp["data_confirmacao_prenhez"] == data_confirmacao.isoformat()
        assert pp["dias_gestacao"] == 100
        assert pp["data_parto_provavel"] == (data_ia + timedelta(days=280)).isoformat()
        assert pp["dias_para_parto"] == 180

    def test_precisao_parto_ausente_sem_gestacao_em_aberto(self, client):
        """Sem serviço positivo em aberto (nenhum serviço, ou já pariu depois
        dele) — o card não deve aparecer (None), não um card vazio."""
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="701", sexo="F", data_nasc=date(2022, 1, 1)))
            s.commit()
        assert c.get("/animais/701/ficha").json()["precisao_parto"] is None

        hoje = date.today()
        with Session(engine) as s:
            animal = Animal(numero="702", sexo="F", data_nasc=date(2021, 1, 1))
            s.add(animal)
            s.commit()
            s.refresh(animal)
            data_ia = hoje - timedelta(days=300)
            s.add(Servico(animal_id=animal.id, numero_matriz="702", data_servico=data_ia, diagnostico="POSITIVO"))
            # Parto já registrado depois da IA — gestação encerrada, não "em aberto".
            s.add(Parto(animal_id=animal.id, numero_matriz="702", data_parto=data_ia + timedelta(days=280), ordem_parto=1))
            s.commit()
        assert c.get("/animais/702/ficha").json()["precisao_parto"] is None

    def test_ordem_de_parto_e_cronologica_mesmo_com_ordem_parto_gravada_errada(self, client):
        """Regressão: a vaca 403 tinha dois partos (2023 e 2025) e AMBOS
        apareciam como "1 de 2" na Ficha porque o campo `Parto.ordem_parto`
        gravado no banco (vindo de um import de CSV) estava errado/duplicado
        (1 nos dois). A ordem exibida deve vir SEMPRE da posição cronológica
        (data_parto), não do campo gravado."""
        c, engine = client
        with Session(engine) as s:
            animal = Animal(numero="403", sexo="F", data_nasc=date(2020, 1, 1))
            s.add(animal)
            s.commit()
            s.refresh(animal)
            # Ambos gravados com ordem_parto=1 (dado de origem errado/duplicado).
            s.add(Parto(animal_id=animal.id, numero_matriz="403", data_parto=date(2023, 3, 10), ordem_parto=1))
            s.add(Parto(animal_id=animal.id, numero_matriz="403", data_parto=date(2025, 4, 20), ordem_parto=1))
            s.commit()

        corpo = c.get("/animais/403/ficha").json()
        assert len(corpo["partos"]) == 2
        partos_por_data = {p["data_parto"]: p["ordem_parto"] for p in corpo["partos"]}
        assert partos_por_data["2023-03-10"] == "1 de 2"
        assert partos_por_data["2025-04-20"] == "2 de 2"

    def test_coluna_parto_do_servico_so_aparece_com_diagnostico_positivo_e_parto_ja_ocorrido(self, client):
        """Cada serviço de IA/diagnóstico deve trazer a data do parto que ele
        originou (`parto_resultante_data`) apenas quando o diagnóstico foi
        POSITIVO e esse parto já aconteceu; senão vem None (o frontend decide
        entre "—" e vazio a partir do campo `diagnostico`)."""
        c, engine = client
        with Session(engine) as s:
            animal = Animal(numero="800", sexo="F", data_nasc=date(2020, 1, 1))
            s.add(animal)
            s.commit()
            s.refresh(animal)
            # 1ª IA: negativa — não deveria ter parto associado.
            s.add(Servico(animal_id=animal.id, numero_matriz="800", data_servico=date(2024, 1, 1),
                           tipo_servico="IA", diagnostico="NEGATIVO"))
            # 2ª IA: positiva e já pariu — deve trazer a data do parto.
            s.add(Servico(animal_id=animal.id, numero_matriz="800", data_servico=date(2024, 3, 1),
                           tipo_servico="IA", diagnostico="POSITIVO"))
            s.add(Parto(animal_id=animal.id, numero_matriz="800", data_parto=date(2024, 12, 15), ordem_parto=1))
            # 3ª IA (depois do parto): positiva mas ainda não pariu de novo.
            s.add(Servico(animal_id=animal.id, numero_matriz="800", data_servico=date(2025, 3, 1),
                           tipo_servico="IA", diagnostico="POSITIVO"))
            s.commit()

        corpo = c.get("/animais/800/ficha").json()
        servicos_por_data = {sv["data_servico"]: sv for sv in corpo["servicos"]}
        assert servicos_por_data["2024-01-01"]["parto_resultante_data"] is None
        assert servicos_por_data["2024-03-01"]["diagnostico"] == "POSITIVO"
        assert servicos_por_data["2024-03-01"]["parto_resultante_data"] == "2024-12-15"
        assert servicos_por_data["2025-03-01"]["diagnostico"] == "POSITIVO"
        assert servicos_por_data["2025-03-01"]["parto_resultante_data"] is None

    def test_mae_vem_do_parto_quando_nao_cadastrada_manualmente(self, client):
        """Regressão: a mãe deve aparecer na ficha mesmo quando ninguém
        preencheu `Animal.mae_numero` manualmente, desde que exista um Parto
        que lista este animal como cria de uma matriz."""
        c, engine = client
        with Session(engine) as s:
            mae = Animal(numero="900", nome="Estrela", sexo="F", data_nasc=date(2018, 1, 1))
            s.add(mae)
            cria = Animal(numero="901", sexo="F", data_nasc=date(2023, 1, 10))
            s.add(cria)
            s.commit()
            s.refresh(mae)
            s.refresh(cria)
            s.add(Parto(animal_id=mae.id, numero_matriz="900", data_parto=date(2023, 1, 10),
                         ordem_parto=1, numero_cria_1="901"))
            s.commit()

        corpo = c.get("/animais/901/ficha").json()
        assert corpo["animal"]["mae_numero"] == "900"
        assert corpo["animal"]["mae_nome"] == "Estrela"

    def test_mae_cadastrada_manualmente_tem_prioridade_sobre_o_parto(self, client):
        c, engine = client
        with Session(engine) as s:
            mae_parto = Animal(numero="910", nome="Mae do parto", sexo="F", data_nasc=date(2018, 1, 1))
            s.add(mae_parto)
            cria = Animal(numero="911", sexo="F", data_nasc=date(2023, 1, 10), mae_numero="999", mae_nome="Mãe manual")
            s.add(cria)
            s.commit()
            s.refresh(mae_parto)
            s.refresh(cria)
            s.add(Parto(animal_id=mae_parto.id, numero_matriz="910", data_parto=date(2023, 1, 10),
                         ordem_parto=1, numero_cria_1="911"))
            s.commit()

        corpo = c.get("/animais/911/ficha").json()
        assert corpo["animal"]["mae_numero"] == "999"
        assert corpo["animal"]["mae_nome"] == "Mãe manual"


def test_estratificacao_rebanho():
    from datetime import date, timedelta
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine
    import fazenda.database as database
    from fazenda.models import Animal, Parto, Servico
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    def _ov():
        with Session(engine) as s: yield s
    import main
    from fazenda.auth import get_current_user
    main.app.dependency_overrides[database.get_session] = _ov
    class U: id=1; papel="admin"; ativo=True; username="t"
    main.app.dependency_overrides[get_current_user] = lambda: U()
    hoje = date.today()
    with TestClient(main.app) as c:
        with Session(engine) as s:
            s.add(Animal(numero="1", data_nasc=hoje - timedelta(days=30), ativo=True, sexo="F"))   # aleitamento
            s.add(Animal(numero="2", data_nasc=hoje - timedelta(days=200), ativo=True, sexo="F"))  # recria 4-11m
            s.add(Animal(numero="3", data_nasc=hoje - timedelta(days=500), ativo=True, sexo="F"))  # recria 12-24m
            s.add(Animal(numero="4", data_nasc=hoje - timedelta(days=800), ativo=True, sexo="F"))  # novilha >24m
            s.add(Animal(numero="5", data_nasc=hoje - timedelta(days=1500), ativo=True, sexo="F", grupo_primario="01 Lact"))  # vaca lactação
            s.add(Parto(numero_matriz="5", data_parto=hoje - timedelta(days=100), ordem_parto=1))
            s.commit()
        j = c.get("/animais/estratificacao").json()
        assert j["total"] == 5
        assert j["estratos"]["aleitamento_0_3m"] == 1
        assert j["estratos"]["recria_4_11m"] == 1
        assert j["estratos"]["recria_12_24m"] == 1
        assert j["estratos"]["novilhas_acima_24m"] == 1
        assert j["estratos"]["vacas_lactacao"] == 1
        assert j["pct_lactacao_sobre_total"] == 20.0
    main.app.dependency_overrides.clear()
