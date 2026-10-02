#!/usr/bin/env bash
# Valida a API de leitura do CowData: token, rotas e a garantia de somente leitura.
# Uso:   COWDATA_TOKEN_FILE=~/.cowdata-agente-token ./testar.sh
#   ou:  COWDATA_AGENTE_TOKEN='...' ./testar.sh      (evite: fica no historico do shell)
# Variavel opcional: COWDATA_API_URL (padrao: producao). O token NUNCA e impresso.
set -uo pipefail
URL="${COWDATA_API_URL:-https://fazendaapp-production.up.railway.app}"
URL="${URL%/}"
ARQ="${COWDATA_TOKEN_FILE:-$HOME/.cowdata-agente-token}"
if [[ -z "${COWDATA_AGENTE_TOKEN:-}" ]]; then
  [[ -r "$ARQ" ]] || { echo "Token nao encontrado (defina COWDATA_AGENTE_TOKEN ou COWDATA_TOKEN_FILE)"; exit 2; }
  COWDATA_AGENTE_TOKEN="$(tr -d '[:space:]' < "$ARQ")"
fi
falhas=0
codigo() {  # codigo METODO CAMINHO [TOKEN]  -> imprime so o status HTTP
  local metodo="$1" caminho="$2" tok="${3-$COWDATA_AGENTE_TOKEN}"
  if [[ -n "$tok" ]]; then
    curl -sS -o /dev/null -w '%{http_code}' --max-time 30 -X "$metodo" -H "Authorization: Bearer $tok" "$URL$caminho"
  else
    curl -sS -o /dev/null -w '%{http_code}' --max-time 30 -X "$metodo" "$URL$caminho"
  fi
}
checar() {  # checar "descricao" "esperados (ex: 200 ou '404 405')" obtido
  if [[ " $2 " == *" $3 "* ]]; then echo "  OK    $1 (HTTP $3)"; else echo "  FALHA $1 (esperado $2, veio $3)"; falhas=$((falhas+1)); fi
}
echo "CowData: $URL"
echo "== Autenticacao =="
checar "sem token"                       "401"     "$(codigo GET /agente/saude '')"
checar "token errado"                    "401 429" "$(codigo GET /agente/saude 'token-errado-0123456789-0123456789-xx')"
checar "token certo: /agente/saude"      "200"     "$(codigo GET /agente/saude)"
echo "== Rotas de consulta (GET) =="
checar "/agente/ferramentas"             "200" "$(codigo GET /agente/ferramentas)"
checar "/agente/instrucoes"              "200" "$(codigo GET /agente/instrucoes)"
checar "consultar listar_lotes"          "200" "$(codigo GET /agente/consultar/listar_lotes)"
checar "consultar consultar_indicadores" "200" "$(codigo GET /agente/consultar/consultar_indicadores)"
checar "ferramenta inexistente"          "404" "$(codigo GET /agente/consultar/apagar_tudo)"
echo "== Escrita deve ser impossivel =="
for m in POST PUT PATCH DELETE; do
  checar "$m /agente/consultar/listar_lotes" "404 405" "$(codigo "$m" /agente/consultar/listar_lotes)"
done
echo
echo "Resumo da saude:"
curl -sS --max-time 30 -H "Authorization: Bearer $COWDATA_AGENTE_TOKEN" "$URL/agente/saude"; echo
if [[ $falhas -eq 0 ]]; then echo "TUDO OK"; else echo "$falhas verificacao(oes) falharam"; exit 1; fi
