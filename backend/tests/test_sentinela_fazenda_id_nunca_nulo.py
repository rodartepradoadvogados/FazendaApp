"""
Teste-sentinela do PR claude/fazenda-id-raiz — a garantia de que a torneira
ficou fechada de verdade.

Percorre TODOS os modelos com coluna `fazenda_id` (`fazenda.models`, ~147
tabelas) e falha se QUALQUER linha ficar nula depois de um fluxo normal de
criação — sem exceções de tabela, com UMA única exceção de FORMA de contagem
(ver `_ALIMENTO_NUTRICIONAL_TOLERA_NULO_LEGITIMO` abaixo). Exercita um
usuário com token SEM "fid" (o cenário exato da causa raiz #1: token
legado/sessão "manter conectado" que nunca deslogou) vinculado a uma ÚNICA
fazenda real via UsuarioFazenda, passando por um recorte representativo dos
domínios tocados no Passo 1 — reprodutivo (protocolo IATF), sanitário
(cadastro + lançamento de protocolo), produtivo (indução de lactação),
financeiro (lançamento) e Formulação de Dietas (biblioteca de alimentos +
simulação — Passo 2, ver PR claude/biblioteca-fracoes-cncps). Tabelas fora
deste recorte simplesmente não têm linha nenhuma neste banco isolado — a
checagem "zero NULL" continua válida pra elas por vacuidade, e cresce
sozinha conforme mais fluxos forem cobertos por outros testes que reusem
este mesmo `client` (ver fixture).

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
from fazenda.auth import EMAIL_DONO
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


# `alimento_nutricional` é a ÚNICA tabela do sistema em que `fazenda_id`
# NULO é dado BOM, de propósito — marca a linha da BIBLIOTECA MESTRE CowData
# (global, semeada em runtime por `semear_biblioteca_mestre`; ver docstring
# de `AlimentoNutricional` em fazenda/models/formulacao.py e
# fazenda.rules.biblioteca_alimentos). O fluxo abaixo abre a aba Biblioteca
# (GET /formulacao/alimentos), que semeia essas linhas mestre — contá-las
# como "vazamento da torneira" seria falso positivo.
#
# Toda escrita de verdade grava `usuario_id` (ver criar_alimento_nutricional/
# obter_para_editar em formulacao_dietas.py); a semeadura da mestre nunca
# grava. Por isso "NULO com usuario_id preenchido" continua sendo o sinal
# correto de vazamento também nesta tabela — só "NULO com usuario_id nulo"
# (a mestre) é tolerado.
_ALIMENTO_NUTRICIONAL_TOLERA_NULO_LEGITIMO = "alimento_nutricional"


def _linhas_nulas_de_escrita_real(engine, tabela: str) -> int:
    with engine.connect() as conn:
        return conn.exec_driver_sql(
            f'SELECT COUNT(*) FROM "{tabela}" WHERE fazenda_id IS NULL AND usuario_id IS NOT NULL'
        ).scalar() or 0


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

        # ── Formulação de Dietas (Passo 2 — #488 tinha deixado este módulo
        # de fora). A permissão de acesso ao módulo é mais estrita que o
        # resto do site (exigir_admin_ou_consultor_fazenda, backlog #127:
        # só dono-equivalente ou Consultor CowData vinculado) — sem isso o
        # "funcionario_campo" comum tomaria 403 antes mesmo de chegar no
        # resolvedor de fazenda_id que este teste quer exercitar. O e-mail
        # dono-equivalente só destrava essa checagem DE PERMISSÃO; a
        # RESOLUÇÃO de fazenda_id em si continua vindo do MESMO vínculo
        # UsuarioFazenda(fazenda_id=1) configurado no setup acima — é
        # exatamente esse caminho (token sem "fid" + vínculo único) que a
        # correção do PR claude/fazenda-id-raiz garante.
        with Session(engine) as s:
            # `usuario_id` do fixture não sobrevive fora do `with` em que foi
            # atribuído — busca pelo username fixo do fixture em vez disso.
            usuario = s.exec(select(Usuario).where(Usuario.username == "funcionario_campo")).one()
            usuario.email = EMAIL_DONO
            s.add(usuario)
            s.commit()

        # Abre a aba Biblioteca — semeia a biblioteca mestre CowData
        # (fazenda_id NULO de propósito, ver
        # _ALIMENTO_NUTRICIONAL_TOLERA_NULO_LEGITIMO abaixo).
        r = c.get("/formulacao/alimentos")
        assert r.status_code == 200, r.text

        r = c.post("/formulacao/alimentos", json={
            "alimento_id": None, "nome": "Farelo sentinela", "categoria_nasem": "Concentrado proteico",
            "conc_pct": 100.0, "fonte": None, "observacao": None, "valores": {},
        })
        assert r.status_code == 201, r.text
        alimento_nutricional_id = r.json()["id"]

        r = c.post("/formulacao/simulacoes", json={"nome": "Sentinela"})
        assert r.status_code == 201, r.text
        simulacao_id = r.json()["id"]
        r = c.put(f"/formulacao/simulacoes/{simulacao_id}", json={
            "animal": {
                "estado_fisiologico": "vaca_lactante", "raca": "Holandes", "peso_vivo_kg": 650.0,
                "peso_maturo_kg": 680.0, "ecc": 3.0, "paridade": 2.0, "del_dias": 150, "eq_cms": 8,
                "producao_leite_kg_dia": 35.0, "gordura_leite_pct": 3.8, "proteina_leite_pct": 3.2,
            },
            "itens": [
                {"nome": "Silagem de milho", "categoria_nasem": "Forragem", "conc_pct": 0.0, "proporcao_ms_pct": 60.0, "origem": "manual"},
                {"nome": "Farelo de soja", "categoria_nasem": "Concentrado proteico", "conc_pct": 100.0, "proporcao_ms_pct": 40.0, "origem": "manual"},
            ],
            "etapa_atual": 1,
        })
        assert r.status_code == 200, r.text

        # Checagem pontual (não só a varredura geral abaixo): o item da
        # biblioteca, a simulação e os itens da grade têm que ter ido para a
        # MESMA fazenda do vínculo, não fazenda_id nulo nem outra fazenda.
        with Session(engine) as s:
            from fazenda.models import AlimentoNutricional, DietaSimulacao, DietaSimulacaoItem
            assert s.get(AlimentoNutricional, alimento_nutricional_id).fazenda_id == 1
            sim = s.get(DietaSimulacao, simulacao_id)
            assert sim.fazenda_id == 1
            itens_sim = s.exec(select(DietaSimulacaoItem).where(DietaSimulacaoItem.simulacao_id == simulacao_id)).all()
            assert itens_sim and all(i.fazenda_id == 1 for i in itens_sim)

        # ── Varredura: NENHUMA tabela com fazenda_id pode ter linha nula —
        # exceto a mestre CowData de `alimento_nutricional`, que é nulo de
        # propósito (ver _ALIMENTO_NUTRICIONAL_TOLERA_NULO_LEGITIMO).
        tabelas_com_linha_nula: dict[str, int] = {}
        for tabela in _tabelas_com_fazenda_id():
            n = (
                _linhas_nulas_de_escrita_real(engine, tabela)
                if tabela == _ALIMENTO_NUTRICIONAL_TOLERA_NULO_LEGITIMO
                else _linhas_nulas(engine, tabela)
            )
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
            # E-mail dono-equivalente só para destravar a permissão PRÓPRIA
            # de Formulação de Dietas (exigir_admin_ou_consultor_fazenda) —
            # sem vínculo nenhum de UsuarioFazenda, exatamente o cenário que
            # este teste quer provar que continua recusado.
            usuario = Usuario(username="sem_fazenda", senha_hash="x", papel="admin", ativo=True, email=EMAIL_DONO)
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

            # Formulação de Dietas (Passo 2): mesma recusa, mesmo caminho
            # (get_fazenda_id_escrita -> resolver_fazenda_id_escrita).
            r = c.post("/formulacao/simulacoes", json={"nome": "Sem fazenda"})
            assert r.status_code == 409, r.text
            r = c.post("/formulacao/alimentos", json={
                "alimento_id": None, "nome": "Sem fazenda", "categoria_nasem": "Outros",
                "conc_pct": 0.0, "fonte": None, "observacao": None, "valores": {},
            })
            assert r.status_code == 409, r.text
        finally:
            main.app.dependency_overrides[get_current_user] = override_original
