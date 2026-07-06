"""
Inspetor do ABS Monitor Offline — RODE ESTA NO SEU PC (o do ABS Monitor).

Ele NÃO altera nada: só procura os arquivos de dados do ABS Monitor Offline
nos locais típicos do Windows, identifica o formato de cada banco encontrado
e imprime um relatório. Copie a saída e me mande — com ela eu construo o
extrator que lê seus lançamentos e envia para o backend.

Uso:
  python abs_monitor_inspect.py

Só usa a biblioteca padrão do Python 3.8+. Se você tiver o Python instalado,
é só dar duplo clique ou rodar no Prompt de Comando dentro da pasta.
"""
from __future__ import annotations

import os
import sqlite3
import struct
from pathlib import Path

# Pastas onde apps de desktop costumam guardar dados no Windows.
def locais_busca() -> list[Path]:
    env = os.environ
    candidatos = [
        env.get("PROGRAMFILES"),
        env.get("PROGRAMFILES(X86)"),
        env.get("PROGRAMDATA"),
        env.get("LOCALAPPDATA"),
        env.get("APPDATA"),
        env.get("USERPROFILE"),
        os.path.join(env.get("USERPROFILE", ""), "Documents"),
        os.path.join(env.get("PUBLIC", "C:\\Users\\Public"), "Documents"),
        "C:\\",
    ]
    vistos, saida = set(), []
    for c in candidatos:
        if c and os.path.isdir(c) and c not in vistos:
            vistos.add(c)
            saida.append(Path(c))
    return saida


# Palavras que indicam pastas/arquivos do ABS Monitor.
CHAVES = ("abs monitor", "absmonitor", "abs_monitor", "pecplan", "abs pecplan")

# Extensões de banco de dados de desktop mais comuns.
EXT_DB = {".fdb", ".gdb", ".ib", ".mdb", ".accdb", ".sqlite", ".sqlite3",
          ".db", ".db3", ".sdf", ".dat", ".fbk", ".bak"}


def identificar_formato(path: Path) -> str:
    """Detecta o formato pelo conteúdo (magic bytes), com fallback na extensão."""
    try:
        with open(path, "rb") as f:
            head = f.read(64)
    except OSError as e:
        return f"(ilegível: {e})"

    if head.startswith(b"SQLite format 3\x00"):
        return "SQLite"
    if b"Standard Jet DB" in head or b"Standard ACE DB" in head:
        return "MS Access (Jet/ACE)"
    # Firebird/Interbase: página de cabeçalho começa com tipo 0x01 e versão ODS.
    if len(head) >= 4 and head[0] == 0x01 and head[1] == 0x00:
        return "Firebird/Interbase (provável)"
    if head[:4] == b"\x00\x01\x00\x00" and b"Standard" not in head:
        return "MS Access (provável)"
    ext = path.suffix.lower()
    if ext in (".fdb", ".gdb", ".ib", ".fbk"):
        return "Firebird/Interbase (por extensão)"
    if ext in (".sdf",):
        return "SQL Server Compact (por extensão)"
    return f"desconhecido (extensão {ext or 'nenhuma'})"


def listar_tabelas_sqlite(path: Path) -> list[str]:
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tabelas = [r[0] for r in cur.fetchall()]
        con.close()
        return tabelas
    except sqlite3.Error as e:
        return [f"(erro ao ler: {e})"]


def procurar(raiz: Path, profundidade: int = 4) -> list[Path]:
    """Varre 'raiz' até certa profundidade, priorizando pastas com as chaves."""
    achados: list[Path] = []
    raiz_str = str(raiz).lower()
    parece_abs = any(k in raiz_str for k in CHAVES)
    try:
        for dirpath, dirnames, filenames in os.walk(raiz):
            rel = Path(dirpath).relative_to(raiz)
            if len(rel.parts) > profundidade:
                dirnames[:] = []
                continue
            low_dir = dirpath.lower()
            na_pasta_abs = parece_abs or any(k in low_dir for k in CHAVES)
            # Fora de pastas do ABS, só desce em diretórios que casem com as chaves.
            if not na_pasta_abs:
                dirnames[:] = [d for d in dirnames if any(k in d.lower() for k in CHAVES)]
            for fn in filenames:
                p = Path(dirpath) / fn
                ext = p.suffix.lower()
                nome_low = fn.lower()
                if ext in EXT_DB or (na_pasta_abs and ext in ("", ".dat")):
                    achados.append(p)
                elif any(k in nome_low for k in CHAVES) and ext in EXT_DB:
                    achados.append(p)
    except (OSError, ValueError):
        pass
    return achados


def main() -> None:
    print("=" * 64)
    print("INSPETOR ABS MONITOR OFFLINE — procurando arquivos de dados")
    print("=" * 64)

    todos: dict[str, Path] = {}
    for raiz in locais_busca():
        print(f"\nVarrendo: {raiz} ...")
        for p in procurar(raiz):
            todos[str(p).lower()] = p

    if not todos:
        print("\nNenhum banco de dados do ABS Monitor encontrado nos locais padrão.")
        print("Ache o atalho na área de trabalho > botão direito > 'Abrir local do arquivo'")
        print("e me diga o caminho da pasta de instalação. Procure por arquivos")
        print("terminados em .fdb, .mdb, .sdf, .sqlite ou .db dentro dela.")
        return

    print(f"\n{'=' * 64}")
    print(f"ENCONTRADOS {len(todos)} arquivo(s) candidato(s):")
    print("=" * 64)
    for p in sorted(todos.values(), key=lambda x: str(x).lower()):
        try:
            tam = p.stat().st_size
        except OSError:
            tam = -1
        fmt = identificar_formato(p)
        print(f"\n• {p}")
        print(f"    tamanho: {tam/1_048_576:.2f} MB   formato: {fmt}")
        if fmt == "SQLite":
            tabelas = listar_tabelas_sqlite(p)
            print(f"    tabelas ({len(tabelas)}): {', '.join(tabelas[:40])}")

    print(f"\n{'=' * 64}")
    print("PRÓXIMO PASSO: copie TODO este relatório e me mande.")
    print("Se aparecer 'Firebird' ou 'MS Access', diga o caminho e (se puder)")
    print("faça uma cópia do arquivo — com ela eu leio o esquema e monto o extrator.")
    print("=" * 64)


if __name__ == "__main__":
    main()
