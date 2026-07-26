"""
Testes da sugestão automática de movimentação entre lotes — usa os critérios
já cadastrados por lote (Configurações > Cadastro > Lotes), sem pedir nenhum
parâmetro novo ao usuário.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, CategoriaManejo, Lote, Parto, Secagem


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


class TestSugestoes:
    def test_animal_fora_do_lote_certo_gera_sugestao(self, client):
        c, engine = client
        with Session(engine) as s:
            # Lote 02 exige peso >= 300kg. Vaca "100" está no lote 01 (sem
            # critério) mas pesa 350kg — deveria ser sugerida para o lote 02.
            s.add(Lote(codigo="01", nome="Recém-chegadas"))
            s.add(Lote(codigo="02", nome="Aptas", peso_min=300))
            s.add(Animal(numero="100", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Recém-chegadas", ativo=True))
            s.commit()

        with Session(engine) as s:
            from fazenda.models import PesagemCorporal
            from datetime import date
            s.add(PesagemCorporal(numero_matriz="100", data_pesagem=date.today(), peso_kg=350))
            s.commit()

        r = c.get("/movimentacoes/sugestoes")
        assert r.status_code == 200
        d = r.json()
        assert d["lotes_com_criterio"] == 1  # só o lote 02 tem critério
        sug = next(s for s in d["sugestoes"] if s["numero_matriz"] == "100")
        assert any(l["codigo"] == "02" for l in sug["lotes_sugeridos"])

    def test_animal_ja_no_lote_certo_nao_gera_sugestao(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Lote(codigo="02", nome="Aptas", peso_min=300))
            s.add(Animal(numero="101", categoria_abrev="Vaca", sexo="F", grupo_primario="02 - Aptas", ativo=True))
            s.commit()
            from fazenda.models import PesagemCorporal
            from datetime import date
            s.add(PesagemCorporal(numero_matriz="101", data_pesagem=date.today(), peso_kg=350))
            s.commit()

        r = c.get("/movimentacoes/sugestoes")
        assert r.status_code == 200
        assert not any(s["numero_matriz"] == "101" for s in r.json()["sugestoes"])

    def test_lote_sem_criterio_nao_entra_na_comparacao(self, client):
        c, engine = client
        with Session(engine) as s:
            # Nenhum lote tem critério — nada pode ser sugerido.
            s.add(Lote(codigo="01", nome="Geral"))
            s.add(Lote(codigo="02", nome="Outro"))
            s.add(Animal(numero="102", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Geral", ativo=True))
            s.commit()

        r = c.get("/movimentacoes/sugestoes")
        assert r.status_code == 200
        d = r.json()
        assert d["lotes_com_criterio"] == 0
        assert d["sugestoes"] == []

    def test_animal_sem_lote_correspondente_nao_gera_sugestao(self, client):
        c, engine = client
        with Session(engine) as s:
            # Lote exige peso >= 500kg; a vaca não pesa isso e não tem peso
            # registrado — não atende a nenhum lote, então nada a sugerir.
            s.add(Lote(codigo="02", nome="Pesadas", peso_min=500))
            s.add(Animal(numero="103", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Sem lote", ativo=True))
            s.commit()

        r = c.get("/movimentacoes/sugestoes")
        assert r.status_code == 200
        assert not any(s["numero_matriz"] == "103" for s in r.json()["sugestoes"])

    def test_motivo_explica_o_criterio_que_bateu(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Lote(codigo="01", nome="Recém-chegadas"))
            s.add(Lote(codigo="02", nome="Aptas", peso_min=300, categorias="vaca"))
            s.add(Animal(numero="104", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Recém-chegadas", ativo=True))
            s.commit()
            from fazenda.models import PesagemCorporal
            from datetime import date
            s.add(PesagemCorporal(numero_matriz="104", data_pesagem=date.today(), peso_kg=350))
            s.commit()

        r = c.get("/movimentacoes/sugestoes")
        sug = next(s for s in r.json()["sugestoes"] if s["numero_matriz"] == "104")
        # Motivo combinado (nível da sugestão) e por lote sugerido — ambos
        # devem mencionar os critérios que efetivamente bateram (peso e categoria).
        assert sug["motivo"] is not None and "Peso" in sug["motivo"]
        lote_sugerido = next(l for l in sug["lotes_sugeridos"] if l["codigo"] == "02")
        assert lote_sugerido["motivo"] is not None and "Peso" in lote_sugerido["motivo"] and "Categoria" in lote_sugerido["motivo"]

    def test_lote_sem_criterio_preenchido_para_aquele_campo_nao_aparece_no_motivo(self, client):
        c, engine = client
        with Session(engine) as s:
            # Lote só filtra por categoria — peso não é critério aqui, então
            # não deve aparecer no motivo mesmo que o animal tenha peso registrado.
            s.add(Lote(codigo="03", nome="Novilhas", categorias="novilha"))
            s.add(Animal(numero="105", categoria_abrev="Novilha", sexo="F", grupo_primario="01 - Sem lote", ativo=True))
            s.commit()
            from fazenda.models import PesagemCorporal
            from datetime import date
            s.add(PesagemCorporal(numero_matriz="105", data_pesagem=date.today(), peso_kg=280))
            s.commit()

        r = c.get("/movimentacoes/sugestoes")
        sug = next(s for s in r.json()["sugestoes"] if s["numero_matriz"] == "105")
        assert "Peso" not in (sug["motivo"] or "")
        assert "Categoria" in (sug["motivo"] or "")


class TestCriteriosAoVivo:
    """Situação produtiva e dias pós-parto passaram a ser calculados a partir do
    Secagem/Parto mais recente do animal, não do texto congelado de
    Animal.categoria_completa/del_dias (só atualizado no próximo GERAL.csv) —
    reproduz o bug relatado: vaca secada pelo próprio app ainda sendo sugerida
    para lote de lactação porque a ficha ainda dizia "lactação"."""

    def test_secagem_lancada_hoje_tira_do_lote_de_lactacao_e_manda_pra_secas(self, client):
        c, engine = client
        from datetime import date
        with Session(engine) as s:
            # categoria_completa ainda diz "lactação" (não foi reimportada),
            # mas a Secagem de hoje já define a situação produtiva real.
            s.add(Lote(codigo="01", nome="Alta lactação", status_lactacao="lactacao"))
            s.add(Lote(codigo="04", nome="Secas", status_lactacao="seca"))
            s.add(Animal(numero="430", categoria_abrev="Vaca", categoria_completa="Vaca em lactação",
                          sexo="F", grupo_primario="01 - Alta lactação", ativo=True))
            s.add(Secagem(numero_matriz="430", data_secagem=date.today(), motivo="rotina"))
            s.commit()

        r = c.get("/movimentacoes/sugestoes")
        sug = next(s for s in r.json()["sugestoes"] if s["numero_matriz"] == "430")
        codigos = {l["codigo"] for l in sug["lotes_sugeridos"]}
        assert codigos == {"04"}  # nunca "01" — ela está seca agora, não em lactação

    def test_del_min_max_usa_dias_pos_parto_reais_nao_del_dias_congelado(self, client):
        c, engine = client
        from datetime import date, timedelta
        with Session(engine) as s:
            s.add(Lote(codigo="03", nome="PEV", del_min=0, del_max=45))
            # del_dias (congelado) diz 200, mas o parto real foi há 10 dias —
            # o critério tem que usar os 10 dias reais, não os 200 congelados.
            s.add(Animal(numero="431", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Sem lote",
                          del_dias=200, ativo=True))
            s.add(Parto(numero_matriz="431", data_parto=date.today() - timedelta(days=10)))
            s.commit()

        r = c.get("/movimentacoes/sugestoes")
        sug = next(s for s in r.json()["sugestoes"] if s["numero_matriz"] == "431")
        assert any(l["codigo"] == "03" for l in sug["lotes_sugeridos"])

    def test_situacao_reprodutiva_filtra_por_sit_rep(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Lote(codigo="02", nome="Prenhas", situacao_reprodutiva="prenha"))
            s.add(Animal(numero="432", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Sem lote",
                          sit_rep="Ges.", ativo=True))
            s.add(Animal(numero="433", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Sem lote",
                          sit_rep="Vazia", ativo=True))
            s.commit()

        r = c.get("/movimentacoes/sugestoes")
        sugeridos = {s["numero_matriz"] for s in r.json()["sugestoes"]}
        assert "432" in sugeridos
        assert "433" not in sugeridos

    def test_vinculo_com_categoria_manejo_exige_classificacao_correspondente(self, client):
        c, engine = client
        with Session(engine) as s:
            cat = CategoriaManejo(nome="Recria alta", dia_min=200, dia_max=400)
            s.add(cat)
            s.commit()
            s.refresh(cat)
            s.add(Lote(codigo="07", nome="Recria alta", categoria_manejo_ids=str(cat.id)))
            # 300 dias de vida -> classifica em "Recria alta"; 100 dias -> não.
            from datetime import date, timedelta
            s.add(Animal(numero="434", categoria_abrev="Novilha", sexo="F", grupo_primario="01 - Sem lote",
                          data_nasc=date.today() - timedelta(days=300), ativo=True))
            s.add(Animal(numero="435", categoria_abrev="Novilha", sexo="F", grupo_primario="01 - Sem lote",
                          data_nasc=date.today() - timedelta(days=100), ativo=True))
            s.commit()

        r = c.get("/movimentacoes/sugestoes")
        sugeridos = {s["numero_matriz"] for s in r.json()["sugestoes"]}
        assert "434" in sugeridos
        assert "435" not in sugeridos
