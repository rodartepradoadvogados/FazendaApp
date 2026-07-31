"use client";
import React, { Fragment, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { Plus, Trash2 } from "lucide-react";
import { encerrarDieta, fetchAlimentos, fetchComparativoDieta, fetchDietas, formatDate, registrarRealDieta } from "@/lib/api";
import { SecaoRecolhivel } from "@/components/ui";
import { TabelaNutricionalBotao } from "@/components/TabelaNutricional";
import { Campo, inputStyle, lbl, nota } from "@/components/lancamentos/comumForms";
import { UNIDADES } from "@/components/lancamentos/_shared";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
const CadastrarNovaDieta = dynamic(() => import("@/components/CadastroAlimentacao").then((m) => m.CadastrarNovaDieta), { ssr: false });

type ItemDieta = { alimento: string; quantidade: string; unidade: string };
const itemDietaVazio = (): ItemDieta => ({ alimento: "", quantidade: "", unidade: "kg" });

type DietaLote = {
  id: number; lote: number; responsavel: string | null; data_abertura: string;
  data_prevista_encerramento: string | null; data_efetivo_encerramento: string | null;
  observacao: string | null; ativa: boolean;
  itens_programados: { alimento: string; quantidade: number; unidade: string }[];
};
type ItemComparativo = { alimento: string; unidade: string; programado: number; real_total: number; real_dias: number; real_media_dia: number | null };

export function FormAlimentacaoDieta() {
  const [dietas, setDietas] = useState<DietaLote[] | null>(null);
  const [alimentosCadastro, setAlimentosCadastro] = useState<string[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  // Encerrar / registrar real / comparativo
  const [encerrando, setEncerrando] = useState<number | null>(null);
  const [dataEncerramento, setDataEncerramento] = useState(() => new Date().toISOString().slice(0, 10));
  const [registrando, setRegistrando] = useState<number | null>(null);
  const [dataReal, setDataReal] = useState(() => new Date().toISOString().slice(0, 10));
  const [itensReal, setItensReal] = useState<ItemDieta[]>([itemDietaVazio()]);
  const [comparandoId, setComparandoId] = useState<number | null>(null);
  const [comparativo, setComparativo] = useState<ItemComparativo[] | null>(null);

  const ordDietas = useOrdenacao(dietas ?? []);

  const carregar = () => fetchDietas().then(setDietas).catch((e) => setErro(e.message));
  useEffect(() => {
    carregar();
    fetchAlimentos().then((d) => setAlimentosCadastro(d.filter((a) => a.ativo !== false).map((a) => a.nome))).catch(() => {});
  }, []);

  // Vindo da Agenda (link "Ir para Dieta" do evento de análise de encerramento)
  // — abre direto a seção de encerrar a dieta ativa daquele lote.
  useEffect(() => {
    if (!dietas) return;
    const lote = new URLSearchParams(window.location.search).get("lote");
    if (!lote) return;
    const ativa = dietas.find((d) => d.lote === Number(lote) && d.ativa);
    if (ativa) setEncerrando(ativa.id);
  }, [dietas]);

  const atualizarItemReal = (idx: number, patch: Partial<ItemDieta>) => setItensReal((p) => { const n = [...p]; n[idx] = { ...n[idx], ...patch }; return n; });
  const acrescentarItemReal = () => setItensReal((p) => [...p, itemDietaVazio()]);
  const removerItemReal = (idx: number) => setItensReal((p) => (p.length > 1 ? p.filter((_, i) => i !== idx) : p));

  async function confirmarEncerramento(dieta: DietaLote) {
    setErro(null); setSucesso(null);
    try {
      await encerrarDieta(dieta.id, dataEncerramento);
      setEncerrando(null);
      setSucesso(`Dieta do lote ${dieta.lote} encerrada. Para lançar uma nova, use "Cadastrar nova dieta" acima.`);
      carregar();
    } catch (e: any) {
      setErro(e.message || "Erro ao encerrar dieta");
    }
  }

  async function salvarReal(dietaId: number) {
    setErro(null); setSucesso(null);
    const itensValidos = itensReal.filter((i) => i.alimento && Number(i.quantidade) > 0 && i.unidade);
    if (!itensValidos.length) { setErro("Adicione ao menos um alimento com quantidade e unidade."); return; }
    try {
      await registrarRealDieta(dietaId, {
        data: dataReal, itens: itensValidos.map((i) => ({ alimento: i.alimento, quantidade: Number(i.quantidade), unidade: i.unidade })),
      });
      setSucesso("Real oferecido registrado com sucesso.");
      setRegistrando(null); setItensReal([itemDietaVazio()]);
      if (comparandoId === dietaId) abrirComparativo(dietaId);
    } catch (e: any) {
      setErro(e.message || "Erro ao registrar o real oferecido");
    }
  }

  const abrirComparativo = (dietaId: number) => {
    setComparandoId((atual) => (atual === dietaId ? null : dietaId));
    if (comparandoId !== dietaId) {
      fetchComparativoDieta(dietaId).then((d) => setComparativo(d.itens)).catch((e) => setErro(e.message));
    }
  };

  return (
    <>
      {/* Mesma tela de Configurações > Cadastro > Alimentação — quantidade só
          por animal/dia, cálculo automático de lote/dia e lote/trato (nota
          explicativa dentro do próprio componente). */}
      <div className="flex justify-end mb-2"><TabelaNutricionalBotao /></div>
      <CadastrarNovaDieta onSalvo={carregar} />

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}

      {dietas && (
        <div className="mt-4">
          <SecaoRecolhivel
            titulo="Dietas lançadas"
            defaultAberta={false}
            descricao="Histórico de dietas por lote — comparativo, real oferecido e encerramento"
            badge={<span style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700 }}>{dietas.length}</span>}
          >
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead>
                <tr>
                  <ThOrdenavel label="Lote" campo="lote" coluna={ordDietas.coluna} dir={ordDietas.dir} ordenar={ordDietas.ordenar} />
                  <ThOrdenavel label="Responsável" campo="responsavel" coluna={ordDietas.coluna} dir={ordDietas.dir} ordenar={ordDietas.ordenar} />
                  <ThOrdenavel label="Abertura" campo="data_abertura" coluna={ordDietas.coluna} dir={ordDietas.dir} ordenar={ordDietas.ordenar} />
                  <ThOrdenavel label="Prev. encerramento" campo="data_prevista_encerramento" coluna={ordDietas.coluna} dir={ordDietas.dir} ordenar={ordDietas.ordenar} />
                  <ThOrdenavel label="Situação" campo="ativa" coluna={ordDietas.coluna} dir={ordDietas.dir} ordenar={ordDietas.ordenar} />
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {ordDietas.linhasOrdenadas.map((d) => (
                  <Fragment key={d.id}>
                    <tr>
                      <td style={{ fontWeight: 700 }}>{d.lote}</td>
                      <td style={{ fontSize: "0.78rem" }}>{d.responsavel || "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{formatDate(d.data_abertura)}</td>
                      <td style={{ fontSize: "0.78rem" }}>{d.data_prevista_encerramento ? formatDate(d.data_prevista_encerramento) : "—"}</td>
                      <td>
                        <span style={{ fontSize: "0.72rem", fontWeight: 700, color: d.ativa ? "var(--green-light)" : "var(--text-muted)" }}>
                          {d.ativa ? "Ativa" : `Encerrada em ${formatDate(d.data_efetivo_encerramento!)}`}
                        </span>
                      </td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => abrirComparativo(d.id)}>Comparativo</button>
                        {d.ativa && <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => setRegistrando(registrando === d.id ? null : d.id)}>Registrar real</button>}
                        {d.ativa && <button className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)" }} onClick={() => setEncerrando(encerrando === d.id ? null : d.id)}>Encerrar</button>}
                      </td>
                    </tr>
                    {encerrando === d.id && (
                      <tr><td colSpan={6} style={{ padding: 0 }}>
                        <div style={{ background: "var(--surface-2)", padding: "0.75rem", display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
                          <label style={lbl}>Data de encerramento efetivo</label>
                          <input type="date" style={{ ...inputStyle, width: "auto" }} value={dataEncerramento} onChange={(e) => setDataEncerramento(e.target.value)} />
                          <button className="btn-primary" style={{ fontSize: "0.75rem" }} onClick={() => confirmarEncerramento(d)}>Confirmar encerramento</button>
                          <button className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => setEncerrando(null)}>Cancelar</button>
                        </div>
                      </td></tr>
                    )}
                    {registrando === d.id && (
                      <tr><td colSpan={6} style={{ padding: 0 }}>
                        <div style={{ background: "var(--surface-2)", padding: "0.75rem" }}>
                          <div className="flex items-center gap-2 mb-2">
                            <label style={lbl}>Data</label>
                            <input type="date" style={{ ...inputStyle, width: "auto" }} value={dataReal} onChange={(e) => setDataReal(e.target.value)} />
                          </div>
                          {itensReal.map((item, idx) => (
                            <div key={idx} className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2" style={{ alignItems: "end" }}>
                              <Campo label="Alimento">
                                <select style={inputStyle} value={item.alimento} onChange={(e) => atualizarItemReal(idx, { alimento: e.target.value })}>
                                  <option value="">Selecione...</option>
                                  {alimentosCadastro.map((a) => <option key={a} value={a}>{a}</option>)}
                                </select>
                              </Campo>
                              <Campo label="Quantidade"><input type="number" inputMode="decimal" style={inputStyle} value={item.quantidade} onChange={(e) => atualizarItemReal(idx, { quantidade: e.target.value })} /></Campo>
                              <Campo label="Unidade">
                                <select style={inputStyle} value={item.unidade} onChange={(e) => atualizarItemReal(idx, { unidade: e.target.value })}>{UNIDADES.map((u) => <option key={u}>{u}</option>)}</select>
                              </Campo>
                              {itensReal.length > 1 && <button onClick={() => removerItemReal(idx)} title="Remover este alimento" aria-label="Remover este alimento" className="btn-ghost" style={{ color: "var(--red)", fontSize: "0.72rem" }}><Trash2 size={13} /></button>}
                            </div>
                          ))}
                          <button onClick={acrescentarItemReal} className="btn-ghost flex items-center gap-1" style={{ fontSize: "0.75rem" }}><Plus size={13} /> Acrescentar alimento</button>
                          <div className="flex items-center gap-2 mt-2">
                            <button className="btn-primary" style={{ fontSize: "0.75rem" }} onClick={() => salvarReal(d.id)}>Salvar real oferecido</button>
                            <button className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => setRegistrando(null)}>Cancelar</button>
                          </div>
                        </div>
                      </td></tr>
                    )}
                    {comparandoId === d.id && comparativo && (
                      <tr><td colSpan={6} style={{ padding: 0 }}>
                        <div style={{ background: "var(--surface-2)", padding: "0.75rem" }}>
                          <table className="fazenda-table" style={{ margin: 0 }}>
                            <thead><tr><th>Alimento</th><th style={{ textAlign: "right" }}>Programado (dia)</th><th style={{ textAlign: "right" }}>Real (total)</th><th style={{ textAlign: "right" }}>Dias registrados</th><th style={{ textAlign: "right" }}>Real (média/dia)</th></tr></thead>
                            <tbody>
                              {comparativo.map((c) => (
                                <tr key={c.alimento}>
                                  <td style={{ fontWeight: 700 }}>{c.alimento}</td>
                                  <td style={{ textAlign: "right" }}>{c.programado} {c.unidade}</td>
                                  <td style={{ textAlign: "right" }}>{c.real_total} {c.unidade}</td>
                                  <td style={{ textAlign: "right" }}>{c.real_dias}</td>
                                  <td style={{ textAlign: "right", fontWeight: 600, color: c.real_media_dia != null && c.real_media_dia > c.programado ? "var(--amber)" : "var(--green-light)" }}>
                                    {c.real_media_dia != null ? `${c.real_media_dia} ${c.unidade}` : "—"}
                                  </td>
                                </tr>
                              ))}
                              {!comparativo.length && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Sem itens.</td></tr>}
                            </tbody>
                          </table>
                        </div>
                      </td></tr>
                    )}
                  </Fragment>
                ))}
                {!dietas.length && <tr><td colSpan={6} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhuma dieta lançada ainda.</td></tr>}
              </tbody>
            </table>
          </div>
          </SecaoRecolhivel>
        </div>
      )}
    </>
  );
}

