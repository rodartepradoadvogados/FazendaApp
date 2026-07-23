"use client";
import { useEffect, useState } from "react";
import { Building2, Plus, Check, Ban, Upload, Trash2, FileText, AlertTriangle, ShieldCheck, Users, UserPlus } from "lucide-react";
import {
  fetchFazendas, criarFazenda, fetchContratoFazenda, definirContratoFazenda, aprovarContratoFazenda,
  suspenderContratoFazenda, fetchPlanosCatalogo, fetchAnexosContrato, anexarContrato, excluirAnexoContrato,
  urlAnexoContrato, fetchUsuariosVinculados, vincularUsuarioFazenda, desvincularUsuarioFazenda,
  type Fazenda, type ContratoFazenda, type PlanoCatalogo, type PlanoNome, type ModuloComercial,
  type AnexoContrato, type UsuarioVinculado,
} from "@/lib/api";

const inp: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem" };
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

const NOME_MODULO: Record<ModuloComercial, string> = {
  rebanho: "Rebanho", reprodutivo: "Reprodutivo", produtivo: "Produtivo", sanitario: "Sanitário",
  financeiro: "Financeiro (básico)", planejamento: "Planejamento", pedidos: "Pedidos", estoque: "Estoque",
  alimentacao: "Alimentação", agricultura: "Agricultura/Plantio", consultor: "Consultor (Diamond)",
};

function formatarBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
function formatarData(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function StatusBadge({ status }: { status: ContratoFazenda["status"] }) {
  const cfg = {
    ativo: { cor: "var(--green-light)", label: "Ativo" },
    aguardando_aprovacao: { cor: "var(--dourado)", label: "Aguardando aprovação" },
    suspenso: { cor: "var(--red)", label: "Suspenso" },
  }[status || "aguardando_aprovacao"] || { cor: "var(--text-muted)", label: "Sem contrato" };
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.75rem", fontWeight: 700, color: cfg.cor, border: `1px solid ${cfg.cor}`, borderRadius: "999px", padding: "0.2rem 0.7rem" }}>
      {cfg.label}
    </span>
  );
}

export default function FazendasAdmin() {
  const [fazendas, setFazendas] = useState<Fazenda[] | null>(null);
  const [selecionada, setSelecionada] = useState<number | null>(null);
  const [catalogo, setCatalogo] = useState<Record<PlanoNome, PlanoCatalogo> | null>(null);
  const [contrato, setContrato] = useState<ContratoFazenda | null>(null);
  const [anexos, setAnexos] = useState<AnexoContrato[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [planoEscolhido, setPlanoEscolhido] = useState<PlanoNome | "custom">("standard");
  const [modulosCustom, setModulosCustom] = useState<Record<ModuloComercial, number | null>>({} as any);
  const [salvando, setSalvando] = useState(false);
  const [aprovando, setAprovando] = useState(false);
  const [enviandoAnexo, setEnviandoAnexo] = useState(false);

  const [abrirNova, setAbrirNova] = useState(false);
  const [novoNome, setNovoNome] = useState("");
  const [novaCidade, setNovaCidade] = useState("");
  const [novaUf, setNovaUf] = useState("");
  const [criando, setCriando] = useState(false);

  const [usuarios, setUsuarios] = useState<UsuarioVinculado[] | null>(null);
  const [novoUsername, setNovoUsername] = useState("");
  const [novoPapel, setNovoPapel] = useState<"funcionario" | "contratante" | "consultor">("funcionario");
  const [vinculando, setVinculando] = useState(false);

  function carregarFazendas() {
    fetchFazendas().then(setFazendas).catch((e) => setErro(e.message));
  }
  useEffect(carregarFazendas, []);
  useEffect(() => { fetchPlanosCatalogo().then(setCatalogo).catch((e) => setErro(e.message)); }, []);

  function carregarContrato(fazendaId: number) {
    fetchContratoFazenda(fazendaId).then((ct) => {
      setContrato(ct);
      if (ct.plano) setPlanoEscolhido(ct.plano);
      else {
        setPlanoEscolhido("custom");
        const mapa: Record<string, number> = {};
        ct.modulos.forEach((m) => { mapa[m.modulo] = m.preco; });
        setModulosCustom(mapa as any);
      }
    }).catch((e) => setErro(e.message));
    fetchAnexosContrato(fazendaId).then(setAnexos).catch((e) => setErro(e.message));
    fetchUsuariosVinculados(fazendaId).then(setUsuarios).catch((e) => setErro(e.message));
  }

  function selecionar(id: number) {
    setSelecionada(id);
    setErro(null);
    setMsg(null);
    carregarContrato(id);
  }

  const temModuloConsultor = contrato?.modulos.some((m) => m.modulo === "consultor" && m.ativo) ?? false;

  async function vincular() {
    if (selecionada == null || !novoUsername.trim()) { setErro("Informe o usuário (username)."); return; }
    setVinculando(true); setErro(null); setMsg(null);
    try {
      await vincularUsuarioFazenda(selecionada, {
        username: novoUsername.trim(),
        contratante: novoPapel === "contratante",
        consultor: novoPapel === "consultor",
      });
      setNovoUsername("");
      fetchUsuariosVinculados(selecionada).then(setUsuarios);
      setMsg("Usuário vinculado.");
    } catch (e: any) { setErro(e.message); } finally { setVinculando(false); }
  }

  async function desvincular(usuarioId: number) {
    if (selecionada == null) return;
    setErro(null);
    try {
      await desvincularUsuarioFazenda(selecionada, usuarioId);
      fetchUsuariosVinculados(selecionada).then(setUsuarios);
    } catch (e: any) { setErro(e.message); }
  }

  async function criarNovaFazenda() {
    if (!novoNome.trim()) { setErro("Nome é obrigatório."); return; }
    setCriando(true);
    setErro(null);
    try {
      const f = await criarFazenda({ nome: novoNome.trim(), cidade: novaCidade.trim() || undefined, uf: novaUf.trim() || undefined });
      setAbrirNova(false); setNovoNome(""); setNovaCidade(""); setNovaUf("");
      carregarFazendas();
      selecionar(f.id);
    } catch (e: any) { setErro(e.message); } finally { setCriando(false); }
  }

  async function salvarContrato() {
    if (selecionada == null) return;
    setSalvando(true); setErro(null); setMsg(null);
    try {
      const dados = planoEscolhido === "custom"
        ? { plano: null, modulos: Object.entries(modulosCustom).filter(([, v]) => v != null).map(([modulo, preco]) => ({ modulo: modulo as ModuloComercial, preco: preco || 0 })) }
        : { plano: planoEscolhido, modulos: [] };
      const ct = await definirContratoFazenda(selecionada, dados);
      setContrato(ct);
      setMsg("Contrato atualizado. Lembre de aprovar/fechar para liberar os módulos.");
    } catch (e: any) { setErro(e.message); } finally { setSalvando(false); }
  }

  async function aprovar() {
    if (selecionada == null) return;
    setAprovando(true); setErro(null); setMsg(null);
    try {
      const ct = await aprovarContratoFazenda(selecionada);
      setContrato(ct);
      setMsg("Contrato aprovado e fechado — os módulos já estão liberados para a fazenda.");
    } catch (e: any) { setErro(e.message); } finally { setAprovando(false); }
  }

  async function suspender() {
    if (selecionada == null) return;
    setAprovando(true); setErro(null); setMsg(null);
    try {
      const ct = await suspenderContratoFazenda(selecionada);
      setContrato(ct);
      setMsg("Fazenda suspensa — nenhum módulo fica acessível até reaprovar.");
    } catch (e: any) { setErro(e.message); } finally { setAprovando(false); }
  }

  async function enviarAnexo(file: File) {
    if (selecionada == null) return;
    setEnviandoAnexo(true); setErro(null);
    try {
      await anexarContrato(selecionada, file);
      fetchAnexosContrato(selecionada).then(setAnexos);
    } catch (e: any) { setErro(e.message); } finally { setEnviandoAnexo(false); }
  }

  async function excluirAnexo(anexoId: number) {
    if (selecionada == null) return;
    try {
      await excluirAnexoContrato(anexoId);
      fetchAnexosContrato(selecionada).then(setAnexos);
    } catch (e: any) { setErro(e.message); }
  }

  const modulosDoPlano = planoEscolhido !== "custom" && catalogo ? catalogo[planoEscolhido]?.modulos || [] : [];

  return (
    <div className="animate-in">
      <h3 className="text-lg font-bold flex items-center gap-2 mb-1"><Building2 size={18} style={{ color: "var(--dourado)" }} /> Fazendas e contratos</h3>
      <p style={{ color: "var(--text-muted)", fontSize: "0.82rem", marginBottom: "1rem" }}>
        Cada fazenda contrata um plano (ou um mix de módulos sob medida). Nada libera — nem Rebanho — até você aprovar
        e fechar o contrato aqui.
      </p>

      {erro && <div className="alert-critico mb-3"><AlertTriangle size={16} /><span>{erro}</span></div>}
      {msg && (
        <div className="mb-3 flex items-center gap-2" style={{ background: "rgba(45,138,86,0.15)", border: "1px solid var(--green-light)", borderRadius: "8px", padding: "0.6rem 1rem", color: "var(--green-light)", fontSize: "0.82rem" }}>
          <Check size={15} /><span>{msg}</span>
        </div>
      )}

      <div className="flex gap-4" style={{ flexWrap: "wrap", alignItems: "flex-start" }}>
        <div className="card" style={{ minWidth: "220px", flex: "0 0 240px" }}>
          <div className="card-header mb-2 flex items-center justify-between">
            <span>Fazendas</span>
            <button onClick={() => setAbrirNova((v) => !v)} title="Cadastrar fazenda nova" style={{ background: "transparent", border: "none", color: "var(--dourado-light)", cursor: "pointer" }}>
              <Plus size={16} />
            </button>
          </div>
          {abrirNova && (
            <div className="mb-3" style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
              <input placeholder="Nome" style={inp} value={novoNome} onChange={(e) => setNovoNome(e.target.value)} />
              <input placeholder="Cidade (opcional)" style={inp} value={novaCidade} onChange={(e) => setNovaCidade(e.target.value)} />
              <input placeholder="UF (opcional)" style={inp} value={novaUf} onChange={(e) => setNovaUf(e.target.value)} />
              <button onClick={criarNovaFazenda} disabled={criando} className="btn-primary" style={{ fontSize: "0.78rem", padding: "0.35rem 0.7rem" }}>
                {criando ? "Criando…" : "Cadastrar"}
              </button>
            </div>
          )}
          {!fazendas ? <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Carregando…</p> : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
              {fazendas.map((f) => (
                <button key={f.id} onClick={() => selecionar(f.id)}
                  style={{ textAlign: "left", padding: "0.5rem 0.7rem", borderRadius: "6px", cursor: "pointer",
                    border: "1px solid " + (selecionada === f.id ? "var(--dourado)" : "var(--border)"),
                    background: selecionada === f.id ? "rgba(212,160,23,0.12)" : "transparent", color: "var(--text)", fontSize: "0.83rem" }}>
                  <div style={{ fontWeight: 600 }}>{f.nome}</div>
                  {(f.cidade || f.uf) && <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{[f.cidade, f.uf].filter(Boolean).join(" / ")}</div>}
                </button>
              ))}
            </div>
          )}
        </div>

        {selecionada != null && contrato && (
          <div className="card" style={{ flex: "1 1 420px", minWidth: "360px" }}>
            <div className="card-header mb-3 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
              <span>Contrato</span>
              <StatusBadge status={contrato.status} />
            </div>

            <label style={lbl}>Plano</label>
            <div className="flex flex-wrap gap-2 mb-3">
              {(["standard", "silver", "gold", "diamond"] as const).map((p) => (
                <label key={p} style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.8rem", cursor: "pointer",
                  border: "1px solid " + (planoEscolhido === p ? "var(--dourado)" : "var(--border)"), borderRadius: "6px", padding: "0.35rem 0.6rem",
                  background: planoEscolhido === p ? "rgba(212,160,23,0.12)" : "transparent" }}>
                  <input type="radio" name="plano" checked={planoEscolhido === p} onChange={() => setPlanoEscolhido(p)} />
                  {catalogo?.[p]?.nome || p} — R$ {catalogo?.[p]?.preco.toFixed(2) ?? "—"}/mês
                </label>
              ))}
              <label style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.8rem", cursor: "pointer",
                border: "1px solid " + (planoEscolhido === "custom" ? "var(--dourado)" : "var(--border)"), borderRadius: "6px", padding: "0.35rem 0.6rem",
                background: planoEscolhido === "custom" ? "rgba(212,160,23,0.12)" : "transparent" }}>
                <input type="radio" name="plano" checked={planoEscolhido === "custom"} onChange={() => setPlanoEscolhido("custom")} />
                Sob medida
              </label>
            </div>

            {planoEscolhido !== "custom" ? (
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
                Módulos inclusos: {modulosDoPlano.map((m) => NOME_MODULO[m]).join(", ")}.
              </p>
            ) : (
              <div className="mb-3" style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "0.4rem 0.8rem", alignItems: "center" }}>
                {(Object.keys(NOME_MODULO) as ModuloComercial[]).map((m) => (
                  <label key={m} style={{ display: "contents" }}>
                    <span style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem" }}>
                      <input type="checkbox" checked={modulosCustom[m] != null} disabled={m === "rebanho"}
                        onChange={(e) => setModulosCustom((s) => ({ ...s, [m]: e.target.checked ? (s[m] ?? 0) : null }))} />
                      {NOME_MODULO[m]}
                    </span>
                    <input type="number" min={0} step="0.01" placeholder="R$" style={{ ...inp, width: "6rem" }}
                      disabled={modulosCustom[m] == null} value={modulosCustom[m] ?? ""}
                      onChange={(e) => setModulosCustom((s) => ({ ...s, [m]: e.target.value === "" ? 0 : Number(e.target.value) }))} />
                  </label>
                ))}
              </div>
            )}

            <div className="flex items-center gap-2 mb-4" style={{ flexWrap: "wrap" }}>
              <button onClick={salvarContrato} disabled={salvando} className="btn-primary" style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem" }}>
                {salvando ? "Salvando…" : "Salvar módulos/plano"}
              </button>
              {contrato.status !== "ativo" ? (
                <button onClick={aprovar} disabled={aprovando}
                  style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem", borderRadius: "6px", border: "1px solid var(--green-light)", background: "transparent", color: "var(--green-light)", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                  <ShieldCheck size={14} /> {aprovando ? "Aprovando…" : "Aprovar/Fechar contrato"}
                </button>
              ) : (
                <button onClick={suspender} disabled={aprovando}
                  style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem", borderRadius: "6px", border: "1px solid var(--red)", background: "transparent", color: "var(--red)", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                  <Ban size={14} /> {aprovando ? "Suspendendo…" : "Suspender"}
                </button>
              )}
            </div>

            <div className="card-header mb-2">Contrato assinado (anexos)</div>
            <label style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.78rem", padding: "0.35rem 0.7rem", borderRadius: "6px", border: "1px solid var(--border)", cursor: "pointer", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
              <Upload size={13} /> {enviandoAnexo ? "Enviando…" : "Anexar PDF/imagem"}
              <input type="file" accept="application/pdf,image/*" style={{ display: "none" }} disabled={enviandoAnexo}
                onChange={(e) => { const f = e.target.files?.[0]; if (f) enviarAnexo(f); e.target.value = ""; }} />
            </label>
            {anexos && anexos.length > 0 && (
              <ul style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                {anexos.map((a) => (
                  <li key={a.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", fontSize: "0.8rem", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.6rem" }}>
                    <a href={urlAnexoContrato(a.id)} target="_blank" rel="noreferrer" style={{ display: "flex", alignItems: "center", gap: "0.35rem", color: "var(--text)", textDecoration: "none" }}>
                      <FileText size={14} /> {a.nome_arquivo} <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>({formatarBytes(a.tamanho_bytes)} — {formatarData(a.criado_em)})</span>
                    </a>
                    <button onClick={() => excluirAnexo(a.id)} title="Excluir anexo" style={{ background: "transparent", border: "none", color: "var(--red)", cursor: "pointer" }}>
                      <Trash2 size={14} />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <div className="card-header mt-4 mb-2 flex items-center gap-2"><Users size={15} /> Usuários vinculados</div>
            <div className="flex items-center gap-2 mb-2" style={{ flexWrap: "wrap" }}>
              <input placeholder="username do usuário" style={{ ...inp, width: "auto", flex: "1 1 12rem" }}
                value={novoUsername} onChange={(e) => setNovoUsername(e.target.value)} />
              <select style={{ ...inp, width: "auto" }} value={novoPapel} onChange={(e) => setNovoPapel(e.target.value as any)}>
                <option value="funcionario">Funcionário (acesso normal)</option>
                <option value="contratante">Contratante (administra a fazenda)</option>
                <option value="consultor" disabled={!temModuloConsultor}>
                  Consultor externo{!temModuloConsultor ? " — requer plano Diamond" : ""}
                </option>
              </select>
              <button onClick={vincular} disabled={vinculando} className="btn-primary" style={{ fontSize: "0.78rem", padding: "0.35rem 0.7rem", display: "flex", alignItems: "center", gap: "0.3rem" }}>
                <UserPlus size={13} /> {vinculando ? "Vinculando…" : "Vincular"}
              </button>
            </div>
            {usuarios && usuarios.length > 0 && (
              <ul style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                {usuarios.map((u) => (
                  <li key={u.usuario_id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", fontSize: "0.8rem", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.6rem" }}>
                    <span>
                      {u.nome || u.username} <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>(@{u.username})</span>
                      {u.contratante && <span style={{ marginLeft: "0.5rem", fontSize: "0.7rem", color: "var(--dourado)", fontWeight: 700 }}>Contratante</span>}
                      {u.consultor && <span style={{ marginLeft: "0.5rem", fontSize: "0.7rem", color: "var(--green-light)", fontWeight: 700 }}>Consultor</span>}
                    </span>
                    <button onClick={() => desvincular(u.usuario_id)} title="Desvincular" style={{ background: "transparent", border: "none", color: "var(--red)", cursor: "pointer" }}>
                      <Trash2 size={14} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
