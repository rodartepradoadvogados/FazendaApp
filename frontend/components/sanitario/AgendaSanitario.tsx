"use client";
// Agenda × Sanitário Preventivo v2:
//   - CartaoVacinasPrevistas: card "Vacinas previstas · 30 d" — SÓ NÚMEROS
//     (GET /sanitario/agenda/resumo), leva a Sanidade › Preventiva › Painel;
//     nunca lista animais (§12).
//   - NotasSanitario: notas do sanitário na Agenda ("aglomerou", carência sem
//     aceite, catálogo mudou, prazo legal, celular sem enviar, reagente...).
//     As marcadas "só administradores" o back só manda para administradores;
//     resolver = POST /sanitario/notas/{id}/resolver.
import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, Bell, BookOpen, Check, FileText, Milk, Smartphone, Syringe } from "lucide-react";
import { CartaoPainel } from "@/components/agenda/CartaoPainel";
import { useToast } from "@/components/Toast";
import { listarNotas, mensagemDoErro, resolverNota, resumoAgenda } from "@/lib/apiSanitario";
import { fmtData, type NotaAgenda } from "@/lib/sanitarioTipos";
import { useCarregar } from "./comum";

export function CartaoVacinasPrevistas() {
  const { dados, erro, carregando } = useCarregar(() => resumoAgenda(30), []);
  const href = dados?.link || "/sanidade?aba=preventiva&sub=painel";
  return (
    <CartaoPainel titulo="Vacinas previstas · 30 d" icon={Syringe} cor="var(--cat-sanidade)" href={href}
      valor={carregando && !dados ? "…" : erro ? "—" : dados?.animais ?? 0}
      desligado={!!erro}
      detalhe={erro ? "não foi possível carregar" : dados
        ? `animais distintos · ${dados.caixas} ${dados.caixas === 1 ? "vacina/exame" : "vacinas/exames"} · ${dados.dias} ${dados.dias === 1 ? "dia marcado" : "dias marcados"}`
        : "carregando"}
      titleAttr="Só números. A lista de animais fica em Sanidade › Preventiva." />
  );
}

const ICONE: Record<string, typeof Bell> = {
  aglomerou: Bell, carencia_pendente: Milk, catalogo_mudou: BookOpen, prazo_legal: FileText, comprovacao: FileText,
  celular_offline: Smartphone, reagente: AlertTriangle, animal_saiu_janela: AlertTriangle, fim_janela: AlertTriangle,
  fechamento_auto: Bell, vespera: Syringe,
};
function linkDaNota(n: NotaAgenda): { href: string; rotulo: string } | null {
  if (n.tipo === "carencia_pendente" && n.caixa_id) return { href: `/protocolos?aba=vacinas&sub=cadastro&caixa=${n.caixa_id}&passo=7`, rotulo: "Resolver no cadastro" };
  if (n.tipo === "catalogo_mudou") return { href: "/protocolos?aba=vacinas&sub=cadastro", rotulo: "Ver o que mudou" };
  if (n.dia_id) return { href: `/protocolos?aba=vacinas&sub=marcados&dia=${n.dia_id}`, rotulo: "Abrir o dia" };
  if (n.tipo === "aglomerou" && n.caixa_id) return { href: `/protocolos?aba=vacinas&sub=marcados&caixas=${n.caixa_id}`, rotulo: "Marcar data" };
  if (n.tipo === "prazo_legal" || n.tipo === "comprovacao") return { href: "/sanidade?aba=preventiva&sub=painel", rotulo: "Ver prazos" };
  if (n.caixa_id) return { href: `/sanidade?aba=preventiva&sub=janela&caixa=${n.caixa_id}`, rotulo: "Ver animais" };
  return null;
}

export function NotasSanitario() {
  const toast = useToast();
  const { dados, erro, recarregar } = useCarregar(() => listarNotas(true), []);
  const [resolvendo, setResolvendo] = useState<number | null>(null);
  if (erro) return null; // módulo não contratado ou fora do ar: a Agenda segue sem as notas
  if (!dados || !dados.length) return null;
  return (
    <section className="san-bloco" style={{ marginBottom: "1rem" }} aria-labelledby="notasSanTit">
      <div className="san-bloco-cab"><h3 id="notasSanTit">Notas do sanitário</h3><span className="san-nota san-num">{dados.length}</span></div>
      {dados.map((n) => {
        const Icone = ICONE[n.tipo] || Bell;
        const link = linkDaNota(n);
        return (
          <div key={n.id} className="san-nota-ag">
            <span className="ico"><Icone size={15} aria-hidden="true" /></span>
            <div>
              <p>{n.titulo}</p>
              <small>{n.texto}{n.data_ref ? ` · ${fmtData(n.data_ref, true)}` : ""}{n.so_admin ? " · só administradores" : ""}</small>
            </div>
            <div className="san-acoes">
              {link && <Link href={link.href} className="btn-ghost san-btn-sm">{link.rotulo}</Link>}
              <button type="button" className="btn-ghost san-btn-sm" disabled={resolvendo === n.id} onClick={async () => {
                setResolvendo(n.id);
                try { await resolverNota(n.id); toast("Nota resolvida."); recarregar(); }
                catch (e) { toast(mensagemDoErro(e), "erro"); } finally { setResolvendo(null); }
              }}><Check size={12} aria-hidden="true" style={{ verticalAlign: "-1px", marginRight: 4 }} />Resolver</button>
            </div>
          </div>
        );
      })}
    </section>
  );
}
