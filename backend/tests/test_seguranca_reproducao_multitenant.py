"""
Isolamento entre fazendas no router de Reprodução
(fazenda/api/routers/reproducao.py) — achados 8, 9, 10 e 11 da auditoria
(docs/security-audit/achados.json) e as ocorrências novas encontradas ao varrer
o arquivo inteiro.

O padrão em julgamento aqui não é "esqueceram de checar": é uma checagem que
PARECE checar e não checa —

    if not servico or (fazenda_id is not None and servico.fazenda_id not in (None, fazenda_id)):
        raise HTTPException(404, ...)

O `None` dentro da tupla faz o registro ÓRFÃO (`fazenda_id = NULL`) passar por
qualquer tenant. E registro órfão não é hipótese: `servico`, `parto`,
`secagem` e o lançamento de protocolo IATF sem molde estão entre as tabelas que
a migração `029227481e9e_backfill_fazenda_id_nulo` não consegue preencher
quando a instalação tem 2+ fazendas (ela imprime o que sobrou nulo no relatório
final e, por decisão explícita, não chuta o dono).

O CowData não tem RLS: o isolamento existe só no código. A trava de porta
(fazenda/auth.py::exigir_fazenda_selecionada, montada no router de Reprodução
em main.py) garante que a requisição diga EM QUAL fazenda ela acontece; estes
testes são a trava de dentro — dizer a fazenda certa não pode dar acesso ao
registro da outra, nem ao registro de ninguém.

404, nunca 403: um 403 já confirma que aquele id existe.

TOKEN DE VERDADE, nunca `dependency_overrides[get_fazenda_atual_id]` — é o
caminho token -> get_fazenda_atual_id -> get_fazenda_id_escrita -> consulta que
está sendo julgado, e falsificar o meio dele foi justamente o que deixou estes
furos passarem (ver tests/test_seguranca_p1_multitenant.py, que só usa
override). Mesmo espírito de tests/test_trava_fazenda_selecionada.py e
tests/test_seguranca_confirmacao_por_id_multitenant.py.

`animal.numero` não é mais único entre fazendas (migração c24befa94c1b): as
duas fazendas aqui têm uma vaca "500", que é como a colisão acontece na vida
real — e vários caminhos deste router casam matriz por NÚMERO (texto livre,
sem FK).
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    Animal, ContratoFazenda, ContratoFazendaModulo, EstoqueSemen, Fazenda, Parto, PesagemCorporal,
    ProtocoloIatfAplicacao, ProtocoloIatfLancamento, Sanidade, Secagem, Servico, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS

D0 = date(2026, 6, 1)
DATA_SERVICO = date(2026, 6, 12)

# A matriz que existe NAS DUAS fazendas — desde c24befa94c1b o número do animal
# só é único dentro da fazenda.
MATRIZ_COLIDIDA = "500"


@pytest.fixture
def ambiente(monkeypatch):
    """Duas fazendas-clientes, um admin em cada, e três variantes de cada
    registro atacável: da fazenda 1 (vítima), da fazenda 2 (controle positivo)
    e ÓRFÃO (`fazenda_id = NULL`, o resíduo real do backfill)."""
    engine = create_engine(
        f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)

    ids: dict[str, int] = {}
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Alvo"))
        s.add(Fazenda(id=2, nome="Fazenda Atacante"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
            s.add(Usuario(
                id=fid, username=f"admin{fid}", senha_hash=hash_senha("x"), papel="admin", ativo=True,
            ))
            s.add(UsuarioFazenda(usuario_id=fid, fazenda_id=fid))
            # A MESMA vaca "500" nas duas fazendas: nulípara, idade acima do
            # mínimo de aptidão e sem pesagem própria.
            s.add(Animal(
                numero=MATRIZ_COLIDIDA, ativo=True, sexo="F", categoria_abrev="Novilha",
                data_nasc=date(2023, 1, 10), fazenda_id=fid,
            ))

        # --- Achado 11: Servico ------------------------------------------
        servico_v = Servico(
            numero_matriz=MATRIZ_COLIDIDA, data_servico=DATA_SERVICO, tipo_servico="IA",
            reprodutor="REBEL", diagnostico="POSITIVO", data_diagnostico=date(2026, 7, 15),
            fazenda_id=1,
        )
        servico_orfao = Servico(
            numero_matriz="A900", data_servico=DATA_SERVICO, tipo_servico="IA",
            diagnostico="POSITIVO", data_diagnostico=date(2026, 7, 15), fazenda_id=None,
        )
        servico_atacante = Servico(
            numero_matriz=MATRIZ_COLIDIDA, data_servico=DATA_SERVICO, tipo_servico="IA",
            reprodutor="REBEL", fazenda_id=2,
        )
        s.add(servico_v)
        s.add(servico_orfao)
        s.add(servico_atacante)

        # --- Achado 12 (11 no relatório impresso): Parto ------------------
        parto_v = Parto(numero_matriz=MATRIZ_COLIDIDA, data_parto=date(2026, 3, 1), ordem_parto=2, fazenda_id=1)
        parto_orfao = Parto(numero_matriz="A900", data_parto=date(2026, 3, 1), ordem_parto=2, fazenda_id=None)
        s.add(parto_v)
        s.add(parto_orfao)

        # --- Secagem (mesma família; a checagem daqui já era estrita) -----
        secagem_v = Secagem(numero_matriz=MATRIZ_COLIDIDA, data_secagem=date(2026, 4, 1), motivo="rotina", fazenda_id=1)
        secagem_orfa = Secagem(numero_matriz="A900", data_secagem=date(2026, 4, 1), motivo="rotina", fazenda_id=None)
        s.add(secagem_v)
        s.add(secagem_orfa)

        # --- Achado 10: protocolo IATF ------------------------------------
        # Lançamento SEM molde (protocolo_id nulo) é o que sobra órfão: a
        # migração deriva `protocolo_iatf_lancamento.fazenda_id` do molde-pai,
        # e sem pai não há de onde derivar.
        lanc_v = ProtocoloIatfLancamento(nome_protocolo="Ovsynch da Fazenda 1", data_d0=D0, fazenda_id=1)
        lanc_orfao = ProtocoloIatfLancamento(nome_protocolo="Protocolo Órfão", data_d0=D0, fazenda_id=None)
        s.add(lanc_v)
        s.add(lanc_orfao)
        s.commit()
        s.refresh(lanc_v)
        s.refresh(lanc_orfao)
        ap_v = ProtocoloIatfAplicacao(
            lancamento_id=lanc_v.id, numero_matriz=MATRIZ_COLIDIDA, dia=0, descricao="D0",
            data_prevista=D0, realizada=False, fazenda_id=1,
        )
        ap_orfa = ProtocoloIatfAplicacao(
            lancamento_id=lanc_orfao.id, numero_matriz=MATRIZ_COLIDIDA, dia=0, descricao="D0",
            data_prevista=D0, realizada=False, fazenda_id=None,
        )
        s.add(ap_v)
        s.add(ap_orfa)

        # --- Achado 9: pesagem corporal ------------------------------------
        # Só a fazenda 1 pesou a vaca "500". O roteiro do veterinário da
        # fazenda 2 não pode enxergar esse peso — é ele que decide se a
        # novilha entra em "aptas vazias".
        s.add(PesagemCorporal(
            numero_matriz=MATRIZ_COLIDIDA, data_pesagem=date(2026, 5, 20), peso_kg=420.0, fazenda_id=1,
        ))

        # --- Ocorrência nova: Estoque de Sêmen no mapa de tipo ------------
        # Só a fazenda 1 cadastrou o touro REBEL, como SEXADO.
        s.add(EstoqueSemen(touro_nome="REBEL", tipo="sexado", doses=10, fazenda_id=1))

        # --- Indução de cio (delete por id) --------------------------------
        inducao_v = Sanidade(
            numero_matriz=MATRIZ_COLIDIDA, data_aplicacao=date(2026, 5, 2), produto="Cloprostenol",
            atividade="Indução de cio", fazenda_id=1,
        )
        s.add(inducao_v)
        s.commit()

        ids.update(
            servico_vitima=servico_v.id,
            servico_orfao=servico_orfao.id,
            servico_atacante=servico_atacante.id,
            parto_vitima=parto_v.id,
            parto_orfao=parto_orfao.id,
            secagem_vitima=secagem_v.id,
            secagem_orfa=secagem_orfa.id,
            lanc_vitima=lanc_v.id,
            lanc_orfao=lanc_orfao.id,
            aplicacao_vitima=ap_v.id,
            aplicacao_orfa=ap_orfa.id,
            inducao_vitima=inducao_v.id,
        )

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine, ids
    main.app.dependency_overrides.clear()


def _cab(fazenda_id: int):
    """Token REAL do admin daquela fazenda, com a claim "fid" carimbada."""
    return {"Authorization": f"Bearer {criar_token(f'admin{fazenda_id}', fazenda_id=fazenda_id)}"}


# ---------------------------------------------------------------------------
# Achado 11 — PUT /reproducao/servicos/{id}
# ---------------------------------------------------------------------------
def test_editar_servico_de_outra_fazenda_e_recusado(ambiente):
    c, engine, ids = ambiente
    r = c.put(
        f"/reproducao/servicos/{ids['servico_vitima']}",
        json={"diagnostico": "NEGATIVO", "motivo_perda_prenhez": "aborto"}, headers=_cab(2),
    )
    assert r.status_code == 404, (
        "404, nunca 403 — responder 403 já confirma que o id existe. "
        f"Resposta: {r.status_code} {r.text[:200]}"
    )
    with Session(engine) as s:
        assert s.get(Servico, ids["servico_vitima"]).diagnostico == "POSITIVO", (
            "a fazenda 2 reescreveu o diagnóstico de gestação de um serviço da fazenda 1"
        )


def test_editar_servico_orfao_e_recusado_por_todas_as_fazendas(ambiente):
    """O furo específico do achado 11: `servico.fazenda_id not in (None,
    fazenda_id)` deixava o Servico órfão (fazenda_id NULL, resíduo real do
    backfill em instalação com 2+ fazendas) editável por QUALQUER tenant."""
    c, engine, ids = ambiente
    for fazenda in (1, 2):
        r = c.put(
            f"/reproducao/servicos/{ids['servico_orfao']}",
            json={"diagnostico": "NEGATIVO"}, headers=_cab(fazenda),
        )
        assert r.status_code == 404, (
            f"a fazenda {fazenda} editou um serviço SEM DONO. Registro órfão não é registro de "
            f"todo mundo. Resposta: {r.status_code} {r.text[:200]}"
        )
    with Session(engine) as s:
        assert s.get(Servico, ids["servico_orfao"]).diagnostico == "POSITIVO"


def test_editar_servico_da_propria_fazenda_continua_funcionando(ambiente):
    c, engine, ids = ambiente
    r = c.put(
        f"/reproducao/servicos/{ids['servico_atacante']}",
        json={"diagnostico": "POSITIVO", "metodo_diagnostico": "ultrassom"}, headers=_cab(2),
    )
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.get(Servico, ids["servico_atacante"]).diagnostico == "POSITIVO"


# ---------------------------------------------------------------------------
# Achado 12 — PUT /reproducao/partos/{id}
# ---------------------------------------------------------------------------
def test_editar_parto_de_outra_fazenda_e_recusado(ambiente):
    c, engine, ids = ambiente
    r = c.put(
        f"/reproducao/partos/{ids['parto_vitima']}", json={"tipo_parto": "aborto"}, headers=_cab(2),
    )
    assert r.status_code == 404, f"Resposta: {r.status_code} {r.text[:200]}"
    with Session(engine) as s:
        assert s.get(Parto, ids["parto_vitima"]).tipo_parto != "aborto", (
            "a fazenda 2 transformou o parto de uma matriz da fazenda 1 em aborto"
        )


def test_editar_parto_orfao_e_recusado_por_todas_as_fazendas(ambiente):
    c, engine, ids = ambiente
    for fazenda in (1, 2):
        r = c.put(
            f"/reproducao/partos/{ids['parto_orfao']}", json={"tipo_parto": "aborto"}, headers=_cab(fazenda),
        )
        assert r.status_code == 404, (
            f"a fazenda {fazenda} editou um parto SEM DONO. Resposta: {r.status_code} {r.text[:200]}"
        )
    with Session(engine) as s:
        assert s.get(Parto, ids["parto_orfao"]).tipo_parto != "aborto"


def test_editar_parto_da_propria_fazenda_continua_funcionando(ambiente):
    c, engine, ids = ambiente
    with Session(engine) as s:
        proprio = Parto(numero_matriz=MATRIZ_COLIDIDA, data_parto=date(2026, 3, 5), ordem_parto=1, fazenda_id=2)
        s.add(proprio)
        s.commit()
        s.refresh(proprio)
        proprio_id = proprio.id
    r = c.put(f"/reproducao/partos/{proprio_id}", json={"retencao_placenta": True}, headers=_cab(2))
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.get(Parto, proprio_id).retencao_placenta is True


# ---------------------------------------------------------------------------
# PUT /reproducao/secagens/{id} — mesma família (a checagem já era estrita;
# aqui ela vira consulta filtrada, e este teste é a trava contra a regressão)
# ---------------------------------------------------------------------------
def test_editar_secagem_de_outra_fazenda_ou_orfa_e_recusado(ambiente):
    c, engine, ids = ambiente
    assert c.put(
        f"/reproducao/secagens/{ids['secagem_vitima']}", json={"motivo": "problema"}, headers=_cab(2),
    ).status_code == 404
    for fazenda in (1, 2):
        assert c.put(
            f"/reproducao/secagens/{ids['secagem_orfa']}", json={"motivo": "problema"}, headers=_cab(fazenda),
        ).status_code == 404
    with Session(engine) as s:
        assert s.get(Secagem, ids["secagem_vitima"]).motivo == "rotina"
        assert s.get(Secagem, ids["secagem_orfa"]).motivo == "rotina"


def test_editar_secagem_da_propria_fazenda_continua_funcionando(ambiente):
    c, engine, ids = ambiente
    with Session(engine) as s:
        propria = Secagem(
            numero_matriz=MATRIZ_COLIDIDA, data_secagem=date(2026, 4, 3), motivo="rotina", fazenda_id=2,
        )
        s.add(propria)
        s.commit()
        s.refresh(propria)
        propria_id = propria.id
    r = c.put(f"/reproducao/secagens/{propria_id}", json={"motivo": "problema"}, headers=_cab(2))
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# Achado 10 — POST/DELETE /reproducao/protocolo-iatf/{lancamento_id}/animais
# ---------------------------------------------------------------------------
def test_adicionar_animais_a_protocolo_iatf_orfao_e_recusado(ambiente):
    """Lançamento IATF sem molde não tem pai de onde a migração derive a
    fazenda — fica órfão, e a checagem tolerante deixava qualquer tenant
    despejar animais dentro dele (fechando de quebra os serviços em aberto
    dessas matrizes, ver fechar_servicos_abertos_por_reinseminacao)."""
    c, engine, ids = ambiente
    r = c.post(
        f"/reproducao/protocolo-iatf/{ids['lanc_orfao']}/animais",
        json={"animais": ["A700"]}, headers=_cab(2),
    )
    assert r.status_code == 404, f"Resposta: {r.status_code} {r.text[:200]}"
    with Session(engine) as s:
        aplicacoes = s.exec(
            select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == "A700")
        ).all()
        assert aplicacoes == [], "a fazenda 2 escreveu dentro de um protocolo IATF sem dono"


def test_adicionar_animais_a_protocolo_iatf_de_outra_fazenda_e_recusado(ambiente):
    c, engine, ids = ambiente
    r = c.post(
        f"/reproducao/protocolo-iatf/{ids['lanc_vitima']}/animais",
        json={"animais": ["A700"]}, headers=_cab(2),
    )
    assert r.status_code == 404, f"Resposta: {r.status_code} {r.text[:200]}"
    with Session(engine) as s:
        assert s.exec(
            select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == "A700")
        ).all() == []


def test_adicionar_animais_ao_proprio_protocolo_iatf_continua_funcionando(ambiente):
    c, engine, ids = ambiente
    with Session(engine) as s:
        proprio = ProtocoloIatfLancamento(nome_protocolo="Ovsynch da Fazenda 2", data_d0=D0, fazenda_id=2)
        s.add(proprio)
        s.commit()
        s.refresh(proprio)
        proprio_id = proprio.id
        s.add(ProtocoloIatfAplicacao(
            lancamento_id=proprio_id, numero_matriz="A800", dia=0, descricao="D0",
            data_prevista=D0, realizada=False, fazenda_id=2,
        ))
        s.commit()
    r = c.post(
        f"/reproducao/protocolo-iatf/{proprio_id}/animais", json={"animais": ["A700"]}, headers=_cab(2),
    )
    assert r.status_code == 200, r.text
    assert r.json()["adicionados"] == 1
    with Session(engine) as s:
        criadas = s.exec(
            select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == "A700")
        ).all()
        assert criadas and all(a.fazenda_id == 2 for a in criadas)


def test_remover_animal_de_protocolo_iatf_alheio_ou_orfao_e_recusado(ambiente):
    """O DELETE é o espelho do POST — e apaga dado de verdade."""
    c, engine, ids = ambiente
    for chave in ("lanc_vitima", "lanc_orfao"):
        r = c.delete(
            f"/reproducao/protocolo-iatf/{ids[chave]}/animais/{MATRIZ_COLIDIDA}", headers=_cab(2),
        )
        assert r.status_code == 404, f"{chave}: {r.status_code} {r.text[:200]}"
    with Session(engine) as s:
        assert s.get(ProtocoloIatfAplicacao, ids["aplicacao_vitima"]) is not None, (
            "a fazenda 2 removeu a matriz do protocolo IATF da fazenda 1"
        )
        assert s.get(ProtocoloIatfAplicacao, ids["aplicacao_orfa"]) is not None, (
            "a fazenda 2 apagou a etapa de um protocolo IATF sem dono"
        )


def test_remover_animal_do_proprio_protocolo_iatf_continua_funcionando(ambiente):
    c, engine, ids = ambiente
    with Session(engine) as s:
        proprio = ProtocoloIatfLancamento(nome_protocolo="Ovsynch da Fazenda 2", data_d0=D0, fazenda_id=2)
        s.add(proprio)
        s.commit()
        s.refresh(proprio)
        proprio_id = proprio.id
        ap = ProtocoloIatfAplicacao(
            lancamento_id=proprio_id, numero_matriz=MATRIZ_COLIDIDA, dia=0, descricao="D0",
            data_prevista=D0, realizada=False, fazenda_id=2,
        )
        s.add(ap)
        s.commit()
        s.refresh(ap)
        ap_id = ap.id
    r = c.delete(f"/reproducao/protocolo-iatf/{proprio_id}/animais/{MATRIZ_COLIDIDA}", headers=_cab(2))
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.get(ProtocoloIatfAplicacao, ap_id) is None


# ---------------------------------------------------------------------------
# POST /reproducao/servico-lote — vínculo com lançamento IATF vindo do corpo
# ---------------------------------------------------------------------------
def test_servico_em_lote_nao_se_vincula_a_protocolo_iatf_orfao(ambiente):
    """`protocolo_lancamento_id` chega no CORPO da requisição. Com a checagem
    tolerante, o lançamento órfão era aceito: os serviços da fazenda 2 nasciam
    carimbados com o nome do protocolo de outra instalação — e a etapa de
    inseminação de lá era resolvida por esse nome."""
    c, engine, ids = ambiente
    r = c.post(
        "/reproducao/servico-lote",
        json={
            "animais": [MATRIZ_COLIDIDA], "data_servico": DATA_SERVICO.isoformat(), "tipo": "iatf",
            "protocolo_lancamento_id": ids["lanc_orfao"], "auto_lancar_iatf": False, "forcar": True,
        },
        headers=_cab(2),
    )
    assert r.status_code == 200, r.text
    assert r.json()["criados"] == 0 and r.json()["incompativeis"] == [MATRIZ_COLIDIDA], (
        "a fazenda 2 vinculou a inseminação da vaca dela a um protocolo IATF sem dono "
        f"(resposta: {r.json()})"
    )
    with Session(engine) as s:
        assert s.exec(select(Servico).where(Servico.protocolo == "Protocolo Órfão")).all() == [], (
            "o nome do protocolo órfão foi carimbado num serviço da fazenda 2"
        )


def test_servico_em_lote_no_proprio_protocolo_iatf_continua_funcionando(ambiente):
    c, engine, ids = ambiente
    with Session(engine) as s:
        proprio = ProtocoloIatfLancamento(nome_protocolo="Ovsynch da Fazenda 2", data_d0=D0, fazenda_id=2)
        s.add(proprio)
        s.commit()
        s.refresh(proprio)
        proprio_id = proprio.id
        s.add(ProtocoloIatfAplicacao(
            lancamento_id=proprio_id, numero_matriz=MATRIZ_COLIDIDA, dia=0, descricao="D0",
            data_prevista=D0, realizada=False, fazenda_id=2,
        ))
        s.commit()
    r = c.post(
        "/reproducao/servico-lote",
        json={
            "animais": [MATRIZ_COLIDIDA], "data_servico": DATA_SERVICO.isoformat(), "tipo": "iatf",
            "protocolo_lancamento_id": proprio_id, "auto_lancar_iatf": False, "forcar": True,
        },
        headers=_cab(2),
    )
    assert r.status_code == 200, r.text
    assert r.json()["criados"] == 1, r.json()
    with Session(engine) as s:
        criado = s.exec(
            select(Servico).where(Servico.fazenda_id == 2, Servico.protocolo == "Ovsynch da Fazenda 2")
        ).all()
        assert len(criado) == 1


# ---------------------------------------------------------------------------
# Achado 9 — GET /reproducao/agenda-veterinario (peso de outra fazenda)
# ---------------------------------------------------------------------------
def test_agenda_veterinario_nao_usa_peso_de_animal_de_outra_fazenda(ambiente):
    """A pesagem era a única subconsulta do roteiro sem filtro de fazenda. O
    peso é o que decide se a novilha entra em "aptas vazias" — e as duas
    fazendas têm uma vaca "500"."""
    c, engine, ids = ambiente
    r = c.get("/reproducao/agenda-veterinario", headers=_cab(2))
    assert r.status_code == 200, r.text
    listas = r.json()["listas"]
    for nome, itens in listas.items():
        for item in itens:
            if item.get("numero_matriz") == MATRIZ_COLIDIDA:
                assert item.get("peso") is None, (
                    f"a lista {nome} da fazenda 2 mostrou {item.get('peso')} kg para a vaca "
                    f"{MATRIZ_COLIDIDA} — o peso é da vaca de mesmo número da fazenda 1"
                )
    assert [i["numero_matriz"] for i in listas["novilhas_aptas_vazias"]] == [], (
        "a novilha da fazenda 2 foi dada como apta usando a pesagem da fazenda 1"
    )


def test_agenda_veterinario_continua_vendo_o_peso_da_propria_fazenda(ambiente):
    c, engine, ids = ambiente
    r = c.get("/reproducao/agenda-veterinario", headers=_cab(1))
    assert r.status_code == 200, r.text
    pesos = [
        item.get("peso")
        for itens in r.json()["listas"].values()
        for item in itens
        if item.get("numero_matriz") == MATRIZ_COLIDIDA
    ]
    assert pesos and all(p == 420.0 for p in pesos), (
        f"a fazenda 1 deixou de enxergar a própria pesagem: {pesos}"
    )


# ---------------------------------------------------------------------------
# Ocorrência nova — GET /reproducao/servicos completava o tipo de sêmen com o
# Estoque de Sêmen de TODAS as fazendas
# ---------------------------------------------------------------------------
def test_listagem_de_servicos_nao_completa_tipo_de_semen_com_estoque_alheio(ambiente):
    c, engine, ids = ambiente
    r = c.get("/reproducao/servicos", headers=_cab(2))
    assert r.status_code == 200, r.text
    servicos = r.json()["servicos"]
    assert len(servicos) == 1, servicos
    assert servicos[0]["tipo_semen"] is None, (
        "o serviço da fazenda 2 foi completado com o tipo de sêmen (sexado) cadastrado para o "
        "touro REBEL no Estoque de Sêmen da fazenda 1"
    )


def test_listagem_de_servicos_continua_completando_com_o_proprio_estoque(ambiente):
    c, engine, ids = ambiente
    r = c.get("/reproducao/servicos", headers=_cab(1))
    assert r.status_code == 200, r.text
    por_numero = {s["numero"]: s for s in r.json()["servicos"]}
    assert por_numero[MATRIZ_COLIDIDA]["tipo_semen"] == "sexado", (
        "a fazenda 1 deixou de completar o tipo de sêmen com o próprio Estoque de Sêmen"
    )


# ---------------------------------------------------------------------------
# DELETE /reproducao/inducao-cio/{id} — a checagem já era estrita; trava de
# regressão da conversão para consulta filtrada
# ---------------------------------------------------------------------------
def test_excluir_inducao_de_cio_de_outra_fazenda_e_recusado(ambiente):
    c, engine, ids = ambiente
    r = c.delete(f"/reproducao/inducao-cio/{ids['inducao_vitima']}", headers=_cab(2))
    assert r.status_code == 404, f"Resposta: {r.status_code} {r.text[:200]}"
    with Session(engine) as s:
        assert s.get(Sanidade, ids["inducao_vitima"]) is not None


def test_excluir_inducao_de_cio_da_propria_fazenda_continua_funcionando(ambiente):
    c, engine, ids = ambiente
    with Session(engine) as s:
        propria = Sanidade(
            numero_matriz=MATRIZ_COLIDIDA, data_aplicacao=date(2026, 5, 4), produto="Cloprostenol",
            atividade="Indução de cio", fazenda_id=2,
        )
        s.add(propria)
        s.commit()
        s.refresh(propria)
        propria_id = propria.id
    assert c.delete(f"/reproducao/inducao-cio/{propria_id}", headers=_cab(2)).status_code == 200
    with Session(engine) as s:
        assert s.get(Sanidade, propria_id) is None
