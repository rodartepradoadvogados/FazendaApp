"""Diagnóstico SOMENTE LEITURA: lotes de protocolo sanitário "fantasmas".

Lista lotes que a Sanidade mostra como "Em andamento" (ativo, sem encerramento)
mas cujas etapas venceram há mais de N dias sem nenhuma aplicação realizada —
candidatos a lançamento de teste/abandonado que nunca foi cancelado. NÃO altera
nada: cancelar/encerrar deve ser decisão do dono, pela Central de Protocolos
(que também estorna estoque). Uso:

    python scripts/diagnostico_protocolos_sanitarios_parados.py --database-url URL [--dias 30]

O banco é passado explicitamente (nunca lê DATABASE_URL) e a conexão é
aberta em modo somente leitura quando o driver permite (SQLite: mode=ro).
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

from sqlalchemy import create_engine, text

SQL = text("""
SELECT lo.id AS lote_id, lo.nome_protocolo, lo.data_inicio, lo.fazenda_id,
       COUNT(ap.id) AS etapas, SUM(CASE WHEN ap.realizada THEN 1 ELSE 0 END) AS realizadas,
       MAX(ap.data_prevista) AS ultima_prevista
FROM protocolo_sanitario_lote lo
JOIN protocolo_sanitario_lancamento la ON la.lote_id = lo.id
JOIN protocolo_sanitario_aplicacao ap ON ap.lancamento_id = la.id
WHERE lo.ativo AND lo.encerrado_em IS NULL
GROUP BY lo.id, lo.nome_protocolo, lo.data_inicio, lo.fazenda_id
HAVING SUM(CASE WHEN ap.realizada THEN 1 ELSE 0 END) = 0 AND MAX(ap.data_prevista) < :limite
ORDER BY lo.data_inicio
""")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--database-url", required=True)
    ap.add_argument("--dias", type=int, default=30)
    args = ap.parse_args()
    url = args.database_url
    if url.startswith("sqlite:///") and "mode=ro" not in url:
        url = "sqlite:///file:" + url[len("sqlite:///"):] + "?mode=ro&uri=true"
    limite = (date.today() - timedelta(days=args.dias)).isoformat()
    with create_engine(url).connect() as conn:
        rows = conn.execute(SQL, {"limite": limite}).mappings().all()
    for r in rows:
        print(dict(r))
    print(f"{len(rows)} lote(s) ativo(s) sem nenhuma aplicação, vencidos há > {args.dias} dias (nada foi alterado).")


if __name__ == "__main__":
    main()
