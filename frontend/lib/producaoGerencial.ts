// Apoio comum das telas gerenciais de Lançamentos › Produção (Qualidade do leite, Indução de lactação, Venda mensal, BST).
// Só funções puras (testáveis com `node --test`): nada aqui fala com a API nem usa React.

/** Data de hoje no fuso LOCAL (AAAA-MM-DD). `toISOString()` usa UTC e, depois das 21h em Brasília, já devolve amanhã. */
export function hojeLocal(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** "2026-10-17" → "17/10/2026" (ou "17/10" quando curta). Vazio vira "—". */
export function dataBR(iso: string | null | undefined, curta = false): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  if (!a || !m || !d) return iso;
  return curta ? `${d}/${m}` : `${d}/${m}/${a}`;
}

const utc = (iso: string) => Date.UTC(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10)));

/** Dias inteiros de `deIso` até `ateIso` (negativo se `ate` for antes). */
export function diasEntre(deIso: string, ateIso: string): number {
  return Math.round((utc(ateIso) - utc(deIso)) / 86400000);
}

export function somarDias(iso: string, dias: number): string {
  return new Date(utc(iso) + dias * 86400000).toISOString().slice(0, 10);
}

/** Número no padrão brasileiro (vírgula decimal, ponto de milhar). */
export function nb(v: number, casas = 0): string {
  return v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

export function plural(n: number, um: string, varios: string): string {
  return n === 1 ? um : varios;
}

/**
 * Lê o número digitado pelo usuário. Em branco = `null` (nunca 0). Vírgula decimal aceita ("3,82").
 * Ponto de milhar NÃO é aceito ("12.480" é lido como 12,48 por `Number`), por isso a tela confirma o número formatado ao lado.
 * Qualquer texto que não seja número não-negativo devolve `NaN` (a tela sinaliza e bloqueia o Salvar).
 */
export function lerNumero(v: string | null | undefined): number | null {
  if (v == null || v.trim() === "") return null;
  const t = v.trim();
  if (!/^(\d+([.,]\d*)?|[.,]\d+)$/.test(t)) return NaN;
  const n = Number(t.replace(",", "."));
  return Number.isFinite(n) ? n : NaN;
}

/** Mensagem de um erro capturado (`catch (e)`), com texto padrão quando não há mensagem. */
export function mensagemDe(e: unknown, padrao: string): string {
  return e instanceof Error && e.message ? e.message : padrao;
}
