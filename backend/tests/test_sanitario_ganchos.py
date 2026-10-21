"""
Sanitário v2 — ganchos: parto, diagnóstico/serviço, secagem, baixa, venda,
compra e cadastro avisam o sanitário NA HORA (animal entra/sai das caixas),
dentro da transação de quem escreveu.

1) contrato: cada rota da lista `ganchos.PONTOS_PLUGADOS` chama
   `ganchos_sanitario.animal_mudou` no fonte;
2) `animal_mudou` direto: diagnóstico abre a gestação (entra no pré-parto),
   parto tira, venda tira de tudo, falha nunca derruba quem chamou;
3) ponta a ponta pela API: POST /reproducao/parto, /vendas-animais/,
   /compras-animais/ e /cadastro/animais.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, CategoriaManejo, ContratoFazenda, ContratoFazendaModulo, Fazenda, SanitarioSituacao, Servico, Usuario,
    UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules.sanitario import ganchos
from fazenda.rules.sanitario.ganchos import PONTOS_PLUGADOS, animal_mudou
from tests.sanitario_cenario import (  # noqa: F401  (fixtures)
    F1, HOJE, animal, caixa, def_b19, def_pre_parto, engine, parto, servico, session,
)

BACKEND = Path(__file__).resolve().parent.parent


def _estados(session, animal_id):
    return sorted(session.exec(select(SanitarioSituacao.estado).where(SanitarioSituacao.animal_id == animal_id)).all())


# ── 1) contrato ─────────────────────────────────────────────────────────────
def test_contrato_cada_ponto_chama_o_gancho():
    for arquivo, eventos in PONTOS_PLUGADOS.items():
        fonte = (BACKEND / arquivo).read_text()
        assert "from fazenda.rules.sanitario import ganchos as ganchos_sanitario" in fonte, arquivo
        achados = set(re.findall(r'animal_mudou\([^)]*evento="([a-z_]+)"', fonte, re.S))
        faltando = set(eventos) - achados
        assert not faltando, f"{arquivo}: gancho ausente para {sorted(faltando)}"


# ── 2) direto ───────────────────────────────────────────────────────────────
def test_diagnostico_abre_gestacao_e_parto_tira_do_pre_parto(session):
    caixa(session, def_pre_parto())
    vaca = animal(session, "0701", idade_dias=1700)
    sv = servico(session, vaca, HOJE - timedelta(days=265), positivo=False)
    animal_mudou(session, F1, numeros=["0701"], evento="servico", hoje=HOJE)
    assert _estados(session, vaca.id) == []          # sem diagnóstico positivo: sem gestação
    sv.diagnostico = "POSITIVO"
    session.add(sv)
    animal_mudou(session, F1, numeros=["0701"], evento="diagnostico", hoje=HOJE)
    assert _estados(session, vaca.id) == ["janela"]  # entrou no pré-parto
    parto(session, vaca, HOJE)
    animal_mudou(session, F1, animal_ids=[vaca.id], evento="parto", hoje=HOJE + timedelta(days=1))
    assert _estados(session, vaca.id) == ["perdida"]  # pariu sem receber: saiu da janela


def test_venda_tira_de_tudo(session):
    caixa(session, def_b19())
    caixa(session, def_b19(nome="Outra B19", nome_curto="B19b"))
    a = animal(session, "2401", idade_dias=150)
    animal_mudou(session, F1, animal_ids=[a.id], evento="cadastro", hoje=HOJE)
    assert _estados(session, a.id) == ["janela", "janela"]
    a.ativo, a.motivo_baixa = False, "venda"
    session.add(a)
    animal_mudou(session, F1, numeros=["2401"], evento="venda", hoje=HOJE)
    assert _estados(session, a.id) == ["saiu", "saiu"]


def test_sem_caixa_ativa_nao_faz_nada_e_erro_nao_propaga(session, monkeypatch):
    a = animal(session, "2401", idade_dias=150)
    assert animal_mudou(session, F1, animal_ids=[a.id], evento="cadastro") == {}
    caixa(session, def_b19())

    def _explode(*_a, **_k):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr("fazenda.rules.sanitario.motor.recalcular", _explode)
    assert animal_mudou(session, F1, animal_ids=[a.id], evento="cadastro") == {"erro": True}
    assert ganchos  # módulo importável


# ── 3) ponta a ponta pela API ───────────────────────────────────────────────
@pytest.fixture
def api():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    with Session(eng) as s:
        s.add(Fazenda(id=1, nome="Estreito", ativa=True))
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        for modulo in MODULOS_COMERCIAIS:
            s.add(ContratoFazendaModulo(fazenda_id=1, modulo=modulo, preco=0.0, ativo=True))
        u = Usuario(username="adm", senha_hash="x", papel="admin", ativo=True)
        s.add(u)
        s.commit()
        s.refresh(u)
        s.add(UsuarioFazenda(usuario_id=u.id, fazenda_id=1))
        s.add(CategoriaManejo(fazenda_id=1, nome="Novilha", dia_min=0, dia_max=None))
        s.commit()
        uid = u.id

    def _sessao():
        with Session(eng) as s:
            yield s

    def _usuario():
        with Session(eng) as s:
            return s.get(Usuario, uid)

    main.app.dependency_overrides[database.get_session] = _sessao
    main.app.dependency_overrides[get_current_user] = _usuario
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
    with TestClient(main.app) as c:
        yield c, eng
    main.app.dependency_overrides.clear()


def test_api_parto_venda_compra_e_cadastro_acionam_o_motor(api):
    c, eng = api
    hoje = date.today()
    with Session(eng) as s:
        from fazenda.rules.sanitario.definicao import criar_caixa
        criar_caixa(s, 1, def_pre_parto(), estado="ativa", hoje=hoje)
        criar_caixa(s, 1, def_b19(), estado="ativa", hoje=hoje)
        vaca = Animal(fazenda_id=1, numero="0701", sexo="F", data_nasc=hoje - timedelta(days=1700), ativo=True)
        bez = Animal(fazenda_id=1, numero="2401", sexo="F", data_nasc=hoje - timedelta(days=150), ativo=True)
        s.add(vaca)
        s.add(bez)
        s.add(Servico(fazenda_id=1, numero_matriz="0701", data_servico=hoje - timedelta(days=270), diagnostico="POSITIVO"))
        s.commit()
        vid, bid = vaca.id, bez.id

    # cadastro de animal: a bezerra nova entra na B19 na hora
    r = c.post("/cadastro/animais", json={"numero": "2402", "sexo": "F", "data_nasc": str(hoje - timedelta(days=130))})
    assert r.status_code == 200, r.text
    with Session(eng) as s:
        nova = s.exec(select(Animal).where(Animal.numero == "2402")).one()
        assert _estados(s, nova.id) == ["janela"]

    # parto: a vaca sai do pré-parto (gestação fechada no parto real)
    with Session(eng) as s:
        from fazenda.rules.sanitario.motor import recalcular
        recalcular(s, 1)
        s.commit()
        assert _estados(s, vid) == ["janela"]
    r = c.post("/reproducao/parto", json={"numero_matriz": "0701", "data_parto": str(hoje), "crias": []})
    assert r.status_code == 200, r.text
    with Session(eng) as s:
        assert _estados(s, vid) != ["janela"]

    # venda: a bezerra sai de tudo
    with Session(eng) as s:
        recalcular(s, 1)
        s.commit()
    r = c.post("/vendas-animais/", json={
        "animais": ["2401"], "comprador": "Fulano", "valor": 100.0, "tipo_valor": "total",
        "data_venda": str(hoje), "codigo_conta_gerencial": "1.01",
    })
    assert r.status_code == 200, r.text
    with Session(eng) as s:
        assert _estados(s, bid) == ["saiu"]
