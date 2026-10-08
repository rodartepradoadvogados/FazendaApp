# AGENTS.md — CowData Milk — sistema de gestão de fazenda leiteira

Este repositório alimenta o projeto **`04_CowData/Milk`** do cofre Obsidian compartilhado
do escritório **Rodarte Prado Advogados**.

## O cofre é a memória comum

O cofre `Projetos-Obsidian` fica no computador do Jairo e é sincronizado com a VPS
pelo Syncthing. É compartilhado entre o **Claude Code**, os **bots do Hermes** e o Jairo.

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
  Não escreve em `Hermes/` nem em pastas de outros projetos.
- **Enriquecimento em duas camadas.** Todo aprendizado vira (a) uma nota datada no
  cofre e (b) a regra generalizável correspondente. Aprendizado não fica só na conversa.
- **Nunca commitar segredos** — tokens, chaves e `.env` ficam fora do repositório.
- **Conflitos `*.sync-conflict-*`:** nunca resolver sozinho. Avisar o Jairo.
- **LGPD:** sem CPF, dados de saúde ou dados de cliente no cofre.
- **Aprovação é do Jairo.** Nenhuma nota substitui um `status: aprovado` dele.

Mapa completo e territórios de todos os agentes: `00_AGENTES.md` na raiz do cofre.
