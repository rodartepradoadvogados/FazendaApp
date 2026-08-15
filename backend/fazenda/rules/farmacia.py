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

from fazenda.models import Doenca, Estoque, IndicacaoTerapeutica, MedicamentoComercial, PrincipioAtivo, SeedFlag
from fazenda.rules.farmacia_indicacoes_seed import INDICACOES, MARCAS
from fazenda.rules.farmacia_seed import PRINCIPIOS
from fazenda.rules.visibilidade import visivel

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
    # O seed cuida SÓ do catálogo global (`fazenda_id IS NULL`). Sem o filtro,
    # a busca por nome achava a linha de uma fazenda que já tivesse cadastrado
    # o mesmo princípio/doença à mão: o seed enriquecia o registro DELA (dado
    # de uma cliente alterado por rotina global) e nunca criava o global, que
    # então faltava para todas as outras.
    for p in PRINCIPIOS:
        doenca_id = None
        if p.get("doenca"):
            doenca = session.exec(
                select(Doenca).where(Doenca.nome == p["doenca"], Doenca.fazenda_id.is_(None))
            ).first()
            if not doenca:
                doenca = Doenca(nome=p["doenca"])
                session.add(doenca)
                session.commit()
                session.refresh(doenca)
            doenca_id = doenca.id

        pa = session.exec(
            select(PrincipioAtivo).where(PrincipioAtivo.nome == p["nome"], PrincipioAtivo.fazenda_id.is_(None))
        ).first()
        if not pa:
            pa = PrincipioAtivo(nome=p["nome"])
            session.add(pa)
        # Preenche só o que estiver vazio (respeita edições do usuário).
        pa.categoria = pa.categoria or p.get("categoria")
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


# ── Seed do catálogo de indicações (Doenca + IndicacaoTerapeutica) ─────────
def seed_indicacoes(session: Session) -> None:
    """Cria/enriquece o catálogo de INDICAÇÕES terapêuticas do documento base
    (`farmacia_indicacoes_seed`): a lista de doenças/manejos (`Doenca`) e o
    vínculo N-para-N com os princípios que tratam cada uma
    (`IndicacaoTerapeutica`, com prioridade clínica), além de enriquecer as
    marcas comerciais que `seed_farmacia` já criou (dose/via/carência/alertas
    de bula). Precisa rodar DEPOIS de `seed_farmacia` — depende dos
    princípios ativos já existirem.

    Segue o MESMO padrão add-missing de `seed_farmacia`:

      • `Doenca`: procurada por (nome, fazenda_id IS NULL). Se não existir,
        cria com fazenda_id=None. Se existir, preenche `tipo`/`descricao` SÓ
        se estiverem vazios. NUNCA renomeia — os 6 nomes já semeados
        (Brucelose, Clostridiose, Leptospirose, Diarreia Neonatal,
        Pasteurelose e Paratifo dos Bezerros, Tuberculose) são referenciados
        por nome em `PrincipioAtivo.doenca_id`, em protocolos sanitários
        gravados por critério "doenca" e no casamento por nome de vacina
        pré-parto em `routers/estoque.py` — renomear quebra os três.

      • `IndicacaoTerapeutica`: cria só o par (princípio, doença) que ainda
        não existe. NUNCA sobrescreve `prioridade` de um vínculo já
        existente — pode ter sido reordenado à mão pelo produtor
        (substituto inteligente). `nota` só é preenchida se estiver vazia.

      • Princípio referenciado por nome no documento de indicações que não
        existir no catálogo (não deveria acontecer — os 40 nomes foram
        conferidos contra `farmacia_seed.PRINCIPIOS`) faz o vínculo ser
        PULADO em silêncio: quem cria princípio ativo é `seed_farmacia`,
        nunca este seed.

      • `MedicamentoComercial`: procurada por (principio_ativo_id,
        nome_comercial, fazenda_id IS NULL). Cria a linha se faltar (mesma
        marca que `seed_farmacia.PRINCIPIOS` já lista — na prática isso é
        redundante hoje, mas mantém o seed correto se um dia a marca só
        existir no documento de indicações). O ENRIQUECIMENTO dos campos de
        bula de uma marca já existente é guardado por `SeedFlag` (chave
        "farmacia_indicacoes_v1") — é a única parte deste seed que poderia
        sobrescrever trabalho manual do produtor, então roda só uma vez; a
        CRIAÇÃO da linha em si fica fora da flag, igual a `seed_farmacia`,
        para não deixar banco antigo travado sem a marca.

      • Honestidade de status (ver `farmacia_indicacoes_seed`): o valor
        gravado NUNCA confia cegamente no campo bruto do dicionário — é
        recalculado a partir do `status_*` correspondente. status
        "a_preencher" grava `None` (nunca 0, nunca chute); status
        "proibido_lactacao" grava `proibido_lactacao=True` e
        `carencia_leite_dias=None` (é proibição, não prazo).
    """
    # ── Doenca + IndicacaoTerapeutica: sem flag, roda em todo start ────────
    principios_por_nome: dict[str, PrincipioAtivo] = {
        p.nome: p for p in session.exec(select(PrincipioAtivo).where(PrincipioAtivo.fazenda_id.is_(None))).all()
    }
    for ind in INDICACOES:
        doenca = session.exec(
            select(Doenca).where(Doenca.nome == ind["nome"], Doenca.fazenda_id.is_(None))
        ).first()
        if not doenca:
            doenca = Doenca(nome=ind["nome"], tipo=ind.get("tipo"), descricao=ind.get("descricao"))
            session.add(doenca)
            session.commit()
            session.refresh(doenca)
        else:
            doenca.tipo = doenca.tipo or ind.get("tipo")
            doenca.descricao = doenca.descricao or ind.get("descricao")
            session.add(doenca)
            session.commit()

        for vinculo in ind.get("principios", []):
            pa = principios_por_nome.get(vinculo["principio"])
            if pa is None:
                continue  # princípio fora do catálogo — pula o vínculo, não cria princípio aqui.
            existente = session.exec(
                select(IndicacaoTerapeutica).where(
                    IndicacaoTerapeutica.principio_ativo_id == pa.id,
                    IndicacaoTerapeutica.doenca_id == doenca.id,
                    IndicacaoTerapeutica.fazenda_id.is_(None),
                )
            ).first()
            if not existente:
                session.add(IndicacaoTerapeutica(
                    principio_ativo_id=pa.id, doenca_id=doenca.id,
                    prioridade=vinculo.get("prioridade", 2), nota=vinculo.get("nota"),
                ))
            else:
                # NUNCA mexe em `prioridade` — só completa nota se estiver vazia.
                existente.nota = existente.nota or vinculo.get("nota")
                session.add(existente)
        session.commit()

    # ── MedicamentoComercial: cria a linha que faltar (sem flag) ───────────
    for m in MARCAS:
        pa = principios_por_nome.get(m["principio"])
        if pa is None:
            continue
        marca = session.exec(
            select(MedicamentoComercial).where(
                MedicamentoComercial.principio_ativo_id == pa.id,
                MedicamentoComercial.nome_comercial == m["nome_comercial"],
                MedicamentoComercial.fazenda_id.is_(None),
            )
        ).first()
        if not marca:
            session.add(MedicamentoComercial(principio_ativo_id=pa.id, nome_comercial=m["nome_comercial"]))
    session.commit()

    # ── Enriquecimento dos campos de bula: guardado por SeedFlag ───────────
    chave = "farmacia_indicacoes_v1"
    if session.get(SeedFlag, chave):
        return
    for m in MARCAS:
        pa = principios_por_nome.get(m["principio"])
        if pa is None:
            continue
        marca = session.exec(
            select(MedicamentoComercial).where(
                MedicamentoComercial.principio_ativo_id == pa.id,
                MedicamentoComercial.nome_comercial == m["nome_comercial"],
                MedicamentoComercial.fazenda_id.is_(None),
            )
        ).first()
        if not marca:
            continue  # não deveria acontecer (acabou de ser garantida acima)

        dose_confirmada = m.get("status_dose") == "referencia"
        leite_confirmada = m.get("status_carencia_leite") == "referencia"
        carne_confirmada = m.get("status_carencia_carne") == "referencia"
        proibido = m.get("status_carencia_leite") == "proibido_lactacao" or bool(m.get("proibido_lactacao"))

        dose_padrao = m.get("dose_padrao") if dose_confirmada else None
        dose_referencia_kg = m.get("dose_referencia_kg") if dose_confirmada else None
        dose_texto = m.get("dose_texto") if dose_confirmada else None
        carencia_leite_dias = None if proibido else (m.get("carencia_leite_dias") if leite_confirmada else None)
        carencia_carne_dias = m.get("carencia_carne_dias") if carne_confirmada else None

        marca.uso_principal = marca.uso_principal or m.get("uso_principal")
        marca.concentracao = marca.concentracao or m.get("concentracao")
        if marca.dose_padrao is None:
            marca.dose_padrao = dose_padrao
        marca.unidade_dose = marca.unidade_dose or m.get("unidade_dose")
        marca.dose_base = marca.dose_base or m.get("dose_base")
        if marca.dose_referencia_kg is None:
            marca.dose_referencia_kg = dose_referencia_kg
        if marca.dose_texto is None:
            marca.dose_texto = dose_texto
        marca.via_padrao = marca.via_padrao or m.get("via_padrao")
        marca.link_bula = marca.link_bula or m.get("link_bula")
        if marca.carencia_leite_dias is None:
            marca.carencia_leite_dias = carencia_leite_dias
        if marca.carencia_carne_dias is None:
            marca.carencia_carne_dias = carencia_carne_dias
        if marca.proibido_lactacao is None and proibido:
            marca.proibido_lactacao = True
        if marca.alerta_gestacao is None:
            marca.alerta_gestacao = m.get("alerta_gestacao")
        marca.alerta = marca.alerta or m.get("alerta")
        session.add(marca)
    session.add(SeedFlag(chave=chave))
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


_NOME_LEGADO_SEM_CATALOGO = "Cepa B19 (Brucella abortus atenuada)"


def _limpar_principio_legado(session: Session) -> None:
    """Remove o placeholder legado (seed mínimo pré-catálogo) se nunca tiver sido
    usado — sem marca comercial nem item de estoque vinculado. O princípio
    correto do documento base é "Brucelose Bovina (Cepa 19 ou RB51)", já criado
    pelo seed_farmacia. Não apaga nada que tenha uso real."""
    pa = session.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == _NOME_LEGADO_SEM_CATALOGO)).first()
    if not pa:
        return
    tem_marca = session.exec(select(MedicamentoComercial).where(MedicamentoComercial.principio_ativo_id == pa.id)).first()
    tem_estoque = session.exec(select(Estoque).where(Estoque.principio_ativo_id == pa.id)).first()
    if tem_marca or tem_estoque:
        return
    session.delete(pa)
    session.commit()


def bootstrap_farmacia(session: Session) -> None:
    """Garante o catálogo de princípios ativos/marcas e compatibiliza o estoque.

    O SEED DO CATÁLOGO roda em TODO start: é add-missing e idempotente (só cria o
    que falta, preenche apenas campos vazios), então novos princípios do documento
    base entram sem depender de flag de versão — corrige bancos que semearam antes
    do catálogo estar completo. A compatibilização do estoque legado roda uma vez."""
    seed_farmacia(session)
    seed_indicacoes(session)
    _limpar_principio_legado(session)
    chave = "farmacia_compat_v2"
    if not session.get(SeedFlag, chave):
        compatibilizar_estoque(session)
        session.add(SeedFlag(chave=chave))
        session.commit()
    backfill_finalidade_estoque(session)
    normalizar_unidades_estoque(session)
    seed_boostin(session)
    vincular_bst_ao_principio(session)


# Sinônimos/abreviações legadas (import de planilha, cadastro antigo) da
# unidade canônica "unidade" — mantém em sincronia com
# rules/unidades._SINONIMOS_UNIDADE (front e back precisam concordar).
_SINONIMOS_UNIDADE_ESTOQUE = {"un", "und", "unid", "unidades"}


def normalizar_unidades_estoque(session: Session) -> None:
    """Corrige `Estoque.unidade` gravada com uma abreviação (ex.: "un" em vez de
    "unidade") — itens assim ficavam fora do grupo de unidades compatíveis e
    escondiam opções válidas (ex.: "ml") no seletor de dose. Roda em todo start
    (idempotente: só normaliza, nunca perde dado)."""
    itens = session.exec(select(Estoque)).all()
    for item in itens:
        if (item.unidade or "").strip().lower() in _SINONIMOS_UNIDADE_ESTOQUE:
            item.unidade = "unidade"
            session.add(item)
    session.commit()


def seed_boostin(session: Session) -> None:
    """Cadastra o item de estoque "Boostin" — alternativa ao Lactotropin no BST,
    mesma unidade ("unidade") e mesma finalidade/categoria do Lactotropin já
    cadastrado. Fica com saldo zero (não inicializado) até o usuário lançar o
    estoque real; aparece no seletor de produto do BST mesmo sem saldo, mas só
    permite baixa a partir do estoque inicial (mesma regra do resto do
    farmácia). Idempotente: não recria se "Boostin" já existir no cadastro."""
    ja_existe = session.exec(select(Estoque).where(Estoque.nome == "Boostin")).first()
    if ja_existe:
        return
    lactotropin = session.exec(select(Estoque).where(Estoque.nome.ilike("%lactotropin%"))).first()
    session.add(Estoque(
        categoria=lactotropin.categoria if lactotropin else None,
        finalidade=(lactotropin.finalidade if lactotropin else None) or "Medicamento",
        nome="Boostin",
        unidade="unidade",
        estoque_inicializado=False,
        quantidade=0,
    ))
    session.commit()


NOME_PRINCIPIO_BST = "Somatotropina Bovina Recombinante (bST)"


def vincular_bst_ao_principio(session: Session) -> None:
    """Liga os itens de estoque de bST (Lactotropin, Boostin) ao princípio
    ativo "Somatotropina Bovina Recombinante (bST)".

    Os dois itens nasceram no cadastro ANTES de o princípio existir no
    catálogo da farmácia (ver `seed_boostin` acima e o item Lactotropin, mais
    antigo ainda), então ficaram com `principio_ativo_id` nulo. Quem faria o
    vínculo por nome de marca é `compatibilizar_estoque`, mas ela é guardada
    por SeedFlag e já rodou — um princípio novo no catálogo nunca alcançaria
    esses itens legados.

    Sem o vínculo, o item não aparece como opção de frasco na hora de
    confirmar uma aplicação (o seletor "qual medicamento/frasco?" agrupa por
    princípio ativo — ver `estoque_baixa.opcoes_medicamento`).

    Add-missing e idempotente: só preenche o que está vazio, nunca sobrescreve
    um vínculo que o usuário já tenha feito à mão.
    """
    principio = session.exec(
        select(PrincipioAtivo).where(PrincipioAtivo.nome == NOME_PRINCIPIO_BST)
    ).first()
    if not principio:
        return  # catálogo ainda não semeado nesta sessão — roda no próximo start
    for item in session.exec(select(Estoque)).all():
        nome = (item.nome or "").strip().lower()
        # "lactotropim" (com M) é erro de grafia frequente na digitação — o
        # produto da Elanco é Lactotropin, com N. Casa as duas formas para o
        # item mal digitado não ficar de fora do vínculo, e corrige a grafia
        # do cadastro. Renomear é seguro: MovimentoEstoque aponta para o item
        # por `estoque_id` (FK), não pelo texto do nome, então o histórico de
        # baixas/entradas continua ligado.
        if "lactotropim" in nome:
            item.nome = (item.nome or "").replace("Lactotropim", "Lactotropin").replace("lactotropim", "lactotropin")
            session.add(item)
            nome = item.nome.strip().lower()
        if item.principio_ativo_id is None and ("lactotropin" in nome or "boostin" in nome):
            item.principio_ativo_id = principio.id
            item.principio_ativo = item.principio_ativo or principio.nome
            session.add(item)
    session.commit()


def backfill_finalidade_estoque(session: Session) -> None:
    """Preenche `Estoque.finalidade` (novo campo) para itens legados que já têm
    sinal forte de serem medicamento — classificação, princípio ativo (texto ou
    vínculo) — e ainda não foram classificados. Roda em todo start (add-missing,
    nunca sobrescreve um valor já definido pelo usuário no cadastro)."""
    itens = session.exec(select(Estoque).where(Estoque.finalidade == None)).all()  # noqa: E711
    if not itens:
        return
    for item in itens:
        if item.classificacao_medicamento or item.principio_ativo_id or (item.principio_ativo or "").strip():
            item.finalidade = "Medicamento"
            session.add(item)
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


def resumo_principios(session: Session, fazenda_id: int | None = None) -> list[dict]:
    """Visão gerencial da farmácia: por princípio ativo, o total unificado na
    unidade-base, o total de apresentações (soma das frações de frasco), o
    status do mínimo e a lista de apresentações (itens de estoque) com saldo,
    marca/laboratório e se precisam de estoque inicial.

    `fazenda_id` filtra os princípios ativos pela fazenda atual — os itens de
    Estoque em si ainda não têm fazenda_id (migração pendente), então o saldo
    agregado por princípio permanece global até essa etapa seguinte."""
    query = visivel(select(PrincipioAtivo).order_by(PrincipioAtivo.nome), PrincipioAtivo, fazenda_id)
    principios = session.exec(query).all()
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
            "id": pa.id, "nome": pa.nome, "ativo": pa.ativo, "categoria": pa.categoria, "categoria_software": pa.categoria_software,
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
