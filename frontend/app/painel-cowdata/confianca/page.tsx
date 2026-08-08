"use client";
import Link from "next/link";
import { ShieldCheck } from "lucide-react";

const COR = { cartao: "#262E39", borda: "#39424F", mudo: "#9CA6B4", dourado: "#6B7F99", texto: "#F1F3F5" };

function Bloco({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "1.2rem 1.4rem" }}>
      <h2 style={{ fontSize: "0.92rem", fontWeight: 700, marginBottom: "0.5rem" }}>{titulo}</h2>
      <div style={{ fontSize: "0.82rem", color: "#c3cbde", lineHeight: 1.55 }}>{children}</div>
    </div>
  );
}

export default function ConfiancaLgpdCowData() {
  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.2rem" }}>Confiança e LGPD</h1>
      <p style={{ color: COR.mudo, fontSize: "0.85rem", marginBottom: "1.5rem", maxWidth: "42rem" }}>
        O que já está implementado tecnicamente hoje — descrição factual, não é parecer jurídico.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem", maxWidth: "48rem" }}>
        <Bloco titulo="Isolamento por fazenda">
          Cada fazenda-cliente cadastrada só enxerga os próprios dados. Todo modelo de negócio do sistema (animais,
          reprodutivo, sanitário, produção, financeiro, estoque, pessoal) carrega um <code style={{ background: "#1A2028", padding: "0.05rem 0.35rem", borderRadius: "var(--r-sm)" }}>fazenda_id</code> obrigatório,
          denormalizado propositalmente para tornar "toda consulta filtra por fazenda_id" uma regra mecânica e
          auditável — desde a fundação multi-fazenda do sistema.
        </Bloco>

        <Bloco titulo="Acesso de suporte sob controle do cliente">
          Toda entrada de suporte da CowData nos dados de uma fazenda passa por pedido, motivo (de uma lista
          fechada, nunca texto livre) e prazo curto (30 minutos) — e fica registrada em log de auditoria, sem
          exceção. Cada fazenda escolhe, no próprio Cofre de acesso, se esse acesso é liberado automaticamente ou
          se exige aprovação prévia do dono.{" "}
          <Link href="/painel-cowdata/cofre" style={{ color: COR.dourado }}>Ver o Cofre de acesso</Link> — a visão
          consolidada de sessões ativas, pedidos e auditoria de todas as fazendas.
        </Bloco>

        <Bloco titulo="Próximo passo: nível de sigilo por conta">
          O modelo de dados para um controle de sigilo mais fino — por conta da Equipe CowData — já existe
          (<code style={{ background: "#1A2028", padding: "0.05rem 0.35rem", borderRadius: "var(--r-sm)" }}>Usuario.nivel_sigilo_maximo</code>),
          mas ainda não está ativo em nenhuma tela.
          <br /><br />
          É aditivo e dormente: hoje ninguém alcança nível de sigilo diferenciado por causa dele, e nenhum
          comportamento muda até uma fase futura ligar esse controle de verdade — quando a Equipe CowData (ver
          Equipe CowData) ganhar contas de login próprias, além dos cadastros de folha de pagamento que já existem.
        </Bloco>
      </div>

      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "1.4rem", display: "flex", flexDirection: "column", gap: "0.7rem", marginTop: "1.4rem", maxWidth: "48rem" }}>
        <p style={{ fontSize: "0.78rem", color: COR.mudo, marginBottom: "0.1rem" }}>
          Compromissos contratuais (ver Cláusula 6 do contrato-modelo, em Fazendas → Contrato → Baixar contrato) —
          o que a CowData se compromete a respeitar sobre os dados de cada fazenda-cliente:
        </p>
        {[
          ["Titularidade", "Os dados do produtor são de propriedade exclusiva da fazenda-cliente — a CowData não adquire nenhum direito sobre eles."],
          ["Papel na LGPD", "A CowData atua só como operadora (Lei 13.709/2018); a fazenda é a controladora."],
          ["Vedação de uso próprio", "Nenhum acesso, cópia ou uso dos dados para desenvolvimento de produto, benchmarking ou comparação entre clientes, sem autorização expressa e específica."],
          ["Segredo empresarial", "Os dados também são protegidos como segredo de empresa (Lei 9.279/1996, art. 195)."],
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
    </div>
  );
}
