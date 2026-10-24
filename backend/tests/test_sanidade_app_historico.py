"""
Menu › Sanidade do app de campo — espec aprovada pelo dono (out/2026).

Cobre as decisões com regra de servidor:
  1/2. Histórico de tratamentos e vacinas: GET /sanidade/aplicacoes junta o
       curativo (`Sanidade`) com o preventivo novo (`sanitario_registro`) quando
       recebe `tipo`; filtros de período (invertido = 400), animal exato, lote
       NA DATA (gravado ou reconstruído), tipo e doença; sem parâmetro nenhum, a
       resposta de sempre (o site depende dela); estornado não entra;
  3.   animal vendido/morto sai da fila e da contagem do dia aberto (com aviso
       `saidos`) e não recebe aplicação depois da baixa;
  4.   "Marcar cura" por qualquer usuário; editar/excluir só admin;
  5.   Remédios por Doença devolve a observação clínica (`nota`), dose/via/
       carência do cadastro da marca e `apresentacoes_cadastradas`;
  6.   dia aberto de data passada sai como `atrasado` com `dias_atraso`;
  7.   ordem de parto contada só na fazenda atual.
Sempre com duas fazendas (mesmos números de brinco) para provar o isolamento.
Nomes de fazenda e pessoas fictícios.
"""
from __future__ import annotations

from datetime import timedelta

from sqlmodel import select

from fazenda.models import (
    Animal, Doenca, Estoque, IndicacaoTerapeutica, MedicamentoComercial, MovimentoLote, Parto, PrincipioAtivo,
    ProtocoloSanitario, ProtocoloSanitarioLancamento, SanitarioDia, SanitarioDiaItem, SanitarioRegistro, Sanidade,
)
from tests.test_sanitario_api import HOJE, animal, api, b19, criar_caixa  # noqa: F401  (fixture `api`)

A1, M2 = "01 - Alta", "02 - Média"


def _d(n: int):
    return HOJE - timedelta(days=n)


def _add(api, *objs):
    with api.s() as s:
        for o in objs:
            s.add(o)
        s.commit()
        for o in objs:
            s.refresh(o)
        return objs


def _hist(api, **params):
    r = api.c.get("/sanidade/aplicacoes", params=params)
    assert r.status_code == 200, r.text
    return r.json()["aplicacoes"]


def _cenario(api):
    """Curativos e vacinas nas duas fazendas, com mudança de lote no meio."""
    cx = criar_caixa(api, b19())
    ids = {}
    for fid in (1, 2):
        for n in ("10", "11", "110"):
            with api.s() as s:
                a = Animal(fazenda_id=fid, numero=n, sexo="F", ativo=True, grupo_primario=M2 if n == "10" else A1)
                s.add(a)
                s.commit()
                ids[(fid, n)] = a.id
    with api.s() as s:
        # Vaca 10 (fazenda 1) ia do 01 para o 02 há 20 dias.
        s.add(MovimentoLote(numero_matriz="10", lote_origem=A1, lote_destino=M2, data_movimento=_d(20), fazenda_id=1))
        doenca = Doenca(nome="Mastite teste", fazenda_id=1)
        s.add(doenca)
        s.commit()
        proto = ProtocoloSanitario(nome="Protocolo mastite teste", doenca_id=doenca.id, fazenda_id=1)
        s.add(proto)
        s.commit()
        lanc = ProtocoloSanitarioLancamento(protocolo_id=proto.id, numero_matriz="11", data_inicio=_d(5), fazenda_id=1)
        s.add(lanc)
        s.commit()
        s.add_all([
            # curativo antes da mudança de lote (lote na data = 01, reconstruído)
            Sanidade(numero_matriz="10", produto="Antibiótico X", data_aplicacao=_d(30), natureza="curativo", fazenda_id=1,
                     responsavel="Zé Teste", obs="Mancando"),
            # curativo do protocolo (doença) com lote gravado no dia
            Sanidade(numero_matriz="11", produto="Intramamário Y", data_aplicacao=_d(5), natureza="curativo", fazenda_id=1,
                     protocolo_sanitario_lancamento_id=lanc.id, lote_no_dia=A1),
            # legado sem natureza conta como curativo
            Sanidade(numero_matriz="110", produto="Antitóxico Z", data_aplicacao=_d(2), fazenda_id=1),
            # BST: manejo — só aparece na chamada SEM tipo (site)
            Sanidade(numero_matriz="10", produto="BST", data_aplicacao=_d(3), natureza="preventivo", fazenda_id=1),
            # muito antigo: fora dos 60 dias
            Sanidade(numero_matriz="10", produto="Antigo", data_aplicacao=_d(200), natureza="curativo", fazenda_id=1),
            # outra fazenda, mesmo número
            Sanidade(numero_matriz="10", produto="Da outra fazenda", data_aplicacao=_d(4), natureza="curativo", fazenda_id=2),
        ])
        s.add_all([
            SanitarioRegistro(fazenda_id=1, animal_id=ids[(1, "10")], caixa_id=cx["id"], data=_d(10), ciclo_chave="U",
                              aplicador_texto="Ana Teste", dose_valor=2.0, dose_unidade="mL",
                              carencia_leite_ate=_d(7)),
            SanitarioRegistro(fazenda_id=1, animal_id=ids[(1, "11")], caixa_id=cx["id"], data=_d(9), ciclo_chave="U",
                              estado="estornado"),
            SanitarioRegistro(fazenda_id=1, numero_animal_texto="999", outro_texto="Vermífugo avulso", data=_d(8),
                              so_registro=True),
            SanitarioRegistro(fazenda_id=2, animal_id=ids[(2, "10")], outro_texto="Outra fazenda", data=_d(6), so_registro=True),
        ])
        # Partos: 2 na fazenda 1, 3 na fazenda 2 para o mesmo número
        s.add_all([Parto(numero_matriz="10", data_parto=_d(400 + k), fazenda_id=1) for k in range(2)]
                  + [Parto(numero_matriz="10", data_parto=_d(500 + k), fazenda_id=2) for k in range(3)])
        s.commit()
    return cx, ids


def test_sem_parametro_resposta_de_sempre_e_ordem_de_parto_por_fazenda(api):
    _cenario(api)
    api.como("adm", 1)
    linhas = _hist(api)
    produtos = sorted(r["produto"] for r in linhas)
    # só Sanidade da fazenda 1, inclusive BST e o antigo; nada do preventivo
    assert produtos == ["Antibiótico X", "Antigo", "Antitóxico Z", "BST", "Intramamário Y"]
    assert all(r["chave"].startswith("c") for r in linhas)
    # bug 1: a ordem de parto contava os partos das DUAS fazendas (5)
    assert {r["ordem_parto"] for r in linhas if r["numero"] == "10"} == {2}
    api.como("adm", 2)
    linhas2 = _hist(api)
    assert [r["produto"] for r in linhas2] == ["Da outra fazenda"] and linhas2[0]["ordem_parto"] == 3


def test_tipo_junta_curativo_e_preventivo_sem_bst_e_sem_estornado(api):
    _cenario(api)
    api.como("adm", 1)
    ini = _d(60).isoformat()
    todos = _hist(api, tipo="todos", data_inicio=ini, data_fim=HOJE.isoformat())
    por_tipo = {}
    for r in todos:
        por_tipo.setdefault(r["tipo_historico"], []).append(r)
    assert sorted(r["produto"] for r in por_tipo["curativo"]) == ["Antibiótico X", "Antitóxico Z", "Intramamário Y"]
    prev = sorted(por_tipo["preventivo"], key=lambda r: r["data"])
    assert [r["numero"] for r in prev] == ["10", "999"]  # estornado fora; brinco sem cadastro entra
    vac = prev[0]
    assert vac["chave"].startswith("p") and vac["categoria"] == "Vacina" and vac["responsavel"] == "Ana Teste"
    assert vac["dose"] == 2.0 and vac["carencia"]["liberacao_leite"] == _d(7).isoformat()
    assert prev[1]["produto"] == "Vermífugo avulso" and prev[1]["carencia"] is None
    # ordenado do mais recente para o mais antigo
    assert [r["data"] for r in todos] == sorted((r["data"] for r in todos), reverse=True)
    # chaves únicas entre as duas tabelas
    assert len({r["chave"] for r in todos}) == len(todos)
    assert {r["tipo_historico"] for r in _hist(api, tipo="preventivo")} == {"preventivo"}
    assert {r["tipo_historico"] for r in _hist(api, tipo="curativo")} == {"curativo"}
    # multi-tenant: nada da fazenda 2
    assert not any("outra fazenda" in (r["produto"] or "").lower() for r in todos)
    api.como("adm", 2)
    assert sorted(r["produto"] for r in _hist(api, tipo="todos")) == ["Da outra fazenda", "Outra fazenda"]


def test_filtros_periodo_numero_exato_lote_na_data_e_doenca(api):
    _cenario(api)
    api.como("adm", 1)
    r = api.c.get("/sanidade/aplicacoes", params={"data_inicio": HOJE.isoformat(), "data_fim": _d(1).isoformat()})
    assert r.status_code == 400 and "Período inválido" in r.json()["detail"]
    assert api.c.get("/sanidade/aplicacoes", params={"tipo": "qualquer"}).status_code == 400
    # número exato: "11" não traz o 110
    assert {x["numero"] for x in _hist(api, tipo="todos", numeros="11")} == {"11"}
    assert {x["numero"] for x in _hist(api, tipo="todos", numeros=["10", "110"])} == {"10", "110"}
    # lote NA DATA: a vaca 10 estava no 01 há 30 dias (curativo) e no 02 há 10 (vacina)
    lote01 = _hist(api, tipo="todos", lotes="01")
    assert {(x["numero"], x["produto"]) for x in lote01} >= {("10", "Antibiótico X"), ("11", "Intramamário Y")}
    assert not any(x["numero"] == "10" and x["tipo_historico"] == "preventivo" for x in lote01)
    x10 = next(x for x in lote01 if x["produto"] == "Antibiótico X")
    assert x10["lote_na_data"] == A1 and x10["lote_fonte"] == "historico" and x10["lote"] == M2  # `lote` = atual (site)
    gravado = next(x for x in lote01 if x["produto"] == "Intramamário Y")
    assert gravado["lote_fonte"] == "dia"
    lote02 = _hist(api, tipo="todos", lotes="02")
    assert [(x["numero"], x["tipo_historico"]) for x in lote02] == [("10", "preventivo")]
    # doença do protocolo aplicado
    with api.s() as s:
        did = s.exec(select(Doenca.id).where(Doenca.nome == "Mastite teste")).one()
    so_doenca = _hist(api, tipo="todos", doencas=did)
    assert [(x["produto"], x["doenca"]) for x in so_doenca] == [("Intramamário Y", "Mastite teste")]
    # período padrão de 60 dias deixa o antigo de fora
    assert "Antigo" not in {x["produto"] for x in _hist(api, tipo="curativo", data_inicio=_d(60).isoformat())}


def test_marcar_cura_qualquer_usuario_editar_excluir_so_admin(api):
    _cenario(api)
    api.como("adm", 1)
    alvo = next(x for x in _hist(api, tipo="curativo") if x["produto"] == "Antibiótico X")
    api.como("op", 1)
    r = api.c.post(f"/sanidade/aplicacoes/{alvo['id']}/cura", json={"curada": True})
    assert r.status_code == 200 and r.json()["curada"] is True
    assert next(x for x in _hist(api, tipo="curativo") if x["id"] == alvo["id"])["curada"] is True
    assert api.c.put(f"/sanidade/aplicacoes/{alvo['id']}", json={"obs": "x"}).status_code == 403
    assert api.c.delete(f"/sanidade/aplicacoes/{alvo['id']}").status_code == 403
    # outra fazenda: 404
    api.como("adm", 2)
    assert api.c.post(f"/sanidade/aplicacoes/{alvo['id']}/cura", json={"curada": False}).status_code == 404


def _dia_com(api, cx, animais_ids, data):
    api.como("adm", 1)
    r = api.c.post("/sanitario/dias", json={"caixa_ids": [cx["id"]], "data": data.isoformat(),
                                            "itens": [{"animal_id": a} for a in animais_ids]})
    assert r.status_code == 200, r.text
    return r.json()


def test_vendido_sai_da_fila_e_da_contagem_e_nao_recebe_aplicacao(api):
    cx = criar_caixa(api, b19())
    a1, a2, a3 = (animal(api, n, idade=150) for n in ("2501", "2502", "2503"))
    dia = _dia_com(api, cx, [a1, a2, a3], HOJE)
    assert dia["contagens"]["pendentes"] == 3
    with api.s() as s:
        for aid, quando in ((a2, _d(1)), (a3, HOJE)):
            a = s.get(Animal, aid)
            a.ativo, a.motivo_baixa, a.data_baixa = False, "Venda", quando
            s.add(a)
        s.commit()
    d = api.c.get(f"/sanitario/dias/{dia['id']}").json()
    assert d["contagens"]["pendentes"] == 1 and d["contagens"]["animais"] == 1 and d["contagens"]["saidos"] == 2
    assert {x["numero"] for x in d["saidos"]} == {"2502", "2503"} and d["saidos"][0]["motivo"] == "Venda"
    assert [i["animal_id"] for i in d["itens"]] == [a1]
    # campo/hoje e o pacote offline usam a mesma contagem
    hoje = api.c.get("/sanitario/campo/hoje").json()["dias"][0]
    assert hoje["contagens"]["pendentes"] == 1 and hoje["contagens"]["saidos"] == 2
    pac = api.c.get(f"/sanitario/dias/{dia['id']}/pacote-offline").json()
    assert [i["animal_id"] for i in pac["dia"]["itens"]] == [a1]
    # a cópia antiga do celular ainda manda o 2502 (vendido ONTEM) e o 2503
    # (vendido hoje, vacinado antes da venda): o primeiro é recusado
    api.como("op", 1)
    r = api.c.post("/sanitario/campo/sincronizar", json={"dispositivo_uid": "cel-teste", "registros": [
        {"dia_id": dia["id"], "animal_id": a2, "caixa_id": cx["id"], "chave_idempotencia": "s-1"},
        {"dia_id": dia["id"], "animal_id": a3, "caixa_id": cx["id"], "chave_idempotencia": "s-2"},
        {"dia_id": dia["id"], "animal_id": a1, "caixa_id": cx["id"], "chave_idempotencia": "s-3"},
    ]}).json()
    st = [i["status"] for i in r["itens"]]
    assert st == ["erro", "gravado", "gravado"], r
    assert r["itens"][0]["avisos"][0]["codigo"] == "saiu_do_rebanho"
    assert "saiu do rebanho" in r["itens"][0]["avisos"][0]["texto"]
    with api.s() as s:
        assert not s.exec(select(SanitarioRegistro).where(SanitarioRegistro.animal_id == a2)).all()


def test_dia_atrasado_sai_marcado_com_dias_de_atraso(api):
    cx = criar_caixa(api, b19())
    a1 = animal(api, "2601", idade=150)
    dia = _dia_com(api, cx, [a1], HOJE)
    with api.s() as s:  # marca o dia como se fosse de 3 dias atrás (ainda aberto)
        d = s.get(SanitarioDia, dia["id"])
        d.data = _d(3)
        s.add(d)
        s.commit()
    dias = api.c.get("/sanitario/campo/hoje").json()["dias"]
    assert dias[0]["quando"] == "hoje" and dias[0]["atrasado"] is True and dias[0]["dias_atraso"] == 3
    with api.s() as s:
        d = s.get(SanitarioDia, dia["id"])
        d.data = HOJE
        s.add(d)
        s.commit()
    dias = api.c.get("/sanitario/campo/hoje").json()["dias"]
    assert dias[0]["atrasado"] is False and dias[0]["dias_atraso"] == 0
    # outra fazenda não vê o dia
    api.como("adm", 2)
    assert api.c.get("/sanitario/campo/hoje").json()["dias"] == []


def test_remedios_por_doenca_nota_bula_e_apresentacoes(api):
    api.como("adm", 1)
    with api.s() as s:
        doenca = Doenca(nome="Pneumonia teste", fazenda_id=1)
        pa1 = PrincipioAtivo(nome="Princípio Um", fazenda_id=1, unidade_base="ml", unidade_apresentacao="frasco")
        pa2 = PrincipioAtivo(nome="Princípio Dois", fazenda_id=1, unidade_base="ml", unidade_apresentacao="frasco")
        pa3 = PrincipioAtivo(nome="Princípio Três", fazenda_id=1, unidade_base="ml", unidade_apresentacao="frasco")
        s.add_all([doenca, pa1, pa2, pa3])
        s.commit()
        m2 = MedicamentoComercial(principio_ativo_id=pa2.id, nome_comercial="Marca Dois", fazenda_id=1, dose_padrao=1.0,
                                  unidade_dose="mL", dose_base="por_kg_pv", dose_referencia_kg=20, via_padrao="IM",
                                  carencia_leite_dias=4, carencia_carne_dias=21)
        # marca de OUTRA fazenda não pode aparecer
        m_outra = MedicamentoComercial(principio_ativo_id=pa2.id, nome_comercial="Marca Alheia", fazenda_id=2, dose_texto="9 mL")
        s.add_all([m2, m_outra])
        s.commit()
        s.add_all([
            IndicacaoTerapeutica(principio_ativo_id=pa1.id, doenca_id=doenca.id, prioridade=1, fazenda_id=1,
                                 nota="Só após cultura"),
            IndicacaoTerapeutica(principio_ativo_id=pa2.id, doenca_id=doenca.id, prioridade=2, fazenda_id=1),
            IndicacaoTerapeutica(principio_ativo_id=pa3.id, doenca_id=doenca.id, prioridade=3, fazenda_id=1),
            # 1ª escolha com item cadastrado mas zerado; 2ª com estoque; 3ª sem item nenhum
            Estoque(nome="Item Um", unidade="ml", quantidade=0, principio_ativo_id=pa1.id, fazenda_id=1,
                    volume_por_apresentacao=100, volume_unidade="ml"),
            Estoque(nome="Item Dois", unidade="ml", quantidade=250, principio_ativo_id=pa2.id, fazenda_id=1,
                    medicamento_comercial_id=m2.id, volume_por_apresentacao=100, volume_unidade="ml"),
        ])
        s.commit()
        did = doenca.id
    r = api.c.get(f"/sanidade/indicacoes-doenca/{did}").json()
    op = {o["nome"]: o for o in r["opcoes"]}
    assert op["Princípio Um"]["nota"] == "Só após cultura" and op["Princípio Dois"]["nota"] is None
    assert op["Princípio Um"]["status_estoque"] == "out" and op["Princípio Um"]["apresentacoes_cadastradas"] == 1
    assert op["Princípio Três"]["apresentacoes_cadastradas"] == 0
    assert op["Princípio Dois"]["status_estoque"] != "out"
    bulas = op["Princípio Dois"]["bulas"]
    assert [b["marca"] for b in bulas] == ["Marca Dois"]
    assert bulas[0]["dose"] == "1 mL a cada 20 kg" and bulas[0]["via"] == "IM" and bulas[0]["em_estoque"] is True
    assert "leite — 4 dias" in bulas[0]["carencia"] and "carne — 21 dias" in bulas[0]["carencia"]
    assert op["Princípio Um"]["bulas"] == []
    # doença de outra fazenda: 404
    api.como("adm", 2)
    assert api.c.get(f"/sanidade/indicacoes-doenca/{did}").status_code == 404


def test_ficha_do_dia_nao_lista_quem_saiu(api):
    cx = criar_caixa(api, b19())
    a1, a2 = animal(api, "2701", idade=150), animal(api, "2702", idade=150)
    dia = _dia_com(api, cx, [a1, a2], HOJE)
    with api.s() as s:
        a = s.get(Animal, a2)
        a.ativo = False
        s.add(a)
        s.commit()
        assert len(s.exec(select(SanitarioDiaItem).where(SanitarioDiaItem.dia_id == dia["id"])).all()) == 2  # nada apagado
    r = api.c.get(f"/sanitario/dias/{dia['id']}/ficha")
    assert r.status_code == 200, r.text
    assert [ln["brinco"] for ln in r.json()["linhas"]] == ["2701"]
