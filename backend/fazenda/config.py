"""
Configurações centrais da aplicação — lidas de variáveis de ambiente / .env
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./fazenda.db"
    environment: str = "development"

    # Robô do Telegram (intake de documentos financeiros). Vazio = desligado.
    telegram_bot_token: str = ""            # token do @BotFather
    telegram_webhook_secret: str = ""       # segredo que valida chamadas do Telegram
    telegram_allowed_chat_ids: str = ""     # ids de chat liberados, separados por vírgula
    # A qual fazenda pertence cada chat do robô — "chat_id:fazenda_id" separados
    # por vírgula (ex.: "12345:1,67890:2"). Sem isso, o lançamento que chega
    # pelo Telegram nasce sem fazenda e aparece na fila de aprovação de todas
    # elas (ver LancamentoPendente.fazenda_id). Instalação de fazenda única
    # pode deixar vazio — o comportamento continua o de sempre.
    telegram_chat_fazenda: str = ""
    public_base_url: str = ""               # ex.: https://fazendaapp-production.up.railway.app
    # URL pública do frontend (site) — usada para montar o link de
    # redefinição de senha enviado por e-mail. Ex.: https://app.fazendaestreito.com
    frontend_base_url: str = "http://localhost:3000"

    # Envio de e-mail (recibo de lançamento financeiro, via Resend). Vazio = desligado.
    resend_api_key: str = ""
    email_remetente: str = "recibos@fazendaestreito.com"

    # Assinatura eletrônica do contrato CowData via ZapSign. Vazio = desligado
    # (o botão "Assinar contrato" retorna erro claro pedindo a configuração).
    # Token em Configurações > Integrações > API ZapSign; o webhook secret é
    # definido por você mesmo e cadastrado igual nos dois lados (ZapSign e aqui).
    zapsign_api_token: str = ""
    zapsign_webhook_secret: str = ""

    # Cobrança (boleto + PIX) via API do Banco do Brasil — scaffold inicial,
    # mantido para referência/plano B. Vazio = desligado (endpoints devolvem
    # erro claro). Ver ASAAS_* abaixo — é a integração ativa (jul/2026).
    bb_client_id: str = ""
    bb_client_secret: str = ""
    bb_developer_application_key: str = ""
    bb_ambiente: str = "sandbox"            # "sandbox" ou "producao"
    bb_pix_chave: str = ""                  # chave PIX recebedora cadastrada no BB
    # Segredo do webhook de cobrança BB, cadastrado igual nos dois lados (BB e
    # aqui) — o Portal Developers BB não embute segredo próprio no payload,
    # então esse valor vai na própria URL do webhook (/cobranca/webhook/bb/{secret}).
    # Vazio = webhook rejeita tudo (ver cobranca_webhook_bb).
    bb_webhook_secret: str = ""

    # Cobrança da assinatura CowData via Asaas (boleto mensal + Pix Automático/
    # recorrente + QR Code Pix dinâmico avulso para o desconto semestral) —
    # ver fazenda/rules/asaas.py. Vazio = desligado. Chave de API em
    # Asaas > Integrações > API Key; asaas_webhook_token é definido por você
    # mesmo e cadastrado igual nos dois lados (Asaas e aqui).
    asaas_api_key: str = ""
    asaas_ambiente: str = "sandbox"         # "sandbox" ou "producao"
    asaas_webhook_token: str = ""

    # Arquivo fiscal-contábil (notas, CCIR, IRPF/IRPJ, contratos...) via
    # Supabase Storage — o conteúdo vive lá, nunca no Postgres; o backend é o
    # único que fala com o Supabase (chave de serviço), o navegador só vê
    # nossos próprios endpoints (ver fazenda/rules/supabase_storage.py e
    # fazenda/api/routers/documentos.py). Vazio = desligado.
    supabase_url: str = ""                  # ex.: https://xxxxx.supabase.co
    supabase_service_key: str = ""          # service_role key (nunca a anon key)
    supabase_bucket: str = "documentos-fiscais"
    # Fotos do campo (app móvel) — bucket separado do arquivo fiscal-contábil
    # acima; mesma conta/chave de serviço do Supabase, ver fazenda/api/routers/fotos.py.
    supabase_bucket_fotos: str = "fotos-campo"
    # Anexo de lançamento financeiro (comprovante/nota de uma conta a pagar ou
    # receber) — bucket próprio, mesma conta/chave de serviço do Supabase, ver
    # fazenda/api/routers/financeiro.py (anexos de LancamentoAnexo).
    supabase_bucket_financeiro: str = "anexos-financeiro"
    # Banco de fotos do Milknews (blog News) — usado para ilustrar as matérias
    # na aba de aprovação/News, ver fazenda/api/routers/fotos_news.py. Único
    # bucket PÚBLICO do sistema (os outros três acima são privados): a página
    # pública do blog (GET /news, sem login) renderiza `<img src={imagem}>`
    # direto com a URL pública do Supabase Storage, sem passar pelo backend.
    supabase_bucket_news_fotos: str = "fotos-news-banco"

    # Push do app Android NATIVO (Capacitor) via Firebase Cloud Messaging —
    # canal irmão do Web Push (VAPID, acima em fazenda/api/routers/push.py):
    # dentro da WebView do Capacitor, Web Push não é confiável com o app
    # fechado, então o app nativo usa FCM (ver fazenda/rules/fcm.py). Vazio =
    # desligado (Web Push do navegador/PWA continua funcionando normalmente).
    # Valor: o CONTEÚDO INTEIRO do JSON da conta de serviço (Firebase Console
    # > Configurações do projeto > Contas de serviço > Gerar nova chave
    # privada), colado numa única variável de ambiente — NUNCA um arquivo no
    # repositório.
    fcm_service_account_json: str = ""
    fcm_project_id: str = ""  # opcional: por padrão sai do project_id do JSON acima

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
