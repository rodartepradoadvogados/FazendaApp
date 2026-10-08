# AGENTS.md — FazendaApp (CowData — Milk)

## Cofre compartilhado (Obsidian)

O cofre "Projetos-Obsidian" (`C:\Users\jairo\Projetos-Obsidian\`, sincronizado com a VPS pelo
Syncthing) é a memória comum entre Claude Code, Hermes (bots de Telegram) e o Jairo.
**Ao iniciar a sessão, leia `00_AGENTS.md`** na raiz do cofre (mapa-mestre).

Este projeto alimenta: **`04_CowData/Milk/`**

| Para quê | Onde |
|---|---|
| Sessões de desenvolvimento | `04_CowData/Milk/Sessoes/` |
| Decisões de arquitetura | `04_CowData/Milk/Sessoes/ (nota com prefixo `ADR_`); regra geral em 04_CowData/Sessoes/` |

## Regras do cofre (valem para este projeto)

- **Um dono por arquivo.** Só escreve quem é dono; os demais apenas leem.
- **Nunca escreva em `Hermes/`** (sistema do Hermes) nem em `hermes_para_claude/`.
- **Enriquecimento em duas camadas:** todo aprendizado vira (a) nota datada na pasta do projeto e
  (b) a regra generalizável correspondente. Aprendizado não fica só na conversa.
- **Conflitos do Syncthing (`*.sync-conflict-*`):** nunca resolver sozinho; avisar o Jairo.
- **LGPD:** sem CPF, dados de saúde, tokens ou senhas no cofre.
- **O Drive é a fonte das mídias.** O cofre guarda notas e caminhos, não os arquivos.
- **Aprovação é do Jairo.** Nenhuma nota substitui um `status: aprovado` dele.
- A pasta `RodartePrado/` foi renomeada para `02_RodartePrado/` (07/10/2026). Use sempre o nome novo.

## Ao final de cada sessão

1. Grave nota datada (`AAAA-MM-DD_assunto.md`) em `04_CowData/Milk/Sessoes/`.
2. Se surgiu regra generalizável, registre-a junto (e, se for decisão de arquitetura, em `04_CowData/Milk/Sessoes/ (prefixo `ADR_`)`).
3. Se precisar do Hermes, deixe mensagem em
   `02_RodartePrado/90_Comunicacao/claude_para_hermes/AAAA-MM-DD_HHMM_assunto.md`.

## Segredos — proibido commitar

Nenhum valor real de chave, senha, token ou string de conexão entra no repositório (código,
`.env.example`, seed, docs) nem no cofre. Segredos vivem nas variáveis de ambiente do provedor de
deploy e no gerenciador de senhas da equipe. Arquivos de exemplo só trazem o NOME da variável, vazio.

## Regras específicas do projeto

- Escrita do Claude neste projeto: `04_CowData/Milk/Sessoes/` e `04_CowData/Sessoes/`.
- Leia `README.md`, `CONTEXTO_PROJETO_FAZENDA.md`, `PRODUCT.md` e `DESIGN.md` antes de alterar código.
- Os CSV/XLSM na raiz são dados reais da fazenda (Ideagri): não os reescreva, não os copie para o cofre.
