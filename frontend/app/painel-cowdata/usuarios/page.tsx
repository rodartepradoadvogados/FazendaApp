"use client";
// Painel CowData > Usuários — cria/edita login de operador de UMA
// fazenda-cliente escolhida explicitamente, sem precisar entrar nela via
// modo suporte (ver backend/fazenda/api/routers/painel_cowdata_usuarios.py).
// Diferente de Cadastros globais/Touros/Farmácia: aqui NUNCA se "aplica em
// várias fazendas de uma vez" — login é sempre de uma fazenda só, por
// natureza (pedido explícito do usuário).
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, ChevronDown, ChevronRight, Pencil, UserPlus, Users } from "lucide-react";
import {
  fetchFazendasCadastroCowData, fetchPessoasUsuarioCowData, fetchUsuariosDaFazendaCowData,
  criarUsuarioDaFazendaCowData, editarUsuarioDaFazendaCowData,
  type FazendaCadastroCowData, type PessoaUsuarioCowData, type UsuarioCowData,
} from "@/lib/api";
import { usePainelCowDataEstilos } from "@/lib/painelCowDataTema";

// Mesma lista de módulos da tela da fazenda (Configurações > Cadastro >
// Pessoas > Controle de Acesso, ver app/usuarios/page.tsx) — precisa ficar
// em sincronia com MODULOS no backend (fazenda/auth.py).
const MODULOS = [
  { key: "capa", label: "Capa" }, { key: "indicadores", label: "Indicadores" }, { key: "agenda", label: "Agenda" },
  { key: "lancamentos", label: "Lançamentos" }, { key: "reproducao", label: "Reprodução" }, { key: "analise", label: "Análise Repr." },
  { key: "vet", label: "Agenda Reprodutiva" },
  { key: "rebanho", label: "Rebanho" }, { key: "producao", label: "Produção" }, { key: "alimentacao", label: "Alimentação" },
  { key: "sanidade", label: "Sanidade" }, { key: "recria", label: "Recria" }, { key: "financeiro", label: "Financeiro" }, { key: "estoque", label: "Sanidade/Estoque" },
  { key: "pedidos", label: "Pedidos" },
  { key: "parametros", label: "Parâmetros" }, { key: "upload", label: "Upload" },
];
const TODOS = MODULOS.map((m) => m.key);

export default function UsuariosPorFazendaCowData() {
  const { cor: COR, inputStyle, labelStyle, btnPrimario, btnGhost } = usePainelCowDataEstilos();
  const [fazendas, setFazendas] = useState<FazendaCadastroCowData[]>([]);
  const [fazendaId, setFazendaId] = useState<number | "">("");
  const [pessoas, setPessoas] = useState<PessoaUsuarioCowData[]>([]);
  const [usuarios, setUsuarios] = useState<UsuarioCowData[]>([]);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [pessoaId, setPessoaId] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [papel, setPapel] = useState<"admin" | "operador">("operador");
  const [perms, setPerms] = useState<Set<string>>(new Set(TODOS));
  const [salvando, setSalvando] = useState(false);

  const [editandoId, setEditandoId] = useState<number | null>(null);

  useEffect(() => { fetchFazendasCadastroCowData().then(setFazendas).catch((e) => setErro(e.message)); }, []);

  function carregar(fid: number) {
    setCarregando(true); setErro(null);
    Promise.all([fetchPessoasUsuarioCowData(fid), fetchUsuariosDaFazendaCowData(fid)])
      .then(([p, u]) => { setPessoas(p); setUsuarios(u); })
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  }
  useEffect(() => {
    if (fazendaId === "") return;
    carregar(fazendaId);
    setPessoaId(""); setUsername(""); setEmail(""); setSenha(""); setPapel("operador"); setPerms(new Set(TODOS)); setMsg(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fazendaId]);

  const pessoasDisponiveis = useMemo(() => pessoas.filter((p) => !p.tem_usuario), [pessoas]);

  const escolherPessoa = (id: string) => {
    setPessoaId(id);
    const p = pessoas.find((pp) => String(pp.id) === id);
    setEmail(p?.email || "");
    if (!username) setUsername((p?.nome || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, ".").replace(/^\.+|\.+$/g, ""));
  };

  const toggle = (k: string) => setPerms((p) => { const s = new Set(p); s.has(k) ? s.delete(k) : s.add(k); return s; });

  const criar = async () => {
    if (fazendaId === "") return;
    setSalvando(true); setErro(null); setMsg(null);
    try {
      await criarUsuarioDaFazendaCowData(fazendaId, {
        pessoa_id: Number(pessoaId), username: username.trim(), senha, email: email.trim() || null,
        papel, permissoes: papel === "admin" ? TODOS : Array.from(perms),
      });
      setMsg(`Usuário "${username}" criado.`);
      setPessoaId(""); setUsername(""); setEmail(""); setSenha(""); setPapel("operador"); setPerms(new Set(TODOS));
      carregar(fazendaId);
    } catch (e: any) { setErro(e.message); }
    finally { setSalvando(false); }
  };

  return (
    <div>
      <div className="flex items-center gap-2 mb-1">
        <Users size={18} style={{ color: COR.dourado }} />
        <h1 style={{ fontSize: "1.2rem", fontWeight: 700, color: COR.texto, margin: 0 }}>Usuários</h1>
      </div>
      <p style={{ fontSize: "0.82rem", color: COR.mudo, marginBottom: "1rem" }}>
        Crie ou edite o login de um operador de uma fazenda-cliente específica, sem precisar entrar nela via Suporte.
        Diferente das outras seções deste menu, aqui o cadastro é sempre de uma fazenda por vez.
      </p>

      <div style={{ marginBottom: "1.1rem", maxWidth: 360 }}>
        <label style={labelStyle}>Fazenda</label>
        <select style={{ ...inputStyle, width: "100%" }} value={fazendaId} onChange={(e) => setFazendaId(e.target.value ? Number(e.target.value) : "")}>
          <option value="">Selecione a fazenda…</option>
          {fazendas.map((f) => <option key={f.id} value={f.id}>{f.nome}</option>)}
        </select>
      </div>

      {erro && <p style={{ color: COR.vermelho, fontSize: "0.82rem", marginBottom: "0.8rem", display: "flex", alignItems: "center", gap: "0.4rem" }}><AlertTriangle size={14} /> {erro}</p>}

      {fazendaId !== "" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "1rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.85rem", fontWeight: 700, color: COR.texto, marginBottom: "0.8rem" }}>
              <UserPlus size={14} /> Novo usuário
            </div>
            <div className="space-y-3">
              <div>
                <label style={labelStyle}>Pessoa</label>
                <select style={{ ...inputStyle, width: "100%" }} value={pessoaId} onChange={(e) => escolherPessoa(e.target.value)}>
                  <option value="">Selecione…</option>
                  {pessoasDisponiveis.map((p) => <option key={p.id} value={p.id}>{p.nome} — {p.tipo}</option>)}
                </select>
                <p style={{ fontSize: "0.64rem", color: COR.mudo, marginTop: "0.25rem" }}>
                  Só pessoas desta fazenda ainda sem login. Cadastre a pessoa em Configurações &gt; Cadastro &gt; Pessoas da própria fazenda antes.
                </p>
              </div>
              <div><label style={labelStyle}>Usuário (login)</label><input style={{ ...inputStyle, width: "100%" }} value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" /></div>
              <div><label style={labelStyle}>E-mail</label><input style={{ ...inputStyle, width: "100%" }} type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="preenchido a partir do cadastro da pessoa, editável" /></div>
              <div><label style={labelStyle}>Senha</label><input style={{ ...inputStyle, width: "100%" }} type="text" value={senha} onChange={(e) => setSenha(e.target.value)} /></div>
              <div>
                <label style={labelStyle}>Tipo</label>
                <select style={{ ...inputStyle, width: "100%" }} value={papel} onChange={(e) => setPapel(e.target.value as any)}>
                  <option value="admin">Administrador (acesso total + gerencia usuários)</option>
                  <option value="operador">Operador (você escolhe os módulos)</option>
                </select>
              </div>
              {papel === "operador" && (
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label style={labelStyle}>Módulos liberados</label>
                    <div className="flex gap-2">
                      <button style={btnGhost} onClick={() => setPerms(new Set(TODOS))}>Acesso total</button>
                      <button style={btnGhost} onClick={() => setPerms(new Set(TODOS.filter((k) => k !== "financeiro")))}>Sem financeiro</button>
                      <button style={btnGhost} onClick={() => setPerms(new Set(["capa"]))}>Limpar</button>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-1" style={{ border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "0.5rem" }}>
                    {MODULOS.map((m) => (
                      <label key={m.key} className="flex items-center gap-2" style={{ fontSize: "0.78rem", color: COR.texto, opacity: m.key === "capa" ? 0.7 : 1 }}>
                        <input type="checkbox" checked={perms.has(m.key)} disabled={m.key === "capa"} onChange={() => toggle(m.key)} /> {m.label}
                      </label>
                    ))}
                  </div>
                </div>
              )}
              <button style={{ ...btnPrimario, width: "100%", justifyContent: "center", opacity: salvando || !username || !senha || !pessoaId ? 0.6 : 1 }}
                onClick={criar} disabled={salvando || !username || !senha || !pessoaId}>
                <Check size={15} /> Criar usuário
              </button>
              {msg && <p style={{ color: COR.verde, fontSize: "0.78rem" }}>{msg}</p>}
            </div>
          </div>

          <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "1rem" }}>
            <div style={{ fontSize: "0.85rem", fontWeight: 700, color: COR.texto, marginBottom: "0.8rem" }}>
              Usuários desta fazenda {carregando && <span style={{ color: COR.mudo, fontWeight: 400 }}>· carregando…</span>}
            </div>
            {usuarios.length === 0 ? (
              <p style={{ fontSize: "0.8rem", color: COR.mudo }}>Nenhum usuário cadastrado ainda para esta fazenda.</p>
            ) : (
              <div className="space-y-2">
                {usuarios.map((u) => (
                  <LinhaUsuario key={u.id} u={u} fazendaId={fazendaId as number} aberto={editandoId === u.id}
                    onAbrir={() => setEditandoId(editandoId === u.id ? null : u.id)}
                    onSalvo={() => { setEditandoId(null); carregar(fazendaId as number); }} />
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function LinhaUsuario({ u, fazendaId, aberto, onAbrir, onSalvo }: {
  u: UsuarioCowData; fazendaId: number; aberto: boolean; onAbrir: () => void; onSalvo: () => void;
}) {
  const { cor: COR, inputStyle, labelStyle, btnPrimario } = usePainelCowDataEstilos();
  const [papel, setPapel] = useState<"admin" | "operador">(u.papel);
  const [perms, setPerms] = useState<Set<string>>(new Set(u.papel === "admin" ? TODOS : u.permissoes));
  const [ativo, setAtivo] = useState(u.ativo);
  const [senha, setSenha] = useState("");
  const [email, setEmail] = useState(u.email || "");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const toggle = (k: string) => setPerms((p) => { const s = new Set(p); s.has(k) ? s.delete(k) : s.add(k); return s; });

  const salvar = async () => {
    setSalvando(true); setErro(null);
    try {
      await editarUsuarioDaFazendaCowData(fazendaId, u.id, {
        papel, ativo, email: email.trim() || null, permissoes: papel === "admin" ? TODOS : Array.from(perms),
        ...(senha ? { senha } : {}),
      });
      onSalvo();
    } catch (e: any) { setErro(e.message); }
    finally { setSalvando(false); }
  };

  return (
    <div style={{ border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", overflow: "hidden" }}>
      <button onClick={onAbrir} style={{
        width: "100%", display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.55rem 0.7rem",
        background: "rgba(255,255,255,0.02)", border: "none", cursor: "pointer", color: COR.texto, textAlign: "left",
      }}>
        {aberto ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span style={{ fontWeight: 700, fontSize: "0.84rem" }}>{u.username}</span>
        <span style={{ fontSize: "0.72rem", color: COR.mudo }}>{u.pessoa_nome}</span>
        <span style={{ marginLeft: "auto", fontSize: "0.7rem", color: u.ativo ? COR.verde : COR.vermelho }}>
          {u.ativo ? "Ativo" : "Inativo"}
        </span>
        <span style={{ fontSize: "0.7rem", color: COR.mudo }}>{u.papel === "admin" ? "Administrador" : `${u.permissoes.length} módulos`}</span>
      </button>
      {aberto && (
        <div style={{ padding: "0.8rem", borderTop: `1px solid ${COR.borda}` }} className="space-y-3">
          <div><label style={labelStyle}>E-mail</label><input style={{ ...inputStyle, width: "100%" }} type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          <div><label style={labelStyle}>Nova senha (deixe em branco para manter)</label><input style={{ ...inputStyle, width: "100%" }} type="text" value={senha} onChange={(e) => setSenha(e.target.value)} /></div>
          <div>
            <label style={labelStyle}>Tipo</label>
            <select style={{ ...inputStyle, width: "100%" }} value={papel} onChange={(e) => setPapel(e.target.value as any)}>
              <option value="admin">Administrador (acesso total + gerencia usuários)</option>
              <option value="operador">Operador (você escolhe os módulos)</option>
            </select>
          </div>
          {papel === "operador" && (
            <div className="grid grid-cols-2 gap-1" style={{ border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "0.5rem" }}>
              {MODULOS.map((m) => (
                <label key={m.key} className="flex items-center gap-2" style={{ fontSize: "0.78rem", color: COR.texto, opacity: m.key === "capa" ? 0.7 : 1 }}>
                  <input type="checkbox" checked={perms.has(m.key)} disabled={m.key === "capa"} onChange={() => toggle(m.key)} /> {m.label}
                </label>
              ))}
            </div>
          )}
          <label className="flex items-center gap-2" style={{ fontSize: "0.82rem", color: COR.texto }}>
            <input type="checkbox" checked={ativo} onChange={(e) => setAtivo(e.target.checked)} /> Usuário ativo
          </label>
          {erro && <p style={{ color: COR.vermelho, fontSize: "0.78rem" }}>{erro}</p>}
          <button style={{ ...btnPrimario, opacity: salvando ? 0.6 : 1 }} onClick={salvar} disabled={salvando}>
            <Pencil size={13} /> {salvando ? "Salvando…" : "Salvar"}
          </button>
        </div>
      )}
    </div>
  );
}
