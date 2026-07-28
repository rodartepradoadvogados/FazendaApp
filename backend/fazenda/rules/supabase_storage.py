"""
Cliente do Supabase Storage — arquivo fiscal-contábil integral (notas fiscais,
CCIR, IRPF/IRPJ, inscrição estadual, matrículas, contratos...). Ver
fazenda/models/documentos.py::DocumentoArquivado e
fazenda/api/routers/documentos.py.

O conteúdo do arquivo nunca passa pelo Postgres — só o caminho dentro do
bucket é guardado. O navegador do usuário nunca fala com o Supabase: todo
upload/download passa pelo nosso próprio backend (chave de serviço,
storage/v1/object REST), o que preserva a sensação de que o anexo está
"dentro do site" e mantém o controle de acesso por fazenda_id igual a
qualquer outro dado do sistema.

Documentação: https://supabase.com/docs/guides/storage/uploads/standard-uploads
(REST puro via httpx, sem o SDK oficial — mesmo estilo de fazenda/rules/asaas.py).

Sem SUPABASE_URL/SUPABASE_SERVICE_KEY configurados, toda função abaixo
levanta RuntimeError com mensagem clara — não falha silenciosamente.
"""
from __future__ import annotations

import httpx

from fazenda.config import settings


def habilitado() -> bool:
    return bool(settings.supabase_url and settings.supabase_service_key)


def _exigir_config() -> tuple[str, str, str]:
    if not habilitado():
        raise RuntimeError(
            "Arquivo fiscal-contábil não configurado — defina SUPABASE_URL e "
            "SUPABASE_SERVICE_KEY nas variáveis de ambiente (Supabase > Configurações "
            "do projeto > API)."
        )
    return settings.supabase_url.rstrip("/"), settings.supabase_service_key, settings.supabase_bucket


def _headers(service_key: str, content_type: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def enviar_arquivo(caminho: str, conteudo: bytes, content_type: str) -> None:
    """Sobe (ou sobrescreve) o arquivo em `caminho` dentro do bucket."""
    url, service_key, bucket = _exigir_config()
    resp = httpx.post(
        f"{url}/storage/v1/object/{bucket}/{caminho}",
        headers={**_headers(service_key, content_type), "x-upsert": "true"},
        content=conteudo,
        timeout=60,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Falha ao enviar arquivo ao Supabase Storage: {resp.status_code} {resp.text}")


def baixar_arquivo(caminho: str) -> bytes:
    url, service_key, bucket = _exigir_config()
    resp = httpx.get(
        f"{url}/storage/v1/object/{bucket}/{caminho}",
        headers=_headers(service_key),
        timeout=60,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Falha ao baixar arquivo do Supabase Storage: {resp.status_code} {resp.text}")
    return resp.content


def excluir_arquivo(caminho: str) -> None:
    url, service_key, bucket = _exigir_config()
    resp = httpx.delete(
        f"{url}/storage/v1/object/{bucket}/{caminho}",
        headers=_headers(service_key),
        timeout=30,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Falha ao excluir arquivo do Supabase Storage: {resp.status_code} {resp.text}")
