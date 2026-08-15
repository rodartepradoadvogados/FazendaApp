// Carência de leite e de carne — configurada SEPARADA, exibida JUNTA.
//
// Espelho de backend/fazenda/rules/carencia.py. O backend é a fonte da verdade
// e já manda `texto` pronto em todo endpoint que expõe carência; este módulo
// existe para o formulário/preview formatar sem ida e volta ao servidor.
//
// Nulo NUNCA vira zero: "não informada" é honesto, "0 dias" é uma liberação
// que ninguém deu — e num rebanho leiteiro isso é o tanque inteiro condenado.

export const SEM_INFORMACAO = "Carência: não informada";

export type Carencia = {
  leite_dias: number | null;
  carne_dias: number | null;
  proibido_lactacao: boolean;
  texto: string;
  liberacao_leite?: string | null;
  liberacao_carne?: string | null;
};

export function formatarCarencia(
  leiteDias: number | null | undefined,
  carneDias: number | null | undefined,
  proibidoLactacao?: boolean | null,
): string {
  const partes: string[] = [];
  if (proibidoLactacao) partes.push("leite — NÃO USAR em lactação");
  else if (leiteDias != null) partes.push(`leite — ${leiteDias} dias`);
  if (carneDias != null) partes.push(`carne — ${carneDias} dias`);
  if (!partes.length) return SEM_INFORMACAO;
  return "Carência: " + partes.join(" / ");
}

/** `true` quando não há nenhum prazo configurado — a UI usa isto para mostrar
 *  o aviso em tom neutro (e não como se fosse liberação). */
export function carenciaNaoInformada(c: Partial<Carencia> | null | undefined): boolean {
  if (!c) return true;
  return c.leite_dias == null && c.carne_dias == null && !c.proibido_lactacao;
}
