"""
A escolha das colunas que ganham sufixo na sincronização da Fazenda Teste
(`replicacao_fazenda._colunas_para_desambiguar`).

O QUE QUEBRAVA, em produção, no dia 08/09/2026: sincronizar a fazenda do
cliente para a Fazenda Teste respondia HTTP 500 e o sandbox ficava vazio. O
erro do banco era `time zone "sandbox-diaria_dia-1" not recognized`, que não
diz nada sobre a causa — a sincronização estava grudando o sufixo de
desambiguação `::sandbox-<tabela>-<id>` na coluna `data` de `diaria_dia`, que
é DATE. O Postgres, recebendo `'2026-07-18::sandbox-diaria_dia-1'` para uma
data, lê o `::` como cast e o resto como fuso horário.

POR QUE `data` VIRAVA CANDIDATA: a regra antiga era "toda coluna não-FK de uma
UNIQUE que não inclui fazenda_id". Em `UniqueConstraint(diaria_id, data)`,
`diaria_id` é FK e `data` não — então `data` entrava.

POR QUE ELA NÃO DEVIA: `diaria_id` aponta para `diaria`, que TAMBÉM é copiada
nesta sincronização e ganha id novo no destino. Como o destino é limpo antes
da cópia, dois registros copiados nunca colidem entre si (a origem já
respeitava a restrição) e nunca colidem com outra fazenda (os ids do pai são
novos). A restrição já estava isolada — não havia o que desambiguar.

ESTE ARQUIVO NÃO PRECISA DE BANCO: mede a decisão, que é onde o defeito
estava. O efeito no banco de verdade é medido em
test_replicacao_desambiguacao_postgres.py, porque em SQLite a coluna DATE
aceita a string com sufixo sem reclamar — um teste lá ficaria verde com o
defeito no lugar.
"""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mktemp(suffix='.db')}")

import pytest

from fazenda.rules.replicacao_fazenda import _colunas_para_desambiguar, _tabelas_fazenda


@pytest.fixture
def tabelas():
    return _tabelas_fazenda()


def _para(tabelas, nome: str) -> set[str]:
    return _colunas_para_desambiguar(tabelas[nome], tabelas, [])


def test_a_data_da_diaria_nao_ganha_sufixo(tabelas):
    """O caso que derrubava a sincronização em produção.

    REGISTRO HONESTO DO ALCANCE, aferido revertendo cada metade em separado:
    este teste passa com QUALQUER uma das duas no lugar — a regra da FK
    remapeada exclui `data` por ser desnecessária, e a guarda de tipo a exclui
    por não ser texto. Ou seja, ele mede o sintoma (o 500 sumiu), não prende
    nenhuma das duas sozinha. Quem prende a regra da FK são os dois testes
    seguintes, que ficam VERMELHOS sem ela."""
    assert "data" not in _para(tabelas, "diaria_dia"), (
        "`data` é DATE: o sufixo de texto produz um valor que o Postgres recusa"
    )


def test_as_outras_restricoes_com_fk_remapeada_tambem_saem(tabelas):
    """Mesma família, mesmo raciocínio — e as duas encostavam na regra antiga.

    Aqui as colunas são VARCHAR, então o sufixo não quebrava; mas desambiguar
    à toa suja o dado do sandbox com `::sandbox-...` sem necessidade."""
    assert "competencia" not in _para(tabelas, "fatura_cartao")
    assert "numero_matriz" not in _para(tabelas, "cronograma_sanitario_animal")


def test_o_que_precisa_de_sufixo_continua_ganhando(tabelas):
    """A correção não pode ter desligado a desambiguação de quem precisa.

    Estas UNIQUEs são globais (sem `fazenda_id`) e não têm FK remapeada: sem o
    sufixo, copiar a fazenda do cliente colidiria com a linha da outra."""
    assert "txid" in _para(tabelas, "cobranca_pix")
    assert "referencia_asaas" in _para(tabelas, "cobranca_asaas")
    assert "document_token" in _para(tabelas, "contrato_assinatura_zapsign")
    assert {"tela", "nome"} <= _para(tabelas, "filtro_salvo")
    assert {"chave", "metodo", "caminho"} <= _para(tabelas, "idempotencia_chave")


def test_nenhuma_coluna_nao_textual_sobra_no_esquema_de_hoje(tabelas):
    """Rede de segurança para o esquema inteiro, e não só para as tabelas
    citadas acima: se alguém criar amanhã uma UNIQUE que exija sufixo numa
    coluna que não é texto, o aviso aparece aqui antes de virar um 500
    ilegível em produção.

    Este teste fica VERMELHO sem a regra da FK remapeada — é ele, junto com o
    anterior, que a prende.

    A GUARDA DE TIPO em si não tem teste que a prenda, e não tem como ter hoje:
    com a regra da FK no lugar, nenhuma coluna do esquema chega nela. Ela vale
    porque não depende de o esquema continuar assim amanhã — e porque o que ela
    troca é um `time zone ... not recognized` no meio de uma cópia de 180
    tabelas por um aviso que diz a tabela, a restrição e a coluna."""
    avisos: list[str] = []
    for nome, tabela in tabelas.items():
        _colunas_para_desambiguar(tabela, tabelas, avisos)
    assert avisos == [], f"coluna não textual exigindo sufixo: {avisos}"
