"""
A TRAVA DURA do motor de replicação (fazenda/rules/replicacao_fazenda.py) —
os testes que existem para o pior cenário do repositório: a sincronização
destrutiva apagar, por engano, uma fazenda-cliente de PRODUÇÃO.

Por que um arquivo só para isto, se `test_replicacao_fazenda.py` já tem um
`test_recusa_quando_destino_nao_e_teste`? Porque aquele teste prova apenas
que a chamada ESTOURA 409 — e estourar 409 não prova nada sobre o dado. Se
alguém, um dia, mover a verificação de `eh_teste` para DEPOIS do
`_apagar_destino` (ou chamar `_apagar_destino` de outro lugar qualquer), o
teste antigo continuaria verde com a fazenda de produção já apagada. Os
testes daqui olham para o DADO depois da recusa, não para a exceção.

Cobrem, nesta ordem:
  1. recusa preserva INTEGRALMENTE o dado do destino não-teste;
  2. o caminho de escrita (`_apagar_destino`) recusa sozinho, sem depender
     de quem o chamou;
  3. a trava lê `eh_teste` do BANCO, não do objeto em memória da Session;
  4. sentido único — nem com os parâmetros invertidos a origem é tocada.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.pool import StaticPool
from sqlalchemy import select as sa_select
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.models import Animal, Fazenda, Lactacao, Parto
from fazenda.rules.replicacao_fazenda import (
    SincronizacaoInvalidaError,
    _apagar_destino,
    _ordenar_com_quebra_de_ciclo,
    _tabelas_fazenda,
    sincronizar_fazenda_teste_destrutivo,
)


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return eng


def _semear(engine):
    """Três fazendas: 1 = origem "real"; 2 = sandbox (eh_teste=True); 3 =
    OUTRA fazenda-cliente de produção, com dado próprio — é ela que nunca
    pode perder uma linha sequer."""
    with Session(engine) as s:
        s.add_all([
            Fazenda(id=1, nome="Jairo Nasser", eh_teste=False),
            Fazenda(id=2, nome="Fazenda Teste", eh_teste=True),
            Fazenda(id=3, nome="Outra fazenda real", eh_teste=False),
        ])
        s.commit()
        for fid, numero in ((1, "100"), (3, "900")):
            animal = Animal(numero=numero, fazenda_id=fid, sexo="F")
            s.add(animal)
            s.commit()
            s.refresh(animal)
            parto = Parto(animal_id=animal.id, numero_matriz=numero, fazenda_id=fid, ordem_parto=1)
            s.add(parto)
            s.commit()
            s.refresh(parto)
            s.add(Lactacao(
                fazenda_id=fid, animal_id=animal.id, parto_id=parto.id,
                numero_matriz=numero, data_inicio=date(2026, 1, 1), numero_lactacao=1,
            ))
        s.commit()


def _retrato(engine, fazenda_id: int) -> dict[str, int]:
    """Quantas linhas cada tabela com `fazenda_id` tem para esta fazenda.
    Percorre as 180+ tabelas descobertas pelo próprio motor (não uma lista
    escrita à mão aqui) — assim o retrato cobre tabela nova sem ninguém
    precisar lembrar de atualizar o teste."""
    tabelas = _tabelas_fazenda()
    with Session(engine) as s:
        conn = s.connection()
        retrato: dict[str, int] = {}
        for nome, tabela in tabelas.items():
            pk = list(tabela.primary_key.columns)[0]
            retrato[nome] = len(conn.execute(sa_select(pk).where(tabela.c.fazenda_id == fazenda_id)).all())
        return retrato


def test_recusa_nao_apaga_nada_do_destino_de_producao(engine):
    """Regra 2 no que importa: depois da recusa, a fazenda de produção que
    foi apontada como destino por engano continua com TODAS as suas linhas.
    É este teste — e não o `pytest.raises` — que fica vermelho se a trava
    for movida para depois do primeiro DELETE."""
    _semear(engine)
    antes = _retrato(engine, 3)
    assert sum(antes.values()) > 0, "cenário sem dado nenhum não prova coisa alguma"

    with Session(engine) as s:
        with pytest.raises(SincronizacaoInvalidaError) as exc:
            sincronizar_fazenda_teste_destrutivo(s, origem_id=1, destino_id=3)
        assert exc.value.status_code == 409
        # Conferência DENTRO da transação recusada, antes do rollback: é o
        # único jeito de provar que nenhum DELETE chegou a rodar. Se
        # olhássemos só depois do rollback, uma trava que apagasse tudo e só
        # então estourasse 409 passaria despercebida — o rollback devolveria
        # as linhas e o teste ficaria verde mentindo.
        conn = s.connection()
        for nome, tabela in _tabelas_fazenda().items():
            pk = list(tabela.primary_key.columns)[0]
            vivas = len(conn.execute(sa_select(pk).where(tabela.c.fazenda_id == 3)).all())
            assert vivas == antes[nome], f"{nome}: {antes[nome]} linha(s) da fazenda de produção viraram {vivas}"
        s.rollback()

    assert _retrato(engine, 3) == antes


def test_caminho_de_escrita_recusa_sozinho(engine):
    """A trava não vive só na porta de entrada: `_apagar_destino`, chamado
    diretamente (como faria uma refatoração futura que separasse "limpar" de
    "copiar"), recusa por conta própria antes de executar qualquer DELETE."""
    _semear(engine)
    antes = _retrato(engine, 3)

    tabelas = _tabelas_fazenda()
    ordem, adiadas = _ordenar_com_quebra_de_ciclo(tabelas)
    with Session(engine) as s:
        with pytest.raises(SincronizacaoInvalidaError):
            _apagar_destino(s.connection(), tabelas, ordem, adiadas, 3)
        s.rollback()

    assert _retrato(engine, 3) == antes


def test_trava_le_o_banco_e_nao_o_objeto_em_memoria(engine):
    """`eh_teste` marcado só na memória da Session (sem flush/commit) não
    destrava nada: a verificação roda em SQL, pela mesma conexão das
    escritas. Sem isso, qualquer rota que carregasse a Fazenda e mexesse no
    campo antes de chamar a sincronização abriria a porta da produção."""
    _semear(engine)
    antes = _retrato(engine, 3)

    with Session(engine) as s:
        producao = s.get(Fazenda, 3)
        producao.eh_teste = True  # só em memória — nunca gravado
        with pytest.raises(SincronizacaoInvalidaError):
            sincronizar_fazenda_teste_destrutivo(s, origem_id=1, destino_id=3)
        s.rollback()

    with Session(engine) as s:
        assert s.get(Fazenda, 3).eh_teste is False
    assert _retrato(engine, 3) == antes


def test_destino_inexistente_nao_apaga_nada(engine):
    """Destino que não existe no banco é recusado como "não é fazenda de
    teste" — nunca tratado como "nada a proteger, pode apagar"."""
    _semear(engine)
    antes_1, antes_3 = _retrato(engine, 1), _retrato(engine, 3)
    with Session(engine) as s:
        with pytest.raises(SincronizacaoInvalidaError):
            sincronizar_fazenda_teste_destrutivo(s, origem_id=1, destino_id=99999)
        s.rollback()
    assert (_retrato(engine, 1), _retrato(engine, 3)) == (antes_1, antes_3)


def test_sentido_unico_origem_intacta_apos_sincronizacao(engine):
    """Regra 1, verificada tabela a tabela (não só no animal): depois de uma
    sincronização bem-sucedida, a fazenda de origem tem exatamente as mesmas
    linhas, com os mesmos ids e os mesmos valores."""
    _semear(engine)

    def _linhas_origem():
        with Session(engine) as s:
            animais = [(a.id, a.numero, a.sexo) for a in s.exec(select(Animal).where(Animal.fazenda_id == 1)).all()]
            partos = [(p.id, p.animal_id, p.ordem_parto) for p in s.exec(select(Parto).where(Parto.fazenda_id == 1)).all()]
            lacts = [(l.id, l.parto_id, l.numero_lactacao) for l in s.exec(select(Lactacao).where(Lactacao.fazenda_id == 1)).all()]
        return animais, partos, lacts

    antes_detalhe, antes_retrato = _linhas_origem(), _retrato(engine, 1)

    with Session(engine) as s:
        sincronizar_fazenda_teste_destrutivo(s, origem_id=1, destino_id=2)
        s.commit()

    assert _linhas_origem() == antes_detalhe
    assert _retrato(engine, 1) == antes_retrato
    # E a cópia de fato aconteceu (senão o teste acima passaria à toa).
    with Session(engine) as s:
        assert len(s.exec(select(Animal).where(Animal.fazenda_id == 2)).all()) == 1


def test_sentido_unico_nao_pode_ser_invertido_por_parametro(engine):
    """O caminho reverso não existe nem trocando os parâmetros de lugar:
    pedir "sandbox -> produção" cai na mesma trava (o destino é que precisa
    ser `eh_teste`), e a produção não perde nada. Antes disso, enche o
    sandbox — se o sentido pudesse ser invertido, seria justamente este dado
    de teste que sujaria a fazenda real."""
    _semear(engine)
    with Session(engine) as s:
        sincronizar_fazenda_teste_destrutivo(s, origem_id=1, destino_id=2)
        s.commit()

    antes_producao = _retrato(engine, 1)
    with Session(engine) as s:
        with pytest.raises(SincronizacaoInvalidaError) as exc:
            sincronizar_fazenda_teste_destrutivo(s, origem_id=2, destino_id=1)
        assert exc.value.status_code == 409
        s.rollback()

    assert _retrato(engine, 1) == antes_producao
