"use client";
// Central de Protocolos › Acompanhamento › Sanitário › Preventivo — o que está
// pendente além dos dias em aberto (que vêm logo abaixo, em ListaDias):
//   - carência sem aceite (GET /sanitario/painel · carencia_sem_aceite) → abre o
//     cadastro na etapa 7;
//   - prazos legais abertos (atestado / comprovação, do mesmo painel) →
//     "Registrar envio" com o MESMO pop-up de Sanidade › Preventiva › Painel;
//   - celular sem enviar (GET /sanitario/dispositivos, só administrador): aparelho
//     com registros guardados há mais tempo que o parâmetro "aviso de celular sem enviar".
// Só lê o que já existe; nada novo no back. `grupo` filtra carência e prazos pelo
// tipo da caixa; o celular não é de uma caixa só, então aparece em todos os grupos.
import Link from "next/link";
import { useState } from "react";
import { FileText, Milk, Smartphone } from "lucide-react";
import { useToast } from "@/components/Toast";
import { listarCaixas, listarDispositivos, painel } from "@/lib/apiSanitario";
import { diaSemana, diferencaDias, fmtData, fmtDataHora, type Prazo } from "@/lib/sanitarioTipos";
import { grupoDoTipo, linkCentral, tipoNoGrupo, type GrupoPreventivo } from "@/lib/protocolosNavegacao";
import { ModalCumprir } from "../consulta/PainelPreventivo";
import { Faixa, useCarregar, useEuSanitario } from "../comum";

export function PendenciasPreventivo({ grupo = null }: { grupo?: GrupoPreventivo | null }) {
  const toast = useToast();
  const { admin } = useEuSanitario();
  const pn = useCarregar(() => painel(30), []);
  const caixas = useCarregar(() => listarCaixas("todas"), []);
  const disp = useCarregar(() => (admin ? listarDispositivos() : Promise.resolve([])), [admin]);
  const [cumprir, setCumprir] = useState<Prazo | null>(null);

  const porId = new Map((caixas.dados || []).map((c) => [c.id, c]));
  const doGrupo = (id: number | null | undefined) => !grupo || id == null || !porId.has(id) || tipoNoGrupo(porId.get(id)?.tipo, grupo);
  const semAceite = (pn.dados?.carencia_sem_aceite || []).filter((id) => doGrupo(id));
  const prazos = (pn.dados?.prazos || []).filter((x) => doGrupo(x.caixa_id));
  const hoje = pn.dados?.parametros.hoje;
  const horas = pn.dados?.parametros.aviso_offline_horas ?? 24;
  const [agora] = useState(() => Date.now());
  const celulares = (disp.dados || []).filter((d) => d.fila_pendentes > 0).map((d) => {
    const desde = d.fila_mais_antigo_em ? Date.parse(/Z$|[+-]\d\d:?\d\d$/.test(d.fila_mais_antigo_em) ? d.fila_mais_antigo_em : d.fila_mais_antigo_em + "Z") : null;
    return { ...d, atrasado: desde != null && agora - desde > horas * 3600 * 1000 };
  });
  const nada = pn.dados && !semAceite.length && !prazos.length && !celulares.length;

  return (
    <section className="san-bloco">
      <div className="san-bloco-cab"><h3>Pendências</h3><span className="san-nota">carência sem aceite · prazos legais{admin ? " · celular sem enviar" : ""}</span></div>
      <div className="san-bloco-corpo" style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {pn.erro && <Faixa tipo="atencao">Não foi possível ver as pendências: {pn.erro}</Faixa>}
        {!pn.dados && !pn.erro && <div className="skeleton" style={{ height: "3rem" }} role="status" aria-label="Carregando as pendências" />}
        {semAceite.map((id) => (
          <Faixa key={`c${id}`} tipo="atencao" role="status">
            <Milk size={13} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4 }} />
            <b>{porId.get(id)?.nome || `Cadastro ${id}`}</b>: carência sem aceite. O leite vai para o tanque e o registro marca “sem aceite”.{" "}
            {admin && <Link className="san-link" href={linkCentral.cadastroPreventivo({ caixa: id, passo: 7 }, porId.has(id) ? grupoDoTipo(porId.get(id)?.tipo) : null)}>Resolver no cadastro</Link>}
          </Faixa>
        ))}
        {prazos.map((x) => {
          const dias = hoje ? diferencaDias(hoje, x.vence_em) : 0;
          return (
            <Faixa key={`p${x.id}`} tipo={dias <= 10 ? "alerta" : "atencao"} role="status">
              <b>{x.tipo === "atestado" ? "Atestado" : "Comprovação"} · {x.caixa || "vacina"}</b>{x.destinatario ? ` para ${x.destinatario}` : ""}
              {" · "}<span className="san-num">vence {diaSemana(x.vence_em)} {fmtData(x.vence_em)} ({dias < 0 ? `vencido há ${-dias} dias` : `${dias} dias`})</span>
              {admin && <div style={{ marginTop: 6 }}><button type="button" className="btn-ghost san-btn-sm" onClick={() => setCumprir(x)}>
                <FileText size={12} aria-hidden="true" style={{ verticalAlign: "-1px", marginRight: 4 }} />{x.tipo === "atestado" ? "Registrar envio" : "Registrar comprovação"}</button></div>}
            </Faixa>
          );
        })}
        {celulares.map((d) => (
          <Faixa key={`d${d.id}`} tipo={d.atrasado ? "alerta" : "info"} role="status">
            <Smartphone size={13} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4 }} />
            <b>{d.nome || "Celular sem nome"}</b>: <span className="san-num">{d.fila_pendentes}</span> {d.fila_pendentes > 1 ? "registros guardados" : "registro guardado"} sem enviar
            {d.fila_mais_antigo_em ? ` desde ${fmtDataHora(d.fila_mais_antigo_em)}` : ""}{d.atrasado ? ` (mais de ${horas} h)` : ""}.
            {d.ultimo_contato_em ? <span className="san-nota"> Último contato: {fmtDataHora(d.ultimo_contato_em)}.</span> : null}
          </Faixa>
        ))}
        {disp.erro && admin && <Faixa tipo="atencao">Não foi possível ver os celulares: {disp.erro}</Faixa>}
        {nada && <p className="san-nota" style={{ margin: 0 }}>Nenhuma pendência{grupo ? " deste tipo" : ""}.</p>}
      </div>
      {cumprir && <ModalCumprir prazo={cumprir} onFechar={() => setCumprir(null)} onFeito={() => { setCumprir(null); toast("Prazo registrado como cumprido."); pn.recarregar(); }} />}
    </section>
  );
}
