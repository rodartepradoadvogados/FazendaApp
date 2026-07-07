"use client";
import { useEffect, useMemo, useState } from "react";
import {
  ClipboardList, Info, Beef, Heart, Stethoscope, Milk, Syringe, Wallet, Package, Baby,
  Search, ExternalLink, BookOpen, X, Plus, AlertTriangle,
} from "lucide-react";
import { fetchAnimais, fetchEstoque, fetchServicosAnalise, fetchSanidade } from "@/lib/api";
import { AnimalRow } from "@/components/AnimalModal";

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

// Pessoas que podem aparecer como responsável / inseminador.
const RESPONSAVEIS = [
  "Jairo Nasser (proprietário)", "Alexandre Rodarte (CEO)", "Alexandre Scarpa (consultor)",
  "Leomir Bonfim (funcionário)", "Alane dos Santos (funcionária)", "Valéria Bonfim (funcionária)",
  "Jorbeson Nunes (funcionário)", "Huerik (veterinário COMIGO)", "Carlos Alpha/ABS (veterinário Alpha/ABS)",
];
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

// Select de animal (nº — grupo · situação). options já filtradas pela chamada.
function SelectAnimal({ animais, value, onChange, placeholder = "Selecione o animal…" }:
  { animais: AnimalRow[]; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <select style={inputStyle} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{placeholder}</option>
      {animais.map((a) => (
        <option key={a.numero} value={a.numero}>
          {a.numero} — {a.grupo_primario || "sem grupo"}{a.sit_rep ? ` · ${a.sit_rep}` : ""}
        </option>
      ))}
    </select>
  );
}

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

function ManualModal({ onClose }: { onClose: () => void }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60, padding: "1rem" }} onClick={onClose}>
      <div className="card" style={{ width: "760px", maxWidth: "96vw", maxHeight: "88vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>Manual — Colostro e Teste de Sangue (IgG)</div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}><X size={20} /></button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <p style={{ fontWeight: 700, color: "var(--dourado-light)", fontSize: "0.85rem", marginBottom: "0.5rem" }}>Rotina do Colostro</p>
            <div className="space-y-2">
              {MANUAL_COLOSTRO.map((s) => (
                <div key={s.t} style={{ borderLeft: "3px solid var(--vinho-light)", paddingLeft: "0.6rem" }}>
                  <p style={{ fontSize: "0.8rem", fontWeight: 700 }}>{s.t}</p>
                  <p style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{s.d}</p>
                </div>
              ))}
            </div>
          </div>
          <div>
            <p style={{ fontWeight: 700, color: "var(--dourado-light)", fontSize: "0.85rem", marginBottom: "0.5rem" }}>Teste de Sangue (IgG)</p>
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
        <a href={LINK_COLOSTRO} target="_blank" rel="noreferrer" className="flex items-center gap-2 mt-4" style={{ color: "var(--dourado-light)", fontSize: "0.8rem" }}>
          <ExternalLink size={14} /> Abrir a tabela oficial da Alta (PDF)
        </a>
      </div>
    </div>
  );
}

/* ───────────────────────── Cadastro geral de touro ───────────────────────── */
function TouroBusca() {
  const [touro, setTouro] = useState("");
  const [manual, setManual] = useState(false);
  return (
    <div style={{ border: "1px dashed var(--border)", borderRadius: "8px", padding: "0.75rem", marginTop: "0.5rem" }}>
      <label style={lbl}>Pai / touro (sêmen)</label>
      <div className="flex gap-2" style={{ flexWrap: "wrap" }}>
        <input style={{ ...inputStyle, flex: 1, minWidth: "10rem" }} value={touro} onChange={(e) => setTouro(e.target.value)} placeholder="nome ou código do touro" />
        <a className="btn-ghost flex items-center gap-1" style={{ fontSize: "0.75rem" }} target="_blank" rel="noreferrer"
          href={"https://absbullsearch.absglobal.com/?lang=bra-pt"}><Search size={13} /> ABS</a>
        <a className="btn-ghost flex items-center gap-1" style={{ fontSize: "0.75rem" }} target="_blank" rel="noreferrer"
          href={"https://touros.altagenetics.com.br/"}><Search size={13} /> Alta</a>
      </div>
      <button onClick={() => setManual((v) => !v)} className="btn-ghost" style={{ fontSize: "0.72rem", marginTop: "0.5rem" }}>
        {manual ? "Ocultar" : "Não encontrei — cadastro geral do touro"}
      </button>
      {manual && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
          <Campo label="Nome do touro"><input style={inputStyle} /></Campo>
          <Campo label="Código / registro"><input style={inputStyle} /></Campo>
          <Campo label="Raça"><input style={inputStyle} /></Campo>
          <Campo label="Central / empresa"><input style={inputStyle} placeholder="ABS, Alta, outra…" /></Campo>
          <Campo label="Observação" full><textarea style={{ ...inputStyle, minHeight: "3rem" }} /></Campo>
        </div>
      )}
      <p style={nota}>A busca automática na ABS/Alta será ligada com o banco; por ora abre o site para consulta e há o cadastro geral como reserva.</p>
    </div>
  );
}

/* ───────────────────────── Formulários por tipo ───────────────────────── */

// Subtítulo de seção dentro de um formulário.
const Secao = ({ children }: { children: React.ReactNode }) => (
  <p style={{ fontSize: "0.72rem", fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--dourado-light)", margin: "1rem 0 0.5rem" }}>{children}</p>
);

const CATEGORIAS_ANIMAL = ["Bezerra", "Novilha", "Novilha gestante", "Vaca", "Vaca em lactação", "Vaca seca", "Vaca gestante", "Touro", "Bezerro", "Descarte"];
const PELAGENS = ["Malhada (preto/branco)", "Malhada (vermelho/branco)", "Preta", "Vermelha", "Baia", "Cinza", "Outra"];

function FormAnimal({ lotes }: { lotes: string[] }) {
  const [origem, setOrigem] = useState<"nascimento" | "compra">("nascimento");
  return (
    <>
      <Secao>Identificação</Secao>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Número / brinco"><input style={inputStyle} placeholder="ex.: 464" /></Campo>
        <Campo label="Nome resumido"><input style={inputStyle} /></Campo>
        <Campo label="Nome completo"><input style={inputStyle} /></Campo>
        <Campo label="SISBOV"><input style={inputStyle} placeholder="105 ..." /></Campo>
        <Campo label="Registro"><input style={inputStyle} /></Campo>
        <Campo label="Sexo"><select style={inputStyle} defaultValue=""><option value="" disabled>Selecione…</option><option>Fêmea</option><option>Macho</option></select></Campo>
        <Campo label="Raça"><select style={inputStyle} defaultValue="Girolando"><option>Girolando</option><option>Holandês</option><option>Gir</option><option>Outra</option></select></Campo>
        <Campo label="Pelagem"><select style={inputStyle} defaultValue=""><option value="" disabled>Selecione…</option>{PELAGENS.map((p) => <option key={p}>{p}</option>)}</select></Campo>
        <Campo label="Categoria"><select style={inputStyle} defaultValue=""><option value="" disabled>Selecione…</option>{CATEGORIAS_ANIMAL.map((c) => <option key={c}>{c}</option>)}</select></Campo>
        <Campo label="Lote inicial"><select style={inputStyle} defaultValue=""><option value="" disabled>Selecione o lote…</option>{lotes.map((l) => <option key={l}>{l}</option>)}</select></Campo>
      </div>

      <Secao>Origem e situação</Secao>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Origem do cadastro">
          <select style={inputStyle} value={origem} onChange={(e) => setOrigem(e.target.value as any)}>
            <option value="nascimento">Nascimento (parto na fazenda)</option>
            <option value="compra">Compra (animal adquirido)</option>
          </select>
        </Campo>
        <Campo label="Data de nascimento"><input type="date" style={inputStyle} /></Campo>
        {origem === "compra" && <Campo label="Data de entrada na fazenda"><input type="date" style={inputStyle} /></Campo>}
        <Campo label="Proprietário"><input style={inputStyle} defaultValue="Jairo Nasser Quintiliano da Silva" /></Campo>
        <Campo label="Valor (R$)"><input type="number" inputMode="decimal" style={inputStyle} placeholder="ex.: 7000" /></Campo>
        <Campo label="Data de baixa (se houver)"><input type="date" style={inputStyle} /></Campo>
        <Campo label="Motivo de baixa" full><input style={inputStyle} placeholder="venda, morte, descarte…" /></Campo>
      </div>

      <Secao>Genealogia</Secao>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Nome da mãe"><input style={inputStyle} /></Campo>
        <Campo label="Número da mãe"><input style={inputStyle} /></Campo>
      </div>
      <TouroBusca />
      <p style={nota}>A busca do pai/touro na ABS/Alta preenche a genealogia paterna (avós/bisavós) automaticamente quando ligarmos o banco.</p>

      <Secao>Produção e reprodução</Secao>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Produção de leite (referência)"><input style={inputStyle} placeholder="kg/dia" /></Campo>
        <Campo label="Parto provável"><input type="date" style={inputStyle} /></Campo>
        <Campo label="Idade ao 1º parto (meses)"><input type="number" style={inputStyle} /></Campo>
        <Campo label="GPD / GMD (ganho de peso)"><input style={inputStyle} placeholder="ex.: -0,05" /></Campo>
      </div>

      <Secao>Outros</Secao>
      <div className="grid grid-cols-1 gap-3">
        <Campo label="Observações" full><textarea style={{ ...inputStyle, minHeight: "3rem" }} /></Campo>
        <Campo label="Foto do animal" full><input type="file" accept="image/*" style={{ ...inputStyle, padding: "0.3rem" }} /></Campo>
      </div>
      <SalvarEmBreve />
    </>
  );
}

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
  const [resultado, setResultado] = useState("");
  // Data da última IA/cobertura vem automaticamente do histórico da matriz.
  const ultimoServico = matriz ? ultServico[matriz] || "" : "";
  const ultimoLabel = ultimoServico ? new Date(ultimoServico + "T00:00:00").toLocaleDateString("pt-BR") : "—";

  const aviso30 = useMemo(() => {
    if (!data || !ultimoServico) return false;
    const dias = (new Date(data + "T00:00:00").getTime() - new Date(ultimoServico + "T00:00:00").getTime()) / 86400000;
    return dias >= 0 && dias < 30;
  }, [data, ultimoServico]);

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Matriz / novilha (servidas)">
          <SelectAnimal animais={servidas} value={matriz} onChange={setMatriz} placeholder="Selecione a matriz servida…" />
        </Campo>
        <Campo label="Última IA / cobertura (automático)"><input style={{ ...inputStyle, opacity: 0.8 }} value={ultimoLabel} readOnly /></Campo>
        <Campo label="Data do diagnóstico"><input type="date" style={inputStyle} value={data} onChange={(e) => setData(e.target.value)} /></Campo>
        <Campo label="Método"><select style={inputStyle} defaultValue=""><option value="" disabled>Selecione…</option><option>Palpação</option><option>Ultrassom</option></select></Campo>
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
          O animal segue na lista de <strong>retoque</strong> (positivo a reconfirmar) para relatórios futuros.
        </p>
      )}
      <SalvarEmBreve />
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
  const [manualAberto, setManualAberto] = useState(false);

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
      {manualAberto && <ManualModal onClose={() => setManualAberto(false)} />}
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
            <button onClick={() => setManualAberto(true)} className="btn-ghost flex items-center gap-1" style={{ fontSize: "0.72rem", marginTop: "0.5rem" }}><BookOpen size={12} /> Manual: quantidade, qualidade e enriquecimento</button>
          </div>
        )}

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
            <button onClick={() => setManualAberto(true)} className="btn-ghost flex items-center gap-1" style={{ fontSize: "0.75rem" }}><BookOpen size={13} /> Ver manual na tela</button>
            <a href={LINK_COLOSTRO} target="_blank" rel="noreferrer" className="flex items-center gap-1" style={{ color: "var(--dourado-light)", fontSize: "0.75rem" }}><ExternalLink size={13} /> Tabela oficial (PDF)</a>
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
  const [lotesSel, setLotesSel] = useState<Set<string>>(new Set());
  const [nOrd, setNOrd] = useState(2);
  const [ord, setOrd] = useState<string[]>(["", "", ""]);
  const toggleLote = (l: string) => setLotesSel((p) => { const s = new Set(p); s.has(l) ? s.delete(l) : s.add(l); return s; });
  const del = useMemo(() => animais.find((a) => a.numero === vaca)?.del_dias ?? null, [animais, vaca]);
  const total = ord.slice(0, nOrd).reduce((s, v) => s + (Number(v) || 0), 0);

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Modalidade">
          <select style={inputStyle} value={modo} onChange={(e) => setModo(e.target.value as any)}>
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
          <Campo label="Lotes em lactação" full>
            <div className="flex gap-3" style={{ flexWrap: "wrap" }}>
              {lotesLact.map((l) => (
                <label key={l} className="flex items-center gap-2" style={{ fontSize: "0.8rem" }}>
                  <input type="checkbox" checked={lotesSel.has(l)} onChange={() => toggleLote(l)} /> {l}
                </label>
              ))}
              {!lotesLact.length && <span style={nota}>Sem lotes de lactação carregados.</span>}
            </div>
          </Campo>
        )}
      </div>

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
        {modo === "lote" && <p style={nota}>No modo lote, os quilos/ordenha são lançados para cada vaca dos lotes selecionados (tela de digitação em massa entra com o salvamento).</p>}
      </div>
      <Campo label="Data do controle"><div style={{ maxWidth: "12rem" }}><input type="date" style={inputStyle} /></div></Campo>
      <p style={nota}>O histórico de controle leiteiro (filtrável por lote) já existe na aba Produção e passará a incluir estes lançamentos.</p>
      <SalvarEmBreve />
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

function FormSanidade({ animais, lotes, estoque, produtos }: { animais: AnimalRow[]; lotes: string[]; estoque: EstoqueItem[]; produtos: string[] }) {
  const [modo, setModo] = useState<"animal" | "lote">("animal");
  const [animal, setAnimal] = useState("");
  const [lotesSel, setLotesSel] = useState<Set<string>>(new Set());
  const [produto, setProduto] = useState("");
  const [qtd, setQtd] = useState("");
  const [unid, setUnid] = useState("ml");
  const toggleLote = (l: string) => setLotesSel((p) => { const s = new Set(p); s.has(l) ? s.delete(l) : s.add(l); return s; });
  // Lista de produtos vem do relatório de sanidade (medicamentos já aplicados),
  // complementada pelos itens do estoque que ainda não apareceram na sanidade.
  const nomesEstoque = estoque.map((e) => e.nome);
  const listaProdutos = Array.from(new Set([...produtos, ...nomesEstoque])).sort();

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Lançar por">
          <select style={inputStyle} value={modo} onChange={(e) => setModo(e.target.value as any)}><option value="animal">Animal</option><option value="lote">Lote</option></select>
        </Campo>
        <Campo label="Data"><input type="date" style={inputStyle} /></Campo>
        {modo === "animal"
          ? <Campo label="Animal" full><SelectAnimal animais={animais} value={animal} onChange={setAnimal} /></Campo>
          : <Campo label="Lotes" full>
              <div className="flex gap-3" style={{ flexWrap: "wrap" }}>
                {lotes.map((l) => <label key={l} className="flex items-center gap-2" style={{ fontSize: "0.8rem" }}><input type="checkbox" checked={lotesSel.has(l)} onChange={() => toggleLote(l)} /> {l}</label>)}
              </div>
            </Campo>}
        <Campo label="Produto / medicamento (relatório de sanidade)">
          <select style={inputStyle} value={produto} onChange={(e) => setProduto(e.target.value)}>
            <option value="" disabled>Selecione…</option>
            {listaProdutos.map((nome) => {
              const est = estoque.find((e) => e.nome === nome);
              return <option key={nome} value={nome}>{nome}{est?.quantidade != null ? ` (${est.quantidade} ${est.unidade || ""})` : ""}</option>;
            })}
          </select>
        </Campo>
        <Campo label="Via"><select style={inputStyle} defaultValue=""><option value="" disabled>Selecione…</option>{["Intramuscular", "Subcutânea", "Oral", "Intravenosa", "Tópica"].map((o) => <option key={o}>{o}</option>)}</select></Campo>
        <Campo label="Quantidade (dose)"><input type="number" inputMode="decimal" style={inputStyle} value={qtd} onChange={(e) => setQtd(e.target.value)} /></Campo>
        <Campo label="Unidade"><select style={inputStyle} value={unid} onChange={(e) => setUnid(e.target.value)}>{UNIDADES.map((u) => <option key={u}>{u}</option>)}</select></Campo>
        <Campo label="Responsável"><select style={inputStyle} defaultValue=""><option value="" disabled>Selecione…</option>{RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}</select></Campo>
        <Campo label="Observação" full><textarea style={{ ...inputStyle, minHeight: "3rem" }} /></Campo>
      </div>
      {produto && <EstoqueRestante estoque={estoque} produto={produto} quantidade={Number(qtd) || 0} />}
      <p style={nota}>Ao salvar, dá baixa da quantidade no estoque (por animal, ou multiplicada pelo efetivo dos lotes).</p>
      <SalvarEmBreve />
    </>
  );
}

function FormFinanceiro() {
  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Data"><input type="date" style={inputStyle} /></Campo>
        <Campo label="Tipo"><select style={inputStyle} defaultValue=""><option value="" disabled>Selecione…</option><option>Receita</option><option>Despesa</option></select></Campo>
        <Campo label="Conta gerencial"><input style={inputStyle} placeholder="ex.: Leite indústria" /></Campo>
        <Campo label="Valor (R$)"><input type="number" inputMode="decimal" style={inputStyle} /></Campo>
        <Campo label="Fornecedor / cliente"><input style={inputStyle} /></Campo>
        <Campo label="Centro de custo"><input style={inputStyle} /></Campo>
        <Campo label="Descrição" full><textarea style={{ ...inputStyle, minHeight: "3rem" }} /></Campo>
      </div>
      <SalvarEmBreve />
    </>
  );
}

function FormEstoque({ estoque }: { estoque: EstoqueItem[] }) {
  const [produto, setProduto] = useState("");
  const [mov, setMov] = useState("");
  const [qtd, setQtd] = useState("");
  const item = estoque.find((e) => e.nome === produto);
  const q = Number(qtd) || 0;
  const baixa = MOV_BAIXA.has(mov);
  const restante = item ? (item.quantidade ?? 0) + (baixa ? -q : q) : null;
  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Produto / medicamento">
          <select style={inputStyle} value={produto} onChange={(e) => setProduto(e.target.value)}>
            <option value="" disabled>Selecione…</option>
            {estoque.map((e) => <option key={e.nome} value={e.nome}>{e.nome}{e.quantidade != null ? ` (${e.quantidade} ${e.unidade || ""})` : ""}</option>)}
          </select>
        </Campo>
        <Campo label="Movimento">
          <select style={inputStyle} value={mov} onChange={(e) => setMov(e.target.value)}>
            <option value="" disabled>Selecione…</option>
            {MOVIMENTOS_ESTOQUE.map((m) => <option key={m}>{m}</option>)}
          </select>
        </Campo>
        <Campo label="Quantidade"><input type="number" inputMode="decimal" style={inputStyle} value={qtd} onChange={(e) => setQtd(e.target.value)} /></Campo>
        <Campo label="Unidade"><select style={inputStyle} defaultValue={item?.unidade || "unidade"}>{UNIDADES.map((u) => <option key={u}>{u}</option>)}</select></Campo>
        <Campo label="Data"><input type="date" style={inputStyle} /></Campo>
        <Campo label="Observação" full><textarea style={{ ...inputStyle, minHeight: "3rem" }} /></Campo>
      </div>
      {item && mov && (
        <p style={{ fontSize: "0.78rem", marginTop: "0.3rem" }}>
          {baixa ? "Baixa" : "Entrada"} · Estoque atual: <strong>{item.quantidade ?? 0} {item.unidade || ""}</strong> → depois:{" "}
          <strong style={{ color: (restante ?? 0) < 0 ? "var(--red)" : "var(--green-light)" }}>{restante} {item.unidade || ""}</strong>
          {(restante ?? 0) < 0 && <span style={{ color: "var(--red)" }}> (insuficiente!)</span>}
        </p>
      )}
      <SalvarEmBreve />
    </>
  );
}

const TIPOS = [
  { id: "animal", label: "Animal (ficha)", icon: Beef, desc: "Cadastro/atualização de um animal do rebanho." },
  { id: "servico", label: "Serviço / IA", icon: Heart, desc: "Inseminação, IATF ou cobertura — individual ou em lote." },
  { id: "diagnostico", label: "Diagnóstico de gestação", icon: Stethoscope, desc: "Resultado do toque / diagnóstico de prenhez." },
  { id: "parto", label: "Parto / nascimento", icon: Baby, desc: "Registro de parto, da cria e do manejo de colostro." },
  { id: "producao", label: "Controle leiteiro", icon: Milk, desc: "Pesagem de leite por vaca ou por lote." },
  { id: "sanidade", label: "Sanidade", icon: Syringe, desc: "Aplicação de medicamento / manejo sanitário." },
  { id: "financeiro", label: "Financeiro", icon: Wallet, desc: "Lançamento de receita ou despesa." },
  { id: "estoque", label: "Estoque", icon: Package, desc: "Entrada ou saída de item do estoque." },
];

export default function LancamentosPage() {
  const [sel, setSel] = useState("animal");
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
  const tipo = TIPOS.find((t) => t.id === sel)!;

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><ClipboardList size={22} style={{ color: "var(--dourado-light)" }} /> Lançamentos</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Entrada de dados direto no sistema — escolha o tipo e preencha.</p>
      </div>

      <div className="card mb-4" style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start", background: "rgba(94,26,46,0.18)" }}>
        <Info size={16} style={{ color: "var(--dourado-light)", marginTop: "0.15rem", flexShrink: 0 }} />
        <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
          <strong style={{ color: "var(--text)" }}>Rascunho funcional.</strong> Os selects já usam o rebanho real e os cálculos funcionam,
          mas <strong>nada é gravado ainda</strong> — o salvamento entra com o banco permanente + login. Me diga o que ajustar em cada tipo.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[240px_1fr] gap-4">
        <div className="card" style={{ padding: "0.5rem", alignSelf: "start" }}>
          <div className="space-y-1">
            {TIPOS.map((t) => {
              const Icon = t.icon; const ativo = t.id === sel;
              return (
                <button key={t.id} onClick={() => setSel(t.id)}
                  style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.55rem 0.7rem", borderRadius: "8px", cursor: "pointer", textAlign: "left",
                    border: "1px solid " + (ativo ? "var(--dourado)" : "transparent"), background: ativo ? "rgba(94,26,46,0.4)" : "transparent",
                    color: ativo ? "var(--dourado-light)" : "var(--text-muted)", fontSize: "0.85rem", fontWeight: ativo ? 700 : 500 }}>
                  <Icon size={16} /> {t.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="card">
          <div className="card-header mb-1 flex items-center gap-2"><tipo.icon size={14} /> {tipo.label}</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", margin: "0.4rem 0 1rem" }}>{tipo.desc}</p>
          {sel === "animal" && <FormAnimal lotes={lotes} />}
          {sel === "servico" && <FormServico animais={aptasServico} />}
          {sel === "diagnostico" && <FormDiagnostico animais={animais} ultServico={ultServico} />}
          {sel === "parto" && <FormParto animais={animais} />}
          {sel === "producao" && <FormControle animais={animais} lotesLact={lotesLact} />}
          {sel === "sanidade" && <FormSanidade animais={animais} lotes={lotes} estoque={estoque} produtos={produtosSanidade} />}
          {sel === "financeiro" && <FormFinanceiro />}
          {sel === "estoque" && <FormEstoque estoque={estoque} />}
        </div>
      </div>
    </div>
  );
}
