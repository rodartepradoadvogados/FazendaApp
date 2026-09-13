"use client";
// Fazendas (clientes) — versão mobile-nativa do Painel CowData (app/PWA
// instalado em tela de celular). Mesmo estado/lógica de negócio de
// FazendasAdmin.tsx (a tela desktop, reaproveitada também em Configurações) —
// nenhuma funcionalidade nova nem removida, só troca o layout de 3 colunas
// lado a lado pelo padrão lista → detalhe em acordeão do estudo /design
// aprovado em 05/09/2026. Ver ComumMobile.tsx pros blocos reaproveitados.
import { useEffect, useState } from "react";
import {
  Plus, Check, Ban, Upload, Trash2, FileText, AlertTriangle, ShieldCheck, Users, UserPlus, Download,
  PenLine, QrCode, Receipt, Repeat, Pencil, X as XIcon,
} from "lucide-react";
import {
  fetchFazendas, criarFazenda, atualizarFazenda, fetchContratoFazenda, definirContratoFazenda, aprovarContratoFazenda,
  suspenderContratoFazenda, fetchPlanosCatalogo, fetchAnexosContrato, anexarContrato, excluirAnexoContrato,
  baixarAnexoContrato, fetchUsuariosVinculados, vincularUsuarioFazenda, desvincularUsuarioFazenda, editarVinculoUsuarioFazenda,
  baixarModeloContrato, assinarContratoZapSign, fetchStatusAssinaturaZapSign,
  criarAssinaturaAsaas, criarPixSemestralAsaas, criarBoletoAsaas, fetchCobrancasAsaas,
  fetchConsultoresCowData,
  type Fazenda, type ContratoFazenda, type PlanoCatalogo, type PlanoNome, type ModuloComercial,
  type AnexoContrato, type UsuarioVinculado, type AssinaturaZapSign, type ConsultorCowData,
  type CobrancaAsaas, type CobrancaAsaasIn,
} from "@/lib/api";
import { casaBusca } from "@/lib/busca";
import { maskCpf, maskCnpj, maskCep, maskCpfCnpj } from "@/lib/masks";
import { usePainelCowDataEstilos } from "@/lib/painelCowDataTema";
import {
  CabecalhoMobilePainelCowData, CorpoMobilePainelCowData, CampoBuscaMobile, LinhaListaMobile,
  SecaoAcordeaoMobile, useAcordeaoUnico, CampoMobile, BotaoMobile, inputEstilo,
} from "@/components/painel-cowdata/mobile/ComumMobile";

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

function corDoStatus(cor: ReturnType<typeof usePainelCowDataEstilos>["cor"], status: ContratoFazenda["status"]) {
  if (status === "ativo") return cor.verde;
  if (status === "suspenso") return cor.vermelho;
  if (status === "aguardando_aprovacao") return cor.dourado;
  return cor.mudo;
}
function labelDoStatus(status: ContratoFazenda["status"]) {
  return status === "ativo" ? "Ativo" : status === "suspenso" ? "Suspenso" : status === "aguardando_aprovacao" ? "Aguardando aprovação" : "Sem contrato";
}

const PAPEIS = [
  { valor: "funcionario", label: "Funcionário (acesso normal)" },
  { valor: "contratante", label: "Contratante (administra a fazenda)" },
  { valor: "consultor", label: "Consultor externo" },
  { valor: "contador", label: "Contador (Financeiro, só leitura)" },
] as const;

export default function FazendasMobile() {
  const estilos = usePainelCowDataEstilos();
  const cor = estilos.cor;

  const [fazendas, setFazendas] = useState<Fazenda[] | null>(null);
  const [busca, setBusca] = useState("");
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
  const [confirmarSuspender, setConfirmarSuspender] = useState(false);
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
  const [editandoVinculoId, setEditandoVinculoId] = useState<number | null>(null);
  const [papelEditando, setPapelEditando] = useState<"funcionario" | "contratante" | "consultor" | "contador">("funcionario");
  const [salvandoVinculo, setSalvandoVinculo] = useState(false);

  const [consultoresCowData, setConsultoresCowData] = useState<ConsultorCowData[] | null>(null);
  const [consultorEscolhido, setConsultorEscolhido] = useState<number | "">("");
  const [vinculandoConsultor, setVinculandoConsultor] = useState(false);

  const { aberta, alternar } = useAcordeaoUnico("identificacao");

  function carregarFazendas() {
    fetchFazendas().then(setFazendas).catch((e) => setErro(e.message));
  }
  useEffect(carregarFazendas, []);
  useEffect(() => { fetchPlanosCatalogo().then(setCatalogo).catch((e) => setErro(e.message)); }, []);
  useEffect(() => { fetchConsultoresCowData().then(setConsultoresCowData).catch((e) => setErro(e.message)); }, []);

  useEffect(() => {
    if (selecionada == null || usuarios == null || consultoresCowData == null) return;
    const ids = new Set(consultoresCowData.map((c) => c.usuario_id));
    const atual = usuarios.find((u) => u.consultor && ids.has(u.usuario_id));
    setConsultorEscolhido(atual ? atual.usuario_id : "");
  }, [selecionada, usuarios, consultoresCowData]);

  function carregarContrato(fazendaId: number) {
    fetchContratoFazenda(fazendaId).then((ct) => {
      setContrato(ct);
      if (ct.plano) setPlanoEscolhido(ct.plano);
      else {
        setPlanoEscolhido("custom");
        const mapa: Record<string, number> = {};
        ct.modulos.filter((m) => m.ativo).forEach((m) => { mapa[m.modulo] = m.preco; });
        if (mapa.rebanho == null) mapa.rebanho = 0;
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
    setErro(null); setMsg(null); setConfirmarSuspender(false);
    carregarContrato(id);
    const f = fazendas?.find((x) => x.id === id);
    if (f) {
      setEditForm({
        nome: f.nome, cidade: f.cidade || "", uf: f.uf || "",
        tipo_documento: (f.tipo_documento as "" | "cpf" | "cnpj") || "", documento: f.documento || "",
        endereco: f.endereco || "", cep: f.cep || "",
        representante_nome: f.representante_nome || "", representante_cpf: f.representante_cpf || "",
      });
      setPagador({ pagador_nome: f.representante_nome || f.nome, pagador_documento: f.documento || "", pagador_email: "" });
    }
  }

  function voltarParaLista() {
    setSelecionada(null); setErro(null); setMsg(null);
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
  const consultorNoRascunho = planoEscolhido === "diamond"
    || (planoEscolhido === "custom" && modulosCustom["consultor" as ModuloComercial] != null);

  function selecionarSobMedida() {
    const semente: Record<string, number> = {};
    (contrato?.modulos || []).filter((m) => m.ativo).forEach((m) => { semente[m.modulo] = m.preco; });
    if (semente.rebanho == null) semente.rebanho = 0;
    setModulosCustom(semente as any);
    setPlanoEscolhido("custom");
  }

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

  async function vincularConsultorCowData() {
    if (selecionada == null) return;
    const anterior = (usuarios || []).find(
      (u) => u.consultor && (consultoresCowData || []).some((c) => c.usuario_id === u.usuario_id),
    );
    setVinculandoConsultor(true); setErro(null); setMsg(null);
    try {
      if (anterior && anterior.usuario_id !== consultorEscolhido) {
        await desvincularUsuarioFazenda(selecionada, anterior.usuario_id);
      }
      if (consultorEscolhido !== "") {
        const alvo = Number(consultorEscolhido);
        const jaVinculado = (usuarios || []).some((u) => u.usuario_id === alvo);
        if (jaVinculado) await editarVinculoUsuarioFazenda(selecionada, alvo, { consultor: true });
        else await vincularUsuarioFazenda(selecionada, { usuario_id: alvo, consultor: true });
      }
      const us = await fetchUsuariosVinculados(selecionada);
      setUsuarios(us);
      setMsg(consultorEscolhido === "" ? "Consultor CowData desvinculado." : "Consultor CowData vinculado a esta fazenda.");
    } catch (e: any) { setErro(e.message); } finally { setVinculandoConsultor(false); }
  }

  async function desvincular(usuarioId: number) {
    if (selecionada == null) return;
    setErro(null);
    try {
      await desvincularUsuarioFazenda(selecionada, usuarioId);
      fetchUsuariosVinculados(selecionada).then(setUsuarios);
    } catch (e: any) { setErro(e.message); }
  }

  function papelDoVinculo(u: UsuarioVinculado): "funcionario" | "contratante" | "consultor" | "contador" {
    if (u.contratante) return "contratante";
    if (u.consultor) return "consultor";
    if (u.contador) return "contador";
    return "funcionario";
  }

  function abrirEdicaoVinculo(u: UsuarioVinculado) {
    setEditandoVinculoId(u.usuario_id);
    setPapelEditando(papelDoVinculo(u));
    setErro(null);
  }

  async function salvarEdicaoVinculo(usuarioId: number) {
    if (selecionada == null) return;
    setSalvandoVinculo(true); setErro(null);
    try {
      await editarVinculoUsuarioFazenda(selecionada, usuarioId, {
        contratante: papelEditando === "contratante",
        consultor: papelEditando === "consultor",
        contador: papelEditando === "contador",
      });
      setEditandoVinculoId(null);
      fetchUsuariosVinculados(selecionada).then(setUsuarios);
    } catch (e: any) { setErro(e.message); } finally { setSalvandoVinculo(false); }
  }

  async function criarNovaFazenda() {
    if (!novoNome.trim()) { setErro("Nome é obrigatório."); return; }
    setCriando(true); setErro(null);
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
    if (!confirmarSuspender) { setConfirmarSuspender(true); return; }
    setConfirmarSuspender(false);
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
  const fazendaAtual = fazendas?.find((f) => f.id === selecionada) || null;
  const fazendasFiltradas = (fazendas || []).filter((f) => casaBusca([f.nome, f.cidade, f.uf].filter(Boolean).join(" "), busca));

  const AvisoErro = erro ? (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", background: "rgba(181,84,74,0.12)", border: `1px solid ${cor.vermelho}`, borderRadius: "var(--r-sm)", padding: "0.6rem 0.8rem", color: cor.vermelho, fontSize: "0.8rem" }}>
      <AlertTriangle size={15} /><span>{erro}</span>
    </div>
  ) : null;
  const AvisoMsg = msg ? (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", background: "rgba(143,170,123,0.12)", border: `1px solid ${cor.verde}`, borderRadius: "var(--r-sm)", padding: "0.6rem 0.8rem", color: cor.verde, fontSize: "0.8rem" }}>
      <Check size={15} /><span>{msg}</span>
    </div>
  ) : null;

  // ── Lista de fazendas ──
  if (selecionada == null) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
        <CabecalhoMobilePainelCowData
          titulo="Fazendas (clientes)"
          subtitulo="Cada fazenda contrata um plano — nada libera até você aprovar e fechar o contrato."
          cor={cor}
          acao={
            <button onClick={() => setAbrirNova((v) => !v)} title="Cadastrar fazenda nova"
              style={{ background: "none", border: "none", color: cor.doradoClaro, cursor: "pointer", display: "flex" }}>
              <Plus size={20} />
            </button>
          }
        />
        <CorpoMobilePainelCowData>
          {AvisoErro}
          {abrirNova && (
            <div style={{ background: cor.painelAlt, border: `1px solid ${cor.borda}`, borderRadius: "var(--r-sm)", padding: "0.9rem" }}>
              <CampoMobile label="Nome" estilos={estilos}>
                <input style={inputEstilo(estilos)} value={novoNome} onChange={(e) => setNovoNome(e.target.value)} />
              </CampoMobile>
              <CampoMobile label="Cidade (opcional)" estilos={estilos}>
                <input style={inputEstilo(estilos)} value={novaCidade} onChange={(e) => setNovaCidade(e.target.value)} />
              </CampoMobile>
              <CampoMobile label="UF (opcional)" estilos={estilos}>
                <input style={inputEstilo(estilos)} value={novaUf} onChange={(e) => setNovaUf(e.target.value)} />
              </CampoMobile>
              <BotaoMobile estilos={estilos} disabled={criando} onClick={criarNovaFazenda}>{criando ? "Criando…" : "Cadastrar"}</BotaoMobile>
            </div>
          )}
          <CampoBuscaMobile valor={busca} onChange={setBusca} placeholder="Buscar fazenda…" cor={cor} />
          {!fazendas ? (
            <p style={{ color: cor.mudo, fontSize: "0.85rem" }}>Carregando…</p>
          ) : fazendasFiltradas.length === 0 ? (
            <p style={{ color: cor.mudo, fontSize: "0.85rem" }}>Nenhuma fazenda encontrada.</p>
          ) : (
            fazendasFiltradas.map((f) => (
              <LinhaListaMobile key={f.id} cor={cor} onClick={() => selecionar(f.id)}
                titulo={f.nome} subtitulo={[f.cidade, f.uf].filter(Boolean).join(" / ") || undefined} />
            ))
          )}
        </CorpoMobilePainelCowData>
      </div>
    );
  }

  // ── Detalhe da fazenda selecionada ──
  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: "calc(1.1rem + env(safe-area-inset-top, 0px)) 1.1rem 0.9rem", borderBottom: `1px solid ${cor.borda}` }}>
        <button onClick={voltarParaLista} style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.75rem", color: cor.mudo, background: "none", border: "none", padding: 0, cursor: "pointer", marginBottom: "0.9rem" }}>
          ← Fazendas
        </button>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem" }}>
          <h1 style={{ fontSize: "1.2rem", fontWeight: 700, margin: 0 }}>{fazendaAtual?.nome || "Fazenda"}</h1>
          {contrato && (
            <span style={{ fontSize: "0.68rem", fontWeight: 700, color: corDoStatus(cor, contrato.status), border: `1px solid ${corDoStatus(cor, contrato.status)}`, borderRadius: "999px", padding: "0.2rem 0.6rem", flexShrink: 0 }}>
              {labelDoStatus(contrato.status)}
            </span>
          )}
        </div>
      </div>
      <CorpoMobilePainelCowData>
        {AvisoErro}
        {AvisoMsg}

        <SecaoAcordeaoMobile titulo="Identificação" cor={cor} aberta={aberta === "identificacao"} onToggle={() => alternar("identificacao")}>
          <CampoMobile label="Nome" estilos={estilos}>
            <input style={inputEstilo(estilos)} value={editForm.nome} onChange={(e) => setEditForm((s) => ({ ...s, nome: e.target.value }))} />
          </CampoMobile>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <div style={{ flex: 1 }}>
              <CampoMobile label="Cidade" estilos={estilos}>
                <input style={inputEstilo(estilos)} value={editForm.cidade} onChange={(e) => setEditForm((s) => ({ ...s, cidade: e.target.value }))} />
              </CampoMobile>
            </div>
            <div style={{ width: "4.5rem" }}>
              <CampoMobile label="UF" estilos={estilos}>
                <input style={inputEstilo(estilos)} value={editForm.uf} onChange={(e) => setEditForm((s) => ({ ...s, uf: e.target.value }))} />
              </CampoMobile>
            </div>
          </div>
          <CampoMobile label="A fazenda é cadastrada como" estilos={estilos}>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              {(["cpf", "cnpj"] as const).map((t) => (
                <button key={t} type="button"
                  onClick={() => setEditForm((s) => (s.tipo_documento === t ? s : { ...s, tipo_documento: t, documento: "" }))}
                  style={{ flex: 1, fontSize: "0.78rem", fontWeight: 700, padding: "0.4rem", borderRadius: "var(--r-sm)", cursor: "pointer",
                    border: `1px solid ${editForm.tipo_documento === t ? cor.dourado : cor.borda}`,
                    background: editForm.tipo_documento === t ? cor.dourado : "transparent",
                    color: editForm.tipo_documento === t ? cor.bg : cor.texto }}>
                  {t.toUpperCase()}
                </button>
              ))}
            </div>
          </CampoMobile>
          <CampoMobile label={editForm.tipo_documento === "cnpj" ? "CNPJ" : "CPF"} estilos={estilos}>
            <input style={inputEstilo(estilos)}
              placeholder={!editForm.tipo_documento ? "Escolha CPF ou CNPJ acima" : editForm.tipo_documento === "cnpj" ? "00.000.000/0000-00" : "000.000.000-00"}
              disabled={!editForm.tipo_documento} value={editForm.documento}
              onChange={(e) => setEditForm((s) => ({ ...s, documento: (s.tipo_documento === "cnpj" ? maskCnpj : maskCpf)(e.target.value) }))} />
          </CampoMobile>
          <CampoMobile label="CEP" estilos={estilos}>
            <input style={inputEstilo(estilos)} placeholder="00.000-000" value={editForm.cep} onChange={(e) => setEditForm((s) => ({ ...s, cep: maskCep(e.target.value) }))} />
          </CampoMobile>
          <CampoMobile label="Endereço completo" estilos={estilos}>
            <input style={inputEstilo(estilos)} value={editForm.endereco} onChange={(e) => setEditForm((s) => ({ ...s, endereco: e.target.value }))} />
          </CampoMobile>
          <CampoMobile label="Nome do representante" estilos={estilos}>
            <input style={inputEstilo(estilos)} value={editForm.representante_nome} onChange={(e) => setEditForm((s) => ({ ...s, representante_nome: e.target.value }))} />
          </CampoMobile>
          <CampoMobile label="CPF do representante" estilos={estilos}>
            <input style={inputEstilo(estilos)} placeholder="000.000.000-00" value={editForm.representante_cpf} onChange={(e) => setEditForm((s) => ({ ...s, representante_cpf: maskCpf(e.target.value) }))} />
          </CampoMobile>
          <BotaoMobile estilos={estilos} disabled={salvandoDados} onClick={salvarDadosFazenda}>{salvandoDados ? "Salvando…" : "Salvar dados da fazenda"}</BotaoMobile>
        </SecaoAcordeaoMobile>

        {contrato && (
          <SecaoAcordeaoMobile titulo="Plano & módulos" cor={cor} aberta={aberta === "plano"} onToggle={() => alternar("plano")}>
            <CampoMobile label="Plano" estilos={estilos}>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                {(["standard", "silver", "gold", "diamond"] as const).map((p) => (
                  <label key={p} style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.82rem", fontWeight: planoEscolhido === p ? 700 : 400, cursor: "pointer",
                    border: `1px solid ${planoEscolhido === p ? cor.dourado : cor.borda}`, borderRadius: "var(--r-sm)", padding: "0.5rem 0.7rem" }}>
                    <input type="radio" name="plano" checked={planoEscolhido === p} onChange={() => setPlanoEscolhido(p)} />
                    {catalogo?.[p]?.nome || p} — R$ {catalogo?.[p]?.preco.toFixed(2) ?? "—"}/mês
                  </label>
                ))}
                <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.82rem", fontWeight: planoEscolhido === "custom" ? 700 : 400, cursor: "pointer",
                  border: `1px solid ${planoEscolhido === "custom" ? cor.dourado : cor.borda}`, borderRadius: "var(--r-sm)", padding: "0.5rem 0.7rem" }}>
                  <input type="radio" name="plano" checked={planoEscolhido === "custom"} onChange={selecionarSobMedida} />
                  Sob medida
                </label>
              </div>
            </CampoMobile>

            {planoEscolhido !== "custom" && (
              <p style={{ fontSize: "0.78rem", color: cor.mudo, marginBottom: "0.6rem" }}>
                Módulos inclusos: {modulosDoPlano.map((m) => NOME_MODULO[m]).join(", ")}.
              </p>
            )}
            {contrato.preco_mensal != null && (
              <p style={{ fontSize: "0.78rem", color: cor.mudo, marginBottom: "0.6rem" }}>
                Ciclo de pagamento: Mensal — R$ {contrato.preco_mensal.toFixed(2)}/mês.
              </p>
            )}

            {planoEscolhido === "custom" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginBottom: "0.7rem" }}>
                {(Object.keys(NOME_MODULO) as ModuloComercial[]).map((m) => (
                  <div key={m} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", flex: 1 }}>
                      <input type="checkbox" checked={modulosCustom[m] != null} disabled={m === "rebanho"}
                        onChange={(e) => setModulosCustom((s) => ({ ...s, [m]: e.target.checked ? (s[m] ?? 0) : null }))} />
                      {NOME_MODULO[m]}
                    </label>
                    <input type="number" min={0} step="0.01" placeholder="R$" style={{ ...inputEstilo(estilos), width: "5.5rem" }}
                      disabled={modulosCustom[m] == null} value={modulosCustom[m] ?? ""}
                      onChange={(e) => setModulosCustom((s) => ({ ...s, [m]: e.target.value === "" ? 0 : Number(e.target.value) }))} />
                  </div>
                ))}
              </div>
            )}

            {consultorNoRascunho && (
              <div style={{ border: `1px solid ${cor.borda}`, borderRadius: "var(--r-sm)", padding: "0.7rem", marginBottom: "0.8rem" }}>
                <CampoMobile label="Consultor CowData desta fazenda" estilos={estilos}>
                  <select style={inputEstilo(estilos)} value={consultorEscolhido}
                    onChange={(e) => setConsultorEscolhido(e.target.value === "" ? "" : Number(e.target.value))}>
                    <option value="">— sem consultor vinculado —</option>
                    {(consultoresCowData || []).map((c) => (
                      <option key={c.usuario_id} value={c.usuario_id}>{c.nome} (@{c.username})</option>
                    ))}
                  </select>
                </CampoMobile>
                <BotaoMobile variante="ghost" estilos={estilos} disabled={vinculandoConsultor || !temModuloConsultor} onClick={vincularConsultorCowData}>
                  {vinculandoConsultor ? "Salvando…" : "Vincular consultor"}
                </BotaoMobile>
                {consultoresCowData?.length === 0 && (
                  <p style={{ color: cor.mudo, fontSize: "0.72rem", marginTop: "0.4rem" }}>
                    Nenhum Consultor CowData disponível — cadastre um membro da Equipe CowData com cargo "Consultor" e crie o login dele em Equipe.
                  </p>
                )}
                {!temModuloConsultor && (
                  <p style={{ color: cor.mudo, fontSize: "0.72rem", marginTop: "0.4rem" }}>
                    Salve o plano e aprove o contrato primeiro — o vínculo só é aceito com o módulo Consultor ativo.
                  </p>
                )}
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <BotaoMobile estilos={estilos} disabled={salvando} onClick={salvarContrato}>{salvando ? "Salvando…" : "Salvar módulos/plano"}</BotaoMobile>
              {contrato.status !== "ativo" ? (
                <BotaoMobile variante="ghost" estilos={estilos} disabled={aprovando} onClick={aprovar}
                  style={{ borderColor: cor.verde, color: cor.verde }}>
                  <ShieldCheck size={14} /> {aprovando ? "Aprovando…" : "Aprovar/Fechar contrato"}
                </BotaoMobile>
              ) : (
                <BotaoMobile variante="ghost" estilos={estilos} disabled={aprovando} onClick={suspender}
                  style={{ borderColor: cor.vermelho, color: confirmarSuspender ? estilos.cor.bg : cor.vermelho, background: confirmarSuspender ? cor.vermelho : undefined }}>
                  <Ban size={14} /> {aprovando ? "Suspendendo…" : confirmarSuspender ? "Toque para confirmar" : "Suspender"}
                </BotaoMobile>
              )}
              {confirmarSuspender && (
                <button onClick={() => setConfirmarSuspender(false)} style={{ background: "none", border: "none", color: cor.mudo, fontSize: "0.75rem", cursor: "pointer" }}>Cancelar</button>
              )}
            </div>
          </SecaoAcordeaoMobile>
        )}

        {contrato && (
          <SecaoAcordeaoMobile titulo="Contrato assinado" cor={cor} aberta={aberta === "contrato"} onToggle={() => alternar("contrato")}>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginBottom: "0.7rem" }}>
              <BotaoMobile variante="ghost" estilos={estilos} disabled={baixandoModelo} onClick={baixarContrato}>
                <Download size={13} /> {baixandoModelo ? "Gerando…" : "Baixar contrato"}
              </BotaoMobile>
              <label style={{ ...estilos.btnGhost, width: "100%", justifyContent: "center", display: "flex", alignItems: "center", gap: "0.4rem", cursor: "pointer" }}>
                <Upload size={13} /> {enviandoAnexo ? "Enviando…" : "Anexar contrato assinado"}
                <input type="file" accept="application/pdf,image/*" style={{ display: "none" }} disabled={enviandoAnexo}
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) enviarAnexo(f); e.target.value = ""; }} />
              </label>
              <BotaoMobile variante="ghost" estilos={estilos} disabled={assinandoZapSign} onClick={assinarZapSign} style={{ borderColor: cor.dourado, color: cor.dourado }}>
                <PenLine size={13} /> {assinandoZapSign ? "Enviando ao ZapSign…" : "Assinar contrato (ZapSign)"}
              </BotaoMobile>
            </div>
            {assinaturaZapSign && (
              <p style={{ fontSize: "0.75rem", color: cor.mudo, marginBottom: "0.6rem" }}>
                Última solicitação ZapSign:{" "}
                <b style={{ color: assinaturaZapSign.status === "signed" ? cor.verde : assinaturaZapSign.status === "refused" ? cor.vermelho : cor.dourado }}>
                  {assinaturaZapSign.status === "signed" ? "assinado" : assinaturaZapSign.status === "refused" ? "recusado" : "pendente"}
                </b>
                {" "}({formatarData(assinaturaZapSign.criado_em)})
                {assinaturaZapSign.sign_url && assinaturaZapSign.status !== "signed" && (
                  <> — <a href={assinaturaZapSign.sign_url} target="_blank" rel="noreferrer" style={{ color: cor.dourado }}>reabrir link de assinatura</a></>
                )}
              </p>
            )}
            {anexos && anexos.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                {anexos.map((a) => (
                  <div key={a.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", fontSize: "0.78rem", border: `1px solid ${cor.borda}`, borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem" }}>
                    <button onClick={() => baixarAnexoContrato(a.id, a.nome_arquivo).catch((e: any) => setErro(e.message))}
                      style={{ display: "flex", alignItems: "center", gap: "0.35rem", color: cor.texto, background: "none", border: "none", padding: 0, cursor: "pointer", textAlign: "left", minWidth: 0 }}>
                      <FileText size={14} style={{ flexShrink: 0 }} />
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.nome_arquivo}</span>
                      <span style={{ color: cor.mudo, fontSize: "0.68rem", flexShrink: 0 }}>({formatarBytes(a.tamanho_bytes)})</span>
                    </button>
                    <button onClick={() => excluirAnexo(a.id)} title="Excluir anexo" style={{ background: "none", border: "none", color: cor.vermelho, cursor: "pointer", flexShrink: 0 }}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </SecaoAcordeaoMobile>
        )}

        {contrato && (
          <SecaoAcordeaoMobile titulo="Cobrança (Asaas)" cor={cor} aberta={aberta === "cobranca"} onToggle={() => alternar("cobranca")}>
            <CampoMobile label="Nome do pagador" estilos={estilos}>
              <input style={inputEstilo(estilos)} value={pagador.pagador_nome} onChange={(e) => setPagador((s) => ({ ...s, pagador_nome: e.target.value }))} />
            </CampoMobile>
            <CampoMobile label="CPF/CNPJ" estilos={estilos}>
              <input style={inputEstilo(estilos)} value={pagador.pagador_documento} onChange={(e) => setPagador((s) => ({ ...s, pagador_documento: maskCpfCnpj(e.target.value) }))} />
            </CampoMobile>
            <CampoMobile label="E-mail (opcional)" estilos={estilos}>
              <input style={inputEstilo(estilos)} value={pagador.pagador_email} onChange={(e) => setPagador((s) => ({ ...s, pagador_email: e.target.value }))} />
            </CampoMobile>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginBottom: "0.7rem" }}>
              <BotaoMobile variante="ghost" estilos={estilos} disabled={gerandoCobranca !== null} onClick={() => gerarCobranca("assinatura")}>
                <Repeat size={13} /> {gerandoCobranca === "assinatura" ? "Criando…" : "Assinatura mensal (Pix)"}
              </BotaoMobile>
              <BotaoMobile variante="ghost" estilos={estilos} disabled={gerandoCobranca !== null} onClick={() => gerarCobranca("semestral")} style={{ borderColor: cor.dourado, color: cor.dourado }}>
                <QrCode size={13} /> {gerandoCobranca === "semestral" ? "Gerando…" : "QR semestral (-20%)"}
              </BotaoMobile>
              <BotaoMobile variante="ghost" estilos={estilos} disabled={gerandoCobranca !== null} onClick={() => gerarCobranca("boleto")}>
                <Receipt size={13} /> {gerandoCobranca === "boleto" ? "Gerando…" : "Boleto"}
              </BotaoMobile>
            </div>
            {cobrancas && cobrancas.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                {cobrancas.map((c) => (
                  <div key={c.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", fontSize: "0.76rem", border: `1px solid ${cor.borda}`, borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem" }}>
                    <span>{c.tipo.replace("_", " ")} — R$ {c.valor.toFixed(2)} <span style={{ color: cor.mudo, fontSize: "0.68rem" }}>({formatarData(c.criado_em)})</span></span>
                    <span style={{ fontWeight: 700, color: c.status === "paga" ? cor.verde : cor.dourado, flexShrink: 0 }}>{c.status === "paga" ? "paga" : "aguardando"}</span>
                  </div>
                ))}
              </div>
            )}
          </SecaoAcordeaoMobile>
        )}

        {contrato && (
          <SecaoAcordeaoMobile titulo="Usuários vinculados" cor={cor} aberta={aberta === "usuarios"} onToggle={() => alternar("usuarios")}
            badge={<Users size={13} style={{ color: cor.mudo }} />}>
            <CampoMobile label="Username do usuário" estilos={estilos}>
              <input style={inputEstilo(estilos)} value={novoUsername} onChange={(e) => setNovoUsername(e.target.value)} />
            </CampoMobile>
            <CampoMobile label="Tipo" estilos={estilos}>
              <select style={inputEstilo(estilos)} value={novoPapel} onChange={(e) => setNovoPapel(e.target.value as any)}>
                {PAPEIS.map((p) => (
                  <option key={p.valor} value={p.valor} disabled={p.valor === "consultor" && !temModuloConsultor}>
                    {p.label}{p.valor === "consultor" && !temModuloConsultor ? " — requer plano Diamond" : ""}
                  </option>
                ))}
              </select>
            </CampoMobile>
            <BotaoMobile estilos={estilos} disabled={vinculando} onClick={vincular} style={{ marginBottom: "0.8rem" }}>
              <UserPlus size={13} /> {vinculando ? "Vinculando…" : "Vincular"}
            </BotaoMobile>
            {usuarios && usuarios.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                {usuarios.map((u) => (
                  <div key={u.usuario_id} style={{ border: `1px solid ${cor.borda}`, borderRadius: "var(--r-sm)", padding: "0.5rem 0.6rem" }}>
                    <div style={{ fontSize: "0.8rem", marginBottom: "0.3rem" }}>
                      {u.nome || u.username} <span style={{ color: cor.mudo, fontSize: "0.7rem" }}>(@{u.username})</span>
                      {u.contratante && <span style={{ marginLeft: "0.4rem", fontSize: "0.68rem", color: cor.dourado, fontWeight: 700 }}>Contratante</span>}
                      {u.consultor && <span style={{ marginLeft: "0.4rem", fontSize: "0.68rem", color: cor.verde, fontWeight: 700 }}>Consultor</span>}
                      {u.contador && <span style={{ marginLeft: "0.4rem", fontSize: "0.68rem", color: cor.doradoClaro, fontWeight: 700 }}>Contador</span>}
                      {!u.contratante && !u.consultor && !u.contador && <span style={{ marginLeft: "0.4rem", fontSize: "0.68rem", color: cor.mudo, fontWeight: 700 }}>Funcionário</span>}
                    </div>
                    {editandoVinculoId === u.usuario_id ? (
                      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                        <select style={{ ...inputEstilo(estilos), flex: 1 }} value={papelEditando} onChange={(e) => setPapelEditando(e.target.value as any)}>
                          {PAPEIS.map((p) => (
                            <option key={p.valor} value={p.valor} disabled={p.valor === "consultor" && !temModuloConsultor}>{p.label}</option>
                          ))}
                        </select>
                        <button onClick={() => salvarEdicaoVinculo(u.usuario_id)} disabled={salvandoVinculo} title="Salvar" style={{ background: "none", border: "none", color: cor.verde, cursor: "pointer" }}>
                          <Check size={16} />
                        </button>
                        <button onClick={() => setEditandoVinculoId(null)} title="Cancelar" style={{ background: "none", border: "none", color: cor.mudo, cursor: "pointer" }}>
                          <XIcon size={16} />
                        </button>
                      </div>
                    ) : (
                      <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                        <button onClick={() => abrirEdicaoVinculo(u)} title="Editar tipo de acesso" style={{ background: "none", border: "none", color: cor.mudo, cursor: "pointer" }}><Pencil size={14} /></button>
                        <button onClick={() => desvincular(u.usuario_id)} title="Desvincular" style={{ background: "none", border: "none", color: cor.vermelho, cursor: "pointer" }}><Trash2 size={14} /></button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </SecaoAcordeaoMobile>
        )}
      </CorpoMobilePainelCowData>
    </div>
  );
}
