"""
Alerta de sobra de cocho fora da faixa aceitável — Sessão 3, Frente C
(specs/sessao-3-consumo-e-sobra.md). Cobre C1 a C8: geração na Agenda como
comunicado, geração na central de alertas como PortalMensagem, texto curto
com kg por alimento, exclusão dos itens sem conversão para kg, um alerta por
lote/dia (atualiza em vez de duplicar) e silêncio quando a sobra está dentro
da faixa.

⚠ NOTA IMPORTANTE PARA QUEM REVISAR ESTE ARQUIVO: no momento em que esta
frente foi escrita, `fazenda/rules/unidades.py` (Frente A, fora do escopo
desta frente) estava com um bug que quebra o import de toda a aplicação —
ver o comentário logo abaixo, antes dos imports de `fazenda`/`main`. Se este
arquivo falhar já na COLETA (ImportError em cadeia a partir de
`fazenda.api.routers.reproducao`), é esse bug, não este teste — confirme
rodando `python -c "import fazenda.rules.estoque_baixa"` fora do pytest.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

# ---------------------------------------------------------------------------
# Ver a nota no docstring do módulo: `rules/estoque_baixa.py` importa
# `pode_dar_baixa_direta` de `rules/unidades.py`, mas o commit da Frente A
# (d7b1936) sobrescreveu esse arquivo por inteiro e apagou a função (junto
# com `leite_para_kg`/`unidades_compativeis`, usadas por
# routers/sanidade.py e routers/producao.py) — sem isto, `import main`
# derruba a coleta inteira do arquivo com ImportError, mesmo sem relação
# nenhuma com sobra de cocho. `rules/` é proibido para esta frente (outro
# dono), então em vez de editar o arquivo no disco, este bloco só repõe os
# nomes que faltam no módulo já carregado, IN-MEMORY, antes de qualquer
# outro módulo de `fazenda.*` importar `rules/unidades`. Remover este bloco
# assim que o arquivo real for corrigido — ele vira um no-op nesse dia
# (o `if not hasattr` não sobrescreve nada que já exista).
import fazenda.rules.unidades as _unidades_bug_frente_a  # noqa: E402

if not hasattr(_unidades_bug_frente_a, "pode_dar_baixa_direta"):
    _unidades_bug_frente_a.pode_dar_baixa_direta = (
        lambda unidade_aplicacao, unidade_estoque: bool(unidade_estoque) and unidade_aplicacao == unidade_estoque
    )
if not hasattr(_unidades_bug_frente_a, "leite_para_kg"):
    _unidades_bug_frente_a.leite_para_kg = (
        lambda quantidade, unidade: quantidade * 1.029 if (unidade or "kg").strip().upper() == "L" else quantidade
    )
if not hasattr(_unidades_bug_frente_a, "unidades_compativeis"):
    _unidades_bug_frente_a.unidades_compativeis = lambda unidade_estoque=None: (
        [unidade_estoque] if unidade_estoque else ["ml", "L", "unidade", "dose", "kg", "saca 30kg", "saca 60kg"]
    )
if not hasattr(_unidades_bug_frente_a, "UNIDADES_ENTREGA_LEITE"):
    _unidades_bug_frente_a.UNIDADES_ENTREGA_LEITE = ("kg", "L")
# ---------------------------------------------------------------------------

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

import fazenda.database as database  # noqa: E402
from fazenda.models import (  # noqa: E402
    ConsumoAlimento, ConsumoSobra, ContratoFazenda, ContratoFazendaModulo, EventoRealizado, Fazenda, PortalMensagem,
    Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS  # noqa: E402


class _FakeAdmin:
    id = 1
    papel = "admin"
    permissoes = None
    ativo = True
    username = "admin_teste"


DATA_HOJE = date(2026, 8, 20)


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Teste"))
        s.add(Fazenda(id=2, nome="Outra Fazenda"))
        s.add(Usuario(id=1, username="admin_teste", senha_hash="x", papel="admin", ativo=True))
        s.add(UsuarioFazenda(usuario_id=1, fazenda_id=1))
        # Funcionário sem acesso a Alimentação — não deve entrar na lista de
        # destinatários do alerta na central (ver _destinatarios_alerta_sobra).
        s.add(Usuario(id=2, username="sem_acesso_teste", senha_hash="x", papel="operador", ativo=True, permissoes="rebanho"))
        s.add(UsuarioFazenda(usuario_id=2, fazenda_id=1))
        # Funcionário da alimentação — deve receber.
        s.add(Usuario(id=3, username="peao_alimentacao_teste", senha_hash="x", papel="operador", ativo=True, permissoes="alimentacao,agenda"))
        s.add(UsuarioFazenda(usuario_id=3, fazenda_id=1))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    yield TestClient(main.app), engine
    main.app.dependency_overrides.clear()


def _lancar(engine, fazenda_id: int, lote: int, itens: list[tuple[str, float, str]], kg_sobra: float, usuario_id: int | None = 3):
    """Grava ConsumoAlimento (fornecido) + ConsumoSobra do dia direto no
    banco — não passa pelo endpoint de lançamento (Frente B, fora do escopo
    desta frente) porque o alerta é COMPUTADO a partir destas duas tabelas,
    não do endpoint que as populou."""
    with Session(engine) as s:
        for alimento, quantidade, unidade in itens:
            s.add(ConsumoAlimento(
                fazenda_id=fazenda_id, data=DATA_HOJE, lote=lote, alimento=alimento,
                quantidade=quantidade, unidade=unidade, usuario_id=usuario_id,
            ))
        existente = s.exec(
            select(ConsumoSobra).where(ConsumoSobra.fazenda_id == fazenda_id, ConsumoSobra.lote == lote, ConsumoSobra.data == DATA_HOJE)
        ).first()
        if existente:
            existente.kg_sobra = kg_sobra  # B10 — relançar no mesmo dia SUBSTITUI
            s.add(existente)
        else:
            s.add(ConsumoSobra(fazenda_id=fazenda_id, data=DATA_HOJE, lote=lote, kg_sobra=kg_sobra, usuario_id=usuario_id))
        s.commit()


def _relancar_sobra(engine, fazenda_id: int, lote: int, kg_sobra: float, usuario_id: int | None = 3):
    """Corrige só a medição de sobra do dia (B10 — substitui), SEM lançar
    fornecido de novo — ao contrário de `_lancar`, que soma ConsumoAlimento a
    cada chamada (B1). Usado para testar C7 isolando "a sobra mudou" de "o
    fornecido também mudou"."""
    with Session(engine) as s:
        existente = s.exec(
            select(ConsumoSobra).where(ConsumoSobra.fazenda_id == fazenda_id, ConsumoSobra.lote == lote, ConsumoSobra.data == DATA_HOJE)
        ).first()
        assert existente is not None, "_relancar_sobra pressupõe uma sobra já lançada antes"
        existente.kg_sobra = kg_sobra
        existente.usuario_id = usuario_id
        s.add(existente)
        s.commit()


def _eventos_alerta(corpo: dict, lote: int | None = None) -> list[dict]:
    evs = [e for e in corpo["eventos"] if e.get("tipo") == "alerta_sobra"]
    if lote is not None:
        evs = [e for e in evs if e.get("lote") == lote]
    return evs


def _portal_msgs(engine, fazenda_id: int = 1) -> list[PortalMensagem]:
    with Session(engine) as s:
        return list(s.exec(select(PortalMensagem).where(PortalMensagem.tipo == "alerta_sobra", PortalMensagem.fazenda_id == fazenda_id)).all())


# ---------------------------------------------------------------------------
# C1/C4 — sobra abaixo do mínimo: alerta no mesmo dia, manda ACRESCENTAR.
# ---------------------------------------------------------------------------
def test_sobra_baixa_gera_alerta_para_acrescentar(client):
    c, engine = client
    # Fornecido: 100 kg de silagem + 20 kg de farelo = 120 kg. Sobra de 1 kg
    # -> 0,83% de sobra, abaixo do mínimo padrão (3%).
    _lancar(engine, 1, 3, [("silagem", 100.0, "kg"), ("farelo", 20.0, "kg")], kg_sobra=1.0)

    r = c.get("/agenda/", params={"data": DATA_HOJE.isoformat(), "dias": 0})
    assert r.status_code == 200
    corpo = r.json()
    evs = _eventos_alerta(corpo, lote=3)
    assert len(evs) == 1
    ev = evs[0]
    assert ev["comunicado"] is True  # C2 — é comunicado, não atividade
    assert ev["categoria"] == "alimentacao"
    assert ev["data"] == DATA_HOJE.isoformat()
    assert ev["id"].startswith("alerta_sobra_")
    assert "Acrescente" in ev["descricao"]
    assert "Lote 03" in ev["descricao"]
    assert "0,8%" in ev["descricao"] or "0,83%" in ev["descricao"]

    # C3 — também vira PortalMensagem, pede_retorno=False, para quem tem
    # acesso a Alimentação (usuário 3), mas NÃO para quem não tem (usuário 2).
    msgs = _portal_msgs(engine)
    destinatarios = {m.destinatario_usuario_id for m in msgs}
    assert 3 in destinatarios
    assert 2 not in destinatarios
    for m in msgs:
        assert m.pede_retorno is False
        assert m.corpo == ev["descricao"]


# ---------------------------------------------------------------------------
# C1/C4 — sobra acima do máximo: alerta manda REDUZIR.
# ---------------------------------------------------------------------------
def test_sobra_alta_gera_alerta_para_reduzir(client):
    c, engine = client
    # 100 kg fornecidos, sobra de 15 kg -> 15%, acima do máximo padrão (7%).
    _lancar(engine, 1, 5, [("silagem", 100.0, "kg")], kg_sobra=15.0)

    r = c.get("/agenda/", params={"data": DATA_HOJE.isoformat(), "dias": 0})
    evs = _eventos_alerta(r.json(), lote=5)
    assert len(evs) == 1
    assert "Reduza" in evs[0]["descricao"]
    assert "Lote 05" in evs[0]["descricao"]


# ---------------------------------------------------------------------------
# C8 — dentro da faixa (3% a 7%), silêncio total: nem Agenda, nem central.
# ---------------------------------------------------------------------------
def test_sobra_dentro_da_faixa_nao_gera_alerta(client):
    c, engine = client
    # 100 kg fornecidos, sobra de 5 kg -> exatamente 5% (o alvo), bem dentro
    # da faixa [3%, 7%].
    _lancar(engine, 1, 7, [("silagem", 100.0, "kg")], kg_sobra=5.0)

    r = c.get("/agenda/", params={"data": DATA_HOJE.isoformat(), "dias": 0})
    assert _eventos_alerta(r.json(), lote=7) == []
    assert _portal_msgs(engine) == []


# ---------------------------------------------------------------------------
# C6 — alimento que não converte para kg (dose/litro/unidade) fica de fora
# da instrução, mas o alerta ainda existe e ainda tem itens convertíveis.
# ---------------------------------------------------------------------------
def test_alimento_sem_conversao_fica_fora_da_instrucao(client):
    c, engine = client
    _lancar(engine, 1, 9, [
        ("silagem", 100.0, "kg"),
        ("premix", 5.0, "saca 30kg"),  # 150 kg — entra
        ("aditivo liquido", 3.0, "L"),  # não converte — não pode virar "kg"
        ("vacina oral", 2.0, "dose"),  # não converte
    ], kg_sobra=2.0)  # fornecido em kg: 100 + 150 = 250 -> sobra 0,8%, abaixo do mínimo

    r = c.get("/agenda/", params={"data": DATA_HOJE.isoformat(), "dias": 0})
    evs = _eventos_alerta(r.json(), lote=9)
    assert len(evs) == 1
    texto = evs[0]["descricao"]
    assert "aditivo liquido" not in texto
    assert "vacina oral" not in texto
    assert "silagem" in texto
    assert "premix" in texto


def test_todos_os_itens_sem_conversao_ainda_assim_alerta(client):
    """C6 levado ao limite: NENHUM item converte para kg. Sem denominador em
    kg não dá para nem calcular o percentual — o alerta não pode inventar um
    número, então este caso não gera evento algum (ao contrário de B13, que é
    do relatório da Frente B, não desta frente)."""
    c, engine = client
    _lancar(engine, 1, 11, [("vacina oral", 2.0, "dose")], kg_sobra=1.0)

    r = c.get("/agenda/", params={"data": DATA_HOJE.isoformat(), "dias": 0})
    assert _eventos_alerta(r.json(), lote=11) == []


# ---------------------------------------------------------------------------
# C7 — um alerta por lote/dia: relançar a sobra no mesmo dia ATUALIZA em vez
# de duplicar. E: repetir a MESMA consulta sem nada mudar não deve resetar o
# "lido" de quem já deu o check (senão o alerta nunca some de verdade).
# ---------------------------------------------------------------------------
def test_relancar_sobra_atualiza_alerta_sem_duplicar(client):
    c, engine = client
    _lancar(engine, 1, 4, [("silagem", 100.0, "kg")], kg_sobra=1.0)  # 1% -> abaixo do mínimo

    r1 = c.get("/agenda/", params={"data": DATA_HOJE.isoformat(), "dias": 0})
    ev1 = _eventos_alerta(r1.json(), lote=4)[0]
    msgs1 = _portal_msgs(engine)
    assert len(msgs1) >= 1
    ids_antes = {m.id for m in msgs1}

    # Marca uma delas como lida (o "Check") diretamente no banco, como faria
    # POST /portal/mensagens/{id}/marcar-lida.
    with Session(engine) as s:
        m = s.get(PortalMensagem, msgs1[0].id)
        m.lida = True
        m.resolvida = True
        s.add(m)
        s.commit()

    # Consulta de novo SEM mudar nada: não deve recriar, não deve duplicar, e
    # não deve "reabrir" quem já leu (mesmo conteúdo = nada muda).
    r2 = c.get("/agenda/", params={"data": DATA_HOJE.isoformat(), "dias": 0})
    ev2 = _eventos_alerta(r2.json(), lote=4)[0]
    assert ev2["descricao"] == ev1["descricao"]
    msgs2 = _portal_msgs(engine)
    assert {m.id for m in msgs2} == ids_antes  # nenhuma linha nova
    with Session(engine) as s:
        m = s.get(PortalMensagem, msgs1[0].id)
        assert m.lida is True  # não foi resetado por uma consulta que não mudou nada

    # Agora relança a sobra (B10 — substitui) com um valor bem diferente:
    # o texto tem de mudar, e quem já tinha lido volta a ver (conteúdo novo).
    _relancar_sobra(engine, 1, 4, kg_sobra=20.0)  # 20% -> acima do máximo
    r3 = c.get("/agenda/", params={"data": DATA_HOJE.isoformat(), "dias": 0})
    ev3 = _eventos_alerta(r3.json(), lote=4)[0]
    assert ev3["descricao"] != ev1["descricao"]
    assert "Reduza" in ev3["descricao"]
    msgs3 = _portal_msgs(engine)
    assert {m.id for m in msgs3} == ids_antes  # mesma linha, atualizada — não duplicou
    with Session(engine) as s:
        m = s.get(PortalMensagem, msgs1[0].id)
        assert m.lida is False  # conteúdo mudou -> volta a aparecer para quem já tinha lido
        assert m.corpo == ev3["descricao"]

    # E se a correção trouxer a sobra de volta para dentro da faixa, o alerta
    # (C8) precisa sumir da central também, não só da Agenda.
    _relancar_sobra(engine, 1, 4, kg_sobra=5.0)  # 5% -> dentro da faixa
    r4 = c.get("/agenda/", params={"data": DATA_HOJE.isoformat(), "dias": 0})
    assert _eventos_alerta(r4.json(), lote=4) == []
    assert _portal_msgs(engine) == []


# ---------------------------------------------------------------------------
# C2 — comunicado: imune a "marcar realizado" e a "excluir" (o mecanismo que
# a spec pede usar de propósito, via COMUNICADO_PREFIXOS).
# ---------------------------------------------------------------------------
def test_comunicado_imune_a_realizado_e_exclusao(client):
    c, engine = client
    _lancar(engine, 1, 6, [("silagem", 100.0, "kg")], kg_sobra=1.0)
    r = c.get("/agenda/", params={"data": DATA_HOJE.isoformat(), "dias": 0})
    evento_id = _eventos_alerta(r.json(), lote=6)[0]["id"]

    r_realizado = c.post("/agenda/realizados", json={"evento_id": evento_id})
    assert r_realizado.status_code == 400

    r_excluir = c.delete(f"/agenda/realizados/{evento_id}")
    assert r_excluir.status_code == 400

    # E nenhum EventoRealizado foi de fato gravado.
    with Session(engine) as s:
        assert s.exec(select(EventoRealizado).where(EventoRealizado.evento_id == evento_id)).first() is None


# ---------------------------------------------------------------------------
# C5 — texto extremamente curto: sem saudação, sem repetir "Lote" mais de
# uma vez, poucas palavras.
# ---------------------------------------------------------------------------
def test_texto_extremamente_curto(client):
    c, engine = client
    _lancar(engine, 1, 2, [("silagem", 100.0, "kg"), ("farelo", 20.0, "kg")], kg_sobra=1.0)
    r = c.get("/agenda/", params={"data": DATA_HOJE.isoformat(), "dias": 0})
    texto = _eventos_alerta(r.json(), lote=2)[0]["descricao"]

    assert texto.lower().count("lote") == 1
    for saudacao in ("olá", "prezado", "atenciosamente", "informamos", "gostaríamos"):
        assert saudacao not in texto.lower()
    assert "cocho" not in texto.lower()  # sem explicar o indicador
    assert len(texto.split()) <= 14  # "poucas palavras" — teto generoso, não um contador rígido
    assert "lançar" not in texto.lower() and "lançamento" not in texto.lower()  # sem convite a lançar


# ---------------------------------------------------------------------------
# Isolamento por fazenda — sobra de uma fazenda não vaza alerta para outra.
# ---------------------------------------------------------------------------
def test_isolamento_por_fazenda(client):
    c, engine = client
    _lancar(engine, 2, 3, [("silagem", 100.0, "kg")], kg_sobra=1.0)  # fazenda 2, mesmo lote "3"

    r = c.get("/agenda/", params={"data": DATA_HOJE.isoformat(), "dias": 0})
    assert _eventos_alerta(r.json(), lote=3) == []  # cliente está na fazenda 1
    assert _portal_msgs(engine, fazenda_id=1) == []
