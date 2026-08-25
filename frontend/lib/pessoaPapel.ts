// Regra de "quem pode ser Responsável" por um lançamento — extraída à parte
// de usePessoasAtivas.ts (que depende de React/fetchPessoas) para ficar pura,
// sem import de React nem alias "@/", e assim testável com o runner nativo do
// Node (mesmo padrão de lib/busca.ts) e auditável isoladamente.

// Papéis que qualificam uma pessoa como possível "Responsável" por um
// lançamento — Diarista/Prestador de serviços/Empreiteiro/Geral/Robô ficam
// de fora de propósito (não são quem se lança como responsável por um
// manejo/lançamento no dia a dia), mas uma pessoa com um desses tipos DE
// APOIO combinado com um papel funcional (ex.: "Diarista,Funcionário")
// continua aparecendo — a regra é sobre ter pelo menos um papel funcional,
// não sobre não ter nenhum papel de apoio. Comparados já normalizados (ver
// normalizarTipo) para tolerar acento/maiúscula vindos do cadastro.
const PAPEIS_FUNCIONAIS = ["funcionario", "veterinario", "zootecnista", "administrador", "contador"];

function normalizarTipo(tipo: string): string {
  return tipo
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "") // remove marcas de acento (combining diacritics) após NFD
    .trim()
    .toLowerCase();
}

// Função pura (sem estado/efeito) — é o único lugar que decide "esta pessoa
// pode ser responsável por um lançamento". Ver PAPEIS_FUNCIONAIS acima para
// o WHY. Usada por usePessoasAtivas (hook consumido por ~28 seletores de
// Responsável em todo o site e no app mobile — ver grep por
// "usePessoasAtivas" antes de mudar essa regra).
export function temPapelFuncional(tipos: string[] | undefined): boolean {
  if (!tipos || tipos.length === 0) return false;
  return tipos.some((t) => PAPEIS_FUNCIONAIS.includes(normalizarTipo(t)));
}
