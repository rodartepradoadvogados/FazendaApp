"""
Leitura de extrato bancário — OFX (1.x SGML e 2.x XML) e CSV dos bancos
brasileiros mais comuns (Banco do Brasil, Sicredi, Sicoob, Itaú, Bradesco,
Santander, Caixa, Inter, Nubank). Parser PRÓPRIO, sem dependência nova: o
que importa é data, valor com sinal, histórico, nº do documento e (quando o
banco informa) o saldo do fim do extrato.

Funções PURAS: recebem os bytes do arquivo e devolvem `ExtratoLido`. Quem
grava (`ExtratoLinha`) é o router de conciliação.

CSV: o cabeçalho é achado nas primeiras linhas pelos nomes de coluna
(data; histórico/descrição/lançamento/detalhes; valor OU crédito+débito;
documento; saldo; tipo D/C). Números no formato brasileiro ("1.234,56",
"-68,00", "68,00 D", "(68,00)") ou americano ("1234.56"). Linhas de saldo
("Saldo anterior", "S A L D O", "Saldo do dia") NÃO são movimento: viram o
saldo informado pelo banco.

A chave de deduplicação é estável entre importações do mesmo extrato: o
FITID no OFX (com data e valor, porque há banco que repete FITID); no CSV, um
hash de (data, valor, histórico, documento) + a ordem da ocorrência daquela
mesma combinação no arquivo — duas tarifas iguais no mesmo dia continuam
sendo duas linhas, e reimportar o arquivo (ou um período que se sobrepõe)
não duplica nada.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

LIMITE_HISTORICO = 120


@dataclass
class MovimentoExtrato:
    data: date
    valor: float  # entrada > 0, saída < 0
    historico: str
    documento: str | None
    chave: str


@dataclass
class ExtratoLido:
    formato: str  # "ofx" | "csv"
    movimentos: list[MovimentoExtrato] = field(default_factory=list)
    saldo_final: float | None = None
    data_saldo: date | None = None
    avisos: list[str] = field(default_factory=list)

    @property
    def data_inicio(self) -> date | None:
        return min((m.data for m in self.movimentos), default=None)

    @property
    def data_fim(self) -> date | None:
        return max((m.data for m in self.movimentos), default=None)


class ExtratoInvalido(ValueError):
    """Arquivo que não é extrato reconhecível (mensagem para a tela)."""


# ── utilitários ────────────────────────────────────────────────────────────
def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def normalizar(texto: str | None) -> str:
    return re.sub(r"\s+", " ", _sem_acento(texto or "").lower()).strip()


def decodificar(conteudo: bytes) -> str:
    for cod in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return conteudo.decode(cod)
        except UnicodeDecodeError:
            continue
    return conteudo.decode("latin-1", errors="replace")  # pragma: no cover - latin-1 nunca falha


def ler_numero(texto: str | None) -> float | None:
    """Número de extrato em qualquer dos formatos comuns. None se não for número."""
    if texto is None:
        return None
    s = str(texto).strip()
    if not s:
        return None
    negativo = False
    s = s.replace("R$", "").replace(" ", " ").strip()
    if s.startswith("(") and s.endswith(")"):
        negativo, s = True, s[1:-1].strip()
    sufixo = re.search(r"\s*([DdCc])$", s)
    if sufixo and re.search(r"\d", s[: sufixo.start()]):
        negativo = negativo or sufixo.group(1).upper() == "D"
        s = s[: sufixo.start()].strip()
    if s.endswith("-"):
        negativo, s = True, s[:-1].strip()
    if s.startswith("-"):
        negativo, s = not negativo, s[1:].strip()
    elif s.startswith("+"):
        s = s[1:].strip()
    s = s.replace(" ", "")
    if not re.fullmatch(r"[\d.,]+", s) or not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    elif "." in s and len(s.split(".")[1]) == 3 and len(s.split(".")[0]) <= 3:
        # "1.234" num extrato brasileiro é mil duzentos e trinta e quatro.
        s = s.replace(".", "")
    try:
        valor = float(s)
    except ValueError:
        return None
    return round(-valor if negativo else valor, 2)


_FORMATOS_DATA = (
    (re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})"), "dmy"),
    (re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})"), "ymd"),
    (re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2})(?!\d)"), "dmy2"),
)


def ler_data(texto: str | None) -> date | None:
    s = (texto or "").strip()
    for rx, ordem in _FORMATOS_DATA:
        m = rx.match(s)
        if not m:
            continue
        a, b, c = (int(x) for x in m.groups())
        try:
            if ordem == "dmy":
                return date(c, b, a)
            if ordem == "ymd":
                return date(a, b, c)
            return date(2000 + c, b, a)
        except ValueError:
            return None
    return None


def _cortar(texto: str) -> str:
    texto = re.sub(r"\s+", " ", texto or "").strip()
    return texto[:LIMITE_HISTORICO]


def _chave_csv(d: date, valor: float, historico: str, documento: str | None, ordem: int) -> str:
    base = f"{d.isoformat()}|{valor:.2f}|{normalizar(historico)}|{(documento or '').strip()}|{ordem}"
    return "csv:" + hashlib.sha1(base.encode("utf-8")).hexdigest()


def eh_linha_de_saldo(historico: str) -> bool:
    h = normalizar(historico).replace(" ", "")
    return h.startswith("saldo") or "s a l d o" in normalizar(historico) or h in ("saldoanterior", "saldododia", "saldofinal")


# ── OFX ────────────────────────────────────────────────────────────────────
def _tag(bloco: str, nome: str) -> str | None:
    m = re.search(rf"<{nome}>\s*([^<\r\n]*)", bloco, flags=re.IGNORECASE)
    return m.group(1).strip() if m else None


def _data_ofx(texto: str | None) -> date | None:
    m = re.match(r"(\d{4})(\d{2})(\d{2})", (texto or "").strip())
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def ler_ofx(texto: str) -> ExtratoLido:
    lido = ExtratoLido(formato="ofx")
    blocos = re.findall(r"<STMTTRN>(.*?)</STMTTRN>", texto, flags=re.IGNORECASE | re.DOTALL)
    if not blocos:
        # SGML sem fechamento do agregado (raro): corta de um <STMTTRN> ao próximo.
        partes = re.split(r"<STMTTRN>", texto, flags=re.IGNORECASE)[1:]
        blocos = [re.split(r"</BANKTRANLIST>|<LEDGERBAL>", p, flags=re.IGNORECASE)[0] for p in partes]
    vistos: dict[str, int] = {}
    for bloco in blocos:
        d = _data_ofx(_tag(bloco, "DTPOSTED"))
        valor = ler_numero(_tag(bloco, "TRNAMT"))
        if d is None or valor is None or valor == 0:
            continue
        memo = _tag(bloco, "MEMO") or ""
        nome = _tag(bloco, "NAME") or ""
        partes = [nome] if nome else []
        if memo and normalizar(memo) != normalizar(nome):
            partes.append(memo)
        historico = _cortar(" · ".join(partes))
        documento = _tag(bloco, "CHECKNUM") or _tag(bloco, "REFNUM") or None
        fitid = _tag(bloco, "FITID")
        if fitid:
            chave = f"ofx:{fitid}:{d.isoformat()}:{valor:.2f}"
        else:
            base = (d, valor, historico, documento)
            vistos[str(base)] = vistos.get(str(base), 0) + 1
            chave = _chave_csv(d, valor, historico, documento, vistos[str(base)])
        lido.movimentos.append(MovimentoExtrato(d, valor, historico, (documento or None), chave))
    bal = re.search(r"<LEDGERBAL>(.*?)(</LEDGERBAL>|<AVAILBAL>|</STMTRS>|$)", texto, flags=re.IGNORECASE | re.DOTALL)
    if bal:
        lido.saldo_final = ler_numero(_tag(bal.group(1), "BALAMT"))
        lido.data_saldo = _data_ofx(_tag(bal.group(1), "DTASOF"))
    if lido.saldo_final is not None and lido.data_saldo is None:
        lido.data_saldo = lido.data_fim
    if not lido.movimentos and lido.saldo_final is None:
        raise ExtratoInvalido("O arquivo OFX não tem nenhum movimento (<STMTTRN>) nem saldo.")
    return lido


# ── CSV ────────────────────────────────────────────────────────────────────
_COL_DATA = ("data", "data lancamento", "data do lancamento", "data movimento", "data mov", "dt", "data da transacao", "data transacao", "dt. lancamento", "data lanc.")
_COL_HIST = ("historico", "descricao", "lancamento", "detalhes", "memo", "titulo", "descricao do lancamento", "complemento", "estabelecimento")
_COL_DOC = ("documento", "n documento", "no documento", "nº documento", "n° documento", "num documento", "numero documento", "doc", "docto", "nr. documento", "identificador", "numero do documento")
_COL_VALOR = ("valor", "valor (r$)", "valor r$", "valor(r$)", "quantia", "montante", "valor lancamento")
_COL_CRED = ("credito", "credito (r$)", "entrada", "entradas", "valor credito")
_COL_DEB = ("debito", "debito (r$)", "saida", "saidas", "valor debito")
_COL_SALDO = ("saldo", "saldo (r$)", "saldo r$", "saldo do dia")
_COL_TIPO = ("tipo", "tipo lancamento", "d/c", "dc", "natureza", "c/d", "tipo de lancamento")


def _achar(cab: list[str], nomes: tuple[str, ...]) -> list[int]:
    return [i for i, c in enumerate(cab) if c in nomes]


def _delimitador(texto: str) -> str:
    linhas = [l for l in texto.splitlines() if l.strip()][:15]
    contagem = {d: sum(l.count(d) for l in linhas) for d in (";", ",", "\t")}
    if contagem[";"] >= max(1, len(linhas) // 2):
        return ";"
    if contagem["\t"] >= max(1, len(linhas) // 2):
        return "\t"
    return ","


def ler_csv(texto: str) -> ExtratoLido:
    lido = ExtratoLido(formato="csv")
    linhas = list(csv.reader(io.StringIO(texto), delimiter=_delimitador(texto)))
    cab_idx = None
    for i, linha in enumerate(linhas[:20]):
        cab = [normalizar(c).strip(" :") for c in linha]
        if _achar(cab, _COL_DATA) and (_achar(cab, _COL_VALOR) or _achar(cab, _COL_CRED) or _achar(cab, _COL_DEB)):
            cab_idx = i
            break
    if cab_idx is None:
        raise ExtratoInvalido(
            "Não achei o cabeçalho do extrato: o CSV precisa ter uma coluna de data e uma de valor "
            "(ou crédito e débito). Exporte o extrato do banco em CSV ou OFX."
        )
    cab = [normalizar(c).strip(" :") for c in linhas[cab_idx]]
    i_data = _achar(cab, _COL_DATA)[0]
    i_hist = _achar(cab, _COL_HIST)
    i_doc = (_achar(cab, _COL_DOC) or [None])[0]
    i_valor = (_achar(cab, _COL_VALOR) or [None])[0]
    i_cred = (_achar(cab, _COL_CRED) or [None])[0]
    i_deb = (_achar(cab, _COL_DEB) or [None])[0]
    i_saldo = (_achar(cab, _COL_SALDO) or [None])[0]
    i_tipo = (_achar(cab, _COL_TIPO) or [None])[0]

    def cel(linha: list[str], i: int | None) -> str:
        return linha[i].strip() if i is not None and i < len(linha) else ""

    vistos: dict[str, int] = {}
    ultimo_saldo: tuple[date, float] | None = None
    for linha in linhas[cab_idx + 1:]:
        if not any(c.strip() for c in linha):
            continue
        d = ler_data(cel(linha, i_data))
        if d is None:
            continue
        historico = _cortar(" · ".join(cel(linha, i) for i in i_hist if cel(linha, i)))
        documento = cel(linha, i_doc) or None
        if i_valor is not None:
            valor = ler_numero(cel(linha, i_valor))
            tipo = normalizar(cel(linha, i_tipo))
            if valor is not None and valor > 0 and tipo in ("d", "debito", "saida", "s", "-"):
                valor = -valor
        else:
            cred, deb = ler_numero(cel(linha, i_cred)), ler_numero(cel(linha, i_deb))
            valor = None
            if cred:
                valor = abs(cred)
            elif deb:
                valor = -abs(deb)
        saldo_col = ler_numero(cel(linha, i_saldo)) if i_saldo is not None else None
        if eh_linha_de_saldo(historico):
            # "Saldo anterior" é o começo; os outros ("S A L D O", "Saldo do dia") são o fim do dia.
            v = saldo_col if saldo_col is not None else valor
            if v is not None and "anterior" not in normalizar(historico):
                if ultimo_saldo is None or d >= ultimo_saldo[0]:
                    ultimo_saldo = (d, v)
            continue
        if valor is None or valor == 0:
            continue
        if saldo_col is not None and (ultimo_saldo is None or d >= ultimo_saldo[0]):
            ultimo_saldo = (d, saldo_col)
        base = f"{d}|{valor}|{normalizar(historico)}|{documento}"
        vistos[base] = vistos.get(base, 0) + 1
        lido.movimentos.append(MovimentoExtrato(d, valor, historico, documento, _chave_csv(d, valor, historico, documento, vistos[base])))
    if ultimo_saldo is not None:
        lido.data_saldo, lido.saldo_final = ultimo_saldo
    if not lido.movimentos:
        raise ExtratoInvalido("O CSV não tem nenhum movimento com data e valor reconhecíveis.")
    return lido


def ler_extrato(conteudo: bytes, nome_arquivo: str | None = None) -> ExtratoLido:
    """Detecta o formato (OFX pelo conteúdo, não pela extensão) e lê."""
    if not conteudo or not conteudo.strip():
        raise ExtratoInvalido("O arquivo está vazio.")
    texto = decodificar(conteudo)
    cabeca = texto[:2000].upper()
    if "<OFX" in cabeca or "OFXHEADER" in cabeca or "<STMTTRN>" in texto.upper():
        return ler_ofx(texto)
    if (nome_arquivo or "").lower().endswith((".xls", ".xlsx", ".pdf")):
        raise ExtratoInvalido("Formato não suportado: exporte o extrato em OFX (preferível) ou CSV.")
    return ler_csv(texto)
