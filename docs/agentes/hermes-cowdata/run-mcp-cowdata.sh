#!/usr/bin/env bash
# Inicia a ponte MCP lendo o token de um arquivo (chmod 600), para o segredo NAO ficar
# no config.yaml do Hermes nem no historico do shell.
#
# Instalacao (exemplo): /opt/cowdata-mcp/{mcp_cowdata_leitura.py,run-mcp-cowdata.sh,venv/}
#   Arquivo do token: ~/.cowdata-agente-token  (so o token, uma linha; chmod 600)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export COWDATA_API_URL="${COWDATA_API_URL:-https://fazendaapp-production.up.railway.app}"
ARQUIVO_TOKEN="${COWDATA_TOKEN_FILE:-$HOME/.cowdata-agente-token}"
if [[ -z "${COWDATA_AGENTE_TOKEN:-}" ]]; then
  [[ -r "$ARQUIVO_TOKEN" ]] || { echo "[run-mcp-cowdata] token nao encontrado em $ARQUIVO_TOKEN" >&2; exit 1; }
  COWDATA_AGENTE_TOKEN="$(tr -d '[:space:]' < "$ARQUIVO_TOKEN")"
  export COWDATA_AGENTE_TOKEN
fi
exec "$DIR/venv/bin/python" "$DIR/mcp_cowdata_leitura.py"
