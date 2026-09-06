"""
ACHADO CRÍTICO 44 da auditoria de segurança (03/09) — o único dos quatro que
APAGA dado de outra fazenda, e apagar de mais não é recuperável.

`_alvos("animal", numero, ...)` (fazenda/api/routers/exclusoes.py), usado por
`POST /exclusoes/confirmar` e por `POST /exclusoes/pendentes/{id}/aprovar`,
buscava o Animal já escopado por fazenda, mas as buscas SEGUINTES —
Servico, Parto, ControleLeiteiro, Sanidade (e a AgendaManual de retenção de
placenta, no tipo "parto") — casavam só por `numero_matriz`, sem
`fazenda_id`. Todos esses objetos vão direto para `_excluir_alvos_em_ordem`,
que os deleta de verdade.

Cenário concreto, disparável em uso NORMAL, sem má-fé nenhuma: `animal.numero`
deixou de ser único globalmente na migração `c24befa94c1b` — números de animal
são curtos e sequenciais por fazenda, então a fazenda 1 e a fazenda 2 têm,
cada uma, o seu animal "500". O administrador da fazenda 2 exclui a ficha do
SEU animal "500" e leva junto o histórico reprodutivo, produtivo e sanitário
do animal "500" da fazenda 1.

Este arquivo tem duas metades, nessa ordem de propósito:

1. CARACTERIZAÇÃO — o que a cascata apaga hoje, dentro da própria fazenda.
   Antes de mexer no comportamento de uma rotina destrutiva é preciso ter
   escrito o que ela faz: apagar de menos se conserta depois, apagar de mais
   não.
2. ISOLAMENTO — a mesma cascata não pode encostar em nada da fazenda 1.

Token de verdade (`criar_token`), como em test_trava_fazenda_selecionada.py.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    AgendaManual, Animal, ColostragemBezerra, ContratoFazenda, ContratoFazendaModulo, ControleLeiteiro,
    Fazenda, FotoCampo, Lactacao, Parto, PesagemCorporal, Sanidade, Servico, SolicitacaoExclusao,
    Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS

NUMERO = "500"


def _povoar_fazenda(s: Session, fazenda_id: int, marca: str) -> None:
    """O MESMO conjunto de registros, com o MESMO número de animal, nas duas
    fazendas — só o texto (`marca`) distingue de quem é cada linha."""
    animal = Animal(numero=NUMERO, nome=f"Vaca {marca}", fazenda_id=fazenda_id, ativo=True)
    s.add(animal)
    s.commit()
    s.refresh(animal)
    s.add(Servico(animal_id=animal.id, numero_matriz=NUMERO, fazenda_id=fazenda_id,
                  data_servico=date(2026, 1, 10), touro=f"Touro {marca}"))
    s.add(Parto(animal_id=animal.id, numero_matriz=NUMERO, fazenda_id=fazenda_id,
                data_parto=date(2026, 2, 20), ordem_parto=1))
    s.add(ControleLeiteiro(animal_id=animal.id, numero_matriz=NUMERO, fazenda_id=fazenda_id,
                           data_controle=date(2026, 3, 1), total_kg=25.0))
    s.add(Sanidade(animal_id=animal.id, numero_matriz=NUMERO, fazenda_id=fazenda_id,
                   produto=f"Produto {marca}", data_aplicacao=date(2026, 3, 5)))
    s.add(PesagemCorporal(numero_matriz=NUMERO, fazenda_id=fazenda_id,
                          data_pesagem=date(2026, 3, 8), peso_kg=520.0))
    s.add(ColostragemBezerra(animal_id=animal.id, numero_animal=NUMERO, fazenda_id=fazenda_id,
                             tomou_colostro=True))
    s.add(Lactacao(animal_id=animal.id, numero_matriz=NUMERO, fazenda_id=fazenda_id,
                   data_inicio=date(2026, 2, 20), origem="parto"))
    s.add(FotoCampo(animal_id=animal.id, identificacao_animal=NUMERO, fazenda_id=fazenda_id,
                    caminho_storage=f"{marca}/foto.jpg", mime_type="image/jpeg",
                    tamanho_bytes=10, tipo_assunto="animal"))
    s.commit()


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(Fazenda(id=2, nome="Fazenda 2"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.add(Usuario(id=1, username="admin2", senha_hash=hash_senha("x"), papel="admin", ativo=True))
        s.add(Usuario(id=2, username="operador2", senha_hash=hash_senha("x"), papel="operador",
                      permissoes="", ativo=True))
        s.add(UsuarioFazenda(usuario_id=1, fazenda_id=2))
        s.add(UsuarioFazenda(usuario_id=2, fazenda_id=2))
        s.commit()
        _povoar_fazenda(s, 1, "da Fazenda 1")
        _povoar_fazenda(s, 2, "da Fazenda 2")

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _cabecalho(username: str, fazenda_id: int):
    return {"Authorization": f"Bearer {criar_token(username, fazenda_id=fazenda_id)}"}


def _contagem(engine, fazenda_id: int) -> dict[str, int]:
    """Quantos registros de cada tipo, ligados ao animal NUMERO, ainda existem
    nesta fazenda."""
    with Session(engine) as s:
        def n(model, coluna):
            return len(s.exec(
                select(model).where(coluna == NUMERO, model.fazenda_id == fazenda_id)
            ).all())
        return {
            "animal": n(Animal, Animal.numero),
            "servico": n(Servico, Servico.numero_matriz),
            "parto": n(Parto, Parto.numero_matriz),
            "controle": n(ControleLeiteiro, ControleLeiteiro.numero_matriz),
            "sanidade": n(Sanidade, Sanidade.numero_matriz),
            "pesagem": n(PesagemCorporal, PesagemCorporal.numero_matriz),
            "colostragem": n(ColostragemBezerra, ColostragemBezerra.numero_animal),
            "lactacao": n(Lactacao, Lactacao.numero_matriz),
            "foto": n(FotoCampo, FotoCampo.identificacao_animal),
        }


CHEIO = {
    "animal": 1, "servico": 1, "parto": 1, "controle": 1, "sanidade": 1,
    "pesagem": 1, "colostragem": 1, "lactacao": 1, "foto": 1,
}


class TestCaracterizacaoDaCascataDeAnimal:
    """O que a exclusão de uma FICHA DE ANIMAL apaga hoje, dentro da própria
    fazenda. Escrito antes de mexer em qualquer coisa: é o contrato que a
    correção de isolamento não pode alterar por acidente."""

    def test_impacto_lista_o_que_sera_apagado(self, client):
        c, _engine = client
        r = c.post("/exclusoes/impacto", json={"tipo": "animal", "id": NUMERO},
                   headers=_cabecalho("admin2", 2))
        assert r.status_code == 200, r.text
        texto = " | ".join(r.json()["impacto"]).lower()
        assert "ficha do animal 500" in texto
        for esperado in ("serviço", "parto", "controle leiteiro", "sanidade",
                         "colostragem", "lactação", "foto"):
            assert esperado in texto, f"o impacto não avisa sobre {esperado}: {texto}"
        # Pesagem corporal NÃO entra na cascata hoje — fica órfã de propósito
        # ou por omissão, mas o comportamento está escrito aqui.
        assert "pesagem" not in texto

    def test_confirmar_apaga_a_cascata_da_propria_fazenda(self, client):
        c, engine = client
        r = c.post("/exclusoes/confirmar", json={"tipo": "animal", "id": NUMERO},
                   headers=_cabecalho("admin2", 2))
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "excluido"
        assert _contagem(engine, 2) == {
            "animal": 0, "servico": 0, "parto": 0, "controle": 0, "sanidade": 0,
            # PesagemCorporal sobrevive: não está entre os alvos de `_alvos`.
            "pesagem": 1,
            "colostragem": 0, "lactacao": 0, "foto": 0,
        }


class TestCascataDeAnimalNaoAtravessaFazenda:
    """A metade que fecha o achado 44: a mesma cascata acima, com o mesmo
    número de animal existindo nas DUAS fazendas."""

    def test_excluir_animal_da_fazenda_2_nao_apaga_nada_da_fazenda_1(self, client):
        c, engine = client
        r = c.post("/exclusoes/confirmar", json={"tipo": "animal", "id": NUMERO},
                   headers=_cabecalho("admin2", 2))
        assert r.status_code == 200, r.text
        assert _contagem(engine, 1) == CHEIO, (
            "a exclusão do animal '500' da fazenda 2 apagou histórico do animal '500' da "
            "fazenda 1 — números de animal colidem entre fazendas desde a migração c24befa94c1b, "
            "e isso é destruição de dado de outro cliente, sem volta"
        )

    def test_impacto_da_fazenda_2_nao_conta_registro_da_fazenda_1(self, client):
        """A prévia mostrada ao usuário também não pode contar (nem revelar)
        o que existe na outra fazenda: '2 parto(s)' já seria vazamento."""
        c, _engine = client
        r = c.post("/exclusoes/impacto", json={"tipo": "animal", "id": NUMERO},
                   headers=_cabecalho("admin2", 2))
        assert r.status_code == 200, r.text
        texto = " | ".join(r.json()["impacto"])
        for plural in ("2 serviço", "2 parto", "2 registro(s) de controle leiteiro",
                       "2 aplicação", "2 lactação", "2 foto"):
            assert plural not in texto, f"o impacto contou registros da outra fazenda: {texto}"

    def test_animal_de_outra_fazenda_e_404_e_nao_403(self, client):
        """Fazenda 2 pedindo um número que só existe na fazenda 1: 404. Um 403
        confirmaria ao atacante que o registro existe do outro lado."""
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="777", nome="Só da Fazenda 1", fazenda_id=1, ativo=True))
            s.commit()
        r = c.post("/exclusoes/confirmar", json={"tipo": "animal", "id": "777"},
                   headers=_cabecalho("admin2", 2))
        assert r.status_code == 404, r.text
        with Session(engine) as s:
            assert s.exec(select(Animal).where(Animal.numero == "777")).first() is not None

    def test_aprovar_pendente_tambem_nao_atravessa(self, client):
        """O outro caminho até `_alvos`: o operador SOLICITA, o admin aprova.
        A exclusão de verdade acontece dentro de `aprovar_pendente`."""
        c, engine = client
        r = c.post("/exclusoes/confirmar", json={"tipo": "animal", "id": NUMERO},
                   headers=_cabecalho("operador2", 2))
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "solicitado"

        with Session(engine) as s:
            sol = s.exec(select(SolicitacaoExclusao)).first()
            assert sol is not None and sol.fazenda_id == 2, (
                f"a solicitação nasceu sem fazenda ou na fazenda errada: {sol}"
            )
            sol_id = sol.id

        r = c.post(f"/exclusoes/pendentes/{sol_id}/aprovar", headers=_cabecalho("admin2", 2))
        assert r.status_code == 200, r.text
        assert _contagem(engine, 1) == CHEIO, (
            "a aprovação da solicitação da fazenda 2 apagou histórico da fazenda 1"
        )
        assert _contagem(engine, 2)["animal"] == 0


class TestCascataDePartoNaoAtravessaFazenda:
    """Mesmo achado, no tipo "parto": a pendência de retenção de placenta é
    achada na Agenda por heurística de texto (matriz + data + prefixo da
    descrição), sem id nenhum — se o número do animal e a data do parto
    coincidirem entre fazendas, a pendência da outra fazenda entra na
    cascata."""

    def _agenda_retencao(self, s: Session, fazenda_id: int) -> None:
        s.add(AgendaManual(
            data_evento=date(2026, 2, 20),
            descricao=f"Retenção de placenta — vaca {NUMERO} (parto em 20/02/2026)",
            numero_animal=NUMERO, categoria="Sanidade", tipo_evento="Sanidade",
            fazenda_id=fazenda_id,
        ))
        s.commit()

    def test_excluir_parto_da_fazenda_2_nao_apaga_agenda_da_fazenda_1(self, client):
        c, engine = client
        with Session(engine) as s:
            self._agenda_retencao(s, 1)
            self._agenda_retencao(s, 2)
            parto_f2 = s.exec(
                select(Parto).where(Parto.numero_matriz == NUMERO, Parto.fazenda_id == 2)
            ).first()
            parto_id = parto_f2.id

        r = c.post("/exclusoes/confirmar", json={"tipo": "parto", "id": str(parto_id)},
                   headers=_cabecalho("admin2", 2))
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            restantes = s.exec(select(AgendaManual)).all()
            fazendas = sorted(a.fazenda_id for a in restantes)
            assert fazendas == [1], (
                "a exclusão do parto da fazenda 2 apagou a pendência de retenção de placenta "
                f"da fazenda 1 (sobraram: {fazendas})"
            )

    def test_parto_de_outra_fazenda_e_404(self, client):
        c, engine = client
        with Session(engine) as s:
            parto_f1 = s.exec(
                select(Parto).where(Parto.numero_matriz == NUMERO, Parto.fazenda_id == 1)
            ).first()
            parto_id = parto_f1.id

        r = c.post("/exclusoes/confirmar", json={"tipo": "parto", "id": str(parto_id)},
                   headers=_cabecalho("admin2", 2))
        assert r.status_code == 404, r.text
        with Session(engine) as s:
            assert s.get(Parto, parto_id) is not None
