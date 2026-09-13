"use client";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Users, Plus, Pencil, Trash2, AlertTriangle, Check, X, Search, FileText, Upload } from "lucide-react";
import {
  fetchPessoas, criarPessoa, atualizarPessoa, excluirPessoa, fetchTiposPessoa, criarTipoPessoa,
  CATEGORIAS_PESSOA_ANEXO, anexarArquivoPessoa, listarAnexosPessoa, excluirAnexoPessoa, urlAnexoPessoa, type AnexoPessoa,
  type PeriodicidadeValeAlimentacao, type RegimeValeAlimentacao, type FormaValeAlimentacao, ehAdmin,
} from "@/lib/api";
import { Modal } from "@/components/Modal";
import { maskTelefone, maskCpfCnpj, maskCep } from "@/lib/masks";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { CampoMoeda } from "@/components/CampoMoeda";
import { normalizarBusca as normalizar } from "@/lib/busca";

type Pessoa = {
  id: number; nome: string; tipos: string[]; telefones: string[]; emails: string[];
  cpf_cnpj: string | null; cep: string | null;
  observacoes: string | null; ativo: boolean; salario_base: number | null; data_admissao: string | null;
  rg: string | null; data_nascimento: string | null; genero: string | null; estado_civil: string | null;
  endereco_rua: string | null; endereco_numero: string | null; endereco_bairro: string | null;
  endereco_cidade: string | null; endereco_uf: string | null;
  vale_alimentacao: boolean;
  vale_alimentacao_valor: number | null;
  vale_alimentacao_periodicidade: PeriodicidadeValeAlimentacao | null;
  vale_alimentacao_regime: RegimeValeAlimentacao | null;
  vale_alimentacao_forma: FormaValeAlimentacao | null;
  vale_alimentacao_natureza_travada_salarial: boolean | null;
};
type Form = {
  nome: string; tipos: string[]; telefones: string[]; emails: string[]; cpfCnpj: string; cep: string; observacoes: string; ativo: boolean;
  salarioBase: string; dataAdmissao: string;
  rg: string; dataNascimento: string; genero: string; estadoCivil: string;
  enderecoRua: string; enderecoNumero: string; enderecoBairro: string; enderecoCidade: string; enderecoUf: string;
  // Vale-alimentação: CONFIGURAÇÃO do vínculo, não rubrica lançada mês a mês.
  // A folha lê estes quatro e gera a linha do holerite sozinha (ver
  // backend/fazenda/rules/vale_alimentacao.py).
  valeAlimentacao: boolean; valeAlimentacaoValor: string;
  valeAlimentacaoPeriodicidade: PeriodicidadeValeAlimentacao;
  valeAlimentacaoRegime: RegimeValeAlimentacao;
  // "" = ainda não escolhida. O servidor RECUSA salvar o benefício ligado sem
  // forma, e a tela não escolhe por ninguém: é dela que sai a resposta de se a
  // verba entra nas bases de INSS, FGTS, 13º e férias.
  valeAlimentacaoForma: FormaValeAlimentacao | "";
  valeAlimentacaoTravadaSalarial: boolean;
};
type AnexoStagedPessoa = { file: File; categoria: string; data_validade: string };
const formVazio: Form = {
  nome: "", tipos: ["Funcionário"], telefones: [], emails: [], cpfCnpj: "", cep: "", observacoes: "", ativo: true, salarioBase: "", dataAdmissao: "",
  rg: "", dataNascimento: "", genero: "", estadoCivil: "",
  enderecoRua: "", enderecoNumero: "", enderecoBairro: "", enderecoCidade: "", enderecoUf: "",
  // Nasce desligado e nos padrões conservadores do servidor ("mensal" não
  // multiplica por dias, "vencido" não desloca o benefício para outro mês).
  valeAlimentacao: false, valeAlimentacaoValor: "",
  valeAlimentacaoPeriodicidade: "mensal", valeAlimentacaoRegime: "vencido",
  // A forma NASCE VAZIA de propósito — ver o comentário do tipo acima.
  valeAlimentacaoForma: "", valeAlimentacaoTravadaSalarial: false,
};

// Obrigatórios para cadastrar (decisão jul/2026): nome, CPF e endereço
// completo. RG/data de nascimento/estado civil são coletados aqui mas só
// exigidos na hora de assinar um contrato — gênero nunca é obrigatório.
const ESTADOS_CIVIS = ["Solteiro(a)", "Casado(a)", "Divorciado(a)", "Viúvo(a)", "União estável"];
const UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"];

const inputStyle: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", fontSize: "0.82rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };
const buscaInputStyle: React.CSSProperties = { width: "100%", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.75rem 0.5rem 2rem", fontSize: "0.85rem" };

function paraPayload(f: Form) {
  const s = (v: string) => (v.trim() === "" ? undefined : v.trim());
  return {
    nome: f.nome.trim(), tipos: f.tipos,
    telefones: f.telefones.map((t) => t.trim()).filter(Boolean),
    emails: f.emails.map((e) => e.trim()).filter(Boolean),
    cpf_cnpj: s(f.cpfCnpj), cep: s(f.cep), observacoes: s(f.observacoes),
    ativo: f.ativo, salario_base: f.salarioBase.trim() === "" ? undefined : parseFloat(f.salarioBase),
    data_admissao: s(f.dataAdmissao),
    rg: s(f.rg), data_nascimento: s(f.dataNascimento), genero: s(f.genero), estado_civil: s(f.estadoCivil),
    endereco_rua: s(f.enderecoRua), endereco_numero: s(f.enderecoNumero), endereco_bairro: s(f.enderecoBairro),
    endereco_cidade: s(f.enderecoCidade), endereco_uf: s(f.enderecoUf),
    // Com o benefício DESLIGADO os outros três não vão: mandar valor/
    // periodicidade de um vale-alimentação desmarcado deixaria no cadastro um
    // resto de configuração que a próxima pessoa leria como "está ligado".
    vale_alimentacao: f.valeAlimentacao,
    vale_alimentacao_valor: f.valeAlimentacao && f.valeAlimentacaoValor.trim() !== ""
      ? parseFloat(f.valeAlimentacaoValor) : undefined,
    vale_alimentacao_periodicidade: f.valeAlimentacao ? f.valeAlimentacaoPeriodicidade : undefined,
    vale_alimentacao_regime: f.valeAlimentacao ? f.valeAlimentacaoRegime : undefined,
    vale_alimentacao_forma: f.valeAlimentacao && f.valeAlimentacaoForma !== ""
      ? f.valeAlimentacaoForma : undefined,
    // A trava só VIAJA quando quem está salvando é administrador: para todo
    // mundo mais o campo nem aparece na tela, e mandar `false` desligaria em
    // silêncio a proteção da OJ 413 de quem já a tinha. `undefined` no payload
    // é o que o servidor lê como "não mexe no que está gravado".
    vale_alimentacao_natureza_travada_salarial: ehAdmin() && f.valeAlimentacao
      ? f.valeAlimentacaoTravadaSalarial : undefined,
  };
}

export default function CadastroPessoas() {
  const [itens, setItens] = useState<Pessoa[] | null>(null);
  const [tipos, setTipos] = useState<{ id: number; nome: string; ativo: boolean }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [erroExclusao, setErroExclusao] = useState<string | null>(null);
  // O aviso de recusa mora no topo do card, mas o botão "Excluir" que o
  // dispara fica na LINHA da pessoa — numa lista com dezenas de nomes, a
  // explicação do backend ("há vínculo com 2 vales…") aparecia acima da
  // dobra e o clique parecia não ter feito nada. A recusa só cumpre o papel
  // se for lida, então o aviso se traz para a vista quando surge.
  const alertaExclusaoRef = useRef<HTMLDivElement | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<Form>(formVazio);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  // Inativos ficam ESCONDIDOS por padrão. Antes a lista trazia todo mundo com
  // um "(inativo)" cinza ao lado do nome, e quem desativava alguém continuava
  // vendo a pessoa ali para sempre — daí a vontade de "excluir" um cadastro
  // que o sistema (e a lei trabalhista) precisa guardar. Esconder é o que a
  // pessoa quer dizer com "sumir da lista"; o registro continua inteiro.
  const [mostrarInativos, setMostrarInativos] = useState(false);
  const [novoTipoAberto, setNovoTipoAberto] = useState(false);
  // Entrada animada do formulário inline (05/09/2026) — mesma técnica do
  // duplo requestAnimationFrame já usada em NovoItemEstoque.tsx: monta
  // fechado (.painel-expansivel) e só then liga `.painel-expansivel-aberto`,
  // pra CSS ter um estado inicial real de onde fazer a transição. Saída
  // continua instantânea (formulário raramente fica aberto tempo suficiente
  // pra a falta de animação de saída incomodar aqui).
  const [entradaConcluida, setEntradaConcluida] = useState(false);
  const animarEntrada = () => {
    setEntradaConcluida(false);
    requestAnimationFrame(() => requestAnimationFrame(() => setEntradaConcluida(true)));
  };

  // Documentos (RG, CPF, contratos, holerite, comprovantes...) — mesmo
  // padrão staged/existente do anexo de Pedido (frontend/app/pedidos/
  // page.tsx): arquivo novo fica "staged" e só sobe de fato depois que a
  // pessoa é salva (uma pessoa nova ainda não tem id).
  const [anexosStaged, setAnexosStaged] = useState<AnexoStagedPessoa[]>([]);
  const [anexosExistentes, setAnexosExistentes] = useState<AnexoPessoa[]>([]);
  // Erro de exclusão de DOCUMENTO — separado de `msg` (que fica lá embaixo,
  // junto dos botões Salvar/Cancelar): o "X" do documento fica no topo do
  // formulário, e num cadastro preenchido a resposta aparecia fora da tela.
  // Aqui o aviso nasce ao lado da própria lista de documentos.
  const [erroAnexo, setErroAnexo] = useState<string | null>(null);

  const carregar = () => fetchPessoas().then(setItens).catch((e) => setError(e.message));
  const carregarTipos = () => fetchTiposPessoa().then(setTipos).catch(() => {});
  useEffect(() => { carregar(); carregarTipos(); }, []);

  const abrirNovo = () => { setForm(formVazio); setEditando("novo"); setMsg(null); setErroAnexo(null); setAnexosStaged([]); setAnexosExistentes([]); animarEntrada(); };
  const abrirEdicao = (p: Pessoa) => {
    setForm({
      nome: p.nome, tipos: p.tipos.length ? p.tipos : ["Funcionário"], telefones: p.telefones ?? [], emails: p.emails ?? [],
      cpfCnpj: p.cpf_cnpj ?? "", cep: p.cep ?? "", observacoes: p.observacoes ?? "",
      ativo: p.ativo, salarioBase: p.salario_base != null ? String(p.salario_base) : "", dataAdmissao: p.data_admissao ?? "",
      rg: p.rg ?? "", dataNascimento: p.data_nascimento ?? "", genero: p.genero ?? "", estadoCivil: p.estado_civil ?? "",
      enderecoRua: p.endereco_rua ?? "", enderecoNumero: p.endereco_numero ?? "", enderecoBairro: p.endereco_bairro ?? "",
      enderecoCidade: p.endereco_cidade ?? "", enderecoUf: p.endereco_uf ?? "",
      valeAlimentacao: !!p.vale_alimentacao,
      valeAlimentacaoValor: p.vale_alimentacao_valor != null ? String(p.vale_alimentacao_valor) : "",
      valeAlimentacaoPeriodicidade: p.vale_alimentacao_periodicidade ?? "mensal",
      valeAlimentacaoRegime: p.vale_alimentacao_regime ?? "vencido",
      // Sem `?? "cartao"`: cadastro antigo (anterior ao campo) abre com a
      // escolha em branco, e é a recusa do servidor que obriga a preenchê-la.
      // Um padrão aqui esconderia justamente o que precisa ser decidido.
      valeAlimentacaoForma: p.vale_alimentacao_forma ?? "",
      valeAlimentacaoTravadaSalarial: !!p.vale_alimentacao_natureza_travada_salarial,
    });
    setEditando(p.id); setMsg(null); setErroAnexo(null);
    setAnexosStaged([]);
    listarAnexosPessoa(p.id).then(setAnexosExistentes).catch(() => setAnexosExistentes([]));
    animarEntrada();
  };
  const cancelar = () => { setEditando(null); setMsg(null); setErroAnexo(null); setAnexosStaged([]); setAnexosExistentes([]); };

  async function excluirAnexoExistente(id: number) {
    if (!window.confirm("Excluir este documento?")) return;
    setErroAnexo(null);
    try {
      await excluirAnexoPessoa(id);
      setAnexosExistentes((arr) => arr.filter((a) => a.id !== id));
    } catch (e: any) {
      setErroAnexo(e.message || "Não foi possível excluir o documento.");
    }
  }

  // Exclusão de fato (não só desativar) — bloqueada pelo backend com 409
  // quando há folha/férias/13º/rescisão/vale/empreitada/contrato/diária ou
  // login de usuário vinculado (ver excluir_pessoa em cadastro/pessoas.py),
  // orientando a desativar em vez de excluir nesse caso.
  const excluir = async (p: Pessoa) => {
    if (!window.confirm(`Excluir "${p.nome}"? Isso não pode ser desfeito.`)) return;
    setErroExclusao(null);
    try {
      await excluirPessoa(p.id);
      await carregar();
    } catch (e: any) {
      setErroExclusao(e.message || "Erro ao excluir");
      // Depois do render, não durante: o alerta só existe no DOM quando
      // `erroExclusao` já está no estado.
      requestAnimationFrame(() => alertaExclusaoRef.current?.scrollIntoView({ block: "center", behavior: "smooth" }));
    }
  };

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    if (!form.tipos.length) { setMsg("Selecione ao menos um tipo."); return; }
    // CPF/endereço NÃO bloqueiam o cadastro — Pessoa é o cadastro de RH usado
    // para qualquer funcionário/veterinário/diarista/empreiteiro, não só o
    // contratante do contrato CowData. Os campos ficam disponíveis para quem
    // quiser preencher (ver pessoas.py:_exigir_campos_obrigatorios).
    setSalvando(true); setMsg(null);
    try {
      const dados = paraPayload(form);
      let pessoaId: number;
      if (editando === "novo") pessoaId = (await criarPessoa(dados)).id;
      else if (typeof editando === "number") { await atualizarPessoa(editando, dados); pessoaId = editando; }
      else return;
      if (anexosStaged.length) {
        await Promise.all(anexosStaged.map((a) => anexarArquivoPessoa(pessoaId, a.file, a.categoria, a.data_validade || undefined)));
      }
      setEditando(null);
      setAnexosStaged([]);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const termoBusca = normalizar(busca.trim());
  const filtrados = (itens ?? []).filter((p) =>
    (mostrarInativos || p.ativo) &&
    (!termoBusca || normalizar(`${p.nome} ${p.tipos.join(" ")} ${(p.telefones ?? []).join(" ")} ${(p.emails ?? []).join(" ")}`).includes(termoBusca))
  );
  const inativosOcultos = (itens ?? []).filter((p) => !p.ativo).length;

  // Colunas derivadas (nome do 1º tipo/telefone/email) só para permitir
  // ordenar por clique no cabeçalho — telefones/emails viram lista na tela.
  const linhasOrdenaveis = useMemo(() => filtrados.map((p) => ({
    ...p, tipoOrdenacao: p.tipos.join(", "), telefoneOrdenacao: (p.telefones ?? [])[0] ?? "", emailOrdenacao: (p.emails ?? [])[0] ?? "",
  })), [filtrados]);
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(linhasOrdenaveis);

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><Users size={16} /> Pessoas</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Novo
        </button>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Funcionários, veterinários, zootecnistas, diaristas e prestadores de serviço ligados à fazenda — diferente de
        Fornecedores, pois entram na folha de pagamento, não em nota de compra. O salário base é usado para calcular
        o limite de 40% de desconto de vale.
      </p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {erroExclusao && (
        <div ref={alertaExclusaoRef} className="alert-critico mb-3"><AlertTriangle size={18} /><span>{erroExclusao}</span></div>
      )}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && (
        <div className={`painel-expansivel${entradaConcluida ? " painel-expansivel-aberto" : ""}`}>
          <FormItem form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
            tipos={tipos} onNovoTipo={() => setNovoTipoAberto(true)}
            anexosStaged={anexosStaged} setAnexosStaged={setAnexosStaged}
            anexosExistentes={anexosExistentes} onExcluirAnexoExistente={excluirAnexoExistente} erroAnexo={erroAnexo} />
        </div>
      )}

      {itens && (
        <>
          <div style={{ position: "relative", marginBottom: "0.8rem" }}>
            <Search size={14} style={{ position: "absolute", left: "0.65rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input style={buscaInputStyle} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar pessoa…" title="Buscar por nome, tipo, telefone ou email" />
          </div>
          {inativosOcultos > 0 && (
            <label style={{
              display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.8rem",
              fontSize: "0.8rem", color: "var(--text-muted)", cursor: "pointer",
            }}>
              <input type="checkbox" checked={mostrarInativos} onChange={(e) => setMostrarInativos(e.target.checked)} />
              Mostrar inativos ({inativosOcultos})
            </label>
          )}
          <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead>
              <tr>
                <ThOrdenavel label="Nome" campo="nome" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Tipo" campo="tipoOrdenacao" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Telefone" campo="telefoneOrdenacao" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Email" campo="emailOrdenacao" coluna={coluna} dir={dir} ordenar={ordenar} />
                <th></th>
              </tr>
            </thead>
            <tbody>
              {linhasOrdenadas.map((p) => (
                <Fragment key={p.id}>
                  <tr>
                    <td style={{ fontWeight: 700 }}>{p.nome}{!p.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                    <td style={{ fontSize: "0.78rem" }}>{p.tipos.join(", ")}</td>
                    <td style={{ fontSize: "0.78rem" }}>{p.telefones.length ? p.telefones.join(", ") : "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{p.emails.length ? p.emails.join(", ") : "—"}</td>
                    <td style={{ textAlign: "right" }}>
                      <div className="flex items-center justify-end gap-1">
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(p)}>
                          <Pencil size={13} /> Editar
                        </button>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem", color: "var(--red)" }} onClick={() => excluir(p)}>
                          <Trash2 size={13} /> Excluir
                        </button>
                      </div>
                    </td>
                  </tr>
                  {editando === p.id && (
                    <tr><td colSpan={5} style={{ padding: 0 }}>
                      <div className={`painel-expansivel${entradaConcluida ? " painel-expansivel-aberto" : ""}`}>
                        <FormItem form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
                          tipos={tipos} onNovoTipo={() => setNovoTipoAberto(true)}
                          anexosStaged={anexosStaged} setAnexosStaged={setAnexosStaged}
                          anexosExistentes={anexosExistentes} onExcluirAnexoExistente={excluirAnexoExistente} erroAnexo={erroAnexo} />
                      </div>
                    </td></tr>
                  )}
                </Fragment>
              ))}
              {!itens.length && !editando && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma pessoa cadastrada ainda.</td></tr>}
              {!!itens.length && !filtrados.length && (
                <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
                  {termoBusca
                    ? <>Nenhum resultado para “{busca}”{!mostrarInativos && inativosOcultos > 0 && " entre as pessoas ativas — marque “Mostrar inativos” para procurar também nelas"}.</>
                    : "Nenhuma pessoa ativa. Marque “Mostrar inativos” para ver as desativadas."}
                </td></tr>
              )}
            </tbody>
          </table>
          </div>
        </>
      )}

      {novoTipoAberto && (
        <Modal title="Adicionar tipo de pessoa" onClose={() => setNovoTipoAberto(false)} width="380px">
          <NovoTipoPessoa
            onCriado={(tipo) => {
              setForm((f) => ({ ...f, tipos: [...f.tipos, tipo.nome] }));
              carregarTipos();
              setNovoTipoAberto(false);
            }}
            onCancelar={() => setNovoTipoAberto(false)}
          />
        </Modal>
      )}
    </div>
  );
}

function NovoTipoPessoa({ onCriado, onCancelar }: { onCriado: (tipo: { id: number; nome: string }) => void; onCancelar: () => void }) {
  const [nome, setNome] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const salvar = async () => {
    if (!nome.trim()) { setErro("Nome é obrigatório."); return; }
    setSalvando(true); setErro(null);
    try {
      const tipo = await criarTipoPessoa(nome.trim());
      onCriado(tipo);
    } catch (e: any) {
      setErro(e.message || "Erro ao criar tipo");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div>
      <label style={labelStyle}>Nome do novo tipo</label>
      <input style={inputStyle} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ex.: Empreiteiro, Consultor…" autoFocus />
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.5rem" }}>{erro}</p>}
      <div className="flex items-center gap-2" style={{ marginTop: "1rem" }}>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onCancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );
}

// Editor de lista de contatos (telefones ou emails) — uma linha por valor,
// com botão de remover e "+ adicionar" — usado dentro do FormItem abaixo.
function ListaContatoInput({ label, valores, onChange, mask, placeholder }: {
  label: string; valores: string[]; onChange: (v: string[]) => void; mask?: (v: string) => string; placeholder?: string;
}) {
  const atualizar = (i: number, v: string) => onChange(valores.map((x, idx) => (idx === i ? (mask ? mask(v) : v) : x)));
  const remover = (i: number) => onChange(valores.filter((_, idx) => idx !== i));
  const adicionar = () => onChange([...valores, ""]);

  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <div className="space-y-1">
        {valores.map((v, i) => (
          <div key={i} className="flex items-center gap-1">
            <input style={inputStyle} value={v} placeholder={placeholder} onChange={(e) => atualizar(i, e.target.value)} />
            <button type="button" className="btn-ghost" title={`Remover ${label.toLowerCase()}`} style={{ padding: "0.3rem" }} onClick={() => remover(i)}>
              <X size={13} />
            </button>
          </div>
        ))}
        <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.2rem", padding: "0.1rem 0.4rem" }} onClick={adicionar}>
          <Plus size={12} /> Adicionar {label.toLowerCase()}
        </button>
      </div>
    </div>
  );
}

function FormItem({
  form, setForm, onSalvar, onCancelar, salvando, msg, tipos, onNovoTipo,
  anexosStaged, setAnexosStaged, anexosExistentes, onExcluirAnexoExistente, erroAnexo,
}: {
  form: Form; setForm: (f: Form) => void; onSalvar: () => void; onCancelar: () => void; salvando: boolean; msg: string | null;
  tipos: { id: number; nome: string; ativo: boolean }[]; onNovoTipo: () => void;
  anexosStaged: AnexoStagedPessoa[]; setAnexosStaged: (fn: (arr: AnexoStagedPessoa[]) => AnexoStagedPessoa[]) => void;
  anexosExistentes: AnexoPessoa[]; onExcluirAnexoExistente: (id: number) => void; erroAnexo: string | null;
}) {
  const toggleTipo = (t: string) =>
    setForm({ ...form, tipos: form.tipos.includes(t) ? form.tipos.filter((x) => x !== t) : [...form.tipos, t] });
  const tiposAtivos = tipos.filter((t) => t.ativo);
  const [categoriaAnexoPadrao, setCategoriaAnexoPadrao] = useState(CATEGORIAS_PESSOA_ANEXO[0]);
  const anexoInputRef = useRef<HTMLInputElement>(null);
  function adicionarAnexosStaged(files: File[]) {
    if (!files.length) return;
    setAnexosStaged((arr) => [...arr, ...files.map((file) => ({ file, categoria: categoriaAnexoPadrao, data_validade: "" }))]);
  }

  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
        <div><label style={labelStyle}>Nome</label><input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} /></div>
        <div style={{ gridColumn: "span 2" }}>
          <label style={labelStyle}>Tipo(s) — pode marcar mais de um</label>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1" style={{ marginTop: "0.2rem" }}>
            {tiposAtivos.map((t) => (
              <label key={t.id} className="flex items-center gap-1" style={{ fontSize: "0.78rem" }}>
                <input type="checkbox" checked={form.tipos.includes(t.nome)} onChange={() => toggleTipo(t.nome)} /> {t.nome}
              </label>
            ))}
            <button type="button" className="btn-ghost" title="Adicionar novo tipo de pessoa"
              style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.2rem", padding: "0.1rem 0.4rem" }}
              onClick={onNovoTipo}>
              <Plus size={12} /> Novo tipo
            </button>
          </div>
        </div>
        <ListaContatoInput label="Telefones" valores={form.telefones} onChange={(v) => setForm({ ...form, telefones: v })} mask={maskTelefone} />
        <ListaContatoInput label="Emails" valores={form.emails} onChange={(v) => setForm({ ...form, emails: v })} placeholder="nome@exemplo.com" />
        <div><label style={labelStyle}>CPF/CNPJ</label>
          <input style={inputStyle} value={form.cpfCnpj} onChange={(e) => setForm({ ...form, cpfCnpj: maskCpfCnpj(e.target.value) })} /></div>
        <div><label style={labelStyle}>RG</label>
          <input style={inputStyle} value={form.rg} onChange={(e) => setForm({ ...form, rg: e.target.value })} /></div>
        <div><label style={labelStyle}>Data de nascimento</label>
          <input type="date" style={inputStyle} value={form.dataNascimento} onChange={(e) => setForm({ ...form, dataNascimento: e.target.value })} /></div>
        <div><label style={labelStyle}>Gênero</label>
          <select style={inputStyle} value={form.genero} onChange={(e) => setForm({ ...form, genero: e.target.value })}>
            <option value="">Prefere não informar</option>
            <option value="Feminino">Feminino</option>
            <option value="Masculino">Masculino</option>
            <option value="Outro">Outro</option>
          </select></div>
        <div><label style={labelStyle}>Estado civil</label>
          <select style={inputStyle} value={form.estadoCivil} onChange={(e) => setForm({ ...form, estadoCivil: e.target.value })}>
            <option value="">—</option>
            {ESTADOS_CIVIS.map((e) => <option key={e} value={e}>{e}</option>)}
          </select></div>
        <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Rua</label>
          <input style={inputStyle} value={form.enderecoRua} onChange={(e) => setForm({ ...form, enderecoRua: e.target.value })} /></div>
        <div><label style={labelStyle}>Número</label>
          <input style={inputStyle} value={form.enderecoNumero} onChange={(e) => setForm({ ...form, enderecoNumero: e.target.value })} /></div>
        <div><label style={labelStyle}>Bairro</label>
          <input style={inputStyle} value={form.enderecoBairro} onChange={(e) => setForm({ ...form, enderecoBairro: e.target.value })} /></div>
        <div><label style={labelStyle}>Cidade</label>
          <input style={inputStyle} value={form.enderecoCidade} onChange={(e) => setForm({ ...form, enderecoCidade: e.target.value })} /></div>
        <div><label style={labelStyle}>UF</label>
          <select style={inputStyle} value={form.enderecoUf} onChange={(e) => setForm({ ...form, enderecoUf: e.target.value })}>
            <option value="">—</option>
            {UFS.map((uf) => <option key={uf} value={uf}>{uf}</option>)}
          </select></div>
        <div><label style={labelStyle}>CEP</label>
          <input style={inputStyle} value={form.cep} onChange={(e) => setForm({ ...form, cep: maskCep(e.target.value) })} /></div>
        <div><label style={labelStyle}>Salário base (R$)</label>
          <CampoMoeda style={inputStyle} value={Number(form.salarioBase) || 0} onChange={(v) => setForm({ ...form, salarioBase: v ? String(v) : "" })} /></div>
        <div><label style={labelStyle}>Data de admissão</label>
          <input type="date" style={inputStyle} value={form.dataAdmissao} onChange={(e) => setForm({ ...form, dataAdmissao: e.target.value })}
            title="Usada para calcular a folha proporcional do 1º mês de trabalho" /></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
        {/* Vale-alimentação — CONFIGURAÇÃO do vínculo, não rubrica lançada mês
            a mês: marcado aqui, a folha passa a gerar a verba sozinha em toda
            competência ainda não paga (ver rules/vale_alimentacao.py). Os três
            campos que dependem dele só aparecem quando está ligado — desligado
            eles não significam nada e só ocupariam a tela. */}
        <div className="flex items-end" style={{ gridColumn: "1 / -1" }}>
          <label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
            <input type="checkbox" checked={form.valeAlimentacao}
              onChange={(e) => setForm({ ...form, valeAlimentacao: e.target.checked })} /> Tem vale-alimentação</label></div>
        {form.valeAlimentacao && <>
          <div><label style={labelStyle}>Valor-base do vale-alimentação (R$)</label>
            <CampoMoeda style={inputStyle} value={Number(form.valeAlimentacaoValor) || 0}
              onChange={(v) => setForm({ ...form, valeAlimentacaoValor: v ? String(v) : "" })} /></div>
          <div><label style={labelStyle}>Diário ou mensal</label>
            <select style={inputStyle} value={form.valeAlimentacaoPeriodicidade}
              onChange={(e) => setForm({ ...form, valeAlimentacaoPeriodicidade: e.target.value as PeriodicidadeValeAlimentacao })}
              title="Diário multiplica o valor-base pelos dias da competência (a mesma contagem que a folha já usa no salário); mensal é o valor cheio">
              <option value="mensal">Mensal (valor cheio)</option>
              <option value="diario">Diário (valor × dias da competência)</option>
            </select></div>
          <div><label style={labelStyle}>Pagamento</label>
            <select style={inputStyle} value={form.valeAlimentacaoRegime}
              onChange={(e) => setForm({ ...form, valeAlimentacaoRegime: e.target.value as RegimeValeAlimentacao })}
              title="Para fins de competência: vencido sai na folha da própria competência; antecipado sai na folha da competência anterior">
              <option value="vencido">Vencido (na folha da própria competência)</option>
              <option value="antecipado">Antecipado (na folha da competência anterior)</option>
            </select></div>
          {/* A FORMA é o campo que decide se a verba entra ou não nas bases de
              INSS, FGTS, 13º e férias — ver
              backend/fazenda/rules/vale_alimentacao.py::natureza_do_vale_alimentacao.
              Nasce em branco e o servidor recusa salvar sem ela: escolher por
              conta própria aqui seria tirar da base do INSS uma verba que
              talvez tivesse de entrar, e o erro só apareceria anos depois. */}
          <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Como é pago</label>
            <select style={inputStyle} value={form.valeAlimentacaoForma}
              onChange={(e) => setForm({ ...form, valeAlimentacaoForma: e.target.value as FormaValeAlimentacao | "" })}
              title="É a forma de pagamento que define a natureza da verba — e, com ela, se o vale-alimentação entra nas bases de INSS, FGTS, 13º e férias">
              <option value="">— escolha —</option>
              <option value="cartao">Cartão ou ticket de alimentação</option>
              <option value="in_natura">Refeição servida na fazenda</option>
              <option value="dinheiro">Dinheiro, junto do salário</option>
            </select></div>
          {form.valeAlimentacaoForma === "cartao" && (
            <p style={{ gridColumn: "1 / -1", fontSize: "0.68rem", color: "var(--text-muted)", margin: 0 }}>
              Natureza indenizatória: fora das bases de INSS, FGTS, 13º e férias — com ou sem inscrição no PAT
              (OJ 133 da SDI-1 do TST; Solução de Consulta COSIT nº 35/2019 da Receita Federal).
            </p>
          )}
          {form.valeAlimentacaoForma === "in_natura" && (
            <p style={{ gridColumn: "1 / -1", fontSize: "0.68rem", color: "var(--text-muted)", margin: 0 }}>
              Refeição fornecida in natura é <strong>salário-utilidade</strong> e <strong>integra</strong> INSS, FGTS,
              13º e férias (CLT, art. 458, caput) — <em>salvo</em> se a fazenda for inscrita no PAT (OJ 133 da SDI-1
              do TST). Marque a inscrição no PAT em Configurações &gt; Parâmetros &gt; Folha de pagamento / RH.
            </p>
          )}
          {/* Dinheiro AVISA e não bloqueia: a decisão é do empregador, e travar
              o cadastro só esconderia do holerite um pagamento que está
              acontecendo de qualquer jeito. As duas consequências são
              independentes — uma é tributária, a outra é uma infração
              autônoma. */}
          {form.valeAlimentacaoForma === "dinheiro" && (
            <div className="alert-critico" style={{ gridColumn: "1 / -1", fontSize: "0.72rem", alignItems: "flex-start" }}>
              <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: "0.1rem" }} />
              <span>
                Pagar o vale-alimentação em dinheiro tem duas consequências, e elas são independentes:
                <br />1. a verba passa a ter <strong>natureza salarial</strong> e <strong>integra as bases de INSS,
                FGTS, 13º e férias</strong> — a exclusão do art. 457, §2º, da CLT vale “vedado seu pagamento em
                dinheiro”;
                <br />2. é <strong>infração à Lei 14.442/2022</strong>, que proíbe o pagamento em dinheiro e o saque
                do saldo, com <strong>multa de R$ 5.000 a R$ 50.000</strong>, dobrada em caso de reincidência.
                <br />O cadastro não bloqueia a escolha — a decisão é sua, e o holerite passará a mostrar a
                incidência.
              </span>
            </div>
          )}
          {/* A trava da OJ 413 só aparece para administrador: ela é o único
              campo do cadastro que aumenta a carga de INSS/FGTS de um
              funcionário específico contra o que a forma diria — e o único
              que, desligado por engano, tira de alguém uma proteção que a
              jurisprudência lhe deu. O servidor recusa a alteração vinda de
              quem não é administrador; esconder é só o outro lado da mesma
              regra. */}
          {ehAdmin() && (
            <div style={{ gridColumn: "1 / -1" }}>
              <label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
                <input type="checkbox" checked={form.valeAlimentacaoTravadaSalarial}
                  onChange={(e) => setForm({ ...form, valeAlimentacaoTravadaSalarial: e.target.checked })} />
                Já recebia o vale-alimentação como salário (mantém a natureza salarial)
              </label>
              <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", margin: "0.2rem 0 0" }}>
                Marque quando este funcionário <strong>já vinha recebendo</strong> o benefício com natureza salarial
                antes de a fazenda mudar a forma de pagamento ou aderir ao PAT. Nesse caso a natureza salarial
                <strong> não se perde</strong>, qualquer que seja a forma escolhida acima — mudá-la depois seria
                alteração contratual lesiva (OJ 413 da SDI-1 do TST; CLT, art. 468). Vale só para quem já recebia:
                quem for contratado daqui em diante segue a forma de pagamento.
              </p>
            </div>
          )}
          <p style={{ gridColumn: "1 / -1", fontSize: "0.68rem", color: "var(--text-muted)", margin: 0 }}>
            A folha inclui o vale-alimentação sozinha no holerite das competências ainda não pagas — não é preciso
            lançar nada mês a mês. A contagem de dias do vale diário (corridos, úteis ou trabalhados), a
            proporcionalidade do mês de admissão e a inscrição no PAT ficam em Configurações &gt; Parâmetros &gt;
            Folha de pagamento / RH.
          </p>
        </>}
        <div style={{ gridColumn: "1 / -1" }}><label style={labelStyle}>Observações</label>
          <textarea style={{ ...inputStyle, minHeight: "2.4rem" }} value={form.observacoes} onChange={(e) => setForm({ ...form, observacoes: e.target.value })} /></div>
      </div>
      <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "-0.4rem", marginBottom: "0.6rem" }}>
        CPF, RG, data de nascimento, estado civil e endereço não bloqueiam o cadastro — ficam disponíveis para preencher agora e valem para o contrato mais tarde.
      </p>

      <div style={{ marginBottom: "0.8rem" }}>
        <label style={{ ...labelStyle, margin: "0 0 0.3rem", display: "block" }}>Documentos (RG, CPF, contratos, holerite, comprovantes...)</label>
        {anexosExistentes.length > 0 && (
          <ul style={{ marginBottom: "0.5rem", fontSize: "0.78rem", listStyle: "none", padding: 0, display: "flex", flexDirection: "column", gap: "0.3rem" }}>
            {anexosExistentes.map((a) => (
              <li key={a.id} className="card" style={{ padding: "0.4rem 0.6rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <FileText size={13} style={{ flexShrink: 0, color: "var(--dourado-light)" }} />
                <a href={urlAnexoPessoa(a.id)} target="_blank" rel="noreferrer" style={{ color: "var(--dourado-light)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {a.nome_arquivo}
                </a>
                <span style={{ color: "var(--text-muted)", flexShrink: 0 }}>{a.categoria}</span>
                {a.data_validade && <span style={{ color: "var(--amber)", flexShrink: 0 }}>válido até {a.data_validade.split("-").reverse().join("/")}</span>}
                <button type="button" className="btn-ghost" title="Excluir documento" onClick={() => onExcluirAnexoExistente(a.id)} style={{ padding: "0.1rem 0.3rem", flexShrink: 0 }}>
                  <X size={12} style={{ color: "var(--red)" }} />
                </button>
              </li>
            ))}
          </ul>
        )}
        {erroAnexo && (
          <p style={{ color: "var(--red)", fontSize: "0.78rem", marginBottom: "0.5rem" }}>{erroAnexo}</p>
        )}
        <div
          onDrop={(e) => { e.preventDefault(); adicionarAnexosStaged(Array.from(e.dataTransfer.files || [])); }}
          onDragOver={(e) => e.preventDefault()}
          className="card"
          style={{ border: "1px dashed var(--border)", background: "var(--surface)", padding: "0.7rem", textAlign: "center" }}
        >
          <div className="flex items-center justify-center gap-2" style={{ flexWrap: "wrap" }}>
            <FileText size={15} style={{ color: "var(--dourado-light)" }} />
            <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Arraste um documento aqui, ou</span>
            <select style={{ ...inputStyle, width: "auto", fontSize: "0.76rem" }} value={categoriaAnexoPadrao} onChange={(e) => setCategoriaAnexoPadrao(e.target.value)}>
              {CATEGORIAS_PESSOA_ANEXO.map((c) => <option key={c}>{c}</option>)}
            </select>
            <button type="button" className="btn-ghost" style={{ fontSize: "0.76rem" }} onClick={() => anexoInputRef.current?.click()}>
              <Upload size={12} /> selecionar arquivo(s)
            </button>
          </div>
          <input ref={anexoInputRef} type="file" multiple accept="application/pdf,image/jpeg,image/png"
            onChange={(e) => { adicionarAnexosStaged(Array.from(e.target.files || [])); e.target.value = ""; }}
            style={{ display: "none" }} />
          {anexosStaged.length > 0 && (
            <ul style={{ marginTop: "0.5rem", textAlign: "left", fontSize: "0.76rem", listStyle: "none", padding: 0 }}>
              {anexosStaged.map((a, i) => (
                <li key={i} className="card" style={{ padding: "0.4rem 0.5rem", marginBottom: "0.35rem", background: "var(--surface-2)" }}>
                  <div className="flex items-center justify-between" style={{ gap: "0.4rem" }}>
                    <a href={URL.createObjectURL(a.file)} target="_blank" rel="noreferrer" style={{ color: "var(--dourado-light)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {a.file.name}
                    </a>
                    <button type="button" className="btn-ghost" title="Remover" onClick={() => setAnexosStaged((arr) => arr.filter((_, j) => j !== i))} style={{ padding: "0.1rem 0.3rem", flexShrink: 0 }}>
                      <X size={12} style={{ color: "var(--red)" }} />
                    </button>
                  </div>
                  <div className="grid grid-cols-2 gap-2" style={{ marginTop: "0.3rem" }}>
                    <select style={{ ...inputStyle, fontSize: "0.74rem", padding: "0.25rem 0.4rem" }} value={a.categoria} title="Categoria deste documento"
                      onChange={(e) => setAnexosStaged((arr) => arr.map((x, j) => j === i ? { ...x, categoria: e.target.value } : x))}>
                      {CATEGORIAS_PESSOA_ANEXO.map((c) => <option key={c}>{c}</option>)}
                    </select>
                    <input type="date" style={{ ...inputStyle, fontSize: "0.74rem", padding: "0.25rem 0.4rem" }} title="Data de validade — opcional"
                      value={a.data_validade} onChange={(e) => setAnexosStaged((arr) => arr.map((x, j) => j === i ? { ...x, data_validade: e.target.value } : x))} />
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
            Validade opcional — preencha só quando fizer sentido (ex.: contrato por prazo determinado). Quando preenchida, a Agenda avisa 15 dias antes do vencimento.
          </p>
        </div>
      </div>

      {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onSalvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onCancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );
}
