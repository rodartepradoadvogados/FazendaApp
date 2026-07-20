import { AnimalPicker } from "@/components/AnimalPicker";

/* ───────────────────────── Utilitários e constantes compartilhados por
   vários formulários de Lançamentos — extraídos de app/lancamentos/page.tsx
   quando usados por mais de um Form* ao mesmo tempo (para não duplicar a
   mesma lógica em arquivos diferentes). ───────────────────────── */

export const IDADE_MIN_SERVICO = 13; // meses — abaixo disso a fêmea não é apta a serviço

export const UNIDADES = ["ml", "kg", "L", "unidade", "dose", "saca 30kg", "saca 60kg"];

export function addDias(iso: string, n: number): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00"); d.setDate(d.getDate() + n);
  return d.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" });
}

// Seleção de animal via tabela clara (Nº · Grupo · Categoria · Sit. Rep. · DEL).
export const SelectAnimal = AnimalPicker;

// Categorias prontas de animais para o lançamento em massa do protocolo sanitário
// — reaproveita o mesmo motor de critérios cumulativos de Configurações > Lotes
// (POST /lotes/preview), sem precisar criar um lote de verdade.
export const CATEGORIAS_ANIMAIS = [
  { id: "novilhas_inseminadas", label: "Novilhas inseminadas", criterios: { novilhas_inseminadas: true } },
  { id: "novilhas_gestantes", label: "Novilhas gestantes", criterios: { novilhas_gestantes: true } },
  { id: "lactacao", label: "Vacas em lactação", criterios: { status_lactacao: "lactacao" } },
  { id: "secas", label: "Vacas secas", criterios: { status_lactacao: "seca" } },
  { id: "pre_parto_15", label: "Pré-parto (próximos 15 dias)", criterios: { dias_para_parto_min: 0, dias_para_parto_max: 15 } },
  { id: "em_tratamento", label: "Em tratamento", criterios: { em_tratamento: true } },
] as const;

export const FREQUENCIA_UNIDADES = [
  { v: "dias", l: "dia(s)" }, { v: "meses", l: "mês(es)" }, { v: "anos", l: "ano(s)" },
];

// ─────────────────────── Preventivo — aplicação (vacina/exame) ───────────────────────
export type ExameDef = { id: number; nome: string; tipo_resultado: "diagnostico" | "numerico"; faixa_min: number | null; faixa_max: number | null; acao_abaixo: string | null; acao_dentro: string | null; acao_acima: string | null };
