# Gauntlet-loop — protocolo da banca

Mesma técnica usada no redesenho do Evento Sanitário (`docs/redesenho-evento-sanitario.md`): um construtor produz o mockup; uma **banca de 6 personas independentes** tenta *usar* o mockup para cumprir tarefas reais e o confronta com o contrato (`02-proposta.md`); as divergências são sintetizadas; o construtor corrige; repete até a conformidade passar do limiar.

## Banca (6 personas)

| # | Persona | Olha para | Não perdoa |
|---|---|---|---|
| 1 | **Zootecnista** (consultor de manejo/reprodução) | IATF, secagem, BST, agrupamento por lote, cobertura, dados para decidir | número sem fonte, lote confuso, regra de negócio simplificada |
| 2 | **Veterinário** | carência, lote/validade do frasco, esquema multidose/reforço, exames (TB/brucelose), rastreabilidade, conformidade | ação sem lote do frasco, aviso que bloqueia ou que some, jargão errado |
| 3 | **Peão de fazenda** (curral, luva, sol, celular) | alvo grande, poucos toques, texto curto, o que fazer agora | botão pequeno, texto técnico, tela que apaga ao tocar, não saber se salvou |
| 4 | **Produtor de leite / dono** (Jairo) | visão em 10 segundos, atrasos, custo, confiança de que "está em dia" | 8 contadores, ter que abrir 4 telas, não saber o que está atrasado |
| 5 | **Dono de cooperativa** (várias fazendas, auditoria) | comprovação, histórico exportável, padronização, conformidade sanitária oficial | ausência de registro auditável, motivo de "pular" sumido |
| 6 | **Pesquisador de gestão de pecuária leiteira** (métodos/UX) | modelo mental, consistência de vocabulário, arquitetura de informação, carga cognitiva | mesmo objeto com dois nomes, estados incoerentes, navegação escondida |

## Como cada persona avalia (por rodada)

1. Abre os HTML em Playwright (1440×900 e 390×844) e **executa as tarefas da sua lista** (abaixo) *clicando de verdade* — não só lendo o código. Registra passos, cliques, onde travou.
2. Confere o **contrato**: cada item marcado `[C]` na lista é um requisito da `02-proposta.md` que ela precisa ver funcionando.
3. Confere os **achados da crítica** marcados `[K]`: o problema apontado em `01-critica-consolidada.md` está realmente resolvido?
4. Dá **nota por item**: `1` = cumprido · `0,5` = parcial · `0` = falha. **Conformidade % = soma ÷ nº de itens**, por mockup.
5. Lista divergências com severidade **P0** (impede a tarefa) · **P1** (atrapalha muito) · **P2** (incomoda) · **P3** (polimento), cada uma com: onde, o que viu, o que deveria acontecer, correção concreta.
6. Não edita o mockup. Não conversa com as outras personas (independência).

## Síntese e critério de saída

O sintetizador (eu) junta as 6 avaliações, elimina duplicatas, resolve conflitos entre personas explicitando a decisão, e produz a **lista única de correções** para o construtor.

**Sai do loop quando:** média das 6 ≥ **90%** em *cada* mockup **e** nenhuma persona < 80% **e** zero P0 aberto. **Teto:** 4 rodadas (o que sobrar vira "pendência registrada").

## Tarefas por persona (mockup 1 = Vacinas e exames + Protocolos · mockup 2 = Agenda)

Legenda: `[C]` contrato · `[K]` achado da crítica resolvido.

### 1 · Zootecnista
**M1**
1. Ver, sem sair da primeira dobra, o que está atrasado e o que vem nesta semana. `[C §3.2]` `[K P0-1]`
2. Ver a cobertura vacinal por lote e identificar quem falta na Brucelose B19. `[C §3.5]`
3. Filtrar o calendário só para o lote *Recria 2*.
4. Lançar um protocolo IATF para um lote e **conferir as consequências** (animais, hormônio, dias na Agenda) antes de confirmar. `[C §4]` `[K P0 Central]`
5. Acompanhar um protocolo IATF em andamento e dar baixa de um dia com escolha de frasco. `[C §4]`
6. Duplicar um modelo de protocolo e ativar/inativar. `[C §4]`
**M2**
7. Trocar para agrupar por **Lote** e ler o que fazer em cada lote hoje. `[C §5.1]`
8. Abrir a gaveta Reprodução e ver candidatas/IATF atual sem poluir a lista de Hoje. `[K P1-4]`
9. Ver a Semana e achar o dia de maior carga. `[C §5.4]`

### 2 · Veterinário
**M1**
1. Registrar uma aplicação de aftosa escolhendo frasco, lote e validade; ver **carência** e resumo antes de confirmar. `[C §3.4]`
2. Perceber o aviso de lote perto do vencimento **sem que bloqueie**. `[C §1.7]`
3. Cadastrar uma vacina com esquema **multidose** (dose 1 → +30 d → anual) e ver as próximas 3 datas. `[C §3.7]`
4. Ver a carteira de vacinação de um animal. `[C §3.5]`
5. Achar exames pendentes/resultados no Histórico unificado. `[C §3.6]`
6. Pular uma aplicação com motivo e ver isso registrado. `[C §3.3]`
**M2**
7. Marcar como Feito uma aplicação sanitária da Agenda abrindo a gaveta Registrar com frasco/dose. `[C §5.4]`
8. Confirmar que "Checar retorno ao cio" e "PEV" estão descritos corretamente. `[C §2]`

### 3 · Peão de fazenda (usar o mockup a 390px)
**M1**
1. Achar "o que vacinar hoje" em ≤2 toques. `[C §3.2]`
2. Registrar uma aplicação (já pré-preenchida) e ter **certeza** de que salvou; desfazer por engano. `[C §3.4]`
3. Abrir a folha de campo para imprimir. `[C §3.5]`
**M2**
4. Abrir a Agenda e ver **Hoje** na primeira tela. `[C §5.1]` `[K P1-4]`
5. Marcar 3 tarefas como Feito em sequência **sem a lista apagar** e sem perder o lugar. `[C §5.4]` `[K P1-5]`
6. Marcar Feito numa tarefa de pesagem e numa de inseminação (gaveta com frasco) usando só o polegar; alvos ≥44px. `[K P1-11]`
7. Adiar uma tarefa para amanhã. `[C §5.4]`

### 4 · Produtor de leite / dono (Jairo)
**M1**
1. Em 10 s dizer quantas vacinas estão atrasadas e se o rebanho está em dia. `[C §3.2]`
2. Ver o custo previsto/realizado numa aplicação (resumo). `[C §3.4]`
3. Entender onde cadastrar uma vacina nova sem instrução. `[K P0-2]`
**M2**
4. Em 10 s dizer quantas tarefas atrasadas e quantas faltam hoje. `[C §5.1]`
5. Fechar o dia e ver o fechamento sóbrio. `[C §5.4]`
6. Achar contas a pagar sem misturá-las com tarefas de curral. `[C §5.2]`
7. Recuperar-se de "Simular erro de rede" sem ser deslogado. `[K P0-2 Agenda]`

### 5 · Dono de cooperativa
**M1**
1. Exportar histórico de aplicações filtrado por produto/lote. `[C §3.6]`
2. Ver comprovante "animal em dia" e folha de campo. `[C §3.5]`
3. Verificar que Pular/Desfazer/Reabrir deixam registro com motivo e quem. `[C §3.3]`
4. Ver que existe **uma só** porta de escrita (Registrar aplicação). `[K P0-2]`
**M2**
5. Exportar a agenda do dia/semana. `[C §5.1]`
6. Desfazer uma tarefa concluída e conferir que o estoque/aplicação voltam. `[K P0 Agenda]`

### 6 · Pesquisador de gestão / UX
**M1**
1. Listar todos os termos usados e conferir que seguem o glossário (nenhum "cronograma/ocorrência/gatilho"). `[C §2]`
2. Verificar que aba/filtro/drawer estão na URL e sobrevivem ao F5. `[C §1.5]`
3. Contar cliques até "registrar aplicação" e "cadastrar vacina". `[K P0-1, 7]`
4. Verificar estados com cor **e** ícone **e** texto. `[C §3.2]`
5. Verificar teclado (Enter na linha, Esc no drawer, trap) e `aria`. `[K P1-12]`
**M2**
6. Verificar que **um só verbo** ("Feito") existe e que nenhum evento mostra "Feito" sem poder ser feito. `[C §5.3]` `[K P1-7]`
7. Contar itens visíveis por decision point (≤4 controles na barra). `[C §1]`
8. Verificar que os 3 trilhos (campo/alertas/gestão) estão separados e só o campo conta no "Dia fechado". `[C §5.2]`
9. Verificar aderência ao DESIGN.md (2px, sem sombra pesada, sem border-left espessa, tokens, fonte ≥12px).

## Registro das rodadas

As avaliações e sínteses de cada rodada ficam em `04-gauntlet-rodadas.md` (gerado durante a execução).
