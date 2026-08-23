# Equivalente maduro — proposta de cálculo, relatório e calculadora

> **SUPERADO pela seção 8** (redesign "padronização por vaca", aprovado e
> implementado). As seções 1-7 abaixo continuam valendo como HISTÓRICO da
> primeira versão (fatores calibrados no rebanho, mínimo de 20 lactações por
> classe) — é o desenho que estava em produção antes do redesign, e o
> raciocínio de pesquisa (305-ME aposentado, tabela Embrapa é de Gir) ainda é
> válido como contexto. Mas o CÓDIGO hoje (`rules/equivalente_maduro.py`,
> `rules/curva_lactacao_referencia.py`) segue a seção 8, não estas.

Documento de decisão. Não há código nesta entrega: o objetivo é fechar o
método antes de implementar, porque as duas escolhas centrais (de onde vêm os
fatores e como se calcula a produção de 305 dias) são difíceis de trocar depois
que houver número na tela e gente decidindo descarte com ele.

---

## 1. A pergunta que a entrega tem de responder

Não é "comparar em pé de igualdade". É **quanto esta vaca ainda vai crescer**.

Toda apresentação — relatório, calculadora e curva — mostra o par lado a lado:

| | |
|---|---|
| **Produz hoje** | o real observado, na ordem de parto atual |
| **Produzirá na maturidade** | o mesmo animal ajustado à base madura |
| **Diferença** | quanto ainda tem a subir, ou zero se já chegou lá |

Isso inverte o uso do dado. Uma novilha de 1ª cria com 25 kg e uma vaca de 4ª
cria com 30 kg parecem, hoje, a vaca sendo melhor. Ajustada, a novilha pode
projetar mais que a vaca. **É decisão de descarte e de seleção, não
estatística**: a primípara boa descartada por parecer pior que a multípara
mediana é exatamente o erro que este indicador existe para impedir.

Três consequências que o número precisa respeitar para não mentir:

- o ajuste **encolhe** conforme o animal amadurece e vale ~1,00 na vaca já
  madura — a coluna "produzirá" tem de convergir para a real, senão está errado;
- na vaca madura a diferença é ~zero, e a tela deve **dizer isso**, não fingir
  projeção;
- a incerteza é **maior justamente na 1ª cria**, onde o ajuste é maior. Número
  seco ali é falsa precisão.

---

## 2. O que a pesquisa encontrou — e uma notícia que muda o plano

### O padrão americano foi aposentado pelo próprio autor

O **305-ME** (*mature equivalent*) foi o padrão do DHI americano de 1994 até
**junho de 2024**, quando o CDCB o descontinuou e o substituiu pelo **305-AA**
(*average age*), padronizado aos **36 meses** em vez de "idade madura".

As razões declaradas valem para nós:

- os fatores eram de 1994, e três décadas de seleção mudaram o padrão de
  maturidade das vacas;
- a base "madura" do 305-ME era de 61 a 86 meses, e **boa parte das vacas
  modernas é descartada antes disso** — extrapolar "o que ela produziria se
  madura" ficou cada vez menos verificável para a maioria do rebanho.

Copiar o 305-ME hoje seria copiar algo que quem publicava parou de publicar.

### Existe base brasileira, e ela trata a estação de outro jeito

A Embrapa Gado de Leite, com a ABCGIL, publicou fatores de ajustamento da
produção total e aos 305 dias para **Gir Leiteiro**, sobre 39.157 lactações de
16.898 vacas em 240 rebanhos (partos de 1960 a 2008), com classes de idade ao
parto de 6 em 6 meses.

O ponto que interessa: a **época de parto é regionalizada**. Seca de abril a
setembro no Sudeste; **o inverso** no Nordeste. O modelo americano usa mês fixo
do calendário do hemisfério norte. Não é uma diferença de detalhe — é a prova de
que a tabela americana não se transplanta.

Não localizei tabela equivalente publicada para Holandês puro em condições
brasileiras.

### Aviso sobre o grau de confiança desta seção

O ambiente onde a pesquisa rodou **bloqueia leitura direta de praticamente
todas as fontes primárias** (CDCB, ICAR, Journal of Dairy Science, Embrapa,
SciELO, PubMed). O levantamento saiu de resumos de busca, não de leitura do
texto original. Tratar como **indicação forte a confirmar**, não como citação
conferida. O que está corroborado por várias fontes independentes: a
descontinuação do 305-ME e a existência dos fatores da Embrapa. O que está em
fonte única e **não** deve virar número na tela sem conferência: qualquer tabela
de fatores específica.

---

## 3. O que a fazenda já tem, e o que falta

Levantado no código, com citação de arquivo e linha.

### O bloqueio: a ordem de parto do controle nunca é gravada

`ControleLeiteiro.ordem_parto` (`models/producao.py:32`) é **lido** em
`routers/producao.py:131,141` e **nunca escrito**. Confirmado nas quatro vias de
entrada: lançamento manual (`producao.py:151-204`), app de campo
(`mobile/lancar/FormProducao.tsx:191`), importação de planilha
(`producao.py:385-440`) e parser legado (`parsers/controle_leiteiro.py:16-43`).

Como consequência, `listar_controles` cai sempre no *fallback*
(`producao.py:131`): a **contagem atual** de partos do animal, aplicada a todo o
histórico dele. **Uma vaca hoje de 5ª cria tem os controles de quando era
primípara rotulados como "5ª".**

Equivalente maduro é, por definição, ajuste por idade e ordem de parto. Sobre
esse histórico, qualquer EM sai errado. **É pré-requisito, não detalhe.**

### A ponte que eu supunha existir não existe

O plano previa reconstruir a ordem casando `ControleLeiteiro.data_ult_parto` com
`Parto.data_parto`. Mas `data_ult_parto` só é escrito pelo **parser legado**
(`parsers/controle_leiteiro.py:39`), lido de uma coluna do CSV. Nas três vias que
o app usa hoje ele fica nulo.

A reconstrução tem de ser **por data**: para cada controle, o parto mais recente
**anterior** à data do controle, e daí `Parto.ordem_parto` — que é populado
(`reproducao.py:1196` calcula, `parsers/reprodutivo.py:169` e
`importar.py:688` copiam do arquivo).

### Outras correções ao que eu havia assumido

- `Animal` **não tem** `n_partos` nem data do último parto. O último parto só
  sai consultando a tabela `Parto`.
- `Animal.idade_meses` (`animais.py:32`) é **congelado**, vem pronto do
  `GERAL.csv` e nunca é recalculado a partir de `data_nasc`. Não serve como
  entrada de cálculo — a idade ao parto tem de ser
  `Parto.data_parto − Animal.data_nasc`.
- **Época do parto não existe em lugar nenhum do sistema**, backend ou frontend.
  Os filtros `fAno`/`fMes` (`producao/page.tsx:150-151`) filtram o mês do
  *controle*, não do parto, e são só filtro de tela.

### A projeção de 305 dias de hoje é uma conta de guardanapo

`producao/page.tsx:303-325`: agrupa por `numero + ordem_parto` (usando a ordem
errada acima), tira a **média aritmética** dos controles e faz `média × 305`
(`:322`). A própria tela admite o método (`:916-917`).

Isso ignora que cada controle representa um intervalo de duração diferente e que
as pontas da lactação não são cobertas. Se o EM for sobre base 305, isto precisa
virar cálculo de verdade antes.

---

## 4. Método proposto — três camadas

### Camada 1 — produção de 305 dias pelo método de intervalo de teste

Substituir `média × 305` pelo **Test Interval Method** da ICAR, que é integração
trapezoidal: cada controle pesa pela metade dos intervalos vizinhos, e as pontas
(do parto ao 1º controle, do último ao fim) entram por meio-intervalo.

```
Produção = I₀·M₁ + I₁·(M₁+M₂)/2 + I₂·(M₂+M₃)/2 + … + Iₙ·Mₙ
```
onde `I` é o intervalo em dias entre datas de controle e `M` a produção no dia
do controle.

Ressalva honesta, que a tela deve carregar: o TIM **também** tende a
superestimar, e o viés cresce quanto mais espaçados os controles. Um rebanho com
controle mensal erra menos que um com controle trimestral. Se a fazenda controla
esporadicamente, o número de 305 dias é estimativa grosseira e não deve ser
apresentado com duas casas decimais.

### Camada 2 — fatores calibrados no próprio rebanho

Você já decidiu isso ("modelo ajustado ao seu rebanho"), e a pesquisa reforça:
o padrão americano foi aposentado e o brasileiro publicado é de Gir/Girolando.

O método: para cada **classe de ordem de parto** (1ª, 2ª, 3ª, 4ª+), calcular a
produção média de 305 dias das lactações **encerradas** do próprio rebanho, e o
fator da classe é

```
fator(ordem) = média305(classe madura) / média305(ordem)
```

com a classe madura sendo 3ª+ (ou 4ª+, a decidir com os dados). Por construção o
fator da classe madura é 1,00 — que é a convergência exigida na seção 1.

**Quando não há dado suficiente**: abaixo de um mínimo de lactações por classe,
o sistema **não inventa fator**. Diz "sem base para ajustar" e mostra só a
produção real. Preferível a exibir um número derivado de meia dúzia de vacas.

**Idade dentro da ordem de parto não é a mesma coisa que ordem de parto.** Uma
novilha que pariu aos 22 meses e outra aos 30, ambas 1ª cria, não têm o mesmo
potencial. O método padrão trata os dois eixos separadamente. Proposta:
**começar só por ordem de parto** — que é o eixo de maior efeito e o que o
rebanho tem massa para estimar — e deixar o refinamento por idade e por época
como etapa 2, quando houver histórico bastante. Registrar isso na tela em vez de
esconder.

### Camada 3 — a apresentação do par

Nunca mostrar o equivalente maduro sozinho. Sempre os três números da seção 1,
e, na vaca já madura, a frase em vez do número: *"já está na maturidade"*.

Para a 1ª cria, exibir a diferença como **faixa**, não como valor único — é onde
o ajuste é maior e a incerteza também.

---

## 5. Onde entra no sistema

**Relatório** (Produção). Lista por animal com as colunas produz hoje ·
produzirá · diferença · ordem de parto · nº de controles que sustentam a conta.
Ordenável pela diferença: é a lista de "quem ainda vai crescer" — e a lista de
descarte lida ao contrário.

**Calculadora**. Simulação avulsa, que **não persiste**: informa ordem de parto,
DEL e produção observada, devolve o equivalente maduro. Serve para avaliar
animal de fora (compra) sem sujar a base. Há padrão pronto para reaproveitar:
`POST /financeiro/calcular-juros` (`financeiro.py:3140-3171`) com
`RecalculoJuros` (`contador/PainelExtraordinario.tsx:111-181`), que calcula e não
grava.

**Curva de lactação** (ficha do animal). É a Sessão 5, que depende desta
aprovação: as quatro séries que você pediu — real, esperada, média do rebanho e
equivalente maduro projetado.

⚠ Antes disso, a "média do rebanho" de hoje **não é comparável**:
`_curva_referencia_rebanho` (`animais.py:733-753`) filtra **só por fazenda** —
todas as raças, todas as ordens de parto, todo o histórico, sem nem a janela de
400 dias que a tela de Produção usa. Para servir de referência por ordem de
parto, precisa de recorte.

**Ficha do animal**. O par produz hoje × produzirá, junto do card da curva.

---

## 6. O que precisa ser decidido com você

1. **Classe madura: 3ª+ ou 4ª+?** Depende de quantas lactações encerradas o
   rebanho tem em cada classe — respondo com os dados assim que rodar o
   levantamento, se você autorizar consulta ao banco.
2. **Mínimo de lactações por classe para publicar um fator.** Minha sugestão é
   não mostrar ajuste abaixo de 20 lactações encerradas na classe, e sinalizar
   entre 20 e 50.
3. **Reconstrução histórica da ordem de parto**: reescrever
   `ControleLeiteiro.ordem_parto` de uma vez para todo o histórico (mudança de
   dado, reversível mas ampla), ou derivar por data a cada consulta (mais lento,
   sem tocar em dado)? Recomendo **gravar**, porque a derivação por data seria
   refeita em toda tela que usar EM.
4. **A confirmação das fontes.** Quer que eu insista em confirmar o 305-AA e os
   fatores da Embrapa em texto primário — o que provavelmente exige liberar
   domínios na configuração de rede do ambiente — ou seguimos com a calibração
   no próprio rebanho, que não depende de tabela externa nenhuma?

Vale notar que a resposta 4 tem uma saída elegante: **como o método proposto
calibra no próprio rebanho, ele não depende de nenhuma tabela publicada**. A
pesquisa serve para justificar a escolha e para não repetir erro conhecido, não
para fornecer números. Isso torna a proposta robusta ao bloqueio de rede.

---

## 7. O que este indicador não faz

Registrar junto, para não virar promessa:

- **Não prevê o futuro de uma vaca individual.** É a média da classe aplicada a
  um animal; a vaca concreta pode ficar acima ou abaixo.
- **Não substitui índice econômico.** Há evidência de que trocar produção real
  por equivalente maduro dentro de um índice de seleção **piora** a predição de
  lucro. O EM é para comparar animais entre si, não para prever resultado
  financeiro.
- **Não conserta dado ruim.** Rebanho com controle leiteiro esporádico terá
  produção de 305 dias mal estimada, e o ajuste só propaga esse erro.

---

## 8. Redesign aprovado — "padronização por vaca" (o que está implementado hoje)

Depois de rodar em produção com o desenho das seções 1-7, o dono aprovou uma
mudança de rumo (mockup mostrado e aprovado literalmente: "Implemente
exatamente assim"). Registro aqui porque é o desenho VIGENTE — as seções
anteriores ficam como histórico do que existia antes.

### 8.1 O que mudou, e por quê

O desenho anterior calibrava o fator de ajuste no próprio rebanho e exigia um
mínimo de 20 lactações ENCERRADAS por classe para publicar qualquer número. Na
prática isso significava: numa fazenda pequena, ou logo depois de trocar o
jeito de registrar lactação, uma novilha de 1ª cria não recebia EM nenhum
enquanto o rebanho não acumulasse histórico — mesmo tendo ela mesma 2, 3, 10
controles próprios perfeitamente utilizáveis.

Decisão: trocar "fator calibrado no rebanho, com mínimo de amostra" por
"fator fixo de tabela (raça Holandês, sempre), sem mínimo nenhum do
rebanho". Qualquer animal com produção de 305 dias calculável (≥ 2 controles
utilizáveis na lactação atual) e ordem de parto conhecida recebe o trio
completo — inclusive uma primípara de 100 dias em leite num rebanho com zero
lactação encerrada.

### 8.2 Fatores fixos (raça Holandês)

| Classe | Fator |
|---|---|
| 1ª cria | 1,22 |
| 2ª cria | 1,08 |
| Madura (3ª+) | 1,00 |

`FATOR_HOLANDES` em `rules/equivalente_maduro.py`. **[risco]** Vêm de
conhecimento treinado sobre o padrão de maturidade de Holandês, NÃO de
tabela CDCB/ICAR conferida ao vivo — o ambiente onde isto foi implementado
bloqueia rede para as fontes primárias, igual ao que a seção 2 já registrava
para a versão anterior. São constantes editáveis, não normas verificadas.
Todo animal é tratado como Holandês para este cálculo, independente da
raça/grau de sangue cadastrado — decisão explícita do dono.

O painel de aferição (§8.5) existe para comparar este número fixo com o que
o próprio rebanho vem mostrando, e sinalizar se a tabela precisa de ajuste.

### 8.3 Confiança — não mais tamanho de amostra do rebanho

Antes: "confiança" media quantas lactações do REBANHO sustentavam o fator da
classe (baixa/ok, por tamanho de amostra). Agora: confiança é por VACA —

```
confiança = kg_medido / kg_projetado
```

isto é, que fração do total de 305 dias projetado é leite REALMENTE medido
nesta vaca (`Producao305.producao_medida_kg` — trapézios entre dois
controles reais, nem a ponta inicial nem a final), contra o total projetado.
Cai com o DEL (mais lactação pela frente ainda projetada); sobe com o
controle em dia.

Quatro níveis, cortes redondos calibrados contra os 7 exemplos do mockup
aprovado (23%→baixa, 7%→muito baixa, 66%→média, 81%→alta, 89%→alta,
42%→baixa, 58%→média):

| Fração medida | Nível |
|---|---|
| < 15% | muito baixa |
| 15% a 45% | baixa |
| 45% a 75% | média |
| ≥ 75% | alta |

### 8.4 Projeção do trecho final: curva, não platô

A lactação ABERTA cujo último controle é anterior ao fim da janela de 305
dias projetava esse trecho final SEGURANDO o ritmo do último controle
constante (platô) até o dia 305. Isso superestimava sistematicamente — toda
vaca declina depois do pico de produção — e o viés crescia quanto menor o
DEL do último controle (levantamento anterior: até +30% em DEL baixo).

Substituído por uma curva de Wood de referência (`rules/
curva_lactacao_referencia.py`): `y(t) = a·t^b·e^(−c·t)`, forma FIXA
(Holandês genérico, não ajustada por animal — poucos controles não sustentam
ajuste individual), ANCORADA no ritmo real do último controle da vaca. Dali
em diante, o ritmo projetado segue a forma declinante da curva, não um
platô. **[risco]** `B_REFERENCIA`/`C_REFERENCIA` — mesmo aviso do §8.2: vêm
de conhecimento treinado, editáveis, não conferidas ao vivo.

A lactação já ENCERRADA (secagem/próximo parto conhecido) continua usando o
platô de sempre no trecho final — é um trecho curto e real até uma data que
de fato aconteceu, não uma projeção para o futuro; o TIM já integra essa
janela corretamente.

### 8.5 Painel de aferição — a calibração antiga, demovida

`calcular_fatores` (a calibração por rebanho da versão anterior) continua
existindo, mas não alimenta mais o trio principal — vira um painel
colapsável de CONFERÊNCIA, informativo: fator observado no próprio rebanho
× fator fixo de tabela × divergência percentual, por classe. Nunca bloqueia
nem muda a conta do trio.

### 8.6 `sem_base` — só duas causas agora

Removida a causa mais comum de antes ("classe sem lactações suficientes do
rebanho"). Sobram:

- produção de 305 dias não calculável (menos de 2 controles utilizáveis);
- ordem de parto desconhecida (sem parto algum no histórico do animal, ou
  parto sem `ordem_parto` gravada) — não dá para escolher o fator fixo sem
  saber a classe.

### 8.7 Nota explicativa permanente no card

Pedido explícito do dono, em nota separada do painel de aferição (esse
compara método × realidade do rebanho; a nota explica o MÉTODO em si,
sempre visível, não colapsável): o card do trio (relatório, Ficha do
Animal, calculadora) traz um texto fixo dizendo que todo animal é
padronizado como Holandês independente da raça cadastrada, o que
"confiança" significa (fração medida/projetada, não margem estatística), e
os três fatores fixos com seus valores. Ver `NotaExplicativaEM` em
`frontend/components/TrioEquivalenteMaduro.tsx`.
