# FazendaApp — Software de Gestão da Fazenda Estreito Ponte de Pedra

## Estrutura do projeto

```
FazendaApp/
├── backend/                    # FastAPI + SQLModel
│   ├── fazenda/
│   │   ├── models/             # Modelos de banco (Animal, Servico, Parto, ...)
│   │   ├── parsers/            # Parsers dos CSV do Ideagri
│   │   │   ├── utils.py        # Utilitários (Win-1252, datas, decimais)
│   │   │   ├── geral.py        # GERAL.csv
│   │   │   ├── reprodutivo.py  # Consulta_SQL_v8.csv
│   │   │   ├── conta_gerencial.py
│   │   │   └── estoque.py
│   │   ├── rules/              # Regras de negócio (puras, testáveis)
│   │   │   ├── gestation.py    # Gestação por raça
│   │   │   ├── dry_off.py      # Secagem (60d, só vacas)
│   │   │   ├── scratch_pev.py  # Scratch (14d) + PEV (45d)
│   │   │   ├── iatf.py         # IATF — candidatas + doses
│   │   │   ├── bst.py          # BST — elegibilidade
│   │   │   └── agenda_engine.py # Motor da agenda
│   │   ├── api/routers/        # Endpoints FastAPI
│   │   │   ├── animais.py
│   │   │   ├── upload.py
│   │   │   ├── agenda.py
│   │   │   └── financeiro.py
│   │   ├── config.py           # Configurações (lê .env)
│   │   └── database.py         # Engine SQLite/PostgreSQL
│   ├── tests/
│   │   └── test_rules.py       # 27 testes das regras de negócio
│   ├── main.py                 # Ponto de entrada FastAPI
│   ├── requirements.txt
│   └── .env                    # DATABASE_URL (SQLite local)
├── frontend/                   # Next.js 14 + Tailwind
└── run_dev.py                  # Inicia backend em modo dev
```

## Como rodar o backend

### 1. Instalar dependências
```powershell
python -m pip install -r backend/requirements.txt
```

### 2. Rodar os testes
```powershell
python -m pytest backend/tests/ -v
```

### 3. Iniciar o servidor
```powershell
python run_dev.py
```
Acesse: http://localhost:8000/docs (Swagger UI interativo)

### 4. Carregar dados (CSV do Ideagri)
Use o Swagger em `/docs` ou a tela `/upload` do frontend.

**Ordem recomendada de upload:**
1. `GERAL.csv` → POST /upload/geral
2. `Consulta_SQL_v8.csv` → POST /upload/reprodutivo
3. `ESTOQUE.csv` → POST /upload/estoque
4. `CONTA_GERENCIAL.csv` → POST /upload/conta_gerencial

### 4.1. Sincronização automática (sem upload manual)

`sync_agent.py` vigia uma pasta local e envia os CSV sozinho — elimina o
arrastar-e-soltar e resolve o problema de cache do Google Drive (Seção 7 do
`CONTEXTO_PROJETO_FAZENDA.md`). Só usa a biblioteca padrão do Python.

```powershell
# No Ideagri: agendar a exportação diária dos relatórios para uma pasta, ex. C:\FazendaApp\ideagri
python sync_agent.py --dir C:\FazendaApp\ideagri --api https://SEU-BACKEND.up.railway.app
```

Ele detecta cada arquivo pelo nome, espera terminar de ser escrito, envia na
ordem correta e só reenvia quando o conteúdo muda (hash em `.sync_state.json`).
Use `--once` para rodar uma vez ou deixe rodando (varre a cada `--intervalo` s).

### 5. Consultar a agenda
```
GET http://localhost:8000/agenda/
GET http://localhost:8000/agenda/?data=2026-07-10
```

## Como rodar o frontend

```powershell
cd frontend
npm run dev
```
Acesse: http://localhost:3000

## Variáveis de ambiente (backend/.env)

| Variável | Padrão | Descrição |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./fazenda.db` | URL do banco. Trocar por `postgresql://...` no deploy |
| `SECRET_KEY` | `change-me` | Chave secreta para JWT (futuro) |
| `ENVIRONMENT` | `development` | `development` ou `production` |

## Endpoints principais

| Método | Rota | Descrição |
|---|---|---|
| GET | `/` | Health check |
| GET | `/docs` | Swagger UI |
| GET | `/animais/` | Lista animais (filtros: grupo, sit_rep) |
| GET | `/animais/{numero}` | Busca animal |
| POST | `/upload/{tipo}` | Upload CSV (geral/reprodutivo/estoque/conta_gerencial) |
| GET | `/agenda/` | Agenda preditiva (param: `?data=YYYY-MM-DD`) |
| POST | `/agenda/manual` | Adicionar evento manual |
| GET | `/financeiro/dre` | DRE por período e regime |
| GET | `/financeiro/contas-a-pagar` | Contas próximas |

## Regras de negócio implementadas

Todas as regras da Seção 5 do `CONTEXTO_PROJETO_FAZENDA.md` estão em `backend/fazenda/rules/`:

| Módulo | Regra | Critério |
|---|---|---|
| `gestation.py` | Gestação | Holandês 280d / Girolando 287d / Gir+Zebu 295d |
| `dry_off.py` | Secagem | 60d antes do parto; só vacas (ordem_parto > 0) |
| `scratch_pev.py` | Scratch | 14d pós serviço; NEGATIVO cancela |
| `scratch_pev.py` | PEV | 45d pós parto |
| `iatf.py` | IATF | Vaz. apt. / Vaz. atr. / Diag. NEGATIVO; calcula doses |
| `bst.py` | BST | Grupos 01/02/03; DEL≥60; >15d p/ secar |
| `agenda_engine.py` | Motor agenda | Orquestra tudo → lista cronológica |

## Deploy (produção)

**Railway** (recomendado — une backend + banco num projeto):
1. Criar projeto Railway
2. Add service: PostgreSQL → copiar `DATABASE_URL`
3. Add service: GitHub repo → `backend/` → `python -m uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add service: GitHub repo → `frontend/` → Next.js auto-detected

**Vercel** (alternativa para o frontend):
- Deploy `frontend/` no Vercel
- Setar `NEXT_PUBLIC_API_URL` apontando para o Railway
