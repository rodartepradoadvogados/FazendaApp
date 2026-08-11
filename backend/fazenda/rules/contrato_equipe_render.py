"""
Geração dos contratos da Equipe CowData — CLT (empregado) e prestação de
serviços (PJ) — a partir do cadastro de `Pessoa` no Painel CowData.

Difere de `contrato_render.py` (contrato de fazenda-cliente) em dois pontos
propositais:

  - são DOIS documentos com invólucro visual idêntico e corpo jurídico
    completamente distinto, então usamos herança Jinja2 (Environment com
    FileSystemLoader) em vez de `Template(arquivo.read_text())` — sem
    loader, `{% extends %}` não funciona;
  - só há saída HTML. O contrato de fazenda-cliente também gera markdown
    porque é enviado ao ZapSign; aqui o pedido é o botão "Baixar contrato",
    e duplicar o texto jurídico em dois formatos garantiria divergência
    entre eles na primeira alteração de cláusula.

Todo campo que o cadastro não tem sai como "[PREENCHER — ...]" destacado em
vermelho no HTML, mesmo padrão do contrato de fazenda-cliente: a minuta
nunca deixa de ser gerada por falta de dado, ela mostra o que falta.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from fazenda.models import Pessoa
from fazenda.models.multitenant import EmpresaOperadora

_DIR_TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

_AMBIENTE = Environment(
    loader=FileSystemLoader(str(_DIR_TEMPLATES)),
    autoescape=select_autoescape(["html"]),
)

TEMPLATE_POR_VINCULO = {"funcionario": "contrato_equipe_clt.html", "pj": "contrato_equipe_pj.html"}

# Padrões quando o cadastro não define — todos sobrescrevíveis por query
# string no endpoint (mesmo espírito do /fazendas/{id}/contrato/modelo).
JORNADA_SEMANAL_PADRAO = 44  # art. 7º, XIII, da Constituição Federal
EXPERIENCIA_DIAS_PADRAO = 90  # teto do art. 445, parágrafo único, da CLT
DIA_PAGAMENTO_PJ_PADRAO = 10
VIGENCIA_PJ_PADRAO = "12 (doze) meses"

_GENEROS_FEMININOS = {"feminino", "feminina", "mulher", "f"}
_GENEROS_MASCULINOS = {"masculino", "homem", "m"}

DESCRICAO_PORTE = {
    "MEI": "microempreendedor individual (MEI)",
    "ME": "microempresa (ME)",
    "EPP": "empresa de pequeno porte (EPP)",
}
DESCRICAO_PORTE_PADRAO = "pessoa jurídica de direito privado"


def _genero(pessoa: Pessoa) -> str:
    """"m" | "f" | "" (neutro). Gênero é campo de texto livre e nunca
    obrigatório — sem ele, o contrato usa a forma dupla "EMPREGADO(A)"."""
    bruto = (pessoa.genero or "").strip().lower()
    if bruto in _GENEROS_FEMININOS:
        return "f"
    if bruto in _GENEROS_MASCULINOS:
        return "m"
    return ""


def _flexao(genero: str, masculino: str, feminino: str, neutro: str) -> str:
    return {"m": masculino, "f": feminino}.get(genero, neutro)


_UNIDADES = [
    "zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez",
    "onze", "doze", "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove",
]
_DEZENAS = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
_CENTENAS = [
    "", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos",
    "seiscentos", "setecentos", "oitocentos", "novecentos",
]


def por_extenso(n: int) -> str:
    """Inteiro de 0 a 999 por extenso — só o suficiente para jornada semanal
    e dias de experiência, que é onde o contrato exige o número escrito."""
    if n < 0 or n > 999:
        return str(n)
    if n < 20:
        return _UNIDADES[n]
    if n < 100:
        dezena, unidade = divmod(n, 10)
        return _DEZENAS[dezena] + (f" e {_UNIDADES[unidade]}" if unidade else "")
    if n == 100:
        return "cem"
    centena, resto = divmod(n, 100)
    return _CENTENAS[centena] + (f" e {por_extenso(resto)}" if resto else "")


def _moeda(valor: Optional[float]) -> str:
    if valor is None:
        return "[PREENCHER — valor]"
    return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _data_br(valor: Optional[date]) -> Optional[str]:
    return valor.strftime("%d/%m/%Y") if valor else None


def _endereco_completo(pessoa: Pessoa) -> Optional[str]:
    """Junta o endereço estruturado numa linha só. Devolve None quando não
    há nada — aí o template mostra o "[PREENCHER]" destacado."""
    logradouro = ", ".join(p for p in (pessoa.endereco_rua, pessoa.endereco_numero) if p)
    cidade_uf = "/".join(p for p in (pessoa.endereco_cidade, pessoa.endereco_uf) if p)
    partes = [p for p in (logradouro, pessoa.endereco_bairro, cidade_uf) if p]
    if pessoa.cep:
        partes.append(f"CEP {pessoa.cep}")
    return ", ".join(partes) or None


def _documento_rotulo(documento: Optional[str]) -> str:
    """CNPJ tem 14 dígitos, CPF tem 11 — o cadastro guarda os dois no mesmo
    campo `cpf_cnpj`, então o rótulo do contrato sai do próprio número."""
    digitos = re.sub(r"\D", "", documento or "")
    return "CPF" if len(digitos) == 11 else "CNPJ"


def _contexto_comum(pessoa: Pessoa, empresa: Optional[EmpresaOperadora], cidade_foro: str | None, estado_foro: str | None) -> dict:
    return {
        "empresa_nome": empresa.nome if empresa else "CowData",
        "empresa_cnpj": empresa.cnpj if empresa else None,
        "empresa_endereco": empresa.endereco if empresa else None,
        "pessoa_nome": pessoa.nome,
        "cpf": pessoa.cpf_cnpj,
        "rg": pessoa.rg,
        "estado_civil": pessoa.estado_civil,
        "endereco_completo": _endereco_completo(pessoa),
        "cidade_foro": cidade_foro or pessoa.endereco_cidade,
        "estado_foro": estado_foro or pessoa.endereco_uf,
        "data_hoje": date.today().strftime("%d/%m/%Y"),
    }


def _contexto_clt(pessoa: Pessoa, funcao: str | None, local_prestacao: str | None,
                  jornada_semanal: int | None, experiencia_dias: int | None) -> dict:
    g = _genero(pessoa)
    jornada = jornada_semanal or JORNADA_SEMANAL_PADRAO
    experiencia = experiencia_dias or EXPERIENCIA_DIAS_PADRAO
    return {
        "rotulo_empregado": _flexao(g, "EMPREGADO", "EMPREGADA", "EMPREGADO(A)"),
        "artigo_o": _flexao(g, "o", "a", "o(a)"),
        "artigo_ao": _flexao(g, "ao", "à", "ao(à)"),
        "artigo_do": _flexao(g, "do", "da", "do(a)"),
        "artigo_pelo": _flexao(g, "pelo", "pela", "pelo(a)"),
        "flexao_nacionalidade": _flexao(g, "brasileiro", "brasileira", "brasileiro(a)"),
        "flexao_portador": _flexao(g, "portador", "portadora", "portador(a)"),
        "flexao_inscrito": _flexao(g, "inscrito", "inscrita", "inscrito(a)"),
        "flexao_residente": _flexao(g, "residente e domiciliado", "residente e domiciliada", "residente e domiciliado(a)"),
        "flexao_denominado": _flexao(g, "denominado", "denominada", "denominado(a)"),
        "funcao": funcao or pessoa.tipo or "[PREENCHER — função]",
        "local_prestacao": local_prestacao or "[PREENCHER — local de prestação dos serviços]",
        "data_admissao": _data_br(pessoa.data_admissao),
        "jornada_semanal": jornada,
        "jornada_semanal_extenso": por_extenso(jornada),
        "experiencia_dias": experiencia,
        "experiencia_dias_extenso": por_extenso(experiencia),
        "salario": _moeda(pessoa.salario_base),
    }


def _contexto_pj(pessoa: Pessoa, objeto_servico: str | None, dia_pagamento: int | None,
                 vigencia: str | None, representante_nome: str | None, representante_cpf: str | None) -> dict:
    return {
        "descricao_porte": DESCRICAO_PORTE.get(pessoa.subtipo_pj or "", DESCRICAO_PORTE_PADRAO),
        "subtipo_pj": pessoa.subtipo_pj,
        "documento_rotulo": _documento_rotulo(pessoa.cpf_cnpj),
        "objeto_servico": objeto_servico or pessoa.tipo or "[PREENCHER — descrição dos serviços]",
        "pagamento_mensal": _moeda(pessoa.pagamento_mensal),
        "dia_pagamento": dia_pagamento or DIA_PAGAMENTO_PJ_PADRAO,
        "vigencia": vigencia or VIGENCIA_PJ_PADRAO,
        "representante_nome": representante_nome,
        "representante_cpf": representante_cpf,
    }


def render_contrato_equipe(
    pessoa: Pessoa,
    empresa: Optional[EmpresaOperadora] = None,
    *,
    funcao: str | None = None,
    local_prestacao: str | None = None,
    jornada_semanal: int | None = None,
    experiencia_dias: int | None = None,
    objeto_servico: str | None = None,
    dia_pagamento: int | None = None,
    vigencia: str | None = None,
    representante_nome: str | None = None,
    representante_cpf: str | None = None,
    cidade_foro: str | None = None,
    estado_foro: str | None = None,
) -> str:
    """Minuta em HTML do contrato do membro da Equipe CowData, escolhida pelo
    `tipo_vinculo` da Pessoa. Levanta ValueError quando o vínculo não está
    definido — é o cadastro que decide qual dos dois contratos existe, e
    gerar o "contrato errado" seria pior do que recusar."""
    template_nome = TEMPLATE_POR_VINCULO.get(pessoa.tipo_vinculo or "")
    if not template_nome:
        raise ValueError(
            "Defina o tipo de vínculo do membro (funcionário ou PJ) antes de gerar o contrato"
        )

    contexto = _contexto_comum(pessoa, empresa, cidade_foro, estado_foro)
    if pessoa.tipo_vinculo == "funcionario":
        contexto.update(_contexto_clt(pessoa, funcao, local_prestacao, jornada_semanal, experiencia_dias))
    else:
        contexto.update(_contexto_pj(pessoa, objeto_servico, dia_pagamento, vigencia, representante_nome, representante_cpf))
    return _AMBIENTE.get_template(template_nome).render(**contexto)


def nome_arquivo_contrato(pessoa: Pessoa) -> str:
    """Nome do arquivo baixado — sem acento/espaço, para não depender de como
    cada navegador trata Content-Disposition com caractere não-ASCII. Os
    acentos viram a letra base ("José" → "jose"), em vez de sumirem."""
    sem_acento = unicodedata.normalize("NFKD", pessoa.nome or "membro").encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9]+", "-", sem_acento).strip("-").lower() or "membro"
    sufixo = "clt" if pessoa.tipo_vinculo == "funcionario" else "pj"
    return f"contrato-{sufixo}-{base}.html"
