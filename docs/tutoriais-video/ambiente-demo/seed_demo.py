#!/usr/bin/env python3
"""Popula a fazenda FICTÍCIA de demonstração pela API (o mesmo caminho do app).

Só biblioteca padrão. Rodar DEPOIS de `setup_fazenda.py` (que cria a fazenda, o
contrato e o vínculo do usuário) e com o backend no ar.

    python3 seed_demo.py --cred /tmp/cowdata-demo/cred.txt [--api http://localhost:8000] [--hoje AAAA-MM-DD]

Todas as datas são RELATIVAS a "hoje" — rodar em qualquer dia dá um cenário
equivalente: mês anterior fechado de gastos e receita, mês corrente em andamento,
uma conta vencida, contas a vencer, uma parcelada, uma receita a receber, o mesmo
mês do ano passado (para a comparação) e um extrato OFX do mês anterior.

Escala fictícia: ~45 vacas, ~13.000 L/mês a ~R$ 2,95/L, margem do mês anterior ~27%.
Nada aqui é dado da fazenda real. Os nomes de empresas são inventados; confira que
nenhum coincide com empresa real antes de publicar um vídeo.
"""
import argparse
import calendar
import json
import re
import sys
import urllib.error
import urllib.request
import uuid
from datetime import date, timedelta

ap = argparse.ArgumentParser()
ap.add_argument("--api", default="http://localhost:8000")
ap.add_argument("--cred", required=True, help="arquivo com linhas 'usuario: X' e 'senha: Y' (fora do repositório)")
ap.add_argument("--hoje", default=None)
ap.add_argument("--ofx-out", default=None, help="onde gravar o OFX gerado (padrão: ao lado do arquivo de credenciais)")
args = ap.parse_args()

HOJE = date.fromisoformat(args.hoje) if args.hoje else date.today()
cred = open(args.cred, encoding="utf-8").read()
USUARIO = re.search(r"usuario:\s+(\S+)", cred).group(1)
SENHA = re.search(r"senha:\s+(\S+)", cred).group(1)
API = args.api.rstrip("/")


def req(method, path, body=None, headers=None, raw=None):
    h = {"Idempotency-Key": str(uuid.uuid4())}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    if raw is None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(API + path, method=method, data=data, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=90) as resp:
            return json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        print("ERRO", method, path, e.code, e.read().decode()[:400], file=sys.stderr)
        return None


TOKEN = None
login = req("POST", "/auth/login", {"username": USUARIO, "senha": SENHA})
if not login:
    sys.exit("login falhou")
TOKEN = login["token"]
print("fazenda:", login.get("fazenda_atual", {}).get("nome"))


# ----- datas relativas -------------------------------------------------------
def add_meses(d, n):
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def dia(n, d):  # dia d do mês (hoje + n meses), limitado ao último dia
    ref = add_meses(date(HOJE.year, HOJE.month, 1), n)
    return date(ref.year, ref.month, min(d, calendar.monthrange(ref.year, ref.month)[1]))


def fim_mes(n):
    ref = add_meses(date(HOJE.year, HOJE.month, 1), n)
    return date(ref.year, ref.month, calendar.monthrange(ref.year, ref.month)[1])


def ate_hoje(d):
    return min(d, HOJE)


def iso(d):
    return d.isoformat() if d else None


# ----- cadastros -------------------------------------------------------------
banco = req("POST", "/financeiro/contas-correntes", {"banco": "Banco Exemplo", "agencia": "0001", "numero_conta": "12345-6"})
coop = req("POST", "/financeiro/contas-correntes", {"banco": "Cooperativa Exemplo", "agencia": "0200", "numero_conta": "98765-4"})
BANCO, COOP = banco["id"], coop["id"]
ABERTURA = fim_mes(-2)
req("PUT", f"/financeiro/contas-correntes/{BANCO}/saldo-abertura", {"saldo_abertura": 38000.0, "data_saldo_abertura": iso(ABERTURA)})
req("PUT", f"/financeiro/contas-correntes/{COOP}/saldo-abertura", {"saldo_abertura": 6200.0, "data_saldo_abertura": iso(ABERTURA)})
CC = "Pecuária Leiteira"
req("POST", "/financeiro/centros-custo", {"nome": CC, "padrao": True})
req("POST", "/financeiro/centros-custo", {"nome": "Agricultura"})
# Regras v2: os litros vêm da NOTA e o item de estoque "Leite" (produto de leite, com unidade) dá a unidade.
req("POST", "/estoque/", {"nome": "Leite", "unidade": "L", "estocavel": False, "produto_leite": True, "gera_receita": True, "categoria": "Produção"})

BS, LAT = "Agropecuária Boa Safra", "Laticínio Serra Azul"
movimentos_banco = []  # (data, valor com sinal, memo) -> vira o OFX do mês anterior


def lancar(tipo, forn, conta, produto, valor, emissao, venc, doc=None, pago=None, cc=BANCO, forma="pix", parcelas=None, qtd=None, memo=None, centro=CC):
    item = {"codigo_conta_gerencial": conta, "produto": produto, "valor_total": valor, "tipo_item": "produto"}
    if qtd:
        item.update(quantidade=qtd, valor_unitario=round(valor / qtd, 4))
    d = {"tipo": tipo, "itens": [item], "centro_custo": centro, "fornecedor_cliente": forn,
         "tipo_documento": "Nota fiscal" if doc else "Recibo", "numero_documento": doc,
         "data_emissao": iso(emissao), "data_competencia": iso(emissao), "data_vencimento": iso(venc)}
    if parcelas:
        d["parcelas"] = parcelas
    if pago:
        d.update(data_pagamento=iso(pago), valor_pago=valor, conta_corrente_id=cc, forma_pagamento=forma)
        if cc == BANCO and memo:
            movimentos_banco.append((pago, valor if tipo == "receita" else -valor, memo))
    r = req("POST", "/financeiro/lancamentos", d)
    print("ok " if r else "FALHOU", forn, produto, valor)
    return r


def desp(*a, **k):
    return lancar("despesa", *a, **k)


def rec(*a, **k):
    return lancar("receita", *a, **k)


# ----- mês anterior (fechado) ------------------------------------------------
rec(LAT, "2.01.01.01", "Leite", 36250, fim_mes(-2), dia(-1, 10), "NF 3301", pago=dia(-1, 10), qtd=12500, memo="TED RECEBIDA LATICINIO SERRA AZUL")
rec(LAT, "2.01.01.01", "Leite", 38350, fim_mes(-1), ate_hoje(dia(0, 10)), "NF 3412", pago=ate_hoje(dia(0, 10)), qtd=13000, memo=None)
rec("Cliente Exemplo", "2.01.02.01", "Venda de bezerros", 2800, dia(-1, 22), dia(-1, 22), None, pago=dia(-1, 22), memo="TRANSFERENCIA RECEBIDA CLIENTE EXEMPLO")
desp("Contabilidade Exemplo", "3.03.02.01", "Honorários contábeis", 600, dia(-1, 8), dia(-1, 8), None, pago=dia(-1, 8), memo="PIX ENVIADO CONTABILIDADE EXEMPLO")
desp("Vet Exemplo Medicamentos", "3.01.02.01", "Vacinas e vermífugos", 1650, dia(-1, 14), dia(-1, 14), "NF 702", pago=dia(-1, 14), memo="PIX ENVIADO VET EXEMPLO MEDICAMENTOS")
desp("Posto Rota 10", "3.04.02", "Diesel", 1150, dia(-1, 18), dia(-1, 18), "NF 8790", pago=dia(-1, 18), memo="PIX ENVIADO POSTO ROTA 10")
desp(BS, "3.01.01.01", "Ração concentrada", 14500, dia(-1, 10), dia(-1, 25), "NF 1498", pago=dia(-1, 25), qtd=17000, memo="PIX ENVIADO AGROPECUARIA BOA SAFRA")
desp("Energia Elétrica Exemplo", "3.04.01", "Energia elétrica - mês anterior", 1440, dia(-1, 12), dia(-1, 28), "Fatura 9921", pago=dia(-1, 28), forma="boleto", memo="PAGTO BOLETO ENERGIA ELETRICA EXEMPLO")
desp("Silagem do Vale", "3.01.01.02", "Silagem de milho", 3800, dia(-1, 12), fim_mes(-1), "NF 77", pago=fim_mes(-1), qtd=38000, memo="PIX ENVIADO SILAGEM DO VALE")
desp("Equipe da fazenda", "3.03.01.01", "Salários - mês anterior", 6800, fim_mes(-1), ate_hoje(dia(0, 5)), None, pago=ate_hoje(dia(0, 5)), forma="transferencia")

# ----- mês corrente (em andamento) -------------------------------------------
desp("Posto Rota 10", "3.04.02", "Diesel", 890, HOJE - timedelta(days=12), HOJE - timedelta(days=12), "NF 8841", pago=HOJE - timedelta(days=12))
desp("Contabilidade Exemplo", "3.03.02.01", "Honorários contábeis", 600, HOJE - timedelta(days=6), HOJE - timedelta(days=6), None, pago=HOJE - timedelta(days=6))
desp(BS, "3.01.01.01", "Ração concentrada", 15200, HOJE - timedelta(days=13), HOJE - timedelta(days=9), "NF 1520", qtd=17500)  # VENCIDA
desp("Energia Elétrica Exemplo", "3.04.01", "Energia elétrica - mês corrente", 1560, HOJE - timedelta(days=6), HOJE + timedelta(days=2), "Fatura 10110")
desp("Vet Exemplo Medicamentos", "3.01.02.01", "Antibióticos e vacinas", 1280, HOJE - timedelta(days=5), HOJE + timedelta(days=6), "NF 771")
desp("Oficina Ordenha Exemplo", "3.01.04.02", "Manutenção da ordenhadeira", 980, HOJE - timedelta(days=2), HOJE + timedelta(days=16), "NF 204")
v1 = HOJE + timedelta(days=11)
desp("Nutrimix Minerais", "3.01.01.03", "Sal mineral (3 parcelas)", 4050, HOJE - timedelta(days=4), v1, "NF 5530",
     parcelas=[{"data_vencimento": iso(add_meses(v1, k)), "valor": 1350} for k in range(3)])
rec(LAT, "2.01.01.01", "Leite", 18000, HOJE, HOJE + timedelta(days=11), "NF 3520", qtd=6000)  # a receber

# ----- mesmo mês do ano passado (para a comparação "mesmo período do ano passado") -----
ano_ant = lambda d: date(d.year - 1, d.month, min(d.day, calendar.monthrange(d.year - 1, d.month)[1]))
M1 = fim_mes(-1)
rec(LAT, "2.01.01.01", "Leite", 33040, ano_ant(M1), ano_ant(M1), "NF 2210", pago=ano_ant(M1), qtd=11800, cc=BANCO)
for forn, conta, prod, v in [(BS, "3.01.01.01", "Ração concentrada", 13200), ("Silagem do Vale", "3.01.01.02", "Silagem de milho", 3300),
                             ("Vet Exemplo Medicamentos", "3.01.02.01", "Vacinas", 1400), ("Energia Elétrica Exemplo", "3.04.01", "Energia elétrica", 1320),
                             ("Posto Rota 10", "3.04.02", "Diesel", 1050), ("Contabilidade Exemplo", "3.03.02.01", "Honorários contábeis", 560),
                             ("Equipe da fazenda", "3.03.01.01", "Salários", 6100)]:
    desp(forn, conta, prod, v, ano_ant(dia(-1, 15)), ano_ant(dia(-1, 15)), None, pago=ano_ant(dia(-1, 15)))

# ----- extrato OFX do mês anterior (todas as linhas do Banco Exemplo + 1 tarifa fora do sistema) -----
mov = sorted([m for m in movimentos_banco if m[0].year == M1.year and m[0].month == M1.month and m[2]])
mov.append((dia(-1, 29), -29.90, "TARIFA PACOTE DE SERVICOS"))
mov.sort()
saldo = 38000.0 + sum(v for d, v, m in movimentos_banco if m and ABERTURA < d <= M1) + (-29.90)
linhas = "\n".join(
    f"<STMTTRN><TRNTYPE>{'CREDIT' if v > 0 else 'DEBIT'}<DTPOSTED>{d:%Y%m%d}<TRNAMT>{v:.2f}<FITID>{d:%Y%m%d}{i:03d}<MEMO>{m}</STMTTRN>"
    for i, (d, v, m) in enumerate(mov, 1)
)
ofx = f"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX>
<SIGNONMSGSRSV1><SONRS><STATUS><CODE>0<SEVERITY>INFO</STATUS><DTSERVER>{HOJE:%Y%m%d}<LANGUAGE>POR</SONRS></SIGNONMSGSRSV1>
<BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STATUS><CODE>0<SEVERITY>INFO</STATUS>
<STMTRS><CURDEF>BRL<BANKACCTFROM><BANKID>999<ACCTID>123456<ACCTTYPE>CHECKING</BANKACCTFROM>
<BANKTRANLIST><DTSTART>{dia(-1, 1):%Y%m%d}<DTEND>{M1:%Y%m%d}
{linhas}
</BANKTRANLIST>
<LEDGERBAL><BALAMT>{saldo:.2f}<DTASOF>{M1:%Y%m%d}</LEDGERBAL>
</STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""
import os
ofx_path = args.ofx_out or os.path.join(os.path.dirname(os.path.abspath(args.cred)), "extrato_banco_exemplo.ofx")
open(ofx_path, "w", encoding="ascii", errors="replace").write(ofx)
boundary = "----demo" + uuid.uuid4().hex
corpo = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"conta_corrente_id\"\r\n\r\n{BANCO}\r\n"
         f"--{boundary}\r\nContent-Disposition: form-data; name=\"arquivo\"; filename=\"extrato.ofx\"\r\nContent-Type: application/x-ofx\r\n\r\n").encode() \
        + ofx.encode("ascii", "replace") + f"\r\n--{boundary}--\r\n".encode()
imp = req("POST", "/financeiro/conciliacao/importar", headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, raw=corpo)
print("OFX importado:", imp)
print(f"pronto. hoje={HOJE}  mês anterior={M1:%m/%Y}  OFX em {ofx_path}")
