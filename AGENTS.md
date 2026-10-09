# AGENTS.md — CowData Milk — sistema de gestão de fazenda leiteira

Este repositório alimenta o projeto **`04_CowData/Milk`** do cofre Obsidian compartilhado
do escritório **Rodarte Prado Advogados**.

## O cofre é a memória comum

O cofre `Projetos-Obsidian` vive no **Google Drive** (conta
rodartepradoadvogados@gmail.com) e é sincronizado com a VPS por **rclone, a cada 5 minutos**.
É compartilhado entre o **Claude Code**, os **bots do Hermes** e o Jairo.

```
Projetos-Obsidian/
├── 00_AGENTES.md      ← mapa-mestre. LEIA ao iniciar cada sessão.
├── 01_Lumen/          ← software de gestão jurídica
├── 02_RodartePrado/   ← escritório: marketing e site
├── 03_Gabarito/       ← portal orquestrador
├── 04_CowData/        ← software de pecuária leiteira
└── Hermes/            ← sistema do Hermes. NUNCA escreva aqui.
```

## Onde registrar o que você faz

| O que | Caminho no cofre |
|-------|------------------|
| Sessão de desenvolvimento | `04_CowData/Milk/Sessoes/AAAA-MM-DD_assunto.md` |
| Decisão de arquitetura | `04_CowData/Milk/Sessoes/` |
| Geral do CowData | `04_CowData/Sessoes/` |

## Regras

- **Um dono por arquivo.** Neste projeto você escreve em `04_CowData/Milk/Sessoes/` e `04_CowData/Sessoes/`.
  Não escreve em `Hermes/`, em `hermes_para_claude/`, em `06_Publicacao/` (do bot de marketing) nem em pastas de outros projetos.
- **Enriquecimento em duas camadas.** Todo aprendizado vira (a) uma nota datada no
  cofre e (b) a regra generalizável correspondente. Aprendizado não fica só na conversa.
- **Nunca commitar segredos** — nenhum valor real de chave, senha, token ou string de conexão entra no repositório
  (código, `.env`, `.env.example`, seed, docs) nem no cofre. Segredos vivem nas variáveis de ambiente do provedor de deploy
  e no gerenciador de senhas da equipe; arquivos de exemplo trazem só o NOME da variável, vazio.
- **Conflitos `*.sync-conflict-*`:** nunca resolver sozinho. Avisar o Jairo.
- **LGPD:** sem CPF, dados de saúde, dados de cliente, tokens ou senhas no cofre.
- **O Drive é a fonte das mídias.** O cofre guarda notas e caminhos, não os arquivos pesados.
- **Aprovação é do Jairo.** Nenhuma nota substitui um `status: aprovado` dele.

## Regras específicas do projeto

- Leia `README.md`, `CONTEXTO_PROJETO_FAZENDA.md`, `PRODUCT.md` e `DESIGN.md` antes de alterar código.
- Os CSV/XLSM na raiz são dados reais da fazenda (Ideagri): não os reescreva e não os copie para o cofre.
- Decisões de arquitetura do Milk ficam em `04_CowData/Milk/Sessoes/` (nota com prefixo `ADR_`).

## Fim de sessão e comunicação

1. Grave nota datada no caminho da tabela acima; se surgiu regra generalizável, registre-a junto.
2. Para falar com o Hermes: `02_RodartePrado/90_Comunicacao/claude_para_hermes/AAAA-MM-DD_HHMM_assunto.md`.
3. **Sessão na nuvem não alcança o cofre** (ele fica no computador do Jairo e na VPS). Nesse caso, entregue o texto da nota ao Jairo na resposta final para ele gravar; não declare a nota como gravada.

Mapa completo e territórios de todos os agentes: `00_AGENTES.md` na raiz do cofre.
