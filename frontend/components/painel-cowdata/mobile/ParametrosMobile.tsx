"use client";
// Parâmetros do Painel CowData, versão mobile-nativa — mesma fonte de dados
// e mesma mecânica de app/painel-cowdata/parametros/page.tsx (metas/manejo/
// agenda/RH/financeiro em ParametroFazenda, aplicáveis a todas as
// fazendas-cliente de uma vez ou só às selecionadas), só que em navegação de
// acordeão (1 grupo aberto por vez) em vez das abas horizontais do desktop —
// ver estudo /design aprovado em 05/09/2026. "Aplicar em todas as fazendas
// ativas" continua literal — sobrescreve inclusive quem já personalizou — e
// por isso o aviso do desktop é reproduzido aqui perto do seletor, não só na
// legenda do topo. Não inclui a aba "Parâmetros financeiros" da fazenda
// (contas correntes, plano de contas, centro de custo) — aquilo é dado de
// identidade por fazenda, nunca faz sentido replicar.
import { useEffect, useState } from "react";
import { Check, Pencil } from "lucide-react";
import {
  fetchFazendasParametroCowData, fetchParametrosCowData, aplicarParametroCowData,
  type FazendaCadastroCowData, type ItemParametroCowData,
} from "@/lib/api";
import { usePainelCowDataEstilos } from "@/lib/painelCowDataTema";
import {
  CabecalhoMobilePainelCowData, CorpoMobilePainelCowData, SecaoAcordeaoMobile, useAcordeaoUnico,
  SeletorAlvoFazendas, inputEstilo,
} from "@/components/painel-cowdata/mobile/ComumMobile";

type Estilos = ReturnType<typeof usePainelCowDataEstilos>;

export default function ParametrosMobile() {
  const estilos = usePainelCowDataEstilos();
  const { cor: COR } = estilos;

  const [grupos, setGrupos] = useState<Record<string, { titulo: string; itens: ItemParametroCowData[] }>>({});
  const [fazendas, setFazendas] = useState<FazendaCadastroCowData[]>([]);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const [alvoTodas, setAlvoTodas] = useState(true);
  const [selecionadas, setSelecionadas] = useState<Set<number>>(new Set());
  const [mostrarSeletor, setMostrarSeletor] = useState(false);

  const [editando, setEditando] = useState<string | null>(null);
  const [novoValor, setNovoValor] = useState<string>("");
  const [aplicando, setAplicando] = useState(false);

  const { aberta, alternar } = useAcordeaoUnico();

  function carregar() {
    setCarregando(true); setErro(null);
    Promise.all([fetchParametrosCowData(), fetchFazendasParametroCowData()])
      .then(([p, f]) => {
        setGrupos(p.grupos);
        setFazendas(f);
        // Abre o primeiro grupo sozinho, só na carga inicial (se nada estava
        // aberto ainda) — recargas depois de "Aplicar" mantêm o grupo que o
        // usuário já tinha aberto.
        setAberta_seNenhum(Object.keys(p.grupos)[0]);
      })
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { carregar(); }, []);

  function setAberta_seNenhum(primeiraChave: string | undefined) {
    if (!aberta && primeiraChave) alternar(primeiraChave);
  }

  function alternarGrupo(chave: string) {
    alternar(chave);
    setEditando(null);
  }

  function fazendaIdsAlvo(): number[] | null {
    if (alvoTodas) return null;
    return [...selecionadas];
  }
  function toggleSelecionada(id: number) {
    setSelecionadas((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }

  function comecarEdicao(item: ItemParametroCowData) {
    setEditando(item.chave);
    setNovoValor(item.valor_global == null ? "" : String(item.valor_global));
    setAviso(null);
  }

  async function aplicar(item: ItemParametroCowData) {
    setAplicando(true); setErro(null); setAviso(null);
    try {
      const valor: number | boolean | string =
        item.tipo === "bool" ? novoValor === "true" :
        item.tipo === "float" ? Number(novoValor) :
        item.tipo === "int" ? Number(novoValor) : novoValor;
      const r = await aplicarParametroCowData(item.chave, { valor, fazenda_ids: fazendaIdsAlvo() });
      setAviso(
        r.global_atualizado
          ? `Padrão global atualizado e aplicado em ${r.atualizados} fazenda(s) ativa(s).`
          : `Aplicado em ${r.atualizados} fazenda(s) selecionada(s), sem mudar o padrão global.`
      );
      setEditando(null);
      carregar();
    } catch (e: any) { setErro(e.message); }
    finally { setAplicando(false); }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <CabecalhoMobilePainelCowData
        titulo="Parâmetros"
        subtitulo="Metas e configurações de manejo, agenda, RH e financeiro (padrão que toda fazenda usa até personalizar)."
        cor={COR}
      />
      <CorpoMobilePainelCowData>
        {erro && <p style={{ color: COR.vermelho, fontSize: "0.82rem", margin: 0 }}>{erro}</p>}
        {aviso && <p style={{ color: COR.verde, fontSize: "0.82rem", margin: 0 }}>{aviso}</p>}

        <div>
          <SeletorAlvoFazendas
            fazendas={fazendas}
            alvoTodas={alvoTodas} setAlvoTodas={setAlvoTodas}
            selecionadas={selecionadas} toggleSelecionada={toggleSelecionada}
            mostrarSeletor={mostrarSeletor} setMostrarSeletor={setMostrarSeletor}
            cor={COR}
          />
          <p style={{ fontSize: "0.72rem", color: COR.mudo, margin: "0.5rem 0 0" }}>
            {alvoTodas
              ? "Atenção: “Todas as fazendas ativas” sobrescreve inclusive quem já personalizou o valor."
              : "“Selecionar fazendas específicas” preserva quem já personalizou o valor nas demais fazendas."}
          </p>
        </div>

        {carregando ? (
          <p style={{ color: COR.mudo, fontSize: "0.85rem" }}>Carregando…</p>
        ) : Object.keys(grupos).length === 0 ? (
          <p style={{ color: COR.mudo, fontSize: "0.85rem" }}>Nenhum parâmetro encontrado.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
            {Object.entries(grupos).map(([id, g]) => (
              <SecaoAcordeaoMobile
                key={id} titulo={g.titulo} aberta={aberta === id} onToggle={() => alternarGrupo(id)} cor={COR}
                badge={<span style={{ fontSize: "0.68rem", color: COR.mudo }}>{g.itens.length}</span>}
              >
                <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
                  {g.itens.map((item, i) => (
                    <LinhaParametro
                      key={item.chave} item={item} estilos={estilos} primeiro={i === 0}
                      editando={editando === item.chave} novoValor={novoValor} setNovoValor={setNovoValor}
                      aplicando={aplicando}
                      onEditar={() => comecarEdicao(item)}
                      onCancelar={() => setEditando(null)}
                      onAplicar={() => aplicar(item)}
                    />
                  ))}
                </div>
              </SecaoAcordeaoMobile>
            ))}
          </div>
        )}
      </CorpoMobilePainelCowData>
    </div>
  );
}

function LinhaParametro({
  item, estilos, primeiro, editando, novoValor, setNovoValor, aplicando, onEditar, onCancelar, onAplicar,
}: {
  item: ItemParametroCowData; estilos: Estilos; primeiro: boolean;
  editando: boolean; novoValor: string; setNovoValor: (v: string) => void;
  aplicando: boolean; onEditar: () => void; onCancelar: () => void; onAplicar: () => void;
}) {
  const { cor } = estilos;
  return (
    <div style={{ borderTop: primeiro ? "none" : `1px solid ${cor.borda}`, paddingTop: primeiro ? 0 : "0.7rem" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "0.5rem", flexWrap: "wrap" }}>
        <span style={{ fontSize: "0.85rem", fontWeight: 600, color: cor.texto }}>{item.label}</span>
        {!editando && (
          <span style={{ fontSize: "0.85rem", fontWeight: 700, color: cor.texto }}>
            {item.tipo === "bool" ? (item.valor_global ? "Sim" : "Não") : String(item.valor_global ?? "—")}
            {item.unidade && <span style={{ color: cor.mudo, fontWeight: 400 }}> {item.unidade}</span>}
          </span>
        )}
      </div>
      {item.total_personalizados > 0 && (
        <div style={{ fontSize: "0.68rem", color: cor.mudo, marginTop: "0.15rem" }}>
          {item.total_personalizados} fazenda(s) personalizaram
        </div>
      )}

      {editando ? (
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.6rem", flexWrap: "wrap" }}>
          {item.tipo === "bool" ? (
            <select style={inputEstilo(estilos, { width: 110 })} value={novoValor} onChange={(e) => setNovoValor(e.target.value)}>
              <option value="true">Sim</option>
              <option value="false">Não</option>
            </select>
          ) : item.tipo === "date" ? (
            <input
              style={inputEstilo(estilos, { width: 160 })} type="date" value={novoValor}
              onChange={(e) => setNovoValor(e.target.value)}
            />
          ) : item.tipo === "int" || item.tipo === "float" ? (
            <input
              style={inputEstilo(estilos, { width: 110 })} type="number" step={item.tipo === "float" ? "0.01" : "1"}
              value={novoValor} onChange={(e) => setNovoValor(e.target.value)}
            />
          ) : (
            <input
              style={inputEstilo(estilos, { width: 160 })} type="text" value={novoValor}
              onChange={(e) => setNovoValor(e.target.value)}
            />
          )}
          {item.unidade && <span style={{ color: cor.mudo, fontSize: "0.76rem" }}>{item.unidade}</span>}
          <button style={{ ...estilos.btnPrimario, opacity: aplicando ? 0.6 : 1 }} onClick={onAplicar} disabled={aplicando}>
            <Check size={13} /> {aplicando ? "Aplicando…" : "Aplicar"}
          </button>
          <button style={estilos.btnGhost} onClick={onCancelar}>Cancelar</button>
        </div>
      ) : (
        <button
          style={{ ...estilos.btnGhost, marginTop: "0.5rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
          onClick={onEditar}
        >
          <Pencil size={12} /> Editar
        </button>
      )}
    </div>
  );
}
