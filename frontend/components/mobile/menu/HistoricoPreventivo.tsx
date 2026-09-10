"use client";
// Lista compartilhada de histórico PREVENTIVO (vacina/tratamento aplicados +
// resultado de exames, agrupados por data+produto) — usada tanto pela aba
// "Preventivo" da tela Histórico (Menu > Sanidade > Histórico) quanto pela
// aba "Já aplicado" do Calendário Sanitário (Menu > Sanidade > Calendário).
// Só leitura — editar/excluir uma aplicação continua em Histórico > Curativo
// (admin) por ora; aqui o objetivo é só responder "o que já foi lançado".
import { useMemo } from "react";
import { fetchSanidade, fetchResultadosExame, formatDate, type ExameResultado } from "@/lib/api";
import { MobCard } from "@/components/mobile/ui";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";

type AplicPrev = {
  id: number; numero: string; produto: string; categoria: string | null;
  dose: number | null; unidade: string | null; responsavel: string | null;
  natureza: string | null; data: string | null;
};

const ROTULO_RESULTADO: Record<string, string> = { positivo: "Positivo", negativo: "Negativo", indefinido: "Indefinido" };
const COR_RESULTADO: Record<string, string> = { positivo: "var(--mob-vermelho)", negativo: "var(--mob-verde)", indefinido: "var(--mob-ambar)" };

type LinhaHistorico =
  | { tipo: "vacina"; data: string; nome: string; animais: number; produto: string; responsavel: string | null }
  | { tipo: "exame"; data: string; nome: string; animais: number; resultados: Record<string, number> };

export function PreventivoHistoricoLista() {
  const aplic = useCarregar<{ aplicacoes: AplicPrev[] }>("historico_preventivo_aplicacoes", () => fetchSanidade());
  const exames = useCarregar<ExameResultado[]>("historico_preventivo_exames", () => fetchResultadosExame());

  const linhas = useMemo(() => {
    // Agrupa vacina por (data, produto) — uma aplicação em lote vira 1 card
    // com a contagem de animais, não N linhas repetidas.
    const porGrupoVacina = new Map<string, { data: string; nome: string; animais: Set<string>; produto: string; responsavel: string | null }>();
    for (const a of (aplic.dados?.aplicacoes || [])) {
      if (a.natureza !== "preventivo" || !a.data) continue;
      const chave = `${a.data}__${a.produto}`;
      const g = porGrupoVacina.get(chave) || { data: a.data, nome: a.produto, animais: new Set<string>(), produto: a.produto, responsavel: a.responsavel };
      g.animais.add(a.numero);
      porGrupoVacina.set(chave, g);
    }
    const vacinas: LinhaHistorico[] = Array.from(porGrupoVacina.values()).map((g) => ({
      tipo: "vacina", data: g.data, nome: g.nome, animais: g.animais.size, produto: g.produto, responsavel: g.responsavel,
    }));

    // Exame agrupado por (data, evento) — mostra a contagem por resultado.
    const porGrupoExame = new Map<string, { data: string; nome: string; animais: Set<string>; resultados: Record<string, number> }>();
    for (const e of (exames.dados || [])) {
      const chave = `${e.data_exame}__${e.evento_sanitario_nome || ""}`;
      const g = porGrupoExame.get(chave) || { data: e.data_exame, nome: e.evento_sanitario_nome || "Exame", animais: new Set<string>(), resultados: {} };
      g.animais.add(e.numero_matriz);
      if (e.resultado) g.resultados[e.resultado] = (g.resultados[e.resultado] || 0) + 1;
      porGrupoExame.set(chave, g);
    }
    const examesLinhas: LinhaHistorico[] = Array.from(porGrupoExame.values()).map((g) => ({
      tipo: "exame", data: g.data, nome: g.nome, animais: g.animais.size, resultados: g.resultados,
    }));

    return [...vacinas, ...examesLinhas].sort((a, b) => b.data.localeCompare(a.data));
  }, [aplic.dados, exames.dados]);

  const carregando = aplic.carregando || exames.carregando;
  const doCache = aplic.doCache || exames.doCache;

  return (
    <>
      <AvisoCopia chave="historico_preventivo_aplicacoes" mostrar={doCache} />
      {carregando && !linhas.length ? (
        <Carregando />
      ) : linhas.length === 0 ? (
        <Vazio>Nenhuma vacina ou exame preventivo lançado ainda.</Vazio>
      ) : (
        linhas.map((l, i) => (
          <MobCard key={`${l.tipo}-${l.data}-${l.nome}-${i}`} style={{ marginBottom: "0.6rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.5rem" }}>
              <span style={{ fontWeight: 700, fontSize: "0.92rem" }}>{l.nome}</span>
              <span style={{ fontSize: "0.76rem", color: "var(--mob-muted)" }}>{formatDate(l.data)}</span>
            </div>
            <div style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginTop: "0.15rem" }}>
              {l.animais} animal(is){l.tipo === "exame" ? " · exame" : ` · ${l.produto}${l.responsavel ? " · " + l.responsavel : ""}`}
            </div>
            {l.tipo === "exame" && (
              <div style={{ display: "flex", gap: "0.4rem", marginTop: "0.45rem", flexWrap: "wrap" }}>
                {Object.entries(l.resultados).map(([r, n]) => (
                  <span key={r} style={{
                    fontSize: "0.68rem", fontWeight: 700, padding: "0.2rem 0.5rem", borderRadius: 6,
                    color: COR_RESULTADO[r] || "var(--mob-muted)",
                    background: "color-mix(in srgb, currentColor 12%, transparent)",
                  }}>
                    {n} {ROTULO_RESULTADO[r] || r}
                  </span>
                ))}
              </div>
            )}
          </MobCard>
        ))
      )}
    </>
  );
}
