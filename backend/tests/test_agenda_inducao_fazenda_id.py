"""
Regressão original: etapa de protocolo de indução de lactação some da Agenda
mesmo continuando visível (e "dar baixa"-vel) na Central de Protocolos.

Causa raiz (ver fazenda/api/routers/agenda.py, bloco "Protocolo de indução de
lactação" dentro de `calcular_agenda`): o trio `ProtocoloInducaoLancamento` /
`ProtocoloInducaoAplicacao` / `ProtocoloInducaoMedicamento` é filtrado com
`_da_fazenda` — igualdade ESTRITA de `fazenda_id`. Qualquer uma dessas linhas
com `fazenda_id IS NULL` nunca casa com `== fazenda_id`, então a etapa (ex.:
D6) some da Agenda sem sumir da Central de Protocolos.

O PR #474 contornou isso com uma variante tolerante a NULL (`_da_fazenda_
tolerante`) — o D6 voltava a aparecer, mas ao custo de um registro órfão
aparecer na Agenda de TODAS as fazendas (a mesma tolerância não sabe
distinguir "sem fazenda" de "de qualquer fazenda"). O PR claude/fazenda-id-
raiz reverte essa tolerância (decisão do dono do produto: não pode existir
registro sem fazenda_id) e ataca a CAUSA do NULL em vez do sintoma:

  1. `fazenda.auth.get_fazenda_id_escrita` — toda rota de escrita agora
     resolve uma fazenda de verdade (do token, ou do único vínculo do
     usuário) e recusa (409) em vez de gravar NULL quando não dá pra
     resolver com segurança.
  2. Migração 029227481e9e — preenche o histórico que já tinha ficado NULO.

Este arquivo cobre o cenário que originou o bug: um USUÁRIO COM TOKEN SEM
"fid" (a claim que carrega a fazenda escolhida no login) — token legado
emitido antes do multi-fazenda existir, ou de uma sessão "manter conectado"
de até 90 dias que nunca deslogou — lança uma indução de lactação. Antes
desta correção isso gravava fazenda_id NULO; agora resolve pelo único
vínculo do usuário (UsuarioFazenda) e o registro nasce corretamente
atribuído, aparecendo na Agenda com o filtro ESTRITO de volta.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    ContratoFazenda, ContratoFazendaModulo, Fazenda, ProtocoloInducaoAplicacao, ProtocoloInducaoLancamento,
    Usuario, UsuarioFazenda,
)


@pytest.fixture
def client_multi():
    """Duas fazendas com ContratoFazenda ativo (produtivo, pra /producao, e
    o resto pra /agenda) — mesmo padrão de test_inducao_fazenda_id.py.

    A conta de teste é um `Usuario` DE VERDADE (não um objeto fake solto),
    porque `get_fazenda_id_escrita` precisa consultar `UsuarioFazenda` pelo
    `id` dela quando o token não traz "fid" — é exatamente esse vínculo que
    este arquivo testa."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Um", ativa=True))
        s.add(Fazenda(id=2, nome="Fazenda Dois", ativa=True))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="produtivo", ativo=True))
        usuario = Usuario(username="funcionario_campo", senha_hash="x", papel="admin", ativo=True)
        s.add(usuario)
        s.commit()
        s.refresh(usuario)
        # Vínculo com UMA ÚNICA fazenda — é o caso do funcionário de campo
        # (celular que fica logado por meses, ver causa raiz #1 do PR).
        s.add(UsuarioFazenda(usuario_id=usuario.id, fazenda_id=1))
        s.commit()
        usuario_id = usuario.id

    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _UsuarioDoToken:
        """Devolve o Usuario de verdade recém-criado a cada chamada — via
        session nova, igual ao `get_current_user` real (que também resolve
        por consulta, não por instância cacheada)."""
        def __call__(self):
            with Session(engine) as s:
                return s.get(Usuario, usuario_id)

    main.app.dependency_overrides[get_current_user] = _UsuarioDoToken()

    def _client_sem_fid() -> TestClient:
        """Sessão com token SEM "fid" — não sobrescreve `get_fazenda_atual_id`,
        então a implementação real roda: sem header Authorization (o
        TestClient não manda nenhum aqui), ela devolve None — o MESMO
        resultado de um token legado de verdade sem a claim "fid"."""
        main.app.dependency_overrides.pop(get_fazenda_atual_id, None)
        return TestClient(main.app)

    def _client_com_fid(fazenda_id: int) -> TestClient:
        """Sessão normal, com a fazenda já selecionada — usada para LER
        depois, simulando outro colega (ou o mesmo usuário, já com o token
        novo) olhando a Agenda da fazenda certa."""
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id
        return TestClient(main.app)

    yield engine, _client_sem_fid, _client_com_fid, usuario_id

    main.app.dependency_overrides.clear()


def _criar_molde_inducao(c: TestClient) -> int:
    r = c.post("/cadastro/protocolos-inducao-lactacao", json={
        "nome": "Indução padrão",
        "etapas": [
            {"dia": 0, "tipo": "medicamento", "produto": "Benzoato de estradiol", "dose": 1, "unidade": "ml"},
            {"dia": 6, "tipo": "manejo", "produto": "Iniciar ordenha"},
        ],
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _eventos_inducao(resposta_json: dict) -> list[dict]:
    return [e for e in resposta_json["eventos"] if e.get("tipo") == "protocolo_inducao"]


class TestReproduzSintomaOriginal:
    def test_inducao_lancada_sem_fid_nasce_com_fazenda_id_e_aparece_na_agenda_estrita(self, client_multi):
        engine, client_sem_fid, client_com_fid, usuario_id = client_multi
        c = client_sem_fid()
        pid = _criar_molde_inducao(c)

        r = c.post("/producao/inducao-lactacao", json={
            "protocolo_id": pid,
            "animais": ["422"],
            "data_d0": (date.today() - timedelta(days=6)).isoformat(),
        })
        assert r.status_code == 201, r.text
        lancamento_id = r.json()["lancamento_id"]

        # 1) O registro NASCE com fazenda_id preenchido — não fica órfão.
        with Session(engine) as s:
            lanc = s.get(ProtocoloInducaoLancamento, lancamento_id)
            assert lanc.fazenda_id == 1, "deveria ter resolvido pelo único vínculo do usuário (UsuarioFazenda)"
            aps = s.exec(
                select(ProtocoloInducaoAplicacao).where(ProtocoloInducaoAplicacao.lancamento_id == lancamento_id)
            ).all()
            assert aps and all(a.fazenda_id == 1 for a in aps)

        # 2) E aparece na Agenda com o filtro ESTRITO (== fazenda_id, sem
        # tolerar NULL) — a etapa D6 do relato original (D0, também dentro
        # da janela de atraso já que data_d0 é 6 dias atrás, aparece junto —
        # não é o que este teste cobre).
        eventos = _eventos_inducao(client_com_fid(1).get("/agenda/").json())
        evento_d6 = next((e for e in eventos if e["dia"] == 6), None)
        assert evento_d6 is not None, f"D6 não apareceu na Agenda com filtro estrito: {eventos}"
        assert "422" in evento_d6["animais"]

        # 3) E não vaza pra Agenda de outra fazenda.
        eventos_outra = _eventos_inducao(client_com_fid(2).get("/agenda/").json())
        assert eventos_outra == []


class TestSemFidEDuasFazendas:
    def test_usuario_vinculado_a_duas_fazendas_sem_fid_e_recusado(self, client_multi):
        """Token sem "fid" + usuário vinculado a MAIS de uma fazenda: não dá
        pra saber qual — recusa com 409 em vez de adivinhar (ver
        resolver_fazenda_id_escrita)."""
        engine, client_sem_fid, client_com_fid, usuario_id = client_multi
        # Cadastra o molde ANTES de vincular a segunda fazenda — cadastro
        # também é rota de escrita (POST /cadastro/protocolos-inducao-
        # lactacao) e este teste quer isolar a recusa no LANÇAMENTO, não no
        # cadastro do molde.
        pid = _criar_molde_inducao(client_com_fid(1))
        with Session(engine) as s:
            s.add(UsuarioFazenda(usuario_id=usuario_id, fazenda_id=2))
            s.commit()

        c = client_sem_fid()
        r = c.post("/producao/inducao-lactacao", json={
            "protocolo_id": pid, "animais": ["422"], "data_d0": "2026-08-04",
        })
        assert r.status_code == 409, r.text


class TestFiltroEstritoNaoMostraRegistroOrfao:
    def test_lancamento_com_fazenda_id_nulo_nao_aparece_mais_na_agenda(self, client_multi):
        """Fim da tolerância do PR #474: um registro que PORVENTURA ainda
        exista com fazenda_id NULO (ex.: linha que a migração 029227481e9e
        não conseguiu resolver — 2+ fazendas reais e sem pai pra derivar)
        não aparece mais na Agenda de fazenda nenhuma. É a troca deliberada
        de "nunca fica órfão visível" por "nunca existe órfão" — a garantia
        passou a ser a torneira fechada (Passo 1) + o backfill (Passo 2),
        não mais a tolerância de leitura."""
        engine, _client_sem_fid, client_com_fid, _usuario_id = client_multi
        with Session(engine) as s:
            lanc = ProtocoloInducaoLancamento(
                protocolo_id=1, nome_protocolo="INDUÇÃO ÓRFÃ — TESTE",
                data_d0=date.today() - timedelta(days=6), fazenda_id=None,
            )
            s.add(lanc)
            s.commit()
            s.refresh(lanc)
            s.add(ProtocoloInducaoAplicacao(
                lancamento_id=lanc.id, numero_matriz="422", dia=6,
                descricao="Indução de lactação — D6", data_prevista=date.today(),
                realizada=False, fazenda_id=None,
            ))
            s.commit()

        eventos = _eventos_inducao(client_com_fid(1).get("/agenda/").json())
        assert eventos == []
