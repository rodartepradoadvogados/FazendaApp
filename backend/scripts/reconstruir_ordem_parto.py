"""
Reconstrói `ControleLeiteiro.ordem_parto` a partir do histórico de partos.

POR QUE ISTO EXISTE
-------------------
O campo nunca foi gravado por nenhuma das quatro vias de entrada do controle
leiteiro. A tela de Produção cai num atalho — a contagem TOTAL de partos do
animal, aplicada a todos os controles dele —, então uma vaca hoje de 5ª cria
aparece com "5ª" até nos controles de quando era primípara.

Isso não é cosmético. O equivalente maduro é, por definição, ajuste por idade e
ordem de parto: com o histórico rotulado errado, a produção baixa da primeira
cria entra na média das maduras e o indicador passa a subestimar justamente o
quanto uma novilha ainda tem a crescer — o oposto do que ele existe para
mostrar.

POR QUE SCRIPT E NÃO MIGRAÇÃO
-----------------------------
Migração roda sozinha no deploy, sem ninguém olhando. Isto é reescrita de dado
histórico, e merece alguém olhando: o padrão aqui é RELATAR primeiro e só
gravar com `--gravar` explícito. Sem essa opção, o script não escreve nada.

COMO USAR
---------
    python -m scripts.reconstruir_ordem_parto              # só relata
    python -m scripts.reconstruir_ordem_parto --exemplos 40
    python -m scripts.reconstruir_ordem_parto --fazenda 2
    python -m scripts.reconstruir_ordem_parto --gravar     # aí sim escreve

⚠ Lê `DATABASE_URL` do ambiente. Confira para onde ela aponta antes de usar
`--gravar`.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlmodel import Session, select  # noqa: E402

from fazenda.database import engine  # noqa: E402
from fazenda.models import Animal, ControleLeiteiro, Parto  # noqa: E402
from fazenda.rules.ordem_parto_historica import (  # noqa: E402
    PartoRef,
    ordem_parto_na_data,
    ordem_parto_pelo_atalho_atual,
)


def _meses(inicio, fim) -> int | None:
    """Idade em meses inteiros. Aproximação por 30,44 dias seria pior: o padrão
    de idade ao parto é lido em meses de calendário."""
    if inicio is None or fim is None:
        return None
    m = (fim.year - inicio.year) * 12 + (fim.month - inicio.month)
    if fim.day < inicio.day:
        m -= 1
    return m if m >= 0 else None


def _faixa(m: int | None) -> str:
    if m is None:
        return "sem idade"
    for lim in (24, 30, 36, 48, 60, 72, 86):
        if m < lim:
            return f"< {lim}"
    return ">= 86"


def levantar(session: Session, fazenda_id: int | None, exemplos: int) -> dict:
    q_partos = select(Parto)
    q_cl = select(ControleLeiteiro)
    q_an = select(Animal)
    if fazenda_id is not None:
        q_partos = q_partos.where(Parto.fazenda_id == fazenda_id)
        q_cl = q_cl.where(ControleLeiteiro.fazenda_id == fazenda_id)
        q_an = q_an.where(Animal.fazenda_id == fazenda_id)

    partos = session.exec(q_partos).all()
    controles = session.exec(q_cl).all()
    nascimento = {a.numero: getattr(a, "data_nasc", None) for a in session.exec(q_an).all()}

    por_animal: dict[str, list[PartoRef]] = defaultdict(list)
    for p in partos:
        por_animal[p.numero_matriz].append(PartoRef(p.data_parto, p.ordem_parto))

    # Lactações por ordem de parto — o denominador de cada classe do fator.
    lactacoes_por_ordem = Counter(p.ordem_parto for p in partos if p.ordem_parto is not None)

    # Idade ao parto: é assim que o padrão internacional define maturidade
    # (faixa de 61 a 86 meses, por raça), não pelo número da cria.
    idades = Counter()
    for p in partos:
        idades[_faixa(_meses(nascimento.get(p.numero_matriz), p.data_parto))] += 1

    muda = 0
    vira_desconhecido = 0
    amostra = []
    for c in controles:
        ps = por_animal.get(c.numero_matriz, [])
        hoje = c.ordem_parto or ordem_parto_pelo_atalho_atual(ps)
        correta = ordem_parto_na_data(ps, c.data_controle)
        if correta == hoje:
            continue
        muda += 1
        if correta is None:
            vira_desconhecido += 1
        if len(amostra) < exemplos:
            amostra.append((c.numero_matriz, c.data_controle, hoje, correta))

    datas_p = [p.data_parto for p in partos if p.data_parto]
    datas_c = [c.data_controle for c in controles if c.data_controle]
    return {
        "partos": len(partos),
        "controles": len(controles),
        "animais_com_parto": len(por_animal),
        "lactacoes_por_ordem": dict(sorted(lactacoes_por_ordem.items())),
        "idade_ao_parto": dict(idades),
        "muda": muda,
        "vira_desconhecido": vira_desconhecido,
        "amostra": amostra,
        "periodo_partos": (min(datas_p), max(datas_p)) if datas_p else None,
        "periodo_controles": (min(datas_c), max(datas_c)) if datas_c else None,
    }


def imprimir(r: dict) -> None:
    print("=" * 72)
    print("RECONSTRUÇÃO DA ORDEM DE PARTO — RELATÓRIO (nada foi gravado)")
    print("=" * 72)
    print(f"partos: {r['partos']}   controles leiteiros: {r['controles']}   "
          f"animais com parto: {r['animais_com_parto']}")
    if r["periodo_partos"]:
        print(f"partos de {r['periodo_partos'][0]} a {r['periodo_partos'][1]}")
    if r["periodo_controles"]:
        print(f"controles de {r['periodo_controles'][0]} a {r['periodo_controles'][1]}")

    print("\n-- Lactações por ordem de parto (denominador de cada classe do fator)")
    for ordem, n in r["lactacoes_por_ordem"].items():
        aviso = "  <-- base pequena" if n < 20 else ("  (base modesta)" if n < 50 else "")
        print(f"   {ordem}ª cria: {n}{aviso}")

    print("\n-- Idade ao parto (o padrão internacional define maturidade por IDADE,")
    print("   faixa de 61 a 86 meses por raça — não pelo número da cria)")
    for faixa in ("sem idade", "< 24", "< 30", "< 36", "< 48", "< 60", "< 72", "< 86", ">= 86"):
        if faixa in r["idade_ao_parto"]:
            print(f"   {faixa:>10} meses: {r['idade_ao_parto'][faixa]}")

    pct = (100 * r["muda"] / r["controles"]) if r["controles"] else 0
    print(f"\n-- Impacto: {r['muda']} de {r['controles']} controles mudariam de ordem ({pct:.1f}%)")
    print(f"   destes, {r['vira_desconhecido']} passariam a NÃO TER ordem — hoje mostram um")
    print("   número derivado que não corresponde a nada (controle anterior ao")
    print("   primeiro parto registrado, ou parto sem ordem gravada)")

    if r["amostra"]:
        print("\n-- Exemplos concretos")
        print(f"   {'vaca':>8}  {'data':>12}  {'hoje':>6}  {'correta':>8}")
        for numero, data, hoje, correta in r["amostra"]:
            print(f"   {numero:>8}  {str(data):>12}  {str(hoje):>6}  {str(correta):>8}")
    print("\nPara gravar: rode de novo com --gravar")


def gravar(session: Session, fazenda_id: int | None) -> int:
    q_partos = select(Parto)
    q_cl = select(ControleLeiteiro)
    if fazenda_id is not None:
        q_partos = q_partos.where(Parto.fazenda_id == fazenda_id)
        q_cl = q_cl.where(ControleLeiteiro.fazenda_id == fazenda_id)
    por_animal: dict[str, list[PartoRef]] = defaultdict(list)
    for p in session.exec(q_partos).all():
        por_animal[p.numero_matriz].append(PartoRef(p.data_parto, p.ordem_parto))

    n = 0
    for c in session.exec(q_cl).all():
        correta = ordem_parto_na_data(por_animal.get(c.numero_matriz, []), c.data_controle)
        # Só grava quando SABE. Deixar nulo é melhor que gravar o palpite que
        # a tela já dava: nulo é honesto, o palpite parece dado.
        if correta is not None and c.ordem_parto != correta:
            c.ordem_parto = correta
            session.add(c)
            n += 1
    session.commit()
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gravar", action="store_true", help="grava de fato (sem isto, só relata)")
    ap.add_argument("--fazenda", type=int, default=None, help="restringe a uma fazenda")
    ap.add_argument("--exemplos", type=int, default=20, help="quantos exemplos concretos mostrar")
    args = ap.parse_args()

    with Session(engine) as s:
        if args.gravar:
            n = gravar(s, args.fazenda)
            print(f"gravados {n} controles com a ordem de parto correta")
        else:
            imprimir(levantar(s, args.fazenda, args.exemplos))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
