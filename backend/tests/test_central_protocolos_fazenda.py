"""
Regressão: um lançamento LEGADO (fazenda_id IS NULL, criado antes de a rota
de lançar carimbar fazenda_id) aparecia em Central de Protocolos >
Acompanhamento — a listagem (_linhas_*) já tolerava NULL — mas dava 404
("Lançamento de protocolo não encontrado") ao clicar na linha, porque
_lancamento_ou_404 (usado pelo detalhe e por TODAS as ações: baixa, desfazer
aplicação, encerrar, reabrir, renomear, cancelar) exigia igualdade estrita de
fazenda_id. Cobre as 5 origens (iatf, inducao, customizado, lida, sanitario —
sanitário só na listagem, ele não tem detalhe/ações pela Central) e o mesmo
buraco no estorno de MovimentoEstoque legado dentro de cancelar().

Segue o padrão de fixture de tests/test_central_protocolos.py e
tests/test_lida.py: StaticPool (OBRIGATÓRIO — SQLite em memória precisa da
mesma conexão entre requisições) e `main.app.dependency_overrides` para
sessão/usuário/fazenda_id, com ContratoFazenda ativo (exigido pelo middleware
de contrato comercial quando get_fazenda_atual_id devolve um int real).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    ContratoFazenda, Estoque, MovimentoEstoque,
    LidaAplicacao, LidaLancamento,
    ProtocoloCustomizado, ProtocoloCustomizadoAplicacao, ProtocoloCustomizadoLancamento,
    ProtocoloIatfAplicacao, ProtocoloIatfLancamento,
    ProtocoloInducaoAplicacao, ProtocoloInducaoLancamento,
    ProtocoloSanitario, ProtocoloSanitarioAplicacao, ProtocoloSanitarioLancamento,
)

# Data prevista no futuro — se a única etapa já tivesse vencido, o lançamento
# ainda apareceria em /acompanhamento (status "ativo" independe de atraso),
# mas manter no futuro evita qualquer acoplamento acidental com "hoje".
DATA_FUTURA = date.today() + timedelta(days=5)


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    with Session(engine) as s:
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        s.commit()

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


# ─────────────────────────── Criação direta na sessão ───────────────────────
# Simula lançamentos gravados antes do carimbo de fazenda_id (fazenda_id=None)
# ou pertencentes a outra fazenda (fazenda_id=2), sem passar pelas rotas de
# lançamento — o que importa aqui é só o comportamento da Central.

def _criar_iatf(engine, fazenda_id):
    with Session(engine) as s:
        l = ProtocoloIatfLancamento(
            nome_protocolo="IATF Legado", data_d0=date.today(), ativo=True, fazenda_id=fazenda_id,
        )
        s.add(l)
        s.commit()
        s.refresh(l)
        s.add(ProtocoloIatfAplicacao(
            lancamento_id=l.id, numero_matriz="700", dia=0, descricao="D0",
            data_prevista=DATA_FUTURA, realizada=False, fazenda_id=fazenda_id,
        ))
        s.commit()
        return l.id


def _criar_inducao(engine, fazenda_id):
    with Session(engine) as s:
        l = ProtocoloInducaoLancamento(
            protocolo_id=1, nome_protocolo="Indução Legado", data_d0=date.today(),
            ativo=True, fazenda_id=fazenda_id,
        )
        s.add(l)
        s.commit()
        s.refresh(l)
        s.add(ProtocoloInducaoAplicacao(
            lancamento_id=l.id, numero_matriz="700", dia=0, descricao="D0",
            data_prevista=DATA_FUTURA, realizada=False, fazenda_id=fazenda_id,
        ))
        s.commit()
        return l.id


def _criar_customizado(engine, fazenda_id):
    with Session(engine) as s:
        molde = ProtocoloCustomizado(
            nome=f"Molde Customizado Legado {fazenda_id}", categoria="Rebanho",
            tipo="sanitario", fazenda_id=fazenda_id,
        )
        s.add(molde)
        s.commit()
        s.refresh(molde)
        l = ProtocoloCustomizadoLancamento(
            protocolo_id=molde.id, nome_protocolo="Customizado Legado", categoria="Rebanho",
            dia_inicial=0, data_inicio=date.today(), ativo=True, fazenda_id=fazenda_id,
        )
        s.add(l)
        s.commit()
        s.refresh(l)
        s.add(ProtocoloCustomizadoAplicacao(
            lancamento_id=l.id, numero_matriz="700", dia=0, descricao="Aplicar produto",
            data_prevista=DATA_FUTURA, realizada=False, fazenda_id=fazenda_id,
        ))
        s.commit()
        return l.id


def _criar_lida(engine, fazenda_id):
    with Session(engine) as s:
        l = LidaLancamento(
            lida_id=1, nome_protocolo="Lida Legado", modo="periodo", dia_inicial=0,
            data_inicio=date.today(), ativo=True, fazenda_id=fazenda_id,
        )
        s.add(l)
        s.commit()
        s.refresh(l)
        s.add(LidaAplicacao(
            lancamento_id=l.id, numero_matriz="700", dia=0, descricao="Fazer",
            data_prevista=DATA_FUTURA, realizada=False, fazenda_id=fazenda_id,
        ))
        s.commit()
        return l.id


def _criar_sanitario(engine, fazenda_id):
    with Session(engine) as s:
        molde = ProtocoloSanitario(nome=f"Sanitário Legado {fazenda_id}", fazenda_id=fazenda_id)
        s.add(molde)
        s.commit()
        s.refresh(molde)
        l = ProtocoloSanitarioLancamento(
            protocolo_id=molde.id, numero_matriz="700", data_inicio=date.today(), fazenda_id=fazenda_id,
        )
        s.add(l)
        s.commit()
        s.refresh(l)
        s.add(ProtocoloSanitarioAplicacao(
            lancamento_id=l.id, etapa_id=1, data_prevista=DATA_FUTURA, realizada=False, fazenda_id=fazenda_id,
        ))
        s.commit()
        return l.id


# Origens com detalhe/ações pela Central (sanitário fica fora — ver
# _ORIGENS_COM_ACAO em central_protocolos.py, é lançado por animal e se
# resolve pela Agenda).
CRIADORES_COM_ACAO = {
    "iatf": _criar_iatf,
    "inducao": _criar_inducao,
    "customizado": _criar_customizado,
    "lida": _criar_lida,
}

# Todas as 5 origens agregadas pela Central — usado só nos testes de listagem.
CRIADORES_TODOS = {**CRIADORES_COM_ACAO, "sanitario": _criar_sanitario}


# ───────────────────────────── Listagem tolera NULL ─────────────────────────

class TestListagemAcompanhamentoToleraLegado:
    @pytest.mark.parametrize("origem", sorted(CRIADORES_TODOS))
    def test_lancamento_legado_aparece_no_acompanhamento(self, client, origem):
        c, engine = client
        criar = CRIADORES_TODOS[origem]
        lancamento_id = criar(engine, None)  # fazenda_id NULL — legado

        linhas = c.get("/central-protocolos/acompanhamento").json()
        assert any(l["origem"] == origem and l["origem_id"] == lancamento_id for l in linhas), (
            f"lançamento legado de {origem} deveria aparecer no Acompanhamento"
        )

    @pytest.mark.parametrize("origem", sorted(CRIADORES_TODOS))
    def test_lancamento_de_outra_fazenda_nao_aparece(self, client, origem):
        c, engine = client
        criar = CRIADORES_TODOS[origem]
        lancamento_id = criar(engine, 2)  # fazenda #2 — não é a fazenda do caller (#1)

        linhas = c.get("/central-protocolos/acompanhamento").json()
        assert not any(l["origem"] == origem and l["origem_id"] == lancamento_id for l in linhas), (
            f"lançamento de OUTRA fazenda ({origem}) não deveria aparecer para a fazenda #1 — isolamento quebrado"
        )


# ─────────────────────────── Detalhe abre para legado ───────────────────────
# Este é o teste que reproduz o print do usuário: a linha aparecia na lista
# mas o clique caía em 404.

class TestDetalheAbreParaLegado:
    @pytest.mark.parametrize("origem", sorted(CRIADORES_COM_ACAO))
    def test_detalhe_de_lancamento_legado_nao_da_404(self, client, origem):
        c, engine = client
        criar = CRIADORES_COM_ACAO[origem]
        lancamento_id = criar(engine, None)

        r = c.get(f"/central-protocolos/{origem}/{lancamento_id}")
        assert r.status_code == 200, r.text
        assert r.json()["origem_id"] == lancamento_id

    @pytest.mark.parametrize("origem", sorted(CRIADORES_COM_ACAO))
    def test_detalhe_de_outra_fazenda_continua_404(self, client, origem):
        # Isolamento não pode afrouxar: só NULL é tolerado, um fazenda_id de
        # OUTRA fazenda tem que continuar 404 para quem está na fazenda #1.
        c, engine = client
        criar = CRIADORES_COM_ACAO[origem]
        lancamento_id = criar(engine, 2)

        r = c.get(f"/central-protocolos/{origem}/{lancamento_id}")
        assert r.status_code == 404, r.text


# ─────────────────────── Todas as ações funcionam em legado ─────────────────

class TestAcoesFuncionamEmLegado:
    """Todo o ciclo de ações (baixa, desfazer aplicação, encerrar, reabrir,
    renomear, cancelar) tinha o mesmo 404 do detalhe — cada uma passa por
    _lancamento_ou_404. Roda o ciclo inteiro num único lançamento legado."""

    @pytest.mark.parametrize("origem", sorted(CRIADORES_COM_ACAO))
    def test_ciclo_completo_de_acoes_em_lancamento_legado(self, client, origem):
        c, engine = client
        criar = CRIADORES_COM_ACAO[origem]
        lancamento_id = criar(engine, None)
        base = f"/central-protocolos/{origem}/{lancamento_id}"

        # baixa
        r = c.post(f"{base}/baixa", json={"dia": 0})
        assert r.status_code == 200, f"baixa ({origem}): {r.text}"

        # desfazer aplicação (a baixa acima marcou "700"/dia 0 como realizada)
        r = c.request("DELETE", f"{base}/baixa", json={"dia": 0, "numero_matriz": "700"})
        assert r.status_code == 200, f"desfazer aplicação ({origem}): {r.text}"

        # encerrar
        r = c.post(f"{base}/encerrar", json={"motivo": "Teste"})
        assert r.status_code == 200, f"encerrar ({origem}): {r.text}"

        # reabrir
        r = c.request("DELETE", f"{base}/encerrar")
        assert r.status_code == 200, f"reabrir ({origem}): {r.text}"

        # renomear
        r = c.patch(f"{base}/renomear", json={"nome": "Nome renomeado"})
        assert r.status_code == 200, f"renomear ({origem}): {r.text}"
        assert r.json()["nome"] == "Nome renomeado"

        # cancelar
        r = c.post(f"{base}/cancelar", json={"motivo": "Cancelado no teste"})
        assert r.status_code == 200, f"cancelar ({origem}): {r.text}"


# ─────────────── Cancelar estorna MovimentoEstoque legado também ────────────

class TestCancelarEstornaMovimentoEstoqueLegado:
    """query_mov do cancelar() filtrava fazenda_id estrito — um movimento de
    estoque legado (fazenda_id NULL), gerado por um protocolo legado, não
    seria estornado no cancelamento."""

    def _preparar_estoque_e_movimento(self, engine, origem, lancamento_id):
        with Session(engine) as s:
            item = Estoque(nome="Produto Legado", quantidade=40, unidade="ml", fazenda_id=None)
            s.add(item)
            s.commit()
            s.refresh(item)
            # Simula uma baixa de 10ml já ocorrida (saldo 50 -> 40), com o
            # MovimentoEstoque gravado sem fazenda_id — exatamente o rastro
            # que um protocolo legado deixaria.
            s.add(MovimentoEstoque(
                fazenda_id=None, nome_item=item.nome, movimento="Aplicação", quantidade=10,
                unidade="ml", data_movimento=date.today(), estoque_id=item.id,
                origem_tipo=origem, origem_id=lancamento_id,
            ))
            s.commit()
            return item.id

    @pytest.mark.parametrize("origem", sorted(CRIADORES_COM_ACAO))
    def test_cancelar_devolve_estoque_do_movimento_legado(self, client, origem):
        c, engine = client
        criar = CRIADORES_COM_ACAO[origem]
        lancamento_id = criar(engine, None)
        item_id = self._preparar_estoque_e_movimento(engine, origem, lancamento_id)

        r = c.post(f"/central-protocolos/{origem}/{lancamento_id}/cancelar", json={})
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            item = s.get(Estoque, item_id)
            assert item.quantidade == 50, (
                f"cancelar ({origem}) deveria ter devolvido as 10ml do MovimentoEstoque legado "
                f"(fazenda_id NULL) — saldo ficou em {item.quantidade}"
            )
