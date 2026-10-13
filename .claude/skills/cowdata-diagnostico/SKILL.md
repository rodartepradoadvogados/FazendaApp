---
name: cowdata-diagnostico
description: >
  Método para diagnosticar "implementei X mas não vejo X funcionando" no CowData/Milk
  (FazendaApp): confere o relato contra o commit, o diff e o deploy, segue o evento da
  escrita à leitura, prova com dado, respeita limites de plataforma (Android/FCM, PWA) e
  entrega um plano em fases com critério de aceite — sem implementar. Use quando o
  usuário ou outro agente relatar uma entrega que não aparece na tela, quando um
  relatório/tela de auditoria estiver vazio ou incompleto, ou quando for pedido
  "diagnostique, ache as falhas e proponha solução".
---

# cowdata-diagnostico

Regra-mãe: **relato de entrega (inclusive de outro bot) é hipótese, não fato.** Fato é commit,
diff, deploy e dado.

## Passos (nesta ordem)

1. **Contexto.** Ler `00_AGENTES.md`, `04_CowData/00_Mapa.md`, as últimas notas de
   `04_CowData/Milk/Sessoes/` e `AGENTS.md`. Anotar o que está desatualizado.
2. **Estar no commit certo.** `git fetch origin main` e comparar com o SHA citado. Se o
   relato cita um PR, `git cat-file -t <sha>` e `git diff --stat <antes> <depois>`.
3. **Procurar os símbolos do relato** (`grep` nomes de tabela, rota, campo, função). Zero
   ocorrências = "não está neste commit", nunca "não achei".
4. **Confirmar o que roda em produção:** deploy do Railway (backend) e da Vercel (front) —
   pelo **SHA**, não pelo título.
5. **Escrita → leitura → gatilho.** Quem grava o evento? Quem lê? O que dispara a gravação?
   Quanto tempo a sessão/token dura? Se o gatilho é raro (login com token de 90 dias), o
   relatório será pobre por construção.
6. **Par "front manda / back recebe".** Para cada campo novo: `grep` nos dois lados e teste de
   ida-e-volta. Pydantic descarta campo desconhecido sem avisar.
7. **Limites da plataforma antes de prometer.** FCM com `notification` e app fechado: o
   Android desenha sozinho, o JS não vê o recebimento. Ícone = recurso Android (PNG branco
   sobre transparente) + manifest + canal + **novo APK**.
8. **Provar com número** (consulta somente leitura, agregada, sem nomes) quando houver
   acesso ao banco. Se não houver, escrever a consulta e dizer que não foi medido.
9. **Plano em fases:** reconciliar relato → corrigir a leitura/escrita → testes → verificação
   em produção → memória. Cada fase com **critério de aceite observável**. Decisões do Jairo
   listadas à parte.
10. **Entregar separando** o provado, o suposto e o não verificado.

## Registrar (duas camadas)

- **O caso:** nota datada em `04_CowData/Milk/Sessoes/AAAA-MM-DD_assunto.md` (`status: rascunho`).
- **A regra:** esta skill (ou, sem acesso a `skill_manage`, nota `tipo: skill` em `Sessoes/`).
- Sessão na nuvem: o conector do Google Drive só **cria** arquivo novo; correção de arquivo
  existente vai pela "ponte de correção" do `00_AGENTES.md` (antes/depois, o Hermes aplica).

## Nunca

Declarar "mesclado/em produção" sem SHA + deploy `SUCCESS`; gravar segredo, CPF ou dado de
cliente; resolver `*.sync-conflict-*`; escrever fora do próprio território no cofre.
