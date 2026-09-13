"""
Isolamento por fazenda na Central de Protocolos, incluindo o caso de um
lançamento LEGADO (fazenda_id IS NULL — dado residual que nem a migração
029227481e9e conseguiu resolver: 2+ fazendas reais e sem pai pra derivar).

Até o PR claude/fazenda-id-raiz, um lançamento assim tinha um comportamento
ASSIMÉTRICO: a listagem (`_filtro_fazenda`) tolerava NULL e mostrava a linha,
mas `_lancamento_ou_404` (usado pelo detalhe e por TODAS as ações — baixa,
desfazer aplicação, encerrar, reabrir, renomear, cancelar) exigia igualdade
estrita e dava 404 — a linha aparecia na lista e sumia ao clicar. O PR
reverteu a tolerância (decisão do dono do produto: registro sem fazenda_id
não pode existir; a escrita agora recusa gravar NULL — fazenda.auth::
get_fazenda_id_escrita — e o backfill da migração resolve o histórico), então
agora o comportamento é UNIFORME: um lançamento com fazenda_id NULL fica
invisível em TODO lugar — não aparece na lista, dá 404 no detalhe e em toda
ação. Este arquivo prova essa uniformidade (sem asimetria) e, à parte, que o
isolamento entre fazendas de verdade (não-NULL, mas de OUTRA fazenda) nunca
mudou.

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
    ProtocoloSanitario, ProtocoloSanitarioAplicacao, ProtocoloSanitarioEtapa,
    ProtocoloSanitarioLancamento, ProtocoloSanitarioLote,
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
# Simula lançamentos com fazenda_id NULL (residual — ver docstring do módulo)
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
        molde = ProtocoloSanitario(nome=f"Sanitário Legado {fazenda_id}", dia_inicial=0, fazenda_id=fazenda_id)
        s.add(molde)
        s.commit()
        s.refresh(molde)
        etapa = ProtocoloSanitarioEtapa(
            protocolo_id=molde.id, dia=0, produto="Borgal", dosagem=40.0, unidade="ml", fazenda_id=fazenda_id,
        )
        s.add(etapa)
        s.commit()
        s.refresh(etapa)
        lote = ProtocoloSanitarioLote(
            protocolo_id=molde.id, nome_protocolo="Sanitário Legado", data_inicio=date.today(),
            ativo=True, fazenda_id=fazenda_id,
        )
        s.add(lote)
        s.commit()
        s.refresh(lote)
        l = ProtocoloSanitarioLancamento(
            protocolo_id=molde.id, numero_matriz="700", data_inicio=date.today(),
            lote_id=lote.id, fazenda_id=fazenda_id,
        )
        s.add(l)
        s.commit()
        s.refresh(l)
        s.add(ProtocoloSanitarioAplicacao(
            lancamento_id=l.id, etapa_id=etapa.id, dia=0, numero_matriz="700",
            data_prevista=DATA_FUTURA, realizada=False, fazenda_id=fazenda_id,
        ))
        s.commit()
        return lote.id


# Origens com detalhe/ações pela Central — as 5 famílias.
CRIADORES_COM_ACAO = {
    "iatf": _criar_iatf,
    "inducao": _criar_inducao,
    "customizado": _criar_customizado,
    "lida": _criar_lida,
    "sanitario": _criar_sanitario,
}

# Mesmo conjunto hoje (ver histórico do PR que unificou o Sanitário) —
# mantido como alias porque outros testes deste arquivo referenciam
# CRIADORES_TODOS para os casos de listagem.
CRIADORES_TODOS = CRIADORES_COM_ACAO


# ────────────────── Listagem — filtro estrito, NULL incluído ────────────────

class TestListagemAcompanhamentoNaoMostraNulo:
    @pytest.mark.parametrize("origem", sorted(CRIADORES_TODOS))
    def test_lancamento_com_fazenda_id_nulo_nao_aparece(self, client, origem):
        c, engine = client
        criar = CRIADORES_TODOS[origem]
        lancamento_id = criar(engine, None)  # fazenda_id NULL

        linhas = c.get("/central-protocolos/acompanhamento").json()
        assert not any(l["origem"] == origem and l["origem_id"] == lancamento_id for l in linhas), (
            f"lançamento com fazenda_id nulo ({origem}) não deveria mais aparecer no Acompanhamento "
            f"(filtro voltou a ser estrito — ver PR claude/fazenda-id-raiz)"
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


# ─────────────────── Detalhe — 404 uniforme, sem assimetria ─────────────────

class TestDetalheNuncaAssimetricoComALista:
    """Antes do PR, um lançamento com fazenda_id nulo APARECIA na lista mas
    dava 404 no detalhe — a assimetria era o próprio bug do relato original
    (linha visível, clique quebrado). Agora não aparece em nenhum dos dois:
    a garantia deixou de ser "tolera na leitura" e passou a ser "não existe
    NULO pra tolerar" (Passo 1 + Passo 2 do PR)."""

    @pytest.mark.parametrize("origem", sorted(CRIADORES_COM_ACAO))
    def test_detalhe_de_lancamento_com_fazenda_id_nulo_continua_404(self, client, origem):
        c, engine = client
        criar = CRIADORES_COM_ACAO[origem]
        lancamento_id = criar(engine, None)

        r = c.get(f"/central-protocolos/{origem}/{lancamento_id}")
        assert r.status_code == 404, r.text

    @pytest.mark.parametrize("origem", sorted(CRIADORES_COM_ACAO))
    def test_detalhe_de_outra_fazenda_continua_404(self, client, origem):
        # Isolamento nunca mudou: fazenda_id de OUTRA fazenda é 404 para
        # quem está na fazenda #1, com ou sem tolerância a NULL.
        c, engine = client
        criar = CRIADORES_COM_ACAO[origem]
        lancamento_id = criar(engine, 2)

        r = c.get(f"/central-protocolos/{origem}/{lancamento_id}")
        assert r.status_code == 404, r.text


# ───────────────── Ações recusam lançamento com fazenda_id nulo ─────────────

class TestAcoesRecusamLancamentoComFazendaIdNulo:
    """Cada ação (baixa, desfazer aplicação, encerrar, reabrir, renomear,
    cancelar) passa por `_lancamento_ou_404`, que agora rejeita fazenda_id
    nulo do mesmo jeito que rejeita fazenda de outro cliente — nenhuma ação
    consegue mais operar um lançamento sem fazenda."""

    @pytest.mark.parametrize("origem", sorted(CRIADORES_COM_ACAO))
    def test_toda_acao_da_404_em_lancamento_com_fazenda_id_nulo(self, client, origem):
        c, engine = client
        criar = CRIADORES_COM_ACAO[origem]
        lancamento_id = criar(engine, None)
        base = f"/central-protocolos/{origem}/{lancamento_id}"

        assert c.post(f"{base}/baixa", json={"dia": 0}).status_code == 404
        assert c.request("DELETE", f"{base}/baixa", json={"dia": 0, "numero_matriz": "700"}).status_code == 404
        assert c.post(f"{base}/encerrar", json={"motivo": "Teste"}).status_code == 404
        assert c.request("DELETE", f"{base}/encerrar").status_code == 404
        assert c.patch(f"{base}/renomear", json={"nome": "Nome renomeado"}).status_code == 404
        assert c.post(f"{base}/cancelar", json={"motivo": "Cancelado no teste"}).status_code == 404

    @pytest.mark.parametrize("origem", sorted(CRIADORES_COM_ACAO))
    def test_ciclo_completo_de_acoes_funciona_com_fazenda_id_preenchido(self, client, origem):
        """Sanity check: o caminho feliz (fazenda_id carimbado, igual ao da
        sessão) continua funcionando ponta a ponta — não é só o caminho nulo
        que virou 404, o normal continua 200."""
        c, engine = client
        criar = CRIADORES_COM_ACAO[origem]
        lancamento_id = criar(engine, 1)
        base = f"/central-protocolos/{origem}/{lancamento_id}"

        r = c.post(f"{base}/baixa", json={"dia": 0})
        assert r.status_code == 200, f"baixa ({origem}): {r.text}"

        r = c.request("DELETE", f"{base}/baixa", json={"dia": 0, "numero_matriz": "700"})
        assert r.status_code == 200, f"desfazer aplicação ({origem}): {r.text}"

        r = c.post(f"{base}/encerrar", json={"motivo": "Teste"})
        assert r.status_code == 200, f"encerrar ({origem}): {r.text}"

        r = c.request("DELETE", f"{base}/encerrar")
        assert r.status_code == 200, f"reabrir ({origem}): {r.text}"

        r = c.patch(f"{base}/renomear", json={"nome": "Nome renomeado"})
        assert r.status_code == 200, f"renomear ({origem}): {r.text}"
        assert r.json()["nome"] == "Nome renomeado"

        r = c.post(f"{base}/cancelar", json={"motivo": "Cancelado no teste"})
        assert r.status_code == 200, f"cancelar ({origem}): {r.text}"


# ──────────── Cancelar não mexe em MovimentoEstoque de fazenda_id nulo ──────

class TestCancelarNaoAlcancaLancamentoComFazendaIdNulo:
    """Como `cancelar()` também passa por `_lancamento_ou_404`, um
    lançamento com fazenda_id nulo dá 404 ANTES de chegar no estorno do
    MovimentoEstoque — o saldo simplesmente não é tocado (nem deveria: sem
    saber de qual fazenda é o lançamento, não tem como saber se é seguro
    mexer no estoque dela)."""

    def _preparar_estoque_e_movimento(self, engine, origem, lancamento_id):
        with Session(engine) as s:
            item = Estoque(nome="Produto Legado", quantidade=40, unidade="ml", fazenda_id=None)
            s.add(item)
            s.commit()
            s.refresh(item)
            # Simula uma baixa de 10ml já ocorrida (saldo 50 -> 40), com o
            # MovimentoEstoque gravado sem fazenda_id.
            s.add(MovimentoEstoque(
                fazenda_id=None, nome_item=item.nome, movimento="Aplicação", quantidade=10,
                unidade="ml", data_movimento=date.today(), estoque_id=item.id,
                origem_tipo=origem, origem_id=lancamento_id,
            ))
            s.commit()
            return item.id

    @pytest.mark.parametrize("origem", sorted(CRIADORES_COM_ACAO))
    def test_cancelar_da_404_e_nao_mexe_no_estoque(self, client, origem):
        c, engine = client
        criar = CRIADORES_COM_ACAO[origem]
        lancamento_id = criar(engine, None)
        item_id = self._preparar_estoque_e_movimento(engine, origem, lancamento_id)

        r = c.post(f"/central-protocolos/{origem}/{lancamento_id}/cancelar", json={})
        assert r.status_code == 404, r.text

        with Session(engine) as s:
            item = s.get(Estoque, item_id)
            assert item.quantidade == 40, "cancelar não deveria ter mexido no estoque de um lançamento 404"
