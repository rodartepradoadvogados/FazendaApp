"""B9 (fim): aviso de pedido/patrimônio ligado; comissão de corretagem apagada."""
import tempfile
from datetime import date

from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import ComissaoCorretagem, ContaGerencial
from fazenda.api.routers.exclusoes import _descrever_reversoes, _excluir_comissao_dos_alvos


def _engine():
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_aviso_patrimonio_ligado():
    engine = _engine()
    with Session(engine) as s:
        s.add(ContaGerencial(id=1, numero_lancamento="LC-2026-00001", fazenda_id=1, descricao="Nota", patrimonio_id=1))
        s.commit()
    with Session(engine) as s:
        conta = s.get(ContaGerencial, 1)
        reverter, avisos = _descrever_reversoes(s, [conta], 1)
        assert any(a.titulo == "Patrimônio ligado" for a in avisos)


def test_exclui_comissao_de_corretagem():
    engine = _engine()
    with Session(engine) as s:
        s.add(ContaGerencial(id=1, numero_lancamento="LC-2026-00099", fazenda_id=1, descricao="Comissão"))
        s.add(ComissaoCorretagem(id=1, fazenda_id=1, origem_tipo="venda_animal",
                                 numero_lancamento="LC-2026-00088", corretor_nome="Corretor",
                                 valor_comissao=100.0, forma="separado",
                                 numero_lancamento_comissao="LC-2026-00099"))
        s.commit()
    with Session(engine) as s:
        conta = s.get(ContaGerencial, 1)
        n = _excluir_comissao_dos_alvos(s, [conta], 1)
        s.commit()
        assert n == 1
        assert s.get(ComissaoCorretagem, 1) is None