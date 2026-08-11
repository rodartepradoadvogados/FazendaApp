"""
Teste-sentinela do PR claude/fazenda-id-raiz — a garantia de que a torneira
ficou fechada de verdade.

Percorre TODOS os modelos com coluna `fazenda_id` (`fazenda.models`, ~147
tabelas) e falha se QUALQUER linha ficar nula depois de um fluxo normal de
criação — sem exceções, sem lista de tabelas toleradas. Exercita um usuário
com token SEM "fid" (o cenário exato da causa raiz #1: token legado/sessão
"manter conectado" que nunca deslogou) vinculado a uma ÚNICA fazenda real
via UsuarioFazenda, passando por um recorte representativo dos domínios
tocados no Passo 1 — reprodutivo (protocolo IATF), sanitário (cadastro +
lançamento de protocolo), produtivo (indução de lactação) e financeiro
(lançamento). Tabelas fora deste recorte simplesmente não têm linha
nenhuma neste banco isolado — a checagem "zero NULL" continua válida pra
elas por vacuidade, e cresce sozinha conforme mais fluxos forem cobertos por
outros testes que reusem este mesmo `client` (ver fixture).

Não precisa de ContratoFazenda/ContratoFazendaModulo: com o token sem "fid",
`exigir_contrato_ativo`/`exigir_modulo_contratado` (fazenda.auth) recebem
`fazenda_id=None` de `get_fazenda_atual_id` e pulam a checagem inteira (é o
"SEM RETROATIVIDADE" documentado nessas dependências) — só
`get_fazenda_id_escrita`, usado dentro de cada endpoint de escrita, resolve
de verdade a partir do vínculo do usuário.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Fazenda, Usuario, UsuarioFazenda


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Sentinela", ativa=True))
        usuario = Usuario(username="funcionario_campo", senha_hash="x", papel="admin", ativo=True)
        s.add(usuario)
        s.commit()
        s.refresh(usuario)
        s.add(UsuarioFazenda(usuario_id=usuario.id, fazenda_id=1))
        s.commit()
        usuario_id = usuario.id

    main.app.dependency_overrides[database.get_session] = _get_session_override

    def _usuario_do_token():
        with Session(engine) as s:
            return s.get(Usuario, usuario_id)

    main.app.dependency_overrides[get_current_user] = _usuario_do_token
    # De propósito: NÃO sobrescreve get_fazenda_atual_id — a implementação
    # real roda, sem header Authorization, devolvendo None (token sem "fid").

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _tabelas_com_fazenda_id() -> list[str]:
    # `.tables.values()` (não `.sorted_tables`) — só precisamos dos nomes e
    # colunas, não da ordem topológica (que nem sempre existe: algumas
    # tabelas têm FK mutuamente dependente, ver aviso do SQLAlchemy).
    return [
        t.name for t in SQLModel.metadata.tables.values()
        if "fazenda_id" in t.columns
    ]


def _linhas_nulas(engine, tabela: str) -> int:
    with engine.connect() as conn:
        return conn.exec_driver_sql(f'SELECT COUNT(*) FROM "{tabela}" WHERE fazenda_id IS NULL').scalar() or 0


class TestSentinelaFazendaIdNuncaNulo:
    def test_fluxo_normal_de_criacao_nao_deixa_fazenda_id_nulo(self, client):
        c, engine = client

        # ── Reprodutivo: protocolo IATF ad-hoc (sem catálogo — protocolo_id
        # opcional) — mesmo caminho usado pelo bot do Telegram (ver
        # rules/telegram_fluxos.py, ramo "protocolo_iatf").
        r = c.post("/reproducao/protocolo-iatf", json={"animais": ["501"], "data_d0": date.today().isoformat()})
        assert r.status_code in (200, 201), r.text

        # ── Sanitário: cadastra o molde (Configurações > Cadastro) e lança.
        r = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Mastite — sentinela", "eh_mastite": False, "dia_inicial": 0,
            "etapas": [{"dia": 0, "produto": "Penicilina", "dosagem": 10, "unidade": "ml"}],
        })
        assert r.status_code == 200, r.text
        protocolo_id = r.json()["id"]
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": protocolo_id, "numeros_matriz": ["502"], "data_inicio": date.today().isoformat(),
        })
        assert r.status_code == 201, r.text

        # ── Produtivo: indução de lactação (o sintoma original do PR).
        r = c.post("/cadastro/protocolos-inducao-lactacao", json={
            "nome": "Indução — sentinela",
            "etapas": [{"dia": 0, "tipo": "medicamento", "produto": "Benzoato de estradiol", "dose": 1, "unidade": "ml"}],
        })
        assert r.status_code == 200, r.text
        molde_id = r.json()["id"]
        r = c.post("/producao/inducao-lactacao", json={
            "protocolo_id": molde_id, "animais": ["503"], "data_d0": date.today().isoformat(),
        })
        assert r.status_code == 201, r.text

        # ── Financeiro: lançamento avulso.
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Ração concentrada", "valor_total": 150.0}],
            "data_emissao": date.today().isoformat(),
        })
        assert r.status_code == 201, r.text

        # ── Varredura: NENHUMA tabela com fazenda_id pode ter linha nula.
        tabelas_com_linha_nula: dict[str, int] = {}
        for tabela in _tabelas_com_fazenda_id():
            n = _linhas_nulas(engine, tabela)
            if n:
                tabelas_com_linha_nula[tabela] = n

        assert not tabelas_com_linha_nula, (
            "Linha(s) com fazenda_id NULO depois de um fluxo normal de escrita — a torneira "
            f"não fechou de verdade: {tabelas_com_linha_nula}"
        )

    def test_usuario_sem_nenhuma_fazenda_vinculada_e_recusado_no_lancamento(self, client):
        """Causa raiz #2 do PR: usuário sem NENHUM vínculo de fazenda e sem
        "fid" no token — recusa com 409 em vez de gravar fazenda_id nulo."""
        c, engine = client
        with Session(engine) as s:
            usuario = Usuario(username="sem_fazenda", senha_hash="x", papel="admin", ativo=True)
            s.add(usuario)
            s.commit()
            s.refresh(usuario)
            usuario_id_sem_fazenda = usuario.id

        import main
        from fazenda.auth import get_current_user

        def _usuario_sem_fazenda():
            with Session(engine) as s:
                return s.get(Usuario, usuario_id_sem_fazenda)

        override_original = main.app.dependency_overrides[get_current_user]
        main.app.dependency_overrides[get_current_user] = _usuario_sem_fazenda
        try:
            r = c.post("/reproducao/protocolo-iatf", json={"animais": ["999"], "data_d0": date.today().isoformat()})
            assert r.status_code == 409, r.text
        finally:
            main.app.dependency_overrides[get_current_user] = override_original
