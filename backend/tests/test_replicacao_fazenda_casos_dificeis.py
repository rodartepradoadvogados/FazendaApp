"""
Casos difíceis do motor de replicação (fazenda/rules/replicacao_fazenda.py)
que não são o caminho principal coberto por test_replicacao_fazenda.py:

- `Animal.numero` é UNIQUE GLOBAL hoje (antes da migração da outra frente
  pra `UniqueConstraint(fazenda_id, numero)`) — confirma que a cópia não
  quebra com IntegrityError e que o número original fica rastreável.
- Autorreferência (CategoriaAlimento.categoria_pai_id) — hierarquia
  pai/filho remapeada corretamente na 2ª passada.
- Ciclo entre duas tabelas (Estoque <-> Alimento via alimento_id /
  estoque_preferido_id) — as duas pontas remapeadas sem laço infinito.
- Anexo com caminho no Supabase Storage: o valor original NUNCA é copiado
  tal como está (nunca aponta pro objeto real de produção).
"""
from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.models import Animal, Fazenda
from fazenda.models.alimentacao import Alimento, CategoriaAlimento
from fazenda.models.documentos import DocumentoArquivado
from fazenda.models.estoque import Estoque
from fazenda.rules.replicacao_fazenda import sincronizar_fazenda_teste_destrutivo


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser", eh_teste=False))
        s.add(Fazenda(id=2, nome="Fazenda Teste", eh_teste=True))
        s.commit()
    return eng


def test_animal_numero_unique_global_nao_quebra_a_copia(engine):
    with Session(engine) as s:
        s.add(Animal(numero="777", fazenda_id=1, sexo="F"))
        s.commit()

    with Session(engine) as s:
        resultado = sincronizar_fazenda_teste_destrutivo(s, origem_id=1, destino_id=2)
        s.commit()
    assert not any("IntegrityError" in a for a in resultado.avisos)  # não deveria nem chegar a mencionar

    with Session(engine) as s:
        original = s.exec(select(Animal).where(Animal.fazenda_id == 1)).one()
        copia = s.exec(select(Animal).where(Animal.fazenda_id == 2)).one()
        assert original.numero == "777"          # origem intocada
        assert copia.numero != original.numero    # mutado pra não colidir com a global unique de hoje
        assert "777" in copia.numero               # mas rastreável até o número original


def test_autorreferencia_categoria_alimento(engine):
    with Session(engine) as s:
        mae = CategoriaAlimento(nome="Volumoso", fazenda_id=1)
        s.add(mae)
        s.commit()
        s.refresh(mae)
        filha = CategoriaAlimento(nome="Silagem", fazenda_id=1, categoria_pai_id=mae.id)
        s.add(filha)
        s.commit()

    with Session(engine) as s:
        sincronizar_fazenda_teste_destrutivo(s, origem_id=1, destino_id=2)
        s.commit()

    with Session(engine) as s:
        mae_copia = s.exec(
            select(CategoriaAlimento).where(CategoriaAlimento.fazenda_id == 2, CategoriaAlimento.nome == "Volumoso")
        ).one()
        filha_copia = s.exec(
            select(CategoriaAlimento).where(CategoriaAlimento.fazenda_id == 2, CategoriaAlimento.nome == "Silagem")
        ).one()
        assert filha_copia.categoria_pai_id == mae_copia.id  # remapeado, não o id antigo da origem


def test_ciclo_estoque_alimento(engine):
    with Session(engine) as s:
        estoque = Estoque(fazenda_id=1, nome="Ração X")
        s.add(estoque)
        s.commit()
        s.refresh(estoque)

        alimento = Alimento(nome="Ração X", fazenda_id=1, estoque_preferido_id=estoque.id)
        s.add(alimento)
        s.commit()
        s.refresh(alimento)

        estoque.alimento_id = alimento.id
        s.add(estoque)
        s.commit()

    with Session(engine) as s:
        sincronizar_fazenda_teste_destrutivo(s, origem_id=1, destino_id=2)
        s.commit()

    with Session(engine) as s:
        estoque_copia = s.exec(select(Estoque).where(Estoque.fazenda_id == 2)).one()
        alimento_copia = s.exec(select(Alimento).where(Alimento.fazenda_id == 2)).one()
        assert estoque_copia.alimento_id == alimento_copia.id
        assert alimento_copia.estoque_preferido_id == estoque_copia.id


def test_anexo_nunca_aponta_pro_arquivo_real(engine):
    with Session(engine) as s:
        s.add(DocumentoArquivado(
            fazenda_id=1, categoria="nota_fiscal", nome_original="nf.pdf",
            caminho_storage="fazenda-1/nf-123.pdf", mime_type="application/pdf", tamanho_bytes=100,
        ))
        s.commit()

    with Session(engine) as s:
        resultado = sincronizar_fazenda_teste_destrutivo(s, origem_id=1, destino_id=2)
        s.commit()
    assert any("anexo" in a.lower() for a in resultado.avisos)  # aviso explícito de que o arquivo não foi copiado

    with Session(engine) as s:
        original = s.exec(select(DocumentoArquivado).where(DocumentoArquivado.fazenda_id == 1)).one()
        copia = s.exec(select(DocumentoArquivado).where(DocumentoArquivado.fazenda_id == 2)).one()
        assert original.caminho_storage == "fazenda-1/nf-123.pdf"  # origem intocada
        assert copia.caminho_storage != original.caminho_storage
        assert "nao_replicado" in copia.caminho_storage  # nunca aponta pro objeto real de produção
