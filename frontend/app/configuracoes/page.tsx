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

type Aba = "cadastro" | "parametros" | "financeiro" | "upload" | "importar" | "usuarios";

export default function ConfiguracoesPage() {
  const [aba, setAba] = useState<Aba | null>(null);
  const [abasVisiveis, setAbasVisiveis] = useState<{ id: Aba; label: string; icon: any }[]>([]);

  useEffect(() => {
    const abas: { id: Aba; label: string; icon: any }[] = [];
    if (podeModulo("parametros")) abas.push({ id: "cadastro", label: "Cadastro", icon: Layers });
    if (podeModulo("parametros")) abas.push({ id: "parametros", label: "Parâmetros", icon: SlidersHorizontal });
    if (podeModulo("financeiro")) abas.push({ id: "financeiro", label: "Parâmetros financeiros", icon: Wallet });
    if (podeModulo("upload")) abas.push({ id: "upload", label: "Upload CSV", icon: Upload });
    if (podeModulo("upload")) abas.push({ id: "importar", label: "Importar dados", icon: FileSpreadsheet });
    if (ehAdmin()) abas.push({ id: "usuarios", label: "Usuários", icon: Users });
    setAbasVisiveis(abas);
    setAba(abas[0]?.id ?? null);
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
      <div className="flex items-center gap-2 mb-2" style={{ flexWrap: "wrap" }}>
        {abasVisiveis.map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setAba(id)}
            style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", padding: "0.4rem 0.9rem", borderRadius: "999px", cursor: "pointer",
              border: "1px solid " + (aba === id ? "var(--dourado)" : "var(--border)"),
              background: aba === id ? "rgba(94,26,46,0.4)" : "transparent",
              color: aba === id ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: aba === id ? 700 : 500 }}>
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>
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
