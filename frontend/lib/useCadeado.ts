"use client";
// Cadeado do Painel do Contador — reautenticação por senha que destrava, por
// 15 minutos, lançamentos extraordinários (guia/imposto/multa), recálculo de
// juros e abertura de chamado. Ver backend/fazenda/auth.py::bloquear_escrita_contador
// e POST /auth/desbloquear. O token vive só em memória (nunca localStorage) —
// some ao trocar de aba do navegador ou recarregar a página, por segurança.
import { useCallback, useEffect, useRef, useState } from "react";
import { desbloquearContador } from "@/lib/api";

export function useCadeado() {
  const [token, setToken] = useState<string | null>(null);
  const [expiraEm, setExpiraEm] = useState<number | null>(null);
  const [restanteSegundos, setRestanteSegundos] = useState(0);
  const [destravando, setDestravando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!expiraEm) return;
    timerRef.current = setInterval(() => {
      const resto = Math.round((expiraEm - Date.now()) / 1000);
      if (resto <= 0) {
        setToken(null); setExpiraEm(null); setRestanteSegundos(0);
        if (timerRef.current) clearInterval(timerRef.current);
      } else {
        setRestanteSegundos(resto);
      }
    }, 1000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [expiraEm]);

  const destravar = useCallback(async (senha: string) => {
    setDestravando(true); setErro(null);
    try {
      const r = await desbloquearContador(senha);
      setToken(r.token_desbloqueio);
      setExpiraEm(Date.now() + r.validade_segundos * 1000);
      setRestanteSegundos(r.validade_segundos);
      return true;
    } catch (e: any) {
      setErro(e.message || "Senha incorreta");
      return false;
    } finally {
      setDestravando(false);
    }
  }, []);

  const bloquear = useCallback(() => {
    setToken(null); setExpiraEm(null); setRestanteSegundos(0);
  }, []);

  return { token, destravado: !!token, restanteSegundos, destravando, erro, destravar, bloquear };
}

export function formatarContagem(segundos: number): string {
  const m = Math.floor(segundos / 60);
  const s = segundos % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}
