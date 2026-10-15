#!/usr/bin/env python3
"""Cadastra no ambiente de demonstração itens de ESTOQUE com unidade e embalagem
(saca de 30 kg, frasco de 50/100 ml, galão...) para testar o lançamento financeiro
por embalagem. Só biblioteca padrão; roda depois de `seed_demo.py`.

    python3 -I seed_estoque.py --cred /tmp/cowdata-demo/cred.txt [--api http://localhost:8000]

Nomes inventados e genéricos; nada aqui é dado da fazenda real. Idempotente: se o
item já existe, só garante as embalagens."""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
import uuid

ap = argparse.ArgumentParser()
ap.add_argument("--api", default="http://localhost:8000")
ap.add_argument("--cred", required=True)
args = ap.parse_args()
cred = open(args.cred, encoding="utf-8").read()
USUARIO = re.search(r"usuario:\s+(\S+)", cred).group(1)
SENHA = re.search(r"senha:\s+(\S+)", cred).group(1)
API = args.api.rstrip("/")
TOKEN = None


def req(method, path, body=None):
    h = {"Idempotency-Key": str(uuid.uuid4()), "Content-Type": "application/json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    r = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        print("ERRO", method, path, e.code, e.read().decode()[:300], file=sys.stderr)
        return None


login = req("POST", "/auth/login", {"username": USUARIO, "senha": SENHA})
TOKEN = (login or {}).get("access_token") or (login or {}).get("token")
if not TOKEN:
    sys.exit("login falhou")

ITENS = [
    # nome, unidade de estoque, finalidade, categoria, embalagem (unid, medida, qtd), conta de despesa padrão, embalagens cadastradas
    ("Ração concentrada 22%", "saca", "Alimentação", "Alimentação", ("saca", "kg/saca", 30), "3.01.01.01", []),
    ("Sal mineral", "saca", "Alimentação", "Alimentação", ("saca", "kg/saca", 25), "3.01.01.03", []),
    ("Silagem de milho", "t", "Alimentação", "Alimentação", (None, None, None), "3.01.01.02", []),
    ("Antibiótico injetável", "ml", "Medicamento", "Medicamento", ("frasco", "mililitros/frasco", 100), "3.01.02.01", [50, 100]),
    ("Vacina aftosa", "dose", "Medicamento", "Medicamento", ("frasco", "unidades", 50), "3.01.02.01", [25, 50]),
    ("Detergente da ordenha", "L", "Ordenha", "Higiene", ("galão", "litros/garrafa", 20), "3.01.04.01", [5, 20]),
    ("Diesel S10", "L", "Combustível", "Combustível", (None, None, None), "3.04.02", []),
]
existentes = {i["nome"]: i for i in ((req("GET", "/estoque/") or {}).get("itens") or [])}
for nome, unidade, finalidade, categoria, (ue, me, qe), conta, embalagens in ITENS:
    item = existentes.get(nome)
    if not item:
        corpo = {"nome": nome, "unidade": unidade, "finalidade": finalidade, "categoria": categoria, "estocavel": True,
                 "quantidade": 0, "conta_gerencial_despesa_padrao": conta, "centro_custo_padrao": "Pecuária Leiteira"}
        if ue:
            corpo.update({"unidade_embalagem": ue, "medida_embalagem": me, "quantidade_embalagem": qe})
        item = req("POST", "/estoque/", corpo)
    if not item:
        continue
    ja = {e["quantidade"] for e in (req("GET", f"/estoque/{item['id']}/embalagens") or [])}
    for q in embalagens:
        if q not in ja:
            req("POST", f"/estoque/{item['id']}/embalagens", {"quantidade": q})
    print("ok", nome, item["id"], "embalagens", embalagens)
print("pronto")
