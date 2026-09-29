# Rotina da lista de espera (decisão do dono)

Objetivo: animais que se aproximam da janela de uma regra de vacina/exame cadastrada entram na **lista de espera** sozinhos.

## Condicionantes (todas obrigatórias)
1. A fazenda **marcou** a rotina como ativa em Parâmetros (padrão: desligada).
2. Existem **regras de vacina ou exame cadastradas** (sem regra, a rotina não atua).
3. O resto vem do **evento/regra já cadastrado** (janela, produto, frequência, critérios). Nada é configurado em dobro.

## Parâmetros da fazenda (módulo Parâmetros)
- **Ativar rotina da lista de espera** (sim/não).
- **Dias de antecedência:** quantos dias antes de o animal entrar na janela cadastrada ele entra na lista de espera.
- **Aviso diário nos cards da 2ª aba da Agenda** (sim/não): no máximo **uma vez por dia**, nunca várias.

## Onde aparece
- **Nunca** nas tarefas do dia a dia (1ª sub-aba da Agenda).
- Na **2ª sub-aba (Painel)**: card próprio "Animais na lista de espera", só quando o aviso diário estiver ligado.
- Atalho para Protocolos › Aplicar.

## O que a rotina não faz
Não aplica, não baixa estoque, não cria agendamento. Só prepara a lista.

## Dependências
- Painel (2ª sub-aba) faz parte da etapa 10; até lá a linha-atalho da Agenda (etapa 6) é só link, não tarefa.
- Vem depois da etapa 7 (lista de espera e agendamento).
