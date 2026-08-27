"""
Bug relatado: vaca que pariu recentemente aparecia com DEL 0 e categoria
ainda "Novilha ges." na Ficha do animal e no seletor de Lançamentos >
Produção, porque `Animal.del_dias`/`categoria_completa`/`categoria_abrev` só
são atualizados no próximo upload do GERAL.csv (Ideagri) — `registrar_parto`
zera o DEL mas não corrige a categoria, e nada incrementa o DEL entre imports.

GET /animais e GET /animais/{numero}/ficha agora corrigem os dois campos AO
VIVO a partir do Parto (e Secagem) mais recente já lançado no app, igual ao
racional já usado em info_secagem/lote_criterios para o mesmo problema.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, Lactacao, Parto, Secagem


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


class TestListarAnimaisAoVivo:
    def test_vaca_recem_parida_corrige_del_e_categoria(self, client):
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            s.add(Animal(
                numero="1274", sexo="F", ativo=True, del_dias=0,
                categoria_completa="Novilha ges.", categoria_abrev="Novilha ges.",
                grupo_primario="01 - Novilhas Alta",
            ))
            s.add(Parto(numero_matriz="1274", data_parto=hoje - timedelta(days=12), ordem_parto=1))
            s.commit()

        r = c.get("/animais/", params={"ativo": True})
        assert r.status_code == 200
        animal = next(a for a in r.json() if a["numero"] == "1274")
        assert animal["del_dias"] == 12
        assert animal["categoria_completa"] == "Vaca em lactação"
        assert animal["categoria_abrev"] == "Vaca em lactação"

    def test_vaca_ja_seca_nao_conta_del_e_mostra_seca(self, client):
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            s.add(Animal(
                numero="900", sexo="F", ativo=True, del_dias=250,
                categoria_completa="Vaca lactação", categoria_abrev="Vaca lactação",
            ))
            s.add(Parto(numero_matriz="900", data_parto=hoje - timedelta(days=305), ordem_parto=3))
            s.add(Secagem(numero_matriz="900", data_secagem=hoje - timedelta(days=10), motivo="rotina"))
            s.commit()

        r = c.get("/animais/", params={"ativo": True})
        animal = next(a for a in r.json() if a["numero"] == "900")
        assert animal["del_dias"] is None
        # Categoria já dizia "vaca" — texto original preservado (não mexe).
        assert animal["categoria_completa"] == "Vaca lactação"

    def test_novilha_ainda_nao_pariu_categoria_e_del_intocados(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(
                numero="2000", sexo="F", ativo=True, del_dias=None,
                categoria_completa="Novilha", categoria_abrev="Novilha",
            ))
            s.commit()

        r = c.get("/animais/", params={"ativo": True})
        animal = next(a for a in r.json() if a["numero"] == "2000")
        assert animal["del_dias"] is None
        assert animal["categoria_completa"] == "Novilha"

    def test_novilha_aborto_sem_lactacao_nao_vira_vaca_nem_ganha_del(self, client):
        """Bug relatado: matriz 108 (novilha) abortou SEM abrir lactação e a
        tela passou a mostrá-la como "Vaca em lactação" com um DEL calculado a
        partir da data do aborto — errado nos dois campos, porque um aborto
        sem lactação não é parto produtivo (ver fazenda.rules.parto,
        eh_parto_produtivo) e não deveria influenciar nem DEL nem categoria."""
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            s.add(Animal(
                numero="108", sexo="F", ativo=True, del_dias=None,
                categoria_completa="Novilha inseminada", categoria_abrev="Nov. insem.",
            ))
            s.add(Parto(
                numero_matriz="108", data_parto=hoje - timedelta(days=5),
                tipo_parto="Aborto", abriu_lactacao=False,
            ))
            s.commit()

        r = c.get("/animais/", params={"ativo": True})
        animal = next(a for a in r.json() if a["numero"] == "108")
        assert animal["del_dias"] is None
        assert animal["categoria_completa"] == "Novilha inseminada"
        assert animal["categoria_abrev"] == "Nov. insem."

    def test_novilha_aborto_com_lactacao_vira_vaca_e_del_vem_da_lactacao(self, client):
        """Contraponto do teste acima: aborto que ABRE lactação conta como
        parto produtivo (pedido do usuário, 27/08/2026) — a categoria deve
        virar "Vaca em lactação" e o DEL sai da `Lactacao` materializada (não
        de `_del_dias_ao_vivo`/`ult_parto_produtivo`, que também serviriam,
        mas a `Lactacao` aberta tem prioridade — ver `lact is not None` em
        `listar_animais`)."""
        c, engine = client
        hoje = date.today()
        data_aborto = hoje - timedelta(days=8)
        with Session(engine) as s:
            animal = Animal(
                numero="109", sexo="F", ativo=True, del_dias=None,
                categoria_completa="Novilha inseminada", categoria_abrev="Novilha insem.",
            )
            s.add(animal)
            s.commit()
            s.refresh(animal)
            parto = Parto(
                numero_matriz="109", data_parto=data_aborto,
                tipo_parto="Aborto", abriu_lactacao=True, animal_id=animal.id,
            )
            s.add(parto)
            s.commit()
            s.refresh(parto)
            s.add(Lactacao(
                numero_matriz="109", data_inicio=data_aborto, origem="aborto",
                parto_id=parto.id, animal_id=animal.id, numero_lactacao=1,
            ))
            s.commit()

        r = c.get("/animais/", params={"ativo": True})
        animal_resp = next(a for a in r.json() if a["numero"] == "109")
        assert animal_resp["del_dias"] == 8
        assert animal_resp["categoria_completa"] == "Vaca em lactação"
        assert animal_resp["categoria_abrev"] == "Vaca em lactação"


class TestEstratificacaoRebanhoAoVivo:
    def test_novilha_aborto_sem_lactacao_fica_no_estrato_de_idade(self, client):
        """Mesmo bug da matriz 108, agora no gráfico de composição do rebanho
        (Capa/Rebanho): uma novilha cujo único `Parto` é um aborto sem
        abertura de lactação não pariu de verdade e deve continuar nos
        estratos por idade (recria/novilhas), não em vacas_*."""
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            # ~18 meses — cai em recria_12_24m se não for tratada como "vaca".
            s.add(Animal(numero="108", sexo="F", ativo=True, data_nasc=hoje - timedelta(days=550)))
            s.add(Parto(
                numero_matriz="108", data_parto=hoje - timedelta(days=5),
                tipo_parto="Aborto", abriu_lactacao=False,
            ))
            s.commit()

        r = c.get("/animais/estratificacao")
        assert r.status_code == 200
        corpo = r.json()
        assert "108" in corpo["numeros"]["recria_12_24m"]
        assert "108" not in corpo["numeros"]["vacas_lactacao"]
        assert "108" not in corpo["numeros"]["vacas_secas"]
        assert "108" not in corpo["numeros"]["vacas_pre_parto"]

    def test_novilha_aborto_com_lactacao_entra_no_estrato_de_vaca(self, client):
        """Contraponto: aborto que abre lactação É parto produtivo — deve
        classificar a matriz como vaca no gráfico, não em estrato de idade."""
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            s.add(Animal(
                numero="109", sexo="F", ativo=True, data_nasc=hoje - timedelta(days=550),
                grupo_primario="01 - Lactação Alta",
            ))
            s.add(Parto(
                numero_matriz="109", data_parto=hoje - timedelta(days=5),
                tipo_parto="Aborto", abriu_lactacao=True,
            ))
            s.commit()

        r = c.get("/animais/estratificacao")
        assert r.status_code == 200
        corpo = r.json()
        assert "109" in corpo["numeros"]["vacas_lactacao"]
        assert "109" not in corpo["numeros"]["recria_12_24m"]


class TestFichaAnimalAoVivo:
    def test_ficha_corrige_del_e_categoria_apos_parto(self, client):
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            s.add(Animal(
                numero="2074", sexo="F", ativo=True, del_dias=0,
                categoria_completa="Novilha ges.", categoria_abrev="Novilha ges.",
            ))
            s.add(Parto(numero_matriz="2074", data_parto=hoje - timedelta(days=20), ordem_parto=1))
            s.commit()

        r = c.get("/animais/2074/ficha")
        assert r.status_code == 200
        animal = r.json()["animal"]
        assert animal["del_dias"] == 20
        assert animal["categoria_abrev"] == "Vaca em lactação"

    def test_ficha_aborto_sem_lactacao_nao_corrige_del_nem_categoria(self, client):
        """Mesmo bug da matriz 108, na Ficha do animal: um aborto sem abertura
        de lactação não deve fazer `_del_dias_ao_vivo`/`_categoria_ao_vivo`
        tratarem a data do aborto como se fosse um parto de verdade."""
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            s.add(Animal(
                numero="108", sexo="F", ativo=True, del_dias=None,
                categoria_completa="Novilha inseminada", categoria_abrev="Nov. insem.",
            ))
            s.add(Parto(
                numero_matriz="108", data_parto=hoje - timedelta(days=5),
                tipo_parto="Aborto", abriu_lactacao=False,
            ))
            s.commit()

        r = c.get("/animais/108/ficha")
        assert r.status_code == 200
        corpo = r.json()
        animal = corpo["animal"]
        assert animal["del_dias"] is None
        assert animal["categoria_abrev"] == "Nov. insem."
        # Coluna nova da tabela de Partos bruta: este aborto NÃO conta.
        assert corpo["partos"][0]["conta_ordem_parto_lactacao"] is False

    def test_ficha_partos_marca_conta_ordem_parto_lactacao_por_linha(self, client):
        """Campo novo `conta_ordem_parto_lactacao` no histórico bruto de
        Partos da Ficha: True para parto normal e aborto-com-lactação, False
        para aborto sem lactação — alimenta a coluna "Considerar ordem de
        parto/lactação" da tela."""
        c, engine = client
        hoje = date.today()
        with Session(engine) as s:
            s.add(Animal(numero="777", sexo="F", ativo=True))
            s.add(Parto(numero_matriz="777", data_parto=hoje - timedelta(days=400), tipo_parto="Parto normal"))
            s.add(Parto(
                numero_matriz="777", data_parto=hoje - timedelta(days=200),
                tipo_parto="Aborto", abriu_lactacao=False,
            ))
            s.add(Parto(
                numero_matriz="777", data_parto=hoje - timedelta(days=30),
                tipo_parto="Aborto", abriu_lactacao=True,
            ))
            s.commit()

        r = c.get("/animais/777/ficha")
        assert r.status_code == 200
        partos = {p["data_parto"]: p["conta_ordem_parto_lactacao"] for p in r.json()["partos"]}
        valores = list(partos.values())
        assert valores == [True, False, True]
