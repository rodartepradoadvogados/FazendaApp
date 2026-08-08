"""Etapa 4 — monta as linhas prontas de necessidade × fornecido × balanço
para a UI, a partir dos resultados de cada bloco do motor.

Para os nutrientes em que o NASEM não define uma "exigência" formal em
termos dietéticos (composição-alvo, e não um requerimento líquido — FDN,
FDN de volumoso, PDR, PNDR, PB, Amido, EE/AG, DCAD, custo), a linha de
balanço mostra o fornecido com exigência=0: são linhas informativas de
composição da dieta formulada, não restrições nutricionais com um "não
atendido" possível dentro do escopo da Fase 1.
"""
from __future__ import annotations

from typing import Literal

from .alimentos import ConcentracoesDieta
from .digestao import IngestoesDieta
from .energia import ResultadoEnergia
from .minerais import ResultadoMinerais
from .proteina import ResultadoProteina
from .tipos import LinhaBalanco

Situacao = Literal["adequado", "deficit", "excesso"]

_TOLERANCIA_RELATIVA_EXCESSO = 0.15


def _situacao(balanco: float, exigencia: float) -> Situacao:
    if exigencia == 0:
        return "adequado"
    if balanco < 0:
        return "deficit"
    if balanco > exigencia * _TOLERANCIA_RELATIVA_EXCESSO:
        return "excesso"
    return "adequado"


def _linha(
    nutriente: str, unidade: str, exigencia: float, fornecido: float
) -> LinhaBalanco:
    balanco = fornecido - exigencia
    return LinhaBalanco(
        nutriente=nutriente,
        unidade=unidade,
        exigencia=exigencia,
        fornecido=fornecido,
        balanco=balanco,
        situacao=_situacao(balanco, exigencia),
    )


def montar_balanco(
    *,
    dieta: ConcentracoesDieta,
    ingestoes: IngestoesDieta,
    energia: ResultadoEnergia,
    proteina: ResultadoProteina,
    minerais: ResultadoMinerais,
    custo_dieta_dia: float,
) -> list[LinhaBalanco]:
    linhas = [
        _linha("CMS", "kg/d", ingestoes.cms_kg_dia, ingestoes.cms_kg_dia),
        _linha("ELl (energia líquida de lactação)", "Mcal/d", energia.nel_uso_total_mcal, energia.energia_liquida_mcal),
        _linha("EM (energia metabolizável)", "Mcal/d", energia.em_uso_total_mcal, energia.energia_metabolizavel_mcal),
        _linha("PB (proteína bruta)", "% MS", 0.0, dieta.pb_pct),
        _linha("PDR (proteína degradável no rúmen)", "% MS", 0.0, dieta.rdp_pct_dm),
        _linha("PNDR (proteína não degradável no rúmen)", "% MS", 0.0, dieta.rup_pct_dm),
        _linha("PM (proteína metabolizável)", "g/d", proteina.exigencias.total_g, proteina.suprimento.pm_fornecida_g),
        _linha("FDN (fibra em detergente neutro)", "% MS", 0.0, dieta.fdn_pct),
        _linha("FDN de volumoso", "% MS", 0.0, dieta.forragem_ndf_pct_dm),
        _linha("Amido", "% MS", 0.0, dieta.amido_pct),
        _linha("EE/AG (extrato etéreo / ácidos graxos)", "% MS", 0.0, dieta.ag_pct),
        _linha("Ca (cálcio, absorvido)", "g/d", minerais.calcio.exigencia, minerais.calcio.fornecido_absorvido),
        _linha("P (fósforo, absorvido)", "g/d", minerais.fosforo.exigencia, minerais.fosforo.fornecido_absorvido),
        _linha("Mg (magnésio, absorvido)", "g/d", minerais.magnesio.exigencia, minerais.magnesio.fornecido_absorvido),
        _linha("K (potássio, absorvido)", "g/d", minerais.potassio.exigencia, minerais.potassio.fornecido_absorvido),
        _linha("Na (sódio, absorvido)", "g/d", minerais.sodio.exigencia, minerais.sodio.fornecido_absorvido),
        _linha("Cl (cloro, absorvido)", "g/d", minerais.cloro.exigencia, minerais.cloro.fornecido_absorvido),
        _linha("S (enxofre)", "g/d", minerais.enxofre.exigencia, minerais.enxofre.fornecido_absorvido),
        _linha("DCAD", "meq/kg MS", 0.0, minerais.dcad_meq_kg),
        _linha("Custo da dieta", "R$/d", 0.0, custo_dieta_dia),
    ]
    return linhas


__all__ = ["montar_balanco"]
