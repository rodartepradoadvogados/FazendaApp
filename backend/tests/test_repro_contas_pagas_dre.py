"""
Reprodução ad-hoc (temporária — não faz parte do escopo permanente da
suíte) usada para diagnosticar os 3 bugs relatados após o uso real da
Rescisão: (1) não aparece em Contas pagas, (2) não aparece na DRE,
(3) "marcar como inativo" não inativou a pessoa.

Bate na mesma API que o frontend usa (GET /financeiro/lancamentos) e
replica em Python o predicado EXATO usado por cada aba do
`frontend/app/financeiro/page.tsx` para provar o que realmente acontece
com os dados, sem depender de um browser.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Pessoa


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

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
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _criar_pessoa(engine, nome: str) -> int:
    with Session(engine) as s:
        p = Pessoa(nome=nome, tipo="Funcionário", salario_base=3000.0, data_admissao=date(2020, 1, 1))
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


def test_repro_pendente_nao_aparece_em_contas_pagas_ate_dar_baixa(client):
    """Fechar como 'pendente' NÃO é um bug — 'Contas pagas' é especificamente
    para o que já foi pago. Confirma o dado subjacente e replica o predicado
    exato da aba (`r.tipo === "despesa" && r.data_pagamento`)."""
    c, engine = client
    pessoa_id = _criar_pessoa(engine, "Valéria Bonfim")
    data_deslig = (date.today() - timedelta(days=10)).isoformat()

    r = c.post("/cadastro/rescisoes", json={
        "pessoa_id": pessoa_id, "tipo_rescisao": "sem_justa_causa",
        "data_desligamento": data_deslig, "dias_ferias_vencidas": 0, "aviso_previo_trabalhado": False,
    })
    assert r.status_code == 200, r.text
    registro_id = r.json()["id"]

    r_fechar = c.post(f"/cadastro/rescisoes/{registro_id}/fechar", json={"forma_lancamento": "unico", "status_pagamento": "pendente"})
    assert r_fechar.status_code == 200, r_fechar.text
    numero = r_fechar.json()["numero_lancamento_gerado"]

    lancs = c.get("/financeiro/lancamentos").json()["lancamentos"]
    conta = next(x for x in lancs if x["numero_lancamento"] == numero)

    assert conta["tipo"] == "despesa"
    assert conta["data_pagamento"] is None  # pendente -> sem data de pagamento, por design (rh_folha.py:1426)
    aparece_em_pagas = conta["tipo"] == "despesa" and bool(conta["data_pagamento"])
    assert aparece_em_pagas is False  # correto: pendente pertence a "Contas a pagar", não a "Contas pagas"

    # E aparece em "Contas a pagar" (o outro lado da mesma moeda)?
    aparece_em_a_pagar = conta["tipo"] == "despesa" and not conta["data_pagamento"]
    assert aparece_em_a_pagar is True


def test_repro_pago_aparece_em_contas_pagas(client):
    """Fechar como 'pago' preenche data_pagamento -> aparece em Contas pagas
    normalmente, confirmando que a classificação em si nunca teve bug."""
    c, engine = client
    pessoa_id = _criar_pessoa(engine, "Fulano Pago")
    data_deslig = (date.today() - timedelta(days=10)).isoformat()
    data_pgto = date.today().isoformat()

    r = c.post("/cadastro/rescisoes", json={
        "pessoa_id": pessoa_id, "tipo_rescisao": "sem_justa_causa",
        "data_desligamento": data_deslig, "dias_ferias_vencidas": 0, "aviso_previo_trabalhado": False,
    })
    registro_id = r.json()["id"]
    r_fechar = c.post(f"/cadastro/rescisoes/{registro_id}/fechar", json={
        "forma_lancamento": "unico", "status_pagamento": "pago", "data_pagamento": data_pgto,
    })
    assert r_fechar.status_code == 200, r_fechar.text
    numero = r_fechar.json()["numero_lancamento_gerado"]

    lancs = c.get("/financeiro/lancamentos").json()["lancamentos"]
    conta = next(x for x in lancs if x["numero_lancamento"] == numero)
    aparece_em_pagas = conta["tipo"] == "despesa" and bool(conta["data_pagamento"])
    assert aparece_em_pagas is True


def test_repro_dre_nao_e_bug_de_classificacao_e_sim_filtro_de_periodo(client):
    """Desmonta a hipótese de 'Rescisão não está numa allow-list do DRE':
    não existe tipo_documento nem codigo_conta exigidos em lugar nenhum do
    caminho real (GET /financeiro/lancamentos + cálculo client-side em
    financeiro/page.tsx — o endpoint /financeiro/dre do backend nem é
    chamado por essa aba, ver lib/api.ts:fetchDRE, sem nenhum call site).
    O que realmente esconde a rescisão é o período padrão da aba DRE
    (antes do fix: hoje-hoje; depois: mês corrente), replicado aqui."""
    c, engine = client
    pessoa_id = _criar_pessoa(engine, "Valéria Bonfim")
    # "Hoje" sintético fixo (dia 15 de um mês qualquer), não o `date.today()`
    # real: este teste é aritmética pura em Python replicando o cálculo
    # client-side de financeiro/page.tsx — nada aqui chama um endpoint cuja
    # resposta dependa do relógio real —, então usar uma data fixa evita
    # que o teste dependa de EM QUE DIA DO MÊS a suíte é rodada. Com
    # `date.today()` de verdade, rodar a suíte no dia 1-3 do mês real
    # quebrava o cenário: `data_competencia` é sempre normalizada pro dia 1
    # do mês (ver rh_contratos.py), então "hoje" sendo também dia 1 colide
    # com ela e as duas janelas ("hoje-hoje" e "mês corrente") viram a
    # mesma — nenhuma data consegue ao mesmo tempo "ficar poucos dias atrás
    # de hoje" E "cair no mês corrente" quando hoje É o dia 1.
    hoje_ref = date(2026, 6, 15)
    data_deslig = (hoje_ref - timedelta(days=3)).isoformat()

    r = c.post("/cadastro/rescisoes", json={
        "pessoa_id": pessoa_id, "tipo_rescisao": "sem_justa_causa",
        "data_desligamento": data_deslig, "dias_ferias_vencidas": 0, "aviso_previo_trabalhado": False,
    })
    registro_id = r.json()["id"]
    r_fechar = c.post(f"/cadastro/rescisoes/{registro_id}/fechar", json={"forma_lancamento": "unico", "status_pagamento": "pendente"})
    numero = r_fechar.json()["numero_lancamento_gerado"]

    lancs = c.get("/financeiro/lancamentos").json()["lancamentos"]
    conta = next(x for x in lancs if x["numero_lancamento"] == numero)

    # Nenhuma classificação foi perdida: tipo_documento gravado normalmente,
    # nenhum "allow-list" filtra por ele em lugar nenhum do backend.
    assert conta["tipo_documento"] == "Rescisão"
    assert conta["centro_custo"] == "Pecuária Leiteira"  # bate com o default do filtro de centro do DRE

    hoje = hoje_ref.isoformat()
    inicio_mes = hoje_ref.replace(day=1).isoformat()

    # Predicado da aba DRE (financeiro/page.tsx: campoData = r.data_competencia)
    def na_dre(inicio: str, fim: str) -> bool:
        d = conta["data_competencia"]
        return bool(d and inicio <= d <= fim and conta["centro_custo"] == "Pecuária Leiteira")

    assert na_dre(hoje, hoje) is False  # período padrão ANTIGO (hoje-hoje) escondia a rescisão
    assert na_dre(inicio_mes, hoje) is True  # período padrão NOVO (mês corrente) mostra


def test_repro_inativar_pessoa_backend_ok_end_to_end(client):
    """Fluxo completo real (criar simulação -> fechar com inativar_pessoa) —
    mesmo teste do arquivo principal, repetido aqui lado a lado com os outros
    2 repros para documentar juntos: o backend grava ativo=False
    corretamente; o problema relatado era o front não atualizar a lista
    `pessoas` em memória (ver FeriasDecimoTerceiroView.tsx)."""
    c, engine = client
    pessoa_id = _criar_pessoa(engine, "Valéria Bonfim")

    r = c.post("/cadastro/rescisoes", json={
        "pessoa_id": pessoa_id, "tipo_rescisao": "sem_justa_causa",
        "data_desligamento": date.today().isoformat(), "dias_ferias_vencidas": 0, "aviso_previo_trabalhado": False,
    })
    registro_id = r.json()["id"]
    r_fechar = c.post(f"/cadastro/rescisoes/{registro_id}/fechar", json={"forma_lancamento": "unico", "inativar_pessoa": True})
    assert r_fechar.status_code == 200, r_fechar.text
    assert r_fechar.json()["inativou_pessoa"] is True

    with Session(engine) as s:
        assert s.get(Pessoa, pessoa_id).ativo is False

    # E a listagem que o frontend usaria pra refletir isso (GET /cadastro/pessoas)?
    listagem = c.get("/cadastro/pessoas").json()
    pessoa_na_lista = next(p for p in listagem if p["id"] == pessoa_id)
    assert pessoa_na_lista["ativo"] is False
