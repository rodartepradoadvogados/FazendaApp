"""
API de leitura para agentes externos (Hermes) — /agente/* (somente GET).
Ver fazenda/api/routers/agente_leitura.py e fazenda/rules/agente_leitura.py.
"""
from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select, text

from fazenda.models import (
    Animal, AssistenteEnsinamento, ContaGerencial, ControleLeiteiro, Estoque, Fazenda, Lote, Secagem,
)
from fazenda.rules import agente_leitura as al
from fazenda.rules.assistente import _TOOLS_DISPONIVEIS

TOKEN = "t" * 20 + "-token-de-teste-do-agente-" + "x" * 10  # >= 32 chars
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for v in ("AGENTE_API_TOKEN", "AGENTE_FAZENDA_ID", "AGENTE_IPS_PERMITIDOS", "AGENTE_RATE_LIMIT_POR_MIN",
              "AGENTE_MAX_BYTES", "AGENTE_MODULOS"):
        monkeypatch.delenv(v, raising=False)
    al._resetar_estado_para_testes()


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Fazenda(id=1, nome="Fazenda Um"))
        s.add(Fazenda(id=2, nome="Fazenda Dois"))
        s.add(Animal(numero="500", nome="Estrela", sexo="F", fazenda_id=1, grupo_primario="04 - SECAS"))
        s.add(Animal(numero="900", nome="Intrusa", sexo="F", fazenda_id=2, grupo_primario="04 - SECAS"))
        s.add(Lote(codigo="04", nome="SECAS F1", fazenda_id=1))
        s.add(Lote(codigo="04", nome="SECAS F2 SEGREDO", fazenda_id=2))
        s.add(Estoque(nome="Ração F1", categoria="alimento", quantidade=1, estoque_minimo=9, abaixo_minimo=True, fazenda_id=1))
        s.add(Estoque(nome="Ração F2 SEGREDO", categoria="alimento", quantidade=1, estoque_minimo=9, abaixo_minimo=True, fazenda_id=2))
        s.add(ContaGerencial(tipo="despesa", valor_total=111.0, valor_pago=0.0, fazenda_id=1, data_vencimento=date(2020, 1, 1)))
        s.add(ContaGerencial(tipo="despesa", valor_total=999999.0, valor_pago=0.0, fazenda_id=2, data_vencimento=date(2020, 1, 1)))
        s.add(AssistenteEnsinamento(fazenda_id=1, usuario_id=1, titulo="Regra F1", texto="Lote 4 é de secas."))
        s.add(AssistenteEnsinamento(fazenda_id=2, usuario_id=1, titulo="Regra F2", texto="NAO VAZAR"))
        s.commit()
    return eng


@pytest.fixture
def client(engine, monkeypatch):
    import main
    import fazenda.database as database

    def _sess():
        with Session(engine) as s:
            yield s

    monkeypatch.setenv("AGENTE_API_TOKEN", TOKEN)
    main.app.dependency_overrides[database.get_session] = _sess
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Ativação e autenticação
# ---------------------------------------------------------------------------
class TestAuth:
    def test_sem_token_configurado_e_404(self, client, monkeypatch):
        monkeypatch.delenv("AGENTE_API_TOKEN")
        for rota in ("/agente/saude", "/agente/ferramentas", "/agente/instrucoes", "/agente/consultar/listar_lotes"):
            assert client.get(rota, headers=AUTH).status_code == 404, rota

    def test_token_curto_demais_mantem_desativada(self, client, monkeypatch):
        monkeypatch.setenv("AGENTE_API_TOKEN", "curto")
        assert client.get("/agente/saude", headers={"Authorization": "Bearer curto"}).status_code == 404

    def test_token_errado_401(self, client):
        r = client.get("/agente/saude", headers={"Authorization": "Bearer " + "z" * 40})
        assert r.status_code == 401
        assert "z" * 40 not in r.text

    def test_sem_cabecalho_401(self, client):
        assert client.get("/agente/saude").status_code == 401

    def test_esquema_errado_401(self, client):
        assert client.get("/agente/saude", headers={"Authorization": f"Basic {TOKEN}"}).status_code == 401

    def test_token_certo_200(self, client):
        r = client.get("/agente/saude", headers=AUTH)
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["ok"] is True and corpo["fazenda_id"] == 1 and corpo["somente_leitura"] is True
        assert TOKEN not in r.text

    def test_comparacao_em_tempo_constante(self, monkeypatch):
        usados = []
        import hmac as _hmac
        original = _hmac.compare_digest

        def espia(a, b):
            usados.append(True)
            return original(a, b)

        monkeypatch.setattr(al.hmac, "compare_digest", espia)
        monkeypatch.setenv("AGENTE_API_TOKEN", TOKEN)
        assert al.token_valido(f"Bearer {TOKEN}") is True
        assert al.token_valido("Bearer outro") is False
        assert len(usados) == 2

    def test_fazenda_inexistente_da_503_clara(self, client, monkeypatch):
        monkeypatch.setenv("AGENTE_FAZENDA_ID", "77")
        r = client.get("/agente/saude", headers=AUTH)
        assert r.status_code == 503


class TestIp:
    def test_ip_fora_da_lista_403(self, client, monkeypatch):
        monkeypatch.setenv("AGENTE_IPS_PERMITIDOS", "143.95.160.39")
        assert client.get("/agente/saude", headers=AUTH).status_code == 403

    def test_ip_permitido_via_x_forwarded_for(self, client, monkeypatch):
        monkeypatch.setenv("AGENTE_IPS_PERMITIDOS", "10.0.0.1, 143.95.160.39")
        r = client.get("/agente/saude", headers={**AUTH, "X-Forwarded-For": "143.95.160.39"})
        assert r.status_code == 200

    def test_ip_forjado_a_esquerda_do_xff_nao_vale(self, client, monkeypatch):
        """Quem manda o próprio X-Forwarded-For forjado fica à ESQUERDA; o
        proxy confiável acrescenta o IP real à DIREITA — vale o da direita."""
        monkeypatch.setenv("AGENTE_IPS_PERMITIDOS", "143.95.160.39")
        r = client.get("/agente/saude", headers={**AUTH, "X-Forwarded-For": "143.95.160.39, 8.8.8.8"})
        assert r.status_code == 403

    def test_ip_negado_antes_do_token(self, client, monkeypatch):
        monkeypatch.setenv("AGENTE_IPS_PERMITIDOS", "143.95.160.39")
        assert client.get("/agente/saude").status_code == 403


class TestRateLimit:
    def test_estoura_o_limite_por_minuto(self, client, monkeypatch):
        monkeypatch.setenv("AGENTE_RATE_LIMIT_POR_MIN", "3")
        codigos = [client.get("/agente/saude", headers=AUTH).status_code for _ in range(5)]
        assert codigos == [200, 200, 200, 429, 429]
        r = client.get("/agente/saude", headers=AUTH)
        assert "retry-after" in {k.lower() for k in r.headers}

    def test_tentativas_com_token_errado_tambem_sao_limitadas(self, client, monkeypatch):
        codigos = [client.get("/agente/saude", headers={"Authorization": "Bearer " + "q" * 40}).status_code for _ in range(14)]
        assert 429 in codigos and codigos[0] == 401
        # e o token certo continua passando (contador separado)
        assert client.get("/agente/saude", headers=AUTH).status_code == 200

    def test_padrao_e_60_por_minuto(self, monkeypatch):
        assert al.limite_por_minuto() == 60


# ---------------------------------------------------------------------------
# Somente leitura — garantia técnica
# ---------------------------------------------------------------------------
class TestSomenteLeitura:
    def test_escrita_sql_falha_na_sessao_somente_leitura(self, engine):
        with Session(engine) as s:
            gerador = al.sessao_somente_leitura(s)
            sessao = next(gerador)
            with pytest.raises(Exception) as e:
                sessao.exec(text("INSERT INTO fazenda (id, nome) VALUES (50, 'Intrusa')"))
            assert "readonly" in str(e.value).lower() or "read-only" in str(e.value).lower() or "read only" in str(e.value).lower()
            sessao.rollback()
            with pytest.raises(StopIteration):
                next(gerador)
        with Session(engine) as s:
            assert s.get(Fazenda, 50) is None

    def test_add_commit_orm_falha(self, engine):
        with Session(engine) as s:
            gerador = al.sessao_somente_leitura(s)
            sessao = next(gerador)
            sessao.add(Fazenda(id=51, nome="X"))
            with pytest.raises(Exception):
                sessao.commit()
            with pytest.raises(StopIteration):
                next(gerador)
        with Session(engine) as s:
            assert s.get(Fazenda, 51) is None

    def test_leitura_funciona_e_a_conexao_volta_ao_normal(self, engine):
        with Session(engine) as s:
            gerador = al.sessao_somente_leitura(s)
            sessao = next(gerador)
            assert sessao.exec(select(Fazenda)).all()
            with pytest.raises(StopIteration):
                next(gerador)
            # depois do dependency, a MESMA sessão/conexão pode escrever de novo (pragma restaurado)
            s.add(Fazenda(id=52, nome="Normal"))
            s.commit()
            assert s.get(Fazenda, 52) is not None

    def test_endpoint_com_ferramenta_que_tenta_escrever_nao_grava(self, client, engine, monkeypatch):
        from fazenda.rules import assistente

        def _ferramenta_maliciosa(session, usuario, entrada, fazenda_id):
            session.add(Fazenda(id=60, nome="Gravada pela ferramenta"))
            session.commit()
            return {"ok": True}

        spec = {"name": "ferramenta_escritora", "description": "teste", "input_schema": {"type": "object", "properties": {}}}
        monkeypatch.setattr(assistente, "_TOOLS_DISPONIVEIS", [*assistente._TOOLS_DISPONIVEIS, {"modulo": "indicadores", "spec": spec}])
        monkeypatch.setitem(assistente._EXECUTORES, "ferramenta_escritora", _ferramenta_maliciosa)
        monkeypatch.setitem(assistente._MODULO_DA_TOOL, "ferramenta_escritora", "indicadores")
        r = client.get("/agente/consultar/ferramenta_escritora", headers=AUTH)
        assert r.status_code >= 400
        with Session(engine) as s:
            assert s.get(Fazenda, 60) is None

    def test_nenhuma_rota_agente_aceita_escrita(self):
        from fazenda.api.routers import agente_leitura as router_mod
        rotas = list(router_mod.router.routes)
        assert len(rotas) == 4
        for r in rotas:
            assert set(r.methods) <= {"GET", "HEAD"}, (r.path, r.methods)
        # e o que o app realmente publica (openapi): só GET sob /agente
        import main
        caminhos = {c: m for c, m in main.app.openapi()["paths"].items() if c.startswith("/agente")}
        assert len(caminhos) == 4
        for c, metodos in caminhos.items():
            assert set(metodos) == {"get"}, (c, metodos)

    @pytest.mark.parametrize("metodo", ["post", "put", "patch", "delete"])
    def test_metodos_de_escrita_sao_recusados(self, client, metodo):
        r = getattr(client, metodo)("/agente/consultar/listar_lotes", headers=AUTH)
        assert r.status_code in (404, 405)
        r = getattr(client, metodo)("/agente/saude", headers=AUTH)
        assert r.status_code in (404, 405)


# ---------------------------------------------------------------------------
# Ferramentas: mesma lista do assistente, mesma implementação, isolamento
# ---------------------------------------------------------------------------
class TestFerramentas:
    def test_lista_identica_a_do_assistente(self, client):
        r = client.get("/agente/ferramentas", headers=AUTH)
        assert r.status_code == 200
        lista = r.json()["ferramentas"]
        esperado = [t["spec"] for t in _TOOLS_DISPONIVEIS]
        assert [f["nome"] for f in lista] == [e["name"] for e in esperado]
        for f, e in zip(lista, esperado):
            assert f["descricao"] == e["description"]
            assert f["parametros"] == e["input_schema"]

    def test_todas_as_ferramentas_executam(self, client):
        for t in _TOOLS_DISPONIVEIS:
            nome = t["spec"]["name"]
            params = {}
            if nome == "buscar_animal":
                params = {"numero": "500"}
            if nome == "consultar_lote":
                params = {"codigo": "04"}
            if nome == "consultar_exames":
                params = {"evento": "bruc"}
            if nome == "executar_relatorio":
                params = {"relatorio": "fluxo_lactacao", "meses": "2"}
            if nome in ("consultar_indicadores_reprodutivos", "consultar_producao_leite"):
                params = {"data_inicio": "2026-01-01", "data_fim": "2026-07-01"}
            r = client.get(f"/agente/consultar/{nome}", params=params, headers=AUTH)
            assert r.status_code == 200, (nome, r.text)
            assert "resultado" in r.json()

    def test_ferramenta_desconhecida_404(self, client):
        assert client.get("/agente/consultar/apagar_tudo", headers=AUTH).status_code == 404

    def test_parametro_obrigatorio_ausente_400(self, client):
        r = client.get("/agente/consultar/buscar_animal", headers=AUTH)
        assert r.status_code == 400 and "numero" in r.json()["detail"]

    def test_parametro_desconhecido_400(self, client):
        r = client.get("/agente/consultar/listar_lotes", params={"x": "1"}, headers=AUTH)
        assert r.status_code == 400

    def test_isolamento_por_fazenda(self, client):
        # animal de outra fazenda não aparece
        r = client.get("/agente/consultar/buscar_animal", params={"numero": "900"}, headers=AUTH)
        assert "erro" in r.json()["resultado"]
        r = client.get("/agente/consultar/buscar_animal", params={"numero": "500"}, headers=AUTH)
        assert r.json()["resultado"]["nome"] == "Estrela"
        lotes = client.get("/agente/consultar/listar_lotes", headers=AUTH).text
        assert "SECAS F1" in lotes and "SEGREDO" not in lotes
        estoque = client.get("/agente/consultar/consultar_estoque", headers=AUTH).text
        assert "Ração F1" in estoque and "SEGREDO" not in estoque
        fin = client.get("/agente/consultar/consultar_financeiro", headers=AUTH).json()["resultado"]
        assert fin["total_em_aberto_a_pagar"] == 111.0

    def test_fazenda_alvo_por_env(self, client, monkeypatch):
        monkeypatch.setenv("AGENTE_FAZENDA_ID", "2")
        r = client.get("/agente/consultar/buscar_animal", params={"numero": "900"}, headers=AUTH)
        assert r.json()["resultado"]["nome"] == "Intrusa"
        fin = client.get("/agente/consultar/consultar_financeiro", headers=AUTH).json()["resultado"]
        assert fin["total_em_aberto_a_pagar"] == 999999.0

    def test_analise_reprodutiva_nao_mistura_fazendas(self, client, engine, monkeypatch):
        from fazenda.rules import reproducao_analise
        with Session(engine) as s:
            s.add(Secagem(numero_matriz="100", data_secagem=date(2026, 1, 1), motivo="x", fazenda_id=1))
            s.add(Secagem(numero_matriz="900", data_secagem=date(2026, 1, 1), motivo="x", fazenda_id=2))
            s.add(ControleLeiteiro(numero_matriz="100", data_controle=date(2026, 1, 1), producao_kg=30, fazenda_id=1))
            s.add(ControleLeiteiro(numero_matriz="900", data_controle=date(2026, 1, 1), producao_kg=30, fazenda_id=2))
            s.commit()
        vistos = {}
        original = reproducao_analise.agregar_mensal

        def espia(registros, secagens, controles, **kw):
            vistos["secagens"] = {x["numero_matriz"] for x in secagens}
            vistos["controles"] = {x["numero_matriz"] for x in controles}
            return original(registros, secagens, controles, **kw)

        monkeypatch.setattr(reproducao_analise, "agregar_mensal", espia)
        r = client.get("/agente/consultar/consultar_analise_reprodutiva", headers=AUTH)
        assert r.status_code == 200, r.text
        assert vistos == {"secagens": {"100"}, "controles": {"100"}}

    def test_modulos_restringem_a_lista(self, client, monkeypatch):
        monkeypatch.setenv("AGENTE_MODULOS", "rebanho,estoque")
        nomes = {f["nome"] for f in client.get("/agente/ferramentas", headers=AUTH).json()["ferramentas"]}
        assert "consultar_financeiro" not in nomes and "buscar_animal" in nomes
        assert client.get("/agente/consultar/consultar_financeiro", headers=AUTH).status_code == 404


class TestInstrucoes:
    def test_base_mais_ensinamentos_ativos_da_fazenda_alvo(self, client, engine):
        from fazenda.rules.assistente import SYSTEM_PROMPT
        r = client.get("/agente/instrucoes", headers=AUTH)
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["instrucoes"].startswith(SYSTEM_PROMPT)
        assert "Regra F1: Lote 4 é de secas." in corpo["instrucoes"]
        assert "NAO VAZAR" not in r.text


# ---------------------------------------------------------------------------
# Paginação / truncamento
# ---------------------------------------------------------------------------
class TestPaginacao:
    @pytest.fixture
    def muitos(self, engine):
        with Session(engine) as s:
            for i in range(120):
                s.add(Animal(numero=f"7{i:03d}", sexo="F", fazenda_id=1, grupo_primario="04 - SECAS"))
            s.commit()

    def test_lista_grande_e_truncada_com_indicacao(self, client, muitos):
        corpo = client.get("/agente/consultar/consultar_lote", params={"codigo": "04"}, headers=AUTH).json()
        assert len(corpo["resultado"]["animais"]) == 50
        assert corpo["truncado"] is True
        assert corpo["paginacao"]["limite"] == 50 and corpo["paginacao"]["offset"] == 0
        assert corpo["paginacao"]["listas"]["animais"] == {"total": 121, "retornados": 50}
        assert corpo["resultado"]["total_animais"] == 121  # campos escalares intactos

    def test_offset_e_limite(self, client, muitos):
        corpo = client.get("/agente/consultar/consultar_lote", params={"codigo": "04", "limite": 100, "offset": 100}, headers=AUTH).json()
        assert len(corpo["resultado"]["animais"]) == 21
        assert corpo["truncado"] is False

    def test_limite_maximo(self, client, muitos):
        corpo = client.get("/agente/consultar/consultar_lote", params={"codigo": "04", "limite": 100000}, headers=AUTH).json()
        assert corpo["paginacao"]["limite"] == al.LIMITE_MAXIMO

    def test_limite_de_bytes(self, client, muitos, monkeypatch):
        monkeypatch.setenv("AGENTE_MAX_BYTES", "3000")
        r = client.get("/agente/consultar/consultar_lote", params={"codigo": "04", "limite": 200}, headers=AUTH)
        assert len(r.content) < 6000
        assert r.json()["truncado"] is True

    def test_parametro_de_paginacao_invalido_400(self, client):
        assert client.get("/agente/consultar/listar_lotes", params={"limite": "abc"}, headers=AUTH).status_code == 400


# ---------------------------------------------------------------------------
# Campos sensíveis
# ---------------------------------------------------------------------------
class TestSensiveis:
    def test_remove_chaves_sensiveis_em_qualquer_nivel(self):
        sujo = {
            "nome": "Joao", "senha_hash": "abc", "password": "x", "token": "t", "reset_senha_token": "r",
            "api_key": "k", "email": "a@b.com", "e_mail_contato": "a@b.com", "banco": "341", "agencia": "1234",
            "conta_bancaria": "99-9", "chave_pix": "x", "iban": "x", "numero_cartao": "4111", "cvv": "123",
            "aninhado": [{"usuario_email": "z@z.com", "ok": 1, "secret_key": "s"}],
        }
        limpo = al.sanitizar(sujo)
        assert limpo == {"nome": "Joao", "aninhado": [{"ok": 1}]}

    def test_mascara_cpf_cnpj_e_email_em_texto_livre(self):
        limpo = al.sanitizar({"observacoes": "Comprador CPF 123.456.789-09 e CNPJ 12.345.678/0001-90, fala com joao.silva@exemplo.com.br"})
        t = limpo["observacoes"]
        assert "123.456.789-09" not in t and "12.345.678/0001-90" not in t and "joao.silva@exemplo.com.br" not in t
        assert "***.***.***-09" in t and "**.***.***/****-90" in t

    def test_cpf_cnpj_so_digitos_em_chave_de_documento(self):
        limpo = al.sanitizar({"cpf": "12345678909", "cnpj": "12345678000190", "outro": "12345678909"})
        assert limpo["cpf"] == "***.***.***-09" and limpo["cnpj"] == "**.***.***/****-90"
        assert limpo["outro"] == "12345678909"  # sem chave de documento nem formatação: não é tocado

    def test_na_resposta_http(self, client, engine):
        with Session(engine) as s:
            a = s.exec(select(Animal).where(Animal.numero == "500")).first()
            a.observacoes = "Vendedor CPF 123.456.789-09 (vendedor@exemplo.com)"
            s.add(a)
            s.commit()
        r = client.get("/agente/consultar/buscar_animal", params={"numero": "500"}, headers=AUTH)
        assert "123.456.789-09" not in r.text and "vendedor@exemplo.com" not in r.text


# ---------------------------------------------------------------------------
# Auditoria
# ---------------------------------------------------------------------------
class TestAuditoria:
    def test_registra_chamada_sem_token(self, client, caplog):
        with caplog.at_level("INFO", logger="fazenda.agente_auditoria"):
            client.get("/agente/consultar/buscar_animal", params={"numero": "500"}, headers={**AUTH, "X-Forwarded-For": "143.95.160.39"})
            client.get("/agente/consultar/buscar_animal", params={"numero": "500"}, headers={"Authorization": "Bearer " + "w" * 40})
        texto = caplog.text
        assert "ferramenta=buscar_animal" in texto and "numero" in texto
        assert "ip=143.95.160.39" in texto and "status=200" in texto and "status=401" in texto
        assert "duracao_ms=" in texto
        assert TOKEN not in texto and "w" * 40 not in texto
        ultimas = al.ultimas_chamadas()
        assert ultimas[-1]["status"] == 401 and ultimas[-2]["status"] == 200
        assert TOKEN not in json.dumps(ultimas)

    def test_desativada_nao_audita_nem_vaza(self, client, monkeypatch, caplog):
        monkeypatch.delenv("AGENTE_API_TOKEN")
        with caplog.at_level("INFO", logger="fazenda.agente_auditoria"):
            assert client.get("/agente/saude").status_code == 404
