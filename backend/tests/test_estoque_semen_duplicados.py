"""
Deduplicação de `EstoqueSemen` — relato do produtor (ago/2026): Henessy,
Heineken e Halle apareciam ao mesmo tempo como sêmen convencional (com doses
duplicadas em duas linhas) e como touro da fazenda (monta natural), porque a
compra pelo catálogo NAAB criava uma linha nova sempre que a linha existente
nunca tinha o NAAB preenchido (cadastro manual/CSV antigo) — ver o fallback
por nome em `compra_semen.registrar_compra` e os backfills abaixo em
`fazenda/api/routers/estoque.py`.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.models import CompraSemen, Estoque, EstoqueSemen, MovimentoEstoque, SeedFlag


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return eng


def _limpar_marca(session, chave):
    flag = session.get(SeedFlag, chave)
    if flag:
        session.delete(flag)
        session.commit()


class TestMesclarEstoqueSemen:
    def test_repontua_compras_e_preserva_metadados(self, engine):
        from fazenda.api.routers.estoque import mesclar_estoque_semen

        with Session(engine) as s:
            sobrevivente = EstoqueSemen(touro_nome="Henessy", tipo="convencional", doses=30, fazenda_id=1)
            perdedor = EstoqueSemen(touro_nome="Henessy", tipo="convencional", doses=20, naab="29HO22199", fazenda_id=1)
            s.add(sobrevivente); s.add(perdedor)
            s.commit()
            s.refresh(sobrevivente); s.refresh(perdedor)
            sobrevivente_id, perdedor_id = sobrevivente.id, perdedor.id
            s.add(CompraSemen(
                estoque_semen_id=perdedor_id, touro_nome="Henessy", origem="naab", tipo="convencional",
                doses=20, valor_unitario=50.0, vendedor="ABS", data_compra=date(2026, 8, 1), fazenda_id=1,
            ))
            s.commit()

        with Session(engine) as s:
            sobrevivente = s.get(EstoqueSemen, sobrevivente_id)
            perdedor = s.get(EstoqueSemen, perdedor_id)
            mesclar_estoque_semen(sobrevivente, perdedor, s)
            s.commit()

        with Session(engine) as s:
            assert s.get(EstoqueSemen, perdedor_id) is None  # perdedor removido
            sobrevivente = s.get(EstoqueSemen, sobrevivente_id)
            assert sobrevivente.doses == 30  # não soma — mantém o total do sobrevivente
            assert sobrevivente.naab == "29HO22199"  # metadado completado (sobrevivente não tinha)

            compra = s.exec(select(CompraSemen)).first()
            assert compra.estoque_semen_id == sobrevivente_id  # histórico de compra preservado

    def test_funde_item_espelhado_e_repontua_movimento(self, engine):
        from fazenda.api.routers.estoque import mesclar_estoque_semen, sincronizar_item_estoque_semen

        with Session(engine) as s:
            sobrevivente = EstoqueSemen(touro_nome="Heineken", tipo="convencional", doses=24, fazenda_id=1)
            perdedor = EstoqueSemen(touro_nome="Heineken", tipo="convencional", doses=6, fazenda_id=1)
            s.add(sobrevivente); s.add(perdedor)
            s.commit()
            s.refresh(sobrevivente); s.refresh(perdedor)
            sincronizar_item_estoque_semen(sobrevivente, s)
            sincronizar_item_estoque_semen(perdedor, s)
            s.commit()
            espelho_perdedor = s.exec(select(Estoque).where(Estoque.estoque_semen_id == perdedor.id)).first()
            s.add(MovimentoEstoque(
                nome_item="Sêmen — Heineken", movimento="Entrada de ajuste", quantidade=6, data_movimento=date(2026, 7, 1),
                estoque_id=espelho_perdedor.id, fazenda_id=1,
            ))
            s.commit()
            sobrevivente_id, perdedor_id = sobrevivente.id, perdedor.id
            espelho_sobrevivente_id = s.exec(select(Estoque).where(Estoque.estoque_semen_id == sobrevivente_id)).first().id
            espelho_perdedor_id = espelho_perdedor.id

        with Session(engine) as s:
            sobrevivente = s.get(EstoqueSemen, sobrevivente_id)
            perdedor = s.get(EstoqueSemen, perdedor_id)
            mesclar_estoque_semen(sobrevivente, perdedor, s)
            s.commit()

        with Session(engine) as s:
            assert s.get(Estoque, espelho_perdedor_id) is None  # espelho do perdedor removido
            mov = s.exec(select(MovimentoEstoque)).first()
            assert mov.estoque_id == espelho_sobrevivente_id  # movimento repontuado pro espelho sobrevivente


class TestBackfillDuplicadosMesmoTipo:
    CHAVE = "estoque_semen_backfill_duplicados_mesmo_tipo_202608"

    def test_funde_linhas_iguais_mantendo_a_de_mais_doses(self, engine):
        from fazenda.api.routers.estoque import backfill_estoque_semen_duplicados_mesmo_tipo

        with Session(engine) as s:
            _limpar_marca(s, self.CHAVE)
            s.add(EstoqueSemen(touro_nome="HENESSY", tipo="convencional", doses=20, fazenda_id=1))
            s.add(EstoqueSemen(touro_nome="Henessy", tipo="convencional", doses=30, fazenda_id=1))
            s.commit()

        with Session(engine) as s:
            backfill_estoque_semen_duplicados_mesmo_tipo(s)

        with Session(engine) as s:
            linhas = s.exec(select(EstoqueSemen).where(EstoqueSemen.fazenda_id == 1)).all()
            assert len(linhas) == 1
            assert linhas[0].doses == 30

    def test_nao_funde_tipos_diferentes(self, engine):
        from fazenda.api.routers.estoque import backfill_estoque_semen_duplicados_mesmo_tipo

        with Session(engine) as s:
            _limpar_marca(s, self.CHAVE)
            s.add(EstoqueSemen(touro_nome="Halle", tipo="convencional", doses=20, fazenda_id=1))
            s.add(EstoqueSemen(touro_nome="Halle", tipo="sexado", doses=10, fazenda_id=1))
            s.commit()

        with Session(engine) as s:
            backfill_estoque_semen_duplicados_mesmo_tipo(s)

        with Session(engine) as s:
            linhas = s.exec(select(EstoqueSemen).where(EstoqueSemen.fazenda_id == 1)).all()
            assert len(linhas) == 2

    def test_nao_funde_entre_fazendas_diferentes(self, engine):
        from fazenda.api.routers.estoque import backfill_estoque_semen_duplicados_mesmo_tipo

        with Session(engine) as s:
            _limpar_marca(s, self.CHAVE)
            s.add(EstoqueSemen(touro_nome="Halle", tipo="convencional", doses=20, fazenda_id=1))
            s.add(EstoqueSemen(touro_nome="Halle", tipo="convencional", doses=30, fazenda_id=2))
            s.commit()

        with Session(engine) as s:
            backfill_estoque_semen_duplicados_mesmo_tipo(s)

        with Session(engine) as s:
            assert len(s.exec(select(EstoqueSemen).where(EstoqueSemen.fazenda_id == 1)).all()) == 1
            assert len(s.exec(select(EstoqueSemen).where(EstoqueSemen.fazenda_id == 2)).all()) == 1

    def test_roda_uma_unica_vez(self, engine):
        from fazenda.api.routers.estoque import backfill_estoque_semen_duplicados_mesmo_tipo

        with Session(engine) as s:
            _limpar_marca(s, self.CHAVE)
            s.add(EstoqueSemen(touro_nome="Repeticao", tipo="convencional", doses=5, fazenda_id=1))
            s.commit()
            backfill_estoque_semen_duplicados_mesmo_tipo(s)
            # Simula duplicidade nova depois do backfill já ter rodado.
            s.add(EstoqueSemen(touro_nome="Repeticao", tipo="convencional", doses=9, fazenda_id=1))
            s.commit()

        with Session(engine) as s:
            backfill_estoque_semen_duplicados_mesmo_tipo(s)  # não roda de novo

        with Session(engine) as s:
            linhas = s.exec(select(EstoqueSemen).where(EstoqueSemen.touro_nome == "Repeticao")).all()
            assert len(linhas) == 2  # continua duplicado — backfill já marcado como feito


class TestBackfillFazendaParaConvencionalNomeados:
    CHAVE = "estoque_semen_backfill_fazenda_para_convencional_nomeados_202608"

    def test_funde_henessy_fazenda_no_convencional_da_mesma_fazenda(self, engine):
        from fazenda.api.routers.estoque import backfill_estoque_semen_fazenda_para_convencional_nomeados

        with Session(engine) as s:
            _limpar_marca(s, self.CHAVE)
            s.add(EstoqueSemen(touro_nome="Henessy", tipo="fazenda", doses=0, fazenda_id=1))
            s.add(EstoqueSemen(touro_nome="Henessy", tipo="convencional", doses=30, fazenda_id=1))
            s.commit()

        with Session(engine) as s:
            backfill_estoque_semen_fazenda_para_convencional_nomeados(s)

        with Session(engine) as s:
            linhas = s.exec(select(EstoqueSemen).where(EstoqueSemen.fazenda_id == 1)).all()
            assert len(linhas) == 1
            assert linhas[0].tipo == "convencional"
            assert linhas[0].doses == 30

    def test_nao_mexe_em_nome_nao_listado(self, engine):
        from fazenda.api.routers.estoque import backfill_estoque_semen_fazenda_para_convencional_nomeados

        with Session(engine) as s:
            _limpar_marca(s, self.CHAVE)
            s.add(EstoqueSemen(touro_nome="Frederico", tipo="fazenda", doses=0, fazenda_id=1))
            s.add(EstoqueSemen(touro_nome="Frederico", tipo="convencional", doses=5, fazenda_id=1))
            s.commit()

        with Session(engine) as s:
            backfill_estoque_semen_fazenda_para_convencional_nomeados(s)

        with Session(engine) as s:
            linhas = s.exec(select(EstoqueSemen).where(EstoqueSemen.fazenda_id == 1)).all()
            assert len(linhas) == 2  # não listado — não mexe, mesmo com nomes coincidindo

    def test_nao_funde_entre_fazendas_diferentes(self, engine):
        """Touro "fazenda" de monta natural da Fazenda B chamado Heineken (nome
        popular, coincidência) não pode ser fundido por causa de um sêmen
        Heineken comprado pela Fazenda A — isolamento multi-tenant."""
        from fazenda.api.routers.estoque import backfill_estoque_semen_fazenda_para_convencional_nomeados

        with Session(engine) as s:
            _limpar_marca(s, self.CHAVE)
            s.add(EstoqueSemen(touro_nome="Heineken", tipo="convencional", doses=24, fazenda_id=1))
            s.add(EstoqueSemen(touro_nome="Heineken", tipo="fazenda", doses=0, fazenda_id=2))
            s.commit()

        with Session(engine) as s:
            backfill_estoque_semen_fazenda_para_convencional_nomeados(s)

        with Session(engine) as s:
            assert len(s.exec(select(EstoqueSemen).where(EstoqueSemen.fazenda_id == 1)).all()) == 1
            assert len(s.exec(select(EstoqueSemen).where(EstoqueSemen.fazenda_id == 2)).all()) == 1

    def test_nao_decide_com_mais_de_um_candidato_convencional(self, engine):
        """Ainda há duplicidade não resolvida no lado convencional (o backfill
        de dedup mesmo-tipo deveria rodar antes) — não decide sozinho qual
        fundir, para não escolher errado."""
        from fazenda.api.routers.estoque import backfill_estoque_semen_fazenda_para_convencional_nomeados

        with Session(engine) as s:
            _limpar_marca(s, self.CHAVE)
            s.add(EstoqueSemen(touro_nome="Halle", tipo="fazenda", doses=0, fazenda_id=1))
            s.add(EstoqueSemen(touro_nome="Halle", tipo="convencional", doses=20, fazenda_id=1))
            s.add(EstoqueSemen(touro_nome="Halle", tipo="sexado", doses=18, fazenda_id=1))
            s.commit()

        with Session(engine) as s:
            backfill_estoque_semen_fazenda_para_convencional_nomeados(s)

        with Session(engine) as s:
            linhas = s.exec(select(EstoqueSemen).where(EstoqueSemen.fazenda_id == 1)).all()
            assert len(linhas) == 3  # 2 candidatos (convencional + sexado) — não decide, não funde nada
