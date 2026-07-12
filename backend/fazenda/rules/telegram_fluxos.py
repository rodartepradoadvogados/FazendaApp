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

from fazenda.models import Animal, Lote


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


MOTIVOS_SECAGEM = [("doente", "Doente"), ("baixa_producao", "Baixa produção"), ("comportamento", "Comportamento"),
                   ("mastite", "Mastite"), ("casco", "Casco"), ("rotina", "Rotina"), ("outros", "Outros")]
RESULTADOS_DIAG = [("reconfirmada", "Prenhe (confirmada)"), ("retoque", "Prenhe — marcar retoque"), ("negativo", "Vazia")]
TIPOS_SERVICO = [("IA", "Inseminação (IA)"), ("Monta natural", "Monta natural")]
TIPOS_BAIXA = [("morte", "Morte"), ("descarte_voluntario", "Descarte voluntário"), ("descarte_involuntario", "Descarte involuntário")]
MOTIVOS_BAIXA = [("venda", "Venda"), ("abate", "Abate"), ("acidente", "Acidente"), ("doenca", "Doença")]
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
            C("tipo_servico", "Foi <b>inseminação</b> ou <b>monta natural</b>?", "opcoes", opcoes=TIPOS_SERVICO),
            C("reprodutor", "Qual o <b>touro/sêmen</b>? (ou <code>pular</code>)", "texto", obrigatorio=False),
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


# ── Materialização (chamada quando a conta principal APROVA) ───────────────
def criar_registro(tipo: str, dados: dict, session: Session) -> dict:
    """Monta o input do endpoint real e cria o registro. Levanta exceção em
    caso de erro (o chamador guarda a mensagem no LancamentoPendente)."""
    if tipo == "controle_leiteiro":
        from fazenda.api.routers.producao import ControlesIn, OrdenhaIn, criar_controles
        entrada = OrdenhaIn(numero_matriz=dados["numero_matriz"], ordenhas=[float(x) for x in dados["ordenhas"]])
        return criar_controles(ControlesIn(data_controle=_d(dados["data_controle"]), entradas=[entrada]), session)

    if tipo == "parto":
        from fazenda.api.routers.reproducao import CriaIn, PartoIn, registrar_parto
        crias = []
        if dados.get("cria_numero") and str(dados["cria_numero"]).strip().lower() not in ("pular", "-"):
            crias.append(CriaIn(numero=str(dados["cria_numero"]).strip(), sexo=dados.get("cria_sexo") or "F"))
        return registrar_parto(PartoIn(numero_matriz=dados["numero_matriz"], data_parto=_d(dados["data_parto"]), crias=crias), session)

    if tipo == "secagem":
        from fazenda.api.routers.producao import SecagemIn, registrar_secagem
        return registrar_secagem(SecagemIn(numero_matriz=dados["numero_matriz"], data_secagem=_d(dados["data_secagem"]), motivo=dados["motivo"]), session)

    if tipo == "inseminacao":
        from fazenda.api.routers.reproducao import ServicoIn, registrar_servico
        return registrar_servico(ServicoIn(
            numero_matriz=dados["numero_matriz"], data_servico=_d(dados["data_servico"]),
            tipo_servico=dados.get("tipo_servico") or "IA",
            reprodutor=(dados.get("reprodutor") if str(dados.get("reprodutor") or "").strip().lower() not in ("pular", "-", "") else None),
        ), session)

    if tipo == "protocolo_iatf":
        from fazenda.api.routers.reproducao import ProtocoloIatfIn, lancar_protocolo_iatf
        return lancar_protocolo_iatf(ProtocoloIatfIn(animais=_lista(dados["animais"]), data_d0=_d(dados["data_d0"])), session)

    if tipo == "troca_lote":
        from fazenda.api.routers.movimentacoes import MoverIn, mover_animais
        return mover_animais(MoverIn(
            data_movimento=_d(dados["data_movimento"]), lote_destino_codigo=dados["lote_destino_codigo"],
            animais=_lista(dados["animais"]),
            motivo=(dados.get("motivo") if str(dados.get("motivo") or "").strip().lower() not in ("pular", "-", "") else None),
        ), session)

    if tipo == "diagnostico":
        from fazenda.api.routers.reproducao import DiagnosticoIn, registrar_diagnostico
        return registrar_diagnostico(DiagnosticoIn(numero_matriz=dados["numero_matriz"], data_diagnostico=_d(dados["data_diagnostico"]), resultado=dados["resultado"]), session)

    if tipo == "sanidade":
        from fazenda.api.routers.sanidade import AplicacaoIn, ItemAplicacaoIn, registrar_aplicacao
        item = ItemAplicacaoIn(produto=dados["produto"], quantidade=float(dados["quantidade"]), unidade=dados["unidade"])
        return registrar_aplicacao(AplicacaoIn(data_aplicacao=_d(dados["data_aplicacao"]), animais=_lista(dados["animais"]), itens=[item]), session)

    if tipo == "baixa_animal":
        from fazenda.api.routers.baixas import BaixaIn, registrar_baixa
        valor = dados.get("valor")
        valor = float(valor) if valor not in (None, "", "pular") else None
        return registrar_baixa(BaixaIn(
            animais=_lista(dados["animais"]), tipo_baixa=dados["tipo_baixa"], motivo=dados["motivo"],
            data_baixa=_d(dados["data_baixa"]), valor=valor,
            tipo_valor=("total" if dados["motivo"] == "venda" and valor is not None else None),
        ), session)

    raise ValueError(f"Tipo de lançamento desconhecido: {tipo}")


def _d(valor) -> date:
    """Aceita date ou string ISO (o payload é salvo como JSON)."""
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor)[:10])


def _lista(valor) -> list[str]:
    if isinstance(valor, list):
        return [str(v).strip() for v in valor if str(v).strip()]
    return [p.strip() for p in str(valor).replace(",", " ").split() if p.strip()]
