"""
Réguas de referência (Financeiro > Relatórios): faixas de mercado para comparar os
indicadores da fazenda, com fonte, selo de fidedignidade e prazo de validade.

Os dados ficam em `seed_data/reguas_referencia.json`, versionado no git e atualizado
por pull request (rotina mensal: docs/agents/reguas-referencia-mensal.md). O arquivo
é igual para todas as fazendas: não há dado de cliente aqui, e o cliente não edita a
faixa (a "meta própria" mora nos parâmetros da fazenda). Os textos da tela (alerta,
pop-up/modal "Entendi", rodapé de exportação) moram em `seed_data/textos_juridicos.json`
(ver rules/textos_juridicos.py).

PARECER JURÍDICO DE 08/10/2026 — "Sem dossiê completo, a faixa não vai ao ar" (3.5).
Uma régua só vira `publicada` quando TUDO abaixo vale; senão a API não devolve número:

1. interruptor geral `publicacao.liberada` ligado (padrão desligado; só o dono liga,
   por PR) e empresa constituída (bloco `empresa` dos textos preenchido);
2. interruptor da régua `ativa` ligado;
3. faixa por desenho: classe VALIDADA/VALIDADA_COM_RESSALVA, `exibir_faixa`, faixa não
   vazia e sem `condicao_para_exibir`;
4. ao menos uma fonte NACIONAL e uma INTERNACIONAL ATIVAS (interruptor `ativa` de cada
   fonte). Fonte desligada some da régua; se a régua perde um dos lados, sai do ar
   sozinha (`retirada`);
5. nada vencido: `valido_ate` do arquivo e `dossie.vence_em` (12 meses da compilação);
6. dossiê completo: fonte BR e estrangeira (valor lido, página/tabela), independência
   "sim" com justificativa, método de agregação, confiabilidade e critério;
7. dupla validação: `validado_por` com ao menos uma pessoa DIFERENTE de `compilado_por`,
   sobre a MESMA faixa que está no arquivo, e `pendente_de` vazio;
8. termos verificados: `dossie.termos_verificados_em` e, em CADA fonte ativa da régua,
   `termos_verificados_em` e `uso_comercial_confirmado_em` (parecer 3.3: fonte não
   verificada não sustenta faixa em produção); fonte "só corroboração" não serve de
   base do dossiê.

Situações (campo `situacao` de cada régua): "publicada" | "em_validacao" | "retirada" |
"vencida" | "sem_faixa". Fora de "publicada", a carga pública não leva faixa, ressalva
(que cita números das fontes) nem quadro de fontes.

Regras do arquivo que o validador faz valer (o CI testa) — o que já valia:
- régua VALIDADA exige pelo menos uma fonte nacional e uma internacional;
- selo "alta" exige duas nacionais, duas internacionais e fontes de no máximo 3 anos;
- régua NAO_VALIDADA nunca exibe faixa;
- fonte com licença que não permite uso comercial (AHDB, IFCN, Cepea) não entra;
e o que o parecer acrescentou: estados inconsistentes dos campos que SÓ HUMANOS
alteram (`publicacao`, `ativa`, `validado_por`, `termos_verificados_em`,
`uso_comercial_confirmado_em`) são recusados — ver `validar`.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Optional

from fazenda.rules import textos_juridicos

ARQUIVO = Path(__file__).resolve().parent.parent / "seed_data" / "reguas_referencia.json"

CLASSES = {"VALIDADA", "VALIDADA_COM_RESSALVA", "PARCIAL", "NAO_VALIDADA"}
CLASSES_COM_FAIXA = {"VALIDADA", "VALIDADA_COM_RESSALVA"}
SELOS = {"alta", "media", "baixa", None}
ORIGENS = {"nacional", "internacional"}
LICENCAS = {"reproducao_com_fonte", "citar_com_link", "nao_verificada"}
# Caminho recomendado pelo parecer (3.3) para cada fonte.
CAMINHOS_PARECER = {
    "citar_apos_confirmacao_escrita", "pedir_autorizacao", "verificar_antes",
    "corroboracao_apenas", "citar_apos_ler_termos", "excluir_por_ora",
}
# Fontes cuja licença não permite uso comercial num SaaS pago: o validador recusa.
HOSTS_VETADOS = ("ahdb.org.uk", "ifcndairy.org", "dairyreport.online", "cepea.org.br", "cepea.esalq.usp.br")
IDADE_MAXIMA_SELO_ALTO = 3  # anos

SITUACOES = ("publicada", "em_validacao", "retirada", "vencida", "sem_faixa")
CAMPOS_FONTE_DOSSIE = ("fonte_id", "valor_lido", "pagina_ou_tabela")


def carregar() -> dict[str, Any]:
    with open(ARQUIVO, encoding="utf-8") as f:
        return json.load(f)


def _data(txt: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(txt))
    except (TypeError, ValueError):
        return None


def _mais_um_ano(d: date) -> date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:  # 29/02
        return d.replace(year=d.year + 1, day=28)


def _mesma_pessoa(a: Any, b: Any) -> bool:
    return " ".join(str(a or "").split()).casefold() == " ".join(str(b or "").split()).casefold()


def _preenchido(v: Any) -> bool:
    return v is not None and (not isinstance(v, str) or bool(v.strip()))


def _br(d: Optional[date]) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def versao_reguas(dados: dict[str, Any]) -> str:
    """Identificador das réguas que vai no rodapé de exportação e no log."""
    return f"{dados['versao']} (revisada em {_br(_data(dados.get('revisado_em')))})"


# ---------------------------------------------------------------------------
# Validador do arquivo (o CI roda): devolve a lista de problemas.
# ---------------------------------------------------------------------------
def _validar_data_humana(erros: list[str], rotulo: str, valor: Any, hoje: date) -> Optional[date]:
    if valor is None:
        return None
    d = _data(valor)
    if d is None:
        erros.append(f"{rotulo}: data inválida")
    elif d > hoje:
        erros.append(f"{rotulo}: data no futuro")
    return d


def validar(dados: dict[str, Any], hoje: Optional[date] = None,
            textos: Optional[dict[str, Any]] = None) -> list[str]:
    """Devolve a lista de problemas (vazia = arquivo válido)."""
    hoje = hoje or date.today()
    textos = textos or textos_juridicos.dados_padrao()
    erros: list[str] = []

    datas = {k: _data(dados.get(k)) for k in ("revisado_em", "conferida_em", "valido_ate", "proxima_conferencia")}
    for k, v in datas.items():
        if v is None:
            erros.append(f"{k}: data inválida ou ausente")
    if not erros:
        if datas["revisado_em"] > hoje or datas["conferida_em"] > hoje:
            erros.append("revisado_em/conferida_em estão no futuro")
        if datas["conferida_em"] < datas["revisado_em"]:
            erros.append("conferida_em anterior a revisado_em")
        if datas["valido_ate"] <= datas["revisado_em"]:
            erros.append("valido_ate deve ser posterior a revisado_em")
        if datas["proxima_conferencia"] <= datas["conferida_em"]:
            erros.append("proxima_conferencia deve ser posterior a conferida_em")
    if "aviso" in dados:
        erros.append("'aviso' saiu do arquivo: o texto do alerta mora em textos_juridicos.json (parecer 7.1)")

    pub = dados.get("publicacao")
    if not isinstance(pub, dict) or not isinstance(pub.get("liberada"), bool):
        erros.append("publicacao.liberada ausente ou não booleano (padrão: false)")
    elif pub["liberada"]:
        if not _preenchido(pub.get("liberada_por")):
            erros.append("publicacao.liberada sem liberada_por (quem liberou)")
        if _validar_data_humana(erros, "publicacao.liberada_em", pub.get("liberada_em"), hoje) is None:
            erros.append("publicacao.liberada sem liberada_em")
        if textos_juridicos.empresa_pendente(textos):
            erros.append("publicacao.liberada com a empresa pendente (razão social, CNPJ e e-mail do responsável)")

    fontes: dict[str, dict] = {}
    for f in dados.get("fontes", []):
        fid = f.get("id")
        if not fid or fid in fontes:
            erros.append(f"fonte com id ausente ou repetido: {fid!r}")
            continue
        fontes[fid] = f
        if f.get("origem") not in ORIGENS:
            erros.append(f"fonte {fid}: origem inválida")
        if f.get("licenca") not in LICENCAS:
            erros.append(f"fonte {fid}: licença inválida")
        url = str(f.get("url", ""))
        if not url.startswith("https://"):
            erros.append(f"fonte {fid}: url deve ser https")
        host = url.split("/")[2] if url.count("/") >= 2 else ""
        if any(host == h or host.endswith("." + h) for h in HOSTS_VETADOS):
            erros.append(f"fonte {fid}: {host} tem licença que não permite uso comercial")
        if "cepea" in str(f.get("nome", "")).lower():
            erros.append(f"fonte {fid}: o nome não pode citar o Cepea (parecer 9, item 3)")
        if not isinstance(f.get("ano"), int) or f["ano"] > hoje.year:
            erros.append(f"fonte {fid}: ano inválido")
        if not isinstance(f.get("ativa"), bool):
            erros.append(f"fonte {fid}: 'ativa' ausente ou não booleano")
        if f.get("caminho_parecer") not in CAMINHOS_PARECER:
            erros.append(f"fonte {fid}: caminho_parecer inválido")
        termos = _validar_data_humana(erros, f"fonte {fid}: termos_verificados_em", f.get("termos_verificados_em"), hoje)
        uso = _validar_data_humana(erros, f"fonte {fid}: uso_comercial_confirmado_em", f.get("uso_comercial_confirmado_em"), hoje)
        if uso and not termos:
            erros.append(f"fonte {fid}: uso comercial confirmado sem termos verificados")
        if termos and f.get("licenca") == "nao_verificada":
            erros.append(f"fonte {fid}: termos verificados, mas a licença continua 'nao_verificada'")

    codigos: set[str] = set()
    for r in dados.get("reguas", []):
        cod = r.get("codigo")
        if not cod or cod in codigos:
            erros.append(f"régua com código ausente ou repetido: {cod!r}")
            continue
        codigos.add(cod)
        refs = r.get("fontes", [])
        faltando = [x for x in refs if x not in fontes]
        if faltando:
            erros.append(f"{cod}: fontes inexistentes {faltando}")
        usadas = [fontes[x] for x in refs if x in fontes]
        nac = [f for f in usadas if f["origem"] == "nacional"]
        intl = [f for f in usadas if f["origem"] == "internacional"]
        classe, selo = r.get("classe"), r.get("fidedignidade")
        if classe not in CLASSES:
            erros.append(f"{cod}: classe inválida")
        if selo not in SELOS:
            erros.append(f"{cod}: fidedignidade inválida")
        if classe in CLASSES_COM_FAIXA and not (nac and intl):
            erros.append(f"{cod}: {classe} exige ao menos uma fonte nacional e uma internacional")
        if selo == "alta":
            if classe != "VALIDADA" or len(nac) < 2 or len(intl) < 2:
                erros.append(f"{cod}: selo alta exige VALIDADA com 2 fontes nacionais e 2 internacionais")
            if any(f["ano"] < hoje.year - IDADE_MAXIMA_SELO_ALTO for f in usadas):
                erros.append(f"{cod}: selo alta com fonte de mais de {IDADE_MAXIMA_SELO_ALTO} anos")
        if classe == "NAO_VALIDADA" and (r.get("exibir_faixa") or selo is not None):
            erros.append(f"{cod}: NAO_VALIDADA não pode ter faixa nem selo")
        if r.get("exibir_faixa"):
            if not r.get("faixa"):
                erros.append(f"{cod}: exibir_faixa sem faixa")
            if r.get("condicao_para_exibir"):
                erros.append(f"{cod}: exibir_faixa com condição pendente")
            if classe == "NAO_VALIDADA":
                erros.append(f"{cod}: faixa exibida em régua NAO_VALIDADA")
        if not str(r.get("ressalva", "")).strip():
            erros.append(f"{cod}: ressalva obrigatória")
        if not isinstance(r.get("ativa"), bool):
            erros.append(f"{cod}: 'ativa' ausente ou não booleano")
        erros.extend(_validar_dossie(r, fontes, hoje))
    return erros


def _validar_dossie(r: dict, fontes: dict[str, dict], hoje: date) -> list[str]:
    cod = r["codigo"]
    d = r.get("dossie")
    if not isinstance(d, dict):
        return [f"{cod}: dossiê ausente (parecer 3.5)"]
    erros: list[str] = []
    for lado, origem in (("fonte_br", "nacional"), ("fonte_estrangeira", "internacional")):
        base = d.get(lado)
        if base is None:
            continue
        if not isinstance(base, dict) or set(base) - set(CAMPOS_FONTE_DOSSIE):
            erros.append(f"{cod}: dossie.{lado} deve ter só {list(CAMPOS_FONTE_DOSSIE)}")
            continue
        fid = base.get("fonte_id")
        if fid not in fontes:
            erros.append(f"{cod}: dossie.{lado} aponta fonte inexistente {fid!r}")
        elif fid not in r.get("fontes", []):
            erros.append(f"{cod}: dossie.{lado} ({fid}) não está nas fontes da régua")
        elif fontes[fid].get("origem") != origem:
            erros.append(f"{cod}: dossie.{lado} ({fid}) precisa ser fonte {origem}")
    indep = d.get("independencia") or {}
    if indep.get("sim_nao") not in ("sim", "nao", None):
        erros.append(f"{cod}: dossie.independencia.sim_nao deve ser 'sim', 'nao' ou null")
    grau = (d.get("confiabilidade") or {}).get("grau")
    if grau != r.get("fidedignidade"):
        erros.append(f"{cod}: dossie.confiabilidade.grau ({grau}) diferente do selo da régua ({r.get('fidedignidade')})")
    compilado = _validar_data_humana(erros, f"{cod}: dossie.compilado_em", d.get("compilado_em"), hoje)
    vence = _data(d.get("vence_em"))
    if compilado is None or vence is None:
        erros.append(f"{cod}: dossie.compilado_em e dossie.vence_em obrigatórios")
    elif not (compilado < vence <= _mais_um_ano(compilado)):
        erros.append(f"{cod}: dossie.vence_em deve cair até 12 meses depois da compilação")
    if not _preenchido(d.get("compilado_por")):
        erros.append(f"{cod}: dossie.compilado_por obrigatório")
    validacoes = d.get("validado_por")
    if not isinstance(validacoes, list):
        erros.append(f"{cod}: dossie.validado_por deve ser lista (vazia = ninguém validou)")
        validacoes = []
    pendentes = d.get("pendente_de")
    if not isinstance(pendentes, list):
        erros.append(f"{cod}: dossie.pendente_de deve ser lista")
        pendentes = []
    for v in validacoes:
        if not isinstance(v, dict) or not _preenchido(v.get("nome")):
            erros.append(f"{cod}: cada validação precisa de 'nome', 'em' e 'faixa'")
            continue
        if _mesma_pessoa(v["nome"], d.get("compilado_por")):
            erros.append(f"{cod}: dupla validação — {v['nome']} compilou e não pode validar a mesma faixa")
        em = _validar_data_humana(erros, f"{cod}: validação de {v['nome']}", v.get("em"), hoje)
        if em is None:
            erros.append(f"{cod}: validação de {v['nome']} sem data")
        elif compilado and em < compilado:
            erros.append(f"{cod}: validação de {v['nome']} anterior à compilação")
        if v.get("faixa") != r.get("faixa"):
            erros.append(
                f"{cod}: a faixa mudou depois da validação de {v['nome']} — revalide (e grave a faixa validada) "
                "ou esvazie validado_por"
            )
        if any(_mesma_pessoa(v["nome"], p) for p in pendentes):
            erros.append(f"{cod}: {v['nome']} validou e continua em pendente_de")
    termos = _validar_data_humana(erros, f"{cod}: dossie.termos_verificados_em", d.get("termos_verificados_em"), hoje)
    if termos:
        sem_termos = [x for x in r.get("fontes", []) if x in fontes and fontes[x].get("ativa")
                      and not fontes[x].get("termos_verificados_em")]
        if sem_termos:
            erros.append(f"{cod}: dossie.termos_verificados_em preenchido, mas as fontes {sem_termos} não têm termos verificados")
    return erros


# ---------------------------------------------------------------------------
# Situação de cada régua (o coração dos interruptores).
# ---------------------------------------------------------------------------
def _avaliar_regua(r: dict, fontes: dict[str, dict], hoje: date, vencida_global: bool) -> dict[str, Any]:
    todas = [fontes[x] for x in r.get("fontes", []) if x in fontes]
    ativas = [f for f in todas if f.get("ativa")]
    d = r.get("dossie") or {}

    def _lados(lista):
        return (any(f["origem"] == "nacional" for f in lista), any(f["origem"] == "internacional" for f in lista))

    saida: dict[str, Any] = {"codigo": r["codigo"], "fontes_ativas": ativas, "motivos": [], "publicavel": False}

    def _fim(situacao: str, *motivos: str) -> dict[str, Any]:
        saida["situacao"] = situacao
        saida["motivos"].extend(motivos)
        return saida

    if not r.get("ativa"):
        return _fim("retirada", "régua desligada pelo interruptor da régua (ativa = false)")
    if not (r.get("exibir_faixa") and r.get("faixa") and not r.get("condicao_para_exibir")
            and r.get("classe") in CLASSES_COM_FAIXA):
        return _fim("sem_faixa", "a régua não tem faixa por desenho (classe, exibir_faixa ou condição pendente)")
    if _lados(todas) != (True, True):
        return _fim("sem_faixa", "falta fonte nacional ou internacional")
    if _lados(ativas) != (True, True):
        return _fim("retirada", "fonte desligada: a régua ficou sem fonte nacional ou internacional ativa")
    ids_ativos = {f["id"] for f in ativas}
    for lado in ("fonte_br", "fonte_estrangeira"):
        fid = (d.get(lado) or {}).get("fonte_id")
        if fid and fid not in ids_ativos:
            return _fim("retirada", f"fonte base do dossiê ({fid}) foi desligada")
    vence = _data(d.get("vence_em"))
    if vencida_global or vence is None or hoje > vence:
        return _fim("vencida", "prazo de validade vencido (12 meses)")

    pend: list[str] = []
    for campo in ("indicador", "faixa_publicada", "metodo_agregacao", "compilado_por"):
        if not _preenchido(d.get(campo)):
            pend.append(f"dossiê sem {campo}")
    for lado in ("fonte_br", "fonte_estrangeira"):
        base = d.get(lado)
        if not isinstance(base, dict):
            pend.append(f"dossiê sem {lado}")
            continue
        for campo in CAMPOS_FONTE_DOSSIE:
            if not _preenchido(base.get(campo)):
                pend.append(f"dossiê: {lado} sem {campo}")
        if fontes.get(base.get("fonte_id"), {}).get("caminho_parecer") == "corroboracao_apenas":
            pend.append(f"dossiê: {lado} ({base.get('fonte_id')}) só serve como corroboração, não como base (parecer 3.3)")
    indep = d.get("independencia") or {}
    if indep.get("sim_nao") != "sim" or not _preenchido(indep.get("justificativa")):
        pend.append("independência entre a fonte BR e a estrangeira não comprovada")
    conf = d.get("confiabilidade") or {}
    if not (_preenchido(conf.get("grau")) and _preenchido(conf.get("criterio"))):
        pend.append("dossiê sem grau de confiabilidade e critério")
    validas = [v for v in d.get("validado_por") or [] if isinstance(v, dict)
               and not _mesma_pessoa(v.get("nome"), d.get("compilado_por")) and v.get("faixa") == r.get("faixa")]
    if not validas:
        pend.append("falta a validação por pessoa diferente de quem compilou")
    if d.get("pendente_de"):
        pend.append("validação pendente de: " + ", ".join(map(str, d["pendente_de"])))
    if not d.get("termos_verificados_em"):
        pend.append("dossiê sem data de verificação dos termos das fontes")
    for f in ativas:
        if not f.get("termos_verificados_em") or not f.get("uso_comercial_confirmado_em"):
            extra = " — o parecer recomenda excluir por ora" if f.get("caminho_parecer") == "excluir_por_ora" else ""
            pend.append(f"fonte {f['id']}: termos ou uso comercial não verificados{extra}")
    if pend:
        return _fim("em_validacao", *pend)
    saida["publicavel"] = True
    return _fim("publicada")


def avaliar(dados: Optional[dict[str, Any]] = None, hoje: Optional[date] = None,
            textos: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Situação de cada régua, com os motivos (uso interno: Painel CowData,
    testes, rotina). A carga pública (`publico`) sai daqui, sem os motivos."""
    dados = dados or carregar()
    hoje = hoje or date.today()
    textos = textos or textos_juridicos.dados_padrao()
    vence = _data(dados.get("valido_ate"))
    vencida = vence is None or hoje > vence
    fontes = {f["id"]: f for f in dados.get("fontes", [])}
    empresa_pendente = textos_juridicos.empresa_pendente(textos)
    liberada = bool((dados.get("publicacao") or {}).get("liberada")) and not empresa_pendente
    reguas = []
    for r in dados.get("reguas", []):
        a = _avaliar_regua(r, fontes, hoje, vencida)
        if a["situacao"] == "publicada" and not liberada:
            a["situacao"] = "em_validacao"
            a["motivos"].append(
                "empresa pendente" if empresa_pendente else "publicação geral não liberada (publicacao.liberada = false)"
            )
        reguas.append(a)
    return {"vencida": vencida, "liberada": liberada, "empresa_pendente": empresa_pendente, "reguas": reguas}


def diagnostico(dados: Optional[dict[str, Any]] = None, hoje: Optional[date] = None) -> dict[str, Any]:
    """O que falta para cada régua ir ao ar — para o Painel CowData e para o dono."""
    dados = dados or carregar()
    av = avaliar(dados, hoje)
    return {
        "versao_reguas": versao_reguas(dados),
        "publicacao": dados.get("publicacao"),
        "liberada_efetiva": av["liberada"],
        "empresa_pendente": av["empresa_pendente"],
        "vencida": av["vencida"],
        "reguas": [
            {"codigo": a["codigo"], "situacao": a["situacao"], "publicavel": a["publicavel"], "motivos": a["motivos"]}
            for a in av["reguas"]
        ],
    }


# ---------------------------------------------------------------------------
# Carga pública (o que a tela consome).
# ---------------------------------------------------------------------------
def textos_da_tela(dados: dict[str, Any], incluir_trecho_metodo: bool,
                   textos: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    textos = textos or textos_juridicos.dados_padrao()
    revisao = _br(_data(dados.get("revisado_em")))
    return {
        "alerta": textos_juridicos.descrever("reguas_alerta", {"ultima_revisao": revisao}, dados=textos),
        "modal": textos_juridicos.descrever("reguas_modal", incluir_trecho_metodo=incluir_trecho_metodo, dados=textos),
        "compartilhamento_parametro": textos_juridicos.descrever("compartilhamento_parametro", dados=textos),
        # Modelos com marcadores ({{gerado_em}}, {{destinatario}}...): o texto
        # preenchido sai de POST /relatorios/exportacoes.
        "rodape_exportacao": textos_juridicos.descrever("reguas_rodape_exportacao", dados=textos),
        "exportacao_autorizacao": textos_juridicos.descrever("exportacao_autorizacao", dados=textos),
    }


def texto_modal_vigente(dados: Optional[dict[str, Any]] = None, hoje: Optional[date] = None,
                        textos: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """O texto do modal "Entendi" vigente AGORA (versão + hash) — é o que o
    aceite de réguas referencia. O trecho do método entra só com régua publicada."""
    dados = dados or carregar()
    av = avaliar(dados, hoje, textos)
    algum = any(a["situacao"] == "publicada" for a in av["reguas"])
    return textos_juridicos.descrever("reguas_modal", incluir_trecho_metodo=algum, dados=textos)


def publico(dados: Optional[dict[str, Any]] = None, hoje: Optional[date] = None,
            textos: Optional[dict[str, Any]] = None, ocultar_faixas: bool = False) -> dict[str, Any]:
    """Carga que a tela consome. Régua fora de "publicada" (ou `ocultar_faixas`,
    usado enquanto o aceite do modal está pendente) nunca leva faixa, ressalva
    nem fontes."""
    dados = dados or carregar()
    hoje = hoje or date.today()
    textos = textos or textos_juridicos.dados_padrao()
    av = avaliar(dados, hoje, textos)
    por_codigo = {a["codigo"]: a for a in av["reguas"]}
    algum_publicado = any(a["situacao"] == "publicada" for a in av["reguas"])
    reguas = []
    for r in dados["reguas"]:
        a = por_codigo[r["codigo"]]
        mostrar = a["situacao"] == "publicada" and not ocultar_faixas
        d = r.get("dossie") or {}
        reguas.append({
            "codigo": r["codigo"],
            "nome": r.get("nome"),
            "unidade": r.get("unidade"),
            "definicao_cowdata": r.get("definicao_cowdata"),
            "situacao": a["situacao"],
            "publicavel": a["publicavel"],
            "exibir_faixa": mostrar,
            "faixa": r.get("faixa") if mostrar else None,
            "fidedignidade": r.get("fidedignidade") if mostrar else None,
            "ressalva": r.get("ressalva") if mostrar else None,
            "compilado_em": d.get("compilado_em") if mostrar else None,
            "vence_em": d.get("vence_em") if mostrar else None,
            "fontes": [
                {k: f.get(k) for k in ("id", "nome", "ano", "url", "origem")} for f in a["fontes_ativas"]
            ] if mostrar else [],
        })
    return {
        "versao": dados["versao"],
        "versao_reguas": versao_reguas(dados),
        "revisado_em": dados["revisado_em"],
        "conferida_em": dados["conferida_em"],
        "valido_ate": dados["valido_ate"],
        "proxima_conferencia": dados["proxima_conferencia"],
        "vencida": av["vencida"],
        "publicacao": {"liberada": av["liberada"]},
        "empresa_pendente": av["empresa_pendente"],
        "faixas_ocultas_ate_aceite": bool(ocultar_faixas),
        "textos": textos_da_tela(dados, incluir_trecho_metodo=algum_publicado, textos=textos),
        "reguas": reguas,
    }


def alguma_publicada(dados: Optional[dict[str, Any]] = None, hoje: Optional[date] = None) -> bool:
    return any(a["situacao"] == "publicada" for a in avaliar(dados, hoje)["reguas"])
