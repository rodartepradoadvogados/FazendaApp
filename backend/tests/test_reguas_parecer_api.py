"""Réguas de referência pela API, com as exigências do parecer jurídico de 08/10/2026:
nenhuma faixa vaza fora de "publicada", aceite do modal "Entendi" append-only e com
hash vigente, isolamento entre fazendas e entre usuários, exportação com réguas só
com o parâmetro da fazenda e autorização, e "Reportar erro na faixa"."""
from __future__ import annotations

import copy
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, delete, select, update

import fazenda.database as database
from fazenda.auth import EMAIL_DONO
from fazenda.models import (
    AceiteTermos, ContratoFazenda, ContratoFazendaModulo, ExportacaoRelatorioLog, Fazenda, ParametroFazenda,
    ReguaErroReportado, Usuario, UsuarioFazenda,
)
from fazenda.models.juridico import RegistroImutavelError
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules import reguas_referencia as rr
from fazenda.rules import textos_juridicos as tj
from fazenda.rules.parametros import seed_parametros

BACKEND = Path(__file__).resolve().parent.parent
HOJE = date(2026, 10, 9)


class _Hoje(date):
    @classmethod
    def today(cls):
        return HOJE


@pytest.fixture(autouse=True)
def _relogio(monkeypatch):
    monkeypatch.setattr(rr, "date", _Hoje)


@pytest.fixture
def ambiente():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    ids = {}
    with Session(engine) as s:
        for fid in (1, 2):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}", ativa=True))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()
        for nome, papel, fid, extra in (
            ("admin1", "admin", 1, {}), ("oper1", "operador", 1, {}), ("admin2", "admin", 2, {}),
            ("contador1", "operador", 1, {"contador": True}),
        ):
            u = Usuario(username=nome, senha_hash="x", papel=papel, permissoes="financeiro", ativo=True)
            s.add(u)
            s.commit()
            s.refresh(u)
            s.add(UsuarioFazenda(usuario_id=u.id, fazenda_id=fid, **extra))
            ids[nome] = u.id
        dono = Usuario(username="dono", senha_hash="x", papel="admin", ativo=True, email=EMAIL_DONO)
        s.add(dono)
        s.commit()
        ids["dono"] = dono.id
        seed_parametros(s)

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    estado = {"usuario": ids["admin1"], "fid": 1}

    def _sessao():
        with Session(engine) as s:
            yield s

    def _usuario():
        with Session(engine) as s:
            return s.get(Usuario, estado["usuario"])

    main.app.dependency_overrides[database.get_session] = _sessao
    main.app.dependency_overrides[get_current_user] = _usuario
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: estado["fid"]

    def como(nome, fid):
        estado["usuario"], estado["fid"] = ids[nome], fid

    yield TestClient(main.app), engine, como, ids
    main.app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Dados de teste: régua "comida_receita" pronta, empresa constituída
# ---------------------------------------------------------------------------
def _publicado():
    d = copy.deepcopy(rr.carregar())
    r = next(x for x in d["reguas"] if x["codigo"] == "comida_receita")
    dos = r["dossie"]
    dos["fonte_br"]["pagina_ou_tabela"] = "Tabela 2"
    dos["validado_por"] = [{"nome": "Dono", "em": "2026-10-09", "faixa": copy.deepcopy(r["faixa"])},
                           {"nome": "Alexandre Scarpa", "em": "2026-10-09", "faixa": copy.deepcopy(r["faixa"])}]
    dos["pendente_de"] = []
    dos["termos_verificados_em"] = "2026-10-09"
    for f in d["fontes"]:
        if f["id"] in r["fontes"]:
            f.update(termos_verificados_em="2026-10-09", uso_comercial_confirmado_em="2026-10-09")
            if f["licenca"] == "nao_verificada":
                f["licenca"] = "citar_com_link"
    d["publicacao"].update(liberada=True, liberada_por="Dono", liberada_em="2026-10-09")
    return d


def _textos_com_empresa():
    t = copy.deepcopy(tj.carregar())
    t["empresa"].update(razao_social="CowData Tecnologia Ltda.", cnpj="00.000.000/0001-00",
                        email_responsavel="reguas@cowdata.example")
    return t


@pytest.fixture
def publicado(monkeypatch):
    d, t = _publicado(), _textos_com_empresa()
    monkeypatch.setattr(rr, "carregar", lambda: copy.deepcopy(d))
    monkeypatch.setattr(tj, "dados_padrao", lambda: t)
    assert rr.validar(d, hoje=HOJE, textos=t) == []
    return d


def _numeros_das_faixas() -> set[float]:
    return {float(v) for r in rr.carregar()["reguas"] for v in (r.get("faixa") or {}).values()}


NUMERO = re.compile(r"(?<![\w/.,:-])(\d+(?:[.,]\d+)?)(?![\w/:])")


def _vazamentos(corpo) -> list:
    """Todo número de faixa que aparece na resposta, fora dos textos jurídicos
    (estáticos, conferidos por hash) e de URLs/hashes."""
    alvo, achados = _numeros_das_faixas(), []

    def _anda(x, chave=""):
        if chave in ("textos", "url", "sha256") or chave.endswith("_utc"):
            return
        if isinstance(x, dict):
            for k, v in x.items():
                _anda(v, k)
        elif isinstance(x, list):
            for v in x:
                _anda(v, chave)
        elif isinstance(x, bool) or x is None:
            return
        elif isinstance(x, (int, float)):
            if float(x) in alvo:
                achados.append((chave, x))
        elif isinstance(x, str):
            for m in NUMERO.findall(x):
                if float(m.replace(",", ".")) in alvo:
                    achados.append((chave, x))
    _anda(corpo)
    return achados


def _aceitar(c):
    a = c.get("/financeiro/reguas-referencia/aceite").json()
    return c.post("/financeiro/reguas-referencia/aceite", json={"versao": a["versao"], "sha256": a["sha256"]})


# ---------------------------------------------------------------------------
# Nenhuma faixa vaza
# ---------------------------------------------------------------------------
def test_estado_versionado_nao_vaza_numero_de_faixa(ambiente):
    c, *_ = ambiente
    r = c.get("/financeiro/reguas-referencia")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["publicacao"]["liberada"] is False and corpo["empresa_pendente"] is True
    assert corpo["aceite_pendente"] is True
    assert {x["situacao"] for x in corpo["reguas"]} <= {"em_validacao", "sem_faixa"}
    assert _vazamentos(corpo) == []
    # Nem depois do "Entendi": o que segura é a publicação, não o aceite.
    assert _aceitar(c).status_code == 201
    corpo = c.get("/financeiro/reguas-referencia").json()
    assert corpo["aceite_pendente"] is False and _vazamentos(corpo) == []


def test_publicada_so_aparece_depois_do_aceite(ambiente, publicado):
    c, *_ = ambiente
    antes = c.get("/financeiro/reguas-referencia").json()
    assert antes["aceite_pendente"] is True and antes["faixas_ocultas_ate_aceite"] is True
    assert _vazamentos(antes) == []
    assert _aceitar(c).status_code == 201
    depois = c.get("/financeiro/reguas-referencia").json()
    comida = next(x for x in depois["reguas"] if x["codigo"] == "comida_receita")
    assert comida["situacao"] == "publicada" and comida["faixa"]["max"] == 55
    # O detector acha o número quando ele está lá (prova de que o teste acima vale).
    assert any(ch == "max" for ch, _ in _vazamentos(depois))
    outras = [x for x in depois["reguas"] if x["codigo"] != "comida_receita"]
    assert _vazamentos({"reguas": outras}) == []


@pytest.mark.parametrize("desligar", ["global", "regua", "fonte"])
def test_interruptores_tiram_a_faixa_da_api(ambiente, publicado, monkeypatch, desligar):
    c, *_ = ambiente
    assert _aceitar(c).status_code == 201
    d = copy.deepcopy(publicado)
    if desligar == "global":
        d["publicacao"]["liberada"] = False
    elif desligar == "regua":
        next(x for x in d["reguas"] if x["codigo"] == "comida_receita")["ativa"] = False
    else:
        for f in d["fontes"]:
            if f["origem"] == "internacional":
                f["ativa"] = False
    monkeypatch.setattr(rr, "carregar", lambda: copy.deepcopy(d))
    corpo = c.get("/financeiro/reguas-referencia").json()
    comida = next(x for x in corpo["reguas"] if x["codigo"] == "comida_receita")
    assert comida["situacao"] == ("em_validacao" if desligar == "global" else "retirada")
    assert comida["faixa"] is None
    # O modal mudou (sem régua publicada, sai o trecho do método): aceite novo.
    assert corpo["aceite_pendente"] is True
    assert _vazamentos(corpo) == []


# ---------------------------------------------------------------------------
# Aceites
# ---------------------------------------------------------------------------
def test_aceite_exige_versao_e_hash_vigentes(ambiente):
    c, engine, _como, ids = ambiente
    a = c.get("/financeiro/reguas-referencia/aceite").json()
    assert a["pendente"] is True and a["texto"]["botao"] == "Entendi"
    r = c.post("/financeiro/reguas-referencia/aceite", json={"versao": a["versao"], "sha256": "0" * 64})
    assert r.status_code == 409
    r = c.post("/financeiro/reguas-referencia/aceite", json={"versao": "99", "sha256": a["sha256"]})
    assert r.status_code == 409
    r = c.post("/financeiro/reguas-referencia/aceite", json={"versao": a["versao"], "sha256": a["sha256"]},
               headers={"user-agent": "Navegador/1.0 " + "x" * 600, "x-forwarded-for": "203.0.113.9, 198.51.100.7"})
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["tipo"] == "reguas" and corpo["sha256"] == a["sha256"] and corpo["criado_em_utc"].endswith("Z")
    assert corpo["ip"] == "198.51.100.7" and len(corpo["user_agent"]) == 512
    with Session(engine) as s:
        linha = s.exec(select(AceiteTermos)).one()
        assert (linha.usuario_id, linha.fazenda_id) == (ids["admin1"], 1)


def test_aceite_generico_e_termos_pendentes(ambiente):
    c, *_ = ambiente
    vig = c.get("/aceites/vigentes").json()
    assert set(vig) == {"geral", "clausula", "reguas"}
    assert vig["geral"]["disponivel_para_aceite"] is False and vig["reguas"]["pendente_para_mim"] is True
    r = c.post("/aceites", json={"tipo": "geral", "versao": vig["geral"]["versao"], "sha256": vig["geral"]["sha256"]})
    assert r.status_code == 409 and "Termos de Uso" in r.json()["detail"]
    r = c.post("/aceites", json={"tipo": "reguas", "versao": vig["reguas"]["versao"], "sha256": vig["reguas"]["sha256"]})
    assert r.status_code == 201
    assert c.get("/aceites/vigentes").json()["reguas"]["pendente_para_mim"] is False


def test_texto_novo_pede_aceite_novo(ambiente, monkeypatch):
    c, *_ = ambiente
    assert _aceitar(c).status_code == 201
    assert c.get("/financeiro/reguas-referencia").json()["aceite_pendente"] is False
    monkeypatch.setattr(tj, "dados_padrao", _textos_com_empresa)  # e-mail do responsável entrou no texto
    assert c.get("/financeiro/reguas-referencia").json()["aceite_pendente"] is True


def test_aceite_isolado_por_usuario_e_por_fazenda(ambiente):
    c, engine, como, ids = ambiente
    assert _aceitar(c).status_code == 201  # admin1 na fazenda 1
    como("oper1", 1)
    assert c.get("/financeiro/reguas-referencia").json()["aceite_pendente"] is True
    assert c.get("/aceites/comprovante").json()["aceites"] == []
    como("admin2", 2)
    assert c.get("/financeiro/reguas-referencia").json()["aceite_pendente"] is True
    assert _aceitar(c).status_code == 201
    # Comprovante: cada um vê o seu; o admin vê o de quem é da fazenda dele.
    como("admin1", 1)
    meu = c.get("/aceites/comprovante").json()
    assert [a["fazenda_id"] for a in meu["aceites"]] == [1] and meu["aceites"][0]["texto_aceito"]
    assert c.get(f"/aceites/comprovante?usuario_id={ids['oper1']}").status_code == 200
    assert c.get(f"/aceites/comprovante?usuario_id={ids['admin2']}").status_code == 404
    como("oper1", 1)
    assert c.get(f"/aceites/comprovante?usuario_id={ids['admin1']}").status_code == 403
    como("admin2", 2)
    outro = c.get("/aceites/comprovante?baixar=true")
    assert outro.status_code == 200 and "attachment" in outro.headers["content-disposition"]
    assert [a["fazenda_id"] for a in outro.json()["aceites"]] == [2]


def test_contador_registra_o_aceite(ambiente):
    c, _e, como, _ids = ambiente
    como("contador1", 1)
    assert _aceitar(c).status_code == 201


def test_aceite_e_append_only(ambiente):
    c, engine, *_ = ambiente
    assert _aceitar(c).status_code == 201
    with Session(engine) as s:
        a = s.exec(select(AceiteTermos)).one()
        a.versao = "adulterada"
        s.add(a)
        with pytest.raises(RegistroImutavelError):
            s.commit()
        s.rollback()
        s.delete(s.exec(select(AceiteTermos)).one())
        with pytest.raises(RegistroImutavelError):
            s.commit()
        s.rollback()
        with pytest.raises(RegistroImutavelError):
            s.exec(delete(AceiteTermos))
        with pytest.raises(RegistroImutavelError):
            s.exec(update(AceiteTermos).values(sha256="x"))
    # Nem SQL cru passa: gatilho no banco.
    for sql in ("UPDATE aceite_termos SET versao = 'x'", "DELETE FROM aceite_termos"):
        with pytest.raises(sa.exc.DBAPIError):
            with engine.begin() as conn:
                conn.exec_driver_sql(sql)
    with Session(engine) as s:
        assert s.exec(select(AceiteTermos)).one().versao != "adulterada"


# ---------------------------------------------------------------------------
# Exportação / compartilhamento
# ---------------------------------------------------------------------------
EXPORT = {"relatorio": "dre", "formato": "pdf", "com_reguas": True, "destinatario": "Banco do Exemplo",
          "destinatario_tipo": "banco", "finalidade": "Pedido de crédito de custeio", "autorizacao_confirmada": True}


def _ligar_exportacao(c):
    r = c.put("/parametros/permitir_exportar_com_reguas", json={"valor": True})
    assert r.status_code == 200, r.text


def test_exportar_com_reguas_desligado_por_padrao(ambiente, publicado):
    c, engine, *_ = ambiente
    assert _aceitar(c).status_code == 201
    r = c.post("/relatorios/exportacoes", json=EXPORT)
    assert r.status_code == 403 and "desligada" in r.json()["detail"]
    with Session(engine) as s:
        assert s.exec(select(ExportacaoRelatorioLog)).all() == []
    sem = c.post("/relatorios/exportacoes", json={"relatorio": "dre", "formato": "pdf"})
    assert sem.status_code == 201 and sem.json()["rodape"] is None and sem.json()["com_reguas"] is False


def test_parametro_so_admin_e_nunca_pelo_painel(ambiente):
    c, engine, como, _ids = ambiente
    como("oper1", 1)
    assert c.put("/parametros/permitir_exportar_com_reguas", json={"valor": True}).status_code == 403
    como("dono", None)
    r = c.put("/painel-cowdata/parametros/permitir_exportar_com_reguas", json={"valor": True})
    assert r.status_code == 403
    chaves = {i["chave"] for g in c.get("/painel-cowdata/parametros/").json()["grupos"].values() for i in g["itens"]}
    assert "permitir_exportar_com_reguas" not in chaves
    with Session(engine) as s:
        assert s.exec(select(ParametroFazenda).where(
            ParametroFazenda.chave == "permitir_exportar_com_reguas", ParametroFazenda.fazenda_id.is_not(None))).all() == []


def test_exportar_com_reguas_exige_destinatario_finalidade_e_autorizacao(ambiente, publicado):
    c, *_ = ambiente
    _ligar_exportacao(c)
    assert _aceitar(c).status_code == 201
    for falta in ({"destinatario": None}, {"finalidade": "  "}, {"autorizacao_confirmada": False}):
        assert c.post("/relatorios/exportacoes", json={**EXPORT, **falta}).status_code == 400


def test_exportar_com_reguas_exige_aceite_e_regua_publicada(ambiente, publicado, monkeypatch):
    c, *_ = ambiente
    _ligar_exportacao(c)
    assert c.post("/relatorios/exportacoes", json=EXPORT).status_code == 409  # aceite pendente
    assert _aceitar(c).status_code == 201
    d = copy.deepcopy(publicado)
    d["publicacao"]["liberada"] = False
    monkeypatch.setattr(rr, "carregar", lambda: copy.deepcopy(d))
    # Sem régua publicada, o modal muda (sai o trecho do método) e pede aceite novo.
    assert _aceitar(c).status_code == 201
    r = c.post("/relatorios/exportacoes", json=EXPORT)
    assert r.status_code == 409 and "publicada" in r.json()["detail"]


def test_exportar_com_reguas_registra_e_devolve_rodape(ambiente, publicado):
    c, engine, como, ids = ambiente
    _ligar_exportacao(c)
    assert _aceitar(c).status_code == 201
    r = c.post("/relatorios/exportacoes", json=EXPORT)
    assert r.status_code == 201, r.text
    corpo = r.json()
    rod = corpo["rodape"]
    assert rod["texto"].startswith("Este relatório contém faixas de referência de mercado")
    assert "com autorização para Banco do Exemplo" in rod["texto"] and "por admin1" in rod["texto"]
    assert "Versão das réguas: 2026-10 (revisada em 08/10/2026)." in rod["texto"]
    assert corpo["versao_reguas"] == "2026-10 (revisada em 08/10/2026)" and corpo["rodape_sha256"] == rod["sha256"]
    log = c.get("/relatorios/exportacoes").json()
    assert len(log) == 1 and log[0]["com_reguas"] is True and log[0]["usuario"]["username"] == "admin1"
    assert log[0]["destinatario"] == "Banco do Exemplo" and log[0]["finalidade"] == "Pedido de crédito de custeio"
    como("oper1", 1)
    assert c.get("/relatorios/exportacoes").status_code == 403
    como("admin2", 2)
    assert c.get("/relatorios/exportacoes").json() == []
    assert c.post("/relatorios/exportacoes", json=EXPORT).status_code == 403  # parâmetro é por fazenda
    with Session(engine) as s:
        e = s.exec(select(ExportacaoRelatorioLog)).one()
        e.destinatario = "outro"
        s.add(e)
        with pytest.raises(RegistroImutavelError):
            s.commit()


# ---------------------------------------------------------------------------
# Reportar erro e Painel CowData
# ---------------------------------------------------------------------------
def test_reportar_erro_e_fila_do_operador(ambiente):
    c, engine, como, ids = ambiente
    r = c.post("/financeiro/reguas-referencia/reportar-erro",
               json={"regua_codigo": "comida_receita", "texto": "A fonte da Penn State mede só vacas em lactação."})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "aberto" and r.json()["versao_reguas"].startswith("2026-10")
    assert c.post("/financeiro/reguas-referencia/reportar-erro",
                  json={"regua_codigo": "nao_existe", "texto": "abc"}).status_code == 404
    assert c.post("/financeiro/reguas-referencia/reportar-erro",
                  json={"regua_codigo": "comida_receita", "texto": "x" * 1001}).status_code == 422
    como("contador1", 1)
    assert c.post("/financeiro/reguas-referencia/reportar-erro",
                  json={"regua_codigo": "coe_receita", "texto": "Conferir o ano."}).status_code == 201
    como("admin1", 1)
    assert c.get("/painel-cowdata/reguas-referencia/erros").status_code == 403
    como("dono", None)
    fila = c.get("/painel-cowdata/reguas-referencia/erros").json()
    assert {e["regua_codigo"] for e in fila} == {"comida_receita", "coe_receita"}
    assert all(e["fazenda"]["nome"] == "Fazenda 1" for e in fila)
    alvo = next(e for e in fila if e["regua_codigo"] == "comida_receita")
    r = c.patch(f"/painel-cowdata/reguas-referencia/erros/{alvo['id']}",
                json={"status": "resolvido", "resposta": "Ressalva já cita a diferença."})
    assert r.status_code == 200 and r.json()["status"] == "resolvido"
    assert len(c.get("/painel-cowdata/reguas-referencia/erros?status=aberto").json()) == 1


def test_painel_diagnostico_e_comprovante(ambiente):
    c, _e, como, ids = ambiente
    assert _aceitar(c).status_code == 201
    como("dono", None)
    diag = c.get("/painel-cowdata/reguas-referencia/diagnostico").json()
    assert diag["liberada_efetiva"] is False and diag["empresa_pendente"] is True
    comida = next(r for r in diag["reguas"] if r["codigo"] == "comida_receita")
    assert comida["situacao"] == "em_validacao" and comida["motivos"]
    comp = c.get(f"/painel-cowdata/reguas-referencia/aceites/comprovante?usuario_id={ids['admin1']}&fazenda_id=1").json()
    assert len(comp["aceites"]) == 1 and comp["aceites"][0]["ip"]
    como("admin1", 1)
    assert c.get("/painel-cowdata/reguas-referencia/diagnostico").status_code == 403


def test_escritas_novas_nunca_deixam_fazenda_id_nulo(ambiente, publicado):
    c, engine, *_ = ambiente
    _ligar_exportacao(c)
    assert _aceitar(c).status_code == 201
    assert c.post("/relatorios/exportacoes", json=EXPORT).status_code == 201
    assert c.post("/financeiro/reguas-referencia/reportar-erro",
                  json={"regua_codigo": "comida_receita", "texto": "teste"}).status_code == 201
    with engine.connect() as conn:
        for tabela in ("aceite_termos", "exportacao_relatorio_log", "regua_erro_reportado"):
            assert conn.exec_driver_sql(f"SELECT COUNT(*) FROM {tabela}").scalar() >= 1
            assert conn.exec_driver_sql(f"SELECT COUNT(*) FROM {tabela} WHERE fazenda_id IS NULL").scalar() == 0


# ---------------------------------------------------------------------------
# Migração
# ---------------------------------------------------------------------------
def _alembic(db: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "FAZENDA_TESTING": "1"}
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_migracao_cria_gatilhos_e_e_reversivel(tmp_path):
    db = tmp_path / "reguas.db"
    _alembic(db, "upgrade", "head")
    eng = sa.create_engine(f"sqlite:///{db}")
    with eng.connect() as conn:
        gatilhos = {r[0] for r in conn.exec_driver_sql("select name from sqlite_master where type='trigger'")}
    assert {"trg_aceite_termos_sem_update", "trg_aceite_termos_sem_delete",
            "trg_exportacao_relatorio_log_sem_update", "trg_exportacao_relatorio_log_sem_delete"} <= gatilhos
    eng.dispose()
    _alembic(db, "downgrade", "b9d3f5a1c864")
    eng = sa.create_engine(f"sqlite:///{db}")
    insp = sa.inspect(eng)
    assert not any(insp.has_table(t) for t in ("aceite_termos", "exportacao_relatorio_log", "regua_erro_reportado"))
    eng.dispose()
    _alembic(db, "upgrade", "head")
