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
from fazenda.models import Animal, CategoriaManejo, Lote, Parto, Secagem, Servico


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

    def test_lote_excluido_da_sugestao_nunca_e_sugerido(self, client):
        c, engine = client
        with Session(engine) as s:
            # Lote 02 exigiria peso >= 300kg (igual ao teste acima), mas está
            # marcado como excluído da sugestão — não deve aparecer mesmo a
            # vaca "100" (350kg) atendendo ao critério.
            s.add(Lote(codigo="01", nome="Recém-chegadas"))
            s.add(Lote(codigo="02", nome="Enfermaria", peso_min=300, excluir_da_sugestao=True))
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
        assert d["lotes_com_criterio"] == 0  # o único lote com critério está excluído da sugestão
        assert d["sugestoes"] == []

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
        # Motivo combinado (nível da sugestão) e por lote sugerido — só o
        # critério GERADOR que bateu (peso) entra no motivo; "categorias" é
        # restritivo (filtra, mas não é o "porquê" da sugestão — ver
        # `_CAMPOS_GERADORES_SUGESTAO` em lote_criterios.py) e não aparece.
        assert sug["motivo"] is not None and "Peso" in sug["motivo"]
        lote_sugerido = next(l for l in sug["lotes_sugeridos"] if l["codigo"] == "02")
        assert lote_sugerido["motivo"] is not None and "Peso" in lote_sugerido["motivo"] and "Categoria" not in lote_sugerido["motivo"]

    def test_lote_sem_criterio_preenchido_para_aquele_campo_nao_aparece_no_motivo(self, client):
        c, engine = client
        with Session(engine) as s:
            # "categorias" sozinho não gera sugestão (é restritivo — ver
            # `_CAMPOS_GERADORES_SUGESTAO`), então o lote precisa de um critério
            # GERADOR de verdade (idade) para entrar na sugestão; peso não é
            # critério nenhum aqui, então não deve aparecer no motivo mesmo que
            # o animal tenha peso registrado, e "Categoria" nunca aparece no
            # motivo (restritivo, filtra mas não é o "porquê").
            s.add(Lote(codigo="03", nome="Novilhas", categorias="novilha", idade_dias_min=0))
            from datetime import date, timedelta
            s.add(Animal(numero="105", categoria_abrev="Novilha", sexo="F", grupo_primario="01 - Sem lote",
                          data_nasc=date.today() - timedelta(days=300), ativo=True))
            s.commit()
            from fazenda.models import PesagemCorporal
            s.add(PesagemCorporal(numero_matriz="105", data_pesagem=date.today(), peso_kg=280))
            s.commit()

        r = c.get("/movimentacoes/sugestoes")
        sug = next(s for s in r.json()["sugestoes"] if s["numero_matriz"] == "105")
        assert "Peso" not in (sug["motivo"] or "")
        assert "Categoria" not in (sug["motivo"] or "")
        assert "Idade" in (sug["motivo"] or "")


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
            # `categoria_manejo_ids` sozinho não gera sugestão (é restritivo —
            # ver `_CAMPOS_GERADORES_SUGESTAO`); `idade_dias_min=0` é o critério
            # GERADOR que faz o lote participar, e o vínculo de categoria segue
            # restringindo em E lógico normalmente.
            s.add(Lote(codigo="07", nome="Recria alta", categoria_manejo_ids=str(cat.id), idade_dias_min=0))
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

    def test_lote_inativo_nunca_e_sugerido(self, client):
        c, engine = client
        with Session(engine) as s:
            # Lote 02 bateria no critério (peso >= 300kg) mas está inativo —
            # não pode ser sugerido nem contado em lotes_com_criterio.
            s.add(Lote(codigo="01", nome="Recém-chegadas"))
            s.add(Lote(codigo="02", nome="Aptas (desativado)", peso_min=300, ativo=False))
            s.add(Animal(numero="436", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Recém-chegadas", ativo=True))
            s.commit()

        with Session(engine) as s:
            from fazenda.models import PesagemCorporal
            from datetime import date
            s.add(PesagemCorporal(numero_matriz="436", data_pesagem=date.today(), peso_kg=350))
            s.commit()

        r = c.get("/movimentacoes/sugestoes")
        assert r.status_code == 200
        d = r.json()
        assert d["lotes_com_criterio"] == 0
        assert not any(s["numero_matriz"] == "436" for s in d["sugestoes"])


class TestPreParto:
    """Gatilho de "faltam ~30 dias para o parto" -> sugestão de mudar a vaca
    para o lote de pré-parto (lote.pre_parto=True, janela de pre_parto_max()
    dias antes do parto previsto — ver fazenda.rules.parametros)."""

    def test_vaca_a_30_dias_do_parto_previsto_e_sugerida_para_pre_parto(self, client):
        c, engine = client
        from datetime import date, timedelta
        from fazenda.rules.parametros import gestacao_dias_referencia, pre_parto_max

        # Confirma o parâmetro padrão documentado na tarefa (30 dias).
        assert pre_parto_max() == 30

        # dias_para_parto() = gestacao_dias_referencia() - dias_gestacao. Serviço
        # datado para deixar a vaca a 28 dias do parto previsto (dentro da janela
        # de pré-parto de 0 a 30 dias, e dentro dos "~25-30 dias" pedidos).
        dias_gestacao = gestacao_dias_referencia() - 28
        data_servico = date.today() - timedelta(days=dias_gestacao)

        with Session(engine) as s:
            s.add(Lote(codigo="09", nome="Pré-parto", pre_parto=True))
            s.add(Animal(numero="900", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Sem lote",
                         sit_rep="Ges.", ativo=True))
            s.add(Servico(numero_matriz="900", data_servico=data_servico, diagnostico="POSITIVO"))
            s.commit()

        r = c.get("/movimentacoes/sugestoes")
        assert r.status_code == 200
        d = r.json()
        sug = next((s for s in d["sugestoes"] if s["numero_matriz"] == "900"), None)
        assert sug is not None, f"Vaca a 28 dias do parto não apareceu nas sugestões: {d}"
        assert any(l["codigo"] == "09" for l in sug["lotes_sugeridos"])
