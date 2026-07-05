"""
Script para carregar os CSV reais no banco via API HTTP.
Execução: python seed_db.py
"""
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = "http://localhost:8000"
BASE_DIR = Path(__file__).parent


def check_health():
    try:
        r = urllib.request.urlopen(BASE_URL + "/health", timeout=5)
        print("Backend:", json.loads(r.read()))
        return True
    except Exception as e:
        print(f"Backend offline: {e}")
        return False


def upload_csv(tipo: str, filepath: str) -> bool:
    path = Path(filepath)
    if not path.exists():
        print(f"  [SKIP] Arquivo nao encontrado: {filepath}")
        return False

    content = path.read_bytes()
    filename = path.name
    boundary = "FazendaBoundary2026"

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: text/csv\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{BASE_URL}/upload/{tipo}",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        r = urllib.request.urlopen(req, timeout=60)
        result = json.loads(r.read())
        print(f"  [OK] {tipo}: {result}")
        return True
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")
        print(f"  [ERRO] {tipo}: {msg[:300]}")
        return False


def main():
    print("=== Seed do banco FazendaApp ===")
    if not check_health():
        print("Suba o backend primeiro: python run_dev.py")
        sys.exit(1)

    csvs = [
        ("geral",             BASE_DIR / "GERAL.csv"),
        ("reprodutivo",       BASE_DIR / "1 - Consulta_SQL_Dados_Reprodutivos_e_Produtivos_Versao_8.csv"),
        ("estoque",           BASE_DIR / "ESTOQUE.csv"),
        ("conta_gerencial",   BASE_DIR / "CONTA_GERENCIAL.csv"),
        ("dieta",             BASE_DIR / "DIETA.csv"),
        ("controle_leiteiro", BASE_DIR / "Lista_de_controles_leiteiros_e_data_do_ultimo_parto_para_matrizes_ativas_e_baixadas_com_possibilidade_de_filtrar_periodo.csv"),
    ]

    ok = 0
    for tipo, path in csvs:
        print(f"\nUpload: {tipo}")
        if upload_csv(tipo, str(path)):
            ok += 1

    print(f"\n=== Concluido: {ok}/{len(csvs)} uploads OK ===")

    if ok > 0:
        # Testa agenda
        print("\nTestando agenda do dia...")
        try:
            r = urllib.request.urlopen(BASE_URL + "/agenda/", timeout=30)
            agenda = json.loads(r.read())
            t = agenda.get("totais", {})
            print(f"  Candidatas IATF: {t.get('candidatas_iatf', 0)}")
            print(f"  BST elegiveis: {t.get('bst_elegiveis', 0)}")
            print(f"  Total eventos: {t.get('eventos', 0)}")
        except Exception as e:
            print(f"  Erro na agenda: {e}")


if __name__ == "__main__":
    main()
