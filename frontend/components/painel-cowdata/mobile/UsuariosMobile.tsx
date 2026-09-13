"use client";
// Usuários mobile do Painel CowData — mesma funcionalidade da tela desktop
// (app/painel-cowdata/usuarios/page.tsx: cria/edita login de operador de UMA
// fazenda-cliente escolhida explicitamente, sem precisar entrar nela via modo
// suporte), em navegação nativa pro app: escolhe a fazenda (busca + lista)
// e só depois vê/edita os usuários dela, em vez do <select> do desktop.
// Igual ao desktop, aqui NUNCA existe "aplicar em várias fazendas de uma
// vez" — login é sempre de uma fazenda só (pedido explícito do usuário) —
// por isso NÃO usa SeletorAlvoFazendas de ComumMobile.
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Check, Pencil } from "lucide-react";
import {
  fetchFazendasCadastroCowData, fetchPessoasUsuarioCowData, fetchUsuariosDaFazendaCowData,
  criarUsuarioDaFazendaCowData, editarUsuarioDaFazendaCowData,
  type FazendaCadastroCowData, type PessoaUsuarioCowData, type UsuarioCowData,
} from "@/lib/api";
import { usePainelCowDataEstilos, type CoresPainelCowData } from "@/lib/painelCowDataTema";
import {
  CabecalhoMobilePainelCowData, CorpoMobilePainelCowData, CampoBuscaMobile, LinhaListaMobile,
  SecaoAcordeaoMobile, useAcordeaoUnico, CampoMobile, BotaoMobile, inputEstilo,
} from "@/components/painel-cowdata/mobile/ComumMobile";

// Mesma lista de módulos da tela desktop (ver app/painel-cowdata/usuarios/page.tsx
// e app/usuarios/page.tsx) — precisa ficar em sincronia com MODULOS no
// backend (fazenda/auth.py).
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

export default function UsuariosMobile() {
  const estilos = usePainelCowDataEstilos();
  const { cor: COR } = estilos;

  const [fazendas, setFazendas] = useState<FazendaCadastroCowData[]>([]);
  const [erroFazendas, setErroFazendas] = useState<string | null>(null);
  const [buscaFazenda, setBuscaFazenda] = useState("");
  const [fazendaId, setFazendaId] = useState<number | null>(null);

  const [pessoas, setPessoas] = useState<PessoaUsuarioCowData[]>([]);
  const [usuarios, setUsuarios] = useState<UsuarioCowData[]>([]);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [mostrarInativos, setMostrarInativos] = useState(false);

  const [pessoaId, setPessoaId] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [papel, setPapel] = useState<"admin" | "operador">("operador");
  const [perms, setPerms] = useState<Set<string>>(new Set(TODOS));
  const [salvando, setSalvando] = useState(false);

  const { aberta, alternar } = useAcordeaoUnico();

  useEffect(() => { fetchFazendasCadastroCowData().then(setFazendas).catch((e) => setErroFazendas(e.message)); }, []);

  function carregar(fid: number) {
    setCarregando(true); setErro(null);
    Promise.all([fetchPessoasUsuarioCowData(fid), fetchUsuariosDaFazendaCowData(fid)])
      .then(([p, u]) => { setPessoas(p); setUsuarios(u); })
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  }

  function escolherFazenda(fid: number) {
    setFazendaId(fid);
    carregar(fid);
    setPessoaId(""); setUsername(""); setEmail(""); setSenha(""); setPapel("operador"); setPerms(new Set(TODOS));
    setMsg(null); setErro(null); setMostrarInativos(false);
  }

  function trocarFazenda() {
    setFazendaId(null);
    setPessoas([]); setUsuarios([]); setErro(null); setMsg(null);
  }

  const fazendasFiltradas = useMemo(
    () => fazendas.filter((f) => f.nome.toLowerCase().includes(buscaFazenda.toLowerCase())),
    [fazendas, buscaFazenda],
  );
  const fazendaAtual = useMemo(() => fazendas.find((f) => f.id === fazendaId) || null, [fazendas, fazendaId]);
  const pessoasDisponiveis = useMemo(() => pessoas.filter((p) => !p.tem_usuario), [pessoas]);
  const usuariosExibidos = useMemo(() => usuarios.filter((u) => mostrarInativos || u.ativo), [usuarios, mostrarInativos]);

  const escolherPessoa = (id: string) => {
    setPessoaId(id);
    const p = pessoas.find((pp) => String(pp.id) === id);
    setEmail(p?.email || "");
    if (!username) setUsername((p?.nome || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, ".").replace(/^\.+|\.+$/g, ""));
  };

  const toggle = (k: string) => setPerms((p) => { const s = new Set(p); s.has(k) ? s.delete(k) : s.add(k); return s; });

  const criar = async () => {
    if (fazendaId === null) return;
    setSalvando(true); setErro(null); setMsg(null);
    try {
      await criarUsuarioDaFazendaCowData(fazendaId, {
        pessoa_id: Number(pessoaId), username: username.trim(), senha, email: email.trim() || null,
        papel, permissoes: papel === "admin" ? TODOS : Array.from(perms),
      });
      setMsg(`Usuário "${username}" criado.`);
      setPessoaId(""); setUsername(""); setEmail(""); setSenha(""); setPapel("operador"); setPerms(new Set(TODOS));
      alternar("novo");
      carregar(fazendaId);
    } catch (e: any) { setErro(e.message); }
    finally { setSalvando(false); }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <CabecalhoMobilePainelCowData
        titulo="Usuários"
        subtitulo={fazendaId === null
          ? "Escolha a fazenda-cliente para criar ou editar um login. Diferente das outras seções, aqui o cadastro é sempre de uma fazenda por vez."
          : fazendaAtual?.nome}
        cor={COR}
      />
      <CorpoMobilePainelCowData>
        {fazendaId === null ? (
          <>
            {erroFazendas && <p style={{ color: COR.vermelho, fontSize: "0.82rem" }}>{erroFazendas}</p>}
            <CampoBuscaMobile valor={buscaFazenda} onChange={setBuscaFazenda} placeholder="Buscar fazenda…" cor={COR} />
            {fazendasFiltradas.length === 0 ? (
              <p style={{ color: COR.mudo, fontSize: "0.82rem" }}>Nenhuma fazenda encontrada.</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {fazendasFiltradas.map((f) => (
                  <LinhaListaMobile key={f.id} cor={COR} titulo={f.nome} onClick={() => escolherFazenda(f.id)} />
                ))}
              </div>
            )}
          </>
        ) : (
          <>
            <button onClick={trocarFazenda} style={{
              display: "flex", alignItems: "center", gap: "0.35rem", alignSelf: "flex-start",
              background: "none", border: "none", color: COR.doradoClaro, fontSize: "0.78rem", cursor: "pointer", padding: 0,
            }}>
              <ArrowLeft size={13} /> Trocar fazenda
            </button>

            {erro && <p style={{ color: COR.vermelho, fontSize: "0.82rem" }}>{erro}</p>}

            <SecaoAcordeaoMobile titulo="Novo usuário" aberta={aberta === "novo"} onToggle={() => alternar("novo")} cor={COR}>
              <CampoMobile label="Pessoa" estilos={estilos}>
                <select style={inputEstilo(estilos)} value={pessoaId} onChange={(e) => escolherPessoa(e.target.value)}>
                  <option value="">Selecione…</option>
                  {pessoasDisponiveis.map((p) => <option key={p.id} value={p.id}>{p.nome} — {p.tipo}</option>)}
                </select>
                <p style={{ fontSize: "0.64rem", color: COR.mudo, marginTop: "0.25rem" }}>
                  Só pessoas desta fazenda ainda sem login. Cadastre a pessoa em Configurações &gt; Cadastro &gt; Pessoas da própria fazenda antes.
                </p>
              </CampoMobile>
              <CampoMobile label="Usuário (login)" estilos={estilos}>
                <input style={inputEstilo(estilos)} value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" />
              </CampoMobile>
              <CampoMobile label="E-mail" estilos={estilos}>
                <input style={inputEstilo(estilos)} type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="preenchido a partir do cadastro da pessoa, editável" />
              </CampoMobile>
              <CampoMobile label="Senha" estilos={estilos}>
                <input style={inputEstilo(estilos)} type="text" value={senha} onChange={(e) => setSenha(e.target.value)} />
              </CampoMobile>
              <CampoMobile label="Tipo" estilos={estilos}>
                <select style={inputEstilo(estilos)} value={papel} onChange={(e) => setPapel(e.target.value as any)}>
                  <option value="admin">Administrador (acesso total + gerencia usuários)</option>
                  <option value="operador">Operador (você escolhe os módulos)</option>
                </select>
              </CampoMobile>
              {papel === "operador" && (
                <div style={{ marginBottom: "0.7rem" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.4rem", gap: "0.4rem" }}>
                    <label style={estilos.labelStyle}>Módulos liberados</label>
                  </div>
                  <div style={{ display: "flex", gap: "0.4rem", marginBottom: "0.5rem" }}>
                    <BotaoMobile variante="ghost" estilos={estilos} style={{ width: "auto", flex: 1, fontSize: "0.68rem", padding: "0.35rem 0.3rem" }} onClick={() => setPerms(new Set(TODOS))}>Acesso total</BotaoMobile>
                    <BotaoMobile variante="ghost" estilos={estilos} style={{ width: "auto", flex: 1, fontSize: "0.68rem", padding: "0.35rem 0.3rem" }} onClick={() => setPerms(new Set(TODOS.filter((k) => k !== "financeiro")))}>Sem financeiro</BotaoMobile>
                    <BotaoMobile variante="ghost" estilos={estilos} style={{ width: "auto", flex: 1, fontSize: "0.68rem", padding: "0.35rem 0.3rem" }} onClick={() => setPerms(new Set(["capa"]))}>Limpar</BotaoMobile>
                  </div>
                  <GradeModulos perms={perms} toggle={toggle} cor={COR} />
                </div>
              )}
              <BotaoMobile estilos={estilos} disabled={salvando || !username || !senha || !pessoaId} onClick={criar}>
                <Check size={15} /> Criar usuário
              </BotaoMobile>
              {msg && <p style={{ color: COR.verde, fontSize: "0.78rem", marginTop: "0.5rem" }}>{msg}</p>}
            </SecaoAcordeaoMobile>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.4rem" }}>
              <p style={{ fontSize: "0.75rem", fontWeight: 700, color: COR.texto, margin: 0 }}>
                Usuários desta fazenda {carregando && <span style={{ color: COR.mudo, fontWeight: 400 }}>· carregando…</span>}
              </p>
              <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.72rem", color: COR.mudo, cursor: "pointer" }}>
                <input type="checkbox" checked={mostrarInativos} onChange={(e) => setMostrarInativos(e.target.checked)} /> Incluir inativos
              </label>
            </div>

            {usuariosExibidos.length === 0 ? (
              <p style={{ fontSize: "0.8rem", color: COR.mudo }}>
                {usuarios.length === 0 ? "Nenhum usuário cadastrado ainda para esta fazenda." : "Nenhum usuário ativo — marque \"Incluir inativos\" para ver todos."}
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {usuariosExibidos.map((u) => (
                  <LinhaUsuarioMobile key={u.id} u={u} fazendaId={fazendaId}
                    aberto={aberta === String(u.id)} onToggle={() => alternar(String(u.id))}
                    onSalvo={() => { alternar(String(u.id)); carregar(fazendaId); }} />
                ))}
              </div>
            )}
          </>
        )}
      </CorpoMobilePainelCowData>
    </div>
  );
}

function GradeModulos({ perms, toggle, cor }: { perms: Set<string>; toggle: (k: string) => void; cor: CoresPainelCowData }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.35rem 0.6rem", border: `1px solid ${cor.borda}`, borderRadius: "var(--r-sm)", padding: "0.6rem" }}>
      {MODULOS.map((m) => (
        <label key={m.key} style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.76rem", color: cor.texto, opacity: m.key === "capa" ? 0.7 : 1 }}>
          <input type="checkbox" checked={perms.has(m.key)} disabled={m.key === "capa"} onChange={() => toggle(m.key)} /> {m.label}
        </label>
      ))}
    </div>
  );
}

function LinhaUsuarioMobile({ u, fazendaId, aberto, onToggle, onSalvo }: {
  u: UsuarioCowData; fazendaId: number; aberto: boolean; onToggle: () => void; onSalvo: () => void;
}) {
  const estilos = usePainelCowDataEstilos();
  const { cor: COR } = estilos;
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

  const badge = (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.68rem", flexShrink: 0 }}>
      <span style={{ color: COR.mudo }}>{u.pessoa_nome}</span>
      <span style={{ color: u.ativo ? COR.verde : COR.vermelho }}>{u.ativo ? "Ativo" : "Inativo"}</span>
    </div>
  );

  return (
    <SecaoAcordeaoMobile titulo={u.username} aberta={aberto} onToggle={onToggle} cor={COR} badge={badge}>
      <CampoMobile label="E-mail" estilos={estilos}>
        <input style={inputEstilo(estilos)} type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </CampoMobile>
      <CampoMobile label="Nova senha (deixe em branco para manter)" estilos={estilos}>
        <input style={inputEstilo(estilos)} type="text" value={senha} onChange={(e) => setSenha(e.target.value)} />
      </CampoMobile>
      <CampoMobile label="Tipo" estilos={estilos}>
        <select style={inputEstilo(estilos)} value={papel} onChange={(e) => setPapel(e.target.value as any)}>
          <option value="admin">Administrador (acesso total + gerencia usuários)</option>
          <option value="operador">Operador (você escolhe os módulos)</option>
        </select>
      </CampoMobile>
      {papel === "operador" && (
        <div style={{ marginBottom: "0.7rem" }}>
          <GradeModulos perms={perms} toggle={toggle} cor={COR} />
        </div>
      )}
      <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.82rem", color: COR.texto, marginBottom: "0.7rem" }}>
        <input type="checkbox" checked={ativo} onChange={(e) => setAtivo(e.target.checked)} /> Usuário ativo
      </label>
      {erro && <p style={{ color: COR.vermelho, fontSize: "0.78rem", marginBottom: "0.5rem" }}>{erro}</p>}
      <BotaoMobile estilos={estilos} disabled={salvando} onClick={salvar}>
        <Pencil size={13} /> {salvando ? "Salvando…" : "Salvar"}
      </BotaoMobile>
    </SecaoAcordeaoMobile>
  );
}
