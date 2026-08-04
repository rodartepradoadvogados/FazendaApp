"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Settings, SlidersHorizontal, Upload, Layers, FileSpreadsheet, Wallet, Palette, Newspaper, CheckCheck, ExternalLink } from "lucide-react";
import { podeModulo, ehAdmin, ehDono, podePublicarMaterias } from "@/lib/api";
import ParametrosPage from "@/app/parametros/page";
import UploadPage from "@/app/upload/page";
import Cadastro, { ABAS_CADASTRO, type AbaCadastro } from "@/components/Cadastro";
import { ABAS_CADASTRO_SANITARIO, type AbaCadastroSanitario } from "@/components/CadastroSanitario";
import { ABAS_CENTRAL_SEMEN, type AbaCentralSemen } from "@/components/CentralSemen";
import { ABAS_CADASTRO_ESTOQUE, type AbaCadastroEstoque } from "@/components/CadastroEstoque";
import ImportarDados from "@/components/ImportarDados";
import ParametrosFinanceiros from "@/components/ParametrosFinanceiros";
import NewsAdmin from "@/components/NewsAdmin";
import { AprovacoesView } from "@/components/AprovacoesView";
import { AparenciaSelector } from "@/components/AparenciaSelector";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";

type Aba = "cadastro" | "parametros" | "upload" | "importar" | "news" | "aprovacoes" | "aparencia";
type AbaParametros = "gerais" | "financeiro";
// Sub-abas de "Parâmetros" — "financeiro" só entra se o módulo financeiro estiver liberado (checado no useMemo abaixo).
const ABAS_PARAMETROS: [AbaParametros, string, any][] = [
  ["gerais", "Parâmetros gerais", SlidersHorizontal],
  ["financeiro", "Parâmetros financeiros", Wallet],
];

export default function ConfiguracoesPage() {
  const [aba, setAba] = useState<Aba | null>(null);
  const [abasVisiveis, setAbasVisiveis] = useState<{ id: Aba; label: string; icon: any; title: string }[]>([]);
  // Um nível abaixo de "cadastro", e mais um abaixo de "sanitario" — vivem
  // aqui (não dentro de Cadastro/CadastroSanitario) para que só exista UM
  // registro de sub-navegação (evita a Sidebar ficar disputada entre pai e filho).
  const [cadastroAba, setCadastroAba] = useState<AbaCadastro>("lotes");
  const [sanitarioAba, setSanitarioAba] = useState<AbaCadastroSanitario>("principios");
  const [centralSemenAba, setCentralSemenAba] = useState<AbaCentralSemen>("estoque-semen");
  const [estoqueAba, setEstoqueAba] = useState<AbaCadastroEstoque>("itens");
  const [parametrosAba, setParametrosAba] = useState<AbaParametros>("gerais");
  const temFinanceiro = podeModulo("financeiro");
  const abasParametrosVisiveis = useMemo(() => ABAS_PARAMETROS.filter(([id]) => id !== "financeiro" || temFinanceiro), [temFinanceiro]);

  useEffect(() => {
    const abas: { id: Aba; label: string; icon: any; title: string }[] = [];
    if (podeModulo("parametros")) abas.push({ id: "cadastro", label: "Cadastro", icon: Layers, title: "Cadastros de animais, lotes, pessoas..." });
    if (podeModulo("parametros")) abas.push({ id: "parametros", label: "Parâmetros", icon: SlidersHorizontal, title: "Parâmetros da fazenda e financeiros" });
    if (podeModulo("upload")) abas.push({ id: "upload", label: "Upload CSV", icon: Upload, title: "Upload dos CSV do Ideagri" });
    if (podeModulo("upload")) abas.push({ id: "importar", label: "Importar dados", icon: FileSpreadsheet, title: "Importação manual de dados históricos" });
    if (podePublicarMaterias()) abas.push({ id: "news", label: "News", icon: Newspaper, title: "Publicação e aprovação de matérias do blog de notícias de pecuária leiteira" });
    if (ehAdmin()) abas.push({ id: "aprovacoes", label: "Aprovações", icon: CheckCheck, title: "Aprovar lançamentos de campo enviados pelo Telegram" });
    // Sempre disponível — mesmo para quem não tem nenhum outro módulo liberado.
    abas.push({ id: "aparencia", label: "Aparência", icon: Palette, title: "Tema e paleta de cores — preferência pessoal" });
    setAbasVisiveis(abas);
    // Respeita ?aba=... (ex.: link da Agenda para "Importar dados"), desde que
    // a sub-aba exista e o usuário tenha acesso a ela; senão cai na primeira.
    const params = new URLSearchParams(window.location.search);
    const alvo = params.get("aba") as Aba | null;
    setAba(alvo && abas.some((a) => a.id === alvo) ? alvo : (abas[0]?.id ?? null));
    // ?sub=... — sub-aba de Cadastro (ex.: link direto de "Novo usuário" para
    // "Cadastre a pessoa primeiro" em Configurações > Cadastro > Pessoas).
    const sub = params.get("sub");
    if (sub && ABAS_CADASTRO.some(([cid]) => cid === sub)) setCadastroAba(sub as AbaCadastro);
  }, []);

  // Árvore completa (3 níveis: Configurações › Cadastro › Sanitário) — um único
  // registro, dono de tudo, evita a corrida de dois componentes escrevendo no
  // mesmo contexto na mesma renderização.
  const subNavTree: SubNavNode[] = useMemo(() => abasVisiveis.map((a) => {
    if (a.id === "cadastro") {
      return {
        id: a.id, label: a.label, icon: a.icon,
        // "usuarios" é restrito a administradores dentro de Cadastro.
        children: ABAS_CADASTRO.filter(([cid]) => cid !== "usuarios" || ehAdmin()).map(([cid, clabel, cIcon]) => ({
          id: cid, label: clabel, icon: cIcon,
          children: cid === "sanitario" ? ABAS_CADASTRO_SANITARIO.map(([sid, slabel, sIcon]) => ({ id: sid, label: slabel, icon: sIcon }))
            : cid === "central-semen" ? ABAS_CENTRAL_SEMEN.map(([sid, slabel, sIcon]) => ({ id: sid, label: slabel, icon: sIcon }))
            : cid === "estoque" ? ABAS_CADASTRO_ESTOQUE.map(([sid, slabel, sIcon]) => ({ id: sid, label: slabel, icon: sIcon }))
            : undefined,
        })),
      };
    }
    if (a.id === "parametros") {
      return {
        id: a.id, label: a.label, icon: a.icon,
        children: abasParametrosVisiveis.map(([pid, plabel, pIcon]) => ({ id: pid, label: plabel, icon: pIcon })),
      };
    }
    return { id: a.id, label: a.label, icon: a.icon };
  }), [abasVisiveis, abasParametrosVisiveis]);
  const activeId = aba === "cadastro" ? (cadastroAba === "sanitario" ? sanitarioAba : cadastroAba === "central-semen" ? centralSemenAba : cadastroAba === "estoque" ? estoqueAba : cadastroAba)
    : aba === "parametros" ? parametrosAba
    : (aba ?? "");
  const onSelect = useCallback((id: string) => {
    if (abasVisiveis.some((a) => a.id === id)) { setAba(id as Aba); return; }
    if (ABAS_CADASTRO_SANITARIO.some(([sid]) => sid === id)) { setAba("cadastro"); setCadastroAba("sanitario"); setSanitarioAba(id as AbaCadastroSanitario); return; }
    if (ABAS_CENTRAL_SEMEN.some(([sid]) => sid === id)) { setAba("cadastro"); setCadastroAba("central-semen"); setCentralSemenAba(id as AbaCentralSemen); return; }
    if (ABAS_CADASTRO_ESTOQUE.some(([sid]) => sid === id)) { setAba("cadastro"); setCadastroAba("estoque"); setEstoqueAba(id as AbaCadastroEstoque); return; }
    if (abasParametrosVisiveis.some(([pid]) => pid === id)) { setAba("parametros"); setParametrosAba(id as AbaParametros); return; }
    setAba("cadastro"); setCadastroAba(id as AbaCadastro);
  }, [abasVisiveis, abasParametrosVisiveis]);
  useSubNavRegister(useMemo(() => (aba ? { tree: subNavTree, activeId, onSelect } : null), [subNavTree, activeId, aba, onSelect]));

  if (!aba) {
    return (
      <div className="p-6 animate-in">
        <p style={{ color: "var(--text-muted)" }}>Você não tem acesso a nenhuma sub-aba de Configurações.</p>
      </div>
    );
  }

  return (
    <div className="px-6 pt-6">
      <div className="mb-2">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Settings size={22} style={{ color: "var(--dourado)" }} /> Configurações</h1>
      </div>
      {ehDono() && (
        <Link href="/painel-cowdata"
          className="mb-4 flex items-center justify-between"
          style={{
            border: "1px solid var(--dourado)", borderRadius: "10px", padding: "0.9rem 1.1rem", textDecoration: "none",
            background: "color-mix(in srgb, var(--dourado) 8%, transparent)",
          }}>
          <div>
            <div className="flex items-center gap-2" style={{ color: "var(--dourado)", fontWeight: 700, fontSize: "0.92rem" }}>
              <ExternalLink size={16} /> Painel Mestre CowData
            </div>
            <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginTop: "0.15rem" }}>
              Administração da própria CowData — fazendas-clientes, assinaturas, financeiro e equipe.
            </p>
          </div>
        </Link>
      )}
      <div style={{ margin: "0 -1.5rem" }}>
        {aba === "aparencia" && <div className="px-6"><AparenciaSelector variant="site" /></div>}
        {aba === "cadastro" && (
          <Cadastro
            aba={cadastroAba} onAbaChange={setCadastroAba}
            abaSanitario={sanitarioAba} onAbaSanitarioChange={setSanitarioAba}
            abaCentralSemen={centralSemenAba} onAbaCentralSemenChange={setCentralSemenAba}
            abaEstoque={estoqueAba} onAbaEstoqueChange={setEstoqueAba}
          />
        )}
        {aba === "parametros" && parametrosAba === "gerais" && <ParametrosPage />}
        {aba === "parametros" && parametrosAba === "financeiro" && temFinanceiro && <ParametrosFinanceiros />}
        {aba === "upload" && <UploadPage />}
        {aba === "importar" && <ImportarDados />}
        {aba === "news" && <NewsAdmin />}
        {aba === "aprovacoes" && <div className="px-6"><AprovacoesView /></div>}
      </div>
    </div>
  );
}
