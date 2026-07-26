"use client";
import Link from "next/link";
import { ShieldCheck } from "lucide-react";

const COR = { cartao: "#0d1220", borda: "#1c2438", mudo: "#7c8aa8", dourado: "#e8c256" };

export default function ConfiancaLgpdCowData() {
  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.2rem" }}>Confiança e LGPD</h1>
      <p style={{ color: COR.mudo, fontSize: "0.85rem", marginBottom: "1.5rem", maxWidth: "42rem" }}>
        O que a CowData se compromete, por contrato, a respeitar sobre os dados de cada fazenda-cliente
        (ver Cláusula 6 do contrato-modelo, em Fazendas → Contrato → Baixar contrato):
      </p>
      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "12px", padding: "1.4rem", display: "flex", flexDirection: "column", gap: "0.7rem" }}>
        {[
          ["Titularidade", "Os dados do produtor são de propriedade exclusiva da fazenda-cliente — a CowData não adquire nenhum direito sobre eles."],
          ["Papel na LGPD", "A CowData atua só como operadora (Lei 13.709/2018); a fazenda é a controladora."],
          ["Vedação de uso próprio", "Nenhum acesso, cópia ou uso dos dados para desenvolvimento de produto, benchmarking ou comparação entre clientes, sem autorização expressa e específica."],
          ["Segredo empresarial", "Os dados também são protegidos como segredo de empresa (Lei 9.279/1996, art. 195)."],
          ["Acesso emergencial", "Só para diagnóstico técnico ou ordem judicial — com log de auditoria e aviso à fazenda em até 5 dias úteis."],
          ["Portabilidade", "Exportação garantida em até 15 dias em caso de rescisão."],
        ].map(([titulo, texto]) => (
          <div key={titulo} style={{ display: "flex", gap: "0.7rem", alignItems: "flex-start" }}>
            <ShieldCheck size={15} style={{ color: COR.dourado, flexShrink: 0, marginTop: "0.15rem" }} />
            <div>
              <b style={{ fontSize: "0.85rem" }}>{titulo}.</b>{" "}
              <span style={{ fontSize: "0.82rem", color: "#c3cbde" }}>{texto}</span>
            </div>
          </div>
        ))}
      </div>
      <p style={{ fontSize: "0.78rem", marginTop: "1rem", color: COR.mudo }}>
        Nada disso é tecnicamente reforçado ainda (é uma promessa contratual, não um controle de acesso) —
        ver <Link href="/painel-cowdata/cofre" style={{ color: COR.dourado }}>Cofre de acesso</Link> para o estado real do gap.
      </p>
    </div>
  );
}
