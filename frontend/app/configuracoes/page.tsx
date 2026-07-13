"use client";
import { useEffect, useState } from "react";
import { Settings, SlidersHorizontal, Upload, Users, Layers, FileSpreadsheet, Wallet } from "lucide-react";
import { podeModulo, ehAdmin } from "@/lib/api";
import ParametrosPage from "@/app/parametros/page";
import UploadPage from "@/app/upload/page";
import UsuariosPage from "@/app/usuarios/page";
import Cadastro from "@/components/Cadastro";
import ImportarDados from "@/components/ImportarDados";
import ParametrosFinanceiros from "@/components/ParametrosFinanceiros";
import { TabBar } from "@/components/ui";

type Aba = "cadastro" | "parametros" | "financeiro" | "upload" | "importar" | "usuarios";

export default function ConfiguracoesPage() {
  const [aba, setAba] = useState<Aba | null>(null);
  const [abasVisiveis, setAbasVisiveis] = useState<{ id: Aba; label: string; icon: any; title: string }[]>([]);

  useEffect(() => {
    const abas: { id: Aba; label: string; icon: any; title: string }[] = [];
    if (podeModulo("parametros")) abas.push({ id: "cadastro", label: "Cadastro", icon: Layers, title: "Cadastros de animais, lotes, pessoas..." });
    if (podeModulo("parametros")) abas.push({ id: "parametros", label: "Parâmetros", icon: SlidersHorizontal, title: "Parâmetros da fazenda e financeiros" });
    if (podeModulo("financeiro")) abas.push({ id: "financeiro", label: "Parâmetros financeiros", icon: Wallet, title: "Parâmetros da fazenda e financeiros" });
    if (podeModulo("upload")) abas.push({ id: "upload", label: "Upload CSV", icon: Upload, title: "Upload dos CSV do Ideagri" });
    if (podeModulo("upload")) abas.push({ id: "importar", label: "Importar dados", icon: FileSpreadsheet, title: "Importação manual de dados históricos" });
    if (ehAdmin()) abas.push({ id: "usuarios", label: "Usuários", icon: Users, title: "Usuários e permissões" });
    setAbasVisiveis(abas);
    // Respeita ?aba=... (ex.: link da Agenda para "Importar dados"), desde que
    // a sub-aba exista e o usuário tenha acesso a ela; senão cai na primeira.
    const alvo = new URLSearchParams(window.location.search).get("aba") as Aba | null;
    setAba(alvo && abas.some((a) => a.id === alvo) ? alvo : (abas[0]?.id ?? null));
  }, []);

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
      <TabBar<Aba> abas={abasVisiveis} ativa={aba} onChange={setAba} />
      <div style={{ margin: "0 -1.5rem" }}>
        {aba === "cadastro" && <Cadastro />}
        {aba === "parametros" && <ParametrosPage />}
        {aba === "financeiro" && <ParametrosFinanceiros />}
        {aba === "upload" && <UploadPage />}
        {aba === "importar" && <ImportarDados />}
        {aba === "usuarios" && <UsuariosPage />}
      </div>
    </div>
  );
}
