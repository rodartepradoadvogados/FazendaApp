"""
Cliente do Supabase Storage — usado tanto pelo arquivo fiscal-contábil
integral (notas fiscais, CCIR, IRPF/IRPJ, inscrição estadual, matrículas,
contratos...; ver fazenda/models/documentos.py::DocumentoArquivado e
fazenda/api/routers/documentos.py) quanto pelas fotos do campo tiradas no
app móvel (ver fazenda/models/fotos.py::FotoCampo e
fazenda/api/routers/fotos.py) — cada um no seu próprio bucket
(settings.supabase_bucket vs settings.supabase_bucket_fotos).

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

import logging

import httpx

from fazenda.config import settings

logger = logging.getLogger(__name__)


def habilitado() -> bool:
    return bool(settings.supabase_url and settings.supabase_service_key)


def _exigir_config(bucket: str | None) -> tuple[str, str, str]:
    if not habilitado():
        raise RuntimeError(
            "Arquivo não configurado — defina SUPABASE_URL e SUPABASE_SERVICE_KEY "
            "nas variáveis de ambiente (Supabase > Configurações do projeto > API)."
        )
    return settings.supabase_url.rstrip("/"), settings.supabase_service_key, bucket or settings.supabase_bucket


def _headers(service_key: str, content_type: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def enviar_arquivo(caminho: str, conteudo: bytes, content_type: str, *, bucket: str | None = None) -> None:
    """Sobe (ou sobrescreve) o arquivo em `caminho` dentro do bucket (padrão: documentos fiscais)."""
    url, service_key, bucket_alvo = _exigir_config(bucket)
    resp = httpx.post(
        f"{url}/storage/v1/object/{bucket_alvo}/{caminho}",
        headers={**_headers(service_key, content_type), "x-upsert": "true"},
        content=conteudo,
        timeout=60,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Falha ao enviar arquivo ao Supabase Storage: {resp.status_code} {resp.text}")


def baixar_arquivo(caminho: str, *, bucket: str | None = None) -> bytes:
    url, service_key, bucket_alvo = _exigir_config(bucket)
    resp = httpx.get(
        f"{url}/storage/v1/object/{bucket_alvo}/{caminho}",
        headers=_headers(service_key),
        timeout=60,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Falha ao baixar arquivo do Supabase Storage: {resp.status_code} {resp.text}")
    return resp.content


def excluir_arquivo(caminho: str, *, bucket: str | None = None) -> None:
    url, service_key, bucket_alvo = _exigir_config(bucket)
    resp = httpx.delete(
        f"{url}/storage/v1/object/{bucket_alvo}/{caminho}",
        headers=_headers(service_key),
        timeout=30,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Falha ao excluir arquivo do Supabase Storage: {resp.status_code} {resp.text}")


def garantir_buckets() -> None:
    """Cria (idempotente) os buckets usados pelo sistema, se ainda não
    existirem — chamado uma vez no startup (main.py::lifespan), igual aos
    outros seeds idempotentes ali. Bucket do Supabase Storage não é criado
    sozinho por nenhum código deste repo até aqui — dependia de alguém criar
    manualmente pelo painel do Supabase (foi o que aconteceu com
    "documentos-fiscais" no passado); sem isso, todo upload ao bucket novo
    ("fotos-campo") falha com "bucket not found" e a foto fica para sempre
    tentando de novo na fila offline do app (>=500 == "tenta depois" — ver
    frontend/lib/offline.ts), nunca aparecendo como erro claro pro usuário.

    Não derruba o startup do app se o Supabase estiver fora do ar ou mal
    configurado — só loga o problema; o app deve subir mesmo assim (o
    arquivo fiscal-contábil e as fotos do campo já lidam com
    RuntimeError/502 nos próprios endpoints)."""
    if not habilitado():
        return
    url = settings.supabase_url.rstrip("/")
    service_key = settings.supabase_service_key
    for bucket in {settings.supabase_bucket, settings.supabase_bucket_fotos}:
        try:
            resp = httpx.get(f"{url}/storage/v1/bucket/{bucket}", headers=_headers(service_key), timeout=15)
            if resp.status_code == 200:
                continue
            resp = httpx.post(
                f"{url}/storage/v1/bucket",
                headers=_headers(service_key, "application/json"),
                json={"id": bucket, "name": bucket, "public": False},
                timeout=15,
            )
            if resp.status_code >= 300:
                logger.warning("Não foi possível criar o bucket '%s' no Supabase Storage: %s %s", bucket, resp.status_code, resp.text)
            else:
                logger.warning("Bucket '%s' criado no Supabase Storage (não existia).", bucket)
        except Exception:
            logger.warning("Falha ao verificar/criar o bucket '%s' no Supabase Storage.", bucket, exc_info=True)
