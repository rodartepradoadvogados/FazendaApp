"use client";
// Configurações > Auditoria CowData — visível só para o contratante-
// administrador da fazenda (ver lib/api.ts::ehContratanteAdministrador).
// 2 cards, pedido explícito do usuário: "Auditoria de Acessos CowData"
// (toda ação feita durante um acesso de suporte da CowData a ESTA fazenda)
// e "Confiança e LGPD" (compromissos institucionais, texto fixo).
import { useEffect, useState } from "react";
import { ClipboardList, ShieldCheck, CheckCircle2, XCircle } from "lucide-react";
import { fetchAcoesSuporteDaMinhaFazenda, LABEL_NIVEL_SIGILO_EQUIPE_COWDATA, type AcaoAuditoriaSuporte } from "@/lib/api";

function formatarData(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function Card({ titulo, icon: Icon, children }: { titulo: string; icon: any; children: React.ReactNode }) {
  return (
    <div className="card" style={{ marginBottom: "1rem" }}>
      <div className="card-header flex items-center gap-2"><Icon size={16} /> {titulo}</div>
      <div style={{ padding: "0.9rem 1rem" }}>{children}</div>
    </div>
  );
}

export function AuditoriaCowDataView() {
  const [acoes, setAcoes] = useState<AcaoAuditoriaSuporte[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    fetchAcoesSuporteDaMinhaFazenda().then(setAcoes).catch((e) => setErro(e.message));
  }, []);

  return (
    <div>
      <Card titulo="Auditoria de Acessos CowData" icon={ClipboardList}>
        <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.8rem" }}>
          Todo acesso de suporte da equipe CowData a esta fazenda (motivo, protocolo, o que foi feito ou tentado
          durante a sessão) fica registrado abaixo — o mesmo histórico que a CowData vê do lado dela.
        </p>
        {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}
        {acoes === null && !erro && <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>Carregando…</p>}
        {acoes && acoes.length === 0 && <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>Nenhum acesso de suporte registrado ainda nesta fazenda.</p>}
        {acoes && acoes.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table className="fazenda-table">
              <thead>
                <tr><th>Quando</th><th>Protocolo</th><th>Membro CowData</th><th>Nível de sigilo</th><th>Ação</th><th>Resultado</th></tr>
              </thead>
              <tbody>
                {acoes.map((a) => (
                  <tr key={a.id}>
                    <td style={{ color: "var(--text-muted)" }}>{formatarData(a.quando)}</td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>{a.protocolo || "—"}</td>
                    <td>{a.membro_nome ?? "—"}</td>
                    <td style={{ color: "var(--text-muted)" }}>{a.nivel_sigilo ? LABEL_NIVEL_SIGILO_EQUIPE_COWDATA[a.nivel_sigilo] : "—"}</td>
                    <td style={{ fontFamily: "monospace", fontSize: "0.74rem" }}>{a.metodo} {a.caminho}</td>
                    <td>
                      {a.bloqueado
                        ? <span style={{ color: "var(--red)", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}><XCircle size={13} /> Bloqueada</span>
                        : <span style={{ color: "var(--green)", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}><CheckCircle2 size={13} /> Permitida</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card titulo="Confiança e LGPD" icon={ShieldCheck}>
        <ul style={{ display: "flex", flexDirection: "column", gap: "0.8rem", fontSize: "0.85rem", listStyle: "none", padding: 0, margin: 0 }}>
          <li>
            <strong>Isolamento por fazenda.</strong> Os dados desta fazenda ficam isolados de todas as outras
            fazendas-clientes da CowData — nenhum outro cliente tem acesso a eles, e nenhum funcionário da CowData
            entra sem passar pelo fluxo de acesso de suporte abaixo.
          </li>
          <li>
            <strong>Acesso de suporte sob controle do cliente.</strong> Todo acesso da equipe CowData a esta fazenda
            exige motivo de uma lista fechada e assunto do chamado, dura no máximo 30 minutos, bloqueia ações
            destrutivas e de dados financeiros, e fica sempre registrado com protocolo — nesta mesma tela.
          </li>
          <li>
            <strong>Compromissos contratuais.</strong> O tratamento dos dados desta fazenda segue os termos de uso e
            a política de privacidade contratados com a CowData, incluindo os princípios da LGPD (finalidade,
            necessidade e transparência no tratamento de dados pessoais).
          </li>
        </ul>
      </Card>
    </div>
  );
}
