"""
Fluxos declarativos dos lançamentos operacionais feitos pelo robô do Telegram.

Cada lançamento é uma lista de PERGUNTAS (campos). O motor de conversa em
`telegram.py` percorre os campos, valida cada resposta e, ao final, grava um
LancamentoPendente. Quando a conta principal APROVA no site/app, o
`criar_registro` monta o payload no formato do endpoint real e cria o registro
de verdade — reaproveitando exatamente a mesma lógica do site.

Adicionar um lançamento novo = acrescentar uma entrada em FLUXOS e um ramo em
`criar_registro`. Nada de código de conversa por tipo.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Callable

from sqlmodel import Session, select

from fazenda.models import Animal, ControleLeiteiro, EstoqueSemen, Lote, MovimentoLote, Parto, Secagem


# ── Tipos de campo ─────────────────────────────────────────────────────────
# "animal"   → um número de animal (validado; aceita mesmo se não achar).
# "numeros"  → um ou vários números separados por espaço/vírgula.
# "texto"    → texto livre.
# "numero"   → número decimal.
# "data"     → aceita "hoje", "ontem", DD/MM, DD/MM/AAAA ou AAAA-MM-DD.
# "ordenhas" → uma ou mais pesagens ("20 18 15").
# "opcoes"   → botões; `opcoes` é lista de (valor, rótulo) ou função(session).
def C(chave, pergunta, tipo, opcoes=None, obrigatorio=True, dica=None):
    return {"chave": chave, "pergunta": pergunta, "tipo": tipo, "opcoes": opcoes,
            "obrigatorio": obrigatorio, "dica": dica}


def _lotes_opcoes(session: Session) -> list[tuple[str, str]]:
    lotes = session.exec(select(Lote).order_by(Lote.codigo)).all()
    vistos: dict[str, str] = {}
    for l in lotes:
        cod = (l.codigo or "").strip()
        if cod and cod not in vistos:
            vistos[cod] = f"{cod}" + (f" — {l.nome}" if getattr(l, "nome", None) else "")
    return [(c, r) for c, r in vistos.items()]


def _touros_opcoes(session: Session, dados: dict) -> list[tuple[str, str]]:
    """Touros/sêmen disponíveis para a inseminação, por categoria — como no site.
    Monta natural → só touros da fazenda; IA (cio natural/IATF) → sêmen com dose
    em estoque (convencional/sexado). Rotulados pela categoria."""
    natureza = (dados or {}).get("natureza")
    rotulo_cat = {"convencional": "convencional", "sexado": "sexado", "fazenda": "fazenda"}
    itens = [i for i in session.exec(select(EstoqueSemen).order_by(EstoqueSemen.touro_nome)).all() if i.ativo]
    saida: list[tuple[str, str]] = []
    for i in itens:
        if natureza == "monta_natural":
            if i.tipo != "fazenda":
                continue
        else:  # cio natural ou IATF → sêmen com dose (touro da fazenda também serve)
            if i.tipo != "fazenda" and (i.doses or 0) <= 0:
                continue
        doses = f" · {i.doses} dose(s)" if i.tipo != "fazenda" else ""
        saida.append((i.touro_nome, f"{i.touro_nome} ({rotulo_cat.get(i.tipo, i.tipo)}{doses})"))
    return saida


MOTIVOS_SECAGEM = [("doente", "Doente"), ("baixa_producao", "Baixa produção"), ("comportamento", "Comportamento"),
                   ("mastite", "Mastite"), ("casco", "Casco"), ("rotina", "Rotina parto"), ("outros", "Outros")]
RESULTADOS_DIAG = [("reconfirmada", "Prenhe (confirmada)"), ("retoque", "Prenhe — marcar retoque"),
                   ("negativo", "Vazia"), ("indefinido", "Indefinido (reavaliar)")]
METODOS_DIAG = [("Palpação", "Palpação (toque)"), ("Ultrassom", "Ultrassom"), ("Cio de repasse", "Cio de repasse")]
# Natureza do serviço reprodutivo (alinha com o site): cio natural (IA sem
# protocolo), IATF (IA em protocolo) ou monta natural (touro).
NATUREZA_SERVICO = [("cio_natural", "Cio natural (IA)"), ("iatf", "IATF (protocolo)"), ("monta_natural", "Monta natural")]
RESULTADOS_RECONF = [("positivo", "Confirmada (positivo)"), ("negativo", "Perdeu a gestação (negativo)")]
TIPOS_BAIXA = [("morte", "Morte"), ("descarte_voluntario", "Descarte voluntário"), ("descarte_involuntario", "Descarte involuntário")]
MOTIVOS_BAIXA = [("venda", "Venda"), ("abate", "Abate"), ("acidente", "Acidente"), ("doenca", "Doença"), ("macho", "Macho"), ("outros", "Outros")]
SEXO_CRIA = [("F", "Fêmea"), ("M", "Macho")]
# Unidades aceitas na aplicação/baixa de estoque (mesma lista de rules/unidades).
UNIDADES = [("ml", "ml"), ("L", "L"), ("unidade", "unidade"), ("dose", "dose"),
            ("kg", "kg"), ("saca 30kg", "saca 30kg"), ("saca 60kg", "saca 60kg")]


# ── Catálogo de fluxos ─────────────────────────────────────────────────────
FLUXOS: dict[str, dict] = {
    "controle_leiteiro": {
        "rotulo": "🥛 Controle leiteiro (pesagem)",
        "campos": [
            C("numero_matriz", "Qual o <b>número da vaca</b>?", "animal"),
            C("data_controle", "Qual a <b>data</b> da pesagem?", "data"),
            C("ordenhas", "Quanto deu cada ordenha em kg? (ex.: <code>20 18 15</code>)", "ordenhas"),
        ],
    },
    "parto": {
        "rotulo": "🐄 Parto / nascimento",
        "campos": [
            C("numero_matriz", "Qual o <b>número da mãe (matriz)</b>?", "animal"),
            C("data_parto", "Qual a <b>data do parto</b>?", "data"),
            C("cria_numero", "Qual o <b>número da cria</b>? (ou escreva <code>pular</code> se não for cadastrar agora)", "texto", obrigatorio=False),
            C("cria_sexo", "Qual o <b>sexo da cria</b>?", "opcoes", opcoes=SEXO_CRIA, obrigatorio=False),
        ],
    },
    "secagem": {
        "rotulo": "💧 Secagem",
        "campos": [
            C("numero_matriz", "Qual o <b>número da vaca</b> a secar?", "animal"),
            C("data_secagem", "Qual a <b>data da secagem</b>?", "data"),
            C("motivo", "Qual o <b>motivo</b> da secagem?", "opcoes", opcoes=MOTIVOS_SECAGEM),
        ],
    },
    "inseminacao": {
        "rotulo": "🧬 Inseminação / cobertura",
        "campos": [
            C("numero_matriz", "Qual o <b>número da vaca</b>?", "animal"),
            C("data_servico", "Qual a <b>data do serviço</b>?", "data"),
            C("natureza", "Foi <b>cio natural</b>, <b>IATF</b> ou <b>monta natural</b>?", "opcoes", opcoes=NATUREZA_SERVICO),
            C("touro", "Qual o <b>touro/sêmen</b> (por categoria)?", "opcoes", opcoes=_touros_opcoes, obrigatorio=False),
        ],
    },
    "protocolo_iatf": {
        "rotulo": "📋 Protocolo IATF (D0)",
        "campos": [
            C("animais", "Quais os <b>números das vacas</b>? (separe por espaço, ex.: <code>1234 1235 1240</code>)", "numeros"),
            C("data_d0", "Qual a <b>data do D0</b> (início do protocolo)?", "data"),
        ],
    },
    "troca_lote": {
        "rotulo": "🔀 Troca de lote",
        "campos": [
            C("animais", "Quais os <b>números dos animais</b> a mover? (separe por espaço)", "numeros"),
            C("lote_destino_codigo", "Para qual <b>lote de destino</b>?", "opcoes", opcoes=_lotes_opcoes),
            C("data_movimento", "Em que <b>data</b>?", "data"),
            C("motivo", "Qual o <b>motivo</b>? (ou <code>pular</code>)", "texto", obrigatorio=False),
        ],
    },
    "diagnostico": {
        "rotulo": "🔎 Diagnóstico de gestação",
        "campos": [
            C("numero_matriz", "Qual o <b>número da vaca</b>?", "animal"),
            C("data_diagnostico", "Qual a <b>data do diagnóstico</b>?", "data"),
            C("resultado", "Qual o <b>resultado</b>?", "opcoes", opcoes=RESULTADOS_DIAG),
            C("metodo", "Qual o <b>método</b>?", "opcoes", opcoes=METODOS_DIAG, obrigatorio=False),
        ],
    },
    "reconfirmacao": {
        "rotulo": "🔁 Reconfirmação (2º exame)",
        "campos": [
            C("numero_matriz", "Qual o <b>número da vaca</b>?", "animal"),
            C("data_reconfirmacao", "Qual a <b>data da reconfirmação</b>?", "data"),
            C("resultado", "Qual o <b>resultado</b> do 2º exame?", "opcoes", opcoes=RESULTADOS_RECONF),
        ],
    },
    "sanidade": {
        "rotulo": "💉 Sanidade (aplicação)",
        "campos": [
            C("animais", "Quais os <b>números dos animais</b>? (separe por espaço)", "numeros"),
            C("data_aplicacao", "Qual a <b>data da aplicação</b>?", "data"),
            C("produto", "Qual o <b>produto/medicamento</b>?", "texto"),
            C("quantidade", "Qual a <b>quantidade/dose</b> por animal?", "numero"),
            C("unidade", "Qual a <b>unidade</b>?", "opcoes", opcoes=UNIDADES),
        ],
    },
    "baixa_animal": {
        "rotulo": "⚰️ Morte / descarte",
        "campos": [
            C("animais", "Quais os <b>números dos animais</b>? (separe por espaço)", "numeros"),
            C("tipo_baixa", "Qual o <b>tipo de baixa</b>?", "opcoes", opcoes=TIPOS_BAIXA),
            C("motivo", "Qual o <b>motivo</b>?", "opcoes", opcoes=MOTIVOS_BAIXA),
            C("data_baixa", "Em que <b>data</b>?", "data"),
            C("valor", "Qual o <b>valor</b> (R$)? (ou <code>pular</code> se não houver)", "numero", obrigatorio=False),
        ],
    },
    # Despesa/receita vindas do intake de documento (foto/PDF/XML) — não são
    # perguntadas em conversa (o motor de conversa nunca abre este fluxo);
    # os "campos" aqui só alimentam o resumo mostrado na tela de aprovação.
    "despesa": {
        "rotulo": "🧾 Despesa (documento)",
        "campos": [
            C("fornecedor_cliente", "Fornecedor", "texto", obrigatorio=False),
            C("valor_total", "Valor total", "numero", obrigatorio=False),
            C("numero_documento", "Nº do documento", "texto", obrigatorio=False),
            C("tipo_documento", "Tipo de documento", "texto", obrigatorio=False),
            C("data_emissao", "Data de emissão", "data", obrigatorio=False),
            C("forma_pagamento", "Forma de pagamento", "texto", obrigatorio=False),
        ],
    },
    "receita": {
        "rotulo": "💰 Receita (documento)",
        "campos": [
            C("fornecedor_cliente", "Cliente", "texto", obrigatorio=False),
            C("valor_total", "Valor total", "numero", obrigatorio=False),
            C("numero_documento", "Nº do documento", "texto", obrigatorio=False),
            C("tipo_documento", "Tipo de documento", "texto", obrigatorio=False),
            C("data_emissao", "Data de emissão", "data", obrigatorio=False),
            C("forma_pagamento", "Forma de pagamento", "texto", obrigatorio=False),
        ],
    },
    # Matéria trazida pelo robô agendado externo (/milknews) via POST
    # /news/manual — não é conversa (o motor de conversa do Telegram nunca
    # abre este fluxo); os "campos" só alimentam o resumo da tela de aprovação.
    "noticia_manual": {
        "rotulo": "📰 Notícia (importação automática)",
        "campos": [
            C("fonte_nome", "Fonte", "texto", obrigatorio=False),
            C("manchete", "Manchete", "texto", obrigatorio=False),
            C("resumo", "Resumo", "texto", obrigatorio=False),
            C("link", "Link", "texto", obrigatorio=False),
            C("data_publicacao", "Data de publicação", "texto", obrigatorio=False),
            # URL da foto escolhida no banco de fotos do Milknews (aba
            # Aprovações) — não é perguntado em conversa, só editado ali via
            # o seletor de fotos (ver frontend/components/AprovacoesView.tsx).
            C("imagem", "Imagem", "texto", obrigatorio=False),
        ],
    },
}


# ── Validação de animal (usada pelo motor de conversa) ─────────────────────
def animal_existe(session: Session, numero: str) -> bool:
    return session.exec(select(Animal).where(Animal.numero == numero.strip())).first() is not None


# ── Parse de data amigável ─────────────────────────────────────────────────
def parse_data_br(texto: str, hoje: date) -> date | None:
    t = (texto or "").strip().lower()
    if t in ("hoje", "hj"):
        return hoje
    if t in ("ontem",):
        from datetime import timedelta
        return hoje - timedelta(days=1)
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d/%m", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%d.%m"):
        try:
            d = datetime.strptime(t, fmt).date()
            if fmt in ("%d/%m", "%d.%m"):
                d = d.replace(year=hoje.year)
            return d
        except ValueError:
            continue
    return None


# ── Resumo legível (tela de aprovação + confirmação no chat) ───────────────
def montar_resumo(tipo: str, dados: dict) -> str:
    fluxo = FLUXOS.get(tipo, {})
    rotulo = fluxo.get("rotulo", tipo)
    partes: list[str] = []
    for campo in fluxo.get("campos", []):
        ch = campo["chave"]
        if ch not in dados or dados[ch] in (None, "", []):
            continue
        val = dados[ch]
        if isinstance(val, list):
            val = ", ".join(str(v) for v in val)
        partes.append(f"{campo['chave'].replace('_', ' ')}: {val}")
    return f"{rotulo} — " + " · ".join(partes)


# ── Desfazer aprovação (G17) ────────────────────────────────────────────────
# Fallback gravado em `resultado["registros"]` quando um ramo criou algo mas
# não conseguiu localizar de volta o id do que criou — mesmo efeito prático
# de "sem desfazer automático" que os ramos que só mutam/estão fora de escopo
# já usam abaixo, só que com um motivo genérico.
_NAO_LOCALIZADO = {
    "reversivel": False,
    "motivo": "Não foi possível localizar o(s) registro(s) criado(s) para permitir desfazer.",
}


# ── Materialização (chamada quando a conta principal APROVA) ───────────────
def criar_registro(tipo: str, dados: dict, session: Session, *, user, fazenda_id: int) -> dict:
    """Monta o input do endpoint real e cria o registro. Levanta exceção em
    caso de erro (o chamador guarda a mensagem no LancamentoPendente).

    `user`/`fazenda_id` são repassados EXPLICITAMENTE a cada função de
    endpoint chamada abaixo — sem isso, `user: Usuario = Depends(...)` e
    `fazenda_id: int | None = Depends(...)` ficam com o valor padrão não
    resolvido (o próprio objeto `Depends`, já que esta chamada acontece fora
    do ciclo de requisição do FastAPI) e `usuario_id_seguro`/
    `fazenda_id_seguro` (rules/auditoria.py) caem para None — era exatamente
    assim que todo lançamento aprovado pelo Telegram (inclusive protocolo
    IATF, ver ramo "protocolo_iatf") nascia órfão. `fazenda_id` chega aqui já
    resolvido e nunca None (ver aprovacoes.aprovar / get_fazenda_id_escrita).

    G17 (Configurações > Aprovações > Desfazer): além do que cada endpoint já
    devolvia, cada ramo abaixo acrescenta uma chave `"registros"` ao
    resultado —

    - `list[{"tipo", "id"}]` quando o fluxo cria entidade(s) com id NOVAS
      nesta chamada. `tipo` é o id do tipo correspondente no motor genérico
      de exclusões (`fazenda.api.routers.exclusoes`/
      `fazenda.rules.exclusao_tipos`) — é o que `aprovacoes.desfazer` usa
      para reverter (mesmo trio `_desvincular_vales_dos_alvos` /
      `_estornar_estoque_dos_alvos` / `session.delete` de
      `exclusoes.confirmar`).
    - `{"reversivel": False, "motivo": "..."}` quando o ramo só MUTA um
      registro existente (diagnóstico, reconfirmação), não cria nada com id
      útil para o motor, ou está fora de escopo nesta fase (morte/descarte,
      notícia do blog) — `aprovacoes.aprovar` grava esse dict como está.

    `aprovacoes.aprovar` trata a ausência da chave (ramo esquecido) com o
    mesmo fallback genérico de "não reversível".
    """
    if tipo == "controle_leiteiro":
        from fazenda.api.routers.producao import ControlesIn, OrdenhaIn, criar_controles
        data_controle = _d(dados["data_controle"])
        entrada = OrdenhaIn(numero_matriz=dados["numero_matriz"], ordenhas=[float(x) for x in dados["ordenhas"]])
        resultado = criar_controles(ControlesIn(data_controle=data_controle, entradas=[entrada]), session=session, user=user, fazenda_id=fazenda_id)
        criado = session.exec(
            select(ControleLeiteiro)
            .where(ControleLeiteiro.numero_matriz == dados["numero_matriz"])
            .where(ControleLeiteiro.data_controle == data_controle)
            .order_by(ControleLeiteiro.id.desc())
        ).first()
        resultado["registros"] = [{"tipo": "controle", "id": criado.id}] if criado else _NAO_LOCALIZADO
        return resultado

    if tipo == "parto":
        from fazenda.api.routers.reproducao import CriaIn, PartoIn, registrar_parto
        crias = []
        if dados.get("cria_numero") and str(dados["cria_numero"]).strip().lower() not in ("pular", "-"):
            crias.append(CriaIn(numero=str(dados["cria_numero"]).strip(), sexo=dados.get("cria_sexo") or "F"))
        resultado = registrar_parto(PartoIn(numero_matriz=dados["numero_matriz"], data_parto=_d(dados["data_parto"]), crias=crias), session=session, user=user, fazenda_id=fazenda_id)
        criado = session.exec(
            select(Parto)
            .where(Parto.numero_matriz == dados["numero_matriz"])
            .where(Parto.ordem_parto == resultado.get("ordem_parto"))
            .order_by(Parto.id.desc())
        ).first()
        resultado["registros"] = [{"tipo": "parto", "id": criado.id}] if criado else _NAO_LOCALIZADO
        return resultado

    if tipo == "secagem":
        from fazenda.api.routers.producao import SecagemIn, registrar_secagem
        data_secagem = _d(dados["data_secagem"])
        resultado = registrar_secagem(SecagemIn(numero_matriz=dados["numero_matriz"], data_secagem=data_secagem, motivo=dados["motivo"]), session=session, user=user, fazenda_id=fazenda_id)
        criado = session.exec(
            select(Secagem)
            .where(Secagem.numero_matriz == dados["numero_matriz"])
            .where(Secagem.data_secagem == data_secagem)
            .order_by(Secagem.id.desc())
        ).first()
        # tipo "secagem" no motor de exclusões é o G5 — implementado em
        # paralelo por outro agente e pode ainda não existir em REGISTRO
        # quando isto roda; nesse caso `aprovacoes.desfazer` só avisa (não
        # falha), mesma tolerância descrita no plano para esta dependência.
        resultado["registros"] = [{"tipo": "secagem", "id": criado.id}] if criado else _NAO_LOCALIZADO
        return resultado

    if tipo == "inseminacao":
        from fazenda.api.routers.reproducao import ServicoIn, registrar_servico
        # Natureza (cio natural / IATF / monta natural) → tipo_servico + protocolo,
        # como no site: monta = touro; IATF = IA em protocolo; cio natural = IA sem protocolo.
        natureza = dados.get("natureza") or "cio_natural"
        tipo_servico = "Monta natural" if natureza == "monta_natural" else "IA"
        protocolo = "IATF" if natureza == "iatf" else None
        touro = dados.get("touro") or dados.get("reprodutor")  # reprodutor: compat. com fluxo antigo
        resultado = registrar_servico(ServicoIn(
            numero_matriz=dados["numero_matriz"], data_servico=_d(dados["data_servico"]),
            tipo_servico=tipo_servico, protocolo=protocolo,
            reprodutor=(touro if str(touro or "").strip().lower() not in ("pular", "-", "") else None),
        ), session=session, user=user, fazenda_id=fazenda_id)
        resultado["registros"] = [{"tipo": "servico", "id": resultado["id"]}] if resultado.get("id") else _NAO_LOCALIZADO
        return resultado

    if tipo == "protocolo_iatf":
        from fastapi import Response as _Response
        from fazenda.api.routers.reproducao import ProtocoloIatfIn, lancar_protocolo_iatf, _nome_auto_iatf
        d0 = _d(dados["data_d0"])
        # Tudo por keyword de propósito: `lancar_protocolo_iatf` tem um
        # `response: Response` entre `dados` e `session` — chamar por
        # posição (como este ramo fazia antes) empurrava `session` para o
        # parâmetro `response` e deixava o próprio `session` do endpoint sem
        # resolver, quebrando a materialização silenciosamente.
        resultado = lancar_protocolo_iatf(
            ProtocoloIatfIn(animais=_lista(dados["animais"]), data_d0=d0, protocolo=_nome_auto_iatf(d0)),
            response=_Response(), session=session, user=user, fazenda_id=fazenda_id,
        )
        if resultado.get("criado") and resultado.get("lancamento_id"):
            resultado["registros"] = [{"tipo": "protocolo_iatf_lancamento", "id": resultado["lancamento_id"]}]
        else:
            # `lancar_protocolo_iatf` reaproveita um lançamento idêntico já
            # ativo em vez de duplicar (ver comentário no próprio endpoint) —
            # desfazer aqui apagaria dados de OUTRO lançamento, que esta
            # aprovação não criou.
            resultado["registros"] = {
                "reversivel": False,
                "motivo": "Esta aprovação reaproveitou um lançamento de protocolo IATF já existente — "
                          "desfazer aqui apagaria dados de outro lançamento.",
            }
        return resultado

    if tipo == "troca_lote":
        from fazenda.api.routers.movimentacoes import MoverIn, mover_animais
        animais_lista = _lista(dados["animais"])
        data_movimento = _d(dados["data_movimento"])
        resultado = mover_animais(MoverIn(
            data_movimento=data_movimento, lote_destino_codigo=dados["lote_destino_codigo"],
            animais=animais_lista,
            motivo=(dados.get("motivo") if str(dados.get("motivo") or "").strip().lower() not in ("pular", "-", "") else None),
        ), session=session, user=user, fazenda_id=fazenda_id)
        # Sem id direto no retorno — busca de volta os MovimentoLote recém-
        # criados por (numero_matriz, data_movimento), um por animal movido.
        # tipo "movimento_lote" é o G4 — mesma tolerância de dependência
        # cruzada do "secagem" acima.
        candidatos = session.exec(
            select(MovimentoLote)
            .where(MovimentoLote.numero_matriz.in_(animais_lista))
            .where(MovimentoLote.data_movimento == data_movimento)
            .order_by(MovimentoLote.id.desc())
        ).all()
        vistos: set[str] = set()
        ids: list[int] = []
        for m in candidatos:
            if m.numero_matriz in vistos:
                continue
            vistos.add(m.numero_matriz)
            ids.append(m.id)
        resultado["registros"] = [{"tipo": "movimento_lote", "id": i} for i in ids] if ids else _NAO_LOCALIZADO
        return resultado

    if tipo == "diagnostico":
        from fazenda.api.routers.reproducao import DiagnosticoIn, registrar_diagnostico
        resultado = registrar_diagnostico(DiagnosticoIn(
            numero_matriz=dados["numero_matriz"], data_diagnostico=_d(dados["data_diagnostico"]),
            resultado=dados["resultado"], metodo=dados.get("metodo") or None,
        ), session=session, fazenda_id=fazenda_id)
        # Só ATUALIZA o Servico em aberto (resultado/data) — não cria
        # entidade nova, não há o que apagar para desfazer.
        resultado["registros"] = {
            "reversivel": False,
            "motivo": "Diagnóstico só atualiza um serviço já existente — não há registro novo para desfazer.",
        }
        return resultado

    if tipo == "reconfirmacao":
        from fazenda.api.routers.reproducao import ReconfirmacaoIn, registrar_reconfirmacao
        resultado = registrar_reconfirmacao(ReconfirmacaoIn(
            numero_matriz=dados["numero_matriz"], data_reconfirmacao=_d(dados["data_reconfirmacao"]),
            resultado=dados["resultado"],
        ), session=session, fazenda_id=fazenda_id)
        resultado["registros"] = {
            "reversivel": False,
            "motivo": "Reconfirmação só atualiza um serviço já existente — não há registro novo para desfazer.",
        }
        return resultado

    if tipo == "sanidade":
        from fazenda.api.routers.sanidade import AplicacaoIn, ItemAplicacaoIn, registrar_aplicacao
        item = ItemAplicacaoIn(produto=dados["produto"], quantidade=float(dados["quantidade"]), unidade=dados["unidade"])
        resultado = registrar_aplicacao(
            AplicacaoIn(data_aplicacao=_d(dados["data_aplicacao"]), animais=_lista(dados["animais"]), itens=[item]),
            session=session, user=user, fazenda_id=fazenda_id,
        )
        sanidade_ids = resultado.get("sanidade_ids") or []
        resultado["registros"] = (
            [{"tipo": "sanidade", "id": i} for i in sanidade_ids] if sanidade_ids else {
                "reversivel": False,
                "motivo": "A aplicação ficou programada na Agenda (data futura ou marcada como não aplicada) "
                          "— nada foi criado em Sanidade ainda para desfazer.",
            }
        )
        return resultado

    if tipo == "baixa_animal":
        from fazenda.api.routers.baixas import BaixaIn, registrar_baixa
        valor = dados.get("valor")
        valor = float(valor) if valor not in (None, "", "pular") else None
        resultado = registrar_baixa(BaixaIn(
            animais=_lista(dados["animais"]), tipo_baixa=dados["tipo_baixa"], motivo=dados["motivo"],
            data_baixa=_d(dados["data_baixa"]), valor=valor,
            tipo_valor=("total" if dados["motivo"] == "venda" and valor is not None else None),
        ), session=session, user=user, fazenda_id=fazenda_id)
        # Morte/descarte mexe em vários registros (Animal, possível
        # lançamento financeiro) sem um tipo único no motor de exclusões —
        # fora de escopo nesta fase (ver Parte 3, G17, do plano de
        # fechamento dos 17 gaps de editar/excluir).
        resultado["registros"] = {
            "reversivel": False,
            "motivo": "Morte/descarte ainda não tem desfazer automático — reverta manualmente em Rebanho, se necessário.",
        }
        return resultado

    if tipo in ("despesa", "receita"):
        resultado = _criar_lancamento_financeiro(tipo, dados, session, user=user, fazenda_id=fazenda_id)
        ids = resultado.get("ids") or []
        resultado["registros"] = [{"tipo": "financeiro", "id": i} for i in ids] if ids else _NAO_LOCALIZADO
        return resultado

    if tipo == "noticia_manual":
        from fazenda.api.routers.news import criar_noticia_a_partir_de_pendente
        resultado = criar_noticia_a_partir_de_pendente(dados, session)
        resultado["registros"] = {
            "reversivel": False,
            "motivo": "Notícias do blog não têm desfazer automático — edite ou exclua a matéria diretamente em News.",
        }
        return resultado

    raise ValueError(f"Tipo de lançamento desconhecido: {tipo}")


def _criar_lancamento_financeiro(tipo: str, dados: dict, session: Session, *, user, fazenda_id: int) -> dict:
    """Materializa a despesa/receita lida do documento (foto/PDF/XML) enviado
    pelo Telegram — só chamada quando a conta principal APROVA. O
    fornecedor/cliente precisa já existir no cadastro (Configurações >
    Cadastro > Fornecedores); nunca é criado à revelia a partir do texto lido
    do documento."""
    from fazenda.api.routers.financeiro import ItemIn, LancamentoIn, ParcelaIn, criar_lancamento
    from fazenda.models import ContaGerencial, Fornecedor

    forn = (dados.get("fornecedor_cliente") or "").strip()
    if forn and not session.exec(select(Fornecedor).where(Fornecedor.nome == forn)).first():
        raise ValueError(
            f'Fornecedor/cliente "{forn}" não está cadastrado. Cadastre-o em Configurações > '
            'Cadastro > Fornecedores (ou corrija o nome para um já cadastrado) antes de aprovar.'
        )

    itens_doc = dados.get("itens") or []
    if isinstance(itens_doc, str):
        itens_doc = [itens_doc]
    itens: list[ItemIn] = []
    for it in itens_doc:
        # A extração do documento (OCR/LLM) às vezes devolve os itens como
        # texto solto em vez de objetos {produto, quantidade, ...} — trata
        # como item único sem preço em vez de quebrar a aprovação.
        if isinstance(it, str):
            it = {"produto": it}
        elif not isinstance(it, dict):
            continue
        produto = (it.get("produto") or "").strip()
        if not produto:
            continue
        vt = it.get("valor_total")
        if vt is None and it.get("quantidade") and it.get("valor_unitario"):
            vt = round(it["quantidade"] * it["valor_unitario"], 2)
        itens.append(ItemIn(
            produto=produto, quantidade=it.get("quantidade"), valor_unitario=it.get("valor_unitario"),
            valor_total=float(vt or 0), codigo_conta_gerencial=it.get("codigo_conta_gerencial") or None,
            nome_conta_gerencial=it.get("nome_conta_gerencial") or None,
        ))
    # Sem itens, ou itens sem preço próprio (ex.: vieram como texto solto) —
    # usa o valor total do documento inteiro num item único, em vez de deixar
    # o lançamento com valor zero (rejeitado pela validação de valor líquido).
    if not itens or not sum(i.valor_total for i in itens):
        itens = [ItemIn(produto=forn or "Documento recebido pelo Telegram", valor_total=float(dados.get("valor_total") or 0))]

    # tipo_documento: usa o que veio do cadastro (editado na tela de Aprovações,
    # closed dropdown) quando presente; senão cai no heurístico antigo do OCR
    # ("recibo" minúsculo/sem acento vindo da extração do documento).
    tipo_documento_bruto = dados.get("tipo_documento")
    eh_recibo = str(tipo_documento_bruto or "").strip().lower() in ("recibo", "recibo/comprovante")
    tipo_documento = tipo_documento_bruto if tipo_documento_bruto and tipo_documento_bruto not in ("recibo", "nota_fiscal") \
        else ("Recibo" if eh_recibo else "Nota fiscal")

    data_emissao = _d_opt(dados.get("data_emissao"))
    parcelas_dados = dados.get("parcelas") or []
    parcelas = [
        ParcelaIn(data_vencimento=_d(p["data_vencimento"]), valor=float(p["valor"]))
        for p in parcelas_dados if isinstance(p, dict) and p.get("data_vencimento") and p.get("valor")
    ]
    data_pagamento = _d_opt(dados.get("data_pagamento")) if not parcelas else None
    valor_total = sum(i.valor_total for i in itens)

    lanc = LancamentoIn(
        tipo=tipo, itens=itens, centro_custo=dados.get("centro_custo") or "Pecuária Leiteira",
        fornecedor_cliente=dados.get("fornecedor_cliente"),
        numero_documento=dados.get("numero_documento"), tipo_documento=tipo_documento,
        data_emissao=data_emissao, data_vencimento=data_emissao or data_pagamento,
        parcelas=parcelas,
        data_pagamento=data_pagamento, valor_pago=valor_total if data_pagamento else None,
        conta_bancaria=dados.get("conta_bancaria") if data_pagamento else None,
        numero_documento_pagamento=dados.get("numero_documento_pagamento") if data_pagamento else None,
        forma_pagamento=dados.get("forma_pagamento") if data_pagamento else None,
    )
    res = criar_lancamento(dados=lanc, session=session, user=user, fazenda_id=fazenda_id)
    # Marca a origem "telegram" (LancamentoIn não carrega esse campo) para
    # identificar os lançamentos que vieram pelo robô.
    for cid in res.get("ids", []):
        conta = session.get(ContaGerencial, cid)
        if conta:
            conta.origem = "telegram"
            session.add(conta)
    session.commit()
    return res


def _d(valor) -> date:
    """Aceita date ou string ISO (o payload é salvo como JSON)."""
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor)[:10])


def _d_opt(valor) -> date | None:
    """Como `_d`, mas aceita None (data opcional, ex.: data_pagamento de nota que ainda não foi paga)."""
    return _d(valor) if valor else None


def _lista(valor) -> list[str]:
    if isinstance(valor, list):
        return [str(v).strip() for v in valor if str(v).strip()]
    return [p.strip() for p in str(valor).replace(",", " ").split() if p.strip()]
