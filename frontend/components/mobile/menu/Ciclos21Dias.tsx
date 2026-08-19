"use client";
// Sub-tela: Ciclos de 21 dias (só leitura) — o BREDSUM\E do DairyComp no
// celular. Mesma fonte de dados e mesmas regras da versão de mesa
// (/ciclos-21-dias, ver backend/fazenda/rules/programa_reprodutivo.py):
// BR ELIG (elegíveis p/ inseminação) → BRED (servidas) → PG ELIG (elegíveis
// p/ prenhez) → PREG (prenhes). O que muda aqui é só a apresentação: em vez
// da tabela de 8 colunas do site, cada ciclo vira um cartão com duas barras
// empilhadas (Serviço e Prenhez) — a mesma leitura, cabendo na largura de um
// celular. Categoria (Todas/Vacas/Novilhas) é a única alavanca oferecida;
// data de referência fica fixa em hoje e a janela em 6 ciclos — o mesmo ponto
// de partida do site, sem exigir teclado numérico nem seletor de data no curral.
import { useState } from "react";
import { ChevronRight, Info } from "lucide-react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchCiclos21Dias, formatDate, type CiclosResposta, type CicloReprodutivo } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";

type Categoria = "todas" | "vaca" | "novilha";
const ROTULO_CATEGORIA: Record<Categoria, string> = { todas: "Todas", vaca: "Vacas", novilha: "Novilhas" };

// Data local, NÃO `toISOString()` (UTC) — no Brasil (UTC−3) a tela abriria com
// a data de amanhã depois das 21h. Mesma função da versão de mesa.
function hojeISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function pct(v: number | null): string {
  return v == null ? "—" : `${v.toFixed(1)}%`;
}

// Uma barra "numerador de denominador" (ex.: BRED de BR ELIG) — a mesma
// pergunta que a versão de mesa faz em duas barras por par (Serviço e
// Prenhez), só que compacta o bastante para caber ao lado da outra numa
// coluna só. `cor` marca o preenchimento; a trilha usa --mob-border.
function Barra({ rotulo, num, den, cor }: { rotulo: string; num: number; den: number; cor: string }) {
  const base = Math.max(den, 1);
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.68rem", color: "var(--mob-muted)", fontWeight: 700, marginBottom: "0.2rem" }}>
        <span>{rotulo}</span>
        <span>{num} / {den}</span>
      </div>
      <div style={{ background: "var(--mob-border)", borderRadius: 4, height: 10, overflow: "hidden" }}>
        <div style={{ width: `${Math.min(100, (num / base) * 100)}%`, background: cor, height: "100%" }} />
      </div>
    </div>
  );
}

// Cartão de um ciclo: período, selo "em apuração" quando a janela de
// diagnóstico ainda está aberta (PREG e taxa de prenhez estão subestimadas
// por construção nesse caso — não é comparável com a meta), e as duas barras.
function CartaoCiclo({ c, onAbrir }: { c: CicloReprodutivo; onAbrir: () => void }) {
  return (
    <MobCard onClick={onAbrir} style={{ marginBottom: "0.6rem", cursor: "pointer" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.55rem" }}>
        <div>
          <span style={{ fontWeight: 800, fontSize: "0.98rem" }}>Ciclo {c.ciclo}</span>
          <span style={{ fontSize: "0.76rem", color: "var(--mob-muted)", marginLeft: "0.5rem" }}>
            {formatDate(c.inicio)} – {formatDate(c.fim)}
          </span>
        </div>
        <ChevronRight size={16} style={{ color: "var(--mob-muted)", flexShrink: 0 }} />
      </div>
      {!c.janela_dg_completa && (
        <span style={{ display: "inline-block", fontSize: "0.66rem", fontWeight: 700, color: "var(--mob-muted)", border: "1px solid var(--mob-border)", borderRadius: 999, padding: "0.05rem 0.5rem", marginBottom: "0.5rem" }}>
          em apuração
        </span>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <Barra rotulo={`Serviço · ${pct(c.taxa_servico)}`} num={c.bred} den={c.br_elig} cor="var(--mob-dourado-2)" />
        <Barra rotulo={`Prenhez · ${c.janela_dg_completa ? pct(c.taxa_prenhez) : `${pct(c.taxa_prenhez)} (parcial)`}`} num={c.preg} den={c.pg_elig} cor="var(--mob-verde)" />
      </div>
    </MobCard>
  );
}

// Chips com os brincos de um balde (BR ELIG/BRED/PG ELIG/PREG) — mesma lista
// que o drill-down da versão de mesa, sem tabela: só os números, para tocar e
// levar para a Ficha não é o objetivo aqui (a lista já basta para conferir
// "quem entrou em cada cesta").
function DetalheCiclo({ c, onVoltar }: { c: CicloReprodutivo; onVoltar: () => void }) {
  const grupos: { titulo: string; nums: string[] }[] = [
    { titulo: "Elegíveis p/ inseminação (BR ELIG)", nums: c.animais?.br_elig ?? [] },
    { titulo: "Inseminadas no ciclo (BRED)", nums: c.animais?.bred ?? [] },
    { titulo: "Elegíveis p/ prenhez (PG ELIG)", nums: c.animais?.pg_elig ?? [] },
    { titulo: "Confirmadas prenhes (PREG)", nums: c.animais?.preg ?? [] },
  ];
  return (
    <div>
      <MobVoltar titulo={`Ciclo ${c.ciclo}`} onVoltar={onVoltar} />
      <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginBottom: "0.8rem" }}>
        {formatDate(c.inicio)} a {formatDate(c.fim)}
      </p>
      {grupos.map((g) => (
        <MobCard key={g.titulo} style={{ marginBottom: "0.6rem" }}>
          <div style={{ fontWeight: 700, fontSize: "0.82rem", marginBottom: "0.45rem" }}>
            {g.titulo} <span style={{ color: "var(--mob-dourado-2)", fontWeight: 500 }}>({g.nums.length})</span>
          </div>
          {g.nums.length ? (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem" }}>
              {g.nums.map((n) => (
                <span key={n} style={{ fontSize: "0.74rem", background: "var(--mob-surface-2)", border: "1px solid var(--mob-border)", borderRadius: 999, padding: "0.12rem 0.55rem", fontWeight: 600 }}>
                  {n}
                </span>
              ))}
            </div>
          ) : (
            <p style={{ fontSize: "0.75rem", color: "var(--mob-muted)" }}>Nenhum animal.</p>
          )}
        </MobCard>
      ))}
    </div>
  );
}

export default function Ciclos21Dias({ onVoltar }: { onVoltar: () => void }) {
  const [categoria, setCategoria] = useState<Categoria>("todas");
  const [detalhe, setDetalhe] = useState<CicloReprodutivo | null>(null);
  const ancora = hojeISO();

  // Chave de cache inclui a categoria — cada filtro guarda sua própria cópia
  // offline, igual ao padrão já usado em Recria > Saúde (curva por doença).
  // `erro` de useCarregar não é checado aqui de propósito — o mesmo padrão
  // das demais sub-telas do Menu (ver comum.tsx): se sobrou uma cópia salva
  // (mesmo que velha), ela aparece com o aviso "Cópia de…"; só falta mesmo
  // conteúdo quando nunca houve cache nenhum.
  const { dados, doCache, carregando } = useCarregar<CiclosResposta>(
    `menu_ciclos21dias_${categoria}`,
    () => fetchCiclos21Dias(ancora, "fim", 6, categoria),
  );

  if (detalhe) return <DetalheCiclo c={detalhe} onVoltar={() => setDetalhe(null)} />;

  return (
    <div>
      <MobVoltar titulo="Ciclos de 21 dias" onVoltar={onVoltar} />
      <AvisoCopia chave={`menu_ciclos21dias_${categoria}`} mostrar={doCache} />

      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.9rem" }}>
        {(Object.keys(ROTULO_CATEGORIA) as Categoria[]).map((k) => (
          <button key={k} type="button" className={`mob-pill${categoria === k ? " ativa" : ""}`} onClick={() => setCategoria(k)}>
            {ROTULO_CATEGORIA[k]}
          </button>
        ))}
      </div>

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : !dados.ciclos?.length ? (
        <Vazio>Sem ciclos para mostrar nesse filtro.</Vazio>
      ) : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.5rem", marginBottom: "0.9rem" }}>
            {[
              { rotulo: "Serviço", v: dados.resumo?.taxa_servico ?? null, meta: dados.metas?.taxa_servico },
              { rotulo: "Prenhez", v: dados.resumo?.taxa_prenhez ?? null, meta: dados.metas?.taxa_prenhez },
              { rotulo: "Concepção", v: dados.resumo?.taxa_concepcao ?? null, meta: dados.metas?.taxa_concepcao },
            ].map((q) => (
              <div key={q.rotulo} className="mob-card" style={{ padding: "0.7rem 0.4rem", textAlign: "center" }}>
                <div style={{ fontSize: "1.15rem", fontWeight: 800, color: q.v != null && q.meta != null && q.v >= q.meta ? "var(--mob-verde)" : "var(--mob-ambar)" }}>
                  {q.v == null ? "—" : `${q.v}%`}
                </div>
                <div style={{ fontSize: "0.66rem", color: "var(--mob-muted)", fontWeight: 600, marginTop: "0.2rem" }}>{q.rotulo}</div>
                {q.meta != null && <div style={{ fontSize: "0.6rem", color: "var(--mob-muted)" }}>meta {q.meta}%</div>}
              </div>
            ))}
          </div>

          <p style={{ fontSize: "0.72rem", color: "var(--mob-muted)", marginBottom: "0.8rem" }}>
            {dados.resumo?.animais_avaliados ?? 0} animal(is) · {dados.periodo ? `${formatDate(dados.periodo.inicio)} a ${formatDate(dados.periodo.fim)}` : ""}
          </p>

          {dados.ciclos.map((c) => (
            <CartaoCiclo key={c.ciclo} c={c} onAbrir={() => setDetalhe(c)} />
          ))}

          {dados.ressalva_historica && (
            <div style={{ display: "flex", gap: "0.4rem", alignItems: "flex-start", marginTop: "0.6rem", fontSize: "0.72rem", color: "var(--mob-muted)" }}>
              <Info size={13} style={{ marginTop: 2, flexShrink: 0 }} />
              <span>{dados.ressalva_historica}</span>
            </div>
          )}
        </>
      )}
    </div>
  );
}
