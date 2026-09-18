"""
Testes dos relatórios gerenciais e de manejo reprodutivo + estoque de sêmen.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, EstoqueSemen, Lactacao, ParametroFazenda, Parto, Secagem, Servico


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


def _hoje():
    return date.today()


class TestManejo:
    def test_vaca_recem_parida_no_pev_vermelho(self, client):
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            s.add(Animal(numero="100", sexo="F", ativo=True, del_dias=5, sit_rep="Vaz. apt."))
            s.add(Parto(numero_matriz="100", data_parto=hoje - timedelta(days=5), ordem_parto=1))
            s.commit()
        r = c.get("/relatorios/manejo")
        assert r.status_code == 200
        pev = r.json()["pev"]
        assert any(x["numero"] == "100" and x["cor"] == "vermelho" for x in pev)

    def test_vaca_passou_meta_a_inseminar_vermelho(self, client):
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            s.add(Animal(numero="101", sexo="F", ativo=True, del_dias=120, sit_rep="Vaz. atr."))
            s.add(Parto(numero_matriz="101", data_parto=hoje - timedelta(days=120), ordem_parto=1))
            s.commit()
        r = c.get("/relatorios/manejo")
        a_inseminar = r.json()["a_inseminar"]
        assert any(x["numero"] == "101" and x["cor"] == "vermelho" for x in a_inseminar)

    def test_inseminada_retorno_cio_vermelho(self, client):
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            s.add(Animal(numero="102", sexo="F", ativo=True, del_dias=90, sit_rep="Ins."))
            s.add(Parto(numero_matriz="102", data_parto=hoje - timedelta(days=110), ordem_parto=1))
            s.add(Servico(numero_matriz="102", data_servico=hoje - timedelta(days=20),
                          ordem_tentativa=1, reprodutor="Touro X"))
            s.commit()
        r = c.get("/relatorios/manejo")
        inseminados = r.json()["inseminados"]
        linha = next(x for x in inseminados if x["numero"] == "102")
        assert linha["dias_inseminada"] == 20
        assert linha["cor_cio"] == "vermelho"  # 18-24 dias

    def test_prenhe_e_previsao_parto(self, client):
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            s.add(Animal(numero="103", sexo="F", ativo=True, del_dias=230, sit_rep="Ges."))
            s.add(Parto(numero_matriz="103", data_parto=hoje - timedelta(days=250), ordem_parto=1))
            s.add(Servico(numero_matriz="103", data_servico=hoje - timedelta(days=230),
                          ordem_tentativa=1, diagnostico="POSITIVO",
                          data_reconfirmacao=hoje - timedelta(days=170), diagnostico_reconfirmacao="POSITIVO"))
            s.commit()
        r = c.get("/relatorios/manejo")
        prenhes = r.json()["prenhes"]
        assert any(x["numero"] == "103" for x in prenhes)
        # 230 dias de gestação, reconfirmada > 200 → entra em previsão de partos
        partos = r.json()["previsao_partos"]
        assert any(x["numero"] == "103" for x in partos)

    def test_estoque_semen_cores(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(EstoqueSemen(touro_nome="Convencional Baixo", tipo="convencional", doses=10))
            s.add(EstoqueSemen(touro_nome="Sexado Bom", tipo="sexado", doses=20))
            s.commit()
        r = c.get("/relatorios/manejo")
        semen = {x["touro_nome"]: x for x in r.json()["estoque_semen"]}
        assert semen["Convencional Baixo"]["cor"] == "vermelho"  # < 15 convencional
        assert semen["Sexado Bom"]["cor"] == "verde"  # > 15 sexado

    def test_servico_aberto_nunca_coexiste_em_a_inseminar_e_inseminados(self, client):
        """Regressão: animal com sit_rep desatualizado (ainda "Vaz.") mas com um
        serviço já lançado (D0/IA) e sem diagnóstico não pode aparecer nas duas
        listas ao mesmo tempo — só em "inseminados"."""
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            s.add(Animal(numero="405", sexo="F", ativo=True, del_dias=80, sit_rep="Vaz. apt."))
            s.add(Parto(numero_matriz="405", data_parto=hoje - timedelta(days=80), ordem_parto=2))
            s.add(Servico(numero_matriz="405", data_servico=hoje - timedelta(days=5),
                          ordem_tentativa=1, reprodutor="Touro Y"))
            s.commit()
        r = c.get("/relatorios/manejo")
        dados = r.json()
        assert any(x["numero"] == "405" for x in dados["inseminados"])
        assert not any(x["numero"] == "405" for x in dados["a_inseminar"])

    def test_novilha_reconfirmada_60_mais_nao_aparece_para_reconfirmar(self, client):
        """Regressão: novilha (nunca pariu) com toque positivo dispensa a
        reconfirmação de 60 dias — não deve aparecer na lista de a_reconfirmar
        mesmo sem data_reconfirmacao lançada."""
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            s.add(Animal(numero="900", sexo="F", ativo=True, sit_rep="Ges."))
            s.add(Servico(numero_matriz="900", data_servico=hoje - timedelta(days=90),
                          ordem_tentativa=1, diagnostico="POSITIVO"))
            s.commit()
        r = c.get("/relatorios/manejo")
        dados = r.json()
        assert not any(x["numero"] == "900" for x in dados["a_reconfirmar"])
        prenhe = next(x for x in dados["prenhes"] if x["numero"] == "900")
        assert prenhe["reconfirmada"] is True

    def test_reconfirmar_nao_coexiste_com_a_tocar_apos_nova_ia(self, client):
        """Regressão: um positivo antigo sem reconfirmação, mas com uma nova IA
        já aberta desde então, não pode aparecer em a_reconfirmar (o serviço
        mais recente é outro, ainda não tocado) — só em a_tocar."""
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            s.add(Animal(numero="700", sexo="F", ativo=True, del_dias=300, sit_rep="Vaz. apt."))
            s.add(Parto(numero_matriz="700", data_parto=hoje - timedelta(days=300), ordem_parto=1))
            s.add(Servico(numero_matriz="700", data_servico=hoje - timedelta(days=200),
                          ordem_tentativa=1, diagnostico="POSITIVO", reprodutor="Touro A"))
            s.add(Servico(numero_matriz="700", data_servico=hoje - timedelta(days=40),
                          ordem_tentativa=2, reprodutor="Touro B"))
            s.commit()
        r = c.get("/relatorios/manejo")
        dados = r.json()
        assert any(x["numero"] == "700" for x in dados["a_tocar"])
        assert not any(x["numero"] == "700" for x in dados["a_reconfirmar"])

    def test_secagem_atraso_implausivel_nao_aparece_pendente(self, client):
        """Regressão: atraso muito grande na previsão de secagem (sinal de
        parto/secagem que não foi lançado a tempo) não deve continuar
        aparecendo como pendência retroativa — some da lista em vez de
        acumular -200+ dias."""
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            s.add(Animal(numero="701", sexo="F", ativo=True, del_dias=200, sit_rep="Ges."))
            s.add(Parto(numero_matriz="701", data_parto=hoje - timedelta(days=400), ordem_parto=1))
            s.add(Servico(numero_matriz="701", data_servico=hoje - timedelta(days=340),
                          ordem_tentativa=1, diagnostico="POSITIVO", reprodutor="Touro C"))
            # Controle: atraso moderado (dentro do limite) continua aparecendo normalmente.
            s.add(Animal(numero="702", sexo="F", ativo=True, del_dias=200, sit_rep="Ges."))
            s.add(Parto(numero_matriz="702", data_parto=hoje - timedelta(days=300), ordem_parto=1))
            s.add(Servico(numero_matriz="702", data_servico=hoje - timedelta(days=250),
                          ordem_tentativa=1, diagnostico="POSITIVO", reprodutor="Touro C"))
            s.commit()
        r = c.get("/relatorios/manejo")
        secagem = r.json()["secagem"]
        assert not any(x["numero"] == "701" for x in secagem)
        assert any(x["numero"] == "702" for x in secagem)

    def test_vaca_422_inducao_sem_parto_entra_em_pev_e_depois_a_inseminar(self, client):
        """Vaca 422: indução de lactação concluída (Lactacao aberta, sem
        Parto) — sem `data_inicio_lactacao`, `dpp` ficava None (dparto
        também None) e ela nunca entrava em "Vacas no PEV" nem, depois,
        em "Vacas a inseminar" nesta Lista de trabalho (Insights >
        Listas), mesmo já corrigida em /indicadores/ e /reproducao/."""
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            s.add(Animal(numero="422", sexo="F", ativo=True, sit_rep="Vaz. atr."))
            s.add(Lactacao(numero_matriz="422", data_inicio=hoje - timedelta(days=10), origem="inducao"))
            s.commit()
        r = c.get("/relatorios/manejo")
        dados = r.json()
        pev = next((x for x in dados["pev"] if x["numero"] == "422"), None)
        assert pev is not None, "vaca 422 (indução, sem parto) não apareceu em Vacas no PEV"
        assert pev["dias_pos_parto"] == 10
        assert not any(x["numero"] == "422" for x in dados["a_inseminar"])

    def test_vaca_422_apos_pev_vencido_aparece_a_inseminar(self, client):
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            s.add(Animal(numero="422", sexo="F", ativo=True, sit_rep="Vaz. atr."))
            s.add(Lactacao(numero_matriz="422", data_inicio=hoje - timedelta(days=120), origem="inducao"))
            s.commit()
        r = c.get("/relatorios/manejo")
        dados = r.json()
        assert not any(x["numero"] == "422" for x in dados["pev"])
        a_inseminar = next((x for x in dados["a_inseminar"] if x["numero"] == "422"), None)
        assert a_inseminar is not None, "vaca 422 passou do PEV mas não apareceu em Vacas a inseminar"
        assert a_inseminar["eh_vaca"] is True
        assert a_inseminar["cor"] == "vermelho"  # 120 dias > meta de 100 dias p/ 1ª IA

    def test_vaca_422_parto_antigo_nao_trava_a_ancora_da_lactacao_recente(self, client):
        """BUG REAL da vaca 422 (o que sobrevivia mesmo com Lactacao aberta):
        um Parto de ~1 ano atrás (ciclo já encerrado) não pode continuar
        ancorando `dpp` depois de uma indução recente ter reaberto a
        lactação — a âncora tem que ser a MAIS RECENTE das duas."""
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            s.add(Animal(numero="422", sexo="F", ativo=True, sit_rep="Vaz. atr."))
            s.add(Parto(numero_matriz="422", data_parto=hoje - timedelta(days=519), ordem_parto=3))
            s.add(Lactacao(numero_matriz="422", data_inicio=hoje - timedelta(days=10), origem="inducao"))
            s.commit()
        r = c.get("/relatorios/manejo")
        dados = r.json()
        pev = next((x for x in dados["pev"] if x["numero"] == "422"), None)
        assert pev is not None, "vaca 422 (parto antigo + indução recente) não apareceu em Vacas no PEV"
        assert pev["dias_pos_parto"] == 10


class TestGerencial:
    def _seed(self, engine):
        hoje = _hoje()
        with Session(engine) as s:
            # 1ª IA no período desejado (DEL 60) e uma após meta (DEL 130)
            s.add(Servico(numero_matriz="200", data_servico=hoje - timedelta(days=200),
                          data_ult_parto=hoje - timedelta(days=260), ordem_tentativa=1, del_servico=60,
                          diagnostico="POSITIVO"))
            s.add(Servico(numero_matriz="201", data_servico=hoje - timedelta(days=100),
                          data_ult_parto=hoje - timedelta(days=230), ordem_tentativa=1, del_servico=130,
                          diagnostico="NEGATIVO", data_diagnostico=hoje - timedelta(days=70)))
            s.add(Servico(numero_matriz="201", data_servico=hoje - timedelta(days=60),
                          ordem_tentativa=2, intervalo_tentativas=40))
            s.commit()

    def test_distribuicao_del(self, client):
        c, engine = client
        self._seed(engine)
        r = c.get("/relatorios/gerencial/distribuicao-del", params={"ordem": 1})
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["pev"] == 45 and corpo["meta"] == 100
        cores = {p["numero"]: p["cor"] for p in corpo["pontos"]}
        assert cores["200"] == "verde"  # DEL 60 no período desejado
        assert cores["201"] == "vermelho"  # DEL 130 após meta

    def test_intervalo_servicos(self, client):
        c, engine = client
        self._seed(engine)
        r = c.get("/relatorios/gerencial/intervalo-servicos")
        barras = {b["faixa"]: b["servicos"] for b in r.json()["barras"]}
        assert barras["36-48 dias"] == 1  # intervalo 40

    def test_dias_reinseminacao(self, client):
        c, engine = client
        self._seed(engine)
        r = c.get("/relatorios/gerencial/dias-reinseminacao")
        # 201: negativo em -70, re-inseminada em -60 → 10 dias, antes da
        # janela padrão (dias_reinseminacao_min/max = 18/25) — adiantada.
        barras = {b["faixa"]: b["servicos"] for b in r.json()["barras"]}
        assert barras["1-17 dias (adiantada)"] == 1

    def test_dias_reinseminacao_reage_ao_parametro_configurado(self, client, monkeypatch):
        c, engine = client
        # get_param()/_linha() lê `fazenda.database.engine` diretamente (não
        # via Depends) — sem isso, a leitura pós-PUT cairia no engine
        # padrão do módulo, não no engine isolado deste teste.
        monkeypatch.setattr(database, "engine", engine)
        self._seed(engine)
        # PUT exige a linha já existir — testes rodam com FAZENDA_TESTING=1
        # (seed_parametros() pulado por velocidade, ver main.py::lifespan),
        # então semeia só as 2 chaves que este teste usa.
        with Session(engine) as s:
            s.add(ParametroFazenda(chave="dias_reinseminacao_min", grupo="reinseminacao_cio",
                                    label="Dias para reinseminação — mínimo", valor="18", tipo="int"))
            s.add(ParametroFazenda(chave="dias_reinseminacao_max", grupo="reinseminacao_cio",
                                    label="Dias para reinseminação — máximo", valor="25", tipo="int"))
            s.commit()
        # Muda a janela para 5-15 dias — os mesmos 10 dias do seed (201)
        # passam a cair DENTRO da janela, não mais "adiantada".
        assert c.put("/parametros/dias_reinseminacao_min", json={"valor": 5}).status_code == 200
        assert c.put("/parametros/dias_reinseminacao_max", json={"valor": 15}).status_code == 200
        r = c.get("/relatorios/gerencial/dias-reinseminacao")
        barras = {b["faixa"]: b["servicos"] for b in r.json()["barras"]}
        assert barras["5-15 dias (janela ideal)"] == 1

    def test_taxa_servico_prenhez_meta_100d_vem_do_parametro(self, client, monkeypatch):
        c, engine = client
        monkeypatch.setattr(database, "engine", engine)
        self._seed(engine)
        r = c.get("/relatorios/gerencial/taxa-servico-prenhez")
        assert r.json()["parametros"]["meta_100d"] == 50  # padrão de meta_taxa_servico

        with Session(engine) as s:
            s.add(ParametroFazenda(chave="meta_taxa_servico", grupo="metas_reproducao",
                                    label="Taxa de serviço em vacas", valor="50", tipo="int", unidade="%"))
            s.commit()
        assert c.put("/parametros/meta_taxa_servico", json={"valor": 65}).status_code == 200
        r2 = c.get("/relatorios/gerencial/taxa-servico-prenhez")
        assert r2.json()["parametros"]["meta_100d"] == 65

    def test_prenhezes_por_del(self, client):
        c, engine = client
        self._seed(engine)
        r = c.get("/relatorios/gerencial/prenhezes-por-del")
        assert r.json()["total"] == 1  # só o serviço 200 é POSITIVO

    def test_fluxo_lactacao(self, client):
        c, engine = client
        self._seed(engine)
        r = c.get("/relatorios/gerencial/fluxo-lactacao", params={"meses": 6})
        assert r.status_code == 200
        assert len(r.json()["linhas"]) == 6


class TestEstadoAoVivo:
    """Migração de `sit_rep` (texto congelado do último GERAL.csv) para o
    estado reprodutivo AO VIVO nas 8 listas de manejo e em `fluxo_lactacao`.
    Cada teste aqui planta um `sit_rep` que MENTE em relação aos registros
    (Parto/Servico/Secagem) reais — o comportamento correto é ignorar o texto
    e seguir os registros."""

    def test_engravidou_pelo_app_sai_de_a_inseminar_e_entra_em_prenhes(self, client):
        """sit_rep ainda diz "Vaz. apt." (não seria atualizado até o próximo
        upload), mas a vaca já tem serviço positivo lançado pelo app."""
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            s.add(Animal(numero="910", sexo="F", ativo=True, sit_rep="Vaz. apt."))
            s.add(Parto(numero_matriz="910", data_parto=hoje - timedelta(days=150), ordem_parto=1))
            s.add(Servico(numero_matriz="910", data_servico=hoje - timedelta(days=100),
                          ordem_tentativa=1, diagnostico="POSITIVO", reprodutor="Touro Z"))
            s.commit()
        r = c.get("/relatorios/manejo")
        dados = r.json()
        assert not any(x["numero"] == "910" for x in dados["a_inseminar"])
        assert any(x["numero"] == "910" for x in dados["prenhes"])

    def test_pariu_pelo_app_entra_em_pev(self, client):
        """sit_rep ainda diz "Ges." (frozen no upload anterior ao parto), mas
        o parto já foi lançado pelo app — o ciclo zerou, a vaca está em PEV,
        não gestante."""
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            s.add(Animal(numero="911", sexo="F", ativo=True, sit_rep="Ges."))
            s.add(Parto(numero_matriz="911", data_parto=hoje - timedelta(days=10), ordem_parto=2))
            s.commit()
        r = c.get("/relatorios/manejo")
        dados = r.json()
        assert any(x["numero"] == "911" for x in dados["pev"])
        assert not any(x["numero"] == "911" for x in dados["prenhes"])

    def test_a_descartar_some_de_a_inseminar_mas_continua_biologica(self, client):
        """O corte de `a_descartar` vale só para "a inseminar" (a lista pede
        uma AÇÃO que contradiz o descarte já decidido). As listas biológicas
        — prenhes, secagem — continuam valendo: a vaca marcada a descartar
        que está prenhe ainda vai parir e ainda precisa ser secada."""
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            # Vaca a descartar, apta (passou do PEV, sem serviço aberto):
            # sem o corte, cairia em "a inseminar".
            s.add(Animal(numero="912", sexo="F", ativo=True, sit_rep="Vaz. apt.", a_descartar=True))
            s.add(Parto(numero_matriz="912", data_parto=hoje - timedelta(days=120), ordem_parto=1))
            # Vaca a descartar, gestante: precisa continuar em prenhes/secagem.
            # Concepção há 190 dias -> secagem prevista em ~30 dias (dentro da
            # janela de 60 dias que a lista de secagem mostra).
            s.add(Animal(numero="913", sexo="F", ativo=True, sit_rep="Vaz. apt.", a_descartar=True))
            s.add(Parto(numero_matriz="913", data_parto=hoje - timedelta(days=250), ordem_parto=1))
            s.add(Servico(numero_matriz="913", data_servico=hoje - timedelta(days=190),
                          ordem_tentativa=1, diagnostico="POSITIVO", reprodutor="Touro Z"))
            s.commit()
        r = c.get("/relatorios/manejo")
        dados = r.json()
        assert not any(x["numero"] == "912" for x in dados["a_inseminar"])
        assert not any(x["numero"] == "913" for x in dados["a_inseminar"])
        assert any(x["numero"] == "913" for x in dados["prenhes"])
        assert any(x["numero"] == "913" for x in dados["secagem"])

    def test_novilha_sem_idade_nem_peso_fora_de_a_inseminar(self, client):
        """Antes, `vazia = sit.startswith("Vaz.")` bastava para uma novilha
        cair em "a inseminar" — mesmo sem idade nem peso cadastrados. No
        estado ao vivo, sem idade/peso a novilha é NAO_APTA (regra 7 de
        `classificar_animal`), não APTA/ATRASADA: não é candidata a serviço."""
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="914", sexo="F", ativo=True, sit_rep="Vaz. apt.",
                        data_nasc=None))
            s.commit()
        r = c.get("/relatorios/manejo")
        dados = r.json()
        assert not any(x["numero"] == "914" for x in dados["a_inseminar"])

    def test_taxa_prenhez_por_del_conta_gestacao_ao_vivo(self, client):
        """A curva acumulada de prenhas por faixa de DEL contava
        `sit_rep == "Ges."`. A vaca que engravidava pelo app ficava de fora da
        curva até o próximo upload, afundando a taxa da faixa dela."""
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            # DEL 120 (faixa 101-150), gestante pelos registros, sit_rep velho.
            s.add(Animal(numero="930", sexo="F", ativo=True, sit_rep="Vaz. apt."))
            s.add(Parto(numero_matriz="930", data_parto=hoje - timedelta(days=120), ordem_parto=1))
            s.add(Servico(numero_matriz="930", data_servico=hoje - timedelta(days=60),
                          ordem_tentativa=1, diagnostico="POSITIVO", reprodutor="Touro Z"))
            s.commit()
        r = c.get("/relatorios/gerencial/taxa-servico-prenhez")
        assert r.status_code == 200
        faixa = next(l for l in r.json()["linhas"] if l["faixa"] == "101-150")
        assert faixa["vacas"] == 1
        assert faixa["taxa_prenhez"] == 100

    def test_fluxo_lactacao_vaca_recem_secada_pelo_app_nao_conta(self, client):
        """`Animal.del_dias` (congelado) continuava > 0 até o próximo upload
        mesmo com a Secagem já lançada pelo app — a vaca some do saldo AO
        VIVO (mesmo critério de `relatorios_manejo`: última secagem posterior
        ao último parto)."""
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            # Recém-secada pelo app: del_dias congelado ainda positivo, mas a
            # Secagem (posterior ao parto) já zerou a lactação ao vivo.
            s.add(Animal(numero="920", sexo="F", ativo=True, del_dias=50))
            s.add(Parto(numero_matriz="920", data_parto=hoje - timedelta(days=100), ordem_parto=1))
            s.add(Secagem(numero_matriz="920", data_secagem=hoje - timedelta(days=10), motivo="rotina"))
            # Controle: mesma situação, sem secagem lançada — continua em lactação.
            s.add(Animal(numero="921", sexo="F", ativo=True, del_dias=50))
            s.add(Parto(numero_matriz="921", data_parto=hoje - timedelta(days=100), ordem_parto=1))
            s.commit()
        r = c.get("/relatorios/gerencial/fluxo-lactacao", params={"meses": 1})
        assert r.status_code == 200
        assert r.json()["lactacao_inicial"] == 1


class TestEstoqueSemenCRUD:
    def test_criar_listar_editar_excluir(self, client):
        c, engine = client
        r = c.post("/cadastro/estoque-semen", json={"touro_nome": "Touro A", "tipo": "sexado", "doses": 8})
        assert r.status_code == 200
        item_id = r.json()["id"]
        assert c.get("/cadastro/estoque-semen").json()[0]["touro_nome"] == "Touro A"
        r2 = c.put(f"/cadastro/estoque-semen/{item_id}", json={"touro_nome": "Touro A", "tipo": "sexado", "doses": 3})
        assert r2.json()["doses"] == 3
        assert c.delete(f"/cadastro/estoque-semen/{item_id}").json()["excluido"] is True
        assert c.get("/cadastro/estoque-semen").json() == []

    def test_tipo_invalido_rejeitado(self, client):
        c, engine = client
        r = c.post("/cadastro/estoque-semen", json={"touro_nome": "X", "tipo": "clone", "doses": 5})
        assert r.status_code == 400


class TestNovilhaAtrasadaNaListaAInseminar:
    """A cor da novilha em "a inseminar" era "verde" por construção (o
    semáforo só olhava DPP, que nulípara não tem). Como o relatório de não
    conformidades conta exatamente os "vermelho" desta lista, o indicador era
    cego para a categoria majoritária desta fazenda. Agora a cor da novilha
    sai do estado AO VIVO: ATRASADA -> vermelho, APTA -> verde."""

    def test_novilha_atrasada_sai_vermelha_e_apta_sai_verde(self, client):
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            # 26 meses: passou do teto de idade para a 1ª cobertura (16) ->
            # ATRASADA. Sem parto e sem serviço, entra em "a inseminar".
            s.add(Animal(numero="940", sexo="F", ativo=True, categoria_abrev="Novilha",
                         data_nasc=hoje - timedelta(days=790)))
            # 15,5 meses: passou do piso de aptidão (15) e ainda não do teto -> APTA.
            s.add(Animal(numero="941", sexo="F", ativo=True, categoria_abrev="Novilha",
                         data_nasc=hoje - timedelta(days=472)))
            s.commit()
        dados = c.get("/relatorios/manejo").json()
        por_numero = {x["numero"]: x for x in dados["a_inseminar"]}
        assert set(por_numero) == {"940", "941"}
        assert por_numero["940"]["cor"] == "vermelho"
        assert por_numero["940"]["situacao"] == "Atrasada"
        assert por_numero["941"]["cor"] == "verde"
        assert por_numero["941"]["situacao"] == "Apta"

    def test_vaca_dentro_da_meta_continua_verde(self, client):
        """Sentinela: o ramo da vaca (semáforo por DPP) não mudou."""
        c, engine = client
        hoje = _hoje()
        with Session(engine) as s:
            s.add(Animal(numero="942", sexo="F", ativo=True, sit_rep="Vaz. apt."))
            s.add(Parto(numero_matriz="942", data_parto=hoje - timedelta(days=50), ordem_parto=1))
            s.commit()
        dados = c.get("/relatorios/manejo").json()
        item = next(x for x in dados["a_inseminar"] if x["numero"] == "942")
        assert item["cor"] == "verde"
