"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Settings, Layers, FileSpreadsheet, Palette, CheckCheck, ExternalLink, ShieldCheck, History } from "lucide-react";
import { podeModulo, ehAdmin, ehDono, ehContratanteAdministrador } from "@/lib/api";
import UploadPage from "@/app/upload/page";
import Cadastro, { ABAS_CADASTRO, type AbaCadastro } from "@/components/Cadastro";
import { ABAS_CADASTRO_SANITARIO, type AbaCadastroSanitario } from "@/components/CadastroSanitario";
import { ABAS_CENTRAL_SEMEN, type AbaCentralSemen } from "@/components/CentralSemen";
import { ABAS_CADASTRO_ESTOQUE, type AbaCadastroEstoque } from "@/components/CadastroEstoque";
import ImportarDados from "@/components/ImportarDados";
import { AprovacoesView } from "@/components/AprovacoesView";
import { AuditoriaCowDataView } from "@/components/AuditoriaCowDataView";
import { OrdemPartoReconstrucaoView } from "@/components/OrdemPartoReconstrucaoView";
import { AparenciaSelector } from "@/components/AparenciaSelector";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";

// "Parâmetros" e "News" viraram abas de primeiro nível de Administração
// (17/08/2026, pedido explícito do usuário) — ver app/parametros/page.tsx e
// app/news-admin/page.tsx. Não vivem mais aqui dentro.
type Aba = "cadastro" | "upload" | "importar" | "aprovacoes" | "auditoria-cowdata" | "ordem-parto" | "aparencia";

export default function ConfiguracoesPage() {
  const [aba, setAba] = useState<Aba | null>(null);
  const [abasVisiveis, setAbasVisiveis] = useState<{ id: Aba; label: string; icon: any; title: string }[]>([]);
  // Um nível abaixo de "cadastro", e mais um abaixo de "sanitario" — vivem
  // aqui (não dentro de Cadastro/CadastroSanitario) para que só exista UM
  // registro de sub-navegação (evita a Sidebar ficar disputada entre pai e filho).
  const [cadastroAba, setCadastroAba] = useState<AbaCadastro>("lotes");
  const [sanitarioAba, setSanitarioAba] = useState<AbaCadastroSanitario>("eventos");
  const [centralSemenAba, setCentralSemenAba] = useState<AbaCentralSemen>("estoque-semen");
  const [estoqueAba, setEstoqueAba] = useState<AbaCadastroEstoque>("itens");

  useEffect(() => {
    const abas: { id: Aba; label: string; icon: any; title: string }[] = [];
    if (podeModulo("parametros")) abas.push({ id: "cadastro", label: "Cadastro", icon: Layers, title: "Cadastros de animais, lotes, pessoas..." });
    // A aba "Upload CSV" (importação dos CSV do Ideagri) fica OCULTA: a
    // fazenda migrou para o CowData e o local de importação passou a ser
    // "Importar dados". A rota /upload e o backend continuam de pé de
    // propósito — a importação do Ideagri apagava e reinseria a base inteira
    // do domínio a cada arquivo, então tirar o botão é o jeito seguro de
    // aposentar o fluxo sem mexer em dado nenhum. Para reativar, basta
    // devolver esta linha.
    if (podeModulo("upload")) abas.push({ id: "importar", label: "Importar dados", icon: FileSpreadsheet, title: "Importação manual de dados históricos" });
    if (ehAdmin()) abas.push({ id: "aprovacoes", label: "Aprovações", icon: CheckCheck, title: "Aprovar lançamentos de campo enviados pelo Telegram" });
    // Logo abaixo de Aprovações, só para o contratante-administrador (quem
    // contratou o plano) — pedido explícito do usuário.
    if (ehContratanteAdministrador()) abas.push({ id: "auditoria-cowdata", label: "Auditoria CowData", icon: ShieldCheck, title: "Acessos de suporte da CowData a esta fazenda, e compromissos de confiança/LGPD" });
    // Ferramenta administrativa pontual de correção de dado histórico — ver
    // OrdemPartoReconstrucaoView. Restrita a administrador, mesmo critério de
    // Aprovações acima (rewrite de dado de produção, não é autoatendimento
    // de qualquer operador).
    // Mesmo critério de "Auditoria CowData" acima — não `ehAdmin()` puro:
    // travar essa ferramenta pro próprio dono da fazenda por causa de um
    // `papel` divergente do literal "admin" seria o bug, não a proteção
    // (ver `exigir_admin_ou_dono` no backend, mesmo raciocínio).
    if (ehContratanteAdministrador()) abas.push({ id: "ordem-parto", label: "Ordem de Parto", icon: History, title: "Corrige a ordem de parto histórica do controle leiteiro" });
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
        children: ABAS_CADASTRO.map(([cid, clabel, cIcon]) => ({
          id: cid, label: clabel, icon: cIcon,
          children: cid === "sanitario" ? ABAS_CADASTRO_SANITARIO.map(([sid, slabel, sIcon]) => ({ id: sid, label: slabel, icon: sIcon }))
            : cid === "central-semen" ? ABAS_CENTRAL_SEMEN.map(([sid, slabel, sIcon]) => ({ id: sid, label: slabel, icon: sIcon }))
            : cid === "estoque" ? ABAS_CADASTRO_ESTOQUE.map(([sid, slabel, sIcon]) => ({ id: sid, label: slabel, icon: sIcon }))
            : undefined,
        })),
      };
    }
    return { id: a.id, label: a.label, icon: a.icon };
  }), [abasVisiveis]);
  const activeId = aba === "cadastro" ? (cadastroAba === "sanitario" ? sanitarioAba : cadastroAba === "central-semen" ? centralSemenAba : cadastroAba === "estoque" ? estoqueAba : cadastroAba)
    : (aba ?? "");
  const onSelect = useCallback((id: string) => {
    if (abasVisiveis.some((a) => a.id === id)) { setAba(id as Aba); return; }
    if (ABAS_CADASTRO_SANITARIO.some(([sid]) => sid === id)) { setAba("cadastro"); setCadastroAba("sanitario"); setSanitarioAba(id as AbaCadastroSanitario); return; }
    if (ABAS_CENTRAL_SEMEN.some(([sid]) => sid === id)) { setAba("cadastro"); setCadastroAba("central-semen"); setCentralSemenAba(id as AbaCentralSemen); return; }
    if (ABAS_CADASTRO_ESTOQUE.some(([sid]) => sid === id)) { setAba("cadastro"); setCadastroAba("estoque"); setEstoqueAba(id as AbaCadastroEstoque); return; }
    setAba("cadastro"); setCadastroAba(id as AbaCadastro);
  }, [abasVisiveis]);
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
            border: "1px solid var(--dourado)", borderRadius: "var(--r-sm)", padding: "0.9rem 1.1rem", textDecoration: "none",
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
        {aba === "upload" && <UploadPage />}
        {aba === "importar" && <ImportarDados />}
        {aba === "aprovacoes" && <div className="px-6"><AprovacoesView /></div>}
        {aba === "auditoria-cowdata" && <div className="px-6"><AuditoriaCowDataView /></div>}
        {aba === "ordem-parto" && <div className="px-6"><OrdemPartoReconstrucaoView /></div>}
      </div>
    </div>
  );
}
