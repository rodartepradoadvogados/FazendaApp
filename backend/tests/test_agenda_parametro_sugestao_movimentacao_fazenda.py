"""
A Agenda lê o parâmetro de agendamento das sugestões de movimentação PELA
FAZENDA — o mesmo recorte por onde a tela de Parâmetros grava.

Bug silencioso que estes testes fixam (ver `calcular_agenda` em
fazenda/api/routers/agenda.py): a Agenda buscava o parâmetro por CHAVE
PRIMÁRIA, `session.get(ParametroSugestaoMovimentacao, 1)`, sobra do desenho
antigo de linha única global. A tela grava uma linha POR FAZENDA
(`movimentacoes._parametro_sugestao_movimentacao`), então:

  • a fazenda cujo parâmetro por acaso ficou com id = 1 mandava na Agenda de
    TODAS as outras;
  • depois que o backfill por fazenda apagou a linha órfã de id 1, o `get`
    passou a devolver None e a Agenda caía no `or ParametroSugestaoMovimentacao
    (id=1)` — objeto não salvo, com o padrão de fábrica —, ignorando por
    completo o que o dono tinha configurado.

O efeito prático é QUANDO a sugestão de troca de lote aparece: no dia em que o
animal passa a atender outro lote, ou só no dia fixo da semana escolhido.

O terceiro teste guarda a outra metade da correção: a Agenda é caminho de
LEITURA e roda a cada carregamento de tela, então lê o parâmetro sem
get-or-create — sem linha cadastrada usa o padrão em memória e NÃO grava nada
(senão a primeira visita à Agenda de um tenant novo criaria a linha sozinha).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import MODULOS
from fazenda.models import (
    Animal, ContratoFazenda, ContratoFazendaModulo, Fazenda, Lote,
    ParametroSugestaoMovimentacao, PesagemCorporal, Usuario, UsuarioFazenda,
)

FAZENDA_A = 1
FAZENDA_B = 2


@pytest.fixture
def ambiente():
    """Duas fazendas-cliente, cada uma com um animal que atende a um lote
    melhor que o seu — ou seja, cada uma com UMA sugestão de movimentação
    pendente hoje. `cliente(fazenda_id)` devolve um TestClient já com aquela
    fazenda selecionada, que é como o front chega às rotas."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    with Session(engine) as s:
        s.add(Fazenda(id=FAZENDA_A, nome="Fazenda A", ativa=True))
        s.add(Fazenda(id=FAZENDA_B, nome="Fazenda B", ativa=True))
        for fid in (FAZENDA_A, FAZENDA_B):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, ativo=True))
        usuario = Usuario(username="dono", senha_hash="x", papel="admin", ativo=True)
        s.add(usuario)
        s.commit()
        s.refresh(usuario)
        for fid in (FAZENDA_A, FAZENDA_B):
            s.add(UsuarioFazenda(usuario_id=usuario.id, fazenda_id=fid))
        # Mesmo cenário de sugestão dos dois lados: matriz pesada num lote de
        # recém-chegadas, com um lote "Aptas" (peso mínimo 300) disponível.
        for fid, numero in ((FAZENDA_A, "900"), (FAZENDA_B, "901")):
            s.add(Lote(codigo="02", nome="Aptas", peso_min=300, fazenda_id=fid))
            s.add(Animal(numero=numero, categoria_abrev="Vaca", sexo="F",
                         grupo_primario="01 - Recém-chegadas", ativo=True, fazenda_id=fid))
        s.commit()
        for fid, numero in ((FAZENDA_A, "900"), (FAZENDA_B, "901")):
            s.add(PesagemCorporal(numero_matriz=numero, data_pesagem=date.today(), peso_kg=350, fazenda_id=fid))
        s.commit()
        usuario_id = usuario.id

    class _UsuarioDoToken:
        def __call__(self):
            with Session(engine) as s:
                return s.get(Usuario, usuario_id)

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = _UsuarioDoToken()

    def cliente(fazenda_id: int) -> TestClient:
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id
        return TestClient(main.app)

    yield engine, cliente

    main.app.dependency_overrides.clear()


def _tem_sugestao(c: TestClient, numero: str) -> bool:
    r = c.get("/agenda/", params={"data": date.today().isoformat()})
    assert r.status_code == 200, r.text
    return any(
        e.get("tipo") == "sugestao_movimentacao" and e["numero_animal"] == numero
        for e in r.json()["eventos"]
    )


def _salvar_dia_fixo(c: TestClient, dia_semana: int) -> None:
    r = c.put("/movimentacoes/parametro-agendamento",
              json={"modo": "dia_fixo_semana", "dia_semana": dia_semana})
    assert r.status_code == 200, r.text


class TestRecortePorFazenda:
    def test_parametro_da_fazenda_a_nao_afeta_a_fazenda_b(self, ambiente):
        """O coração da regressão: a A escolhe um dia fixo que NÃO é hoje
        (some da agenda dela) e a B, que não configurou nada, continua vendo a
        sugestão. Com a busca por id = 1 a linha da A — a primeira gravada,
        logo id 1 — silenciava a Agenda da B junto."""
        engine, cliente = ambiente
        hoje = date.today()
        outro_dia = (hoje.weekday() + 1) % 7

        _salvar_dia_fixo(cliente(FAZENDA_A), outro_dia)

        assert _tem_sugestao(cliente(FAZENDA_A), "900") is False
        assert _tem_sugestao(cliente(FAZENDA_B), "901") is True

    def test_cada_fazenda_enxerga_o_proprio_dia_fixo(self, ambiente):
        """Contraprova simétrica: as duas configuram dia fixo, cada uma o seu.
        Hoje só pode aparecer a sugestão de quem escolheu hoje."""
        engine, cliente = ambiente
        hoje = date.today()

        _salvar_dia_fixo(cliente(FAZENDA_A), hoje.weekday())
        _salvar_dia_fixo(cliente(FAZENDA_B), (hoje.weekday() + 3) % 7)

        assert _tem_sugestao(cliente(FAZENDA_A), "900") is True
        assert _tem_sugestao(cliente(FAZENDA_B), "901") is False


class TestAgendaRespeitaATela:
    def test_agenda_segue_o_que_a_tela_de_parametros_gravou(self, ambiente):
        """Grava pela tela, lê pela Agenda, na mesma fazenda: ligar o dia fixo
        num dia diferente esconde a sugestão; trocar para hoje a traz de
        volta. Antes, a Agenda não enxergava nenhuma das duas gravações.

        A fazenda A grava PRIMEIRO de propósito: assim a linha dela fica com
        id = 1 e a da B com id = 2 — a B cai fora justamente da chave fixa que
        a leitura antiga procurava, que é o caso real de toda fazenda que não
        foi a primeira a salvar."""
        engine, cliente = ambiente
        hoje = date.today()

        _salvar_dia_fixo(cliente(FAZENDA_A), hoje.weekday())
        c = cliente(FAZENDA_B)

        _salvar_dia_fixo(c, (hoje.weekday() + 2) % 7)
        assert _tem_sugestao(c, "901") is False

        _salvar_dia_fixo(c, hoje.weekday())
        assert _tem_sugestao(c, "901") is True

        r = c.put("/movimentacoes/parametro-agendamento",
                  json={"modo": "na_data_parametro", "dia_semana": 4})
        assert r.status_code == 200
        assert _tem_sugestao(c, "901") is True


class TestLeituraNaoGrava:
    def test_sem_linha_usa_o_padrao_e_nao_escreve_no_banco(self, ambiente):
        """Nenhuma fazenda configurou nada: a Agenda usa o padrão de fábrica
        ("na_data_parametro", sugestão todo dia) e a tabela continua VAZIA
        depois de carregar a tela — a Agenda não pode criar linha nem commitar
        num GET."""
        engine, cliente = ambiente

        assert _tem_sugestao(cliente(FAZENDA_A), "900") is True
        assert _tem_sugestao(cliente(FAZENDA_B), "901") is True

        with Session(engine) as s:
            assert s.exec(select(ParametroSugestaoMovimentacao)).all() == []

    def test_agenda_nao_cria_linha_para_fazenda_que_nunca_configurou(self, ambiente):
        """A A configura, a B só olha a Agenda várias vezes: continua existindo
        UMA linha só, a da A."""
        engine, cliente = ambiente
        _salvar_dia_fixo(cliente(FAZENDA_A), date.today().weekday())

        for _ in range(3):
            _tem_sugestao(cliente(FAZENDA_B), "901")

        with Session(engine) as s:
            linhas = s.exec(select(ParametroSugestaoMovimentacao)).all()
            assert [p.fazenda_id for p in linhas] == [FAZENDA_A]
