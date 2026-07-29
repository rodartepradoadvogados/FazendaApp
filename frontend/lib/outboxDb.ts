"use client";
// ─────────────────────────────────────────────────────────────────────────────
// Camada de armazenamento da fila offline (outbox) — IndexedDB.
//
// Por quê IndexedDB e não localStorage: localStorage é síncrono, só guarda
// string e tem cota pequena (~5-10 MB) — insuficiente para fotos de câmera
// (2-8 MB cada). IndexedDB é assíncrono, guarda Blob nativamente (por
// referência, não string) e tem cota ordens de grandeza maior.
//
// Um único object store ("outbox"), com um campo discriminador `tipo`, guarda
// tanto lançamentos JSON quanto uploads binários (fotos) — dá atomicidade de
// graça (enfileirar/descartar é uma transação sobre um store só) e mantém
// sincronizar() (em lib/offline.ts) agnóstico ao tipo de item.
//
// Este módulo é só o MECANISMO de armazenamento. A fachada pública usada
// pelo resto do app é lib/offline.ts — nenhum componente/tela deve importar
// daqui diretamente.
//
// ATENÇÃO (Capacitor): assim como o localStorage, este banco vive presa à
// origem soldada em capacitor.config.ts (server.url) — trocar de domínio
// apaga a fila (lançamentos E fotos pendentes) de todos os celulares. Ver
// aviso em capacitor.config.ts.
// ─────────────────────────────────────────────────────────────────────────────

export const DB_NOME = "cowdata_offline";
export const DB_VERSAO = 1;
export const STORE = "outbox";

export type TipoItem = "json" | "form";
export type StatusItem = "pendente" | "erro";

/** Parte binária de um item multipart (ex.: a foto em si). `campo` é o nome
 *  do campo esperado pelo backend no FormData (para /fotos/upload: "file"). */
export type ArquivoOutbox = {
  campo: string;
  nome: string;
  mime: string;
  tamanho: number;
  blob: Blob;
};

export type RegistroOutbox = {
  id: string;
  criadoEm: string;              // ISO — também é a chave do índice porCriadoEm (ordem FIFO)
  descricao: string;
  caminho: string;
  metodo: "POST" | "PUT" | "DELETE";
  tipo: TipoItem;
  status: StatusItem;
  // tipo "json": o payload inteiro. tipo "form": campos de texto do
  // multipart (Record<string, string>) — o binário vai em `arquivo`.
  corpo: unknown;
  arquivo?: ArquivoOutbox;
  erro?: string;
  tentativas?: number;
  proximaTentativaEm?: string;
};

/** Projeção seguro para UI/React — nunca carrega o Blob (evita reter
 *  megabytes de imagem em memória só por listar a fila). */
export type ResumoOutbox = Omit<RegistroOutbox, "arquivo"> & {
  arquivo?: Omit<ArquivoOutbox, "blob">;
};

export class ErroCotaOutbox extends Error {
  constructor(msg = "Sem espaço no aparelho para guardar o item") {
    super(msg);
    this.name = "ErroCotaOutbox";
  }
}

const CHAVE_LEGADA = "mob_outbox";
const CHAVE_BACKUP_MIGRACAO = "mob_outbox_backup_migracao";
const CHAVE_FLAG_MIGRADO = "mob_outbox_migrado_idb";

function promessa<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

/** true se este ambiente tem IndexedDB utilizável (falso no SSR e em alguns
 *  modos de navegação restritos — ver modoLegado em lib/offline.ts). */
export function idbDisponivel(): boolean {
  return typeof window !== "undefined" && "indexedDB" in window;
}

let dbPromise: Promise<IDBDatabase> | null = null;
let prontoPromise: Promise<void> | null = null;

function abrirDb(): Promise<IDBDatabase> {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NOME, DB_VERSAO);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          const store = db.createObjectStore(STORE, { keyPath: "id" });
          store.createIndex("porCriadoEm", "criadoEm");
          store.createIndex("porStatus", "status");
          store.createIndex("porTipo", "tipo");
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  return dbPromise;
}

/** Migração one-shot: copia itens do outbox antigo (localStorage) para o
 *  IndexedDB. NÃO apaga a chave antiga aqui — quem decide apagar é
 *  lib/offline.ts, só depois de confirmar que o IndexedDB é a fonte da
 *  verdade (ver Fatia B do plano). add() (não put()) + tolerar
 *  ConstraintError torna a migração idempotente mesmo que a flag se perca. */
async function migrarDoLocalStorage(db: IDBDatabase): Promise<void> {
  if (localStorage.getItem(CHAVE_FLAG_MIGRADO) === "1") return;
  const raw = localStorage.getItem(CHAVE_LEGADA);
  if (!raw) {
    localStorage.setItem(CHAVE_FLAG_MIGRADO, "1");
    return;
  }
  let itens: any[] = [];
  try {
    itens = JSON.parse(raw);
    if (!Array.isArray(itens)) itens = [];
  } catch {
    // Corrompido — não mexe em nada, só marca pra não tentar de novo a
    // cada abertura do app (os dados antigos ficam preservados na chave,
    // só não migram automaticamente).
    localStorage.setItem(CHAVE_FLAG_MIGRADO, "1");
    return;
  }

  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    const store = tx.objectStore(STORE);
    for (const item of itens) {
      if (!item || !item.id) continue;
      const req = store.add({
        ...item,
        tipo: "json",
        status: item.erro ? "erro" : "pendente",
        metodo: item.metodo ?? "POST",
      } as RegistroOutbox);
      req.onerror = (e) => {
        if (req.error?.name === "ConstraintError") { e.preventDefault(); return; } // já migrado
      };
    }
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });

  // Só remove a chave antiga DEPOIS do tx.oncomplete acima — se o app for
  // morto no meio, a próxima abertura ainda encontra os dados originais e
  // tenta de novo (a flag só é marcada aqui, no final).
  localStorage.setItem(CHAVE_BACKUP_MIGRACAO, raw);
  localStorage.removeItem(CHAVE_LEGADA);
  localStorage.setItem(CHAVE_FLAG_MIGRADO, "1");
}

/** Abre o banco e roda a migração one-shot. Idempotente (memoiza a Promise).
 *  Toda função pública abaixo espera por isto antes de mexer no banco. */
export function garantirPronto(): Promise<void> {
  if (!prontoPromise) {
    prontoPromise = (async () => {
      const db = await abrirDb();
      await migrarDoLocalStorage(db);
    })();
  }
  return prontoPromise;
}

export async function inserirRegistro(reg: RegistroOutbox): Promise<void> {
  const db = await abrirDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).add(reg);
    tx.oncomplete = () => resolve();
    tx.onerror = () => {
      if (tx.error?.name === "QuotaExceededError") reject(new ErroCotaOutbox());
      else reject(tx.error);
    };
  });
}

export async function lerRegistro(id: string): Promise<RegistroOutbox | null> {
  const db = await abrirDb();
  const tx = db.transaction(STORE, "readonly");
  const reg = await promessa(tx.objectStore(STORE).get(id));
  return (reg as RegistroOutbox) ?? null;
}

function semBlob(reg: RegistroOutbox): ResumoOutbox {
  if (!reg.arquivo) return reg as ResumoOutbox;
  const { campo, nome, mime, tamanho } = reg.arquivo; // omite blob de propósito
  return { ...reg, arquivo: { campo, nome, mime, tamanho } };
}

/** Ordenado por criadoEm (FIFO) — a ordem entre lançamentos importa (ex.:
 *  "mover de lote" antes de "concluir evento"). Projeção sem Blob. */
export async function listarResumos(): Promise<ResumoOutbox[]> {
  const db = await abrirDb();
  const tx = db.transaction(STORE, "readonly");
  const registros = await promessa(tx.objectStore(STORE).index("porCriadoEm").getAll());
  return (registros as RegistroOutbox[]).map(semBlob);
}

export async function atualizarRegistro(id: string, patch: Partial<RegistroOutbox>): Promise<void> {
  const db = await abrirDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    const store = tx.objectStore(STORE);
    const getReq = store.get(id);
    getReq.onsuccess = () => {
      const atual = getReq.result as RegistroOutbox | undefined;
      if (!atual) return; // já removido (outra aba/rodada) — nada a fazer
      store.put({ ...atual, ...patch });
    };
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function removerRegistro(id: string): Promise<void> {
  const db = await abrirDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function lerBlob(id: string): Promise<Blob | null> {
  const reg = await lerRegistro(id);
  return reg?.arquivo?.blob ?? null;
}

export async function contarPorStatus(status: StatusItem): Promise<number> {
  const db = await abrirDb();
  const tx = db.transaction(STORE, "readonly");
  return promessa(tx.objectStore(STORE).index("porStatus").count(status));
}

/** navigator.storage.estimate() — margem de 10% (evita a beira exata da
 *  cota). Sem suporte à API (ex.: Safari) → assume que cabe; o guard real
 *  nesse caso é o catch de QuotaExceededError na escrita. */
export async function cabeNoDisco(bytes: number): Promise<boolean> {
  if (typeof navigator === "undefined" || !navigator.storage?.estimate) return true;
  try {
    const { usage = 0, quota = 0 } = await navigator.storage.estimate();
    if (!quota) return true;
    return usage + bytes < quota * 0.9;
  } catch {
    return true;
  }
}

/** Reduz o risco de o navegador despejar o banco sob pressão de disco.
 *  Chamado uma vez na inicialização; falha é ignorada (best-effort). */
export async function pedirStoragePersistente(): Promise<boolean> {
  if (typeof navigator === "undefined" || !navigator.storage?.persist) return false;
  try { return await navigator.storage.persist(); } catch { return false; }
}
