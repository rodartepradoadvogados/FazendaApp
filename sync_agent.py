"""
Sincronizador local FazendaApp — vigia uma pasta e envia os CSV do Ideagri
para o backend automaticamente, sem upload manual.

Fluxo recomendado:
  1. No Ideagri: agendar a exportação diária dos relatórios para uma pasta local
     (ex.: C:\\FazendaApp\\ideagri).
  2. Rodar este script apontando para essa pasta. Ele detecta cada CSV pelo nome,
     espera o arquivo terminar de ser escrito, e faz POST /upload/{tipo} só quando
     o conteúdo muda (evita reenvio à toa).

Uso:
  python sync_agent.py --dir C:\\FazendaApp\\ideagri            # vigia continuamente
  python sync_agent.py --dir ./  --once                         # envia uma vez e sai
  python sync_agent.py --dir ./  --api https://minha-api.up.railway.app

Só usa a biblioteca padrão do Python 3.8+ (nenhuma dependência a instalar).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Ordem importa: 'reprodutivo' vincula serviços aos animais já carregados por 'geral'.
# Cada tipo casa com o primeiro padrão encontrado no nome do arquivo (minúsculo).
TIPOS = [
    ("geral",           ["geral"]),
    ("reprodutivo",     ["consulta_sql", "reprodut"]),
    ("estoque",         ["estoque"]),
    ("conta_gerencial", ["conta_ger", "conta gerencial", "conta_gerencial"]),
]

STATE_FILE = ".sync_state.json"


def classificar(nome: str) -> str | None:
    """Descobre o tipo de upload a partir do nome do arquivo."""
    low = nome.lower()
    for tipo, padroes in TIPOS:
        if any(p in low for p in padroes):
            return tipo
    return None


def hash_arquivo(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def esperar_estavel(path: Path, tentativas: int = 5, intervalo: float = 1.0) -> bool:
    """Espera o arquivo parar de crescer (evita ler exportação pela metade)."""
    ultimo = -1
    for _ in range(tentativas):
        try:
            tam = path.stat().st_size
        except OSError:
            return False
        if tam == ultimo and tam > 0:
            return True
        ultimo = tam
        time.sleep(intervalo)
    return ultimo > 0


def enviar(api: str, tipo: str, path: Path) -> tuple[bool, str]:
    """POST multipart do CSV para /upload/{tipo}. Sem dependências externas."""
    content = path.read_bytes()
    boundary = "----FazendaSyncBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        "Content-Type: text/csv\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        f"{api.rstrip('/')}/upload/{tipo}",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return True, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:300]}"
    except urllib.error.URLError as e:
        return False, f"Sem conexão com {api}: {e.reason}"


def carregar_estado(pasta: Path) -> dict:
    f = pasta / STATE_FILE
    if f.exists():
        try:
            return json.loads(f.read_text("utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def salvar_estado(pasta: Path, estado: dict) -> None:
    try:
        (pasta / STATE_FILE).write_text(json.dumps(estado, indent=2), "utf-8")
    except OSError:
        pass


def varrer(api: str, pasta: Path, estado: dict) -> int:
    """Uma passada: envia os CSV que mudaram desde a última vez. Retorna nº enviados."""
    # Agrupa por tipo e respeita a ordem de TIPOS (geral antes de reprodutivo).
    candidatos: dict[str, Path] = {}
    for path in sorted(pasta.glob("*.csv")):
        tipo = classificar(path.name)
        if tipo and tipo not in candidatos:
            candidatos[tipo] = path

    enviados = 0
    for tipo, _ in TIPOS:
        path = candidatos.get(tipo)
        if not path:
            continue
        if not esperar_estavel(path):
            print(f"  [SKIP] {path.name}: arquivo instável/vazio")
            continue
        h = hash_arquivo(path)
        if estado.get(tipo) == h:
            continue  # inalterado desde o último envio
        print(f"  Enviando {tipo} ← {path.name} ...")
        ok, msg = enviar(api, tipo, path)
        if ok:
            estado[tipo] = h
            enviados += 1
            print(f"    [OK] {msg}")
        else:
            print(f"    [ERRO] {msg}")
    return enviados


def main() -> None:
    ap = argparse.ArgumentParser(description="Sincronizador local FazendaApp")
    ap.add_argument("--dir", required=True, help="Pasta a vigiar (onde caem os CSV do Ideagri)")
    ap.add_argument("--api", default="http://localhost:8000", help="URL do backend")
    ap.add_argument("--once", action="store_true", help="Envia uma vez e encerra")
    ap.add_argument("--intervalo", type=int, default=60, help="Segundos entre varreduras (modo contínuo)")
    args = ap.parse_args()

    pasta = Path(args.dir).expanduser()
    if not pasta.is_dir():
        print(f"Pasta não encontrada: {pasta}")
        sys.exit(1)

    print(f"Sincronizador FazendaApp — pasta: {pasta} → API: {args.api}")
    estado = carregar_estado(pasta)

    if args.once:
        n = varrer(args.api, pasta, estado)
        salvar_estado(pasta, estado)
        print(f"Concluído: {n} arquivo(s) enviado(s).")
        return

    print(f"Vigiando a cada {args.intervalo}s. Ctrl+C para parar.")
    try:
        while True:
            n = varrer(args.api, pasta, estado)
            if n:
                salvar_estado(pasta, estado)
            time.sleep(args.intervalo)
    except KeyboardInterrupt:
        print("\nEncerrado.")


if __name__ == "__main__":
    main()
