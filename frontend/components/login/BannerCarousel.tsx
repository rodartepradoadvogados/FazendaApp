"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { bannersDeHoje } from "./banners";

const DURACAO_MS = 4000;

export function BannerCarousel() {
  const banners = useMemo(() => bannersDeHoje(), []);
  const [indice, setIndice] = useState(0);
  const reduzMovimento = useRef(false);

  useEffect(() => {
    reduzMovimento.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduzMovimento.current || banners.length <= 1) return;
    const id = setInterval(() => setIndice((i) => (i + 1) % banners.length), DURACAO_MS);
    return () => clearInterval(id);
  }, [banners.length]);

  return (
    <div>
      <div style={{ position: "relative", overflow: "hidden", minHeight: "clamp(220px, 28vw, 300px)" }}>
        <div
          style={{
            display: "flex", flexWrap: "nowrap",
            transform: `translateX(-${indice * 100}%)`,
            transition: reduzMovimento.current ? "none" : "transform 0.6s ease",
          }}
        >
          {banners.map((b) => (
            <Link
              key={b.slug}
              href={b.href}
              style={{ flex: "0 0 100%", textDecoration: "none", display: "block", minWidth: 0 }}
            >
              <span style={{
                display: "inline-block", padding: "0.3rem 0.75rem", borderRadius: "999px", fontSize: "0.72rem", fontWeight: 700,
                letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--dourado-light)",
                background: "rgba(212,160,23,0.14)", border: "1px solid rgba(212,160,23,0.3)", marginBottom: "1.1rem",
              }}>
                {b.eyebrow}
              </span>
              <h1 style={{ fontSize: "clamp(1.8rem, 3.4vw, 2.7rem)", fontWeight: 800, lineHeight: 1.12, margin: "0 0 0.9rem", color: "#fff", maxWidth: "34rem" }}>
                {b.titulo}
              </h1>
              <p style={{ fontSize: "1rem", color: "rgba(245,238,241,0.78)", maxWidth: "34rem", margin: "0 0 1.4rem", lineHeight: 1.55 }}>
                {b.descricao}
              </p>
              <span className="btn-primary" style={{ display: "inline-flex" }}>
                Saiba mais <ChevronRight size={16} />
              </span>
            </Link>
          ))}
        </div>
      </div>
      <div style={{ display: "flex", gap: "0.4rem", marginTop: "1.2rem" }}>
        {banners.map((b, i) => (
          <button
            key={b.slug}
            onClick={() => setIndice(i)}
            aria-label={`Ver banner ${b.eyebrow}`}
            style={{
              width: i === indice ? "1.6rem" : "0.5rem", height: "0.5rem", borderRadius: "999px",
              background: i === indice ? "var(--dourado-light)" : "rgba(255,255,255,0.25)",
              border: "none", cursor: "pointer", transition: "all 0.3s ease", padding: 0,
            }}
          />
        ))}
      </div>
    </div>
  );
}
