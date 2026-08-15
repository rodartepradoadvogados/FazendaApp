"""
Anexo de comprovante em lançamento SEM `numero_lancamento`.

Lançamento importado da planilha Ideagri (parsers/conta_gerencial.py) nasce
com `numero_lancamento = None`. Como todo o mecanismo de anexo era ancorado
nessa string, esses lançamentos históricos não aceitavam comprovante nenhum:
na tela de Pagamento a área de arrastar vinha desabilitada (nem arrastar nem
clicar funcionava) e na tela de Edição o bloco de Anexos nem aparecia.

Os endpoints `/lancamentos/por-id/{id}/anexos` resolvem o lançamento pelo id
e emitem a numeração que faltava na PRIMEIRA anexação.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
import fazenda.models  # noqa: F401 — registra as tabelas antes do create_all
from fazenda.models import ContaGerencial


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    import fazenda.api.routers.financeiro as financeiro_mod
    _bucket: dict[str, bytes] = {}
    monkeypatch.setattr(financeiro_mod, "enviar_arquivo", lambda caminho, conteudo, *a, **k: _bucket.__setitem__(caminho, conteudo))
    monkeypatch.setattr(financeiro_mod, "baixar_arquivo", lambda caminho, *a, **k: _bucket[caminho])
    monkeypatch.setattr(financeiro_mod, "excluir_arquivo", lambda caminho, *a, **k: _bucket.pop(caminho, None))

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _lancamento_importado(engine, **campos) -> int:
    """Reproduz o que a importação da planilha grava: sem numero_lancamento."""
    padrao = dict(
        codigo_conta="3.01.01.01",
        descricao="Compra de ração — importado da planilha",
        data_vencimento=date(2026, 7, 10),
        data_competencia=date(2026, 7, 1),
        fornecedor_cliente="Fornecedor Antigo",
        valor_total=1000.0,
        tipo="despesa",
    )
    padrao.update(campos)
    with Session(engine) as s:
        conta = ContaGerencial(**padrao)
        s.add(conta)
        s.commit()
        s.refresh(conta)
        assert conta.numero_lancamento is None, "o teste precisa partir de um lançamento sem numeração"
        return conta.id


def _pdf(nome="comprovante.pdf"):
    return {"file": (nome, b"%PDF-1.4 comprovante", "application/pdf")}


class TestAnexoEmLancamentoSemNumeracao:
    def test_anexa_e_emite_a_numeracao_que_faltava(self, client):
        c, engine = client
        lid = _lancamento_importado(engine)

        r = c.post(f"/financeiro/lancamentos/por-id/{lid}/anexos", files=_pdf())
        assert r.status_code == 201, r.text
        assert r.json()["nome_arquivo"] == "comprovante.pdf"

        with Session(engine) as s:
            conta = s.get(ContaGerencial, lid)
            assert conta.numero_lancamento, "a numeração deveria ter sido emitida na anexação"
            assert conta.numero_lancamento.startswith("LC-2026-"), conta.numero_lancamento

    def test_numeracao_usa_o_ano_da_competencia_do_lancamento(self, client):
        """Nota histórica de 2024 não pode virar LC do ano corrente."""
        c, engine = client
        lid = _lancamento_importado(engine, data_competencia=date(2024, 3, 5), data_vencimento=date(2024, 4, 5))
        c.post(f"/financeiro/lancamentos/por-id/{lid}/anexos", files=_pdf())
        with Session(engine) as s:
            assert s.get(ContaGerencial, lid).numero_lancamento.startswith("LC-2024-")

    def test_segunda_anexacao_reaproveita_a_mesma_numeracao(self, client):
        c, engine = client
        lid = _lancamento_importado(engine)
        c.post(f"/financeiro/lancamentos/por-id/{lid}/anexos", files=_pdf("nota.pdf"))
        with Session(engine) as s:
            numero = s.get(ContaGerencial, lid).numero_lancamento
        c.post(f"/financeiro/lancamentos/por-id/{lid}/anexos", files=_pdf("recibo.pdf"))
        with Session(engine) as s:
            assert s.get(ContaGerencial, lid).numero_lancamento == numero, "não pode trocar de numeração a cada anexo"

        anexos = c.get(f"/financeiro/lancamentos/por-id/{lid}/anexos").json()
        assert sorted(a["nome_arquivo"] for a in anexos) == ["nota.pdf", "recibo.pdf"]

    def test_listar_antes_de_anexar_nao_altera_o_lancamento(self, client):
        """Só abrir a tela de pagamento não pode escrever no banco."""
        c, engine = client
        lid = _lancamento_importado(engine)
        r = c.get(f"/financeiro/lancamentos/por-id/{lid}/anexos")
        assert r.status_code == 200 and r.json() == []
        with Session(engine) as s:
            assert s.get(ContaGerencial, lid).numero_lancamento is None

    def test_anexo_aparece_tambem_pela_rota_por_numero(self, client):
        """O anexo tem que ser o MESMO nas duas telas — a de pagamento (por id)
        e a de edição/consulta que já usava o número."""
        c, engine = client
        lid = _lancamento_importado(engine)
        c.post(f"/financeiro/lancamentos/por-id/{lid}/anexos", files=_pdf())
        with Session(engine) as s:
            numero = s.get(ContaGerencial, lid).numero_lancamento

        por_numero = c.get(f"/financeiro/lancamentos/{numero}/anexos").json()
        por_id = c.get(f"/financeiro/lancamentos/por-id/{lid}/anexos").json()
        assert len(por_numero) == 1
        assert [a["id"] for a in por_numero] == [a["id"] for a in por_id]

    def test_conteudo_anexado_pode_ser_baixado(self, client):
        c, engine = client
        lid = _lancamento_importado(engine)
        anexo_id = c.post(f"/financeiro/lancamentos/por-id/{lid}/anexos", files=_pdf()).json()["id"]
        r = c.get(f"/financeiro/anexos/{anexo_id}")
        assert r.status_code == 200
        assert r.content == b"%PDF-1.4 comprovante"

    def test_lancamento_inexistente_da_404(self, client):
        c, _ = client
        assert c.post("/financeiro/lancamentos/por-id/999999/anexos", files=_pdf()).status_code == 404
        assert c.get("/financeiro/lancamentos/por-id/999999/anexos").status_code == 404

    def test_numeracao_emitida_nao_colide_com_a_ja_existente(self, client):
        """Emitir sob demanda não pode roubar o número de outro lançamento."""
        c, engine = client
        criado = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa", "data_competencia": "2026-07-01", "data_vencimento": "2026-07-10",
            "itens": [{"produto": "Sal mineral", "codigo_conta_gerencial": "3.01.01.03", "valor_total": 200.0}],
        })
        assert criado.status_code in (200, 201), criado.text
        numero_existente = criado.json()["numero_lancamento"]

        lid = _lancamento_importado(engine)
        c.post(f"/financeiro/lancamentos/por-id/{lid}/anexos", files=_pdf())
        with Session(engine) as s:
            assert s.get(ContaGerencial, lid).numero_lancamento != numero_existente


class TestAnexoNoLancamentoQueJaTemNumero:
    def test_caminho_por_id_funciona_igual_para_lancamento_normal(self, client):
        """A tela de pagamento passou a usar sempre a rota por id — ela não
        pode se comportar diferente para lançamento criado pelo sistema."""
        c, _ = client
        criado = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa", "data_competencia": "2026-07-01", "data_vencimento": "2026-07-10",
            "itens": [{"produto": "Ração", "codigo_conta_gerencial": "3.01.01.01", "valor_total": 500.0}],
        }).json()
        lid = c.get("/financeiro/lancamentos").json()["lancamentos"][0]["id"]

        r = c.post(f"/financeiro/lancamentos/por-id/{lid}/anexos", files=_pdf())
        assert r.status_code == 201, r.text
        anexos = c.get(f"/financeiro/lancamentos/{criado['numero_lancamento']}/anexos").json()
        assert len(anexos) == 1
