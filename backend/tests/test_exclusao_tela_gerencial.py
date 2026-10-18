"""Excluir lançamento (tela gerencial, 3 passos): o que a tela passou a usar do servidor.

- GET /exclusoes/tipos devolve dominio/plural/dica (e cadastro/contagem/sem_filtro_data) para TODO tipo, inclusive os do
  REGISTRO (antes chegavam sem META e a tela os jogava em "Outros");
- GET /exclusoes/buscar devolve `data` (AAAA-MM-DD) em cada item (a coluna Data/ordenação da tabela);
- diagnóstico: o impacto traz as linhas de `reverter` (situação reprodutiva) e o risco sobe a "médio" na prévia E na
  confirmação (o servidor repete a exigência de motivo);
- lote (itens[] ≤ 50, só admin): ficha de animal no lote é risco alto também na confirmação.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, ContratoFazenda, ContratoFazendaModulo, Fazenda, Lote, Parto, Servico
from fazenda.models.planos import MODULOS_COMERCIAIS

HOJE = date.today()


class _Admin:
    id = 1
    papel = "admin"
    ativo = True
    username = "admin-teste"
    permissoes = ""


class _Operador:
    id = 2
    papel = "operador"
    ativo = True
    username = "operador-teste"
    permissoes = ""


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    with Session(engine) as s:
        for fid in (1, 2):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    def _sessao():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import exigir_admin, get_current_user, get_fazenda_atual_id

    main.app.dependency_overrides[database.get_session] = _sessao
    main.app.dependency_overrides[get_current_user] = lambda: _Admin()
    main.app.dependency_overrides[exigir_admin] = lambda: _Admin()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _como(usuario):
    import main
    from fazenda.auth import get_current_user

    main.app.dependency_overrides[get_current_user] = lambda: usuario()


def _servico(engine, numero, dias_atras, fazenda_id=1, **kw):
    with Session(engine) as s:
        s.add(Animal(numero=numero, categoria_abrev="Vaca", sexo="F", ativo=True, fazenda_id=fazenda_id))
        s.add(Servico(numero_matriz=numero, data_servico=HOJE - timedelta(days=dias_atras), ult_ocorrencia=1, fazenda_id=fazenda_id, **kw))
        s.commit()


# ── GET /exclusoes/tipos ────────────────────────────────────────────────────────────────────────────────────────────
class TestTipos:
    def test_todo_tipo_chega_com_dominio_plural_e_dica(self, client):
        c, _ = client
        tipos = c.get("/exclusoes/tipos").json()
        assert len(tipos) >= 35
        sem_meta = [t["id"] for t in tipos if not (t.get("dominio") and t.get("plural") and t.get("dica"))]
        assert sem_meta == [], f"tipos sem META_TIPOS (a tela os jogaria em 'Outros'): {sem_meta}"
        for t in tipos:
            assert isinstance(t["sem_filtro_data"], bool)
            assert "contagem" in t

    def test_tipos_do_registro_tem_o_dominio_certo(self, client):
        c, _ = client
        por_id = {t["id"]: t for t in c.get("/exclusoes/tipos").json()}
        assert por_id["secagem"]["dominio"] == "reb"
        assert por_id["movimento_lote"]["dominio"] == "reb"
        assert por_id["exame_resultado"]["dominio"] == "san"
        assert por_id["diaria"]["dominio"] == "pes"
        assert por_id["safra"]["cadastro"] is True
        # sem `cadastro` E dominio "cad" o bloco sumia da tela (a grade principal ignora "cad"):
        assert por_id["evento_manual"]["dominio"] == "reb"
        assert all(t["dominio"] != "cad" for t in por_id.values() if not t.get("cadastro") and t["id"] != "todos_lancamentos")

    def test_contagem_por_fazenda_inclusive_diagnostico(self, client):
        c, engine = client
        _servico(engine, "11153", 40, diagnostico="POSITIVO", data_diagnostico=HOJE,
                 diagnostico_reconfirmacao="POSITIVO", data_reconfirmacao=HOJE)  # 2 exames num serviço
        _servico(engine, "3335", 30, diagnostico="NEGATIVO", data_diagnostico=HOJE)  # +1
        _servico(engine, "9999", 30, fazenda_id=2, diagnostico="POSITIVO", data_diagnostico=HOJE)  # outra fazenda
        with Session(engine) as s:
            s.add(Lote(codigo="02", nome="02 - Vacas Alta", fazenda_id=1))
            s.add(Lote(codigo="09", nome="Outro", fazenda_id=2))
            s.commit()
        por_id = {t["id"]: t for t in c.get("/exclusoes/tipos").json()}
        assert por_id["diagnostico"]["contagem"] == 3
        assert por_id["servico"]["contagem"] == 2
        assert por_id["lote"]["contagem"] == 1
        assert por_id["parto"]["contagem"] == 0
        assert por_id["todos_lancamentos"]["contagem"] is None  # soma parcial enganaria: fica "—" na tela


# ── GET /exclusoes/buscar → `data` ──────────────────────────────────────────────────────────────────────────────────
class TestBuscarExpoeData:
    def test_diagnostico_devolve_data_iso_e_nao_vaza_o_campo_interno(self, client):
        c, engine = client
        _servico(engine, "11153", 40, diagnostico="POSITIVO", data_diagnostico=HOJE)
        itens = c.get("/exclusoes/buscar", params={"tipo": "diagnostico"}).json()
        assert itens[0]["data"] == HOJE.isoformat()
        assert "_data" not in itens[0]

    def test_servico_e_todos_lancamentos_trazem_data_e_tipo_real(self, client):
        c, engine = client
        _servico(engine, "11153", 40, diagnostico="POSITIVO", data_diagnostico=HOJE)
        assert c.get("/exclusoes/buscar", params={"tipo": "servico"}).json()[0]["data"] == (HOJE - timedelta(days=40)).isoformat()
        todos = c.get("/exclusoes/buscar", params={"tipo": "todos_lancamentos"}).json()
        assert all("_data" not in i and "data" in i and i["tipo_real"] for i in todos)
        assert todos[0]["data"] == HOJE.isoformat() and todos[0]["tipo_real"] == "diagnostico"

    def test_cadastro_sem_data_devolve_null(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Lote(codigo="02", nome="02 - Vacas Alta", fazenda_id=1))
            s.commit()
        itens = c.get("/exclusoes/buscar", params={"tipo": "lote"}).json()
        assert itens and itens[0]["data"] is None


# ── POST /exclusoes/impacto e /confirmar — diagnóstico ───────────────────────────────────────────────────────────────
class TestImpactoDiagnostico:
    def _id(self, c, exame):
        return next(i["id"] for i in c.get("/exclusoes/buscar", params={"tipo": "diagnostico"}).json() if i["id"].endswith(exame))

    def test_toque_tem_reverter_da_situacao_reprodutiva_e_risco_medio(self, client):
        c, engine = client
        _servico(engine, "11153", 40, diagnostico="POSITIVO", data_diagnostico=HOJE, metodo_diagnostico="Palpação")
        r = c.post("/exclusoes/impacto", json={"tipo": "diagnostico", "id": self._id(c, ":toque")}).json()
        assert [l["titulo"] for l in r["reverter"]] == ["Situação reprodutiva de 11153"]
        assert "«a tocar»" in r["reverter"][0]["consequencia"] and r["reverter"][0]["chip"] == "Mexe na reprodução"
        assert r["risco"] == "medio" and r["porque"]
        assert r["apagar"] and not r["bloqueia"]

    def test_retoque_e_perda_descrevem_a_volta_certa(self, client):
        c, engine = client
        _servico(engine, "11153", 90, diagnostico="POSITIVO", data_diagnostico=HOJE - timedelta(days=55),
                 diagnostico_reconfirmacao="POSITIVO", data_reconfirmacao=HOJE - timedelta(days=20), retoque=False)
        ret = c.post("/exclusoes/impacto", json={"tipo": "diagnostico", "id": self._id(c, ":reconfirmacao")}).json()
        assert "«a reconfirmar»" in ret["reverter"][0]["consequencia"]
        with Session(engine) as s:
            sv = s.exec(select(Servico)).one()
            sv.data_perda_prenhez, sv.motivo_perda_prenhez = HOJE - timedelta(days=5), "aborto"
            s.add(sv)
            s.commit()
        perda = c.post("/exclusoes/impacto", json={"tipo": "diagnostico", "id": self._id(c, ":perda")}).json()
        assert "prenhez volta a valer" in perda["reverter"][0]["consequencia"]

    def test_o_servidor_repete_a_exigencia_de_motivo_do_risco_medio(self, client):
        c, engine = client
        _servico(engine, "11153", 40, diagnostico="POSITIVO", data_diagnostico=HOJE)
        sid = self._id(c, ":toque")
        sem_motivo = c.post("/exclusoes/confirmar", json={"tipo": "diagnostico", "id": sid})
        assert sem_motivo.status_code == 422 and sem_motivo.json()["detail"]["codigo"] == "motivo_obrigatorio"
        ok = c.post("/exclusoes/confirmar", json={"tipo": "diagnostico", "id": sid, "motivo": "lançado no animal errado"})
        assert ok.status_code == 200 and ok.json()["status"] == "excluido" and ok.json()["comprovante"].startswith("EX-")
        with Session(engine) as s:
            assert s.exec(select(Servico)).one().diagnostico is None  # ida e volta: a tela pediu, o servidor desfez

    def test_operador_gera_pedido_com_o_mesmo_item(self, client):
        c, engine = client
        _servico(engine, "11153", 40, diagnostico="POSITIVO", data_diagnostico=HOJE)
        sid = self._id(c, ":toque")
        _como(_Operador)
        r = c.post("/exclusoes/confirmar", json={"tipo": "diagnostico", "id": sid, "motivo": "errei"})
        assert r.status_code == 200 and r.json()["status"] == "solicitado"
        again = c.post("/exclusoes/confirmar", json={"tipo": "diagnostico", "id": sid, "motivo": "errei"})
        assert again.json()["status"] == "ja_pedido"
        with Session(engine) as s:
            assert s.exec(select(Servico)).one().diagnostico == "POSITIVO"  # nada foi desfeito


# ── Lote ────────────────────────────────────────────────────────────────────────────────────────────────────────────
class TestLote:
    def _dois_toques(self, engine):
        _servico(engine, "11153", 40, diagnostico="POSITIVO", data_diagnostico=HOJE)
        _servico(engine, "3335", 40, diagnostico="NEGATIVO", data_diagnostico=HOJE - timedelta(days=1))

    def _itens(self, c):
        return [{"tipo": "diagnostico", "id": i["id"]} for i in c.get("/exclusoes/buscar", params={"tipo": "diagnostico"}).json()]

    def test_impacto_e_confirmacao_do_lote_de_diagnosticos(self, client):
        c, engine = client
        self._dois_toques(engine)
        itens = self._itens(c)
        imp = c.post("/exclusoes/impacto", json={"itens": itens}).json()
        assert len(imp["reverter"]) == 2 and imp["risco"] == "medio"
        sem = c.post("/exclusoes/confirmar", json={"itens": itens})
        assert sem.status_code == 422 and sem.json()["detail"]["codigo"] == "motivo_obrigatorio"
        ok = c.post("/exclusoes/confirmar", json={"itens": itens, "motivo": "lote errado"})
        assert ok.status_code == 200 and ok.json()["status"] == "excluido"
        with Session(engine) as s:
            assert all(sv.diagnostico is None for sv in s.exec(select(Servico)).all())
            assert len(s.exec(select(Servico)).all()) == 2  # as inseminações ficaram

    def test_mais_de_50_itens_e_422_com_limite(self, client):
        c, _ = client
        itens = [{"tipo": "diagnostico", "id": f"{i}:toque"} for i in range(51)]
        for rota in ("/exclusoes/impacto", "/exclusoes/confirmar"):
            r = c.post(rota, json={"itens": itens, "motivo": "x"})
            assert r.status_code == 422 and r.json()["detail"] == {"codigo": "lote_grande", "limite": 50}

    def test_lote_e_exclusivo_do_administrador(self, client):
        c, engine = client
        self._dois_toques(engine)
        itens = self._itens(c)
        _como(_Operador)
        assert c.post("/exclusoes/confirmar", json={"itens": itens, "motivo": "x"}).status_code == 403

    def test_ficha_de_animal_no_lote_e_risco_alto_tambem_na_confirmacao(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="7001", categoria_abrev="Novilha", sexo="F", ativo=True, fazenda_id=1))
            s.commit()
            animal_id = s.exec(select(Animal)).one().numero
        itens = [{"tipo": "animal", "id": animal_id}]
        previa = c.post("/exclusoes/impacto", json={"itens": itens}).json()
        assert previa["risco"] == "alto"
        # sem a confirmação digitada o servidor recusa (antes um lote de 1 animal passava só com motivo)
        r = c.post("/exclusoes/confirmar", json={"itens": itens, "motivo": "duplicada"})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "confirmacao_invalida"
        ok = c.post("/exclusoes/confirmar", json={"itens": itens, "motivo": "duplicada", "confirmacao": "APAGAR"})
        assert ok.status_code == 200


# ── Pedido de não-admin: o segundo operador APOIA o pedido do primeiro ───────────────────────────────────────────────
def test_apoio_devolve_quem_pediu_primeiro(client):
    c, engine = client
    _servico(engine, "11153", 40, diagnostico="POSITIVO", data_diagnostico=HOJE)
    sid = c.get("/exclusoes/buscar", params={"tipo": "diagnostico"}).json()[0]["id"]

    class _Outro(_Operador):
        id = 3
        username = "outro-operador"

    _como(_Operador)
    assert c.post("/exclusoes/confirmar", json={"tipo": "diagnostico", "id": sid, "motivo": "errei"}).json()["status"] == "solicitado"
    _como(_Outro)
    r = c.post("/exclusoes/confirmar", json={"tipo": "diagnostico", "id": sid, "motivo": "também"}).json()
    assert r["status"] == "apoiado" and r["solicitado_por"] == "operador-teste"


def test_lote_com_duas_parcelas_da_mesma_nota_apaga_a_nota_uma_vez(client):
    """Apagar UMA parcela leva a nota inteira (todas as irmãs). Duas parcelas da mesma nota no lote não podem repetir
    o objeto na lista de exclusão (a segunda exclusão do mesmo objeto estourava)."""
    from fazenda.models import ContaGerencial

    c, engine = client
    with Session(engine) as s:
        for i in (1, 2, 3):
            s.add(ContaGerencial(id=i, numero_lancamento="LC-2026-N", fazenda_id=1, descricao="Nota", valor_total=10.0,
                                 parcela_num=i, parcela_total=3))
        s.commit()
    itens = [{"tipo": "financeiro", "id": "1"}, {"tipo": "financeiro", "id": "2"}]
    r = c.post("/exclusoes/confirmar", json={"itens": itens, "motivo": "nota duplicada"})
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.exec(select(ContaGerencial)).all() == []
