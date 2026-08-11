"""
Regressão: etapa de protocolo de indução de lactação some da Agenda mesmo
continuando visível (e "dar baixa"-vel) na Central de Protocolos.

Causa raiz (ver fazenda/api/routers/agenda.py, bloco "Protocolo de indução de
lactação" dentro de `calcular_agenda`): o trio `ProtocoloInducaoLancamento` /
`ProtocoloInducaoAplicacao` / `ProtocoloInducaoMedicamento` era filtrado com
`_da_fazenda` — igualdade ESTRITA de `fazenda_id`. Qualquer uma dessas linhas
com `fazenda_id IS NULL` (lançamento legado, de antes da rota de criação
carimbar o campo, ou qualquer outro caminho que deixe a coluna vazia) nunca
casa com `== fazenda_id`, então:
  - a `ProtocoloInducaoAplicacao` do dia (ex.: D6) some da lista de
    aplicações pendentes, OU
  - mesmo que a aplicação apareça, `lancamentos_inducao_por_id.get(...)`
    devolve None (o Lancamento também sumiu do dicionário) e o `if not
    lancamento: continue` descarta o grupo inteiro.
Em ambos os casos a etapa desaparece da Agenda.

A Central de Protocolos NUNCA teve esse problema: `_filtro_fazenda` em
central_protocolos.py já tolera `fazenda_id IS NULL` desde a correção
coberta por tests/test_inducao_fazenda_id.py — daí a divergência relatada
("aparece o cronograma... mas não aparece na agenda").

É a MESMA FAMÍLIA da regressão, já documentada no código (ver comentário
"ProtocoloSanitarioEtapa nunca grava fazenda_id" logo acima deste bloco em
agenda.py), só que ali a coluna nem existe — aqui ela existe e normalmente
vem preenchida, mas precisa TOLERAR os casos em que não veio, exatamente como
a Central já faz.

O corretivo troca `_da_fazenda` por `_da_fazenda_tolerante` (mesma regra
`fazenda_id == atual OR fazenda_id IS NULL` de `_filtro_fazenda`) nas três
consultas do bloco de indução.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import ContratoFazenda, ProtocoloInducaoAplicacao, ProtocoloInducaoLancamento


class _FakeAdmin:
    id = 1
    papel = "admin"
    permissoes = None
    ativo = True
    username = "admin_teste"


@pytest.fixture
def client_multi():
    """Duas fazendas com ContratoFazenda ativo — mesmo padrão de
    test_agenda_diaria.py/test_central_protocolos_fazenda.py.
    `make_client(id)` troca a fazenda "atual" a cada chamada."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    with Session(engine) as s:
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        s.add(ContratoFazenda(fazenda_id=2, status="ativo"))
        s.commit()

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()

    def _make_client(fazenda_id: int) -> TestClient:
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id
        return TestClient(main.app)

    yield engine, _make_client

    main.app.dependency_overrides.clear()


def _lancamento_e_aplicacao_d6(engine, numero_matriz: str = "422", fazenda_id: int | None = None) -> int:
    """Cria um lançamento de indução de lactação com uma única etapa pendente,
    D6, prevista para hoje — replica exatamente o caso do relato (vaca 422,
    D6, "hoje"). `fazenda_id=None` simula o lançamento legado que dispara a
    regressão; passar um int reproduz o caminho já-correto (sanity check)."""
    with Session(engine) as s:
        lanc = ProtocoloInducaoLancamento(
            protocolo_id=1, nome_protocolo="INDUÇÃO DE LACTAÇÃO — TESTE",
            data_d0=date.today() - timedelta(days=6), fazenda_id=fazenda_id,
        )
        s.add(lanc)
        s.commit()
        s.refresh(lanc)
        s.add(ProtocoloInducaoAplicacao(
            lancamento_id=lanc.id, numero_matriz=numero_matriz, dia=6,
            descricao="Indução de lactação — D6", observacao_manejo="Iniciar ordenha",
            data_prevista=date.today(), realizada=False, fazenda_id=fazenda_id,
        ))
        s.commit()
        return lanc.id


def _eventos_inducao(resposta_json: dict) -> list[dict]:
    return [e for e in resposta_json["eventos"] if e.get("tipo") == "protocolo_inducao"]


class TestEtapaInducaoLegadaApareceNaAgenda:
    def test_lancamento_legado_fazenda_id_nulo_aparece_na_agenda_hoje(self, client_multi):
        """O caso do relato: lançamento/aplicação com fazenda_id NULL (legado)
        precisa continuar aparecendo na Agenda da fazenda que está olhando —
        antes desta correção, o filtro estrito zerava o grupo inteiro."""
        engine, make_client = client_multi
        _lancamento_e_aplicacao_d6(engine, numero_matriz="422", fazenda_id=None)
        c = make_client(1)
        r = c.get("/agenda/")
        assert r.status_code == 200
        eventos = _eventos_inducao(r.json())
        assert len(eventos) == 1, f"D6 da vaca 422 não apareceu na Agenda: {r.json().get('eventos')}"
        assert eventos[0]["dia"] == 6
        assert "422" in eventos[0]["animais"]
        assert eventos[0]["data"] == date.today().isoformat()

    def test_lancamento_com_fazenda_id_da_propria_fazenda_continua_aparecendo(self, client_multi):
        """Sanity check: o caminho feliz (fazenda_id carimbado corretamente)
        não pode ter sido quebrado pela troca de `_da_fazenda` por
        `_da_fazenda_tolerante`."""
        engine, make_client = client_multi
        _lancamento_e_aplicacao_d6(engine, numero_matriz="422", fazenda_id=1)
        c = make_client(1)
        eventos = _eventos_inducao(c.get("/agenda/").json())
        assert len(eventos) == 1
        assert "422" in eventos[0]["animais"]

    def test_lancamento_de_outra_fazenda_continua_isolado(self, client_multi):
        """O isolamento entre fazendas não pode ter afrouxado: um fazenda_id
        de OUTRA fazenda (não NULL) continua de fora — só NULL é tolerado."""
        engine, make_client = client_multi
        _lancamento_e_aplicacao_d6(engine, numero_matriz="422", fazenda_id=2)
        c = make_client(1)
        eventos = _eventos_inducao(c.get("/agenda/").json())
        assert eventos == []
