"use client";
// Sub-tela: Menu > Rebanho — painel de indicadores do rebanho (só leitura).
// O 1º card ("Rebanho") abre a aba Rebanho de verdade (mesma do rodapé); os
// demais abrem uma lista de animais por trás do número, só com os campos
// pertinentes ao indicador (nunca Raça, nunca Nome ao lado de Número).
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { MobVoltar } from "@/components/mobile/ui";
import { CowIcon } from "@/components/CowIcon";
import { fetchIndicadores, fetchAnimais, fetchRelatoriosManejo, formatDate } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";
import { FichaDetalhe } from "@/components/mobile/rebanho/Ficha";

type Indicadores = {
  rebanho?: { total?: number | null };
  reproducao?: {
    prenhes?: number | null; inseminadas?: number | null; vazias?: number | null; aptas?: number | null;
    aptas_nums?: string[]; iep_dias?: number | null;
    partos_previstos?: { em_30_dias?: number | null };
    partos_previstos_nums?: { em_30_dias?: string[] };
    partos_previstos_datas?: Record<string, string>;
    gestantes_detalhe?: { numero: string; dias_gestacao: number; parto_previsto: string }[];
    iep_por_matriz?: { numero: string; iep_dias: number; data_ultimo_parto: string }[];
  };
  reproducao_categorias?: { todas?: { pev?: number | null } };
  producao?: { del_medio?: number | null; producao_media_kg?: number | null };
};

type Animal = {
  numero: string; grupo_primario?: string | null; sit_rep?: string | null;
  del_dias?: number | null; ult_cl_kg?: number | null; categoria_abrev?: string | null;
};

type ItemSecagem = { numero: string; grupo?: string | null; dias_para_secagem?: number | null; previsao_secagem?: string | null };

const SIT_LABEL: Record<string, string> = { "Vaz. pev": "PEV", "Vaz. apt.": "Apta", "Vaz. atr.": "Atrasada" };
function situacaoLabel(sit?: string | null): string {
  const s = (sit || "").trim();
  return SIT_LABEL[s] || (s.startsWith("Vaz.") ? "Vazia" : s || "—");
}

function ordenarNumero(a: { numero: string }, b: { numero: string }): number {
  const na = Number(a.numero), nb = Number(b.numero);
  if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb;
  return a.numero.localeCompare(b.numero);
}

function val(v?: number | null, sufixo = ""): string {
  if (v == null) return "—";
  return `${v.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}${sufixo}`;
}

type Drill = "gestantes" | "inseminadas" | "pev" | "vazias" | "aptas" | "atrasadas" | "partoPrevisto" | "iep" | "secagens" | "producao";

const DRILL_TITULO: Record<Drill, string> = {
  gestantes: "Gestantes", inseminadas: "Inseminadas", pev: "PEV", vazias: "Vazias", aptas: "Aptas",
  atrasadas: "Atrasadas", partoPrevisto: "Parto previsto", iep: "IEP médio", secagens: "Secagens previstas",
  producao: "DEL médio e produção média",
};

/** Pílula de categoria (Vaca/Novilha/...) acima dos campos de cada linha. */
function Pilula({ children }: { children: React.ReactNode }) {
  return (
    <span style={{ display: "inline-block", fontSize: "0.68rem", fontWeight: 700, color: "var(--mob-dourado-2)", background: "color-mix(in srgb, var(--mob-dourado-2) 14%, transparent)", borderRadius: 999, padding: "0.15rem 0.55rem", marginBottom: "0.5rem" }}>
      {children}
    </span>
  );
}

function Campo({ label, valor }: { label: string; valor: React.ReactNode }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem", padding: "0.15rem 0" }}>
      <span style={{ color: "var(--mob-muted)", fontWeight: 600 }}>{label}</span>
      <span style={{ fontWeight: 700 }}>{valor}</span>
    </div>
  );
}

function LinhaAnimal({ campos, onVerAnimal }: { campos: React.ReactNode; onVerAnimal: () => void }) {
  return (
    <div className="mob-card" style={{ padding: "0.9rem 1rem", marginBottom: "0.6rem" }}>
      {campos}
      <button type="button" className="mob-btn-2" onClick={onVerAnimal} style={{ marginTop: "0.7rem" }}>
        Ver Animal
      </button>
    </div>
  );
}

export default function RebanhoDashboard({ onVoltar }: { onVoltar: () => void }) {
  const router = useRouter();
  const { dados, doCache, carregando } = useCarregar<Indicadores>("menu_rebanho_dash", fetchIndicadores);
  const animaisReq = useCarregar<Animal[]>("menu_rebanho_dash_animais", () => fetchAnimais() as Promise<Animal[]>);
  const secagemReq = useCarregar<Record<string, ItemSecagem[]>>("menu_rebanho_dash_secagem", fetchRelatoriosManejo);
  const [drill, setDrill] = useState<Drill | null>(null);
  const [numeroAberto, setNumeroAberto] = useState<string | null>(null);

  const animais = animaisReq.dados || [];
  const porNumero = new Map(animais.map((a) => [a.numero, a]));
  const categoriaDe = (numero: string) => porNumero.get(numero)?.categoria_abrev || porNumero.get(numero)?.grupo_primario || "—";

  if (numeroAberto) {
    return <FichaDetalhe numero={numeroAberto} onVoltar={() => setNumeroAberto(null)} />;
  }

  // ── Drill-down de um card ───────────────────────────────────────────────
  if (drill) {
    const rep = dados?.reproducao || {};

    let linhas: React.ReactNode[] = [];
    let total = 0;

    if (drill === "gestantes") {
      const lista = [...(rep.gestantes_detalhe || [])].sort((a, b) => b.dias_gestacao - a.dias_gestacao);
      total = lista.length;
      linhas = lista.map((g) => (
        <LinhaAnimal key={g.numero} onVerAnimal={() => setNumeroAberto(g.numero)} campos={<>
          <Pilula>{categoriaDe(g.numero)}</Pilula>
          <Campo label="Nº" valor={g.numero} />
          <Campo label="Dias de gestação" valor={g.dias_gestacao} />
          <Campo label="Parto previsto" valor={formatDate(g.parto_previsto)} />
        </>} />
      ));
    } else if (drill === "inseminadas") {
      const lista = animais.filter((a) => (a.sit_rep || "").trim() === "Ins.").sort(ordenarNumero);
      total = lista.length;
      linhas = lista.map((a) => (
        <LinhaAnimal key={a.numero} onVerAnimal={() => setNumeroAberto(a.numero)} campos={<>
          <Pilula>{categoriaDe(a.numero)}</Pilula>
          <Campo label="Nº" valor={a.numero} />
          <Campo label="Lote atual" valor={a.grupo_primario || "—"} />
        </>} />
      ));
    } else if (drill === "pev") {
      const lista = animais.filter((a) => (a.sit_rep || "").trim() === "Vaz. pev").sort(ordenarNumero);
      total = lista.length;
      linhas = lista.map((a) => (
        <LinhaAnimal key={a.numero} onVerAnimal={() => setNumeroAberto(a.numero)} campos={<>
          <Pilula>{categoriaDe(a.numero)}</Pilula>
          <Campo label="Nº" valor={a.numero} />
          <Campo label="DEL (dias pós-parto)" valor={a.del_dias ?? "—"} />
        </>} />
      ));
    } else if (drill === "vazias") {
      const lista = animais.filter((a) => (a.sit_rep || "").trim().startsWith("Vaz.")).sort(ordenarNumero);
      total = lista.length;
      linhas = lista.map((a) => (
        <LinhaAnimal key={a.numero} onVerAnimal={() => setNumeroAberto(a.numero)} campos={<>
          <Pilula>{categoriaDe(a.numero)}</Pilula>
          <Campo label="Nº" valor={a.numero} />
          <Campo label="Situação" valor={situacaoLabel(a.sit_rep)} />
          <Campo label="Lote atual" valor={a.grupo_primario || "—"} />
        </>} />
      ));
    } else if (drill === "aptas") {
      const nums = rep.aptas_nums || [];
      const lista = nums.map((n) => porNumero.get(n)).filter(Boolean).sort(ordenarNumero as any) as Animal[];
      total = lista.length;
      linhas = lista.map((a) => (
        <LinhaAnimal key={a.numero} onVerAnimal={() => setNumeroAberto(a.numero)} campos={<>
          <Pilula>{categoriaDe(a.numero)}</Pilula>
          <Campo label="Nº" valor={a.numero} />
          <Campo label="DEL (dias pós-parto)" valor={a.del_dias ?? "—"} />
          <Campo label="Lote atual" valor={a.grupo_primario || "—"} />
        </>} />
      ));
    } else if (drill === "atrasadas") {
      const lista = animais.filter((a) => (a.sit_rep || "").trim() === "Vaz. atr.").sort(ordenarNumero);
      total = lista.length;
      linhas = lista.map((a) => (
        <LinhaAnimal key={a.numero} onVerAnimal={() => setNumeroAberto(a.numero)} campos={<>
          <Pilula>{categoriaDe(a.numero)}</Pilula>
          <Campo label="Nº" valor={a.numero} />
          <Campo label="Lote atual" valor={a.grupo_primario || "—"} />
        </>} />
      ));
    } else if (drill === "partoPrevisto") {
      const nums = rep.partos_previstos_nums?.em_30_dias || [];
      const datas = rep.partos_previstos_datas || {};
      total = nums.length;
      linhas = [...nums].sort().map((numero) => (
        <LinhaAnimal key={numero} onVerAnimal={() => setNumeroAberto(numero)} campos={<>
          <Pilula>{categoriaDe(numero)}</Pilula>
          <Campo label="Nº" valor={numero} />
          <Campo label="Parto previsto" valor={datas[numero] ? formatDate(datas[numero]) : "—"} />
        </>} />
      ));
    } else if (drill === "iep") {
      const lista = [...(rep.iep_por_matriz || [])].sort(ordenarNumero);
      total = lista.length;
      linhas = lista.map((m) => (
        <LinhaAnimal key={m.numero} onVerAnimal={() => setNumeroAberto(m.numero)} campos={<>
          <Pilula>{categoriaDe(m.numero)}</Pilula>
          <Campo label="Nº" valor={m.numero} />
          <Campo label="IEP" valor={`${m.iep_dias} dias`} />
          <Campo label="Último parto" valor={formatDate(m.data_ultimo_parto)} />
        </>} />
      ));
    } else if (drill === "secagens") {
      const lista = [...(secagemReq.dados?.secagem || [])].sort(ordenarNumero);
      total = lista.length;
      linhas = lista.map((s) => (
        <LinhaAnimal key={s.numero} onVerAnimal={() => setNumeroAberto(s.numero)} campos={<>
          <Pilula>{categoriaDe(s.numero)}</Pilula>
          <Campo label="Nº" valor={s.numero} />
          <Campo label="Lote atual" valor={s.grupo || "—"} />
          <Campo label="Secar em" valor={s.dias_para_secagem != null ? `${s.dias_para_secagem} dias` : "—"} />
          <Campo label="Previsão de secagem" valor={s.previsao_secagem ? formatDate(s.previsao_secagem) : "—"} />
        </>} />
      ));
    } else if (drill === "producao") {
      const lista = animais.filter((a) => (a.del_dias != null && a.del_dias >= 0) || (a.ult_cl_kg != null && a.ult_cl_kg > 0)).sort(ordenarNumero);
      total = lista.length;
      linhas = lista.map((a) => (
        <LinhaAnimal key={a.numero} onVerAnimal={() => setNumeroAberto(a.numero)} campos={<>
          <Pilula>{categoriaDe(a.numero)}</Pilula>
          <Campo label="Nº" valor={a.numero} />
          <Campo label="DEL" valor={a.del_dias != null ? `${a.del_dias} dias` : "—"} />
          <Campo label="Última produção" valor={a.ult_cl_kg != null ? `${val(a.ult_cl_kg)} L` : "—"} />
        </>} />
      ));
    }

    const carregandoLista = (drill === "secagens" ? secagemReq.carregando && !secagemReq.dados : animaisReq.carregando && !animaisReq.dados) || (carregando && !dados);

    return (
      <div>
        <MobVoltar titulo={DRILL_TITULO[drill]} onVoltar={() => setDrill(null)} />
        {carregandoLista ? (
          <Carregando />
        ) : !linhas.length ? (
          <Vazio>Nenhum animal nesta lista.</Vazio>
        ) : (
          <>
            <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginBottom: "0.6rem" }}>
              Total: {total} animal{total !== 1 ? "is" : ""}
            </p>
            {linhas}
          </>
        )}
      </div>
    );
  }

  // ── Painel de cards ──────────────────────────────────────────────────────
  const reb = dados?.rebanho || {};
  const rep = dados?.reproducao || {};
  const pev = dados?.reproducao_categorias?.todas?.pev;
  const prod = dados?.producao || {};

  type Cartao = { chave: string; titulo: string; valor: string; sufixo?: string; onClick: () => void; combo?: { valor: string; rotulo: string }[] };
  const cartoes: Cartao[] = [
    { chave: "rebanho", titulo: "Rebanho", valor: val(reb.total), onClick: () => router.push("/app/rebanho") },
    { chave: "gestantes", titulo: "Gestantes", valor: val(rep.prenhes), onClick: () => setDrill("gestantes") },
    { chave: "inseminadas", titulo: "Inseminadas", valor: val(rep.inseminadas), onClick: () => setDrill("inseminadas") },
    { chave: "pev", titulo: "PEV", valor: val(pev), onClick: () => setDrill("pev") },
    { chave: "vazias", titulo: "Vazias", valor: val(rep.vazias), onClick: () => setDrill("vazias") },
    { chave: "aptas", titulo: "Aptas", valor: val(rep.aptas), onClick: () => setDrill("aptas") },
    { chave: "atrasadas", titulo: "Atrasadas", valor: val((animais.filter((a) => (a.sit_rep || "").trim() === "Vaz. atr.")).length), onClick: () => setDrill("atrasadas") },
    { chave: "partoPrevisto", titulo: "Parto previsto", valor: val(rep.partos_previstos?.em_30_dias), onClick: () => setDrill("partoPrevisto") },
    { chave: "iep", titulo: "IEP médio", valor: rep.iep_dias != null ? `${val(rep.iep_dias)} d` : "—", onClick: () => setDrill("iep") },
    { chave: "secagens", titulo: "Secagens previstas", valor: val(secagemReq.dados?.secagem?.length ?? null), onClick: () => setDrill("secagens") },
    {
      chave: "producao", titulo: "DEL médio · Produção média", valor: "", onClick: () => setDrill("producao"),
      combo: [
        { valor: prod.del_medio != null ? `${val(prod.del_medio)} d` : "—", rotulo: "DEL médio" },
        { valor: prod.producao_media_kg != null ? `${val(prod.producao_media_kg)} L` : "—", rotulo: "Produção média" },
      ],
    },
  ];

  return (
    <div>
      <MobVoltar titulo="Rebanho" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_rebanho_dash" mostrar={doCache} />

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.6rem" }}>
          {cartoes.map((c) => (
            <button key={c.chave} type="button" onClick={c.onClick}
              className="mob-card" style={{ padding: "1rem 0.9rem", textAlign: "center", cursor: "pointer", border: "1px solid var(--mob-border)", gridColumn: c.combo ? "1 / -1" : undefined }}>
              {c.chave === "rebanho" && (
                <div style={{ display: "flex", justifyContent: "center", marginBottom: "0.3rem" }}><CowIcon size={22} /></div>
              )}
              {c.combo ? (
                <div style={{ display: "flex", justifyContent: "space-around" }}>
                  {c.combo.map((x) => (
                    <div key={x.rotulo}>
                      <div style={{ fontSize: "1.5rem", fontWeight: 800, lineHeight: 1.1, color: "var(--mob-text)" }}>{x.valor}</div>
                      <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)", marginTop: "0.25rem", fontWeight: 600 }}>{x.rotulo}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: "1.7rem", fontWeight: 800, lineHeight: 1.1, color: "var(--mob-text)" }}>{c.valor}</div>
              )}
              <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)", marginTop: "0.35rem", fontWeight: 600 }}>{c.titulo}</div>
              <div style={{ fontSize: "0.68rem", color: "var(--mob-dourado-2)", marginTop: "0.3rem", fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", gap: "0.15rem" }}>
                {c.chave === "rebanho" ? "abrir" : "ver lista"} <ChevronRight size={12} />
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
