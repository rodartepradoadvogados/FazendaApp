"""
Isolamento entre fazendas nos blocos de FARMÁCIA, SANIDADE (calendário) e
FINANCEIRO (recibo) — os achados de severidade ALTA da auditoria cujo `local`
aponta para esses arquivos, mais os furos da mesma família encontrados na
varredura de hoje.

O CowData não tem RLS: o isolamento existe só no código da aplicação. A trava
de porta (fazenda/auth.py::exigir_fazenda_selecionada, montada em main.py)
garante que a requisição diga EM QUAL fazenda ela acontece; estes testes são a
trava de dentro — dizer a fazenda certa não pode dar acesso ao registro da
outra, nem ao registro de NINGUÉM (`fazenda_id` NULL).

Os dois anti-padrões em julgamento aqui:

  1. o TOLERANTE — `if fazenda_id is not None: ...where(fazenda_id == ...)`.
     Um token sem "fid" desliga o isolamento inteiro de uma vez.
  2. a TOLERÂNCIA A NULL — `registro.fazenda_id not in (None, fazenda_id)` (e
     a versão implícita dela: nunca comparar nada). Parece checagem, mas o
     registro ÓRFÃO passa por QUALQUER inquilino — e órfão existe de verdade
     (ver a migração 029227481e9e_backfill_fazenda_id_nulo, que imprime o que
     sobrou e, por decisão explícita, não chuta o dono).

TOKEN DE VERDADE, nunca `dependency_overrides[get_fazenda_atual_id]`: é o
caminho token -> get_fazenda_atual_id -> get_fazenda_id_escrita -> consulta
que está em julgamento, e falsificar o meio dele já deixou furo passar antes.
Mesmo desenho de tests/test_seguranca_confirmacao_por_id_multitenant.py.

Onde o casamento é por TEXTO (nome de produto sanitário, nome de fornecedor,
número do animal), as duas fazendas recebem propositalmente o MESMO texto: a
colisão entre tenants é o caso normal, não o excepcional — `animal.numero`
nem sequer é mais único entre fazendas desde a migração c24befa94c1b.
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
    Animal, CalendarioSanitario, ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Doenca,
    EventoSanitario, Fazenda, Fornecedor, IndicacaoTerapeutica, MedicamentoComercial, Pessoa,
    PrincipioAtivo, Sanidade, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS

D = date(2026, 6, 1)


@pytest.fixture
def ambiente(monkeypatch):
    """Duas fazendas-clientes, um admin em cada, e um alvo da fazenda 1 para
    cada rota sob teste. A fazenda 2 ganha o espelho onde o teste precisa
    provar que a rota continua funcionando para o dono (controle positivo)."""
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
        s.commit()

        # ── Farmácia: catálogo GLOBAL (fazenda_id NULL) + o de cada fazenda ──
        # O global é o padrão CowData semeado igual para todo produtor: nenhum
        # tenant pode apagá-lo (é justamente o registro que o token sem "fid"
        # apagava para todo mundo de uma vez).
        pa_global = PrincipioAtivo(nome="Ivermectina (padrão)", fazenda_id=None)
        pa1 = PrincipioAtivo(nome="Ocitocina", fazenda_id=1)
        pa2 = PrincipioAtivo(nome="Ocitocina", fazenda_id=2)  # mesmo nome nas duas
        doenca_global = Doenca(nome="Mastite (padrão)", fazenda_id=None, tipo="doenca")
        doenca1 = Doenca(nome="Retenção de placenta", fazenda_id=1, tipo="doenca")
        doenca2 = Doenca(nome="Retenção de placenta", fazenda_id=2, tipo="doenca")
        for o in (pa_global, pa1, pa2, doenca_global, doenca1, doenca2):
            s.add(o)
        s.commit()
        for o in (pa_global, pa1, pa2, doenca_global, doenca1, doenca2):
            s.refresh(o)

        marca_global = MedicamentoComercial(
            principio_ativo_id=pa_global.id, nome_comercial="Ivomec Gold", laboratorio="Boehringer",
            fazenda_id=None,
        )
        marca1 = MedicamentoComercial(
            principio_ativo_id=pa1.id, nome_comercial="Ocitocina Alvo", laboratorio="Lab da Fazenda 1",
            fazenda_id=1,
        )
        marca2 = MedicamentoComercial(
            principio_ativo_id=pa2.id, nome_comercial="Ocitocina Atacante", fazenda_id=2,
        )
        ind1 = IndicacaoTerapeutica(principio_ativo_id=pa1.id, doenca_id=doenca1.id, prioridade=1, fazenda_id=1)
        ind2 = IndicacaoTerapeutica(principio_ativo_id=pa2.id, doenca_id=doenca2.id, prioridade=1, fazenda_id=2)
        # Personalização da fazenda 1: clone de uma doença global (origem_id
        # preenchido) — é o que DELETE /indicacoes/{id}/personalizar desfaz.
        doenca1_clone = Doenca(
            nome="Mastite (padrão)", fazenda_id=1, tipo="doenca", origem_id=doenca_global.id,
        )
        # Princípio ativo ÓRFÃO — nem global de catálogo nem de fazenda
        # nenhuma. É a linha que a migração de backfill não consegue atribuir.
        pa_orfao = PrincipioAtivo(nome="Princípio sem dono", fazenda_id=None)
        for o in (marca_global, marca1, marca2, ind1, ind2, doenca1_clone, pa_orfao):
            s.add(o)

        # ── Sanidade: evento sanitário por fazenda + um órfão ──
        ev1 = EventoSanitario(nome="Brucelose B19", fazenda_id=1, categoria_preventiva="vacina")
        ev2 = EventoSanitario(nome="Brucelose B19", fazenda_id=2, categoria_preventiva="vacina")
        ev_orfao = EventoSanitario(nome="Vermífugo (legado)", fazenda_id=None)
        for o in (ev1, ev2, ev_orfao):
            s.add(o)

        # Aplicação preventiva da fazenda 1 com um produto de nome comum: é o
        # casamento por TEXTO que _ultimo_evento_por_produto faz.
        s.add(Sanidade(
            numero_matriz="500", data_aplicacao=date(2026, 5, 20), produto="Ivomec Gold",
            natureza="preventivo", fazenda_id=1,
        ))

        # ── Financeiro: fornecedor e funcionário HOMÔNIMOS nas duas fazendas ──
        s.add(Fornecedor(nome="Agropecuária Central", tipo="fornecedor",
                         email="compras@fazenda1.com.br", fazenda_id=1))
        s.add(Fornecedor(nome="Agropecuária Central", tipo="fornecedor",
                         email="compras@fazenda2.com.br", fazenda_id=2))
        s.add(Pessoa(nome="José da Silva", tipo="funcionario", email="jose@fazenda1.com.br", fazenda_id=1))
        s.add(Pessoa(nome="José da Silva", tipo="funcionario", email="jose@fazenda2.com.br", fazenda_id=2))
        s.add(ContaGerencial(
            numero_lancamento="LC-2026-00001", fornecedor_cliente="Agropecuária Central",
            tipo_documento="Nota fiscal", tipo="despesa", valor_total=1000.0, fazenda_id=2,
        ))
        s.add(ContaGerencial(
            numero_lancamento="LC-2026-00002", fornecedor_cliente="José da Silva",
            tipo_documento="Folha de pagamento", tipo="despesa", valor_total=2000.0, fazenda_id=2,
        ))

        # ── Produção: as DUAS fazendas têm uma vaca "500" (c24befa94c1b) ──
        s.add(Animal(numero="500", ativo=True, fazenda_id=1, grupo_primario="Lote Alvo"))
        s.add(Animal(numero="500", ativo=True, fazenda_id=2, grupo_primario="Lote Atacante"))
        s.add(Sanidade(
            numero_matriz="500", data_aplicacao=date(2026, 5, 10), produto="Lactotropin",
            atividade="BST", dose=500.0, unidade="mg", responsavel="Vet da Fazenda 1", fazenda_id=1,
        ))
        s.commit()

        for o in (marca_global, marca1, marca2, ind1, ind2, doenca1_clone, pa_orfao,
                  ev1, ev2, ev_orfao):
            s.refresh(o)

        ids.update(
            pa_global=pa_global.id, pa1=pa1.id, pa2=pa2.id, pa_orfao=pa_orfao.id,
            doenca_global=doenca_global.id, doenca1=doenca1.id, doenca2=doenca2.id,
            doenca1_clone=doenca1_clone.id,
            marca_global=marca_global.id, marca1=marca1.id, marca2=marca2.id,
            ind1=ind1.id, ind2=ind2.id,
            ev1=ev1.id, ev2=ev2.id, ev_orfao=ev_orfao.id,
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


def _regra(evento_id: int, **extra) -> dict:
    corpo = {
        "evento_sanitario_id": evento_id,
        "frequencia_valor": 12,
        "frequencia_unidade": "meses",
        "data_evento": D.isoformat(),
    }
    corpo.update(extra)
    return corpo


# ---------------------------------------------------------------------------
# Achado 33 — DELETE de marca/indicação/personalização (farmacia.py)
# ---------------------------------------------------------------------------
def test_marca_de_outra_fazenda_nao_e_excluida(ambiente):
    c, engine, ids = ambiente
    r = c.delete(f"/farmacia/medicamentos/{ids['marca1']}", headers=_cab(2))
    assert r.status_code == 404, r.text
    with Session(engine) as s:
        assert s.get(MedicamentoComercial, ids["marca1"]) is not None, (
            "a fazenda 2 apagou a marca comercial da fazenda 1 — o id vem na URL, é inteiro "
            "pequeno e sequencial; junto com a marca vai a bula (dose, via, carência de leite/carne)"
        )


def test_marca_global_do_catalogo_nao_e_excluida_por_um_tenant(ambiente):
    """O caso `fazenda_id = NULL`: a marca do catálogo padrão CowData é de
    TODAS as fazendas-clientes. Apagá-la a partir de uma delas apagaria a
    referência de dose/carência de todo mundo de uma vez."""
    c, engine, ids = ambiente
    r = c.delete(f"/farmacia/medicamentos/{ids['marca_global']}", headers=_cab(2))
    assert r.status_code == 404, r.text
    with Session(engine) as s:
        assert s.get(MedicamentoComercial, ids["marca_global"]) is not None, (
            "um tenant apagou a marca GLOBAL (fazenda_id NULL) do catálogo padrão"
        )


def test_marca_da_propria_fazenda_continua_sendo_excluida(ambiente):
    c, engine, ids = ambiente
    r = c.delete(f"/farmacia/medicamentos/{ids['marca1']}", headers=_cab(1))
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.get(MedicamentoComercial, ids["marca1"]) is None


def test_indicacao_de_outra_fazenda_nao_e_excluida(ambiente):
    c, engine, ids = ambiente
    r = c.delete(f"/farmacia/indicacoes/{ids['ind1']}", headers=_cab(2))
    assert r.status_code == 404, r.text
    with Session(engine) as s:
        assert s.get(IndicacaoTerapeutica, ids["ind1"]) is not None, (
            "a fazenda 2 apagou o vínculo princípio↔doença da fazenda 1 — é o que alimenta o "
            "'substituto inteligente' no lançamento da aplicação"
        )


def test_indicacao_da_propria_fazenda_continua_sendo_excluida(ambiente):
    c, engine, ids = ambiente
    r = c.delete(f"/farmacia/indicacoes/{ids['ind2']}", headers=_cab(2))
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.get(IndicacaoTerapeutica, ids["ind2"]) is None


def test_personalizacao_de_outra_fazenda_nao_e_desfeita(ambiente):
    c, engine, ids = ambiente
    r = c.delete(f"/farmacia/indicacoes/{ids['doenca1_clone']}/personalizar", headers=_cab(2))
    assert r.status_code == 404, r.text
    with Session(engine) as s:
        assert s.get(Doenca, ids["doenca1_clone"]) is not None, (
            "a fazenda 2 desfez a personalização da fazenda 1 — a rota apaga a Doenca clonada, "
            "suas indicações e as marcas clonadas junto"
        )


def test_token_sem_fazenda_nao_entra_na_farmacia(ambiente):
    """A OUTRA metade do achado 33, e a que descreve o ataque original: o
    `if fazenda_id is not None` das rotas de exclusão só isolava enquanto o
    token trouxesse "fid" — sem ele, o DELETE valia para qualquer linha do
    banco, incluindo o catálogo GLOBAL.

    Hoje esse token nem chega ao handler: a trava de porta
    (auth.py::exigir_fazenda_selecionada, montada em main.py junto do router
    da Farmácia) recusa antes com 409 sempre que existe fazenda cadastrada.
    Este teste é o que impede a defesa de baixo (as consultas já filtradas
    acima) e a de cima (a porta) de serem removidas sem ninguém notar — foi
    a assimetria entre PUT e DELETE que criou o achado, e a porta que hoje o
    segura. Usuário com DUAS fazendas: é uma das três formas reais de um
    token sair sem "fid" (ver o docstring de exigir_fazenda_selecionada)."""
    c, engine, ids = ambiente
    with Session(engine) as s:
        s.add(UsuarioFazenda(usuario_id=2, fazenda_id=1))
        s.commit()
    sem_fid = {"Authorization": f"Bearer {criar_token('admin2')}"}
    r = c.delete(f"/farmacia/medicamentos/{ids['marca_global']}", headers=sem_fid)
    assert r.status_code == 409, r.text
    with Session(engine) as s:
        assert s.get(MedicamentoComercial, ids["marca_global"]) is not None
        assert s.get(MedicamentoComercial, ids["marca1"]) is not None


# ---------------------------------------------------------------------------
# Mesma família do achado 33 — PUT/DELETE de princípio ativo (farmacia.py)
# ---------------------------------------------------------------------------
def test_principio_ativo_de_outra_fazenda_nao_e_editado(ambiente):
    c, engine, ids = ambiente
    r = c.put(
        f"/farmacia/principios/{ids['pa1']}",
        json={"nome": "Sequestrado", "ativo": True, "estoque_minimo_apresentacoes": 1.0},
        headers=_cab(2),
    )
    assert r.status_code == 404, r.text
    with Session(engine) as s:
        assert s.get(PrincipioAtivo, ids["pa1"]).nome == "Ocitocina"


def test_principio_ativo_orfao_nao_e_excluido_por_qualquer_tenant(ambiente):
    """O caso `fazenda_id = NULL`. `checar_e_desvincular_exclusao_principio`
    desvincula/apaga em 7 tabelas dependentes — a linha de ninguém não pode
    ser demolida por qualquer um."""
    c, engine, ids = ambiente
    r = c.delete(f"/farmacia/principios/{ids['pa_orfao']}", headers=_cab(2))
    assert r.status_code == 404, r.text
    with Session(engine) as s:
        assert s.get(PrincipioAtivo, ids["pa_orfao"]) is not None


def test_principio_ativo_da_propria_fazenda_continua_sendo_excluido(ambiente):
    c, engine, ids = ambiente
    # A marca sai primeiro — a rota recusa (400) princípio ainda referenciado
    # por medicamento, e é essa recusa de NEGÓCIO que o controle positivo não
    # pode confundir com a recusa de ISOLAMENTO (404) que os testes acima
    # exigem.
    assert c.delete(f"/farmacia/medicamentos/{ids['marca2']}", headers=_cab(2)).status_code == 200
    r = c.delete(f"/farmacia/principios/{ids['pa2']}", headers=_cab(2))
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.get(PrincipioAtivo, ids["pa2"]) is None


# ---------------------------------------------------------------------------
# Furo novo — PUT /farmacia/medicamentos aceitava principio_ativo_id alheio
# ---------------------------------------------------------------------------
def test_marca_nao_migra_para_principio_de_outra_fazenda(ambiente):
    """A atacante edita uma marca que É dela, mas apontando `principio_ativo_id`
    para o princípio da vítima — escrita cruzada disfarçada de edição própria,
    sem tocar em nenhum id da vítima na URL."""
    c, engine, ids = ambiente
    r = c.put(
        f"/farmacia/medicamentos/{ids['marca2']}",
        json={
            "principio_ativo_id": ids["pa1"], "nome_comercial": "Ocitocina Atacante",
            "ativo": True, "alerta": "PROPAGANDA DA CONCORRENTE",
        },
        headers=_cab(2),
    )
    assert r.status_code == 400, r.text
    with Session(engine) as s:
        assert s.get(MedicamentoComercial, ids["marca2"]).principio_ativo_id == ids["pa2"], (
            "a marca da fazenda 2 foi repontada para o princípio ativo da fazenda 1"
        )


def test_detalhe_do_principio_nao_lista_marca_de_outra_fazenda(ambiente):
    """A outra metade do mesmo furo: mesmo com a linha já plantada no banco, a
    vítima não pode enxergar a marca da atacante na tela de onde ela tira a
    dose que vai aplicar no animal."""
    c, engine, ids = ambiente
    with Session(engine) as s:
        intrusa = MedicamentoComercial(
            principio_ativo_id=ids["pa1"], nome_comercial="Marca Intrusa", fazenda_id=2,
        )
        s.add(intrusa)
        s.commit()
    r = c.get(f"/farmacia/principios/{ids['pa1']}", headers=_cab(1))
    assert r.status_code == 200, r.text
    nomes = {m["nome_comercial"] for m in r.json()["marcas"]}
    assert "Marca Intrusa" not in nomes, (
        f"a fazenda 1 recebeu a marca comercial da fazenda 2 no detalhe do próprio princípio: {nomes}"
    )
    assert "Ocitocina Alvo" in nomes, "controle positivo: a marca da própria fazenda sumiu"


# ---------------------------------------------------------------------------
# Furo novo (família do achado 29) — calendário sanitário aceitava evento alheio
# ---------------------------------------------------------------------------
def test_regra_do_calendario_nao_nasce_apontando_evento_de_outra_fazenda(ambiente):
    c, engine, ids = ambiente
    r = c.post("/sanidade/calendario", json=_regra(ids["ev1"]), headers=_cab(2))
    assert r.status_code == 400, r.text
    with Session(engine) as s:
        intrusas = s.exec(
            select(CalendarioSanitario).where(CalendarioSanitario.evento_sanitario_id == ids["ev1"])
        ).all()
        assert [x for x in intrusas if x.fazenda_id == 2] == [], (
            "a fazenda 2 criou uma regra de calendário apontada para o evento sanitário da "
            "fazenda 1 — a resposta devolve nome do protocolo, categoria e serviço financeiro dele"
        )


def test_regra_do_calendario_nao_aceita_evento_orfao(ambiente):
    """O caso `fazenda_id = NULL`: evento sanitário sem dono (seed legado de
    cadastro/sanitario.py) não pode ser o evento de qualquer um."""
    c, engine, ids = ambiente
    r = c.post("/sanidade/calendario", json=_regra(ids["ev_orfao"]), headers=_cab(2))
    assert r.status_code == 400, r.text


def test_regra_do_calendario_nao_aceita_doenca_de_outra_fazenda(ambiente):
    c, engine, ids = ambiente
    r = c.post(
        "/sanidade/calendario", json=_regra(ids["ev2"], doenca_id=ids["doenca1"]), headers=_cab(2)
    )
    assert r.status_code == 400, r.text


def test_regra_do_calendario_nao_aceita_principio_ativo_de_outra_fazenda(ambiente):
    c, engine, ids = ambiente
    r = c.post(
        "/sanidade/calendario",
        json=_regra(ids["ev2"], principio_ativo_id=ids["pa1"]), headers=_cab(2),
    )
    assert r.status_code == 400, r.text


def test_regra_do_calendario_da_propria_fazenda_continua_sendo_criada(ambiente):
    """Controle positivo — inclusive com doença e princípio do catálogo GLOBAL
    (fazenda_id NULL), que é de todo mundo e não pode ser recusado junto."""
    c, engine, ids = ambiente
    r = c.post(
        "/sanidade/calendario",
        json=_regra(ids["ev2"], doenca_id=ids["doenca_global"], principio_ativo_id=ids["pa_global"]),
        headers=_cab(2),
    )
    assert r.status_code == 200, r.text
    assert r.json()["evento_sanitario_nome"] == "Brucelose B19"


def test_editar_regra_nao_a_repontar_para_evento_de_outra_fazenda(ambiente):
    c, engine, ids = ambiente
    criada = c.post("/sanidade/calendario", json=_regra(ids["ev2"]), headers=_cab(2))
    assert criada.status_code == 200, criada.text
    regra_id = criada.json()["id"]
    r = c.put(f"/sanidade/calendario/{regra_id}", json=_regra(ids["ev1"]), headers=_cab(2))
    assert r.status_code == 400, r.text
    with Session(engine) as s:
        assert s.get(CalendarioSanitario, regra_id).evento_sanitario_id == ids["ev2"]


# ---------------------------------------------------------------------------
# Achado 28 — "último evento" do calendário casava por NOME DE PRODUTO
# ---------------------------------------------------------------------------
def test_ultimo_evento_do_calendario_nao_vem_da_outra_fazenda(ambiente):
    """A fazenda 2 cadastra uma regra com o MESMO nome de produto que a
    fazenda 1 já aplicou. O vocabulário de produto é compartilhado ("Ivomec
    Gold" é o mesmo frasco nas duas), então a colisão é o caso normal."""
    c, engine, ids = ambiente
    criada = c.post(
        "/sanidade/calendario", json=_regra(ids["ev2"], produto="Ivomec Gold"), headers=_cab(2)
    )
    assert criada.status_code == 200, criada.text
    assert criada.json()["ultimo_evento_data"] is None, (
        "a fazenda 2 recebeu a data da última aplicação de 'Ivomec Gold' feita pela fazenda 1"
    )
    assert criada.json()["ultimo_evento_id"] is None, (
        "a fazenda 2 recebeu o id da linha Sanidade da fazenda 1 em ultimo_evento_id"
    )

    listagem = c.get("/sanidade/calendario", headers=_cab(2))
    assert listagem.status_code == 200, listagem.text
    assert all(r["ultimo_evento_id"] is None for r in listagem.json())

    # Controle positivo: para a DONA da aplicação, o último evento aparece.
    propria = c.post(
        "/sanidade/calendario", json=_regra(ids["ev1"], produto="Ivomec Gold"), headers=_cab(1)
    )
    assert propria.status_code == 200, propria.text
    assert propria.json()["ultimo_evento_data"] == "2026-05-20"


# ---------------------------------------------------------------------------
# Achado 13 (resíduo) — destinatário do recibo resolvido só pelo NOME
# ---------------------------------------------------------------------------
def test_destinatario_do_recibo_nao_pega_email_de_fornecedor_homonimo(ambiente):
    c, engine, ids = ambiente
    r = c.get("/financeiro/lancamentos/LC-2026-00001/destinatario-recibo", headers=_cab(2))
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "compras@fazenda2.com.br", (
        "o e-mail devolvido veio do cadastro de fornecedor de OUTRA fazenda (mesmo nome) — e é "
        "esse endereço que o POST .../recibo/enviar usa como destinatário sugerido"
    )


def test_destinatario_do_recibo_de_folha_nao_pega_email_de_homonimo(ambiente):
    c, engine, ids = ambiente
    r = c.get("/financeiro/lancamentos/LC-2026-00002/destinatario-recibo", headers=_cab(2))
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "jose@fazenda2.com.br", (
        "o recibo de folha resolveu o e-mail do funcionário homônimo de outra fazenda"
    )


def test_recibo_de_lancamento_de_outra_fazenda_continua_404(ambiente):
    """Trava do achado 13 propriamente dito: numero_lancamento é sequencial e
    GLOBAL (LC-{ano}-{00001,...}), portanto trivialmente enumerável entre
    tenants."""
    c, engine, ids = ambiente
    r = c.get("/financeiro/lancamentos/LC-2026-00001/destinatario-recibo", headers=_cab(1))
    assert r.status_code == 404, r.text
    r = c.post(
        "/financeiro/lancamentos/LC-2026-00001/recibo/enviar",
        data={"destinatario": "atacante@exemplo.com"}, headers=_cab(1),
    )
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# Achado 6 — relatório de BST agregava Sanidade e Animal de todas as fazendas
# ---------------------------------------------------------------------------
def test_relatorio_bst_nao_mistura_fazendas(ambiente):
    """As duas fazendas têm uma vaca "500" (o número não é mais único entre
    fazendas desde c24befa94c1b), e só a fazenda 1 tem aplicação de BST."""
    c, engine, ids = ambiente
    r = c.get("/producao/relatorio-bst", headers=_cab(2))
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 0, (
        f"a fazenda 2 recebeu as aplicações de BST da fazenda 1: {r.json()['aplicacoes']}"
    )

    propria = c.get("/producao/relatorio-bst", headers=_cab(1))
    assert propria.status_code == 200, propria.text
    assert propria.json()["total"] == 1
    assert propria.json()["aplicacoes"][0]["lote"] == "Lote Alvo", (
        "o lote/categoria veio do animal '500' da outra fazenda"
    )
