"""Cascata de caixa/folha do financeiro (B9) — `_dependentes_financeiros` devolve
CaixaMovimento/CaixaTimeMovimento/FolhaRubrica que referenciam as contas, para
serem apagados antes da conta (FK). ExtratoLinha continua bloqueio."""
import tempfile
from datetime import date

from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import CaixaMovimento, ContaGerencial, Pessoa
from fazenda.api.routers.exclusoes import _dependentes_financeiros, _bloquear_conta_referenciada


def _engine():
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_dependentes_financeiros_devolve_caixa():
    engine = _engine()
    with Session(engine) as s:
        s.add(Pessoa(id=1, nome="Fulano", tipo="Funcionário"))
        s.add(ContaGerencial(id=1, numero_lancamento="LC-2026-00001", fazenda_id=1, descricao="Nota"))
        s.add(CaixaMovimento(id=1, fazenda_id=1, pessoa_id=1, tipo="comissao", valor=10.0,
                             data=date(2026, 1, 1), motivo="x", lancamento_id=1))
        s.commit()

    with Session(engine) as s:
        dep = _dependentes_financeiros(s, [1])
        tipos = {type(d).__name__ for d in dep}
        assert "CaixaMovimento" in tipos


def test_bloqueio_agora_so_extrato():
    engine = _engine()
    with Session(engine) as s:
        s.add(Pessoa(id=1, nome="Fulano", tipo="Funcionário"))
        s.add(ContaGerencial(id=1, numero_lancamento="LC-2026-00001", fazenda_id=1, descricao="Nota"))
        # caixa NÃO bloqueia mais (vira cascata)
        s.add(CaixaMovimento(id=1, fazenda_id=1, pessoa_id=1, tipo="comissao", valor=10.0,
                             data=date(2026, 1, 1), motivo="x", lancamento_id=1))
        s.commit()

    with Session(engine) as s:
        # não deve levantar ExclusaoBloqueada por causa do caixa
        _bloquear_conta_referenciada(s, [s.get(ContaGerencial, 1)])