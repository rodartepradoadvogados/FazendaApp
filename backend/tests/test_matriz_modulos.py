"""
Plano Financeiro, §0.3 — matriz de caracterização (golden) de status por rota
para contratos Standard, Silver, Gold e a fazenda #1 grandfathered.

Esta matriz foi gravada contra o código ATUAL, ANTES de qualquer mudança de
gating do Plano Financeiro, e é a rede de proteção das fases seguintes:
`/indicadores` ganhando `exigir_algum_modulo_contratado`, o ponto único de
estoque, o filtro de módulos da Agenda. Para Standard/Silver/Gold/#1 NADA aqui
pode mudar — se mudou, a regressão é do código novo, não deste arquivo.

Os cenários novos (fazenda só-Financeiro `[financeiro, pedidos]` e
`[rebanho, financeiro]`) descrevem o comportamento ALVO do plano.

Convenção: o valor é o status HTTP. "ok" = qualquer 2xx (a rota respondeu,
independente do conteúdo); 403 = barrado pela trava de contrato. Rotas que
podem devolver 404/422 por falta de dado de teste não entram na matriz — só
GETs de listagem/abertura que respondem 200 numa fazenda vazia.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda
from fazenda.models.planos import MODULOS_COMERCIAIS, PLANOS_CATALOGO

# fazenda_id -> (rótulo, plano|None, módulos)
FAZENDAS = {
    1: ("grandfathered", None, list(MODULOS_COMERCIAIS)),
    2: ("standard", "standard", list(PLANOS_CATALOGO["standard"]["modulos"])),
    3: ("gold", "gold", list(PLANOS_CATALOGO["gold"]["modulos"])),
    4: ("silver", "silver", list(PLANOS_CATALOGO["silver"]["modulos"])),
    5: ("so_financeiro", None, ["financeiro", "pedidos"]),
    6: ("rebanho_financeiro", None, ["rebanho", "financeiro"]),
    7: ("so_rebanho_reprodutivo_sem_plano", None, ["rebanho", "reprodutivo"]),
}

_PER = "?data_inicio=2026-09-01&data_fim=2026-09-30"

# Matriz GOLDEN: rota -> status para as fazendas, NESTA ordem:
#   (#1 grandfathered, standard, gold, silver, só-financeiro, rebanho+financeiro, rebanho+reprodutivo)
# Colunas 1-4, 6 e 7 foram gravadas contra o código de ANTES do Plano Financeiro (HEAD 534bdb9)
# e não podem mudar. A coluna 5 (só-financeiro) é idêntica ao código antigo, EXCETO
# /indicadores/ (403 pelo gate novo) — ver DIFERE_SO_FINANCEIRO.
GOLDEN: dict[str, tuple[int, ...]] = {
    '/animais/'                                   : (200, 200, 200, 200, 403, 200, 200),
    '/lotes/'                                     : (200, 200, 200, 200, 403, 200, 200),
    '/estoque/'                                   : (200, 403, 200, 403, 403, 403, 403),
    '/pedidos/'                                   : (200, 403, 200, 403, 200, 403, 403),
    '/pedidos/opcoes'                             : (200, 403, 200, 403, 200, 403, 403),
    '/cotacoes/'                                  : (200, 403, 200, 403, 200, 403, 403),
    '/financeiro/opcoes'                          : (200, 403, 200, 200, 200, 200, 403),
    '/financeiro/plano-contas'                    : (200, 403, 200, 200, 200, 200, 403),
    '/financeiro/contas-correntes'                : (200, 403, 200, 200, 200, 200, 403),
    '/financeiro/lancamentos'                     : (200, 403, 200, 200, 200, 200, 403),
    '/financeiro/dre' + _PER                      : (200, 403, 200, 200, 200, 200, 403),
    '/financeiro/resultado-por-litro' + _PER      : (200, 403, 200, 200, 200, 200, 403),
    '/financeiro/custos-leite' + _PER             : (200, 403, 200, 200, 200, 200, 403),
    '/financeiro/fechamento/meses'                : (200, 403, 200, 200, 200, 200, 403),
    '/planejamento/orcamento'                     : (200, 403, 200, 403, 403, 403, 403),
    '/planejamento/cenarios'                      : (200, 403, 200, 403, 403, 403, 403),
    '/indicadores/'                               : (200, 200, 200, 200, 200, 200, 200),
    '/agenda/'                                    : (200, 200, 200, 200, 200, 200, 200),
    '/agenda/dia'                                 : (200, 200, 200, 200, 200, 200, 200),
    '/agenda/painel'                              : (200, 200, 200, 200, 200, 200, 200),
    '/reproducao/servicos'                        : (200, 200, 200, 200, 403, 403, 200),
    '/producao/'                                  : (200, 403, 200, 200, 403, 403, 403),
    '/sanidade/aplicacoes'                        : (200, 403, 200, 200, 403, 403, 403),
    '/alimentacao/'                               : (200, 403, 200, 403, 403, 403, 403),
    '/safras/'                                    : (200, 403, 200, 403, 403, 403, 403),
    '/relatorio-compra-venda-animais/'            : (200, 200, 200, 200, 403, 200, 200),
    '/relatorios/manejo'                          : (200, 200, 200, 200, 403, 403, 200),
    '/parametros/'                                : (200, 200, 200, 200, 200, 200, 200),
    '/onboarding'                                 : (200, 200, 200, 200, 200, 200, 200),
    '/notificacoes/'                              : (200, 200, 200, 200, 200, 200, 200),
}
ROTAS = list(GOLDEN)
COLUNA = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6}
# Única linha da coluna 5 que difere do código antigo (antes era 200).
DIFERE_SO_FINANCEIRO = {"/indicadores/": 403}
ANTES_DO_GATE_INDICADORES = {"/indicadores/": 200}


@pytest.fixture
def ambiente(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        for fid, (rotulo, plano, modulos) in FAZENDAS.items():
            s.add(Fazenda(id=fid, nome=f"Fazenda {rotulo}"))
        s.commit()
        for fid, (rotulo, plano, modulos) in FAZENDAS.items():
            s.add(ContratoFazenda(fazenda_id=fid, plano=plano, status="ativo"))
            for m in modulos:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=m, preco=0.0, ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "admin_comum"
        email = "admin_comum@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def _matriz(c, fazenda_id: int) -> dict[str, int]:
    _como_fazenda(fazenda_id)
    return {rota: c.get(rota).status_code for rota in ROTAS}


def _esperado(fazenda_id: int) -> dict[str, int]:
    col = COLUNA[fazenda_id]
    esp = {r: GOLDEN[r][col] for r in ROTAS}
    if fazenda_id == 5:
        esp.update(DIFERE_SO_FINANCEIRO)
    return esp


def _confere(c, fazenda_id: int) -> None:
    obtido = _matriz(c, fazenda_id)
    esperado = _esperado(fazenda_id)
    diferencas = {r: (esperado[r], obtido[r]) for r in ROTAS if esperado[r] != obtido[r]}
    assert not diferencas, f"fazenda {FAZENDAS[fazenda_id][0]}: (esperado, obtido) por rota: {diferencas}"


@pytest.mark.parametrize("fazenda_id", [1, 2, 3, 4])
def test_matriz_golden_planos_de_catalogo_e_fazenda_1(ambiente, fazenda_id):
    """Standard, Silver, Gold e fazenda #1: matriz INALTERADA pelo Plano Financeiro."""
    c, _ = ambiente
    _confere(c, fazenda_id)


def test_matriz_rebanho_mais_financeiro(ambiente):
    """[rebanho, financeiro]: Financeiro e Rebanho abertos; Pedidos/Estoque/Planejamento/Reprodução fechados."""
    c, _ = ambiente
    _confere(c, 6)


def test_matriz_rebanho_mais_reprodutivo(ambiente):
    """[rebanho, reprodutivo] (pacote Standard sob medida): igual ao Standard, linha a linha."""
    c, _ = ambiente
    _confere(c, 7)


def test_matriz_so_financeiro_e_pedidos(ambiente):
    """[financeiro, pedidos] (plano Financeiro): Financeiro+Pedidos+Cotações abertos; nada de rebanho,
    estoque, planejamento — e /indicadores/ fechado (gate exigir_algum_modulo_contratado)."""
    c, _ = ambiente
    _confere(c, 5)
    # Reforço explícito do gate novo, com a mensagem que o front mostra.
    _como_fazenda(5)
    r = c.get("/indicadores/")
    assert r.status_code == 403
    assert "não contratado" in r.json()["detail"]


def test_gate_indicadores_aceita_qualquer_modulo_de_rebanho(ambiente):
    """/indicadores/ abre com QUALQUER um de {rebanho, reprodutivo, produtivo}."""
    c, engine = ambiente
    with Session(engine) as s:
        for fid, modulos in ((8, ["reprodutivo"]), (9, ["produtivo"]), (10, ["financeiro", "pedidos", "estoque"])):
            s.add(Fazenda(id=fid, nome=f"F{fid}"))
            s.commit()
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for m in modulos:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=m, preco=0.0, ativo=True))
            s.commit()
    for fid, esperado in ((8, 200), (9, 200), (10, 403)):
        _como_fazenda(fid)
        assert c.get("/indicadores/").status_code == esperado, fid
