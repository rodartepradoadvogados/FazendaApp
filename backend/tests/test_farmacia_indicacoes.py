"""
Catálogo de INDICAÇÕES da farmácia (`Doenca` + `IndicacaoTerapeutica`) e o
enriquecimento de bula das marcas comerciais (`farmacia_indicacoes_seed`) —
ver `rules/farmacia.seed_indicacoes`.
"""
from __future__ import annotations

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.models import Doenca, IndicacaoTerapeutica, MedicamentoComercial, PrincipioAtivo
from fazenda.rules.farmacia import bootstrap_farmacia, seed_farmacia, seed_indicacoes


def _engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return eng


class TestSeedIndicacoesIdempotente:
    def test_roda_duas_vezes_sem_duplicar(self):
        eng = _engine()
        with Session(eng) as s:
            seed_farmacia(s)
            seed_indicacoes(s)
            n_doencas = len(s.exec(select(Doenca)).all())
            n_indicacoes = len(s.exec(select(IndicacaoTerapeutica)).all())
            n_marcas = len(s.exec(select(MedicamentoComercial)).all())

            seed_indicacoes(s)

            assert len(s.exec(select(Doenca)).all()) == n_doencas
            assert len(s.exec(select(IndicacaoTerapeutica)).all()) == n_indicacoes
            assert len(s.exec(select(MedicamentoComercial)).all()) == n_marcas

    def test_bootstrap_completo_idempotente(self):
        eng = _engine()
        with Session(eng) as s:
            bootstrap_farmacia(s)
            bootstrap_farmacia(s)
            # 40 indicações do documento base, todas com vínculo.
            doencas = {d.nome for d in s.exec(select(Doenca)).all()}
            assert "Mastite" in doencas and "Cisto Ovariano" in doencas
            assert len(s.exec(select(IndicacaoTerapeutica)).all()) > 0


class TestPrioridadeEditadaSobrevive:
    def test_prioridade_ajustada_a_mao_nao_e_sobrescrita(self):
        eng = _engine()
        with Session(eng) as s:
            seed_farmacia(s)
            seed_indicacoes(s)

            mastite = s.exec(select(Doenca).where(Doenca.nome == "Mastite")).one()
            ceftiofur = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Ceftiofur")).one()
            vinculo = s.exec(
                select(IndicacaoTerapeutica).where(
                    IndicacaoTerapeutica.doenca_id == mastite.id,
                    IndicacaoTerapeutica.principio_ativo_id == ceftiofur.id,
                )
            ).one()
            assert vinculo.prioridade == 1  # valor original do documento base

            # Produtor reordena à mão.
            vinculo.prioridade = 9
            s.add(vinculo)
            s.commit()

            seed_indicacoes(s)  # roda de novo

            vinculo_depois = s.get(IndicacaoTerapeutica, vinculo.id)
            assert vinculo_depois.prioridade == 9, "seed não pode sobrescrever prioridade editada à mão"


class TestDoencasPreexistentesSaoSagradas:
    def test_seis_doencas_ja_semeadas_nao_duplicam_nem_renomeiam(self):
        eng = _engine()
        nomes_sagrados = [
            "Brucelose", "Clostridiose", "Leptospirose", "Diarreia Neonatal",
            "Pasteurelose e Paratifo dos Bezerros", "Tuberculose",
        ]
        with Session(eng) as s:
            seed_farmacia(s)  # cria os 6 nomes sagrados via PRINCIPIOS[*]["doenca"]
            ids_antes = {}
            for nome in nomes_sagrados:
                d = s.exec(select(Doenca).where(Doenca.nome == nome, Doenca.fazenda_id.is_(None))).one()
                ids_antes[nome] = d.id

            seed_indicacoes(s)  # documento de indicações também referencia os 6 nomes

            for nome in nomes_sagrados:
                encontrados = s.exec(select(Doenca).where(Doenca.nome == nome, Doenca.fazenda_id.is_(None))).all()
                assert len(encontrados) == 1, f"'{nome}' foi duplicada"
                assert encontrados[0].id == ids_antes[nome], f"'{nome}' trocou de id (recriada em vez de reaproveitada)"
                assert encontrados[0].nome == nome, "nome sagrado não pode ser alterado"

            # Cada uma ganhou o vínculo de indicação terapêutica do documento base.
            leptospirose = s.exec(select(Doenca).where(Doenca.nome == "Leptospirose", Doenca.fazenda_id.is_(None))).one()
            vinculos = s.exec(
                select(IndicacaoTerapeutica).where(IndicacaoTerapeutica.doenca_id == leptospirose.id)
            ).all()
            assert len(vinculos) >= 1


class TestMarcaNaoSobrescritaAMao:
    def test_carencia_leite_preenchida_a_mao_nao_e_sobrescrita(self):
        eng = _engine()
        with Session(eng) as s:
            seed_farmacia(s)
            oxitetraciclina = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Oxitetraciclina (LA)")).one()
            marca = s.exec(
                select(MedicamentoComercial).where(
                    MedicamentoComercial.principio_ativo_id == oxitetraciclina.id,
                    MedicamentoComercial.nome_comercial == "Terramicina LA",
                )
            ).one()
            # No documento base, carência de leite da Terramicina LA é "a_preencher" (None).
            # O produtor preenche à mão com o valor real do lote dele.
            marca.carencia_leite_dias = 5
            s.add(marca)
            s.commit()

            seed_indicacoes(s)

            marca_depois = s.get(MedicamentoComercial, marca.id)
            assert marca_depois.carencia_leite_dias == 5, "seed não pode sobrescrever carência preenchida pelo produtor"


class TestStatusAPreencherViraNone:
    def test_marca_a_preencher_fica_none_nao_zero(self):
        eng = _engine()
        with Session(eng) as s:
            seed_farmacia(s)
            seed_indicacoes(s)

            penicilina = s.exec(
                select(PrincipioAtivo).where(PrincipioAtivo.nome == "Penicilina G (Procaína, Potássica e Benzatina)")
            ).one()
            agropen = s.exec(
                select(MedicamentoComercial).where(
                    MedicamentoComercial.principio_ativo_id == penicilina.id,
                    MedicamentoComercial.nome_comercial == "Agropen",
                )
            ).one()
            # status_dose="a_preencher" no documento base.
            assert agropen.dose_padrao is None
            assert agropen.dose_padrao != 0
            assert agropen.carencia_leite_dias is None
            assert agropen.carencia_carne_dias is None


class TestProibidoLactacao:
    def test_marca_proibida_em_lactacao_tem_carencia_leite_nula(self):
        eng = _engine()
        with Session(eng) as s:
            seed_farmacia(s)
            seed_indicacoes(s)

            florfenicol = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Florfenicol")).one()
            nuflor = s.exec(
                select(MedicamentoComercial).where(
                    MedicamentoComercial.principio_ativo_id == florfenicol.id,
                    MedicamentoComercial.nome_comercial == "Nuflor",
                )
            ).one()
            assert nuflor.proibido_lactacao is True
            assert nuflor.carencia_leite_dias is None

            # Confere que existe mais de uma marca proibida em lactação no catálogo inteiro.
            proibidas = s.exec(
                select(MedicamentoComercial).where(MedicamentoComercial.proibido_lactacao == True)  # noqa: E712
            ).all()
            assert len(proibidas) >= 5
            assert all(m.carencia_leite_dias is None for m in proibidas)


class TestErrosDeCatalogoNaoApagamMarca:
    def test_marcas_com_erro_de_catalogo_continuam_no_principio_original_com_alerta(self):
        eng = _engine()
        with Session(eng) as s:
            seed_farmacia(s)
            seed_indicacoes(s)

            b12 = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Cianocobalamina (B12)")).one()
            dexacito = s.exec(
                select(MedicamentoComercial).where(
                    MedicamentoComercial.principio_ativo_id == b12.id,
                    MedicamentoComercial.nome_comercial == "Dexacito",
                )
            ).first()
            assert dexacito is not None, "marca com erro de catálogo nunca pode ser apagada"
            assert dexacito.alerta_gestacao is True
            assert dexacito.alerta and "DEXAMETASONA" in dexacito.alerta

            ceftiofur = s.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == "Ceftiofur")).one()
            ubrolexin = s.exec(
                select(MedicamentoComercial).where(
                    MedicamentoComercial.principio_ativo_id == ceftiofur.id,
                    MedicamentoComercial.nome_comercial == "Ubrolexin",
                )
            ).first()
            assert ubrolexin is not None
            assert ubrolexin.alerta and "cefalexina" in ubrolexin.alerta.lower()
