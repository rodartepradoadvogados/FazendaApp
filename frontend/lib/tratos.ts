// Tratos por dia da dieta e ciclo de 24h da sobra de cocho — espelho, no
// front, de backend/fazenda/rules/tratos.py (mesmas regras; o servidor é quem
// grava e recalcula — isto aqui serve para a tela montar o formulário, o
// "por trato" ao vivo e o resumo "A sobra se refere ao…" mesmo sem internet).
//
// Resumo das regras (decisões do dono, 21/10/2026):
// - 1 a 4 tratos por DIETA, cada um com um %, somando 100%; o % vale para a
//   dieta inteira. Dieta sem cadastro = 2 tratos 50/50 (a conta de antes).
// - Posição da leitura da sobra = nº do trato DEPOIS do qual a sobra é lida
//   (1..N; N = entre o último trato e o Trato 1 do dia seguinte). Com 1 trato
//   não se pergunta (vale 1). Sem posição = comportamento antigo: a data
//   informada é o próprio dia do fornecimento (dia civil).
// - A sobra lida no dia D fecha os N tratos anteriores à leitura:
//   p < N → Tratos p+1..N de D-1 + Tratos 1..p de D; p = N → Tratos 1..N de D-1.

export const MAX_TRATOS = 4;
export const TRATOS_PADRAO = [50, 50];

/** % iguais para `n` tratos, com o resto do arredondamento no último (33,33 + 33,33 + 33,34). */
export function tratosIguais(n: number): number[] {
  const base = Math.floor((100 / n) * 100) / 100;
  const pcts = Array.from({ length: n }, () => base);
  pcts[n - 1] = Math.round((100 - base * (n - 1)) * 100) / 100;
  return pcts;
}

/** Mensagem de erro do cadastro de tratos, ou null se está válido. */
export function validarTratos(pcts: number[]): string | null {
  if (pcts.length < 1 || pcts.length > MAX_TRATOS) return `Informe de 1 a ${MAX_TRATOS} tratos por dia.`;
  if (pcts.some((p) => !Number.isFinite(p) || p <= 0)) return "Cada trato precisa de um % maior que zero.";
  const soma = pcts.reduce((s, p) => s + p, 0);
  if (Math.abs(soma - 100) > 0.01) return `Os % dos tratos precisam somar 100% (hoje somam ${Math.round(soma * 100) / 100}%).`;
  return null;
}

/** Opções da pergunta "entre quais tratos a sobra é lida?" — vazia com 1 trato. */
export function opcoesPosicaoLeitura(n: number): { valor: number; rotulo: string }[] {
  if (n <= 1) return [];
  return Array.from({ length: n }, (_, i) => ({
    valor: i + 1,
    rotulo: `Trato ${i + 1} → Trato ${i + 1 === n ? 1 : i + 2}`,
  }));
}

/** Posição que vale para `n` tratos: 1 sempre com 1 trato; fora da faixa vira null. */
export function posicaoValida(n: number, posicao: number | null | undefined): number | null {
  if (n === 1) return 1;
  return posicao != null && posicao >= 1 && posicao <= n ? posicao : null;
}

/** Quantidade de cada trato a partir do total do dia. */
export function dividirPorTrato(total: number | null | undefined, pcts: number[]): (number | null)[] {
  return pcts.map((p) => (total == null ? null : Math.round(total * p) / 100));
}

// ── Ciclo da sobra ──────────────────────────────────────────────────────────
function somarDias(iso: string, dias: number): string {
  const [a, m, d] = iso.split("-").map(Number);
  const dt = new Date(Date.UTC(a, m - 1, d + dias));
  return dt.toISOString().slice(0, 10);
}
const ddmm = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;

export type ItemJanela = { data: string; trato: number };

/** Janela de tratos da sobra lida em `dataLeitura` (ISO). `posicao` null = dia civil. */
export function janelaSobra(dataLeitura: string, nTratos: number, posicao: number | null): { fechamento: string; itens: ItemJanela[] } {
  if (posicao == null) {
    return { fechamento: dataLeitura, itens: Array.from({ length: nTratos }, (_, i) => ({ data: dataLeitura, trato: i + 1 })) };
  }
  if (posicao >= nTratos) {
    const ontem = somarDias(dataLeitura, -1);
    return { fechamento: ontem, itens: Array.from({ length: nTratos }, (_, i) => ({ data: ontem, trato: i + 1 })) };
  }
  const ontem = somarDias(dataLeitura, -1);
  const itens: ItemJanela[] = [];
  for (let t = posicao + 1; t <= nTratos; t++) itens.push({ data: ontem, trato: t });
  for (let t = 1; t <= posicao; t++) itens.push({ data: dataLeitura, trato: t });
  return { fechamento: dataLeitura, itens };
}

function listaTratos(ts: number[]): string {
  const nums = ts.map(String);
  const texto = nums.length === 1 ? nums[0] : `${nums.slice(0, -1).join(", ")} e ${nums[nums.length - 1]}`;
  return `${nums.length === 1 ? "ao trato" : "aos tratos"} ${texto}`;
}

/** "A sobra se refere aos tratos 2 e 3 do dia 20/10 e ao trato 1 do dia 21/10?" */
export function descreverJanela(itens: ItemJanela[]): string {
  const porDia = new Map<string, number[]>();
  for (const it of itens) porDia.set(it.data, [...(porDia.get(it.data) ?? []), it.trato]);
  const partes = [...porDia.entries()].map(([d, ts]) => `${listaTratos(ts)} do dia ${ddmm(d)}`);
  return `A sobra se refere ${partes.join(" e ")}?`;
}
