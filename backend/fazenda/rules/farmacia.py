"""
Farmácia — a hierarquia do estoque de medicamentos/hormônios/vacinas é o
PRINCÍPIO ATIVO (ou, para biológicos, a doença/antígeno). Este módulo faz:

  • seed idempotente do catálogo (princípios + marcas comerciais) — farmacia_seed;
  • compatibilização sem perda: vincula os itens de estoque já existentes ao
    princípio certo (por texto ou por marca), criando o que faltar;
  • unificação de volumes: soma o saldo das apresentações (frascos de tamanhos
    diferentes) na unidade-base do princípio;
  • mínimo por "apresentações primárias" (frações de frasco somadas < mínimo).

Nada é apagado: o histórico (Sanidade, MovimentoEstoque, compras) referencia os
itens por nome e segue intacto; aqui só ACRESCENTAMOS vínculos e catálogo.
"""
from __future__ import annotations

import re
import unicodedata

from sqlmodel import Session, select

from fazenda.models import Doenca, Estoque, MedicamentoComercial, PrincipioAtivo, SeedFlag
from fazenda.rules.farmacia_seed import PRINCIPIOS

# Conversões entre unidades do mesmo eixo (fator para a unidade-base).
_PARA_BASE = {
    ("l", "ml"): 1000.0, ("ml", "ml"): 1.0,
    ("ml", "l"): 0.001, ("l", "l"): 1.0,
    ("kg", "g"): 1000.0, ("g", "g"): 1.0,
    ("g", "kg"): 0.001, ("kg", "kg"): 1.0,
    ("dose", "dose"): 1.0, ("unidade", "unidade"): 1.0,
    ("seringa", "unidade"): 1.0, ("dispositivo", "unidade"): 1.0,
}


def converter(qtd: float, de: str | None, para: str | None) -> float | None:
    """Converte `qtd` da unidade `de` para a unidade `para`. None se as unidades
    forem incompatíveis (eixos diferentes) — o chamador decide o que fazer."""
    if qtd is None:
        return None
    d = (de or "").strip().lower()
    p = (para or "").strip().lower()
    if not d or not p or d == p:
        return qtd
    fator = _PARA_BASE.get((d, p))
    return qtd * fator if fator is not None else None


def _norm(s: str | None) -> str:
    """Normaliza para casar nomes: sem acento, minúsculo, sem pontuação/espaços extras."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


# ── Seed do catálogo ────────────────────────────────────────────────────────
def seed_farmacia(session: Session) -> None:
    """Cria/enriquece os princípios ativos e as marcas comerciais do documento
    base. Idempotente: só CRIA o que falta e só PREENCHE campos vazios de
    princípios já existentes (não sobrescreve edição do usuário)."""
    for p in PRINCIPIOS:
        doenca_id = None
        if p.get("doenca"):
            doenca = session.exec(select(Doenca).where(Doenca.nome == p["doenca"])).first()
            if not doenca:
                doenca = Doenca(nome=p["doenca"])
                session.add(doenca)
                session.commit()
                session.refresh(doenca)
            doenca_id = doenca.id

        pa = session.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == p["nome"])).first()
        if not pa:
            pa = PrincipioAtivo(nome=p["nome"])
            session.add(pa)
        # Preenche só o que estiver vazio (respeita edições do usuário).
        pa.categoria_software = pa.categoria_software or p.get("categoria_software")
        pa.uso_principal = pa.uso_principal or p.get("uso_principal")
        pa.justificativa = pa.justificativa or p.get("justificativa")
        pa.unidade_base = pa.unidade_base or p.get("unidade_base")
        pa.unidade_apresentacao = pa.unidade_apresentacao or p.get("unidade_apresentacao")
        pa.eh_biologico = pa.eh_biologico or bool(p.get("eh_biologico"))
        if pa.doenca_id is None:
            pa.doenca_id = doenca_id
        if pa.estoque_minimo_apresentacoes is None:
            pa.estoque_minimo_apresentacoes = 1.0
        session.add(pa)
        session.commit()
        session.refresh(pa)

        # Marcas comerciais (tabela filha) — cria as que faltam.
        for nome_comercial, laboratorio in p.get("marcas", []):
            existe = session.exec(
                select(MedicamentoComercial).where(
                    MedicamentoComercial.principio_ativo_id == pa.id,
                    MedicamentoComercial.nome_comercial == nome_comercial,
                )
            ).first()
            if not existe:
                session.add(MedicamentoComercial(
                    principio_ativo_id=pa.id, nome_comercial=nome_comercial, laboratorio=laboratorio,
                ))
        session.commit()


# ── Compatibilização do estoque já existente ────────────────────────────────
def compatibilizar_estoque(session: Session) -> dict:
    """Vincula cada item de Estoque (sem princípio) ao princípio ativo certo,
    sem apagar nada. Ordem de tentativa:
      1) texto `principio_ativo` do item bate com um princípio do catálogo;
      2) o `nome` do item contém uma marca comercial conhecida → seu princípio;
      3) tem texto `principio_ativo` sem correspondência → cria o princípio e vincula.
    Retorna um resumo {vinculados, criados}."""
    principios = session.exec(select(PrincipioAtivo)).all()
    por_nome = {_norm(p.nome): p for p in principios}
    marcas = session.exec(select(MedicamentoComercial)).all()
    por_marca = {_norm(m.nome_comercial): m for m in marcas}

    vinculados = 0
    criados = 0
    for item in session.exec(select(Estoque)).all():
        if item.principio_ativo_id is not None:
            continue
        # Só faz sentido para medicamentos — pula itens de alimentação/insumos
        # que não têm nem texto de princípio nem cara de medicamento.
        alvo_pa: PrincipioAtivo | None = None
        alvo_marca: MedicamentoComercial | None = None

        txt = _norm(item.principio_ativo)
        if txt and txt in por_nome:
            alvo_pa = por_nome[txt]

        if alvo_pa is None:
            nome_norm = _norm(item.nome)
            for marca_norm, marca in por_marca.items():
                if marca_norm and marca_norm in nome_norm:
                    alvo_marca = marca
                    alvo_pa = next((p for p in principios if p.id == marca.principio_ativo_id), None)
                    break

        if alvo_pa is None and txt:
            # Tem princípio ativo em texto mas fora do catálogo → cria e vincula.
            novo = PrincipioAtivo(nome=item.principio_ativo.strip(), unidade_base=item.unidade)
            session.add(novo)
            session.commit()
            session.refresh(novo)
            principios.append(novo)
            por_nome[txt] = novo
            alvo_pa = novo
            criados += 1

        if alvo_pa is not None:
            item.principio_ativo_id = alvo_pa.id
            if alvo_marca is not None:
                item.medicamento_comercial_id = alvo_marca.id
                if not item.laboratorio:
                    item.laboratorio = alvo_marca.laboratorio
            session.add(item)
            vinculados += 1
    session.commit()
    return {"vinculados": vinculados, "criados": criados}


def bootstrap_farmacia(session: Session) -> None:
    """Garante o catálogo de princípios ativos/marcas e compatibiliza o estoque.

    O SEED DO CATÁLOGO roda em TODO start: é add-missing e idempotente (só cria o
    que falta, preenche apenas campos vazios), então novos princípios do documento
    base entram sem depender de flag de versão — corrige bancos que semearam antes
    do catálogo estar completo. A compatibilização do estoque legado roda uma vez."""
    seed_farmacia(session)
    chave = "farmacia_compat_v2"
    if not session.get(SeedFlag, chave):
        compatibilizar_estoque(session)
        session.add(SeedFlag(chave=chave))
        session.commit()


# ── Gatilho de comunicação ──────────────────────────────────────────────────
def pode_baixar_estoque(item: Estoque) -> bool:
    """Baixa real só a partir do estoque inicial/primeira compra. None (item
    legado, já em uso antes desta regra) conta como inicializado — não quebra as
    baixas que já funcionavam."""
    return item.estoque_inicializado is not False


# ── Unificação de volumes + mínimo por apresentação ─────────────────────────
def _apresentacoes_do_item(item: Estoque, pa: PrincipioAtivo) -> float | None:
    """Quantas apresentações (frascos) o saldo do item representa. Usa o volume
    por apresentação do item; se não houver, o item conta como 1 apresentação
    inteira enquanto tiver qualquer saldo."""
    saldo = item.quantidade or 0
    vol = item.volume_por_apresentacao
    if vol and vol > 0:
        # converte o saldo (na unidade do item) para a unidade do volume
        saldo_conv = converter(saldo, item.unidade or item.volume_unidade, item.volume_unidade)
        if saldo_conv is None:
            saldo_conv = saldo
        return saldo_conv / vol
    return 1.0 if saldo > 0 else 0.0


def resumo_principios(session: Session) -> list[dict]:
    """Visão gerencial da farmácia: por princípio ativo, o total unificado na
    unidade-base, o total de apresentações (soma das frações de frasco), o
    status do mínimo e a lista de apresentações (itens de estoque) com saldo,
    marca/laboratório e se precisam de estoque inicial."""
    principios = session.exec(select(PrincipioAtivo).order_by(PrincipioAtivo.nome)).all()
    itens = session.exec(select(Estoque)).all()
    por_pa: dict[int, list[Estoque]] = {}
    for it in itens:
        if it.principio_ativo_id is not None:
            por_pa.setdefault(it.principio_ativo_id, []).append(it)

    saida = []
    for pa in principios:
        grupo = por_pa.get(pa.id, [])
        total_base = 0.0
        base_ok = True
        apresentacoes = 0.0
        precisa_inicializar = False
        linhas = []
        for it in grupo:
            saldo = it.quantidade or 0
            conv = converter(saldo, it.unidade, pa.unidade_base)
            if conv is None:
                base_ok = False
            else:
                total_base += conv
            apres = _apresentacoes_do_item(it, pa)
            if apres is not None:
                apresentacoes += apres
            nao_inic = it.estoque_inicializado is False
            if nao_inic:
                precisa_inicializar = True
            linhas.append({
                "estoque_id": it.id, "nome": it.nome,
                "marca": it.laboratorio, "medicamento_comercial_id": it.medicamento_comercial_id,
                "saldo": saldo, "unidade": it.unidade,
                "volume_por_apresentacao": it.volume_por_apresentacao, "volume_unidade": it.volume_unidade,
                "apresentacoes": round(apres, 2) if apres is not None else None,
                "estoque_inicializado": it.estoque_inicializado is not False,
            })
        minimo = pa.estoque_minimo_apresentacoes if pa.estoque_minimo_apresentacoes is not None else 1.0
        abaixo_minimo = bool(grupo) and apresentacoes < minimo
        saida.append({
            "id": pa.id, "nome": pa.nome, "categoria_software": pa.categoria_software,
            "uso_principal": pa.uso_principal, "justificativa": pa.justificativa,
            "eh_biologico": pa.eh_biologico, "doenca_id": pa.doenca_id,
            "unidade_base": pa.unidade_base, "unidade_apresentacao": pa.unidade_apresentacao,
            "estoque_minimo_apresentacoes": minimo,
            "total_base": round(total_base, 2) if base_ok else None,
            "total_apresentacoes": round(apresentacoes, 2),
            "qtd_marcas_estoque": len(grupo),
            "abaixo_minimo": abaixo_minimo,
            "precisa_inicializar": precisa_inicializar,
            "itens": linhas,
        })
    return saida
