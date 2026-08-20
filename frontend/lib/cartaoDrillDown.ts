/**
 * Cartão com drill-down — declarar o par (valor, lista), nunca só o valor.
 *
 * O defeito que este módulo existe para impedir já aconteceu duas vezes: um
 * card dizia "70 fêmeas prenhas" e a lista que o clique abria mostrava outra
 * coisa. As duas vezes a causa foi a mesma — o número do card e o filtro que
 * gera a lista eram escritos em DOIS lugares diferentes do componente,
 * livres para divergir quando um dos dois mudava e o outro ficava para trás.
 *
 * A cura caso a caso já é conhecida e funciona: o backend passou a mandar,
 * ao lado de cada contador, a lista de números que o compõe (o padrão
 * `aptas`/`aptas_nums`, `prenhes_programa_nums`, `controle_nums`,
 * `congelado_nums` — ver `lib/api.ts`). O que faltava era uma forma de a
 * TELA consumir esse par sem poder separar os dois de novo por acidente.
 *
 * `cartao()` resolve isso lendo valor e lista de UM ÚNICO objeto de origem
 * (`origem`), por DUAS chaves desse mesmo objeto (`conta`/`nums`). Como
 * `conta` e `nums` são tipados como `keyof Origem`, o TypeScript recusa a
 * chamada se qualquer um dos dois apontar para um campo que não existe
 * nesse objeto — ou seja, não dá para declarar a lista de um card lendo um
 * campo de OUTRO objeto do payload sem que isso seja, no mínimo, visível e
 * deliberado (um segundo `origem` explícito, não um deslize de digitação).
 * Não impede escolher o PAR errado de propósito (isso é decisão de produto,
 * não de tipo) — impede inventar um campo ou buscar em outro lugar sem
 * querer, que foi o defeito real das duas recaídas.
 *
 * `cartaoDeMapas()` cobre a variação onde valor e lista não são dois campos
 * do mesmo objeto, mas dois DICIONÁRIOS irmãos indexados pela mesma chave
 * (ex.: `partos_previstos.em_30_dias` e `partos_previstos_nums.em_30_dias`).
 * A chave é lida uma única vez e usada nos dois lugares — não há como os
 * dois lookups usarem chaves diferentes por engano.
 *
 * O que este módulo NÃO faz: não força `valor === lista.length`. Vários
 * cartões reais mostram uma TAXA (ex. `taxa_prenhez_pct`) cujo denominador
 * não é o tamanho da lista que o drill-down abre (`prenhes_programa_nums`,
 * o numerador) — isso é correto por design, documentado em
 * `indicadores.py`. A garantia aqui é de PROVENIÊNCIA (os dois vêm do mesmo
 * lugar, nomeados explicitamente), não de igualdade aritmética.
 */
import type React from "react";

/** Cartão já resolvido: pronto para renderizar e para abrir o drill-down.
 *
 * `titulo` é sempre texto puro — é o que vira `key` de lista e o título do
 * modal de drill-down (`abrirNums(titulo, nums)`). `rotulo` é o que aparece
 * no card em si, e pode ser JSX mais rico (ex.: título + legenda menor); por
 * padrão é o próprio `titulo`. */
export type Cartao = {
  titulo: string;
  rotulo: React.ReactNode;
  valor: React.ReactNode;
  /** Números por trás do valor — o que `abrirNums`/`abrir` recebe direto. */
  nums: string[] | null | undefined;
  cor?: string;
};

/** Restringe as chaves de `Origem` às que guardam uma lista de números —
 * o "documento de identidade" que `nums` precisa satisfazer. */
type ChaveDeLista<Origem> = {
  [K in keyof Origem]: Origem[K] extends string[] | null | undefined ? K : never;
}[keyof Origem];

export type DefCartao<Origem, ChaveValor extends keyof Origem> = {
  titulo: string;
  /** Conteúdo do card, se diferente do `titulo` puro (ex.: título + legenda). */
  rotulo?: React.ReactNode;
  /** O objeto de onde SAEM os dois campos — sempre o mesmo para valor e lista. */
  origem: Origem | null | undefined;
  /** Chave de `origem` com o valor bruto a exibir. */
  conta: ChaveValor;
  /** Chave de `origem` com a lista de números por trás desse valor. */
  nums: ChaveDeLista<Origem>;
  cor?: string;
  /** Formata o valor bruto para exibição; sem isso, número vira texto e
   * `null`/`undefined` viram "—" (mesmo padrão do `num()` das telas atuais). */
  formatar?: (bruto: Origem[ChaveValor]) => React.ReactNode;
};

export function cartao<Origem, ChaveValor extends keyof Origem>(def: DefCartao<Origem, ChaveValor>): Cartao {
  const bruto = def.origem ? def.origem[def.conta] : undefined;
  const valor = def.formatar
    ? def.formatar(bruto as Origem[ChaveValor])
    : bruto === null || bruto === undefined
      ? "—"
      : String(bruto);
  const nums = def.origem ? (def.origem[def.nums] as unknown as string[] | null | undefined) : undefined;
  return { titulo: def.titulo, rotulo: def.rotulo ?? def.titulo, valor, nums, cor: def.cor };
}

/** Par de dicionários irmãos (valor e lista) indexados pela MESMA chave —
 * ver docstring do módulo. `Mapa` é o dicionário de valores; `numsMapa`
 * espelha suas chaves com listas de números. */
export function cartaoDeMapas<Mapa extends Record<string, number | null | undefined>>(
  titulo: string,
  valores: Mapa | null | undefined,
  numsMapa: Partial<Record<keyof Mapa, string[] | null | undefined>> | null | undefined,
  chave: keyof Mapa,
  cor?: string,
): Cartao {
  const bruto = valores ? valores[chave] : undefined;
  const valor = bruto === null || bruto === undefined ? "—" : String(bruto);
  const nums = numsMapa ? numsMapa[chave] : undefined;
  return { titulo, rotulo: titulo, valor, nums, cor };
}
