# As 25 altas da auditoria: estado em 06/09/2026

Conferi as **25** de severidade alta uma a uma no código da `main`, como foi
feito com as críticas. **Todas estão fechadas.** Nenhuma correção nova foi
necessária, e este documento não propõe mudança de código — ele registra o
estado e o que ele revela.

O achado que interessa não é nenhuma delas em particular. É o que aparece
quando se olha *como* foram fechadas.

## Três formas de estar fechado, e elas não valem o mesmo

| | Como está fechado | Quantos |
|---|---|---|
| **A** | Trava estrutural — resolvedor estrito, rota movida de lugar, segredo validado, autoescape ligado | 12 |
| **B** | Filtro incondicional na própria consulta (`_buscar_da_fazenda` e equivalentes) | 4 |
| **C** | **Padrão tolerante** — `if fazenda_id is not None`, sobre o objeto já carregado | 9 |

### A — fechado por trava estrutural (12)

`#14` webhook do BB agora exige `BB_WEBHOOK_SECRET` comparado em tempo
constante; `#27` marcar inapta para BST, `#29` cadastrar preventivo, `#33` as
três exclusões da Farmácia, `#38` registrar alimentação real, `#41` importação
de genealogia e `#43` importação de calendário passaram a `get_fazenda_id_escrita`;
`#47` e `#48` (revogação de sessão de suporte, hoje conferida no middleware a
cada requisição) foram corrigidos na própria sessão da auditoria; `#51` teve as
rotas de touro **movidas** para o Painel CowData atrás de `_dep_edicao` — mesma
correção estrutural do achado 35; `#55` sanitiza a key do Storage; `#62` liga
`select_autoescape` no Jinja2.

Essas não dependem de mais nada. São as únicas que continuariam fechadas se
todo o resto do sistema mudasse.

### B — fechado por filtro incondicional (4)

`#10` editar Serviço e `#11` editar Parto passaram a `_buscar_da_fazenda`, que
põe o recorte dentro da consulta; `#52` e `#26` filtram na consulta que monta o
relatório. "De outra fazenda" e "sem fazenda" caem os dois em não encontrado.

### C — fechado pelo padrão tolerante (9)

`#6` relatório de BST, `#12` vincular evento sanitário, `#13` recibo por
número, `#17` folha de pagamento (17 rotas), `#18` empreitadas e contratos (11
rotas), `#19` dados pessoais e anexos, `#25` desmarcar protocolo, `#35` e `#36`
produto da tabela nutricional.

Todas seguem a forma:

```python
fazenda_id = fazenda_id_seguro(fazenda_id)          # pode virar None
...
if fazenda_id is not None:                          # com None, não filtra nada
    query = query.where(Modelo.fazenda_id == fazenda_id)
```

**Elas funcionam hoje.** Não porque a guarda seja boa, mas porque a trava de
porta (`auth.py::exigir_fazenda_selecionada`) recusa o token sem `"fid"` antes
de a requisição chegar na rota. O isolamento delas é emprestado: mora em outro
arquivo, e some no dia em que alguém montar um router novo sem `_protegido`.

## O que isso revela

**As "altas" e a dívida das 188 rotas são o mesmo problema visto de dois
ângulos.** A auditoria enxergou 25 sintomas; a catraca do PR #712 mediu a
doença: 188 rotas de escrita ainda resolvem `fazenda_id` pela dependência
tolerante. As 9 do grupo C são um subconjunto dessas 188.

Corrigir as 9 do grupo C não fecharia nada que esteja aberto hoje — fecharia a
**dependência** de que a trava de porta continue existindo e continue montada
em todo router.

## Como priorizar a redução da dívida

"188 rotas" não é um plano. Dois cortes foram medidos:

**Por verbo** — o modo de falha muda:

| Verbo | Quantas | O que acontece se o isolamento falhar |
|---|---|---|
| `DELETE` | **53** | **perda de dado**, sem volta |
| `PUT` | 80 | dado da vítima alterado em silêncio |
| `POST` | 54 | registro nasce órfão ou no lugar errado |
| `PATCH` | 1 | idem |

**As 53 exclusões vêm primeiro**, e a razão não é estatística: nas outras o
estrago é reversível com backup; numa exclusão em cascata cruzada, não é. Foi
exatamente esse raciocínio que levou o achado 44 (`exclusoes.py`) a receber
filtro **incondicional** em vez de tolerante, com o comentário no código
dizendo por quê: "aqui não se lê dado demais, se APAGA dado demais, e isso não
tem volta".

**Por arquivo marcado pela auditoria** — 108 das 188 estão em arquivos que têm
pelo menos um achado alto ou crítico. É um corte mais fraco que o anterior
(estar no mesmo arquivo não diz nada sobre a rota em si) e serve só para
ordenar dentro do primeiro.

## Ordem sugerida

1. As **53 rotas `DELETE`** da lista congelada, começando pelas que apagam em
   cascata.
2. As `PUT`/`POST` nos arquivos com achado alto ou crítico.
3. O resto, à medida que cada arquivo for tocado por outro motivo.

Cada correção tira uma linha da lista da catraca, que é como esse número
desce sem precisar de um mutirão.

**Ressalva sobre território:** `financeiro.py` (24), `cadastro/rh_folha.py`
(16), `cadastro/rh_contratos.py` (12), `cadastro/pessoas.py` (4) e
`exclusoes.py` (4) — 60 das 188 — são de outras sessões. A ordem acima vale
para elas, mas a execução não é desta sessão.
