"""B9 restante: fatura fechada/paga bloqueia; documento arquivado é desvinculado."""
import tempfile
from datetime import date

from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import ContaGerencial, DocumentoArquivado, FaturaFornecedor
from fazenda.api.routers.exclusoes import _alvos, _desvincular_documentos_dos_alvos
from fazenda.rules.exclusao_impacto import ExclusaoBloqueada


def _engine():
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_fatura_fechada_bloqueia():
    engine = _engine()
    with Session(engine) as s:
        s.add(FaturaFornecedor(id=1, fazenda_id=1, fornecedor="Fornecedor", rotulo="Fatura 1",
                               data_abertura=date(2026, 1, 1), status="fechada"))
        s.add(ContaGerencial(id=1, numero_lancamento="LC-2026-00001", fazenda_id=1, descricao="Nota", fatura_id=1))
        s.commit()

    with Session(engine) as s:
        try:
            _alvos("financeiro", "1", s, fazenda_id=1)
            assert False, "deveria bloquear"
        except ExclusaoBloqueada:
            pass


def test_fatura_aberta_nao_bloqueia():
    engine = _engine()
    with Session(engine) as s:
        s.add(FaturaFornecedor(id=1, fazenda_id=1, fornecedor="Fornecedor", rotulo="Fatura 1",
                               data_abertura=date(2026, 1, 1), status="aberta"))
        s.add(ContaGerencial(id=1, numero_lancamento="LC-2026-00001", fazenda_id=1, descricao="Nota", fatura_id=1))
        s.commit()

    with Session(engine) as s:
        itens, alvos = _alvos("financeiro", "1", s, fazenda_id=1)
        assert len(alvos) >= 1


def test_documento_arquivado_desvincula():
    engine = _engine()
    with Session(engine) as s:
        s.add(ContaGerencial(id=1, numero_lancamento="LC-2026-00001", fazenda_id=1, descricao="Nota"))
        s.add(DocumentoArquivado(id=1, fazenda_id=1, categoria="Nota fiscal", nome_original="nf.pdf",
                                 caminho_storage="nf.pdf", mime_type="application/pdf", tamanho_bytes=10,
                                 numero_lancamento="LC-2026-00001"))
        s.commit()

    with Session(engine) as s:
        conta = s.get(ContaGerencial, 1)
        n = _desvincular_documentos_dos_alvos(s, [conta], 1)
        s.commit()
        assert n == 1
        doc = s.get(DocumentoArquivado, 1)
        assert doc.numero_lancamento is None
