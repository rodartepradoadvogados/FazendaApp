"""Cascata de anexos do financeiro (B9) — `_excluir_anexos_do_lancamento` apaga
as linhas de `LancamentoAnexo` do lançamento, removendo o arquivo do Storage só
na última referência (mesma regra de `excluir_anexo`)."""
import tempfile

from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.models import ContaGerencial, LancamentoAnexo
from fazenda.api.routers.exclusoes import _excluir_anexos_do_lancamento


def _engine():
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_apaga_anexos_do_lancamento():
    engine = _engine()
    with Session(engine) as s:
        s.add(ContaGerencial(id=1, numero_lancamento="LC-2026-00001", fazenda_id=1, descricao="Nota"))
        s.add(LancamentoAnexo(id=1, numero_lancamento="LC-2026-00001", fazenda_id=1,
                              nome_arquivo="a.pdf", mime_type="application/pdf", tamanho_bytes=10))
        s.add(LancamentoAnexo(id=2, numero_lancamento="LC-2026-00001", fazenda_id=1,
                              nome_arquivo="b.pdf", mime_type="application/pdf", tamanho_bytes=10,
                              caminho_storage="nota/a.pdf"))
        s.commit()

    with Session(engine) as s:
        n = _excluir_anexos_do_lancamento(s, "LC-2026-00001", 1)
        s.commit()
        assert n == 2
        restantes = s.exec(select(LancamentoAnexo).where(LancamentoAnexo.numero_lancamento == "LC-2026-00001")).all()
        assert restantes == []


def test_nao_toca_anexo_de_outra_fazenda():
    engine = _engine()
    with Session(engine) as s:
        s.add(ContaGerencial(id=1, numero_lancamento="LC-2026-00001", fazenda_id=1, descricao="Nota"))
        s.add(LancamentoAnexo(id=1, numero_lancamento="LC-2026-00001", fazenda_id=2,
                              nome_arquivo="outra.pdf", mime_type="application/pdf", tamanho_bytes=10))
        s.commit()

    with Session(engine) as s:
        n = _excluir_anexos_do_lancamento(s, "LC-2026-00001", 1)
        s.commit()
        assert n == 0
        restantes = s.exec(select(LancamentoAnexo)).all()
        assert len(restantes) == 1  # o anexo da fazenda 2 fica


def test_sem_numero_lancamento_nao_faz_nada():
    engine = _engine()
    with Session(engine) as s:
        assert _excluir_anexos_do_lancamento(s, None, 1) == 0
