"use client";
import { useEffect, useState } from "react";
import { Building2, Plus, Check, Ban, Upload, Trash2, FileText, AlertTriangle, ShieldCheck, Users, UserPlus, Briefcase, Download, PenLine, QrCode, Receipt, Repeat } from "lucide-react";
import {
  fetchFazendas, criarFazenda, atualizarFazenda, fetchContratoFazenda, definirContratoFazenda, aprovarContratoFazenda,
  suspenderContratoFazenda, fetchPlanosCatalogo, fetchAnexosContrato, anexarContrato, excluirAnexoContrato,
  baixarAnexoContrato, fetchUsuariosVinculados, vincularUsuarioFazenda, desvincularUsuarioFazenda,
  fetchContratosConsultor, aprovarContratoConsultor, suspenderContratoConsultor,
  baixarModeloContrato, assinarContratoZapSign, fetchStatusAssinaturaZapSign,
  criarAssinaturaAsaas, criarPixSemestralAsaas, criarBoletoAsaas, fetchCobrancasAsaas,
  type Fazenda, type ContratoFazenda, type PlanoCatalogo, type PlanoNome, type ModuloComercial,
  type AnexoContrato, type UsuarioVinculado, type ContratoConsultorAdmin, type AssinaturaZapSign,
  type CobrancaAsaas, type CobrancaAsaasIn,
} from "@/lib/api";
import { maskCpf, maskCnpj, maskCep, maskCpfCnpj } from "@/lib/masks";

const inp: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", fontSize: "0.85rem" };
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

const NOME_MODULO: Record<ModuloComercial, string> = {
  rebanho: "Rebanho", reprodutivo: "Reprodutivo", produtivo: "Produtivo", sanitario: "Sanitário",
  financeiro: "Financeiro (básico)", planejamento: "Planejamento", pedidos: "Pedidos", estoque: "Estoque",
  alimentacao: "Alimentação", agricultura: "Agricultura/Plantio", consultor: "Consultor (Diamond)",
  formulacao_dietas: "Formulação de Dietas",
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
  const [baixandoModelo, setBaixandoModelo] = useState(false);
  const [assinandoZapSign, setAssinandoZapSign] = useState(false);
  const [assinaturaZapSign, setAssinaturaZapSign] = useState<AssinaturaZapSign>(null);

  const [cobrancas, setCobrancas] = useState<CobrancaAsaas[] | null>(null);
  const [pagador, setPagador] = useState<CobrancaAsaasIn>({ pagador_nome: "", pagador_documento: "", pagador_email: "" });
  const [gerandoCobranca, setGerandoCobranca] = useState<"assinatura" | "semestral" | "boleto" | null>(null);

  const [abrirNova, setAbrirNova] = useState(false);
  const [novoNome, setNovoNome] = useState("");
  const [novaCidade, setNovaCidade] = useState("");
  const [novaUf, setNovaUf] = useState("");
  const [criando, setCriando] = useState(false);

  const [editForm, setEditForm] = useState({ nome: "", cidade: "", uf: "", tipo_documento: "" as "" | "cpf" | "cnpj", documento: "", endereco: "", cep: "", representante_nome: "", representante_cpf: "" });
  const [salvandoDados, setSalvandoDados] = useState(false);

  const [usuarios, setUsuarios] = useState<UsuarioVinculado[] | null>(null);
  const [novoUsername, setNovoUsername] = useState("");
  const [novoPapel, setNovoPapel] = useState<"funcionario" | "contratante" | "consultor" | "contador">("funcionario");
  const [vinculando, setVinculando] = useState(false);

  // Assinaturas do produto de Consultor independente (Fase 2C) — fora de
  // qualquer fazenda-tenant, ver fazenda/models/consultores.py.
  const [consultores, setConsultores] = useState<ContratoConsultorAdmin[] | null>(null);
  const [processandoConsultor, setProcessandoConsultor] = useState<number | null>(null);

  function carregarConsultores() {
    fetchContratosConsultor().then(setConsultores).catch((e) => setErro(e.message));
  }
  useEffect(carregarConsultores, []);

  async function aprovarConsultor(usuarioId: number) {
    setProcessandoConsultor(usuarioId); setErro(null);
    try { await aprovarContratoConsultor(usuarioId); carregarConsultores(); }
    catch (e: any) { setErro(e.message); } finally { setProcessandoConsultor(null); }
  }
  async function suspenderConsultor(usuarioId: number) {
    setProcessandoConsultor(usuarioId); setErro(null);
    try { await suspenderContratoConsultor(usuarioId); carregarConsultores(); }
    catch (e: any) { setErro(e.message); } finally { setProcessandoConsultor(null); }
  }

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
    fetchStatusAssinaturaZapSign(fazendaId).then(setAssinaturaZapSign).catch((e) => setErro(e.message));
    fetchCobrancasAsaas(fazendaId).then(setCobrancas).catch((e) => setErro(e.message));
  }

  function selecionar(id: number) {
    setSelecionada(id);
    setErro(null);
    setMsg(null);
    carregarContrato(id);
    const f = fazendas?.find((x) => x.id === id);
    if (f) {
      setEditForm({
        nome: f.nome, cidade: f.cidade || "", uf: f.uf || "",
        tipo_documento: (f.tipo_documento as "" | "cpf" | "cnpj") || "", documento: f.documento || "",
        endereco: f.endereco || "", cep: f.cep || "",
        representante_nome: f.representante_nome || "", representante_cpf: f.representante_cpf || "",
      });
      // Pré-preenche o pagador da cobrança com o representante/documento já
      // salvos da fazenda — evita redigitar toda vez (ver "Complementar" abaixo).
      setPagador({ pagador_nome: f.representante_nome || f.nome, pagador_documento: f.documento || "", pagador_email: "" });
    }
  }

  async function salvarDadosFazenda() {
    if (selecionada == null) return;
    setSalvandoDados(true); setErro(null); setMsg(null);
    try {
      const atualizada = await atualizarFazenda(selecionada, editForm);
      setFazendas((atuais) => atuais?.map((f) => (f.id === selecionada ? atualizada : f)) ?? null);
      setMsg("Dados da fazenda atualizados.");
    } catch (e: any) { setErro(e.message); } finally { setSalvandoDados(false); }
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
        contador: novoPapel === "contador",
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
        ? { plano: null, modulos: Object.entries(modulosCustom).filter(([, v]) => v != null).map(([modulo, preco]) => ({ modulo: modulo as ModuloComercial, preco: preco || 0 })), ciclo_pagamento: "mensal" as const }
        : { plano: planoEscolhido, modulos: [], ciclo_pagamento: "mensal" as const };
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

  async function baixarContrato() {
    if (selecionada == null) return;
    setBaixandoModelo(true); setErro(null);
    try { await baixarModeloContrato(selecionada); }
    catch (e: any) { setErro(e.message); } finally { setBaixandoModelo(false); }
  }

  async function assinarZapSign() {
    if (selecionada == null) return;
    setAssinandoZapSign(true); setErro(null); setMsg(null);
    try {
      const tentativa = await assinarContratoZapSign(selecionada);
      setAssinaturaZapSign(tentativa);
      if (tentativa?.sign_url) window.open(tentativa.sign_url, "_blank", "noreferrer");
      setMsg("Solicitação de assinatura enviada pelo ZapSign — confira o e-mail cadastrado no seu usuário.");
    } catch (e: any) { setErro(e.message); } finally { setAssinandoZapSign(false); }
  }

  async function gerarCobranca(tipo: "assinatura" | "semestral" | "boleto") {
    if (selecionada == null) return;
    if (!pagador.pagador_nome.trim() || !pagador.pagador_documento.trim()) {
      setErro("Informe nome e CPF/CNPJ do pagador antes de gerar a cobrança."); return;
    }
    setGerandoCobranca(tipo); setErro(null); setMsg(null);
    try {
      const criar = tipo === "assinatura" ? criarAssinaturaAsaas : tipo === "semestral" ? criarPixSemestralAsaas : criarBoletoAsaas;
      const resultado = await criar(selecionada, pagador);
      if (resultado.pix_qr_code) setMsg("QR Code Pix gerado — copie o código ou escaneie para pagar.");
      else if (resultado.invoice_url) { window.open(resultado.invoice_url, "_blank", "noreferrer"); setMsg("Cobrança gerada — abrindo o link de pagamento."); }
      else setMsg("Cobrança gerada com sucesso.");
      fetchCobrancasAsaas(selecionada).then(setCobrancas);
    } catch (e: any) { setErro(e.message); } finally { setGerandoCobranca(null); }
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
        <div className="mb-3 flex items-center gap-2" style={{ background: "rgba(45,138,86,0.15)", border: "1px solid var(--green-light)", borderRadius: "var(--r-sm)", padding: "0.6rem 1rem", color: "var(--green-light)", fontSize: "0.82rem" }}>
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
                  style={{ textAlign: "left", padding: "0.5rem 0.7rem", borderRadius: "var(--r-sm)", cursor: "pointer",
                    border: "1px solid " + (selecionada === f.id ? "var(--dourado)" : "var(--border)"),
                    background: selecionada === f.id ? "rgba(212,160,23,0.12)" : "transparent", color: "var(--text)", fontSize: "0.83rem" }}>
                  <div style={{ fontWeight: 600 }}>{f.nome}</div>
                  {(f.cidade || f.uf) && <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{[f.cidade, f.uf].filter(Boolean).join(" / ")}</div>}
                </button>
              ))}
            </div>
          )}
        </div>

        {selecionada != null && (
          <div className="card" style={{ flex: "1 1 300px", minWidth: "280px" }}>
            <div className="card-header mb-2">Dados da fazenda</div>
            <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "0.6rem" }}>
              Nome, endereço, CPF/CNPJ e representante — usados como padrão no contrato-modelo e na cobrança.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
              <label style={lbl}>Nome</label>
              <input style={inp} value={editForm.nome} onChange={(e) => setEditForm((s) => ({ ...s, nome: e.target.value }))} />
              <div className="flex gap-2">
                <div style={{ flex: 1 }}>
                  <label style={lbl}>Cidade</label>
                  <input style={inp} value={editForm.cidade} onChange={(e) => setEditForm((s) => ({ ...s, cidade: e.target.value }))} />
                </div>
                <div style={{ width: "5rem" }}>
                  <label style={lbl}>UF</label>
                  <input style={inp} value={editForm.uf} onChange={(e) => setEditForm((s) => ({ ...s, uf: e.target.value }))} />
                </div>
              </div>
              <label style={lbl}>A fazenda é cadastrada como</label>
              <div className="flex gap-2" style={{ marginBottom: "0.2rem" }}>
                {(["cpf", "cnpj"] as const).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setEditForm((s) => (s.tipo_documento === t ? s : { ...s, tipo_documento: t, documento: "" }))}
                    className={editForm.tipo_documento === t ? "btn-primary" : "btn-secondary"}
                    style={{ fontSize: "0.78rem", padding: "0.35rem 0.8rem", flex: 1 }}
                  >
                    {t.toUpperCase()}
                  </button>
                ))}
              </div>
              <label style={lbl}>{editForm.tipo_documento === "cnpj" ? "CNPJ" : "CPF"}</label>
              <input
                style={inp}
                placeholder={!editForm.tipo_documento ? "Escolha CPF ou CNPJ acima" : editForm.tipo_documento === "cnpj" ? "00.000.000/0000-00" : "000.000.000-00"}
                disabled={!editForm.tipo_documento}
                value={editForm.documento}
                onChange={(e) => setEditForm((s) => ({ ...s, documento: (s.tipo_documento === "cnpj" ? maskCnpj : maskCpf)(e.target.value) }))}
              />
              <label style={lbl}>CEP</label>
              <input style={inp} placeholder="00.000-000" value={editForm.cep} onChange={(e) => setEditForm((s) => ({ ...s, cep: maskCep(e.target.value) }))} />
              <label style={lbl}>Endereço completo</label>
              <input style={inp} value={editForm.endereco} onChange={(e) => setEditForm((s) => ({ ...s, endereco: e.target.value }))} />
              <label style={lbl}>Nome do representante</label>
              <input style={inp} value={editForm.representante_nome} onChange={(e) => setEditForm((s) => ({ ...s, representante_nome: e.target.value }))} />
              <label style={lbl}>CPF do representante</label>
              <input style={inp} placeholder="000.000.000-00" value={editForm.representante_cpf} onChange={(e) => setEditForm((s) => ({ ...s, representante_cpf: maskCpf(e.target.value) }))} />
              <button onClick={salvarDadosFazenda} disabled={salvandoDados} className="btn-primary" style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem", marginTop: "0.3rem" }}>
                {salvandoDados ? "Salvando…" : "Salvar dados da fazenda"}
              </button>
            </div>
          </div>
        )}

        {selecionada != null && contrato && (
          <div className="card" style={{ flex: "1 1 420px", minWidth: "360px" }}>
            <div className="card-header mb-3 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
              <span>Contrato</span>
              <StatusBadge status={contrato.status} />
            </div>

            <label style={lbl}>Plano</label>
            <div className="flex flex-wrap gap-2 mb-3">
              {(["standard", "silver", "gold", "diamond"] as const).map((p) => (
                <label key={p} style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.8rem", fontWeight: planoEscolhido === p ? 700 : 400, cursor: "pointer",
                  border: "1px solid " + (planoEscolhido === p ? "var(--dourado)" : "var(--border)"), borderRadius: "var(--r-sm)", padding: "0.35rem 0.6rem",
                  // Fundo sólido + cor de texto explícita (não hardcoded): --pill-active-bg/--pill-active-fg
                  // já seguem tema (claro/misto/escuro) E paleta (vinho/verde/azul) — o tom âmbar fixo
                  // que estava aqui antes não acompanhava a paleta escolhida e deixava a opção
                  // selecionada com contraste ruim em claro/misto (texto herdado sobre fundo quase
                  // branco). Mesmo padrão de SeletorTipoProtocolo (app/protocolos/page.tsx).
                  background: planoEscolhido === p ? "var(--pill-active-bg)" : "transparent",
                  color: planoEscolhido === p ? "var(--pill-active-fg)" : "var(--text)" }}>
                  <input type="radio" name="plano" checked={planoEscolhido === p} onChange={() => setPlanoEscolhido(p)} />
                  {catalogo?.[p]?.nome || p} — R$ {catalogo?.[p]?.preco.toFixed(2) ?? "—"}/mês
                </label>
              ))}
              <label style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.8rem", fontWeight: planoEscolhido === "custom" ? 700 : 400, cursor: "pointer",
                border: "1px solid " + (planoEscolhido === "custom" ? "var(--dourado)" : "var(--border)"), borderRadius: "var(--r-sm)", padding: "0.35rem 0.6rem",
                background: planoEscolhido === "custom" ? "var(--pill-active-bg)" : "transparent",
                color: planoEscolhido === "custom" ? "var(--pill-active-fg)" : "var(--text)" }}>
                <input type="radio" name="plano" checked={planoEscolhido === "custom"} onChange={() => setPlanoEscolhido("custom")} />
                Sob medida
              </label>
            </div>

            {planoEscolhido !== "custom" ? (
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
                Módulos inclusos: {modulosDoPlano.map((m) => NOME_MODULO[m]).join(", ")}.
              </p>
            ) : null}

            {/* Trimestral/semestral saíram do catálogo (pedido explícito do
                usuário, ago/2026) — assinatura é só mensal agora, sem
                desconto por adiantamento; não há mais o que escolher aqui. */}
            {contrato.preco_mensal != null && (
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
                Ciclo de pagamento: Mensal — R$ {contrato.preco_mensal.toFixed(2)}/mês.
              </p>
            )}

            {planoEscolhido === "custom" && (
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
                  style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem", borderRadius: "var(--r-sm)", border: "1px solid var(--green-light)", background: "transparent", color: "var(--green-light)", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                  <ShieldCheck size={14} /> {aprovando ? "Aprovando…" : "Aprovar/Fechar contrato"}
                </button>
              ) : (
                <button onClick={suspender} disabled={aprovando}
                  style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem", borderRadius: "var(--r-sm)", border: "1px solid var(--red)", background: "transparent", color: "var(--red)", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                  <Ban size={14} /> {aprovando ? "Suspendendo…" : "Suspender"}
                </button>
              )}
            </div>

            <div className="card-header mb-2">Contrato assinado</div>
            <div className="flex flex-wrap gap-2 mb-2">
              <button onClick={baixarContrato} disabled={baixandoModelo}
                style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.78rem", padding: "0.35rem 0.7rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", cursor: "pointer", color: "var(--text)", background: "transparent" }}>
                <Download size={13} /> {baixandoModelo ? "Gerando…" : "Baixar contrato"}
              </button>
              <label style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.78rem", padding: "0.35rem 0.7rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", cursor: "pointer", color: "var(--text-muted)" }}>
                <Upload size={13} /> {enviandoAnexo ? "Enviando…" : "Anexar contrato assinado"}
                <input type="file" accept="application/pdf,image/*" style={{ display: "none" }} disabled={enviandoAnexo}
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) enviarAnexo(f); e.target.value = ""; }} />
              </label>
              <button onClick={assinarZapSign} disabled={assinandoZapSign}
                style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.78rem", padding: "0.35rem 0.7rem", borderRadius: "var(--r-sm)", border: "1px solid var(--dourado)", cursor: "pointer", color: "var(--dourado)", background: "transparent" }}>
                <PenLine size={13} /> {assinandoZapSign ? "Enviando ao ZapSign…" : "Assinar contrato (ZapSign)"}
              </button>
            </div>
            {assinaturaZapSign && (
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
                Última solicitação ZapSign: <b style={{
                  color: assinaturaZapSign.status === "signed" ? "var(--green-light)" : assinaturaZapSign.status === "refused" ? "var(--red)" : "var(--dourado)",
                }}>{assinaturaZapSign.status === "signed" ? "assinado" : assinaturaZapSign.status === "refused" ? "recusado" : "pendente"}</b>
                {" "}({formatarData(assinaturaZapSign.criado_em)}){assinaturaZapSign.sign_url && assinaturaZapSign.status !== "signed" && (
                  <> — <a href={assinaturaZapSign.sign_url} target="_blank" rel="noreferrer" style={{ color: "var(--dourado)" }}>reabrir link de assinatura</a></>
                )}
              </p>
            )}
            {anexos && anexos.length > 0 && (
              <ul style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                {anexos.map((a) => (
                  <li key={a.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", fontSize: "0.8rem", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.6rem" }}>
                    <button onClick={() => baixarAnexoContrato(a.id, a.nome_arquivo).catch((e: any) => setErro(e.message))}
                      style={{ display: "flex", alignItems: "center", gap: "0.35rem", color: "var(--text)", background: "transparent", border: "none", padding: 0, cursor: "pointer", textAlign: "left" }}>
                      <FileText size={14} /> {a.nome_arquivo} <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>({formatarBytes(a.tamanho_bytes)} — {formatarData(a.criado_em)})</span>
                    </button>
                    <button onClick={() => excluirAnexo(a.id)} title="Excluir anexo" style={{ background: "transparent", border: "none", color: "var(--red)", cursor: "pointer" }}>
                      <Trash2 size={14} />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <div className="card-header mt-4 mb-2">Cobrança da assinatura (Asaas)</div>
            <div className="flex flex-wrap gap-2 mb-2">
              <input placeholder="Nome do pagador" style={{ ...inp, width: "auto", flex: "1 1 10rem" }}
                value={pagador.pagador_nome} onChange={(e) => setPagador((s) => ({ ...s, pagador_nome: e.target.value }))} />
              <input placeholder="CPF/CNPJ" style={{ ...inp, width: "auto", flex: "1 1 8rem" }}
                value={pagador.pagador_documento} onChange={(e) => setPagador((s) => ({ ...s, pagador_documento: maskCpfCnpj(e.target.value) }))} />
              <input placeholder="E-mail (opcional)" style={{ ...inp, width: "auto", flex: "1 1 10rem" }}
                value={pagador.pagador_email} onChange={(e) => setPagador((s) => ({ ...s, pagador_email: e.target.value }))} />
            </div>
            <div className="flex flex-wrap gap-2 mb-2">
              <button onClick={() => gerarCobranca("assinatura")} disabled={gerandoCobranca !== null}
                style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.78rem", padding: "0.35rem 0.7rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", cursor: "pointer", color: "var(--text)", background: "transparent" }}>
                <Repeat size={13} /> {gerandoCobranca === "assinatura" ? "Criando…" : "Assinatura mensal (Pix)"}
              </button>
              <button onClick={() => gerarCobranca("semestral")} disabled={gerandoCobranca !== null}
                style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.78rem", padding: "0.35rem 0.7rem", borderRadius: "var(--r-sm)", border: "1px solid var(--dourado)", cursor: "pointer", color: "var(--dourado)", background: "transparent" }}>
                <QrCode size={13} /> {gerandoCobranca === "semestral" ? "Gerando…" : "QR semestral (-20%)"}
              </button>
              <button onClick={() => gerarCobranca("boleto")} disabled={gerandoCobranca !== null}
                style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.78rem", padding: "0.35rem 0.7rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", cursor: "pointer", color: "var(--text)", background: "transparent" }}>
                <Receipt size={13} /> {gerandoCobranca === "boleto" ? "Gerando…" : "Boleto"}
              </button>
            </div>
            {cobrancas && cobrancas.length > 0 && (
              <ul style={{ display: "flex", flexDirection: "column", gap: "0.3rem", marginBottom: "0.5rem" }}>
                {cobrancas.map((c) => (
                  <li key={c.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", fontSize: "0.78rem", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.6rem" }}>
                    <span>{c.tipo.replace("_", " ")} — R$ {c.valor.toFixed(2)} <span style={{ color: "var(--text-muted)", fontSize: "0.7rem" }}>({formatarData(c.criado_em)})</span></span>
                    <span style={{ fontWeight: 700, color: c.status === "paga" ? "var(--green-light)" : "var(--dourado)" }}>{c.status === "paga" ? "paga" : "aguardando"}</span>
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
                <option value="contador">Contador (Financeiro, só leitura)</option>
              </select>
              <button onClick={vincular} disabled={vinculando} className="btn-primary" style={{ fontSize: "0.78rem", padding: "0.35rem 0.7rem", display: "flex", alignItems: "center", gap: "0.3rem" }}>
                <UserPlus size={13} /> {vinculando ? "Vinculando…" : "Vincular"}
              </button>
            </div>
            {usuarios && usuarios.length > 0 && (
              <ul style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                {usuarios.map((u) => (
                  <li key={u.usuario_id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", fontSize: "0.8rem", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.6rem" }}>
                    <span>
                      {u.nome || u.username} <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>(@{u.username})</span>
                      {u.contratante && <span style={{ marginLeft: "0.5rem", fontSize: "0.7rem", color: "var(--dourado)", fontWeight: 700 }}>Contratante</span>}
                      {u.consultor && <span style={{ marginLeft: "0.5rem", fontSize: "0.7rem", color: "var(--green-light)", fontWeight: 700 }}>Consultor</span>}
                      {u.contador && <span style={{ marginLeft: "0.5rem", fontSize: "0.7rem", color: "var(--blue-light, #6fa8dc)", fontWeight: 700 }}>Contador</span>}
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

      <div className="card mt-4">
        <div className="card-header mb-2 flex items-center gap-2"><Briefcase size={16} style={{ color: "var(--dourado)" }} /> Assinaturas de consultor</div>
        <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
          Produto independente do consultor (fora de qualquer fazenda) — fazendas gerenciadas por importação de
          planilha. Nada libera até você aprovar o plano solicitado.
        </p>
        {!consultores ? <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Carregando…</p> : consultores.length === 0 ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Nenhuma solicitação de plano de consultor ainda.</p>
        ) : (
          <ul style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            {consultores.map((c) => (
              <li key={c.usuario_id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem", flexWrap: "wrap", fontSize: "0.82rem", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.7rem" }}>
                <span>
                  <strong>@{c.username}</strong>{" "}
                  <span style={{ color: "var(--text-muted)" }}>— {c.plano || "sem plano"} (até {c.limite_fazendas ?? "—"} fazenda(s))</span>
                </span>
                <span className="flex items-center gap-2">
                  <StatusBadge status={c.status} />
                  {c.status !== "ativo" ? (
                    <button onClick={() => aprovarConsultor(c.usuario_id)} disabled={processandoConsultor === c.usuario_id}
                      style={{ fontSize: "0.76rem", padding: "0.3rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--green-light)", background: "transparent", color: "var(--green-light)", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.3rem" }}>
                      <ShieldCheck size={13} /> {processandoConsultor === c.usuario_id ? "Aprovando…" : "Aprovar"}
                    </button>
                  ) : (
                    <button onClick={() => suspenderConsultor(c.usuario_id)} disabled={processandoConsultor === c.usuario_id}
                      style={{ fontSize: "0.76rem", padding: "0.3rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--red)", background: "transparent", color: "var(--red)", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.3rem" }}>
                      <Ban size={13} /> {processandoConsultor === c.usuario_id ? "Suspendendo…" : "Suspender"}
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
