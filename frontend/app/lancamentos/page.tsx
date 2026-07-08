"use client";
import { useEffect, useMemo, useState } from "react";
import {
  ClipboardList, Info, Heart, Stethoscope, Milk, Syringe, Wallet, Package, Baby, Scale,
  Search, ExternalLink, BookOpen, X, Plus, AlertTriangle, Trash2,
} from "lucide-react";
import { fetchAnimais, fetchEstoque, fetchServicosAnalise, fetchSanidade, criarControlesLeiteiros, salvarDiagnostico, movimentarEstoque, criarAplicacaoSanidade } from "@/lib/api";
import { RESPONSAVEIS } from "@/lib/constants";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPicker } from "@/components/AnimalPicker";
import { FormFinanceiro } from "@/components/FormFinanceiro";
import { FormExclusao } from "@/components/FormExclusao";
import { FormPesagemCorporal } from "@/components/FormPesagemCorporal";

type EstoqueItem = { nome: string; quantidade?: number | null; unidade?: string | null; categoria?: string | null };

/**
 * Tela de Lançamentos — RASCUNHO funcional.
 * Os formulários já reagem aos dados reais do rebanho (selects, DEL automático,
 * cálculos de colostro, cronograma de IATF), mas ainda NÃO gravam nada — o
 * salvamento entra com o banco permanente + login. Serve para desenharmos a
 * forma final de cada lançamento.
 */

const LINK_COLOSTRO = "https://altagenetics.inf.br/shared/Circulares/Informativo_formas%20de%20utiliza%C3%A7%C3%A3o%20colostro_site.pdf";
const cod = (g: string | null | undefined) => (g && /^\d\d/.test(g) ? g.slice(0, 2) : "");
const LACT = ["01", "02", "03"];
const IDADE_MIN_SERVICO = 13; // meses — abaixo disso a fêmea não é apta a serviço
// Sêmen (touros) atualmente em estoque — usados na seleção do touro em Serviço/IA.
const TOUROS_ESTOQUE = [
  "COORS", "GUINESS", "ABS LABEL", "CAMPEAO FI", "DESCONHECIDO", "HAGEN", "JAG", "LUZIO", "METEORO",
  "MOSAIC", "HILLUX", "NABIL", "PRAFESS", "ROBO", "MESSI", "STORMY", "SUCESSOR", "VALENTE", "VICTINHO",
];
const UNIDADES = ["ml", "kg", "L", "unidade", "dose"];
const MOVIMENTOS_ESTOQUE = ["Aplicação", "Saída de ajuste", "Entrada de ajuste", "Entrada de cortesia", "Doação"];
// Movimentos que reduzem o estoque (baixa).
const MOV_BAIXA = new Set(["Aplicação", "Saída de ajuste", "Doação"]);

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };
const nota: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)", marginLeft: "0.35rem" };

function Campo({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return <div style={{ gridColumn: full ? "1 / -1" : undefined }}><label style={lbl}>{label}</label>{children}</div>;
}

function addDias(iso: string, n: number): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00"); d.setDate(d.getDate() + n);
  return d.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" });
}

// Seleção de animal via tabela clara (Nº · Grupo · Categoria · Sit. Rep. · DEL).
const SelectAnimal = AnimalPicker;

const SalvarEmBreve = () => (
  <div className="flex items-center gap-3 mt-4" style={{ flexWrap: "wrap" }}>
    <button className="btn-primary" disabled style={{ opacity: 0.55, cursor: "not-allowed" }}>Salvar (em breve)</button>
    <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>O salvamento entra com o banco de dados permanente e o login.</span>
  </div>
);

/* ───────────────────────── Manual do colostro (modal em tela) ───────────────────────── */
const MANUAL_COLOSTRO = [
  { t: "1. Nascimento e ordenha rápida", d: "Curar umbigo (iodo 10%). Ordenhar a vaca na 1ª HORA pós-parto, com higiene total dos tetos. Coletar todo o colostro em balde limpo. Meta: ordenhar dentro da 1ª hora." },
  { t: "2. Teste de qualidade (Brix)", d: "Misturar o colostro. Pingar 2 gotas no refratômetro limpo e ler a escala Brix contra a luz." },
  { t: "3. A decisão", d: ">25% (OURO): congelar/dar (excelente). 18–25% (PRATA): enriquecer com pó até 25% (médio). <18% (BRONZE): descartar 1ª mamada (ruim) — apenas se o estoque estiver cheio." },
  { t: "4. Banco de colostro (congelamento)", d: "2 L de colostro OURO (>25%) no saco. Tirar o ar, selar, etiquetar (data, vaca, Brix), deitar na forma e congelar." },
  { t: "5. A hora de mamar", d: "Descongelar em banho-maria (máx. 50°C — use termômetro!). Fornecer a 37°C. Volume: 10% do peso vivo (aprox. 4 L)." },
  { t: "6. O tira-teima (monitoramento)", d: "Coletar sangue da bezerra entre 24h e 48h de vida. Separar o soro e medir no refratômetro. Meta: Brix do soro > 8,4%." },
];
const MANUAL_SANGUE = [
  { t: "1. O momento certo", d: "Coletar entre 24h e 48h após o nascimento. Antes de 24h a absorção continua; após 48h perde precisão." },
  { t: "2. A coleta", d: "Conter a bezerra. Agulha e tubo limpos (tampa vermelha). Coletar 5 ml da veia jugular. Higiene total." },
  { t: "3. Separação do soro", d: "Deixar o tubo em pé em temperatura ambiente por 2–4 horas. O sangue coagula e libera o soro (líquido amarelo)." },
  { t: "4. Leitura no refratômetro", d: "Limpar o refratômetro. Pingar uma gota do SORO amarelo (não o sangue). Ler a escala Brix contra a luz." },
  { t: "5. Resultado e ação", d: "≥ 8,4% (sucesso): manter rotina, bezerra protegida. 8,1–8,3% (alerta): monitorar e revisar rotina de colostro. ≤ 8,0% (falha): ação urgente, bezerra desprotegida." },
  { t: "6. Ação urgente (falha ≤ 8,0%)", d: "1) Isolar a bezerra. 2) Monitorar temperatura 2x/dia. 3) Avisar Vet/Gerente. 4) Auditar urgente a rotina de colostro." },
];

function ManualColostroModal({ onClose }: { onClose: () => void }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60, padding: "1rem" }} onClick={onClose}>
      <div className="card" style={{ width: "500px", maxWidth: "96vw", maxHeight: "88vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>Manual — Rotina do Colostro</div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}><X size={20} /></button>
        </div>
        <div className="space-y-2">
          {MANUAL_COLOSTRO.map((s) => (
            <div key={s.t} style={{ borderLeft: "3px solid var(--green-light)", paddingLeft: "0.6rem" }}>
              <p style={{ fontSize: "0.8rem", fontWeight: 700 }}>{s.t}</p>
              <p style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{s.d}</p>
            </div>
          ))}
        </div>
        <a href={LINK_COLOSTRO} target="_blank" rel="noreferrer" className="flex items-center gap-2 mt-4" style={{ color: "var(--dourado-light)", fontSize: "0.8rem" }}>
          <ExternalLink size={14} /> Abrir a tabela oficial da Alta (PDF)
        </a>
      </div>
    </div>
  );
}

function ManualSangueModal({ onClose }: { onClose: () => void }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60, padding: "1rem" }} onClick={onClose}>
      <div className="card" style={{ width: "500px", maxWidth: "96vw", maxHeight: "88vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>Manual — Teste de Sangue (IgG)</div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}><X size={20} /></button>
        </div>
        <div className="space-y-2">
          {MANUAL_SANGUE.map((s) => (
            <div key={s.t} style={{ borderLeft: "3px solid var(--blue)", paddingLeft: "0.6rem" }}>
              <p style={{ fontSize: "0.8rem", fontWeight: 700 }}>{s.t}</p>
              <p style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{s.d}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ───────────────────────── Formulários por tipo ───────────────────────── */

// Subtítulo de seção dentro de um formulário.
const Secao = ({ children }: { children: React.ReactNode }) => (
  <p style={{ fontSize: "0.72rem", fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--dourado-light)", margin: "1rem 0 0.5rem" }}>{children}</p>
);

const HORMONIOS: Record<string, string[]> = {
  progesterona: ["Sincrogest", "Cidr"],
  benzoato: ["Sincrodiol"],
  buserelina: ["Sincroforte"],
  cloprostenol: ["Estron"],
  cipionato: ["SincroCP"],
};

function FormServico({ animais }: { animais: AnimalRow[] }) {
  const [emLote, setEmLote] = useState(false);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [um, setUm] = useState("");
  const [protocolo, setProtocolo] = useState<"IATF" | "Cio">("IATF");
  const [d0, setD0] = useState("");
  const toggle = (n: string) => setSel((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Matriz (nº)">
          {emLote
            ? <div style={{ ...inputStyle, padding: "0.4rem", maxHeight: "8rem", overflowY: "auto" }}>
                {animais.map((a) => (
                  <label key={a.numero} className="flex items-center gap-2" style={{ fontSize: "0.8rem", padding: "0.15rem 0" }}>
                    <input type="checkbox" checked={sel.has(a.numero)} onChange={() => toggle(a.numero)} />
                    {a.numero} · {a.grupo_primario || "—"}
                  </label>
                ))}
              </div>
            : <SelectAnimal animais={animais} value={um} onChange={setUm} placeholder="Selecione a matriz…" />}
        </Campo>
        <Campo label="Serviço">
          <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", padding: "0.45rem 0" }}>
            <input type="checkbox" checked={emLote} onChange={(e) => setEmLote(e.target.checked)} /> Em lote (vários animais)
          </label>
          {emLote && <span style={nota}>{sel.size} animal(is) selecionado(s)</span>}
        </Campo>
        <Campo label="Data do serviço / D0"><input type="date" style={inputStyle} value={d0} onChange={(e) => setD0(e.target.value)} /></Campo>
        <Campo label="Protocolo">
          <select style={inputStyle} value={protocolo} onChange={(e) => setProtocolo(e.target.value as any)}>
            <option value="IATF">Protocolo IATF</option>
            <option value="Cio">Cio natural</option>
          </select>
        </Campo>
        <Campo label="Touro / sêmen (em estoque)">
          <select style={inputStyle} defaultValue=""><option value="" disabled>Selecione o sêmen…</option>{TOUROS_ESTOQUE.map((t) => <option key={t}>{t}</option>)}</select>
        </Campo>
        <Campo label="Responsável / inseminador">
          <select style={inputStyle} defaultValue=""><option value="" disabled>Selecione…</option>{RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}</select>
        </Campo>
      </div>
      <p style={nota}>Matriz lista apenas fêmeas aptas (≥ {IDADE_MIN_SERVICO} meses). Touro mostra o sêmen em estoque.</p>

      {protocolo === "IATF" ? (
        <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
          <div className="card-header mb-2" style={{ background: "none", color: "var(--dourado-light)", padding: "0 0 0.3rem" }}>
            Cronograma IATF — será lançado na agenda
          </div>
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead><tr><th>Dia</th><th>Data</th><th>Ação / hormônio</th><th>Produto (estoque)</th></tr></thead>
              <tbody>
                <tr><td style={{ fontWeight: 700 }}>D0</td><td>{addDias(d0, 0)}</td><td>Implante de progesterona</td>
                  <td><select style={{ ...inputStyle, padding: "0.25rem" }}>{HORMONIOS.progesterona.map((o) => <option key={o}>{o}</option>)}</select></td></tr>
                <tr><td></td><td></td><td>Benzoato de estradiol — 2 ml</td>
                  <td><select style={{ ...inputStyle, padding: "0.25rem" }}>{HORMONIOS.benzoato.map((o) => <option key={o}>{o}</option>)}</select></td></tr>
                <tr><td></td><td></td><td>Acetato de buserelina — 2,5 ml</td>
                  <td><select style={{ ...inputStyle, padding: "0.25rem" }}>{HORMONIOS.buserelina.map((o) => <option key={o}>{o}</option>)}</select></td></tr>
                <tr><td style={{ fontWeight: 700 }}>D7</td><td>{addDias(d0, 7)}</td><td>Cloprostenol — 2 ml</td>
                  <td><select style={{ ...inputStyle, padding: "0.25rem" }}>{HORMONIOS.cloprostenol.map((o) => <option key={o}>{o}</option>)}</select></td></tr>
                <tr><td style={{ fontWeight: 700 }}>D9</td><td>{addDias(d0, 9)}</td><td>Retirar implante</td><td>—</td></tr>
                <tr><td></td><td></td><td>Cipionato de estradiol — 1 ml</td>
                  <td><select style={{ ...inputStyle, padding: "0.25rem" }}>{HORMONIOS.cipionato.map((o) => <option key={o}>{o}</option>)}</select></td></tr>
                <tr><td></td><td></td><td>Cloprostenol — 2 ml</td>
                  <td><select style={{ ...inputStyle, padding: "0.25rem" }}>{HORMONIOS.cloprostenol.map((o) => <option key={o}>{o}</option>)}</select></td></tr>
                <tr><td style={{ fontWeight: 700, color: "var(--green-light)" }}>D11</td><td>{addDias(d0, 11)}</td><td style={{ color: "var(--green-light)" }}>Inseminação (IATF)</td><td>—</td></tr>
              </tbody>
            </table>
          </div>
          <p style={nota}>Ao salvar, cria os eventos D0/D7/D9/D11 na agenda para cada animal. A baixa de estoque dos hormônios entra junto com o banco permanente.</p>
        </div>
      ) : (
        <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>
          Cio natural: registra a inseminação/cobertura na data do serviço, sem protocolo hormonal.
        </p>
      )}
      <SalvarEmBreve />
    </>
  );
}

function FormDiagnostico({ animais, ultServico }: { animais: AnimalRow[]; ultServico: Record<string, string> }) {
  // Lista as matrizes servidas (inseminadas ou prenhes a reconfirmar).
  const servidas = useMemo(() => animais.filter((a) => a.sit_rep === "Ins." || a.sit_rep === "Ges."), [animais]);
  const [matriz, setMatriz] = useState("");
  const [data, setData] = useState("");
  const [metodo, setMetodo] = useState("");
  const [resultado, setResultado] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  // Data da última IA/cobertura vem automaticamente do histórico da matriz.
  const ultimoServico = matriz ? ultServico[matriz] || "" : "";
  const ultimoLabel = ultimoServico ? new Date(ultimoServico + "T00:00:00").toLocaleDateString("pt-BR") : "—";

  const aviso30 = useMemo(() => {
    if (!data || !ultimoServico) return false;
    const dias = (new Date(data + "T00:00:00").getTime() - new Date(ultimoServico + "T00:00:00").getTime()) / 86400000;
    return dias >= 0 && dias < 30;
  }, [data, ultimoServico]);

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!matriz || !data || !resultado) { setErro("Selecione a matriz, a data e o resultado do diagnóstico."); return; }
    setSalvando(true);
    try {
      await salvarDiagnostico({ numero_matriz: matriz, data_diagnostico: data, resultado: resultado as any, metodo: metodo || undefined });
      setSucesso(
        resultado === "retoque"
          ? `Diagnóstico salvo. ${matriz} entrou na agenda para retoque.`
          : `Diagnóstico de ${matriz} salvo com sucesso.`
      );
      setMatriz(""); setData(""); setMetodo(""); setResultado("");
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar diagnóstico");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Matriz / novilha (servidas)">
          <SelectAnimal animais={servidas} value={matriz} onChange={setMatriz} placeholder="Selecione a matriz servida…" />
        </Campo>
        <Campo label="Última IA / cobertura (automático)"><input style={{ ...inputStyle, opacity: 0.8 }} value={ultimoLabel} readOnly /></Campo>
        <Campo label="Data do diagnóstico"><input type="date" style={inputStyle} value={data} onChange={(e) => setData(e.target.value)} /></Campo>
        <Campo label="Método">
          <select style={inputStyle} value={metodo} onChange={(e) => setMetodo(e.target.value)}>
            <option value="" disabled>Selecione…</option><option>Palpação</option><option>Ultrassom</option>
          </select>
        </Campo>
        <Campo label="Resultado" full>
          <select style={inputStyle} value={resultado} onChange={(e) => setResultado(e.target.value)}>
            <option value="" disabled>Selecione…</option>
            <option value="retoque">Positivo — marcar para retoque (segue em observação para reconfirmar)</option>
            <option value="reconfirmada">Positivo — reconfirmada (prenhez confirmada)</option>
            <option value="negativo">Negativo ou indefinido</option>
          </select>
        </Campo>
      </div>

      {aviso30 && (
        <div className="mt-3" style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", background: "rgba(217,119,6,0.12)", border: "1px solid var(--amber)", borderRadius: "8px", padding: "0.6rem 0.8rem" }}>
          <AlertTriangle size={16} style={{ color: "var(--amber)", marginTop: "0.1rem" }} />
          <span style={{ fontSize: "0.8rem" }}>Animal com menos de 30 dias da última inseminação/cobertura. Deseja confirmar?</span>
        </div>
      )}
      {resultado === "negativo" && (
        <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>
          Ao confirmar, o animal fica como <strong>vazia</strong> e será colocado para observação no próximo serviço.
        </p>
      )}
      {resultado === "retoque" && (
        <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>
          O animal entra na <strong>agenda para retoque</strong>, no dia do próximo serviço.
        </p>
      )}
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}

// Classificação padrão ouro/prata/bronze (manual da fazenda):
//  > 25% OURO (excelente) · 18–25% PRATA (médio, enriquecer) · < 18% BRONZE (ruim).
// Tabela de enriquecimento: medidas de pó por litro = Brix alvo − Brix atual.
function classeColostro(brix: number): { txt: string; cor: string } {
  if (brix > 25) return { txt: "Ouro (excelente)", cor: "var(--dourado-light)" };
  if (brix >= 18) return { txt: "Prata (médio — enriquecer)", cor: "var(--text-muted)" };
  return { txt: "Bronze (ruim — descartar 1ª mamada)", cor: "var(--red)" };
}

// Brix do soro (teste de IgG): >=8,4 sucesso; 8,1-8,3 alerta; <=8,0 falha.
function classeSoro(brix: number): { txt: string; cor: string } {
  if (brix >= 8.4) return { txt: "Sucesso — bezerra protegida", cor: "var(--green-light)" };
  if (brix >= 8.1) return { txt: "Alerta — monitorar, revisar colostro", cor: "var(--amber)" };
  return { txt: "Falha — bezerra desprotegida (ação urgente)", cor: "var(--red)" };
}
const OPCOES_SORO = Array.from({ length: 13 }, (_, i) => (6 + i * 0.5).toFixed(1)); // 6,0 … 12,0

function FormParto({ animais }: { animais: AnimalRow[] }) {
  const [matriz, setMatriz] = useState("");
  const [tomouColostro, setTomou] = useState("");
  const [litros, setLitros] = useState("");
  const [brix, setBrix] = useState("");
  const [alvo, setAlvo] = useState("25");
  const [manualColostroAberto, setManualColostroAberto] = useState(false);
  const [manualSangueAberto, setManualSangueAberto] = useState(false);

  const [soro, setSoro] = useState("");
  const brixN = brix ? Number(brix) : null;
  const litrosN = litros ? Number(litros) : 0;
  const cls = brixN != null ? classeColostro(brixN) : null;
  const soroN = soro ? Number(soro) : null;
  const clsSoro = soroN != null ? classeSoro(soroN) : null;
  const enriquecer = brixN != null && brixN < 25;
  const medidasPorL = enriquecer ? Math.max(0, Number(alvo) - brixN!) : 0;
  const totalMedidas = medidasPorL * (litrosN || 1);

  return (
    <>
      {manualColostroAberto && <ManualColostroModal onClose={() => setManualColostroAberto(false)} />}
      {manualSangueAberto && <ManualSangueModal onClose={() => setManualSangueAberto(false)} />}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Matriz (nº)"><SelectAnimal animais={animais} value={matriz} onChange={setMatriz} placeholder="Selecione a matriz que pariu…" /></Campo>
        <Campo label="Data do parto"><input type="date" style={inputStyle} /></Campo>
        <Campo label="Situação">
          <select style={inputStyle} defaultValue=""><option value="" disabled>Selecione…</option><option>Normal</option><option>Natimorto</option><option>Aborto</option><option>Parto assistido / puxado</option></select>
        </Campo>
        <Campo label="Nº de crias"><input type="number" style={inputStyle} defaultValue="1" /></Campo>
      </div>

      <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
        <div className="card-header mb-2 flex items-center gap-2" style={{ background: "none", color: "var(--dourado-light)", padding: "0 0 0.3rem" }}>
          <Baby size={14} /> Cadastro da cria (prole)
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Campo label="Número da cria"><input style={inputStyle} placeholder="ex.: 483" /></Campo>
          <Campo label="Sexo da cria"><select style={inputStyle} defaultValue=""><option value="" disabled>Selecione…</option><option>Fêmea</option><option>Macho</option></select></Campo>
          <Campo label="Cria baixada? (não entra no rebanho)"><select style={inputStyle} defaultValue="Não"><option>Não</option><option>Sim</option></select></Campo>
        </div>

        <div className="mt-3" style={{ background: "rgba(22,101,52,0.12)", border: "1px solid var(--green-light)", borderRadius: "8px", padding: "0.6rem 0.8rem" }}>
          <p style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--green-light)" }}>Colostragem da cria</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
            <Campo label="Tomou colostro?"><select style={inputStyle} value={tomouColostro} onChange={(e) => setTomou(e.target.value)}><option value="" disabled>Selecione…</option><option>Sim</option><option>Não</option></select></Campo>
            <Campo label="Quantidade de colostro (litros)">
              <select style={inputStyle} value={litros} onChange={(e) => setLitros(e.target.value)}>
                <option value="" disabled>Selecione…</option>
                {["1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5"].map((l) => <option key={l} value={l}>{l} L</option>)}
              </select>
            </Campo>
            <Campo label="Brix do colostro (%)">
              <select style={inputStyle} value={brix} onChange={(e) => setBrix(e.target.value)}>
                <option value="" disabled>Selecione…</option>
                {Array.from({ length: 21 }, (_, i) => 15 + i).map((b) => <option key={b} value={b}>{b}%</option>)}
              </select>
            </Campo>
          </div>

          {cls && (
            <div className="mt-2" style={{ fontSize: "0.82rem" }}>
              Qualidade: <strong style={{ color: cls.cor }}>{cls.txt}</strong>
              {enriquecer && (
                <div style={{ marginTop: "0.5rem", background: "rgba(94,26,46,0.2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "0.6rem 0.8rem" }}>
                  <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
                    <span>Enriquecer até</span>
                    <select style={{ ...inputStyle, width: "auto", padding: "0.2rem 0.4rem" }} value={alvo} onChange={(e) => setAlvo(e.target.value)}>
                      {["22", "23", "24", "25", "26", "27", "28", "29", "30"].map((a) => <option key={a} value={a}>{a}%</option>)}
                    </select>
                  </div>
                  <p style={{ marginTop: "0.4rem" }}>
                    Adicionar <strong style={{ color: "var(--dourado-light)" }}>{medidasPorL} medida(s) de colostro em pó por litro</strong> (15 g cada).
                    {litrosN > 0 && <> Para {litrosN} L: <strong>{totalMedidas} medidas ≈ {totalMedidas * 15} g</strong>.</>}
                  </p>
                </div>
              )}
            </div>
          )}

          <div className="flex items-center gap-3 mt-2" style={{ flexWrap: "wrap" }}>
            <button onClick={() => setManualColostroAberto(true)} className="btn-ghost flex items-center gap-1" style={{ fontSize: "0.75rem" }}><BookOpen size={13} /> Manual do colostro</button>
            <a href={LINK_COLOSTRO} target="_blank" rel="noreferrer" className="flex items-center gap-1" style={{ color: "var(--dourado-light)", fontSize: "0.75rem" }}><ExternalLink size={13} /> Tabela oficial (PDF)</a>
          </div>
        </div>

        <div className="mt-3" style={{ background: "rgba(30,111,168,0.1)", border: "1px solid var(--blue)", borderRadius: "8px", padding: "0.6rem 0.8rem" }}>
          <p style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--blue)" }}>Exame de sangue (IgG) da cria</p>
          <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
            Colher entre <strong>24h e 48h</strong> após o nascimento. Meta: Brix do soro &gt; 8,4%
            (≥ 8,4% sucesso · 8,1–8,3% alerta · ≤ 8,0% falha).
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
            <Campo label="Brix do soro (%)">
              <select style={inputStyle} value={soro} onChange={(e) => setSoro(e.target.value)}>
                <option value="" disabled>Selecione…</option>
                {OPCOES_SORO.map((v) => <option key={v} value={v}>{v.replace(".", ",")}%</option>)}
              </select>
            </Campo>
            {clsSoro && <div style={{ display: "flex", alignItems: "flex-end" }}><p style={{ fontSize: "0.82rem" }}>Resultado: <strong style={{ color: clsSoro.cor }}>{clsSoro.txt}</strong></p></div>}
          </div>
          <div className="flex items-center gap-3 mt-2" style={{ flexWrap: "wrap" }}>
            <button onClick={() => setManualSangueAberto(true)} className="btn-ghost flex items-center gap-1" style={{ fontSize: "0.75rem" }}><BookOpen size={13} /> Manual do sangue</button>
          </div>
        </div>
      </div>
      <SalvarEmBreve />
    </>
  );
}

function FormControle({ animais, lotesLact }: { animais: AnimalRow[]; lotesLact: string[] }) {
  const [modo, setModo] = useState<"vaca" | "lote">("vaca");
  const [vaca, setVaca] = useState("");
  const [lote, setLote] = useState("");
  const [nOrd, setNOrd] = useState(2);
  const [ord, setOrd] = useState<string[]>(["", "", ""]);
  const [porVaca, setPorVaca] = useState<Record<string, string[]>>({});
  const [dataControle, setDataControle] = useState(() => new Date().toISOString().slice(0, 10));
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const del = useMemo(() => animais.find((a) => a.numero === vaca)?.del_dias ?? null, [animais, vaca]);
  const total = ord.slice(0, nOrd).reduce((s, v) => s + (Number(v) || 0), 0);

  // Vacas do lote selecionado — abre a listagem individual pra pesagem de cada uma.
  const vacasDoLote = useMemo(() => (lote ? animais.filter((a) => a.grupo_primario === lote) : []), [animais, lote]);
  const setOrdVaca = (numero: string, idx: number, valor: string) =>
    setPorVaca((p) => { const arr = [...(p[numero] || ["", "", ""])]; arr[idx] = valor; return { ...p, [numero]: arr }; });
  const totalVaca = (numero: string) => (porVaca[numero] || []).slice(0, nOrd).reduce((s, v) => s + (Number(v) || 0), 0);
  const totalLote = vacasDoLote.reduce((s, a) => s + totalVaca(a.numero), 0);

  function limpar() {
    setOrd(["", "", ""]);
    setPorVaca({});
  }

  async function salvar() {
    setErro(null); setSucesso(null);
    const entradas = modo === "vaca"
      ? (vaca ? [{ numero_matriz: vaca, ordenhas: ord.slice(0, nOrd).map((v) => Number(v) || 0) }] : [])
      : vacasDoLote.map((a) => ({ numero_matriz: a.numero, ordenhas: (porVaca[a.numero] || []).slice(0, nOrd).map((v) => Number(v) || 0) }))
          .filter((e) => e.ordenhas.some((v) => v > 0));
    if (!entradas.length) { setErro(modo === "vaca" ? "Selecione a vaca e informe ao menos uma ordenha." : "Informe a pesagem de ao menos uma vaca do lote."); return; }
    setSalvando(true);
    try {
      const r = await criarControlesLeiteiros({ data_controle: dataControle, entradas });
      setSucesso(`${r.criados} ${r.criados === 1 ? "pesagem" : "pesagens"} lançada${r.criados === 1 ? "" : "s"} com sucesso.`);
      limpar();
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar controle leiteiro");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Modalidade">
          <select style={inputStyle} value={modo} onChange={(e) => { setModo(e.target.value as any); setErro(null); setSucesso(null); }}>
            <option value="vaca">Por vaca</option>
            <option value="lote">Por lote</option>
          </select>
        </Campo>
        <Campo label="Nº de ordenhas">
          <select style={inputStyle} value={nOrd} onChange={(e) => setNOrd(Number(e.target.value))}>
            <option value={2}>2 ordenhas</option>
            <option value={3}>3 ordenhas</option>
          </select>
        </Campo>
        {modo === "vaca" ? (
          <>
            <Campo label="Vaca"><SelectAnimal animais={animais} value={vaca} onChange={setVaca} placeholder="Selecione a vaca…" /></Campo>
            <Campo label="DEL (automático)"><input style={{ ...inputStyle, opacity: 0.8 }} value={del != null ? `${del} dias` : "—"} readOnly /></Campo>
          </>
        ) : (
          <Campo label="Lote">
            <select style={inputStyle} value={lote} onChange={(e) => setLote(e.target.value)}>
              <option value="">Selecione…</option>
              {lotesLact.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </Campo>
        )}
        <Campo label="Data do controle"><input type="date" style={inputStyle} value={dataControle} onChange={(e) => setDataControle(e.target.value)} /></Campo>
      </div>

      {modo === "vaca" ? (
        <div className="mt-3">
          <label style={lbl}>Quilos por ordenha</label>
          <div className="flex gap-3" style={{ flexWrap: "wrap" }}>
            {Array.from({ length: nOrd }, (_, i) => (
              <div key={i}>
                <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{i + 1}ª ordenha</span>
                <input type="number" inputMode="decimal" style={{ ...inputStyle, width: "7rem" }} value={ord[i]}
                  onChange={(e) => setOrd((p) => { const n = [...p]; n[i] = e.target.value; return n; })} placeholder="kg" />
              </div>
            ))}
            <div>
              <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Total do dia</span>
              <div style={{ ...inputStyle, width: "7rem", fontWeight: 700, color: "var(--green-light)" }}>{total.toFixed(1)} kg</div>
            </div>
          </div>
        </div>
      ) : lote ? (
        <div className="card mt-3" style={{ padding: 0 }}>
          <div className="card-header m-3 flex items-center justify-between">
            <span>Vacas do lote {lote} ({vacasDoLote.length})</span>
            <span style={{ fontSize: "0.78rem", color: "var(--green-light)", fontWeight: 700 }}>Total do lote: {totalLote.toFixed(1)} kg</span>
          </div>
          <div className="overflow-x-auto" style={{ maxHeight: "460px" }}>
            <table className="fazenda-table" style={{ margin: 0 }}>
              <thead>
                <tr>
                  <th>Nº</th><th style={{ textAlign: "right" }}>DEL</th>
                  {Array.from({ length: nOrd }, (_, i) => <th key={i} style={{ textAlign: "right" }}>{i + 1}ª ordenha (kg)</th>)}
                  <th style={{ textAlign: "right" }}>Total</th>
                </tr>
              </thead>
              <tbody>
                {vacasDoLote.map((a) => (
                  <tr key={a.numero}>
                    <td style={{ fontWeight: 700 }}>{a.numero}</td>
                    <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{a.del_dias ?? "—"}</td>
                    {Array.from({ length: nOrd }, (_, i) => (
                      <td key={i}>
                        <input type="number" inputMode="decimal" style={{ ...inputStyle, textAlign: "right" }}
                          value={(porVaca[a.numero] || [])[i] || ""} onChange={(e) => setOrdVaca(a.numero, i, e.target.value)} placeholder="kg" />
                      </td>
                    ))}
                    <td style={{ textAlign: "right", fontWeight: 700, color: "var(--green-light)" }}>{totalVaca(a.numero).toFixed(1)}</td>
                  </tr>
                ))}
                {!vacasDoLote.length && <tr><td colSpan={nOrd + 3} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>Nenhuma vaca neste lote.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <p style={nota}>Selecione um lote para ver a listagem de vacas e lançar a pesagem individual de todas de uma vez.</p>
      )}

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}

      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}

// Prévia do estoque restante após uma baixa de quantidade.
function EstoqueRestante({ estoque, produto, quantidade }: { estoque: EstoqueItem[]; produto: string; quantidade: number }) {
  const item = estoque.find((e) => e.nome === produto);
  if (!item) return null;
  const atual = item.quantidade ?? 0;
  const restante = atual - (quantidade || 0);
  return (
    <p style={{ fontSize: "0.78rem", marginTop: "0.3rem" }}>
      Estoque atual: <strong>{atual} {item.unidade || ""}</strong> → após a aplicação:{" "}
      <strong style={{ color: restante < 0 ? "var(--red)" : "var(--green-light)" }}>{restante} {item.unidade || ""}</strong>
      {restante < 0 && <span style={{ color: "var(--red)" }}> (estoque insuficiente!)</span>}
    </p>
  );
}

// Mesma regra do backend (fazenda.rules.unidades): unidade de aplicação
// precisa ser compatível com a unidade de estoque do produto — ex.: um
// produto guardado em "ml" pode ser aplicado em ml/unidade/dose, mas não em L.
const GRUPOS_UNIDADE: string[][] = [["ml", "unidade", "dose"], ["L", "kg"]];
function unidadesCompativeis(unidadeEstoque: string | null | undefined): string[] {
  if (!unidadeEstoque) return UNIDADES;
  const grupo = GRUPOS_UNIDADE.find((g) => g.includes(unidadeEstoque));
  return grupo || [unidadeEstoque];
}

type ItemSanidade = { produto: string; via: string; quantidade: string; unidade: string };
const itemSanidadeVazio = (): ItemSanidade => ({ produto: "", via: "", quantidade: "", unidade: "" });

function FormSanidade({ animais, lotes, estoque, produtos }: { animais: AnimalRow[]; lotes: string[]; estoque: EstoqueItem[]; produtos: string[] }) {
  const [modo, setModo] = useState<"animal" | "lote">("animal");
  const [animal, setAnimal] = useState("");
  const [lotesSel, setLotesSel] = useState<Set<string>>(new Set());
  const [itens, setItens] = useState<ItemSanidade[]>([itemSanidadeVazio()]);
  const [dataAplicacao, setDataAplicacao] = useState(() => new Date().toISOString().slice(0, 10));
  const [responsavel, setResponsavel] = useState("");
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const toggleLote = (l: string) => setLotesSel((p) => { const s = new Set(p); s.has(l) ? s.delete(l) : s.add(l); return s; });
  // Lista de produtos vem do relatório de sanidade (medicamentos já aplicados),
  // complementada pelos itens do estoque que ainda não apareceram na sanidade.
  const nomesEstoque = estoque.map((e) => e.nome);
  const listaProdutos = Array.from(new Set([...produtos, ...nomesEstoque])).sort();

  const atualizarItem = (idx: number, patch: Partial<ItemSanidade>) => setItens((p) => {
    const n = [...p]; n[idx] = { ...n[idx], ...patch }; return n;
  });
  const escolherProduto = (idx: number, produto: string) => {
    const compativeis = unidadesCompativeis(estoque.find((e) => e.nome === produto)?.unidade);
    atualizarItem(idx, { produto, unidade: compativeis[0] || "" });
  };
  const acrescentarItem = () => setItens((p) => [...p, itemSanidadeVazio()]);
  const removerItem = (idx: number) => setItens((p) => (p.length > 1 ? p.filter((_, i) => i !== idx) : p));

  async function salvar() {
    setErro(null); setSucesso(null);
    const animaisAlvo = modo === "animal"
      ? (animal ? [animal] : [])
      : animais.filter((a) => a.grupo_primario && lotesSel.has(a.grupo_primario)).map((a) => a.numero);
    if (!animaisAlvo.length) { setErro(modo === "animal" ? "Selecione o animal." : "Selecione ao menos um lote."); return; }
    const itensValidos = itens.filter((i) => i.produto && Number(i.quantidade) > 0 && i.unidade);
    if (!itensValidos.length) { setErro("Adicione ao menos um produto com quantidade e unidade."); return; }

    setSalvando(true);
    try {
      const r = await criarAplicacaoSanidade({
        data_aplicacao: dataAplicacao, animais: animaisAlvo, responsavel: responsavel || undefined, observacao: observacao || undefined,
        itens: itensValidos.map((i) => ({ produto: i.produto, via: i.via || undefined, quantidade: Number(i.quantidade), unidade: i.unidade })),
      });
      setSucesso(`${r.criados} aplicação(ões) lançada(s) com sucesso.${r.avisos?.length ? " " + r.avisos.join(" ") : ""}`);
      setItens([itemSanidadeVazio()]); setObservacao("");
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar aplicação de sanidade");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Lançar por">
          <select style={inputStyle} value={modo} onChange={(e) => setModo(e.target.value as any)}><option value="animal">Animal</option><option value="lote">Lote</option></select>
        </Campo>
        <Campo label="Data"><input type="date" style={inputStyle} value={dataAplicacao} onChange={(e) => setDataAplicacao(e.target.value)} /></Campo>
        {modo === "animal"
          ? <Campo label="Animal" full><SelectAnimal animais={animais} value={animal} onChange={setAnimal} /></Campo>
          : <Campo label="Lotes" full>
              <div className="flex gap-3" style={{ flexWrap: "wrap" }}>
                {lotes.map((l) => <label key={l} className="flex items-center gap-2" style={{ fontSize: "0.8rem" }}><input type="checkbox" checked={lotesSel.has(l)} onChange={() => toggleLote(l)} /> {l}</label>)}
              </div>
            </Campo>}
        <Campo label="Responsável"><select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}><option value="" disabled>Selecione…</option>{RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}</select></Campo>
        <Campo label="Observação"><input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
      </div>

      <Secao>Produtos aplicados</Secao>
      <div className="space-y-3">
        {itens.map((item, idx) => {
          const estoqueItem = estoque.find((e) => e.nome === item.produto);
          const compativeis = unidadesCompativeis(estoqueItem?.unidade);
          return (
            <div key={idx} style={{ border: "1px solid var(--border)", borderRadius: "8px", padding: "0.75rem", position: "relative" }}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Campo label={`Produto/medicamento ${idx + 1}`}>
                  <select style={inputStyle} value={item.produto} onChange={(e) => escolherProduto(idx, e.target.value)}>
                    <option value="" disabled>Selecione…</option>
                    {listaProdutos.map((nome) => {
                      const est = estoque.find((e) => e.nome === nome);
                      return <option key={nome} value={nome}>{nome}{est?.quantidade != null ? ` (${est.quantidade} ${est.unidade || ""})` : ""}</option>;
                    })}
                  </select>
                </Campo>
                <Campo label="Via">
                  <select style={inputStyle} value={item.via} onChange={(e) => atualizarItem(idx, { via: e.target.value })}>
                    <option value="">Selecione…</option>
                    {["Intramuscular", "Subcutânea", "Oral", "Intravenosa", "Tópica"].map((o) => <option key={o}>{o}</option>)}
                  </select>
                </Campo>
                <Campo label="Quantidade (dose)"><input type="number" inputMode="decimal" style={inputStyle} value={item.quantidade} onChange={(e) => atualizarItem(idx, { quantidade: e.target.value })} /></Campo>
                <Campo label="Unidade">
                  <select style={inputStyle} value={item.unidade} onChange={(e) => atualizarItem(idx, { unidade: e.target.value })}>
                    {compativeis.map((u) => <option key={u}>{u}</option>)}
                  </select>
                </Campo>
              </div>
              {item.produto && <EstoqueRestante estoque={estoque} produto={item.produto} quantidade={Number(item.quantidade) || 0} />}
              {itens.length > 1 && (
                <button onClick={() => removerItem(idx)} className="btn-ghost" style={{ position: "absolute", top: "0.5rem", right: "0.5rem", color: "var(--red)", fontSize: "0.72rem" }}>
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          );
        })}
      </div>
      <button onClick={acrescentarItem} className="btn-ghost flex items-center gap-1 mt-2" style={{ fontSize: "0.78rem" }}><Plus size={14} /> Acrescentar produto</button>

      <p style={nota}>Ao salvar, dá baixa da quantidade no estoque (por animal, ou multiplicada pelo efetivo dos lotes) quando a unidade escolhida bater com a unidade de estoque do produto.</p>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}

const MOVIMENTOS_SAIDA = MOVIMENTOS_ESTOQUE.filter((m) => MOV_BAIXA.has(m));
const MOVIMENTOS_ENTRADA = MOVIMENTOS_ESTOQUE.filter((m) => !MOV_BAIXA.has(m));

function FormEstoque({ estoque }: { estoque: EstoqueItem[] }) {
  const [produto, setProduto] = useState("");
  const [tipo, setTipo] = useState<"entrada" | "saida" | "">("");
  const [mov, setMov] = useState("");
  const [qtd, setQtd] = useState("");
  const [unidade, setUnidade] = useState("");
  const [dataMov, setDataMov] = useState(() => new Date().toISOString().slice(0, 10));
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const item = estoque.find((e) => e.nome === produto);
  const q = Number(qtd) || 0;
  const baixa = MOV_BAIXA.has(mov);
  const restante = item ? (item.quantidade ?? 0) + (baixa ? -q : q) : null;

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!produto || !tipo || !mov || !q) { setErro("Selecione o produto, o tipo de movimento e a quantidade."); return; }
    setSalvando(true);
    try {
      const r = await movimentarEstoque({ nome: produto, movimento: mov, quantidade: q, unidade: unidade || item?.unidade || undefined, data_movimento: dataMov, observacao: observacao || undefined });
      setSucesso(`Estoque de ${produto} atualizado: ${r.quantidade} ${r.unidade || ""}.`);
      setMov(""); setQtd(""); setObservacao("");
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar movimento de estoque");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Produto / medicamento">
          <select style={inputStyle} value={produto} onChange={(e) => setProduto(e.target.value)}>
            <option value="" disabled>Selecione…</option>
            {estoque.map((e) => <option key={e.nome} value={e.nome}>{e.nome}{e.quantidade != null ? ` (${e.quantidade} ${e.unidade || ""})` : ""}</option>)}
          </select>
        </Campo>
        <Campo label="Tipo de movimento">
          <select style={inputStyle} value={tipo} onChange={(e) => { setTipo(e.target.value as any); setMov(""); }}>
            <option value="" disabled>Selecione…</option>
            <option value="entrada">Entrada</option>
            <option value="saida">Saída</option>
          </select>
        </Campo>
        <Campo label="Movimento">
          <select style={inputStyle} value={mov} onChange={(e) => setMov(e.target.value)} disabled={!tipo}>
            <option value="" disabled>{tipo ? "Selecione…" : "Escolha o tipo primeiro"}</option>
            {(tipo === "entrada" ? MOVIMENTOS_ENTRADA : tipo === "saida" ? MOVIMENTOS_SAIDA : []).map((m) => <option key={m}>{m}</option>)}
          </select>
        </Campo>
        <Campo label="Quantidade"><input type="number" inputMode="decimal" style={inputStyle} value={qtd} onChange={(e) => setQtd(e.target.value)} /></Campo>
        <Campo label="Unidade">
          <select style={inputStyle} value={unidade || item?.unidade || "unidade"} onChange={(e) => setUnidade(e.target.value)}>
            {UNIDADES.map((u) => <option key={u}>{u}</option>)}
          </select>
        </Campo>
        <Campo label="Data"><input type="date" style={inputStyle} value={dataMov} onChange={(e) => setDataMov(e.target.value)} /></Campo>
        <Campo label="Observação" full><textarea style={{ ...inputStyle, minHeight: "3rem" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
      </div>
      {item && mov && (
        <p style={{ fontSize: "0.78rem", marginTop: "0.3rem" }}>
          {baixa ? "Baixa" : "Entrada"} · Estoque atual: <strong>{item.quantidade ?? 0} {item.unidade || ""}</strong> → depois:{" "}
          <strong style={{ color: (restante ?? 0) < 0 ? "var(--red)" : "var(--green-light)" }}>{restante} {item.unidade || ""}</strong>
          {(restante ?? 0) < 0 && <span style={{ color: "var(--red)" }}> (insuficiente!)</span>}
        </p>
      )}
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}

// Tipos de lançamento, agrupados: alguns grupos (Reprodutivo, Produção) têm uma
// camada inferior de sub-tipos, para economizar abas no menu.
const TIPOS_GRUPOS = [
  {
    id: "reprodutivo", label: "Reprodutivo", icon: Heart,
    desc: "Serviço/IA, diagnóstico de gestação ou parto/nascimento.",
    subs: [
      { id: "servico", label: "Serviço / IA", icon: Heart, desc: "Inseminação, IATF ou cobertura — individual ou em lote." },
      { id: "diagnostico", label: "Diagnóstico de gestação", icon: Stethoscope, desc: "Resultado do toque / diagnóstico de prenhez." },
      { id: "parto", label: "Parto / nascimento", icon: Baby, desc: "Registro de parto, da cria e do manejo de colostro." },
    ],
  },
  {
    id: "producao", label: "Produção", icon: Milk,
    desc: "Controle leiteiro ou pesagem corporal.",
    subs: [
      { id: "controle", label: "Controle leiteiro", icon: Milk, desc: "Pesagem de leite por vaca ou por lote." },
      { id: "pesagem", label: "Pesagem corporal", icon: Scale, desc: "Peso vivo por animal ou por lote — acompanha o crescimento do rebanho." },
    ],
  },
  { id: "sanidade", label: "Sanidade", icon: Syringe, desc: "Aplicação de medicamento / manejo sanitário.", leaf: "sanidade" },
  { id: "financeiro", label: "Financeiro", icon: Wallet, desc: "Lançamento de receita ou despesa.", leaf: "financeiro" },
  { id: "estoque", label: "Estoque", icon: Package, desc: "Entrada ou saída de item do estoque.", leaf: "estoque" },
  { id: "exclusao", label: "Exclusão", icon: Trash2, desc: "Apagar um lançamento já salvo, com prévia de impacto.", leaf: "exclusao" },
];

// Lista achatada de sub-tipos (folhas), usada para saber qual formulário renderizar.
const TIPOS_LEAFS = TIPOS_GRUPOS.flatMap((g) => (g.subs ? g.subs : [{ id: g.leaf!, label: g.label, icon: g.icon, desc: g.desc }]));
// Grupo dono de um determinado sub-tipo (folha).
const grupoDoSel = (id: string) => TIPOS_GRUPOS.find((g) => g.leaf === id || g.subs?.some((s) => s.id === id))?.id ?? "reprodutivo";

export default function LancamentosPage() {
  const [sel, setSel] = useState("servico");
  const [sujo, setSujo] = useState(false);
  const trocarTipo = (novoId: string) => {
    if (novoId === sel) return;
    if (sujo && !window.confirm("Você tem certeza que quer sair dessa página? Os dados não salvos serão perdidos.")) return;
    setSujo(false);
    setSel(novoId);
  };
  // Avisa também ao fechar a aba/recarregar/sair do site com dados não salvos.
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => { if (sujo) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [sujo]);
  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  const [estoque, setEstoque] = useState<EstoqueItem[]>([]);
  const [servicos, setServicos] = useState<any[]>([]);
  const [produtosSanidade, setProdutosSanidade] = useState<string[]>([]);
  useEffect(() => {
    fetchAnimais().then(setAnimais).catch(() => {});
    fetchEstoque().then((d) => setEstoque(d.itens || [])).catch(() => {});
    fetchServicosAnalise().then((d) => setServicos(d.servicos || [])).catch(() => {});
    fetchSanidade().then((d) => setProdutosSanidade(Array.from(new Set((d.aplicacoes || d.registros || []).map((r: any) => r.produto).filter(Boolean))).sort() as string[])).catch(() => {});
  }, []);

  // Última IA/cobertura por matriz (para o diagnóstico puxar automático).
  const ultServico = useMemo(() => {
    const m: Record<string, string> = {};
    servicos.forEach((s) => { if (s.numero && s.data && (!m[s.numero] || s.data > m[s.numero])) m[s.numero] = s.data; });
    return m;
  }, [servicos]);

  // Lotes: remove duplicados que diferem só por maiúscula/minúscula (ex.: "03 - Média"
  // e "03 - MÉDIA"), mantendo a versão em caixa-alta.
  const lotes = useMemo(() => {
    const porChave = new Map<string, string>();
    (animais.map((a) => a.grupo_primario).filter(Boolean) as string[]).forEach((l) => {
      const chave = l.toUpperCase();
      const atual = porChave.get(chave);
      if (!atual || l === l.toUpperCase()) porChave.set(chave, l === l.toUpperCase() ? l : atual || l);
    });
    return Array.from(porChave.values()).sort();
  }, [animais]);
  const lotesLact = useMemo(() => lotes.filter((l) => LACT.includes(cod(l))), [lotes]);
  // Fêmeas aptas a serviço: idade >= 13 meses (mantém as sem idade informada, por segurança).
  const aptasServico = useMemo(() => animais.filter((a) => {
    const idade = (a as any).idade_meses;
    return idade == null || idade >= IDADE_MIN_SERVICO;
  }), [animais]);
  const tipo = TIPOS_LEAFS.find((t) => t.id === sel)!;
  const grupoAtivo = grupoDoSel(sel);

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><ClipboardList size={22} style={{ color: "var(--dourado-light)" }} /> Lançamentos</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Entrada de dados direto no sistema — escolha o tipo e preencha.</p>
      </div>

      <div className="card mb-4" style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start", background: "rgba(94,26,46,0.18)" }}>
        <Info size={16} style={{ color: "var(--dourado-light)", marginTop: "0.15rem", flexShrink: 0 }} />
        <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
          {sel === "financeiro" ? (
            <><strong style={{ color: "var(--text)" }}>Financeiro já grava de verdade.</strong> Os lançamentos aqui vão para o banco permanente e aparecem nas 5 abas de contas do menu Financeiro.</>
          ) : sel === "controle" ? (
            <><strong style={{ color: "var(--text)" }}>Controle leiteiro já grava de verdade.</strong> As pesagens lançadas aqui vão para o banco permanente.</>
          ) : sel === "pesagem" ? (
            <><strong style={{ color: "var(--text)" }}>Pesagem corporal já grava de verdade.</strong> Os pesos lançados aqui vão para o banco permanente e alimentam o relatório de GMD/GPD logo abaixo.</>
          ) : sel === "exclusao" ? (
            <><strong style={{ color: "var(--text)" }}>Exclusão apaga de verdade.</strong> Administradores excluem na hora; os demais usuários só solicitam, e a exclusão fica pendente de aprovação.</>
          ) : sel === "diagnostico" ? (
            <><strong style={{ color: "var(--text)" }}>Diagnóstico já grava de verdade.</strong> Um resultado marcado para retoque entra na agenda automaticamente.</>
          ) : sel === "estoque" ? (
            <><strong style={{ color: "var(--text)" }}>Estoque já grava de verdade.</strong> Entradas e saídas lançadas aqui atualizam a quantidade do item na hora.</>
          ) : sel === "sanidade" ? (
            <><strong style={{ color: "var(--text)" }}>Sanidade já grava de verdade.</strong> Aceita vários produtos por lançamento; a baixa de estoque só acontece quando a unidade escolhida bate com a do estoque.</>
          ) : (
            <><strong style={{ color: "var(--text)" }}>Rascunho funcional.</strong> Os selects já usam o rebanho real e os cálculos funcionam,
            mas <strong>nada é gravado ainda</strong> — o salvamento entra com o banco permanente + login. Me diga o que ajustar em cada tipo.</>
          )}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[240px_1fr] gap-4">
        <div className="card" style={{ padding: "0.5rem", alignSelf: "start" }}>
          <div className="space-y-1">
            {TIPOS_GRUPOS.map((g) => {
              const Icon = g.icon;
              const ativo = g.id === grupoAtivo;
              const alvo = g.subs ? (ativo ? sel : g.subs[0].id) : g.leaf!;
              return (
                <div key={g.id}>
                  <button onClick={() => trocarTipo(alvo)}
                    style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.55rem 0.7rem", borderRadius: "8px", cursor: "pointer", textAlign: "left",
                      border: "1px solid " + (ativo ? "var(--dourado)" : "transparent"), background: ativo ? "rgba(94,26,46,0.4)" : "transparent",
                      color: ativo ? "var(--dourado-light)" : "var(--text-muted)", fontSize: "0.85rem", fontWeight: ativo ? 700 : 500 }}>
                    <Icon size={16} /> {g.label}
                  </button>
                  {ativo && g.subs && (
                    <div className="space-y-1" style={{ paddingLeft: "1.4rem", marginTop: "0.2rem" }}>
                      {g.subs.map((s) => {
                        const SIcon = s.icon; const subAtivo = s.id === sel;
                        return (
                          <button key={s.id} onClick={() => trocarTipo(s.id)}
                            style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.4rem 0.6rem", borderRadius: "6px", cursor: "pointer", textAlign: "left",
                              border: "1px solid " + (subAtivo ? "var(--dourado)" : "transparent"), background: subAtivo ? "rgba(94,26,46,0.3)" : "transparent",
                              color: subAtivo ? "var(--dourado-light)" : "var(--text-muted)", fontSize: "0.78rem", fontWeight: subAtivo ? 700 : 500 }}>
                            <SIcon size={13} /> {s.label}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="card" onChange={() => sel !== "exclusao" && setSujo(true)}>
          <div className="card-header mb-1 flex items-center gap-2"><tipo.icon size={14} /> {tipo.label}</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", margin: "0.4rem 0 1rem" }}>{tipo.desc}</p>
          {sel === "servico" && <FormServico animais={aptasServico} />}
          {sel === "diagnostico" && <FormDiagnostico animais={animais} ultServico={ultServico} />}
          {sel === "parto" && <FormParto animais={animais} />}
          {sel === "controle" && <FormControle animais={animais} lotesLact={lotesLact} />}
          {sel === "pesagem" && <FormPesagemCorporal animais={animais} lotes={lotes} />}
          {sel === "sanidade" && <FormSanidade animais={animais} lotes={lotes} estoque={estoque} produtos={produtosSanidade} />}
          {sel === "financeiro" && <FormFinanceiro responsaveis={RESPONSAVEIS} onSujo={setSujo} />}
          {sel === "estoque" && <FormEstoque estoque={estoque} />}
          {sel === "exclusao" && <FormExclusao />}
        </div>
      </div>
    </div>
  );
}
