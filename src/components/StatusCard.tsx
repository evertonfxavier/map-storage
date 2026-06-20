import { Spinner } from "@decky/ui";
import { TONE_COLOR } from "../theme";
import type { CardTone } from "../theme";

export type StatusCardProps = {
  tone: CardTone;
  title: string;
  lines: string[];
  busy?: boolean;
};

export function StatusCard({ tone, title, lines, busy }: StatusCardProps) {
  const accent = TONE_COLOR[tone];
  return (
    <div
      style={{
        width: "100%",
        borderLeft: `3px solid ${accent}`,
        background: "rgba(255,255,255,0.04)",
        borderRadius: 6,
        padding: "10px 12px",
        display: "flex",
        flexDirection: "column",
        gap: 4,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {busy ? <Spinner width={16} height={16} /> : null}
        <span style={{ color: accent, fontWeight: 700, fontSize: "0.95em" }}>
          {title}
        </span>
      </div>
      {lines.map((line, index) => (
        <span key={index} style={{ fontSize: "0.82em", opacity: 0.9 }}>
          {line}
        </span>
      ))}
    </div>
  );
}
