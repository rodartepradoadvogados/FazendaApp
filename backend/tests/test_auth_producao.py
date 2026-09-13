"""
_rodando_em_producao() decide se o app exige AUTH_SECRET de verdade no
startup (exigir_segredo_de_producao). Passou a checar RAILWAY_ENVIRONMENT_NAME
diretamente (a variável que o Railway injeta em todo serviço) em vez de
deduzir produção só pelo tipo de banco configurado — ver auth.py.
"""
from __future__ import annotations

from fazenda.auth import _rodando_em_producao


def test_railway_environment_name_production_e_producao(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("FAZENDA_TESTING", raising=False)
    assert _rodando_em_producao() is True


def test_railway_environment_name_staging_nao_e_producao():
    import os
    os.environ["RAILWAY_ENVIRONMENT_NAME"] = "staging"
    os.environ["DATABASE_URL"] = "postgresql://qualquer"
    os.environ.pop("FAZENDA_TESTING", None)
    try:
        assert _rodando_em_producao() is False
    finally:
        os.environ.pop("RAILWAY_ENVIRONMENT_NAME", None)
        os.environ.pop("DATABASE_URL", None)


def test_sem_railway_environment_name_cai_no_heuristico_antigo(monkeypatch):
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgres://qualquer")
    monkeypatch.delenv("FAZENDA_TESTING", raising=False)
    assert _rodando_em_producao() is True


def test_fazenda_testing_sempre_vence(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    monkeypatch.setenv("DATABASE_URL", "postgres://qualquer")
    monkeypatch.setenv("FAZENDA_TESTING", "1")
    assert _rodando_em_producao() is False
