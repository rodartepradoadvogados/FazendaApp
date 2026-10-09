"""
Textos jurídicos versionados (parecer de 08/10/2026, item 7) e a identidade de
cada um para fins de aceite: versão + SHA-256 do texto normalizado.

Os textos moram em `seed_data/textos_juridicos.json`, versionado no git e editado
só por humanos (PR revisado pelo dono). O código nunca escreve texto jurídico:
lê o modelo, troca os marcadores `{{...}}` e devolve o texto exato que a tela
mostra, junto com o hash desse texto. O aceite (tabela `aceite_termos`) guarda a
versão e o hash do que a pessoa viu; texto novo = hash novo = aceite novo.

Marcadores:
- `{{razao_social}}` / `{{email_responsavel}}`: vêm do bloco `empresa`. A empresa
  ainda não existe (parecer, item 8): enquanto `razao_social`, `cnpj` ou
  `email_responsavel` estiverem vazios, `empresa_pendente()` é verdadeiro, a
  publicação das réguas fica travada (ver rules/reguas_referencia.py) e o texto
  sai com o nome do produto e um aviso de pendência no lugar do e-mail;
- `{{trecho_metodo}}`: trecho CONDICIONAL do pop-up (parecer 7.2) — só entra
  quando o chamador afirma que o dossiê o comprova;
- os demais (`{{gerado_em}}`, `{{usuario}}`, `{{destinatario}}`,
  `{{versao_reguas}}`, `{{ultima_revisao}}`...) são preenchidos por quem renderiza.

Normalização para o hash (`normalizar`): Unicode NFC, quebras de linha `\\n`,
sem espaço no fim das linhas, sem linhas em branco nas pontas. É o mesmo texto
que a pessoa lê; a normalização só impede que um espaço invisível mude o hash.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

ARQUIVO = Path(__file__).resolve().parent.parent / "seed_data" / "textos_juridicos.json"

# Tipo de aceite (coluna `aceite_termos.tipo`) -> chave do texto que ele aceita.
TIPOS_ACEITE = {"geral": "termos_aceite", "clausula": "termos_clausula_aceite", "reguas": "reguas_modal"}

MARCADOR = re.compile(r"\{\{([a-z_]+)\}\}")
MARCADORES_CONHECIDOS = {
    "razao_social", "email_responsavel", "ultima_revisao", "trecho_metodo",
    "gerado_em", "usuario", "destinatario", "versao_reguas",
    "versao_termos", "data_termos", "clausula",
}
EMAIL_PENDENTE = "[e-mail do responsável: pendente]"


def carregar() -> dict[str, Any]:
    with open(ARQUIVO, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _carregado() -> dict[str, Any]:
    return carregar()


def dados_padrao() -> dict[str, Any]:
    """O arquivo versionado (lido uma vez por processo: só muda com deploy)."""
    return _carregado()


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFC", texto or "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(linha.rstrip() for linha in texto.split("\n")).strip()


def sha256(texto: str) -> str:
    return hashlib.sha256(normalizar(texto).encode("utf-8")).hexdigest()


def empresa_pendente(dados: Optional[dict[str, Any]] = None) -> bool:
    emp = (dados or dados_padrao()).get("empresa") or {}
    return not all(str(emp.get(k) or "").strip() for k in ("razao_social", "cnpj", "email_responsavel"))


def _valores_empresa(dados: dict[str, Any]) -> dict[str, str]:
    emp = dados.get("empresa") or {}
    return {
        "razao_social": (emp.get("razao_social") or "").strip() or emp.get("nome_produto") or "CowData",
        "email_responsavel": (emp.get("email_responsavel") or "").strip() or EMAIL_PENDENTE,
    }


def renderizar(chave: str, valores: Optional[dict[str, str]] = None, *, incluir_trecho_metodo: bool = False,
               dados: Optional[dict[str, Any]] = None) -> str:
    """Texto final de `chave`, com os marcadores trocados. Marcador sem valor
    fica como está (`{{x}}`) — o modelo devolvido por `vigentes()` é assim."""
    dados = dados or dados_padrao()
    item = dados["textos"][chave]
    subst = {**_valores_empresa(dados), **(valores or {})}
    trecho = ((item.get("condicionais") or {}).get("trecho_metodo") or {}).get("texto", "")
    subst["trecho_metodo"] = (" " + trecho) if (incluir_trecho_metodo and trecho) else ""

    def _troca(m: re.Match) -> str:
        nome = m.group(1)
        return str(subst[nome]) if nome in subst and subst[nome] is not None else m.group(0)

    return normalizar(MARCADOR.sub(_troca, item["modelo"]))


def descrever(chave: str, valores: Optional[dict[str, str]] = None, *, incluir_trecho_metodo: bool = False,
              dados: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """O texto como a API entrega: versão, texto renderizado e o SHA-256 dele."""
    dados = dados or dados_padrao()
    item = dados["textos"][chave]
    texto = renderizar(chave, valores, incluir_trecho_metodo=incluir_trecho_metodo, dados=dados)
    saida = {
        "chave": chave,
        "versao": item["versao"],
        "vigente_desde": item["vigente_desde"],
        "texto": texto,
        "sha256": sha256(texto),
        "aceite": item.get("aceite"),
        "disponivel_para_aceite": bool(item.get("aceite")) and not item.get("pendente"),
        "pendente": item.get("pendente"),
    }
    if item.get("botao"):
        saida["botao"] = item["botao"]
    return saida


def validar(dados: dict[str, Any]) -> list[str]:
    """Problemas do arquivo de textos (vazia = válido). O CI roda isto."""
    erros: list[str] = []
    if "empresa" not in dados or not isinstance(dados["empresa"], dict):
        erros.append("bloco 'empresa' ausente")
    textos = dados.get("textos") or {}
    for tipo, chave in TIPOS_ACEITE.items():
        if chave not in textos:
            erros.append(f"texto {chave} (aceite {tipo}) ausente")
        elif textos[chave].get("aceite") != tipo:
            erros.append(f"texto {chave}: campo 'aceite' deve ser {tipo!r}")
    for chave, item in textos.items():
        for campo in ("versao", "vigente_desde", "origem", "modelo"):
            if not str(item.get(campo) or "").strip():
                erros.append(f"texto {chave}: '{campo}' obrigatório")
        modelo = item.get("modelo") or ""
        desconhecidos = set(MARCADOR.findall(modelo)) - MARCADORES_CONHECIDOS
        if desconhecidos:
            erros.append(f"texto {chave}: marcador desconhecido {sorted(desconhecidos)}")
        if "[" in modelo and re.search(r"\[[^\]]*(raz[aã]o social|e-mail|CowData/)", modelo):
            erros.append(f"texto {chave}: placeholder entre colchetes; use {{{{marcador}}}}")
        esperado = sha256(modelo)
        if item.get("sha256_modelo") != esperado:
            erros.append(
                f"texto {chave}: modelo mudou e a versão não foi registrada — suba 'versao', mova a anterior "
                f"para 'historico' e grave sha256_modelo = {esperado}"
            )
    alerta = (textos.get("reguas_alerta") or {}).get("modelo", "")
    if re.search(r"cepea", alerta, re.IGNORECASE):
        erros.append("reguas_alerta: a caixa de alerta não pode citar o Cepea (parecer 7.1)")
    if "{{trecho_metodo}}" in alerta:
        erros.append("reguas_alerta: o trecho do método só pode entrar no pop-up (parecer 7.1)")
    vistos = set()
    for h in dados.get("historico") or []:
        par = (h.get("chave"), h.get("versao"))
        if par in vistos:
            erros.append(f"historico: versão repetida {par}")
        vistos.add(par)
        if par[0] in textos and textos[par[0]].get("versao") == par[1]:
            erros.append(f"historico: {par} é a versão vigente; o histórico guarda só as anteriores")
        if not h.get("vigente_ate") or not h.get("modelo"):
            erros.append(f"historico {par}: 'modelo' e 'vigente_ate' obrigatórios")
    return erros
