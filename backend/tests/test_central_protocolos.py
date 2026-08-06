"""
Central de Protocolos (proposta aprovada — 4 abas: Cadastro, Lançamento,
Acompanhamento e Histórico):

- Molde de IATF (padronizado com Indução/Sanitário/Customizado): cadastro com
  etapas D0/D7/D9 (D11 é sempre a inseminação, nunca faz parte do molde).
- Nome automático do lançamento: ninguém digita nome — o sistema monta
  "{NOME CADASTRADO} - {D0} A {último dia} (D{inicial} A D{final} - {n} DIAS)".
- Tipo obrigatório do Protocolo Customizado (produtivo/reprodutivo/sanitario)
  para entrar no agregador da Central.
- Agregador /central-protocolos/acompanhamento e /historico juntando os 4
  tipos, filtrável por nome/período/tipo.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
import fazenda.models  # noqa: F401 — força o registro de todas as tabelas (inclui ProtocoloIatf/Etapa) antes do create_all() do fixture
from fazenda.models import Estoque, PrincipioAtivo, ProtocoloIatfAplicacao


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


def _etapa_iatf(dia, produto="Sincrodiol", dose=2.0, unidade="ml", via="Intramuscular"):
    return {"dia": dia, "produto": produto, "dose": dose, "unidade": unidade, "via": via}


class TestMoldeIatf:
    def test_cria_molde_com_etapas_d0_d7_d9(self, client):
        c, engine = client
        r = c.post("/cadastro/protocolos-iatf", json={
            "nome": "Protocolo IATF padrão",
            "etapas": [_etapa_iatf(0), _etapa_iatf(7, produto="Sincroforte"), _etapa_iatf(9, produto="Estron")],
        })
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert [e["dia"] for e in corpo["etapas"]] == [0, 7, 9]

    def test_aceita_dia_livre(self, client):
        # Dias do molde são livres (ex.: D0/D8/D10/D12) — só dia negativo é
        # rejeitado, ver fazenda.rules.protocolo_iatf.
        c, engine = client
        r = c.post("/cadastro/protocolos-iatf", json={
            "nome": "Molde de dias livres", "etapas": [_etapa_iatf(0), _etapa_iatf(8), _etapa_iatf(10), _etapa_iatf(12)],
        })
        assert r.status_code == 200, r.text
        assert [e["dia"] for e in r.json()["etapas"]] == [0, 8, 10, 12]

    def test_rejeita_dia_negativo(self, client):
        c, engine = client
        r = c.post("/cadastro/protocolos-iatf", json={
            "nome": "Molde inválido", "etapas": [_etapa_iatf(-1)],
        })
        assert r.status_code == 400

    def test_rejeita_nome_duplicado(self, client):
        c, engine = client
        payload = {"nome": "Duplicado IATF", "etapas": [_etapa_iatf(0)]}
        assert c.post("/cadastro/protocolos-iatf", json=payload).status_code == 200
        assert c.post("/cadastro/protocolos-iatf", json=payload).status_code == 409

    def test_atualiza_molde(self, client):
        c, engine = client
        pid = c.post("/cadastro/protocolos-iatf", json={
            "nome": "Molde editável", "etapas": [_etapa_iatf(0)],
        }).json()["id"]
        r = c.put(f"/cadastro/protocolos-iatf/{pid}", json={
            "nome": "Molde editável", "etapas": [_etapa_iatf(0), _etapa_iatf(7)],
        })
        assert r.status_code == 200, r.text
        assert len(r.json()["etapas"]) == 2

    def test_nao_exclui_molde_ja_lancado(self, client):
        c, engine = client
        pid = c.post("/cadastro/protocolos-iatf", json={
            "nome": "Molde lançado", "etapas": [_etapa_iatf(0)],
        }).json()["id"]
        c.post("/reproducao/protocolo-iatf", json={
            "animais": ["700"], "data_d0": "2026-07-08", "protocolo_id": pid,
        })
        r = c.delete(f"/cadastro/protocolos-iatf/{pid}")
        assert r.status_code == 409


class TestNomeAutomatico:
    def test_iatf_ad_hoc_usa_base_generica(self, client):
        c, engine = client
        r = c.post("/reproducao/protocolo-iatf", json={"animais": ["700"], "data_d0": "2026-08-05"})
        assert r.status_code == 200, r.text
        lancs = c.get("/reproducao/protocolo-iatf/lancamentos").json()
        nome = next(l["nome_protocolo"] for l in lancs if l["lancamento_id"] == r.json()["lancamento_id"])
        assert nome == "PROTOCOLO IATF - 05/08/26 A 16/08/26 (D0 A D11 - 12 DIAS)"

    def test_iatf_com_molde_usa_nome_cadastrado(self, client):
        # Molde de dias livres (D0/D8, sem D9 clássico) — dia de inseminação
        # é calculado como o último dia com hormônio + 2 (ver
        # fazenda.rules.protocolo_iatf.dia_inseminacao), não mais fixo em D11.
        c, engine = client
        pid = c.post("/cadastro/protocolos-iatf", json={
            "nome": "Protocolo IATF Lote A", "etapas": [_etapa_iatf(0), _etapa_iatf(8)],
        }).json()["id"]
        r = c.post("/reproducao/protocolo-iatf", json={
            "animais": ["700"], "data_d0": "2026-08-05", "protocolo_id": pid,
        })
        assert r.status_code == 200, r.text
        lancs = c.get("/reproducao/protocolo-iatf/lancamentos").json()
        nome = next(l["nome_protocolo"] for l in lancs if l["lancamento_id"] == r.json()["lancamento_id"])
        assert nome == "PROTOCOLO IATF LOTE A - 05/08/26 A 15/08/26 (D0 A D10 - 11 DIAS)"

    def test_inducao_gera_nome_com_intervalo_de_dias(self, client):
        c, engine = client
        pid = c.post("/cadastro/protocolos-inducao-lactacao", json={
            "nome": "Indução padrão 2",
            "etapas": [
                {"dia": 0, "tipo": "medicamento", "produto": "Benzoato de estradiol", "dose": 1, "unidade": "ml"},
                {"dia": 27, "tipo": "manejo", "produto": "Iniciar ordenha"},
            ],
        }).json()["id"]
        r = c.post("/producao/inducao-lactacao", json={
            "protocolo_id": pid, "animais": ["800"], "data_d0": "2026-08-05",
        })
        assert r.status_code == 201, r.text
        lanc_id = r.json()["lancamento_id"] if "lancamento_id" in r.json() else None
        # Confirma via /producao/inducao-lactacao/ativos, que expõe nome_protocolo.
        ativos = c.get("/producao/inducao-lactacao/ativos").json()
        assert any(
            a.get("nome_protocolo") == "INDUÇÃO PADRÃO 2 - 05/08/26 A 01/09/26 (D0 A D27 - 28 DIAS)"
            for a in ativos
        )


class TestTipoProtocoloCustomizado:
    def test_cria_sem_tipo(self, client):
        c, engine = client
        r = c.post("/cadastro/protocolos-customizados", json={
            "nome": "Cura de casco", "categoria": "Rebanho",
            "etapas": [{"dia": 0, "descricao_evento": "Aplicar produto"}],
        })
        assert r.status_code == 201, r.text
        assert r.json()["tipo"] is None

    def test_rejeita_tipo_invalido(self, client):
        c, engine = client
        r = c.post("/cadastro/protocolos-customizados", json={
            "nome": "Tipo inválido", "categoria": "Rebanho", "tipo": "financeiro",
            "etapas": [{"dia": 0, "descricao_evento": "Aplicar produto"}],
        })
        assert r.status_code == 400

    def test_cria_com_tipo_sanitario(self, client):
        c, engine = client
        r = c.post("/cadastro/protocolos-customizados", json={
            "nome": "Cura de casco B", "categoria": "Rebanho", "tipo": "sanitario",
            "etapas": [{"dia": 0, "descricao_evento": "Aplicar produto"}, {"dia": 3, "descricao_evento": "Reaplicar"}],
        })
        assert r.status_code == 201, r.text
        assert r.json()["tipo"] == "sanitario"


class TestAgregadorCentralProtocolos:
    def _lancar_iatf(self, c, data_d0="2026-08-05"):
        return c.post("/reproducao/protocolo-iatf", json={"animais": ["700"], "data_d0": data_d0}).json()

    def _lancar_customizado(self, c, tipo="sanitario"):
        pid = c.post("/cadastro/protocolos-customizados", json={
            "nome": "Cura de casco", "categoria": "Rebanho", "tipo": tipo,
            "etapas": [{"dia": 0, "descricao_evento": "Aplicar produto"}],
        }).json()["id"]
        return c.post("/protocolos-customizados/lancar", json={
            "protocolo_id": pid, "animais": ["701"], "data_inicio": "2026-08-05",
        }).json()

    def test_iatf_entra_no_acompanhamento_como_reprodutivo(self, client):
        c, engine = client
        self._lancar_iatf(c)
        linhas = c.get("/central-protocolos/acompanhamento").json()
        assert any(l["tipo"] == "reprodutivo" and l["origem"] == "iatf" for l in linhas)

    def test_customizado_sem_tipo_fica_fora_do_agregador(self, client):
        c, engine = client
        self._lancar_customizado(c, tipo=None)
        linhas = c.get("/central-protocolos/acompanhamento").json()
        assert not any(l["origem"] == "customizado" for l in linhas)

    def test_customizado_com_tipo_entra_no_agregador(self, client):
        c, engine = client
        self._lancar_customizado(c, tipo="sanitario")
        linhas = c.get("/central-protocolos/acompanhamento").json()
        assert any(l["origem"] == "customizado" and l["tipo"] == "sanitario" for l in linhas)

    def test_filtro_por_tipo(self, client):
        c, engine = client
        self._lancar_iatf(c)
        self._lancar_customizado(c, tipo="sanitario")
        so_sanitario = c.get("/central-protocolos/acompanhamento", params={"tipo": "sanitario"}).json()
        assert all(l["tipo"] == "sanitario" for l in so_sanitario)
        assert any(l["origem"] == "customizado" for l in so_sanitario)

    def test_filtro_por_nome(self, client):
        c, engine = client
        self._lancar_iatf(c)
        achou = c.get("/central-protocolos/acompanhamento", params={"nome": "IATF"}).json()
        assert achou and all("IATF" in l["nome"].upper() for l in achou)
        vazio = c.get("/central-protocolos/acompanhamento", params={"nome": "não existe"}).json()
        assert vazio == []

    def test_iatf_concluido_sai_do_acompanhamento_e_entra_no_historico(self, client):
        c, engine = client
        resultado = self._lancar_iatf(c, data_d0="2026-01-01")
        lancamento_id = resultado["lancamento_id"]
        # Marca as 4 etapas (D0/D7/D9/D11) como realizadas direto no banco —
        # o que importa aqui é o agregador, não o fluxo de confirmação da
        # Agenda (já coberto em test_agenda_protocolo_iatf.py).
        from fazenda.models import ProtocoloIatfAplicacao
        with Session(engine) as s:
            aps = s.exec(
                __import__("sqlmodel").select(ProtocoloIatfAplicacao).where(
                    ProtocoloIatfAplicacao.lancamento_id == lancamento_id
                )
            ).all()
            for a in aps:
                a.realizada = True
                a.data_realizacao = a.data_prevista
                s.add(a)
            s.commit()

        acompanhamento = c.get("/central-protocolos/acompanhamento").json()
        assert not any(l["origem_id"] == lancamento_id and l["origem"] == "iatf" for l in acompanhamento)
        historico = c.get("/central-protocolos/historico").json()
        assert any(l["origem_id"] == lancamento_id and l["origem"] == "iatf" and l["status"] == "concluido" for l in historico)


# ─────────────────────── Detalhe: hormônios/opções + baixa com frasco ───────

def _lancar_iatf_com_hormonio(c, animais, data_d0="2026-07-08", produto="Sincrocp"):
    return c.post("/reproducao/protocolo-iatf", json={
        "animais": animais, "data_d0": data_d0,
        "hormonios": [{"dia": 0, "produto": produto, "dose": 2, "unidade": "ml", "via": "Intramuscular"}],
    }).json()


class TestDetalheOpcoesDeFrasco:
    """O detalhe do lançamento IATF (usado pela Central para "dar baixa de um
    dia") tem que expor as mesmas opções de frasco que a Agenda já mostra —
    sem isso o usuário nunca vê que há mais de um frasco do mesmo princípio
    ativo em estoque."""

    def _preparar_estoque_duplo(self, engine):
        with Session(engine) as s:
            pa = PrincipioAtivo(nome="Cloprostenol")
            s.add(pa)
            s.commit()
            s.refresh(pa)
            s.add(Estoque(nome="Sincrocp", quantidade=50, unidade="ml", principio_ativo_id=pa.id))
            s.add(Estoque(nome="Croniben", quantidade=30, unidade="ml", principio_ativo_id=pa.id))
            s.commit()

    def test_detalhe_iatf_traz_opcoes_de_frasco_por_dia(self, client):
        c, engine = client
        self._preparar_estoque_duplo(engine)
        resultado = _lancar_iatf_com_hormonio(c, ["700"])
        lancamento_id = resultado["lancamento_id"]

        det = c.get(f"/central-protocolos/iatf/{lancamento_id}").json()
        d0 = next(d for d in det["dias"] if d["dia"] == 0)
        assert d0["hormonios"], "dia D0 deveria trazer o hormônio cadastrado no lançamento"
        h = d0["hormonios"][0]
        assert h["produto"] == "Sincrocp"
        assert {o["nome"] for o in h["opcoes"]} == {"Sincrocp", "Croniben"}

    def test_dia_sem_hormonio_cadastrado_traz_lista_vazia(self, client):
        # Protocolo ad-hoc, sem molde: sem ProtocoloIatfHormonio nenhum — não
        # deve quebrar, só não tem nada para mostrar.
        c, engine = client
        resultado = c.post("/reproducao/protocolo-iatf", json={"animais": ["700"], "data_d0": "2026-07-08"}).json()
        det = c.get(f"/central-protocolos/iatf/{resultado['lancamento_id']}").json()
        for d in det["dias"]:
            assert d["hormonios"] == []

    def test_outras_origens_nao_ganham_campo_hormonios(self, client):
        # Escopo do pedido: só IATF. Indução/customizado/lida continuam como
        # estavam — sem o campo extra.
        c, engine = client
        pid = c.post("/cadastro/protocolos-customizados", json={
            "nome": "Cura de casco", "categoria": "Rebanho", "tipo": "sanitario",
            "etapas": [{"dia": 0, "descricao_evento": "Aplicar produto"}],
        }).json()["id"]
        lanc = c.post("/protocolos-customizados/lancar", json={
            "protocolo_id": pid, "animais": ["700"], "data_inicio": "2026-08-05",
        }).json()
        det = c.get(f"/central-protocolos/customizado/{lanc['lancamento_id']}").json()
        assert all("hormonios" not in d for d in det["dias"])


class TestBaixaComFrascoExplicito:
    """POST .../baixa com `medicamentos` explícito dá baixa NAQUELE frasco —
    não no hormônio cadastrado no lançamento (que é só o fallback)."""

    def _preparar_estoque_duplo(self, engine):
        with Session(engine) as s:
            pa = PrincipioAtivo(nome="Cloprostenol")
            s.add(pa)
            s.commit()
            s.refresh(pa)
            s.add(Estoque(nome="Sincrocp", quantidade=50, unidade="ml", principio_ativo_id=pa.id))
            s.add(Estoque(nome="Croniben", quantidade=30, unidade="ml", principio_ativo_id=pa.id))
            s.commit()

    def test_baixa_com_estoque_id_explicito_abate_o_frasco_escolhido(self, client):
        c, engine = client
        self._preparar_estoque_duplo(engine)
        resultado = _lancar_iatf_com_hormonio(c, ["700"], produto="Sincrocp")
        lancamento_id = resultado["lancamento_id"]

        with Session(engine) as s:
            croniben_id = s.exec(select(Estoque).where(Estoque.nome == "Croniben")).first().id

        r = c.post(f"/central-protocolos/iatf/{lancamento_id}/baixa", json={
            "dia": 0,
            "medicamentos": [{"produto": "Croniben", "estoque_id": croniben_id, "dose": 2, "unidade": "ml", "via": "Intramuscular"}],
        })
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            sincro = s.exec(select(Estoque).where(Estoque.nome == "Sincrocp")).first()
            croniben = s.exec(select(Estoque).where(Estoque.nome == "Croniben")).first()
            # Baixou do frasco ESCOLHIDO (Croniben) — o hormônio cadastrado no
            # lançamento (Sincrocp) nunca é tocado quando `medicamentos` vem.
            assert croniben.quantidade == 30 - 2
            assert sincro.quantidade == 50


# ─────────────────────────────── Renomear ────────────────────────────────

class TestRenomearProtocolo:
    def test_renomeia_o_nome_protocolo(self, client):
        c, engine = client
        resultado = _lancar_iatf_com_hormonio(c, ["700"])
        lancamento_id = resultado["lancamento_id"]
        r = c.patch(f"/central-protocolos/iatf/{lancamento_id}/renomear", json={"nome": "Lote A renomeado"})
        assert r.status_code == 200, r.text
        assert r.json()["nome"] == "Lote A renomeado"
        det = c.get(f"/central-protocolos/iatf/{lancamento_id}").json()
        assert det["nome"] == "Lote A renomeado"

    def test_nome_vazio_da_400(self, client):
        c, engine = client
        resultado = _lancar_iatf_com_hormonio(c, ["700"])
        lancamento_id = resultado["lancamento_id"]
        r = c.patch(f"/central-protocolos/iatf/{lancamento_id}/renomear", json={"nome": "   "})
        assert r.status_code == 400

    def test_nome_aparece_atualizado_no_acompanhamento(self, client):
        c, engine = client
        resultado = _lancar_iatf_com_hormonio(c, ["700"])
        lancamento_id = resultado["lancamento_id"]
        c.patch(f"/central-protocolos/iatf/{lancamento_id}/renomear", json={"nome": "Nome Novo Aqui"})
        linhas = c.get("/central-protocolos/acompanhamento").json()
        linha = next(l for l in linhas if l["origem"] == "iatf" and l["origem_id"] == lancamento_id)
        assert linha["nome"] == "Nome Novo Aqui"


# ─────────────────────────── Desfazer uma aplicação ──────────────────────

class TestDesfazerAplicacao:
    """DELETE .../baixa desfaz UMA aplicação (um animal, um dia) — sem mexer
    nas outras aplicações do mesmo dia nem cancelar o lançamento inteiro."""

    def _preparar_estoque(self, engine):
        with Session(engine) as s:
            s.add(Estoque(nome="Sincrocp", quantidade=50, unidade="ml"))
            s.commit()

    def test_desfaz_uma_aplicacao_sem_afetar_a_outra(self, client):
        c, engine = client
        self._preparar_estoque(engine)
        resultado = _lancar_iatf_com_hormonio(c, ["700", "701"], produto="Sincrocp")
        lancamento_id = resultado["lancamento_id"]
        c.post(f"/central-protocolos/iatf/{lancamento_id}/baixa", json={"dia": 0})

        r = c.request("DELETE", f"/central-protocolos/iatf/{lancamento_id}/baixa", json={"dia": 0, "numero_matriz": "700"})
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            aps = s.exec(
                select(ProtocoloIatfAplicacao).where(
                    ProtocoloIatfAplicacao.lancamento_id == lancamento_id, ProtocoloIatfAplicacao.dia == 0,
                )
            ).all()
            ap_700 = next(a for a in aps if a.numero_matriz == "700")
            ap_701 = next(a for a in aps if a.numero_matriz == "701")
            assert ap_700.realizada is False
            assert ap_700.data_realizacao is None
            assert ap_701.realizada is True, "a outra aplicação do mesmo dia não pode ser desfeita junto"

    def test_estorna_so_uma_dose_nao_a_batelada_toda(self, client):
        c, engine = client
        self._preparar_estoque(engine)
        resultado = _lancar_iatf_com_hormonio(c, ["700", "701"], produto="Sincrocp")
        lancamento_id = resultado["lancamento_id"]
        c.post(f"/central-protocolos/iatf/{lancamento_id}/baixa", json={"dia": 0})

        with Session(engine) as s:
            antes = s.exec(select(Estoque).where(Estoque.nome == "Sincrocp")).first().quantidade
        assert antes == 50 - 2 * 2  # dose 2ml × 2 vacas

        c.request("DELETE", f"/central-protocolos/iatf/{lancamento_id}/baixa", json={"dia": 0, "numero_matriz": "700"})

        with Session(engine) as s:
            depois = s.exec(select(Estoque).where(Estoque.nome == "Sincrocp")).first().quantidade
        assert depois == antes + 2, "deveria estornar só UMA dose (2ml), não a batelada das 2 vacas"

    def test_desfazer_aplicacao_ja_desfeita_da_400(self, client):
        c, engine = client
        self._preparar_estoque(engine)
        resultado = _lancar_iatf_com_hormonio(c, ["700"], produto="Sincrocp")
        lancamento_id = resultado["lancamento_id"]
        c.post(f"/central-protocolos/iatf/{lancamento_id}/baixa", json={"dia": 0})
        primeira = c.request("DELETE", f"/central-protocolos/iatf/{lancamento_id}/baixa", json={"dia": 0, "numero_matriz": "700"})
        assert primeira.status_code == 200
        segunda = c.request("DELETE", f"/central-protocolos/iatf/{lancamento_id}/baixa", json={"dia": 0, "numero_matriz": "700"})
        assert segunda.status_code == 400
