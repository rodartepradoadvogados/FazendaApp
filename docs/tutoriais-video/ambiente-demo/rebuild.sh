#!/usr/bin/env bash
# Recria do zero o ambiente FICTÍCIO de tutoriais do CowData: backend + banco SQLite
# descartável + fazenda "Vale Verde" + dados de demonstração. Idempotente (apaga o banco).
#
#   bash docs/tutoriais-video/ambiente-demo/rebuild.sh            # só backend (porta 8000)
#   bash docs/tutoriais-video/ambiente-demo/rebuild.sh --front    # + build e servidor de produção do front (porta 3000)
#
# Nada aqui toca produção: SQLite em $DEMO, usuário `teste_local` com senha aleatória gravada em
# $DEMO/cred.txt (FORA do repositório; nunca commitar, nunca colar em nota/vídeo).
set -euo pipefail
AQUI="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$AQUI/../../.." && pwd)"
DEMO="${DEMO_DIR:-/tmp/cowdata-demo}"
mkdir -p "$DEMO"

if [ ! -x "$DEMO/venv/bin/python" ]; then
  python3 -m venv "$DEMO/venv"
  "$DEMO/venv/bin/pip" install -q -r "$REPO/backend/requirements.txt"
fi
PY="$DEMO/venv/bin/python"

# para o backend anterior (o colchete evita casar com este próprio comando)
pkill -f "[u]vicorn main:app" 2>/dev/null || true
sleep 2
rm -f "$DEMO/tutorial.db"

cd "$REPO/backend"
export DATABASE_URL="sqlite:///$DEMO/tutorial.db" ENVIRONMENT=production
nohup "$DEMO/venv/bin/uvicorn" main:app --host 127.0.0.1 --port 8000 > "$DEMO/backend.log" 2>&1 &
for _ in $(seq 1 90); do curl -s localhost:8000/health >/dev/null && break; sleep 4; done
curl -s localhost:8000/health >/dev/null || { echo "backend não subiu; veja $DEMO/backend.log"; exit 1; }

"$PY" scripts/criar_usuario_teste_local.py 2>&1 | grep -E "usuario:|senha:" > "$DEMO/cred.txt"
"$PY" "$AQUI/setup_fazenda.py" 2>&1 | grep -E "^fazenda_id|^preparar_financeiro"
"$PY" "$AQUI/seed_demo.py" --cred "$DEMO/cred.txt" --ofx-out "$DEMO/extrato_banco_exemplo.ofx" 2>&1 | grep -E "^fazenda:|FALHOU|ERRO|OFX|pronto"

if [ "${1:-}" = "--front" ]; then
  cd "$REPO/frontend"
  [ -d node_modules ] || npm ci --no-audit --no-fund
  pkill -f "[n]ext-server|[n]ext start|[n]ext dev" 2>/dev/null || true
  sleep 2
  NEXT_TELEMETRY_DISABLED=1 npm run build > "$DEMO/front_build.log" 2>&1
  NEXT_TELEMETRY_DISABLED=1 nohup npx next start -p 3000 > "$DEMO/front.log" 2>&1 &
  sleep 8
  curl -s -o /dev/null -w "front HTTP %{http_code}\n" localhost:3000/login
fi
echo "Login: usuário e senha em $DEMO/cred.txt (fora do repositório)."
