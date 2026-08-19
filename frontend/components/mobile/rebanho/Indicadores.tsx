"use client";
// Tela raiz de Rebanho — painel único com todos os quadros: Animais, Lotes e
// os 10 indicadores (só leitura). Animais/Lotes abrem a tela cheia
// correspondente (via callback do pai); os demais quadros abrem uma lista de
// animais por trás do número, só com os campos pertinentes ao indicador
// (nunca Raça, nunca Nome ao lado de Número).
import { useState } from "react";
import { ChevronRight, Fence, Baby, Syringe, CalendarClock, HeartCrack, CheckCircle2, AlertTriangle, CalendarDays, Repeat, Droplet, Milk, FileDown } from "lucide-react";
import { MobTitulo, MobVoltar } from "@/components/mobile/ui";
import { CowIcon } from "@/components/CowIcon";
import { fetchIndicadores, fetchAnimais, fetchRelatoriosManejo, fetchEstadosReprodutivos, formatDate, type EstadosReprodutivos, type EstadoReprodutivoAnimal } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";
import { FichaDetalhe } from "@/components/mobile/rebanho/Ficha";
import { exportarPDF, type ColunaExport } from "@/lib/export";

type IndicadoresResp = {
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
  reproducao_categorias?: { todas?: { pev?: number | null; vazias?: number | null } };
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

// Rótulo de cada estado reprodutivo ao vivo (ver backend
// fazenda/rules/estado_reprodutivo.py — mesmas chaves).
const ROTULO_ESTADO: Record<string, string> = {
  gestante: "Gestante", inseminada: "Inseminada", em_protocolo: "Em protocolo (IA atual)",
  pev: "PEV", apta: "Apta", atrasada: "Atrasada", nao_apta: "Não apta", vazia: "Vazia",
};

function ordenarNumero(a: { numero: string }, b: { numero: string }): number {
  const na = Number(a.numero), nb = Number(b.numero);
  if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb;
  return a.numero.localeCompare(b.numero);
}

function val(v?: number | null, sufixo = ""): string {
  if (v == null) return "—";
  return `${v.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}${sufixo}`;
}

// Dias entre a data de referência do snapshot (data_referencia do endpoint)
// e uma data-alvo ISO — usado para "Dias para o parto".
function diasAte(referenciaIso: string, alvoIso?: string | null): number | null {
  if (!alvoIso) return null;
  const ref = new Date(`${referenciaIso}T00:00:00`);
  const alvo = new Date(`${alvoIso}T00:00:00`);
  return Math.round((alvo.getTime() - ref.getTime()) / 86400000);
}

// Rótulo do tipo de inseminação: monta natural, IATF (com protocolo) ou cio
// natural (protocolo ausente/"cio natural") — regra combinada de tipo_servico + protocolo.
function tipoInseminacaoLabel(a: EstadoReprodutivoAnimal): string {
  const tipo = (a.tipo_servico || "").toLowerCase();
  if (tipo.includes("monta") || tipo.includes("natural")) return "Monta natural";
  const protocolo = (a.protocolo || "").trim();
  if (protocolo && protocolo.toLowerCase() !== "cio natural") return "IA — IATF";
  return "IA — cio natural";
}

type Drill = "gestantes" | "inseminadas" | "pev" | "vazias" | "aptas" | "atrasadas" | "protocolo" | "partoPrevisto" | "iep" | "secagens" | "producao";

const DRILL_TITULO: Record<Drill, string> = {
  gestantes: "Gestantes", inseminadas: "Inseminadas", pev: "PEV", vazias: "Vazias", aptas: "Aptas",
  atrasadas: "Atrasadas", protocolo: "IA atual (D0–D11)", partoPrevisto: "Parto previsto", iep: "IEP médio", secagens: "Secagens previstas",
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

export default function Indicadores({ onAbrirAnimais, onAbrirLotes }: { onAbrirAnimais: () => void; onAbrirLotes: () => void }) {
  const { dados, doCache, carregando } = useCarregar<IndicadoresResp>("menu_rebanho_dash", fetchIndicadores);
  const animaisReq = useCarregar<Animal[]>("menu_rebanho_dash_animais", () => fetchAnimais() as Promise<Animal[]>);
  const secagemReq = useCarregar<Record<string, ItemSecagem[]>>("menu_rebanho_dash_secagem", fetchRelatoriosManejo);
  // Estado reprodutivo AO VIVO (substitui Animal.sit_rep, congelado do CSV) —
  // ver GET /indicadores/estados-reprodutivos.
  const estadosReq = useCarregar<EstadosReprodutivos>("menu_rebanho_dash_estados", fetchEstadosReprodutivos);
  const [drill, setDrill] = useState<Drill | null>(null);
  const [numeroAberto, setNumeroAberto] = useState<string | null>(null);
  const [exportando, setExportando] = useState(false);

  const animais = animaisReq.dados || [];
  const porNumero = new Map(animais.map((a) => [a.numero, a]));
  const categoriaDe = (numero: string) => porNumero.get(numero)?.categoria_abrev || porNumero.get(numero)?.grupo_primario || "—";
  const estadoAnimais = estadosReq.dados?.animais || [];
  const dataRef = estadosReq.dados?.data_referencia || "";
  const contagemEstados = estadosReq.dados?.contagem || {};

  if (numeroAberto) {
    return <FichaDetalhe numero={numeroAberto} onVoltar={() => setNumeroAberto(null)} />;
  }

  // ── Drill-down de um card ───────────────────────────────────────────────
  if (drill) {
    const rep = dados?.reproducao || {};

    let linhas: React.ReactNode[] = [];
    let total = 0;
    // Colunas/linhas em formato plano para o botão "Exportar PDF" — mesmos
    // valores exibidos em tela, sem re-ordenar (listas de estado já vêm
    // ordenadas por número do endpoint).
    let colunasExport: ColunaExport[] = [];
    let linhasExport: Record<string, unknown>[] = [];

    if (drill === "gestantes") {
      // Estado AO VIVO (não Animal.sit_rep, congelado do CSV) — ver
      // GET /indicadores/estados-reprodutivos. Não reordenar: o endpoint já
      // devolve por número crescente.
      const lista = estadoAnimais.filter((a) => a.estado === "gestante");
      total = lista.length;
      linhas = lista.map((g) => (
        <LinhaAnimal key={g.numero} onVerAnimal={() => setNumeroAberto(g.numero)} campos={<>
          <Pilula>{g.categoria}</Pilula>
          <Campo label="Nº" valor={g.numero} />
          <Campo label="Dias de gestação" valor={g.dias_gestacao ?? "—"} />
          <Campo label="Dias para o parto" valor={diasAte(dataRef, g.parto_previsto) ?? "—"} />
          <Campo label="Parto previsto" valor={formatDate(g.parto_previsto || "")} />
        </>} />
      ));
      colunasExport = [
        { header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" },
        { header: "Dias de gestação", key: "dias_gestacao" }, { header: "Dias para o parto", key: "dias_parto" },
        { header: "Parto previsto", key: "parto_previsto" },
      ];
      linhasExport = lista.map((g) => ({
        numero: g.numero, categoria: g.categoria, dias_gestacao: g.dias_gestacao ?? "",
        dias_parto: diasAte(dataRef, g.parto_previsto) ?? "", parto_previsto: formatDate(g.parto_previsto || ""),
      }));
    } else if (drill === "inseminadas") {
      const lista = estadoAnimais.filter((a) => a.estado === "inseminada");
      total = lista.length;
      linhas = lista.map((a) => (
        <LinhaAnimal key={a.numero} onVerAnimal={() => setNumeroAberto(a.numero)} campos={<>
          <Pilula>{a.categoria}</Pilula>
          <Campo label="Nº" valor={a.numero} />
          <Campo label="Lote atual" valor={a.lote || "—"} />
          <Campo label="Data da inseminação" valor={formatDate(a.data_servico || "")} />
          <Campo label="Tipo" valor={tipoInseminacaoLabel(a)} />
        </>} />
      ));
      colunasExport = [
        { header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" }, { header: "Lote atual", key: "lote" },
        { header: "Data da inseminação", key: "data_servico" }, { header: "Tipo", key: "tipo" },
      ];
      linhasExport = lista.map((a) => ({
        numero: a.numero, categoria: a.categoria, lote: a.lote || "—",
        data_servico: formatDate(a.data_servico || ""), tipo: tipoInseminacaoLabel(a),
      }));
    } else if (drill === "protocolo") {
      const lista = estadoAnimais.filter((a) => a.estado === "em_protocolo");
      total = lista.length;
      linhas = lista.map((a) => (
        <LinhaAnimal key={a.numero} onVerAnimal={() => setNumeroAberto(a.numero)} campos={<>
          <Pilula>{a.categoria}</Pilula>
          <Campo label="Nº" valor={a.numero} />
          <Campo label="Dia do protocolo" valor={a.protocolo_dia_atual != null ? `D${a.protocolo_dia_atual}` : "—"} />
          <Campo label="D0" valor={formatDate(a.protocolo_d0 || "")} />
        </>} />
      ));
      colunasExport = [
        { header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" },
        { header: "Dia do protocolo", key: "dia" }, { header: "D0", key: "d0" },
      ];
      linhasExport = lista.map((a) => ({
        numero: a.numero, categoria: a.categoria,
        dia: a.protocolo_dia_atual != null ? `D${a.protocolo_dia_atual}` : "—", d0: formatDate(a.protocolo_d0 || ""),
      }));
    } else if (drill === "pev") {
      const lista = estadoAnimais.filter((a) => a.estado === "pev");
      total = lista.length;
      linhas = lista.map((a) => (
        <LinhaAnimal key={a.numero} onVerAnimal={() => setNumeroAberto(a.numero)} campos={<>
          <Pilula>{a.categoria}</Pilula>
          <Campo label="Nº" valor={a.numero} />
          <Campo label="DEL (dias pós-parto)" valor={a.del_dias ?? "—"} />
        </>} />
      ));
      colunasExport = [
        { header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" }, { header: "DEL (dias pós-parto)", key: "del" },
      ];
      linhasExport = lista.map((a) => ({ numero: a.numero, categoria: a.categoria, del: a.del_dias ?? "" }));
    } else if (drill === "vazias") {
      // Estado AO VIVO. "Vazia" aqui é o guarda-chuva de quem NÃO está prenhe,
      // inseminada nem em protocolo — mesmo conjunto que o "Vaz.*" do CSV
      // representava, para o número do card não mudar de significado.
      const lista = estadoAnimais.filter((a) => ["vazia", "apta", "atrasada", "pev", "nao_apta"].includes(a.estado));
      total = lista.length;
      linhas = lista.map((a) => (
        <LinhaAnimal key={a.numero} onVerAnimal={() => setNumeroAberto(a.numero)} campos={<>
          <Pilula>{a.categoria}</Pilula>
          <Campo label="Nº" valor={a.numero} />
          <Campo label="Situação" valor={ROTULO_ESTADO[a.estado] || a.estado} />
          <Campo label="Lote atual" valor={a.lote || "—"} />
        </>} />
      ));
      colunasExport = [
        { header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" },
        { header: "Situação", key: "situacao" }, { header: "Lote atual", key: "lote" },
      ];
      linhasExport = lista.map((a) => ({
        numero: a.numero, categoria: a.categoria, situacao: ROTULO_ESTADO[a.estado] || a.estado, lote: a.lote || "—",
      }));
    } else if (drill === "aptas") {
      // Estado AO VIVO — ver GET /indicadores/estados-reprodutivos.
      const lista = estadoAnimais.filter((a) => a.estado === "apta");
      total = lista.length;
      linhas = lista.map((a) => (
        <LinhaAnimal key={a.numero} onVerAnimal={() => setNumeroAberto(a.numero)} campos={<>
          <Pilula>{a.categoria}</Pilula>
          <Campo label="Nº" valor={a.numero} />
          <Campo label="DEL (dias pós-parto)" valor={a.del_dias ?? "—"} />
          <Campo label="Lote atual" valor={a.lote || "—"} />
        </>} />
      ));
      colunasExport = [
        { header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" },
        { header: "DEL (dias pós-parto)", key: "del" }, { header: "Lote atual", key: "lote" },
      ];
      linhasExport = lista.map((a) => ({ numero: a.numero, categoria: a.categoria, del: a.del_dias ?? "", lote: a.lote || "—" }));
    } else if (drill === "atrasadas") {
      const lista = estadoAnimais.filter((a) => a.estado === "atrasada");
      total = lista.length;
      linhas = lista.map((a) => (
        <LinhaAnimal key={a.numero} onVerAnimal={() => setNumeroAberto(a.numero)} campos={<>
          <Pilula>{a.categoria}</Pilula>
          <Campo label="Nº" valor={a.numero} />
          <Campo label="Lote atual" valor={a.lote || "—"} />
        </>} />
      ));
      colunasExport = [
        { header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" }, { header: "Lote atual", key: "lote" },
      ];
      linhasExport = lista.map((a) => ({ numero: a.numero, categoria: a.categoria, lote: a.lote || "—" }));
    } else if (drill === "partoPrevisto") {
      // Sai do payload antigo (partos_previstos_nums, derivado de sit_rep) e
      // passa a usar as gestantes AO VIVO — é o que traz dias de gestação e
      // permite calcular quantos dias faltam para o parto.
      const lista = estadoAnimais.filter((e) => {
        if (e.estado !== "gestante" || !e.parto_previsto) return false;
        const faltam = diasAte(dataRef, e.parto_previsto);
        return faltam !== null && faltam >= 0 && faltam <= 30;
      });
      total = lista.length;
      linhas = lista.map((e) => (
        <LinhaAnimal key={e.numero} onVerAnimal={() => setNumeroAberto(e.numero)} campos={<>
          <Pilula>{e.categoria}</Pilula>
          <Campo label="Nº" valor={e.numero} />
          <Campo label="Parto previsto" valor={e.parto_previsto ? formatDate(e.parto_previsto) : "—"} />
          <Campo label="Dias de gestação" valor={e.dias_gestacao ?? "—"} />
          <Campo label="Dias para o parto" valor={diasAte(dataRef, e.parto_previsto) ?? "—"} />
        </>} />
      ));
      colunasExport = [
        { header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" },
        { header: "Parto previsto", key: "parto_previsto" },
        { header: "Dias de gestação", key: "dias_gestacao" }, { header: "Dias para o parto", key: "dias_parto" },
      ];
      linhasExport = lista.map((e) => ({
        numero: e.numero, categoria: e.categoria,
        parto_previsto: e.parto_previsto ? formatDate(e.parto_previsto) : "—",
        dias_gestacao: e.dias_gestacao ?? "—", dias_parto: diasAte(dataRef, e.parto_previsto) ?? "—",
      }));
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
      colunasExport = [
        { header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" },
        { header: "IEP", key: "iep" }, { header: "Último parto", key: "ultimo_parto" },
      ];
      linhasExport = lista.map((m) => ({
        numero: m.numero, categoria: categoriaDe(m.numero), iep: `${m.iep_dias} dias`, ultimo_parto: formatDate(m.data_ultimo_parto),
      }));
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
      colunasExport = [
        { header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" }, { header: "Lote atual", key: "lote" },
        { header: "Secar em", key: "secar_em" }, { header: "Previsão de secagem", key: "previsao" },
      ];
      linhasExport = lista.map((s) => ({
        numero: s.numero, categoria: categoriaDe(s.numero), lote: s.grupo || "—",
        secar_em: s.dias_para_secagem != null ? `${s.dias_para_secagem} dias` : "—",
        previsao: s.previsao_secagem ? formatDate(s.previsao_secagem) : "—",
      }));
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
      colunasExport = [
        { header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" },
        { header: "DEL", key: "del" }, { header: "Última produção", key: "producao" },
      ];
      linhasExport = lista.map((a) => ({
        numero: a.numero, categoria: categoriaDe(a.numero),
        del: a.del_dias != null ? `${a.del_dias} dias` : "—", producao: a.ult_cl_kg != null ? `${val(a.ult_cl_kg)} L` : "—",
      }));
    }

    const carregandoLista =
      (drill === "secagens" ? secagemReq.carregando && !secagemReq.dados
        : ["gestantes", "inseminadas", "protocolo", "pev", "aptas", "atrasadas"].includes(drill) ? estadosReq.carregando && !estadosReq.dados
        : animaisReq.carregando && !animaisReq.dados) || (carregando && !dados);

    return (
      <div>
        <MobVoltar titulo={DRILL_TITULO[drill]} onVoltar={() => setDrill(null)} />
        {carregandoLista ? (
          <Carregando />
        ) : !linhas.length ? (
          <Vazio>Nenhum animal nesta lista.</Vazio>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem", marginBottom: "0.6rem" }}>
              <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)" }}>
                Total: {total} animal(is)
              </p>
              <button
                type="button"
                disabled={exportando}
                onClick={async () => {
                  setExportando(true);
                  try { await exportarPDF(DRILL_TITULO[drill], colunasExport, linhasExport, `rebanho_${drill}`); }
                  catch { /* erro já mostrado ao usuário dentro de exportarPDF (lib/export.ts) */ }
                  finally { setExportando(false); }
                }}
                style={{
                  display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.76rem", fontWeight: 700,
                  padding: "0.35rem 0.65rem", borderRadius: "var(--r-app)", border: "1px solid var(--mob-border)",
                  background: "var(--mob-surface)", color: "var(--mob-dourado-2)", opacity: exportando ? 0.6 : 1,
                }}
              >
                <FileDown size={14} /> {exportando ? "Gerando…" : "Exportar PDF"}
              </button>
            </div>
            {linhas}
          </>
        )}
      </div>
    );
  }

  // ── Painel de cards ──────────────────────────────────────────────────────
  const rep = dados?.reproducao || {};
  const pev = dados?.reproducao_categorias?.todas?.pev;
  const prod = dados?.producao || {};
  // Mesma chave de agrupamento usada em Lotes.tsx (grupo_primario, "(sem lote)"
  // quando vazio) — sem endpoint dedicado de contagem de lotes no backend.
  const totalLotes = new Set(animais.map((a) => a.grupo_primario || "(sem lote)")).size;

  type Cartao = {
    chave: string; titulo: string; valor: string; onClick: () => void; icone: React.ReactNode;
    combo?: { valor: string; rotulo: string }[];
    // "Atrasadas" é o único card do painel que sinaliza um problema, não uma
    // contagem neutra — ganha destaque em âmbar pra não se confundir com os
    // demais (ex.: "Lotes", "IEP médio"), que são só números de consulta.
    atencao?: boolean;
  };
  const cartoes: Cartao[] = [
    { chave: "animais", titulo: "Animais", valor: val(animais.length || null), onClick: onAbrirAnimais, icone: <CowIcon size={20} color="var(--mob-dourado-2)" /> },
    { chave: "lotes", titulo: "Lotes", valor: val(totalLotes || null), onClick: onAbrirLotes, icone: <Fence size={20} /> },
    { chave: "gestantes", titulo: "Gestantes", valor: val(rep.prenhes), onClick: () => setDrill("gestantes"), icone: <Baby size={20} /> },
    { chave: "inseminadas", titulo: "Inseminadas", valor: val(rep.inseminadas), onClick: () => setDrill("inseminadas"), icone: <Syringe size={20} /> },
    { chave: "pev", titulo: "PEV", valor: val(pev), onClick: () => setDrill("pev"), icone: <CalendarClock size={20} /> },
    // `reproducao.vazias` é o catch-all do backend (tudo que não é gestante
    // nem inseminada — inclusive quem está em protocolo); este card abre a
    // lista dos 5 estados vazia/apta/atrasada/pev/nao_apta, e é
    // `reproducao_categorias.todas.vazias` que conta exatamente esses 5.
    { chave: "vazias", titulo: "Vazias", valor: val(dados?.reproducao_categorias?.todas?.vazias ?? null), onClick: () => setDrill("vazias"), icone: <HeartCrack size={20} /> },
    { chave: "aptas", titulo: "Aptas", valor: val(rep.aptas), onClick: () => setDrill("aptas"), icone: <CheckCircle2 size={20} /> },
    // Contagem AO VIVO (estado), não mais Animal.sit_rep — mesma fonte da lista de drill-down.
    { chave: "atrasadas", titulo: "Atrasadas", valor: val(contagemEstados.atrasada ?? null), onClick: () => setDrill("atrasadas"), icone: <AlertTriangle size={20} />, atencao: true },
    { chave: "protocolo", titulo: "IA atual (D0–D11)", valor: val(contagemEstados.em_protocolo ?? null), onClick: () => setDrill("protocolo"), icone: <Syringe size={20} /> },
    // Contagem também ao vivo, para bater com a lista que o card abre.
    { chave: "partoPrevisto", titulo: "Parto previsto", valor: val(estadoAnimais.filter((e) => {
      if (e.estado !== "gestante" || !e.parto_previsto) return false;
      const faltam = diasAte(dataRef, e.parto_previsto);
      return faltam !== null && faltam >= 0 && faltam <= 30;
    }).length), onClick: () => setDrill("partoPrevisto"), icone: <CalendarDays size={20} /> },
    { chave: "iep", titulo: "IEP médio", valor: rep.iep_dias != null ? `${val(rep.iep_dias)} d` : "—", onClick: () => setDrill("iep"), icone: <Repeat size={20} /> },
    { chave: "secagens", titulo: "Secagens previstas", valor: val(secagemReq.dados?.secagem?.length ?? null), onClick: () => setDrill("secagens"), icone: <Droplet size={20} /> },
    {
      chave: "producao", titulo: "DEL médio · Produção média", valor: "", onClick: () => setDrill("producao"), icone: <Milk size={20} />,
      combo: [
        { valor: prod.del_medio != null ? `${val(prod.del_medio)} d` : "—", rotulo: "DEL médio" },
        { valor: prod.producao_media_kg != null ? `${val(prod.producao_media_kg)} L` : "—", rotulo: "Produção média" },
      ],
    },
  ];

  return (
    <div>
      <MobTitulo>Rebanho</MobTitulo>
      <AvisoCopia chave="menu_rebanho_dash" mostrar={doCache} />

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.6rem" }}>
          {cartoes.map((c) => (
            <button key={c.chave} type="button" onClick={c.onClick}
              className="mob-card" style={{
                padding: "0.9rem 0.85rem", textAlign: "center", cursor: "pointer",
                border: c.atencao ? "1px solid color-mix(in srgb, var(--mob-ambar) 45%, var(--mob-border))" : "1px solid var(--mob-border)",
                background: c.atencao ? "color-mix(in srgb, var(--mob-ambar) 7%, var(--mob-surface))" : undefined,
              }}>
              <div style={{ color: c.atencao ? "var(--mob-ambar)" : "var(--mob-dourado-2)", display: "flex", justifyContent: "center", marginBottom: "0.35rem" }}>{c.icone}</div>
              {c.combo ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                  {c.combo.map((x) => (
                    <div key={x.rotulo} style={{ display: "flex", alignItems: "baseline", justifyContent: "center", gap: "0.3rem" }}>
                      <span style={{ fontSize: "1.05rem", fontWeight: 800, color: "var(--mob-text)" }}>{x.valor}</span>
                      <span style={{ fontSize: "0.66rem", color: "var(--mob-muted)", fontWeight: 600 }}>{x.rotulo}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <>
                  <div style={{ fontSize: "1.7rem", fontWeight: 800, lineHeight: 1.1, color: c.atencao ? "var(--mob-ambar)" : "var(--mob-text)" }}>{c.valor}</div>
                  <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)", marginTop: "0.35rem", fontWeight: 600 }}>{c.titulo}</div>
                </>
              )}
              <div style={{ fontSize: "0.68rem", color: c.atencao ? "var(--mob-ambar)" : "var(--mob-dourado-2)", marginTop: "0.3rem", fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", gap: "0.15rem" }}>
                ver lista <ChevronRight size={12} />
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
