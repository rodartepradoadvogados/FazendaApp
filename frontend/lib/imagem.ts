"use client";
// Redimensiona uma foto de câmera antes de guardar/enviar — uma foto de
// celular moderno vem em 4000×3000px (4-8 MB); reduzida para 1600px no
// lado maior em JPEG q0.8 fica por volta de 300-500 KB. Isso multiplica por
// ~10 quantas fotos cabem na fila offline (IndexedDB, ver lib/outboxDb.ts) e
// encurta bastante o tempo de upload em 3G rural.
//
// createImageBitmap com imageOrientation: "from-image" já aplica a
// orientação EXIF na decodificação — sem isso, fotos tiradas em retrato
// saem deitadas (o canvas não herda o EXIF sozinho).

const LADO_MAXIMO_PADRAO = 1600;
const QUALIDADE_PADRAO = 0.8;

/** Nunca lança — se o redimensionamento falhar por qualquer motivo (formato
 *  não suportado, memória, navegador sem createImageBitmap), devolve o
 *  arquivo original. Redimensionar é uma otimização, não pode bloquear o
 *  envio de uma foto real do campo. */
export async function redimensionarFoto(
  arquivo: Blob,
  ladoMaximo: number = LADO_MAXIMO_PADRAO,
  qualidade: number = QUALIDADE_PADRAO,
): Promise<Blob> {
  try {
    if (typeof createImageBitmap !== "function") return arquivo;
    const bitmap = await createImageBitmap(arquivo, { imageOrientation: "from-image" });
    const maiorLado = Math.max(bitmap.width, bitmap.height);
    if (maiorLado <= ladoMaximo) { bitmap.close?.(); return arquivo; } // já é pequena, não perde qualidade à toa

    const escala = ladoMaximo / maiorLado;
    const largura = Math.round(bitmap.width * escala);
    const altura = Math.round(bitmap.height * escala);

    const canvas = typeof OffscreenCanvas !== "undefined"
      ? new OffscreenCanvas(largura, altura)
      : Object.assign(document.createElement("canvas"), { width: largura, height: altura });
    const ctx = canvas.getContext("2d") as CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D | null;
    if (!ctx) { bitmap.close?.(); return arquivo; }
    ctx.drawImage(bitmap, 0, 0, largura, altura);
    bitmap.close?.();

    const blob = canvas instanceof OffscreenCanvas
      ? await canvas.convertToBlob({ type: "image/jpeg", quality: qualidade })
      : await new Promise<Blob | null>((resolve) => (canvas as HTMLCanvasElement).toBlob(resolve, "image/jpeg", qualidade));
    return blob || arquivo;
  } catch {
    return arquivo; // formato não suportado (ex.: HEIC em navegador sem decode) — segue com o original
  }
}
