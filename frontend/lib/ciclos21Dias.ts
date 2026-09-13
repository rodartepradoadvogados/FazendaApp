// Réplica em TS de `ciclos_21_dias` em backend/fazenda/rules/programa_reprodutivo.py
// — mesma aritmética de janelas FECHADAS de 21 dias ancoradas numa data livre
// escolhida pelo usuário (início OU fim da série). O backend usa isso para o
// motor de risco de prenhez (R1-R9, ver Ciclos de 21 dias); aqui é só para
// recortar localmente registros já carregados por período de ciclo (ver
// HistoricoServicos.tsx), sem chamar o backend de novo.
export type CicloJanela = { indice: number; inicio: Date; fim: Date };

export function ciclos21Dias(
  ancoraISO: string, modo: "inicio" | "fim", nCiclos: number, dias = 21,
): CicloJanela[] {
  if (!ancoraISO || nCiclos < 1 || dias < 1) return [];
  const ancora = new Date(ancoraISO + "T00:00:00");
  const primeiroInicio = new Date(ancora);
  if (modo === "fim") {
    // A âncora é o FIM do último ciclo: recua (n_ciclos * dias) - 1 dias.
    primeiroInicio.setDate(primeiroInicio.getDate() - (nCiclos * dias - 1));
  }
  const arr: CicloJanela[] = [];
  for (let i = 0; i < nCiclos; i++) {
    const inicio = new Date(primeiroInicio); inicio.setDate(inicio.getDate() + i * dias);
    const fim = new Date(primeiroInicio); fim.setDate(fim.getDate() + (i + 1) * dias - 1);
    arr.push({ indice: i + 1, inicio, fim });
  }
  return arr;
}

// Data local ISO (não `toISOString()`, que é UTC e erra o dia perto da meia-noite no Brasil).
export const isoLocal = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
