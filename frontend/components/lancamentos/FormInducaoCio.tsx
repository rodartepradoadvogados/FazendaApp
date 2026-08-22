"use client";
import React, { useEffect, useMemo, useState } from "react";
import { registrarInducaoCio, fetchInducoesCio, excluirInducaoCio, type InducaoCioLancamento } from "@/lib/api";
import { VIAS_APLICACAO } from "@/lib/constants";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPickerModal } from "@/components/AnimalPickerModal";
import { LotePicker, opcoesLoteDeAnimais } from "@/components/LotePicker";
import { EstoquePicker, type EstoqueItemPicker } from "@/components/EstoquePicker";
import { TabBar } from "@/components/ui";
import { Campo, inputStyle, lbl, nota, codigoGrupo, type EstoqueItem } from "@/components/lancamentos/comumForms";
import { Trash2 } from "lucide-react";

const PRODUTO_PADRAO = "Cloprostenol";

export function FormInducaoCio({ animais, estoque, motivosInaptidao }: {
  animais: AnimalRow[]; estoque: EstoqueItem[];
  // numero -> motivo de inaptidão a serviço. Aqui é só informativo (a indução
  // de cio não cria Servico, então o backend não a trava), mas a mesma
  // marcação em cinza evita mandar hormônio numa bezerra por engano.
  motivosInaptidao?: Map<string, string>;
}) {
  const [vinculo, setVinculo] = useState<"animal" | "lote">("animal");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [lotesSelecionados, setLotesSelecionados] = useState<string[]>([]);
  const [selLote, setSelLote] = useState<Set<string>>(new Set());
  const toggle = (n: string) => setSel((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  const toggleLote = (n: string) => setSelLote((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });

  const codigosLotes = useMemo(
    () => Array.from(new Set(animais.map((a) => codigoGrupo(a.grupo_primario)).filter((c): c is string => !!c))).sort(),
    [animais]
  );
  const animaisDoLote = useMemo(() => {
    const cods = new Set(lotesSelecionados);
    return animais.filter((a) => { const c = codigoGrupo(a.grupo_primario); return c && cods.has(c); });
  }, [animais, lotesSelecionados]);
  useEffect(() => { setSelLote(new Set(animaisDoLote.map((a) => a.numero))); }, [lotesSelecionados.join("|")]); // eslint-disable-line react-hooks/exhaustive-deps
  const alvoFinal = useMemo(() => (vinculo === "lote" ? selLote : sel), [vinculo, selLote, sel]);

  const [dataAplicacao, setDataAplicacao] = useState(() => new Date().toISOString().slice(0, 10));
  const [produto, setProduto] = useState(PRODUTO_PADRAO);
  const [dose, setDose] = useState("");
  const [unidade, setUnidade] = useState("ml");
  const [via, setVia] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const { nomes: nomesResponsaveis } = usePessoasAtivas();
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const [historico, setHistorico] = useState<InducaoCioLancamento[]>([]);
  const carregarHistorico = () => fetchInducoesCio().then(setHistorico).catch(() => {});
  useEffect(() => { carregarHistorico(); }, []);

  const estoqueParaPicker: EstoqueItemPicker[] = useMemo(
    () => estoque.map((e) => ({ nome: e.nome, unidade: e.unidade ?? null, quantidade: e.quantidade ?? null, finalidade: e.finalidade ?? null })),
    [estoque]
  );

  async function salvar() {
    setErro(null); setSucesso(null);
    const alvo = Array.from(alvoFinal);
    if (!alvo.length) { setErro("Selecione ao menos uma matriz."); return; }
    if (!dataAplicacao) { setErro("Informe a data da aplicação."); return; }
    if (!produto) { setErro("Informe o produto (ex.: Cloprostenol / PGF2α)."); return; }
    setSalvando(true);
    try {
      const r = await registrarInducaoCio({
        numeros_matriz: alvo, data_aplicacao: dataAplicacao, produto,
        dose: dose ? Number(dose) : undefined, unidade: dose ? unidade : undefined,
        via: via || undefined, responsavel: responsavel || undefined, observacao: observacao || undefined,
      });
      setSucesso(`${r.aplicados} aplicação(ões) lançada(s) com sucesso.${r.avisos?.length ? " " + r.avisos.join(" ") : ""} Cio esperado em 2 a 5 dias — a Agenda vai lembrar de observar.`);
      setSel(new Set()); setLotesSelecionados([]); setObservacao("");
      carregarHistorico();
    } catch (e: any) {
      setErro(e.message || "Erro ao registrar indução de cio");
    } finally {
      setSalvando(false);
    }
  }

  async function excluir(id: number) {
    if (!confirm("Excluir este lançamento de indução de cio?")) return;
    try { await excluirInducaoCio(id); carregarHistorico(); } catch (e: any) { setErro(e.message); }
  }

  return (
    <>
      <p style={{ ...nota, marginLeft: 0, marginBottom: "0.6rem", display: "block" }}>
        Estímulo hormonal (não é IATF, não é diagnóstico) aplicado geralmente nos últimos dias do PEV para a
        vaca entrar em cio em 2 a 5 dias — gera histórico próprio e um lembrete "Observar cio" na Agenda,
        que some sozinho assim que uma inseminação for lançada para o animal.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
      <Campo label="Matriz(es) — animal(is) ou lote(s)" full>
        <TabBar<"animal" | "lote">
          abas={[
            { id: "animal", label: "Animal(is)", title: "Selecionar matrizes individualmente" },
            { id: "lote", label: "Lote(s)", title: "Selecionar um ou mais lotes" },
          ]}
          ativa={vinculo}
          onChange={setVinculo}
        />
        {vinculo === "animal" ? (
          <AnimalPickerModal
            animais={animais}
            selecionados={sel} onToggle={toggle}
            titulo="Escolher matriz(es)"
            motivosInaptidao={motivosInaptidao}
            colunas={[
              { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
              { header: "Lote", render: (a) => a.grupo_primario || "—" },
            ]}
          />
        ) : (
          <div style={{ marginTop: "0.5rem" }}>
            <LotePicker
              opcoes={opcoesLoteDeAnimais(animais, codigosLotes)}
              selecionados={lotesSelecionados}
              onChange={setLotesSelecionados}
              placeholder="Selecionar lote(s)…"
            />
            {lotesSelecionados.length > 0 && (
              <div style={{ marginTop: "0.6rem" }}>
                <AnimalPickerModal
                  animais={animaisDoLote} selecionados={selLote} onToggle={toggleLote}
                  titulo="Ajustar animais do(s) lote(s) selecionado(s)"
                  placeholder="Ajustar animais do(s) lote(s)…"
                  colunas={[
                    { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                    { header: "Lote", render: (a) => a.grupo_primario || "—" },
                  ]}
                />
              </div>
            )}
          </div>
        )}
      </Campo>

      {alvoFinal.size > 0 && (
        <div className="mt-3" style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", alignItems: "center" }}>
          <span style={{ fontSize: "0.78rem", color: "var(--text-muted)", fontWeight: 600 }}>
            {alvoFinal.size} matriz(es) selecionada(s):
          </span>
          {Array.from(alvoFinal).sort().map((n) => (
            <span key={n} style={{
              fontSize: "0.76rem", background: "var(--surface-2)", border: "1px solid var(--border)",
              borderRadius: "999px", padding: "0.15rem 0.6rem", fontWeight: 600,
            }}>
              {n}
            </span>
          ))}
        </div>
      )}

      {historico.length > 0 && (
        <div className="mt-4">
          <label style={lbl}>Últimas induções de cio lançadas</label>
          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            <table className="fazenda-table">
              <thead><tr><th>Matriz</th><th>Data</th><th>Produto</th><th>Dose</th><th>Via</th><th>Responsável</th><th></th></tr></thead>
              <tbody>
                {historico.slice(0, 10).map((h) => (
                  <tr key={h.id}>
                    <td style={{ fontWeight: 700 }}>{h.numero_matriz}</td>
                    <td>{h.data_aplicacao || "—"}</td>
                    <td>{h.produto}</td>
                    <td>{h.dose != null ? `${h.dose} ${h.unidade || ""}` : "—"}</td>
                    <td>{h.via || "—"}</td>
                    <td>{h.responsavel || "—"}</td>
                    <td>
                      <button title="Excluir" onClick={() => excluir(h.id)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)" }}>
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      </div>

      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Data da aplicação"><input type="date" style={inputStyle} value={dataAplicacao} onChange={(e) => setDataAplicacao(e.target.value)} /></Campo>
        <Campo label="Produto"><EstoquePicker itens={estoqueParaPicker} value={produto} onChange={setProduto} placeholder="Cloprostenol / PGF2α…" /></Campo>
        <Campo label="Dose (opcional)"><input type="number" inputMode="decimal" style={inputStyle} value={dose} onChange={(e) => setDose(e.target.value)} /></Campo>
        <Campo label="Unidade"><select style={inputStyle} value={unidade} onChange={(e) => setUnidade(e.target.value)} disabled={!dose}><option value="ml">ml</option><option value="unidade">unidade</option><option value="dose">dose</option></select></Campo>
        <Campo label="Via">
          <select style={inputStyle} value={via} onChange={(e) => setVia(e.target.value)}>
            <option value="">Selecione…</option>
            {VIAS_APLICACAO.map((o) => <option key={o}>{o}</option>)}
          </select>
        </Campo>
        <Campo label="Responsável">
          <select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
            <option value="">Selecione…</option>{nomesResponsaveis.map((r) => <option key={r}>{r}</option>)}
          </select>
        </Campo>
        <Campo label="Observação (opcional)" full><input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
      </div>

      <p style={nota}>Se dose e unidade forem informadas, dá baixa no estoque do produto ao salvar.</p>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
      </div>
      </div>
    </>
  );
}
