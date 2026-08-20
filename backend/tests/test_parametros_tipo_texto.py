"""
Parâmetro de tipo `texto` na leitura de `GET /parametros/`.

Bug pré-existente, achado ao acrescentar o grupo de Alimentação. A montagem da
resposta tinha ramos para `bool`, `date` e `float`, e um `else` final que fazia
`int(float(valor))` — então TEXTO caía no `else`, estourava ValueError e virava
`None` em silêncio.

Não era hipótese: o único parâmetro de texto que existia, `laticinio_nome` (o
nome do laticínio que faz o RMCA reconhecer a receita de leite), chegava nulo à
tela desde que foi criado. Na prática o campo aparecia vazio; quem salvasse a
tela por cima gravava vazio e desligava o reconhecimento da receita de leite
sem nenhum aviso.

Este teste trava os dois lados: o texto volta como texto, e os outros tipos
continuam convertidos como antes — porque a correção mexe numa cadeia de
if/elif que o resto dos parâmetros do sistema atravessa.
"""
from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import ParametroFazenda
from fazenda.rules.parametros import fazenda_atual


@pytest.fixture
def engine_com_tipos(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(ParametroFazenda(chave="laticinio_nome", fazenda_id=None, grupo="financeiro",
                               label="Nome do laticínio", valor="italac", tipo="texto"))
        s.add(ParametroFazenda(chave="modo_lancamento_alimentacao", fazenda_id=None, grupo="alimentacao",
                               label="Como lançar a alimentação", valor="fornecido_sobra", tipo="texto"))
        s.add(ParametroFazenda(chave="sobra_alvo_pct", fazenda_id=None, grupo="alimentacao",
                               label="Sobra alvo", valor="5", tipo="int"))
        s.add(ParametroFazenda(chave="usa_adesivo_deteccao_cio", fazenda_id=None, grupo="reinseminacao_cio",
                               label="Usa adesivo", valor="true", tipo="bool"))
        s.add(ParametroFazenda(chave="percentual_estimado_fgts_mensal", fazenda_id=None, grupo="folha_rh",
                               label="FGTS", valor="0.08", tipo="float"))
        s.commit()
    monkeypatch.setattr(database, "engine", engine)
    yield engine
    fazenda_atual.set(None)


def _valores(engine) -> dict:
    """Chama o endpoint de listagem e devolve {chave: valor} já convertido."""
    from fazenda.api.routers.parametros import obter_parametros

    with Session(engine) as s:
        resposta = obter_parametros(session=s, fazenda_id=None)
    achatado = {}
    for grupo in resposta.get("grupos", {}).values():
        for item in grupo["itens"]:
            achatado[item["chave"]] = item["valor"]
    return achatado


class TestParametroTexto:
    def test_texto_volta_como_texto_e_nao_como_none(self, engine_com_tipos):
        """O caso que estava quebrado."""
        v = _valores(engine_com_tipos)
        assert v["laticinio_nome"] == "italac", "texto virou None — o RMCA perderia o reconhecimento da receita de leite"
        assert v["modo_lancamento_alimentacao"] == "fornecido_sobra"

    def test_os_outros_tipos_continuam_convertidos(self, engine_com_tipos):
        """A correção mexe numa cadeia de if/elif por onde passam todos os
        parâmetros do sistema — não pode ter deslocado nenhum outro tipo."""
        v = _valores(engine_com_tipos)
        assert v["sobra_alvo_pct"] == 5 and isinstance(v["sobra_alvo_pct"], int)
        assert v["usa_adesivo_deteccao_cio"] is True
        assert v["percentual_estimado_fgts_mensal"] == pytest.approx(0.08)

    def test_texto_vazio_e_string_vazia_nao_none(self, engine_com_tipos):
        """Distinguir "configurado como vazio" de "não consegui ler" importa:
        só o primeiro é estado do usuário."""
        with Session(engine_com_tipos) as s:
            linha = s.exec(
                __import__("sqlmodel").select(ParametroFazenda).where(ParametroFazenda.chave == "laticinio_nome")
            ).first()
            linha.valor = ""
            s.add(linha)
            s.commit()
        assert _valores(engine_com_tipos)["laticinio_nome"] == ""
