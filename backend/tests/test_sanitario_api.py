"""
Sanitário Preventivo v2 — API (fase F5), ponta a ponta pelo TestClient.

Cobre: ida-e-volta dos schemas (front envia → back grava → back devolve,
inclusive os campos novos) e `extra="forbid"`; validação do wizard por etapa;
prévia e simulação que NÃO gravam; nenhum GET grava; registrar idempotente;
aplicar nunca cria caixa; consentimento obrigatório fora da regra; estoque
por animal, desfazer e estorno; carência (pop-up, sem aceite) e produção nos
3 modos; prazos legais; permissões; duas fazendas; sincronização offline com
conflito; heartbeat; catálogo central (ativar = copiar, nova versão avisa);
exame (leitura por vet/admin, reagente só avisa); fechar dia; ficha do animal
e vínculo financeiro; leite separado; push das notas.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import EMAIL_DONO
from fazenda.models import (
    Animal, CategoriaManejo, ContratoFazenda, ContratoFazendaModulo, ControleLeiteiro, Estoque, Fazenda, Lactacao,
    LoteEstoque, MovimentoEstoque, Pessoa, SanitarioCaixa, SanitarioDispositivo, SanitarioLog, SanitarioNotaAgenda,
    SanitarioPrazoLegal, SanitarioRegistro, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.models.sanitario_preventivo import TABELAS_SANITARIO_V2
from fazenda.rules.datas import hoje_local

HOJE = hoje_local()


# ════════════════════════════════════════════════════════════════════════════
# Cenário
# ════════════════════════════════════════════════════════════════════════════
class Ctx:
    def __init__(self, client, engine, ids):
        self.c, self.eng, self.ids = client, engine, ids
        self.estado = {"uid": ids["adm"], "fid": 1}

    def como(self, quem: str, fid: int = 1) -> "Ctx":
        self.estado["uid"], self.estado["fid"] = self.ids[quem], fid
        return self

    def s(self) -> Session:
        return Session(self.eng)


@pytest.fixture
def api():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    ids: dict[str, int] = {}
    with Session(eng) as s:
        for fid, nome in ((1, "Estreito"), (2, "Outra")):
            s.add(Fazenda(id=fid, nome=nome, ativa=True, uf="GO"))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
            for cat, dmin, dmax, ordem in (("Aleitamento", 0, 90, 0), ("Recria 1", 91, 210, 1),
                                           ("Recria 2", 211, 390, 2), ("Novilha", 391, None, 3)):
                s.add(CategoriaManejo(fazenda_id=fid, nome=cat, dia_min=dmin, dia_max=dmax, ordem=ordem))
        s.commit()
        vet_p = Pessoa(fazenda_id=1, nome="Dra. Ana", tipo="Veterinário", crmv="CRMV-GO 123")
        s.add(vet_p)
        s.commit()
        usuarios = {
            "adm": Usuario(username="adm", senha_hash="x", papel="admin", ativo=True),
            "op": Usuario(username="op", senha_hash="x", papel="operador", ativo=True),
            "op2": Usuario(username="op2", senha_hash="x", papel="operador", ativo=True),
            "vet": Usuario(username="vet", senha_hash="x", papel="operador", ativo=True, pessoa_id=vet_p.id),
            "contr": Usuario(username="contr", senha_hash="x", papel="operador", ativo=True),
            "dono": Usuario(username="dono", senha_hash="x", papel="operador", ativo=True, email=EMAIL_DONO),
        }
        for u in usuarios.values():
            s.add(u)
        s.commit()
        for k, u in usuarios.items():
            ids[k] = u.id
        s.add(UsuarioFazenda(usuario_id=ids["adm"], fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=ids["adm"], fazenda_id=2))
        s.add(UsuarioFazenda(usuario_id=ids["op"], fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=ids["op2"], fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=ids["vet"], fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=ids["contr"], fazenda_id=1, contratante=True))
        ids["vet_pessoa"] = vet_p.id
        s.commit()

    ctx = Ctx(None, eng, ids)

    def _sessao():
        with Session(eng) as s:
            yield s

    def _usuario():
        with Session(eng) as s:
            return s.get(Usuario, ctx.estado["uid"])

    main.app.dependency_overrides[database.get_session] = _sessao
    main.app.dependency_overrides[database.get_session_manutencao] = _sessao
    main.app.dependency_overrides[get_current_user] = _usuario
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: ctx.estado["fid"]
    with TestClient(main.app) as c:
        ctx.c = c
        yield ctx
    main.app.dependency_overrides.clear()


def animal(ctx: Ctx, numero: str, *, idade: int, sexo: str = "F", fid: int = 1) -> int:
    with ctx.s() as s:
        a = Animal(fazenda_id=fid, numero=numero, sexo=sexo, data_nasc=HOJE - timedelta(days=idade), ativo=True,
                   raca="Holandês", grupo_primario="01 - Recria")
        s.add(a)
        s.commit()
        return a.id


def estoque(ctx: Ctx, nome: str = "Vacina B19", qtd: float = 100.0, fid: int = 1, valor: float = 1.5) -> int:
    with ctx.s() as s:
        e = Estoque(fazenda_id=fid, nome=nome, unidade="mL", quantidade=qtd, ativo=True, valor_unitario=valor)
        s.add(e)
        s.commit()
        return e.id


def b19(**kw) -> dict:
    d = {
        "nome": "Brucelose B19", "nome_curto": "B19", "tipo": "vacina", "obrigatoria": True,
        "produto_modo": "vazio", "dose_valor": 2.0, "dose_unidade": "mL",
        "pub_sexo": "F", "jan_usa_evento": True, "evento_tipo": "idade", "evento_de_dias": 120, "evento_ate_dias": 240,
        "jan_usa_periodo": True, "periodo_modo": "continuo", "ao_fechar": "perder", "aglo_min": 2,
        "ficha_colunas": ["brinco", "categoria", "idade", "dose", "aplicado", "obs"],
        "car_leite_dias": 0, "car_carne_dias": 0,
    }
    d.update(kw)
    return d


def criar_caixa(ctx: Ctx, definicao: dict, *, estado: str = "ativa", aceitar: bool = True) -> dict:
    ctx.como("adm")
    r = ctx.c.post("/sanitario/caixas", json={"definicao": definicao, "estado": estado, "aceitar_carencia": aceitar})
    assert r.status_code == 200, r.text
    return r.json()


def contagens(eng) -> dict:
    tabelas = [*TABELAS_SANITARIO_V2, "movimento_estoque", "estoque", "controle_leiteiro"]
    out = {}
    with eng.connect() as conn:
        for t in tabelas:
            out[t] = conn.exec_driver_sql(f"SELECT COUNT(*) FROM {t}").scalar()
            if t == "estoque":
                out["estoque_saldo"] = conn.exec_driver_sql("SELECT COALESCE(SUM(quantidade),0) FROM estoque").scalar()
    return out


# ════════════════════════════════════════════════════════════════════════════
# 1) Ida-e-volta do cadastro (wizard) + extra="forbid" + versão
# ════════════════════════════════════════════════════════════════════════════
def test_ida_e_volta_caixa_todos_os_campos_e_versao(api):
    eid = estoque(api)
    with api.s() as s:
        cats = s.exec(select(CategoriaManejo.id).where(CategoriaManejo.fazenda_id == 1)).all()
    ref = criar_caixa(api, b19(nome="Referência", nome_curto="Ref"))
    enviado = b19(
        produto_modo="estoque", estoque_id=eid, produto_texto="B19 frasco", dose_x_kg=None, peso_ausente="exigir",
        pub_cat_modo="incluir", categorias=sorted(cats[:2]), pub_idade_min_dias=100, pub_idade_max_dias=300,
        pub_condicoes=["apta_ia"], pub_hist_tipo="nunca", pub_hist_caixa_id=ref["id"],
        periodo_grupos=[], periodo_anos=None, periodo_ano_base=None, data_base_dia=10, comecar_em="2027-01-01",
        serie=[{"dose": 2, "apos_dias": 30, "janela_dias": 15}],
        aviso_antecedencia_dias=20, aviso_fim_janela_dias=7, push_admin=False,
        legal_crmv_pedir=True,
        legal_atestado={"destinatario_tipo": "orgao", "destinatario_texto": "SIDAGO", "quando": "primeiro", "dias": 30},
        legal_comprovacao={"dias": 180, "aviso_dias": 30, "push": True, "email": True},
        legal_leitura={"modo": "so_resultado", "horas": 72, "tolerancia": 6},
        legal_reagente_aviso=True, legal_marca_texto="Marcar face esquerda",
        car_leite_dias=3, car_carne_dias=30, car_modo_leite="descarte", observacao="obs livre",
    )
    cx = criar_caixa(api, enviado)
    devolvido = api.c.get(f"/sanitario/caixas/{cx['id']}").json()["definicao"]
    assert devolvido == enviado
    assert cx["versao_numero"] == 1 and cx["carencia_aceita"] is True

    # extra="forbid": campo desconhecido (no topo e aninhado) é recusado, nada grava
    antes = contagens(api.eng)
    r = api.c.post("/sanitario/caixas", json={"definicao": {**b19(nome="X"), "campo_novo": 1}})
    assert r.status_code == 422
    r = api.c.post("/sanitario/caixas", json={"definicao": {**b19(nome="Y"), "legal_atestado": {"dias": 1, "x": 2}}})
    assert r.status_code == 422
    r = api.c.post("/sanitario/caixas", json={"definicao": b19(nome="Z"), "campo_raiz": True})
    assert r.status_code == 422
    assert contagens(api.eng) == antes

    # editar = versão nova; a antiga continua consultável como foi
    v1 = cx["versao_atual_id"]
    novo = {**enviado, "dose_valor": 3.0, "aglo_min": 9}
    r = api.c.put(f"/sanitario/caixas/{cx['id']}", json={"definicao": novo})
    assert r.status_code == 200, r.text
    d2 = r.json()
    assert d2["versao_numero"] == 2 and d2["definicao"] == novo and len(d2["versoes"]) == 2
    antiga = api.c.get(f"/sanitario/caixas/{cx['id']}/versoes/{v1}").json()
    assert antiga["definicao"]["dose_valor"] == 2.0 and antiga["vigente_ate"] is not None


def test_wizard_valida_etapa_a_etapa_e_previa_nao_grava(api):
    animal(api, "2401", idade=150)
    animal(api, "2402", idade=150, sexo="M")
    r = api.c.post("/sanitario/caixas/validar", json={"definicao": b19(nome=""), "etapa": 1})
    assert r.json()["ok"] is False and r.json()["erros"][0]["campo"] == "nome"
    r = api.c.post("/sanitario/caixas/validar", json={"definicao": b19(jan_usa_evento=False, jan_usa_periodo=False),
                                                      "etapa": 4})
    assert {e["campo"] for e in r.json()["erros"]} == {"jan_usa_evento"}
    r = api.c.post("/sanitario/caixas/validar", json={"definicao": b19(dose_unidade="mL_por_x_kg"), "etapa": 2})
    assert r.json()["erros"][0]["campo"] == "dose_x_kg"
    assert api.c.post("/sanitario/caixas/validar", json={"definicao": b19(), "etapa": 9}).json()["ok"] is True
    # criação com erro de etapa -> 422 com a lista
    r = api.c.post("/sanitario/caixas", json={"definicao": b19(evento_de_dias=300, evento_ate_dias=100)})
    assert r.status_code == 422 and r.json()["detail"]["codigo"] == "validacao"

    antes = contagens(api.eng)
    r = api.c.post("/sanitario/caixas/previa", json={"definicao": b19(), "data_base": HOJE.isoformat()})
    assert r.status_code == 200
    p = r.json()
    assert [x["numero"] for x in p["entram"]] == ["2401"]
    assert p["fora"][0]["numero"] == "2402" and "Macho" in p["fora"][0]["motivo"]
    assert contagens(api.eng) == antes


def test_parametros_ida_e_volta_e_so_admin(api):
    antes = contagens(api.eng)
    assert api.c.get("/sanitario/parametros").json()["modo_tuberculina"] == "so_resultado"
    assert contagens(api.eng) == antes  # GET não cria a linha
    body = {"uf": "GO", "prazos_legais_ativo": True, "antecedencia_padrao_dias": 20, "corrigir_ate": "fechar_dia",
            "dose_externa_sem_data": "nao_contar", "peso_estimado": "exigir", "modo_tuberculina": "diferenca",
            "aviso_offline_horas": 12}
    api.como("op")
    assert api.c.put("/sanitario/parametros", json=body).status_code == 403
    api.como("adm")
    r = api.c.put("/sanitario/parametros", json=body)
    assert r.status_code == 200
    got = api.c.get("/sanitario/parametros").json()
    assert {k: got[k] for k in body} == body
    assert api.c.put("/sanitario/parametros", json={**body, "outro": 1}).status_code == 422


# ════════════════════════════════════════════════════════════════════════════
# 2) Lançamento simples: idempotência, nunca cria caixa, consentimento, "outro"
# ════════════════════════════════════════════════════════════════════════════
def test_lancamento_simples_idempotente_consentimento_e_nunca_cria_caixa(api):
    cx = criar_caixa(api, b19())
    f1 = animal(api, "2401", idade=150)
    macho = animal(api, "2404", idade=150, sexo="M")
    with api.s() as s:
        n_caixas = s.exec(select(func.count()).select_from(SanitarioCaixa)).one()
    api.como("op")
    body = {"caixa_id": cx["id"], "data": HOJE.isoformat(), "animal_ids": [f1, macho], "chave_lote": "L1",
            "aplicador_texto": "Zé"}
    r = api.c.post("/sanitario/lancamento-simples", json=body).json()
    st = {i["animal_id"]: i for i in r["itens"]}
    assert st[f1]["status"] == "gravado"
    assert st[macho]["status"] == "pendente" and st[macho]["requer"] == ["consentimento"]
    assert "Macho" in st[macho]["motivo_fora"] and st[macho]["pergunta_atestado"] is True
    # reenviar o mesmo lote: idempotente
    r2 = api.c.post("/sanitario/lancamento-simples", json=body).json()
    assert {i["animal_id"]: i["status"] for i in r2["itens"]}[f1] == "duplicado"
    # agora com consentimento explícito (e pedido de atestado)
    body2 = {**body, "animal_ids": [macho], "consentimentos": [
        {"animal_id": macho, "aceito": True, "motivo_exibido": "Macho", "quer_atestado": True,
         "atestado_destinatario": "SIDAGO"}]}
    r3 = api.c.post("/sanitario/lancamento-simples", json=body2).json()
    assert r3["itens"][0]["status"] == "gravado"
    # outra chave, mesmo animal/caixa/ciclo: chave única -> duplicado + log
    r4 = api.c.post("/sanitario/lancamento-simples", json={**body, "chave_lote": "L2", "animal_ids": [f1]}).json()
    assert r4["itens"][0]["status"] == "duplicado"
    # "outro": só registra; nunca cria caixa
    r5 = api.c.post("/sanitario/lancamento-simples", json={"outro_texto": "Vermífugo fora do calendário",
                                                           "data": HOJE.isoformat(), "animal_ids": [f1]}).json()
    assert r5["itens"][0]["status"] == "gravado"
    # caixa inexistente / de outra fazenda: erro do item, nada criado
    r6 = api.c.post("/sanitario/lancamento-simples", json={"caixa_id": 999, "data": HOJE.isoformat(), "animal_ids": [f1]})
    assert r6.status_code == 404
    with api.s() as s:
        assert s.exec(select(func.count()).select_from(SanitarioCaixa)).one() == n_caixas
        regs = s.exec(select(SanitarioRegistro).order_by(SanitarioRegistro.id)).all()
        assert len(regs) == 3
        assert [r.fora_da_regra for r in regs] == [False, True, False]
        assert regs[2].so_registro is True and regs[2].caixa_id is None and regs[2].outro_texto
        logs = {lg.tipo for lg in s.exec(select(SanitarioLog)).all()}
        assert {"consentimento.inelegivel", "escrita.duplicada"} <= logs
        prazo = s.exec(select(SanitarioPrazoLegal).where(SanitarioPrazoLegal.tipo == "atestado")).one()
        assert prazo.registro_ids == [regs[1].id] and prazo.destinatario == "SIDAGO"


def test_retroativo_com_motivo_pulavel_e_importacao_so_registro(api):
    cx = criar_caixa(api, b19())
    a = animal(api, "2401", idade=150)
    r = api.c.post("/sanitario/lancamento-simples", json={
        "caixa_id": cx["id"], "data": (HOJE - timedelta(days=3)).isoformat(), "animal_ids": [a]}).json()
    assert r["itens"][0]["status"] == "gravado"
    hist = api.c.get(f"/sanitario/animais/{a}/historico").json()["registros"]
    assert hist[0]["retroativo"] is True and hist[0]["retroativo_motivo"] is None
    with api.s() as s:
        assert s.exec(select(SanitarioLog).where(SanitarioLog.tipo == "registro.retroativo")).one()

    # planilha: só registro (não conta, não tira da caixa), nunca apaga nada
    b = animal(api, "2402", idade=150)
    csv = "Brinco;Data;Vacina/exame;Dose\n2402;01/03/2026;B19;2\n9999;01/03/2026;Raiva;5\n;;;\n"
    r = api.c.post("/sanitario/importar-planilha", files={"file": ("vac.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["gravados"] == 2
    r2 = api.c.post("/sanitario/importar-planilha", files={"file": ("vac.csv", csv.encode(), "text/csv")}).json()
    assert r2["duplicados"] == 2 and r2["gravados"] == 0
    with api.s() as s:
        imp = s.exec(select(SanitarioRegistro).where(SanitarioRegistro.origem == "importado")).all()
        assert all(x.so_registro for x in imp)
        assert {x.numero_animal_texto for x in imp} == {"2402", "9999"}
        assert s.exec(select(func.count()).select_from(SanitarioRegistro)).one() == 3
    sit = api.c.get(f"/sanitario/animais/{b}/situacao").json()["caixas"]
    assert sit[0]["estado"] == "janela"  # planilha não tirou a 2402 da caixa


# ════════════════════════════════════════════════════════════════════════════
# 3) Dia marcado: consentimento, riscos, estoque por animal, desfazer, estorno
# ════════════════════════════════════════════════════════════════════════════
def test_dia_estoque_por_animal_desfazer_e_estorno(api):
    eid = estoque(api, qtd=100.0)
    cx = criar_caixa(api, b19(produto_modo="estoque", estoque_id=eid))
    a1, a2, a3 = (animal(api, n, idade=150) for n in ("2401", "2402", "2403"))
    macho = animal(api, "2404", idade=150, sexo="M")
    # marcar com o macho sem consentimento -> 409 e nada gravado
    antes = contagens(api.eng)
    body = {"caixa_ids": [cx["id"]], "data": HOJE.isoformat(), "hora": "07:00",
            "veterinario": {"pessoa_id": api.ids["vet_pessoa"]},
            "itens": [{"animal_id": a} for a in (a1, a2, a3, macho)]}
    r = api.c.post("/sanitario/dias", json=body)
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "consentimento_necessario"
    assert r.json()["detail"]["itens"][0]["animal_id"] == macho
    assert contagens(api.eng) == antes
    body["itens"] = [{"animal_id": a} for a in (a1, a2, a3)]
    r = api.c.post("/sanitario/dias", json=body)
    assert r.status_code == 200, r.text
    dia = r.json()
    assert dia["nome"].startswith("Vacina · B19 · ") and dia["contagens"]["pendentes"] == 3
    assert dia["veterinario"]["texto"] == "Dra. Ana" and dia["veterinario"]["crmv"] == "CRMV-GO 123"
    assert all(i["origem"] == "janela" for i in dia["itens"])

    api.como("op")
    r = api.c.post(f"/sanitario/dias/{dia['id']}/aplicar", json={"aplicador_texto": "Zé"}).json()
    assert r["gravados"] == 3 and r["desfazer_ate"]
    with api.s() as s:
        assert s.get(Estoque, eid).quantidade == pytest.approx(94.0)
        movs = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.origem_tipo == "sanitario_registro")).all()
        assert len(movs) == 3
        regs = s.exec(select(SanitarioRegistro).order_by(SanitarioRegistro.id)).all()
        assert all(x.quantidade_baixada == 2.0 and x.custo == 3.0 for x in regs)
    d = api.c.get(f"/sanitario/dias/{dia['id']}").json()
    assert d["estado"] == "em_execucao" and d["contagens"]["feitos"] == 3

    # desfazer (até 10 s): o estoque volta e o registro some
    rid = r["registro_ids"][0]
    assert api.c.post("/sanitario/registros/desfazer", json={"registro_ids": [rid]}).json()["desfeitos"] == [rid]
    with api.s() as s:
        assert s.get(SanitarioRegistro, rid) is None
        assert s.get(Estoque, eid).quantidade == pytest.approx(96.0)
    # depois do prazo, desfazer é recusado
    with api.s() as s:
        reg = s.get(SanitarioRegistro, r["registro_ids"][1])
        reg.criado_em = datetime.utcnow() - timedelta(minutes=5)
        s.add(reg)
        s.commit()
    rec = api.c.post("/sanitario/registros/desfazer", json={"registro_ids": [r["registro_ids"][1]]}).json()
    assert rec["desfeitos"] == [] and "estorno" in rec["recusados"][0]["motivo"]

    # estorno: só admin, com motivo; devolve estoque e mantém o histórico
    alvo = r["registro_ids"][1]
    assert api.c.post(f"/sanitario/registros/{alvo}/estornar", json={"motivo": "erro"}).status_code == 403
    api.como("adm")
    assert api.c.post(f"/sanitario/registros/{alvo}/estornar", json={"motivo": ""}).status_code == 422
    r = api.c.post(f"/sanitario/registros/{alvo}/estornar", json={"motivo": "aplicado no animal errado"})
    assert r.status_code == 200 and r.json()["estado"] == "estornado"
    with api.s() as s:
        assert s.get(Estoque, eid).quantidade == pytest.approx(98.0)
        assert s.get(SanitarioRegistro, alvo).estado == "estornado"
    hist = api.c.get(f"/sanitario/historico?caixa_id={cx['id']}").json()
    assert {h["estado"] for h in hist} == {"valido", "estornado"}
    # o animal estornado volta para a janela; o dia reabre o item
    d = api.c.get(f"/sanitario/dias/{dia['id']}").json()
    assert d["contagens"]["pendentes"] == 2  # o desfeito e o estornado voltaram a pendente


def test_dia_data_diferente_pede_decisao_e_simulacao_nao_grava(api):
    cx = criar_caixa(api, b19())
    # passa de 240 dias (8 meses) amanhã
    a = animal(api, "2410", idade=239)
    antes = contagens(api.eng)
    r = api.c.post("/sanitario/dias/simular", json={"caixa_ids": [cx["id"]], "data": (HOJE + timedelta(days=5)).isoformat(),
                                                    "data_prevista": HOJE.isoformat(), "animal_ids": [a]})
    assert r.status_code == 200
    riscos = r.json()["riscos"]
    assert riscos and riscos[0]["kind"] == "idade" and "2410" in riscos[0]["texto"]
    assert contagens(api.eng) == antes
    body = {"caixa_ids": [cx["id"]], "data": (HOJE + timedelta(days=5)).isoformat(), "data_prevista": HOJE.isoformat(),
            "itens": [{"animal_id": a}], "consentimentos": [{"animal_id": a, "aceito": True}]}
    r = api.c.post("/sanitario/dias", json=body)
    assert r.status_code == 200, r.text  # entra por consentimento (fora da idade na data)
    # sem consentimento mas na data prevista: marca; mudar a data pede decisão
    b = animal(api, "2411", idade=239)
    r = api.c.post("/sanitario/dias", json={"caixa_ids": [cx["id"]], "data": HOJE.isoformat(),
                                            "itens": [{"animal_id": b}]})
    assert r.status_code == 200
    dia = r.json()
    antes = contagens(api.eng)
    r = api.c.put(f"/sanitario/dias/{dia['id']}", json={"versao_lock": dia["versao_lock"],
                                                        "data": (HOJE + timedelta(days=5)).isoformat()})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "decisao_riscos_necessaria"
    assert contagens(api.eng) == antes
    r = api.c.put(f"/sanitario/dias/{dia['id']}", json={"versao_lock": dia["versao_lock"],
                                                        "data": (HOJE + timedelta(days=5)).isoformat(),
                                                        "decisao_riscos": {"decisao": "manter"}})
    assert r.status_code == 200 and r.json()["versao_lock"] == dia["versao_lock"] + 1
    # versão velha -> conflito
    r = api.c.put(f"/sanitario/dias/{dia['id']}", json={"versao_lock": dia["versao_lock"], "hora": "08:00"})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "versao_desatualizada"
    with api.s() as s:
        assert s.exec(select(SanitarioLog).where(SanitarioLog.tipo == "dia.data_diferente")).first() is not None


def test_dia_adicionar_no_curral_fechar_e_apos_fechamento(api):
    cx = criar_caixa(api, b19())
    a1, a2 = animal(api, "2401", idade=150), animal(api, "2402", idade=150)
    macho = animal(api, "2404", idade=150, sexo="M")
    dia = api.c.post("/sanitario/dias", json={"caixa_ids": [cx["id"]], "data": HOJE.isoformat(),
                                              "itens": [{"animal_id": a1}, {"animal_id": a2}]}).json()
    r = api.c.post(f"/sanitario/dias/{dia['id']}/itens", json={"itens": [{"animal_id": macho}]})
    assert r.status_code == 409
    r = api.c.post(f"/sanitario/dias/{dia['id']}/itens", json={
        "itens": [{"animal_id": macho}], "consentimentos": [{"animal_id": macho, "aceito": True}]})
    assert r.status_code == 200
    item_macho = next(i for i in r.json()["itens"] if i["animal_id"] == macho)
    assert item_macho["origem"] == "curral" and item_macho["consentimento_log_id"]
    # registra um (o macho, já consentido no dia)
    r = api.c.post(f"/sanitario/dias/{dia['id']}/registros",
                   json={"registros": [{"animal_id": macho, "caixa_id": cx["id"]}]}).json()
    assert r["gravados"] == 1
    # fecha: a 2402 é dispensada (motivo pulável), a 2401 volta
    r = api.c.post(f"/sanitario/dias/{dia['id']}/fechar", json={"faltantes": "dispensar"})
    assert r.status_code == 200 and r.json()["estado"] == "fechado"
    assert sorted(r.json()["fechamento"]["faltantes"]) == sorted([a1, a2])
    sit = api.c.get(f"/sanitario/animais/{a2}/situacao").json()["caixas"]
    assert sit[0]["estado"] == "dispensada"
    # chegou do celular depois do fechamento: "lançado após o fechamento"
    r = api.c.post(f"/sanitario/dias/{dia['id']}/registros",
                   json={"registros": [{"animal_id": a1, "caixa_id": cx["id"], "chave_idempotencia": "cel-1"}],
                         "canal": "app", "dispositivo_uid": "cel-ze"}).json()
    assert r["gravados"] == 1 and any(a["codigo"] == "apos_fechamento" for a in r["itens"][0]["avisos"])
    regs = api.c.get(f"/sanitario/dias/{dia['id']}/registros").json()
    assert sorted(x["apos_fechamento"] for x in regs) == [False, True]
    assert any(x["decisao_curral"] for x in regs)


# ════════════════════════════════════════════════════════════════════════════
# 4) Carência: pop-up de decisão, sem aceite, e a produção nos 3 modos (D4)
# ════════════════════════════════════════════════════════════════════════════
def _vaca_em_lactacao(api, numero: str) -> int:
    aid = animal(api, numero, idade=1700)
    with api.s() as s:
        s.add(Lactacao(fazenda_id=1, animal_id=aid, numero_matriz=numero, data_inicio=HOJE - timedelta(days=40)))
        s.commit()
    return aid


def _vacina_vacas(**kw) -> dict:
    return {"nome": kw.pop("nome", "Leptospirose"), "nome_curto": kw.pop("nome_curto", "Lepto"), "tipo": "vacina",
            "pub_sexo": "F", "jan_usa_evento": False, "jan_usa_periodo": True, "periodo_modo": "continuo",
            "dose_valor": 5.0, "dose_unidade": "mL", "car_leite_dias": 5, "car_carne_dias": 20,
            "ficha_colunas": ["brinco", "aplicado"], **kw}


def test_carencia_popup_admin_sem_aceite_operador_e_producao_tres_modos(api):
    cx = criar_caixa(api, _vacina_vacas(car_modo_leite="bloqueio"), aceitar=False)
    vacas = {n: _vaca_em_lactacao(api, n) for n in ("0701", "0702", "0703", "0704")}
    dia = api.c.post("/sanitario/dias", json={"caixa_ids": [cx["id"]], "data": HOJE.isoformat(),
                                              "itens": [{"animal_id": v} for v in vacas.values()]}).json()
    # admin sem aceite: pop-up obrigatório (pendente), nada grava
    r = api.c.post(f"/sanitario/dias/{dia['id']}/registros",
                   json={"registros": [{"animal_id": vacas["0701"], "caixa_id": cx["id"]}]}).json()
    assert r["itens"][0]["status"] == "pendente" and r["itens"][0]["requer"] == ["carencia_decisao"]
    assert r["itens"][0]["carencia_sugerida"]["leite_dias"] == 5
    # operador não decide o modo
    api.como("op")
    assert api.c.post(f"/sanitario/dias/{dia['id']}/carencia",
                      json={"caixa_id": cx["id"], "modo": "bloqueio", "leite_dias": 5}).status_code == 403
    # operador sem decisão: grava com tanque · sem aceite (log + nota), nunca trava
    r = api.c.post(f"/sanitario/dias/{dia['id']}/registros",
                   json={"registros": [{"animal_id": vacas["0704"], "caixa_id": cx["id"]}]}).json()
    it = r["itens"][0]
    assert it["status"] == "gravado" and it["carencia"]["modo"] == "tanque"
    assert any(a["codigo"] == "carencia_sem_aceite" for a in it["avisos"])
    # admin decide no pop-up (vale para o dia): bloqueio
    api.como("adm")
    r = api.c.post(f"/sanitario/dias/{dia['id']}/carencia", json={"caixa_id": cx["id"], "modo": "bloqueio",
                                                                   "leite_dias": 5, "carne_dias": 20})
    assert r.status_code == 200
    r = api.c.post(f"/sanitario/dias/{dia['id']}/registros",
                   json={"registros": [{"animal_id": vacas["0701"], "caixa_id": cx["id"]}]}).json()
    assert r["itens"][0]["status"] == "gravado" and r["itens"][0]["carencia"]["modo"] == "bloqueio"
    # decisão no próprio registro (outro modo) para as outras duas
    for numero, modo in (("0702", "descarte"), ("0703", "tanque")):
        with api.s() as s:
            from fazenda.models import SanitarioDiaCaixa
            dc = s.exec(select(SanitarioDiaCaixa).where(SanitarioDiaCaixa.dia_id == dia["id"])).one()
            dc.carencia_decisao_id = None
            s.add(dc)
            s.commit()
        r = api.c.post(f"/sanitario/dias/{dia['id']}/registros", json={
            "registros": [{"animal_id": vacas[numero], "caixa_id": cx["id"]}],
            "carencia": {str(cx["id"]): {"modo": modo, "leite_dias": 5, "carne_dias": 20}}}).json()
        assert r["itens"][0]["carencia"]["modo"] == modo

    # produção: bloqueio recusa; descarte grava fora do tanque; tanque segue com log
    def lanca(numero):
        return api.c.post("/producao/controles", json={"data_controle": HOJE.isoformat(),
                                                       "entradas": [{"numero_matriz": numero, "total_kg": 20.0}]})
    r = lanca("0701")
    assert r.status_code == 409 and r.json()["detail"]["erro"] == "carencia_bloqueio"
    r = lanca("0702")
    assert r.status_code == 200 and r.json()["carencia"][0]["modo"] == "descarte"
    r = lanca("0703")
    assert r.status_code == 200 and r.json()["carencia"][0]["modo"] == "tanque"
    with api.s() as s:
        ctrl = {c.numero_matriz: c for c in s.exec(select(ControleLeiteiro)).all()}
        assert "0701" not in ctrl
        assert ctrl["0702"].destino_leite == "descarte" and ctrl["0702"].sanitario_registro_id
        assert ctrl["0703"].destino_leite is None
        tipos = [lg.tipo for lg in s.exec(select(SanitarioLog)).all()]
        assert "leite.descarte" in tipos and "leite.tanque_em_carencia" in tipos
        assert "carencia.sem_aceite" in tipos and "carencia.decisao" in tipos
        nota = s.exec(select(SanitarioNotaAgenda).where(SanitarioNotaAgenda.tipo == "carencia_pendente")).first()
        assert nota is not None and nota.so_admin
    # "Leite separado": preventivos e curativos juntos
    from fazenda.models import Sanidade
    with api.s() as s:
        e = Estoque(fazenda_id=1, nome="Antibiótico X", unidade="mL", quantidade=10, ativo=True, carencia_leite_dias=4)
        s.add(e)
        s.add(Sanidade(fazenda_id=1, numero_matriz="0704", data_aplicacao=HOJE - timedelta(days=1),
                       produto="Antibiótico X", natureza="curativo"))
        s.commit()
    ls = api.c.get("/sanitario/leite-separado").json()
    assert {i["origem"] for i in ls["itens"]} == {"preventivo", "curativo"}
    assert {"0701", "0702", "0703", "0704"} <= {i["numero"] for i in ls["itens"]}


def test_aceite_de_carencia_um_clique_so_admin(api):
    cx = criar_caixa(api, _vacina_vacas(), aceitar=False)
    api.como("op")
    assert api.c.post(f"/sanitario/caixas/{cx['id']}/carencia/aceite", json={"modo_leite": "descarte"}).status_code == 403
    api.como("contr")  # contratante da fazenda = administrador
    r = api.c.post(f"/sanitario/caixas/{cx['id']}/carencia/aceite",
                   json={"modo_leite": "descarte", "leite_dias": 5, "carne_dias": 20})
    assert r.status_code == 200
    det = api.c.get(f"/sanitario/caixas/{cx['id']}").json()
    assert det["carencia_aceita"] and det["aceite_carencia"]["modo_leite"] == "descarte"
    # com aceite, o admin não recebe mais o pop-up
    v = _vaca_em_lactacao(api, "0801")
    api.como("adm")
    r = api.c.post("/sanitario/lancamento-simples", json={"caixa_id": cx["id"], "data": HOJE.isoformat(),
                                                          "animal_ids": [v]}).json()
    it = r["itens"][0]
    assert it["status"] == "gravado" and it["carencia"]["modo"] == "descarte"
    assert it["carencia"]["leite_ate"] == (HOJE + timedelta(days=5)).isoformat()


# ════════════════════════════════════════════════════════════════════════════
# 5) Prazos legais e exame
# ════════════════════════════════════════════════════════════════════════════
def test_prazos_legais_o_que_vencer_primeiro_e_comprovacao(api):
    eid = estoque(api)
    with api.s() as s:
        s.add(LoteEstoque(fazenda_id=1, estoque_id=eid, data_compra=HOJE - timedelta(days=20), quantidade_comprada=100,
                          quantidade_restante=100))
        s.commit()
    cx = criar_caixa(api, b19(produto_modo="estoque", estoque_id=eid, legal_atestado={
        "destinatario_texto": "SIDAGO", "quando": "primeiro", "dias": 30},
        legal_comprovacao={"dias": 180, "aviso_dias": 30}))
    a = animal(api, "2401", idade=150)
    dia = api.c.post("/sanitario/dias", json={"caixa_ids": [cx["id"]], "data": HOJE.isoformat(),
                                              "itens": [{"animal_id": a}]}).json()
    api.c.post(f"/sanitario/dias/{dia['id']}/aplicar", json={})
    prazos = {p["tipo"]: p for p in api.c.get("/sanitario/prazos").json()}
    assert prazos["atestado"]["vence_em"] == (HOJE + timedelta(days=10)).isoformat()  # NF-e venceu antes
    assert prazos["atestado"]["destinatario"] == "SIDAGO" and prazos["atestado"]["referencia"] == f"dia:{dia['id']}"
    assert prazos["comprovacao"]["vence_em"] == (HOJE + timedelta(days=180)).isoformat()
    api.como("op")
    assert api.c.post(f"/sanitario/prazos/{prazos['atestado']['id']}/cumprir", json={}).status_code == 403
    api.como("adm")
    r = api.c.post(f"/sanitario/prazos/{prazos['atestado']['id']}/cumprir", json={"documento_numero": "AT-1"})
    assert r.json()["estado"] == "cumprido" and r.json()["documento_numero"] == "AT-1"


def test_exame_resultado_por_vet_ou_admin_com_vet_e_reagente_so_avisa(api):
    exame = criar_caixa(api, {"nome": "Exame de tuberculose", "nome_curto": "Exame TB", "tipo": "exame",
                              "produto_modo": "nao_se_aplica", "jan_usa_periodo": True, "periodo_modo": "continuo",
                              "jan_usa_evento": False, "legal_reagente_aviso": True,
                              "legal_leitura": {"modo": "so_resultado", "horas": 72, "tolerancia": 6},
                              "ficha_colunas": ["brinco", "resultado"]})
    a = animal(api, "0701", idade=1700)
    dia = api.c.post("/sanitario/dias", json={"caixa_ids": [exame["id"]], "data": HOJE.isoformat(),
                                              "itens": [{"animal_id": a}]}).json()
    assert dia["tipo"] == "exame" and dia["nome"].startswith("Exame · Exame TB")
    api.como("op")
    r = api.c.post(f"/sanitario/dias/{dia['id']}/aplicar", json={}).json()
    rid = r["registro_ids"][0]
    assert api.c.post(f"/sanitario/registros/{rid}/resultado", json={"resultado": "negativo"}).status_code == 403
    api.como("adm")
    assert api.c.post(f"/sanitario/registros/{rid}/resultado", json={"resultado": "negativo"}).status_code == 400
    api.como("vet")
    r = api.c.post(f"/sanitario/registros/{rid}/resultado", json={"resultado": "positivo"})
    assert r.status_code == 200 and r.json()["avisos"][0]["codigo"] == "reagente"
    api.como("adm")
    r = api.c.post(f"/sanitario/registros/{rid}/resultado",
                   json={"resultado": "positivo", "veterinario_texto": "Dr. Fulano", "crmv_texto": "CRMV 9"})
    assert r.status_code == 200
    with api.s() as s:
        reg = s.get(SanitarioRegistro, rid)
        assert reg.resultado == "positivo" and reg.veterinario_texto == "Dr. Fulano" and reg.leitura_em
        assert reg.carencia_leite_ate is None  # exame não tem carência
        assert s.exec(select(SanitarioNotaAgenda).where(SanitarioNotaAgenda.tipo == "reagente")).one()
    # a ficha do animal e o vínculo financeiro voltam a ver os exames
    ficha = api.c.get("/animais/0701/ficha").json()
    assert ficha["exames_resultados"][0]["resultado"] == "positivo"
    cand = api.c.get("/financeiro/candidatos-vinculo-sanitario-reprodutivo").json()
    assert cand["exames"][0]["ids"] == [rid] and cand["exames"][0]["tipo"] == "sanitario_registro"


# ════════════════════════════════════════════════════════════════════════════
# 6) Permissões e duas fazendas
# ════════════════════════════════════════════════════════════════════════════
def test_permissoes_so_admin_cadastra_e_estorna(api):
    api.como("op")
    assert api.c.post("/sanitario/caixas", json={"definicao": b19()}).status_code == 403
    assert api.c.get("/sanitario/eu").json()["administrador"] is False
    api.como("vet")
    assert api.c.get("/sanitario/eu").json()["pode"]["ler_exame"] is True
    api.como("contr")
    assert api.c.post("/sanitario/caixas", json={"definicao": b19()}).status_code == 200
    api.como("op")
    cid = api.c.get("/sanitario/caixas").json()[0]["id"]
    assert api.c.post("/sanitario/caixas/estado", json={"caixa_ids": [cid], "acao": "ativar"}).status_code == 403
    assert api.c.put(f"/sanitario/caixas/{cid}", json={"definicao": b19()}).status_code == 403
    vets = api.c.get("/sanitario/veterinarios").json()
    assert vets["pessoas"][0]["nome"] == "Dra. Ana" and vets["aceita_texto_livre"] is True


def test_duas_fazendas_isoladas(api):
    cx = criar_caixa(api, b19())
    a = animal(api, "2401", idade=150)
    b = animal(api, "2401", idade=150, fid=2)
    dia = api.c.post("/sanitario/dias", json={"caixa_ids": [cx["id"]], "data": HOJE.isoformat(),
                                              "itens": [{"animal_id": a}]}).json()
    api.como("adm", fid=2)
    assert api.c.get("/sanitario/caixas").json() == []
    assert api.c.get(f"/sanitario/caixas/{cx['id']}").status_code == 404
    assert api.c.get(f"/sanitario/dias/{dia['id']}").status_code == 404
    assert api.c.get("/sanitario/dias").json() == []
    assert api.c.post(f"/sanitario/dias/{dia['id']}/aplicar", json={}).status_code == 404
    assert api.c.post("/sanitario/dias", json={"caixa_ids": [cx["id"]], "data": HOJE.isoformat()}).status_code == 404
    assert api.c.get(f"/sanitario/animais/{a}/situacao").status_code == 404
    r = api.c.post("/sanitario/lancamento-simples", json={"caixa_id": cx["id"], "data": HOJE.isoformat(),
                                                          "animal_ids": [b]})
    assert r.status_code == 404
    # registros de F1 nunca aparecem em F2
    api.como("adm", fid=1)
    api.c.post(f"/sanitario/dias/{dia['id']}/aplicar", json={})
    api.como("adm", fid=2)
    assert api.c.get("/sanitario/registros").json() == []
    assert api.c.get("/sanitario/painel").json()["cobertura"] == []
    assert api.c.get("/sanitario/agenda/resumo").json()["animais"] == 0


# ════════════════════════════════════════════════════════════════════════════
# 7) App: pacote offline, sincronização com conflito, heartbeat
# ════════════════════════════════════════════════════════════════════════════
def test_app_pacote_sincronizacao_conflito_e_heartbeat(api):
    cx = criar_caixa(api, b19())
    a1, a2 = animal(api, "2401", idade=150), animal(api, "2402", idade=150)
    macho = animal(api, "2404", idade=150, sexo="M")
    dia = api.c.post("/sanitario/dias", json={"caixa_ids": [cx["id"]], "data": HOJE.isoformat(),
                                              "itens": [{"animal_id": a1}, {"animal_id": a2}]}).json()
    antes = contagens(api.eng)
    pac = api.c.get(f"/sanitario/dias/{dia['id']}/pacote-offline").json()
    assert contagens(api.eng) == antes
    regras = {x["brinco"]: x["caixas"][str(cx["id"])] for x in pac["animais"]}
    assert regras["2401"]["elegivel"] is True and regras["2404"]["elegivel"] is False
    assert "Macho" in regras["2404"]["motivo"] and pac["caixas"][0]["regras"]["pub_sexo"] == "F"
    assert api.c.get("/sanitario/campo/hoje").json()["dias"][0]["id"] == dia["id"]

    # celular do Zé (operador) manda 2 registros + o macho com consentimento no curral
    api.como("op")
    lote = {"dispositivo_uid": "cel-ze", "nome": "Celular do Zé", "fila_pendentes_restantes": 0, "registros": [
        {"dia_id": dia["id"], "animal_id": a1, "caixa_id": cx["id"], "chave_idempotencia": "ze-1", "hora": "07:10"},
        {"dia_id": dia["id"], "animal_id": macho, "caixa_id": cx["id"], "chave_idempotencia": "ze-2",
         "consentimento": {"aceito": True, "motivo_exibido": "Macho"}},
        {"dia_id": dia["id"], "animal_id": a2, "caixa_id": cx["id"], "chave_idempotencia": "ze-3",
         "campo_desconhecido": 1},
    ]}
    assert api.c.post("/sanitario/campo/sincronizar", json=lote).status_code == 422  # extra="forbid"
    lote["registros"].pop()
    r = api.c.post("/sanitario/campo/sincronizar", json=lote).json()
    assert [i["status"] for i in r["itens"]] == ["gravado", "gravado"]
    # reenviar (o celular achou que não foi): idempotente
    r = api.c.post("/sanitario/campo/sincronizar", json=lote).json()
    assert [i["status"] for i in r["itens"]] == ["duplicado", "duplicado"]
    # outro celular registrou a 2401 também (chave diferente): conflito
    api.como("vet")
    r = api.c.post("/sanitario/campo/sincronizar", json={"dispositivo_uid": "cel-ana", "registros": [
        {"dia_id": dia["id"], "animal_id": a1, "caixa_id": cx["id"], "chave_idempotencia": "ana-1", "hora": "07:30"}]}).json()
    assert r["itens"][0]["status"] == "conflito" and r["conflitos"] == 1
    log_id = r["itens"][0]["conflito_log_id"]
    conflitos = api.c.get("/sanitario/conflitos").json()
    assert [c["id"] for c in conflitos] == [log_id]
    # quem não é aplicador nem admin não decide
    api.como("op2")
    assert api.c.post(f"/sanitario/conflitos/{log_id}/decidir", json={"manter": "novo"}).status_code == 403
    api.como("op")  # o Zé gravou o existente: é aplicador, pode decidir
    r = api.c.post(f"/sanitario/conflitos/{log_id}/decidir", json={"manter": "novo"})
    assert r.status_code == 200 and r.json()["registro"]["status"] == "gravado"
    assert api.c.get("/sanitario/conflitos").json() == []
    with api.s() as s:
        regs = s.exec(select(SanitarioRegistro).where(SanitarioRegistro.animal_id == a1)).all()
        assert sorted(r.estado for r in regs) == ["estornado", "valido"]
        assert {d.dispositivo_uid for d in s.exec(select(SanitarioDispositivo)).all()} == {"cel-ze", "cel-ana"}

    # heartbeat com fila -> 25 h sem contato -> nota ao admin (+ push uma vez)
    r = api.c.post("/sanitario/dispositivos/heartbeat", json={"dispositivo_uid": "cel-ze", "fila_pendentes": 12,
                                                              "fila_mais_antigo_em": "2026-10-20T10:40:00Z"})
    assert r.status_code == 200 and r.json()["fila_pendentes"] == 12
    from fazenda.rules.sanitario.job import notas_celular_offline
    from fazenda.rules.sanitario.push import despachar_push_notas
    enviados = []
    with api.s() as s:
        n = notas_celular_offline(s, 1, agora=datetime.utcnow() + timedelta(hours=25))
        s.commit()
        assert n == 1
        despachar_push_notas(s, 1, enviar=lambda **kw: enviados.append(kw))
        despachar_push_notas(s, 1, enviar=lambda **kw: enviados.append(kw))
    admins = {api.ids["adm"], api.ids["contr"]}
    assert {e["usuario_id"] for e in enviados} == admins and len(enviados) == len(admins)
    api.como("adm")
    assert api.c.get("/sanitario/dispositivos").json()[0]["fila_pendentes"] == 12
    # heartbeat zerado resolve a nota
    api.como("op")
    api.c.post("/sanitario/dispositivos/heartbeat", json={"dispositivo_uid": "cel-ze", "fila_pendentes": 0})
    with api.s() as s:
        assert s.exec(select(SanitarioNotaAgenda).where(SanitarioNotaAgenda.tipo == "celular_offline")).one().resolvida_em


def test_push_aglomerou_so_admins_e_vespera_para_todos(api):
    criar_caixa(api, b19())
    for n in ("2401", "2402", "2403"):
        animal(api, n, idade=150)
    from fazenda.rules.sanitario.job import executar_diaria
    from fazenda.rules.sanitario.push import despachar_push_notas
    cx2 = criar_caixa(api, _vacina_vacas(nome="Raiva", nome_curto="Raiva"))
    api.c.post("/sanitario/dias", json={"caixa_ids": [cx2["id"]], "data": (HOJE + timedelta(days=1)).isoformat(),
                                        "itens": []})
    enviados = []
    with api.s() as s:
        executar_diaria(s, 1, forcar=True)
        despachar_push_notas(s, 1, enviar=lambda **kw: enviados.append(kw))
        notas = {n.tipo: n for n in s.exec(select(SanitarioNotaAgenda)).all()}
    assert notas["aglomerou"].push_enviado_em and notas["vespera"].push_enviado_em
    por_titulo: dict[str, set] = {}
    for e in enviados:
        por_titulo.setdefault(e["titulo"], set()).add(e["usuario_id"])
    aglo = next(v for k, v in por_titulo.items() if "aglomerou" in k)
    vesp = next(v for k, v in por_titulo.items() if k.startswith("Amanhã"))
    assert aglo == {api.ids["adm"], api.ids["contr"]}
    assert vesp == {api.ids[k] for k in ("adm", "op", "op2", "vet", "contr")}
    # notas: operador não vê as "só administradores"
    api.como("op")
    assert {n["tipo"] for n in api.c.get("/sanitario/notas").json()} == {"vespera"}


# ════════════════════════════════════════════════════════════════════════════
# 8) Catálogo central: cockpit cria/publica; fazenda ativa (copia) e atualiza
# ════════════════════════════════════════════════════════════════════════════
def test_catalogo_ativar_copia_e_nova_versao_avisa_sem_sobrescrever(api):
    api.como("op")
    assert api.c.post("/painel-cowdata/sanitario/catalogo", json={
        "chave": "x", "nome": "X", "definicao": b19(nome="X")}).status_code == 403
    api.como("dono")
    r = api.c.post("/painel-cowdata/sanitario/catalogo", json={
        "chave": "lepto_teste", "nome": "Lepto teste", "tipo": "vacina",
        "definicao": {**_vacina_vacas(nome="Lepto teste"), "categorias_ref": ["novilha"]},
        "nota_mudanca": "v1"})
    assert r.status_code == 200, r.text
    item = r.json()
    assert item["versao_atual"] == 1 and item["definicao"]["categorias_ref"] == ["novilha"]
    api.como("adm")
    cat = next(c for c in api.c.get("/sanitario/catalogo").json() if c["chave"] == "lepto_teste")
    assert cat["caixas_da_fazenda"] == [] and cat["nova_versao"] is False
    api.como("op")
    assert api.c.post(f"/sanitario/catalogo/{cat['versao_id']}/ativar", json={}).status_code == 403
    api.como("adm")
    cx = api.c.post(f"/sanitario/catalogo/{cat['versao_id']}/ativar", json={"estado": "inativa"}).json()
    assert cx["estado"] == "inativa" and cx["catalogo"]["versao"] == 1
    with api.s() as s:
        novilha = s.exec(select(CategoriaManejo.id).where(CategoriaManejo.fazenda_id == 1,
                                                          CategoriaManejo.nome == "Novilha")).one()
    assert cx["definicao"]["categorias"] == [novilha]  # referência resolvida para o ID da fazenda
    assert api.c.post(f"/sanitario/catalogo/{cat['versao_id']}/ativar", json={}).status_code == 409  # nome duplicado
    # cockpit publica a v2: a caixa NÃO muda, só avisa
    api.como("dono")
    r = api.c.post(f"/painel-cowdata/sanitario/catalogo/{item['id']}/versoes", json={
        "definicao": {**_vacina_vacas(nome="Lepto teste"), "dose_valor": 3.0}, "nota_mudanca": "dose 3 mL"})
    assert r.json()["versao_atual"] == 2 and r.json()["copias_desatualizadas"] == 1
    api.como("adm")
    det = api.c.get(f"/sanitario/caixas/{cx['id']}").json()
    assert det["definicao"]["dose_valor"] == 5.0 and det["catalogo"]["nova_versao"] is True
    assert next(c for c in api.c.get("/sanitario/catalogo").json() if c["chave"] == "lepto_teste")["nova_versao"]
    assert any(n["tipo"] == "catalogo_mudou" for n in api.c.get("/sanitario/notas").json())
    r = api.c.post(f"/sanitario/caixas/{cx['id']}/atualizar-do-catalogo")
    assert r.status_code == 200
    det = r.json()
    assert det["definicao"]["dose_valor"] == 3.0 and det["versao_numero"] == 2 and det["catalogo"]["versao"] == 2
    assert not any(n["tipo"] == "catalogo_mudou" for n in api.c.get("/sanitario/notas").json())


def test_caixas_em_massa_arquivar_reativar(api):
    c1 = criar_caixa(api, b19(nome="A1"), estado="inativa")
    c2 = criar_caixa(api, b19(nome="A2"), estado="inativa")
    r = api.c.post("/sanitario/caixas/estado", json={"caixa_ids": [c1["id"], c2["id"]], "acao": "ativar"}).json()
    assert all(x["ok"] for x in r["resultados"])
    r = api.c.post("/sanitario/caixas/estado", json={"caixa_ids": [c1["id"], c2["id"]], "acao": "arquivar",
                                                     "motivo": "duplicadas"}).json()
    assert {c["id"] for c in api.c.get("/sanitario/caixas?estado=arquivada").json()} == {c1["id"], c2["id"]}
    assert api.c.get("/sanitario/caixas").json() == []
    criar_caixa(api, b19(nome="A1"))  # arquivar libera o nome
    r = api.c.post("/sanitario/caixas/estado", json={"caixa_ids": [c1["id"], c2["id"]], "acao": "reativar"}).json()
    res = {x["caixa_id"]: x for x in r["resultados"]}
    assert res[c1["id"]]["ok"] is False and res[c2["id"]]["ok"] is True


# ════════════════════════════════════════════════════════════════════════════
# 9) Nenhum GET grava
# ════════════════════════════════════════════════════════════════════════════
def test_nenhum_get_grava(api):
    cx = criar_caixa(api, b19(legal_comprovacao={"dias": 180, "aviso_dias": 30}))
    a = animal(api, "2401", idade=150)
    dia = api.c.post("/sanitario/dias", json={"caixa_ids": [cx["id"]], "data": HOJE.isoformat(),
                                              "itens": [{"animal_id": a}]}).json()
    api.c.post(f"/sanitario/dias/{dia['id']}/aplicar", json={})
    rid = api.c.get("/sanitario/registros").json()[0]["id"]
    with api.s() as s:
        rid_ok = s.get(SanitarioRegistro, rid) is not None
    assert rid_ok
    antes = contagens(api.eng)
    gets = [
        "/sanitario/caixas", f"/sanitario/caixas/{cx['id']}", f"/sanitario/caixas/{cx['id']}/ficha-vazia",
        f"/sanitario/ficha-vazia?caixa_ids={cx['id']}", "/sanitario/catalogo", "/sanitario/parametros",
        "/sanitario/veterinarios", "/sanitario/eu", "/sanitario/dias", f"/sanitario/dias/{dia['id']}",
        f"/sanitario/dias/data-prevista?caixa_ids={cx['id']}", f"/sanitario/dias/{dia['id']}/ficha",
        f"/sanitario/dias/{dia['id']}/log", f"/sanitario/dias/{dia['id']}/registros", "/sanitario/conflitos",
        "/sanitario/campo/hoje", f"/sanitario/dias/{dia['id']}/pacote-offline", "/sanitario/dispositivos",
        "/sanitario/painel", "/sanitario/janela", f"/sanitario/janela?caixa_id={cx['id']}", "/sanitario/calendario",
        "/sanitario/registros", f"/sanitario/historico?animal_id={a}", f"/sanitario/animais/{a}/situacao",
        f"/sanitario/animais/{a}/historico", "/sanitario/agenda/resumo", "/sanitario/notas", "/sanitario/prazos",
        "/sanitario/log", "/sanitario/leite-separado", "/sanitario/importar-planilha/modelo",
    ]
    for url in gets:
        r = api.c.get(url)
        assert r.status_code == 200, (url, r.text)
    assert contagens(api.eng) == antes
    ficha = api.c.get(f"/sanitario/dias/{dia['id']}/ficha").json()
    assert ficha["linhas"][0]["brinco"] == "2401" and ficha["linhas_em_branco"] == 3
    cal = api.c.get("/sanitario/calendario").json()
    assert cal["meses"][HOJE.month - 1]["aplicados_total"] == 1


# ════════════════════════════════════════════════════════════════════════════
# 10) Ida-e-volta do dia e do registro (todos os campos que o front envia)
# ════════════════════════════════════════════════════════════════════════════
def test_ida_e_volta_dia_e_registro(api):
    eid = estoque(api, qtd=50)
    eid2 = estoque(api, nome="B19 outro laboratório", qtd=50)
    with api.s() as s:
        lote = LoteEstoque(fazenda_id=1, estoque_id=eid2, data_compra=HOJE, quantidade_comprada=50,
                           quantidade_restante=50, validade=HOJE + timedelta(days=90))
        s.add(lote)
        s.commit()
        lote_id = lote.id
    cx = criar_caixa(api, b19(produto_modo="estoque", estoque_id=eid))
    a = animal(api, "2401", idade=150)
    enviado = {"caixa_ids": [cx["id"]], "data": (HOJE + timedelta(days=1)).isoformat(), "hora": "06:30",
               "data_prevista": (HOJE + timedelta(days=1)).isoformat(),
               "veterinario": {"pessoa_id": None, "texto": "Dr. Livre", "crmv": "CRMV-GO 77"},
               "produtos": {str(cx["id"]): {"modo": "estoque", "estoque_id": eid, "dose_valor": 3.0, "dose_unidade": "mL"}},
               "itens": [{"animal_id": a}], "observacao": "levar seringa"}
    dia = api.c.post("/sanitario/dias", json=enviado).json()
    got = api.c.get(f"/sanitario/dias/{dia['id']}").json()
    assert got["hora"] == "06:30" and got["observacao"] == "levar seringa"
    assert got["data"] == enviado["data"] and got["data_prevista"] == enviado["data_prevista"]
    assert got["veterinario"] == {"pessoa_id": None, "texto": "Dr. Livre", "crmv": "CRMV-GO 77"}
    prod = got["caixas"][0]["produto"]
    assert (prod["modo"], prod["estoque_id"], prod["dose_valor"], prod["dose_unidade"]) == ("estoque", eid, 3.0, "mL")
    # troca de produto e dose NA HORA, com partida/fabricante/validade/peso
    reg_in = {"animal_id": a, "caixa_id": cx["id"], "chave_idempotencia": "rt-1", "data": HOJE.isoformat(),
              "hora": "06:45", "produto": {"modo": "estoque", "estoque_id": eid2, "lote_estoque_id": lote_id,
                                           "dose_valor": 2.5, "dose_unidade": "mL"},
              "peso_kg": 180.0, "partida_texto": "P-123", "fabricante": "Lab X",
              "validade": (HOJE + timedelta(days=90)).isoformat(), "aplicador_texto": "Zé",
              "veterinario_texto": "Dr. Livre", "crmv_texto": "CRMV-GO 77",
              "atestado_numero": "AT-9", "atestado_destinatario": "SIDAGO",
              "consentimento": None, "carencia": None}
    r = api.c.post(f"/sanitario/dias/{dia['id']}/registros", json={"registros": [reg_in]}).json()
    # produto trocado sem carência cadastrada: o administrador decide no pop-up
    assert r["itens"][0]["status"] == "pendente" and r["itens"][0]["requer"] == ["carencia_decisao"]
    reg_in["carencia"] = {"modo": "tanque", "leite_dias": 0, "carne_dias": 0}
    r = api.c.post(f"/sanitario/dias/{dia['id']}/registros", json={"registros": [reg_in]}).json()
    assert r["itens"][0]["status"] == "gravado", r
    reg = api.c.get(f"/sanitario/dias/{dia['id']}/registros").json()[0]
    for k in ("hora", "partida_texto", "fabricante", "validade", "aplicador_texto", "veterinario_texto", "crmv_texto",
              "atestado_numero", "atestado_destinatario"):
        assert reg[k] == reg_in[k], k
    assert (reg["estoque_id"], reg["lote_estoque_id"], reg["dose_valor"]) == (eid2, lote_id, 2.5)
    assert reg["quantidade_baixada"] == 2.5 and reg["data"] == HOJE.isoformat()
    with api.s() as s:
        assert s.get(Estoque, eid2).quantidade == pytest.approx(47.5)
        assert s.get(Estoque, eid).quantidade == pytest.approx(50.0)


def test_dispensar_e_descartar_com_motivo_pulavel(api):
    cx = criar_caixa(api, b19())
    a1, a2 = animal(api, "2401", idade=150), animal(api, "2402", idade=150)
    api.como("op")
    r = api.c.post("/sanitario/situacoes/dispensar", json={"itens": [{"caixa_id": cx["id"], "animal_id": a1}]})
    assert r.status_code == 200 and r.json()["dispensados"] == 1
    r = api.c.post("/sanitario/situacoes/dispensar", json={"itens": [{"caixa_id": cx["id"], "animal_id": a2}],
                                                          "acao": "descartar", "motivo": "decisão do veterinário"})
    assert r.json()["dispensados"] == 1
    jan = api.c.get(f"/sanitario/janela?caixa_id={cx['id']}").json()[0]
    assert jan["animais"] == 0  # sumiram da lista, ficam registrados
    with api.s() as s:
        tipos = {lg.tipo: lg for lg in s.exec(select(SanitarioLog).where(SanitarioLog.tipo.startswith("situacao."))).all()}
        assert "motivo pulado" in tipos["situacao.dispensada"].texto_livre
        assert "decisão do veterinário" in tipos["situacao.descartada"].texto_livre
    api.como("adm", fid=2)
    assert api.c.post("/sanitario/situacoes/dispensar",
                      json={"itens": [{"caixa_id": cx["id"], "animal_id": a1}]}).status_code == 404
