"""
Script de smoke test — carrega os CSV reais do Ideagri e verifica os parsers.
Execução: python -m backend.tests.smoke_test (da raiz do projeto)
"""
import sys
from pathlib import Path

# Adiciona o backend ao path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from fazenda.parsers.geral import parse_geral
from fazenda.parsers.reprodutivo import parse_reprodutivo
from fazenda.parsers.conta_gerencial import parse_conta_gerencial
from fazenda.parsers.estoque import parse_estoque

BASE = Path(__file__).parent.parent.parent  # c:\FazendaApp


def test_geral():
    path = BASE / "GERAL.csv"
    content = path.read_bytes()
    animais = parse_geral(content)
    print(f"✅ GERAL: {len(animais)} animais parseados")

    grupos = {}
    for a in animais:
        g = a.grupo_primario or "(sem grupo)"
        grupos[g] = grupos.get(g, 0) + 1

    print("   Distribuição por grupo:")
    for g, n in sorted(grupos.items()):
        print(f"     {g}: {n}")

    sit_reps = {}
    for a in animais:
        s = a.sit_rep or "(sem sit. rep.)"
        sit_reps[s] = sit_reps.get(s, 0) + 1
    print("   Sit. rep.:", sit_reps)
    return animais


def test_reprodutivo():
    path = BASE / "1 - Consulta_SQL_Dados_Reprodutivos_e_Produtivos_Versao_8.csv"
    content = path.read_bytes()
    servicos, partos = parse_reprodutivo(content)
    print(f"✅ REPRODUTIVO: {len(servicos)} serviços, {len(partos)} partos")

    # Conta últimas ocorrências
    ult_ocorr = [s for s in servicos if s.ult_ocorrencia == 1]
    print(f"   Últimas ocorrências (ult_ocorr=1): {len(ult_ocorr)}")

    diagnosticos = {}
    for s in ult_ocorr:
        d = (s.diagnostico or "(aberto)").upper()
        diagnosticos[d] = diagnosticos.get(d, 0) + 1
    print("   Diagnósticos (últimas ocorrências):", diagnosticos)
    return servicos, partos


def test_conta_gerencial():
    path = BASE / "CONTA_GERENCIAL.csv"
    content = path.read_bytes()
    contas = parse_conta_gerencial(content)
    print(f"✅ CONTA_GERENCIAL: {len(contas)} movimentações")
    receitas = sum(c.valor_total or 0 for c in contas if c.tipo == "receita")
    despesas = sum(c.valor_total or 0 for c in contas if c.tipo == "despesa")
    print(f"   Receitas: R$ {receitas:,.2f}  |  Despesas: R$ {despesas:,.2f}")
    return contas


def test_estoque():
    path = BASE / "ESTOQUE.csv"
    content = path.read_bytes()
    items = parse_estoque(content)
    print(f"✅ ESTOQUE: {len(items)} itens")
    hormonios = [i for i in items if i.categoria and "hormônio" in i.categoria.lower() or "hormone" in (i.categoria or "").lower()]
    print(f"   Hormônios/veterinários: {len(hormonios)}")
    for h in hormonios:
        print(f"     {h.nome}: {h.quantidade} {h.unidade or ''} — abaixo: {h.abaixo_minimo}")
    return items


if __name__ == "__main__":
    print("=" * 60)
    print("SMOKE TEST — Parsers CSV Ideagri")
    print("=" * 60)
    animais = test_geral()
    print()
    servicos, partos = test_reprodutivo()
    print()
    contas = test_conta_gerencial()
    print()
    items = test_estoque()
    print()
    print("✅ Todos os parsers OK!")
