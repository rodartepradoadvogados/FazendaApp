"use client";
// Sub-tela: Consultar dietas — lista as dietas por lote com datas de início e
// provável fim; ao tocar, abre a apresentação (produtos, por cabeça, total/dia,
// total/trato e o somatório de kg no vagão do lote).
import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchDietas, fetchApresentacaoDieta, type ApresentacaoDieta } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";

type DietaRow = { id: number; lote: number; responsavel?: string | null; data_abertura: string; data_prevista_encerramento?: string | null; data_efetivo_encerramento?: string | null; ativa: boolean };

function num(v?: number | null, casas = 2): string {
  if (v == null) return "—";
  return v.toLocaleString("pt-BR", { maximumFractionDigits: casas });
}
function fmtData(iso?: string | null): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

export default function ConsultarDietas({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando } = useCarregar<DietaRow[]>("menu_consultar_dietas", () => fetchDietas() as Promise<DietaRow[]>);
  const [aberta, setAberta] = useState<number | null>(null);
  const [apres, setApres] = useState<Record<number, ApresentacaoDieta | null>>({});

  function toggle(id: number) {
    setAberta((cur) => (cur === id ? null : id));
    if (aberta !== id && !(id in apres)) {
      setApres((a) => ({ ...a, [id]: null }));
      fetchApresentacaoDieta(id).then((d) => setApres((a) => ({ ...a, [id]: d }))).catch(() => setApres((a) => ({ ...a, [id]: null })));
    }
  }

  const dietas = (dados || []).slice().sort((a, b) => (a.data_abertura < b.data_abertura ? 1 : -1));

  return (
    <div>
      <MobVoltar titulo="Consultar dietas" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_consultar_dietas" mostrar={doCache} />

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : dietas.length === 0 ? (
        <Vazio>Nenhuma dieta cadastrada ainda.</Vazio>
      ) : (
        dietas.map((d) => {
          const aberto = aberta === d.id;
          const a = apres[d.id];
          return (
            <MobCard key={d.id} style={{ marginBottom: "0.6rem" }}>
              <button type="button" onClick={() => toggle(d.id)}
                style={{ width: "100%", background: "none", border: "none", padding: 0, textAlign: "left", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.6rem" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: "1.05rem", fontWeight: 800 }}>Lote {d.lote}</div>
                  <div style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>
                    Início {fmtData(d.data_abertura)} · Fim {d.ativa ? `previsto ${fmtData(d.data_prevista_encerramento)}` : fmtData(d.data_efetivo_encerramento)}
                  </div>
                  <div style={{ fontSize: "0.74rem", fontWeight: 700, marginTop: "0.15rem", color: d.ativa ? "var(--mob-verde)" : "var(--mob-muted)" }}>
                    {d.ativa ? "Ativa" : "Encerrada"}
                  </div>
                </div>
                <ChevronRight size={20} style={{ color: "var(--mob-muted)", transform: aberto ? "rotate(90deg)" : "none", transition: "transform .15s", flexShrink: 0 }} />
              </button>

              {aberto && (
                <div style={{ marginTop: "0.7rem", borderTop: "1px solid var(--mob-border)", paddingTop: "0.6rem" }}>
                  {a === null ? (
                    <p style={{ fontSize: "0.82rem", color: "var(--mob-muted)" }}>Carregando dieta…</p>
                  ) : a ? (
                    <>
                      <div style={{ fontSize: "0.8rem", fontWeight: 700, marginBottom: "0.5rem" }}>
                        {a.nome ? `${a.nome} — ` : ""}{a.qtd_animais} {a.qtd_animais === 1 ? "animal" : "animais"} · {a.num_tratos} tratos
                      </div>
                      {a.itens.map((it, i) => (
                        <div key={i} style={{ padding: "0.5rem 0", borderTop: i ? "1px solid var(--mob-border)" : "none" }}>
                          <div style={{ fontWeight: 800, fontSize: "0.95rem" }}>{it.alimento}</div>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.9rem", marginTop: "0.2rem", fontSize: "0.8rem" }}>
                            <span style={{ color: "var(--mob-verde)", fontWeight: 800 }}>{num(it.total_trato)} {it.unidade}/trato</span>
                            <span style={{ color: "var(--mob-ambar)", fontWeight: 700 }}>{num(it.total_dia)} {it.unidade}/dia</span>
                            <span style={{ color: "var(--mob-muted)" }}>{it.por_cabeca != null ? `${num(it.por_cabeca, 3)} ${it.unidade}/cab` : "—/cab"}</span>
                          </div>
                        </div>
                      ))}
                      <div style={{ marginTop: "0.6rem", padding: "0.55rem 0.7rem", background: "var(--mob-surface)", border: "1px solid var(--mob-border)", borderRadius: 10, fontSize: "0.85rem", fontWeight: 800 }}>
                        Vagão: <span style={{ color: "var(--mob-verde)" }}>{num(a.vagao_kg_trato)} kg/trato</span> · {num(a.vagao_kg_dia)} kg/dia
                      </div>
                    </>
                  ) : (
                    <p style={{ fontSize: "0.82rem", color: "var(--mob-muted)" }}>Não foi possível carregar a dieta.</p>
                  )}
                </div>
              )}
            </MobCard>
          );
        })
      )}
    </div>
  );
}
