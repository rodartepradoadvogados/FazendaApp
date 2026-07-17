"use client";
import { useEffect, useMemo, useState } from "react";
import { Beef, Check, Eye } from "lucide-react";
import {
  fetchAnimais, criarAnimalFicha, atualizarAnimalFicha, fetchRacas, fetchGrausSangue,
  fetchEstoqueSemen, fetchTouros, type Touro,
} from "@/lib/api";
import { AnimalRow } from "./AnimalModal";
import { AnimalPicker } from "./AnimalPicker";
import { TouroPicker, type TouroPickerItem } from "./TouroPicker";
import { TouroDetalheModal } from "./TouroDetalheModal";
import { CAMPOS_NUMERICOS, parseDadosExtra } from "./CadastroTouros";

const CATEGORIAS_ANIMAL = ["Bezerra", "Novilha", "Vaca", "Touro", "Bezerro"];
// Fallback caso o cadastro (Configurações > Cadastro > Raças e grau de
// sangue) ainda não tenha sido carregado/semeado.
const GRAUS_SANGUE_FALLBACK = [
  "1/2 Holandês x Gir", "3/4 Holandês", "7/8 Holandês", "15/16 Holandês",
  "31/32 Holandês", "PCOD Holandês", "PO Holandês",
];
const RACAS_FALLBACK = ["Girolando", "Holandês", "Gir", "Outra"];

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };
const Campo = ({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) => (
  <div style={{ gridColumn: full ? "1 / -1" : undefined }}><label style={lbl}>{label}</label>{children}</div>
);
const Secao = ({ children }: { children: React.ReactNode }) => (
  <p style={{ fontSize: "0.72rem", fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--dourado-light)", margin: "1rem 0 0.5rem" }}>{children}</p>
);

type Ficha = {
  numero: string; nome: string; sisbov: string; sexo: string; raca: string; grau_sangue: string; categoria_abrev: string;
  grupo_primario: string; data_nasc: string; data_entrada: string; proprietario: string; valor: string;
  motivo_baixa: string; data_baixa: string; mae_numero: string; mae_nome: string; observacoes: string;
  pai_nome: string; pai_naab: string;
  avo_paterno_nome: string; avo_paterno_naab: string;
  bisavo_paterno_nome: string; bisavo_paterno_naab: string;
};
const fichaVazia: Ficha = {
  numero: "", nome: "", sisbov: "", sexo: "", raca: "Girolando", grau_sangue: "", categoria_abrev: "",
  grupo_primario: "", data_nasc: "", data_entrada: "", proprietario: "Jairo Nasser Quintiliano da Silva", valor: "",
  motivo_baixa: "", data_baixa: "", mae_numero: "", mae_nome: "", observacoes: "",
  pai_nome: "", pai_naab: "", avo_paterno_nome: "", avo_paterno_naab: "", bisavo_paterno_nome: "", bisavo_paterno_naab: "",
};

function paraPayload(f: Ficha) {
  const s = (v: string) => (v.trim() === "" ? null : v.trim());
  return {
    numero: f.numero.trim(), nome: s(f.nome), sisbov: s(f.sisbov), sexo: s(f.sexo), raca: s(f.raca),
    grau_sangue: s(f.grau_sangue),
    categoria_abrev: s(f.categoria_abrev), grupo_primario: s(f.grupo_primario),
    data_nasc: s(f.data_nasc), data_entrada: s(f.data_entrada), proprietario: s(f.proprietario),
    valor: f.valor.trim() === "" ? null : Number(f.valor),
    motivo_baixa: s(f.motivo_baixa), data_baixa: s(f.data_baixa),
    mae_numero: s(f.mae_numero), mae_nome: s(f.mae_nome), observacoes: s(f.observacoes),
    pai_nome: s(f.pai_nome), pai_naab: s(f.pai_naab),
    avo_paterno_nome: s(f.avo_paterno_nome), avo_paterno_naab: s(f.avo_paterno_naab),
    bisavo_paterno_nome: s(f.bisavo_paterno_nome), bisavo_paterno_naab: s(f.bisavo_paterno_naab),
  };
}

const fmt = (v?: number | null, dec = 0) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: dec, maximumFractionDigits: dec });

export default function CadastroAnimalForm() {
  const [modo, setModo] = useState<"novo" | "editar">("novo");
  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  const [numeroEdicao, setNumeroEdicao] = useState("");
  const [lotes, setLotes] = useState<string[]>([]);
  const [form, setForm] = useState<Ficha>(fichaVazia);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  const [racas, setRacas] = useState<string[]>(RACAS_FALLBACK);
  const [grausSangue, setGrausSangue] = useState<string[]>(GRAUS_SANGUE_FALLBACK);
  const [naab, setNaab] = useState<Touro[]>([]);
  const [estoqueSemen, setEstoqueSemen] = useState<TouroPickerItem[]>([]);
  const [detalheTouro, setDetalheTouro] = useState<{ titulo: string; campos: [string, string][] } | null>(null);

  useEffect(() => {
    fetchAnimais({ incluirMachos: true }).then((d) => {
      setAnimais(d);
      const grupos = Array.from(new Set(d.map((a: AnimalRow) => a.grupo_primario).filter(Boolean))) as string[];
      setLotes(grupos.sort());
    }).catch(() => {});
    fetchRacas().then((d) => {
      const ativas = d.filter((r: any) => r.ativo).map((r: any) => r.nome as string);
      if (ativas.length) setRacas(ativas);
    }).catch(() => {});
    fetchGrausSangue().then((d) => {
      const ativos = d.filter((g: any) => g.ativo).map((g: any) => g.nome as string);
      if (ativos.length) setGrausSangue(ativos);
    }).catch(() => {});
    fetchTouros().then(setNaab).catch(() => {});
    fetchEstoqueSemen().then((d) => setEstoqueSemen(
      d.map((e: any): TouroPickerItem => ({ naab: e.naab, nome: e.touro_nome, central: e.central, doses: e.doses }))
    )).catch(() => {});
  }, []);

  // Touros da fazenda (monta natural) + sêmen em estoque + catálogo NAAB, numa
  // única lista de busca — a genealogia (pai/avô/bisavô) pode vir de qualquer
  // uma dessas três fontes, buscável pelo nome de guerra ou código NAAB.
  const itensTouros: TouroPickerItem[] = useMemo(() => {
    const fazenda = (animais as any[])
      .filter((a) => a.sexo === "M" && a.nome)
      .map((a): TouroPickerItem => ({ nome: a.nome, naab: null }));
    const semen = estoqueSemen;
    const naabItens = naab.map((t): TouroPickerItem => ({ naab: t.naab, nome: t.nome || t.naab, central: t.central, raca: t.raca, tpi: t.tpi }));
    const vistos = new Set<string>();
    return [...fazenda, ...semen, ...naabItens].filter((t) => {
      const chave = `${t.naab || ""}|${t.nome.toLowerCase()}`;
      if (vistos.has(chave)) return false;
      vistos.add(chave);
      return true;
    });
  }, [animais, estoqueSemen, naab]);

  function abrirFichaTouro(nome: string, naabCodigo: string) {
    const touro = naab.find((t) => (t.naab || "").trim().toUpperCase() === naabCodigo.trim().toUpperCase())
      || naab.find((t) => (t.nome || "").trim().toLowerCase() === nome.trim().toLowerCase());
    if (!touro) {
      setDetalheTouro({ titulo: nome, campos: [["NAAB", naabCodigo || "—"]] });
      return;
    }
    const fixos: [string, string][] = [
      ["NAAB", touro.naab], ["Nome completo", touro.nome_completo || "—"],
      ["Central", touro.central || "—"], ["Raça", touro.raca || "—"],
      ...CAMPOS_NUMERICOS.map(({ chave, label }): [string, string] => [label, fmt(touro[chave] as number | null)]),
      ["Fonte", touro.fonte || "—"], ["Rodada da prova", touro.rodada_prova || "—"],
    ];
    const rotulosFixos = new Set(fixos.map(([r]) => r.trim().toLowerCase()));
    const extras = parseDadosExtra(touro.dados_extra).filter(([r]) => !rotulosFixos.has(r.trim().toLowerCase()));
    setDetalheTouro({ titulo: touro.nome || touro.naab, campos: [...fixos, ...extras] });
  }

  const escolherParaEditar = (numero: string) => {
    setNumeroEdicao(numero);
    const a = animais.find((x) => x.numero === numero) as any;
    if (!a) return;
    setForm({
      numero: a.numero, nome: a.nome || "", sisbov: a.sisbov || "", sexo: a.sexo || "", raca: a.raca || "",
      grau_sangue: a.grau_sangue || "",
      categoria_abrev: a.categoria_abrev || "", grupo_primario: a.grupo_primario || "",
      data_nasc: a.data_nasc || "", data_entrada: a.data_entrada || "", proprietario: a.proprietario || "",
      valor: a.valor?.toString() ?? "", motivo_baixa: a.motivo_baixa || "", data_baixa: a.data_baixa || "",
      mae_numero: a.mae_numero || "", mae_nome: a.mae_nome || "", observacoes: a.observacoes || "",
      pai_nome: a.pai_nome || "", pai_naab: a.pai_naab || "",
      avo_paterno_nome: a.avo_paterno_nome || "", avo_paterno_naab: a.avo_paterno_naab || "",
      bisavo_paterno_nome: a.bisavo_paterno_nome || "", bisavo_paterno_naab: a.bisavo_paterno_naab || "",
    });
  };

  const trocarModo = (m: "novo" | "editar") => {
    setModo(m); setErro(null); setSucesso(null);
    setForm(fichaVazia); setNumeroEdicao("");
  };

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!form.numero.trim()) { setErro("Número/brinco é obrigatório."); return; }
    setSalvando(true);
    try {
      const payload = paraPayload(form);
      if (modo === "novo") {
        await criarAnimalFicha(payload);
        setSucesso(`Animal ${form.numero} cadastrado com sucesso.`);
        setForm(fichaVazia);
      } else {
        await atualizarAnimalFicha(numeroEdicao, payload);
        setSucesso(`Ficha de ${numeroEdicao} atualizada com sucesso.`);
      }
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center gap-2"><Beef size={16} /> Ficha do animal</div>

      <div className="flex items-center gap-2 mb-4" style={{ flexWrap: "wrap" }}>
        {([["novo", "Novo animal"], ["editar", "Editar existente"]] as const).map(([k, t]) => (
          <button key={k} onClick={() => trocarModo(k)}
            style={{ fontSize: "0.78rem", padding: "0.35rem 0.8rem", borderRadius: "999px", cursor: "pointer",
              border: "1px solid " + (modo === k ? "var(--dourado)" : "var(--border)"),
              background: modo === k ? "var(--dourado)" : "transparent",
              color: modo === k ? "#1a1a1a" : "var(--text-muted)", fontWeight: modo === k ? 700 : 400 }}>{t}</button>
        ))}
      </div>

      {modo === "editar" && (
        <div className="mb-4" style={{ maxWidth: "420px" }}>
          <Campo label="Selecione o animal">
            <AnimalPicker animais={animais} value={numeroEdicao} onChange={escolherParaEditar} />
          </Campo>
          {numeroEdicao && (
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.4rem" }}>
              Para remover este animal do rebanho (venda, morte, descarte), use{" "}
              <a href="/rebanho?aba=baixar" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>
                Rebanho &gt; Baixar animal
              </a>{" "}
              — não edite os campos de baixa abaixo diretamente.
            </p>
          )}
        </div>
      )}

      {(modo === "novo" || numeroEdicao) && (
        <>
          <Secao>Identificação</Secao>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Campo label="Número / brinco">
              <input style={inputStyle} value={form.numero} disabled={modo === "editar"} onChange={(e) => setForm({ ...form, numero: e.target.value })} placeholder="ex.: 464" />
            </Campo>
            <Campo label="Nome"><input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} /></Campo>
            <Campo label="SISBOV"><input style={inputStyle} value={form.sisbov} onChange={(e) => setForm({ ...form, sisbov: e.target.value })} placeholder="105 ..." /></Campo>
            <Campo label="Sexo">
              <select style={inputStyle} value={form.sexo} onChange={(e) => setForm({ ...form, sexo: e.target.value })}>
                <option value="">Selecione…</option><option value="F">Fêmea</option><option value="M">Macho</option>
              </select>
            </Campo>
            <Campo label="Raça">
              <input style={inputStyle} list="racas-cadastro" value={form.raca}
                onChange={(e) => setForm({ ...form, raca: e.target.value })}
                placeholder="Selecione ou digite…" />
              <datalist id="racas-cadastro">{racas.map((r) => <option key={r} value={r} />)}</datalist>
            </Campo>
            <Campo label="Grau de sangue">
              <input style={inputStyle} list="graus-sangue" value={form.grau_sangue}
                onChange={(e) => setForm({ ...form, grau_sangue: e.target.value })}
                placeholder="Selecione ou digite…" />
              <datalist id="graus-sangue">{grausSangue.map((g) => <option key={g} value={g} />)}</datalist>
            </Campo>
            <Campo label="Categoria">
              <select style={inputStyle} value={form.categoria_abrev} onChange={(e) => setForm({ ...form, categoria_abrev: e.target.value })}>
                <option value="">Selecione…</option>{CATEGORIAS_ANIMAL.map((c) => <option key={c}>{c}</option>)}
              </select>
            </Campo>
            <Campo label="Lote">
              <select style={inputStyle} value={form.grupo_primario} onChange={(e) => setForm({ ...form, grupo_primario: e.target.value })}>
                <option value="">Selecione o lote…</option>{lotes.map((l) => <option key={l}>{l}</option>)}
              </select>
            </Campo>
          </div>

          <Secao>Origem e situação</Secao>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Campo label="Data de nascimento"><input type="date" style={inputStyle} value={form.data_nasc} onChange={(e) => setForm({ ...form, data_nasc: e.target.value })} /></Campo>
            <Campo label="Data de entrada na fazenda (se comprado)"><input type="date" style={inputStyle} value={form.data_entrada} onChange={(e) => setForm({ ...form, data_entrada: e.target.value })} /></Campo>
            <Campo label="Proprietário"><input style={inputStyle} value={form.proprietario} onChange={(e) => setForm({ ...form, proprietario: e.target.value })} /></Campo>
            <Campo label="Valor (R$)"><input type="number" inputMode="decimal" style={inputStyle} value={form.valor} onChange={(e) => setForm({ ...form, valor: e.target.value })} placeholder="ex.: 7000" /></Campo>
            <Campo label="Data de baixa (se houver)"><input type="date" style={inputStyle} value={form.data_baixa} onChange={(e) => setForm({ ...form, data_baixa: e.target.value })} /></Campo>
            <Campo label="Motivo de baixa"><input style={inputStyle} value={form.motivo_baixa} onChange={(e) => setForm({ ...form, motivo_baixa: e.target.value })} placeholder="venda, morte, descarte…" /></Campo>
          </div>
          {form.data_baixa && (
            <p style={{ fontSize: "0.76rem", color: "var(--amber)", marginTop: "0.4rem" }}>
              Ao salvar com data de baixa preenchida, o animal fica <strong>inativo</strong> no rebanho.
            </p>
          )}

          <Secao>Genealogia</Secao>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Campo label="Nome/Número da mãe"><input style={inputStyle} value={form.mae_numero} onChange={(e) => setForm({ ...form, mae_numero: e.target.value })} /></Campo>
            <Campo label="Nome da mãe"><input style={inputStyle} value={form.mae_nome} onChange={(e) => setForm({ ...form, mae_nome: e.target.value })} /></Campo>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3" style={{ marginTop: "0.75rem" }}>
            <Campo label="Nome/Número do pai">
              <div className="flex items-center gap-2">
                <div style={{ flex: 1 }}>
                  <TouroPicker
                    style={inputStyle} itens={itensTouros} value={form.pai_nome}
                    placeholder="Buscar touro da fazenda, sêmen em estoque ou NAAB…"
                    onChangeTexto={(v) => setForm({ ...form, pai_nome: v, pai_naab: "" })}
                    onSelecionar={(t) => setForm({ ...form, pai_nome: t.nome, pai_naab: t.naab || "" })}
                  />
                </div>
                {form.pai_nome && (
                  <button type="button" className="btn-ghost" title="Ver ficha completa do pai"
                    onClick={() => abrirFichaTouro(form.pai_nome, form.pai_naab)}
                    style={{ padding: "0.4rem", flexShrink: 0 }}>
                    <Eye size={16} />
                  </button>
                )}
              </div>
            </Campo>
          </div>
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
            Genealogia paterna (avô e bisavô): preenchida automaticamente quando o pai também está cadastrado
            com sua própria genealogia; senão, selecione manualmente abaixo.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3" style={{ marginTop: "0.4rem" }}>
            <Campo label="Avô paterno">
              <TouroPicker
                style={inputStyle} itens={itensTouros} value={form.avo_paterno_nome}
                placeholder="Selecionar (opcional)…"
                onChangeTexto={(v) => setForm({ ...form, avo_paterno_nome: v, avo_paterno_naab: "" })}
                onSelecionar={(t) => setForm({ ...form, avo_paterno_nome: t.nome, avo_paterno_naab: t.naab || "" })}
              />
            </Campo>
            <Campo label="Bisavô paterno">
              <TouroPicker
                style={inputStyle} itens={itensTouros} value={form.bisavo_paterno_nome}
                placeholder="Selecionar (opcional)…"
                onChangeTexto={(v) => setForm({ ...form, bisavo_paterno_nome: v, bisavo_paterno_naab: "" })}
                onSelecionar={(t) => setForm({ ...form, bisavo_paterno_nome: t.nome, bisavo_paterno_naab: t.naab || "" })}
              />
            </Campo>
          </div>

          <Secao>Outros</Secao>
          <div className="grid grid-cols-1 gap-3">
            <Campo label="Observações" full><textarea style={{ ...inputStyle, minHeight: "3rem" }} value={form.observacoes} onChange={(e) => setForm({ ...form, observacoes: e.target.value })} /></Campo>
          </div>

          {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
          {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
          <div className="flex items-center gap-3 mt-4">
            <button className="btn-primary flex items-center gap-2" onClick={salvar} disabled={salvando}>
              <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
            </button>
          </div>
        </>
      )}

      {detalheTouro && (
        <TouroDetalheModal titulo={detalheTouro.titulo} campos={detalheTouro.campos} onFechar={() => setDetalheTouro(null)} />
      )}
    </div>
  );
}
