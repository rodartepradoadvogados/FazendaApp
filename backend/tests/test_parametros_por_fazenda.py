"""
Parâmetros por fazenda (Fase 0).

`ParametroFazenda.chave` era única no sistema inteiro: TODAS as fazendas
dividiam o mesmo PEV, a mesma gestação e as mesmas metas. Agora cada fazenda
pode personalizar, e quem não personalizou continua enxergando o padrão
global (fazenda_id NULL) — que é exatamente o valor de antes.
"""
from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import ParametroFazenda
from fazenda.rules.parametros import fazenda_atual, get_param


@pytest.fixture
def engine_com_parametros(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        # Padrão global (o que o seed cria).
        s.add(ParametroFazenda(chave="pev_dias", fazenda_id=None, grupo="manejo",
                               label="PEV", valor="45", tipo="int"))
        # Fazenda 2 personalizou o PEV dela.
        s.add(ParametroFazenda(chave="pev_dias", fazenda_id=2, grupo="manejo",
                               label="PEV", valor="60", tipo="int"))
        s.commit()
    monkeypatch.setattr(database, "engine", engine)
    yield engine
    # Não deixa a fazenda vazar para os testes seguintes.
    fazenda_atual.set(None)


class TestParametroPorFazenda:
    def test_sem_fazenda_no_contexto_usa_o_padrao_global(self, engine_com_parametros):
        """Regra pura / loop de fundo / instalação de fazenda única: continua
        lendo exatamente o valor de antes."""
        fazenda_atual.set(None)
        assert get_param("pev_dias") == 45

    def test_fazenda_sem_personalizacao_cai_no_padrao_global(self, engine_com_parametros):
        fazenda_atual.set(1)
        assert get_param("pev_dias") == 45

    def test_fazenda_com_personalizacao_usa_o_valor_dela(self, engine_com_parametros):
        fazenda_atual.set(2)
        assert get_param("pev_dias") == 60

    def test_uma_fazenda_nao_enxerga_o_parametro_da_outra(self, engine_com_parametros):
        """O ponto do isolamento: mudar de fazenda muda o valor lido, sem que
        uma sobrescreva a outra."""
        fazenda_atual.set(2)
        assert get_param("pev_dias") == 60
        fazenda_atual.set(1)
        assert get_param("pev_dias") == 45

    def test_chave_inexistente_usa_o_padrao_do_chamador(self, engine_com_parametros):
        fazenda_atual.set(2)
        assert get_param("chave_que_nao_existe", 99) == 99
