"use client";
// Painel CowData > Farmácia — mesmo catálogo global de indicações/princípios/
// marcas usado por TODAS as fazendas como padrão (PrincipioAtivo/
// MedicamentoComercial com fazenda_id=None, ver backend/fazenda/api/routers/
// farmacia.py). Reaproveita o componente inteiro da sub-aba Farmácia dos
// Cadastros da fazenda: como o token de quem chama daqui não tem fazenda_id
// (fid=null), o backend nunca clona pra uma fazenda específica — edita
// direto a linha global (mesmo comportamento de "elif fazenda_id is not
// None" nunca disparar). O prop contextoGlobal só ajusta textos/afordances
// (esconde "Personalizar para minha fazenda", que 400 sem fazenda_id) sem
// mudar nenhuma chamada de API.
import Farmacia from "@/components/Farmacia";

export default function FarmaciaCowData() {
  return (
    <div style={{ padding: "1.4rem" }}>
      <Farmacia contextoGlobal />
    </div>
  );
}
