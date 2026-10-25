import type { AgentId } from "../agents";
import { agentIdentity } from "../agents";

/**
 * Original, abstract medallions for the public agent identities.
 * These are deliberately emblematic rather than portraits of real people.
 */
export function MythicPortrait({ agent, decorative = false }: { agent: AgentId; decorative?: boolean }) {
  const identity = agentIdentity(agent);
  const label = identity ? `${identity.name}, ${identity.epithet}` : agent;

  return (
    <svg
      className={`mythic-portrait mythic-portrait-${agent}`}
      viewBox="0 0 180 180"
      role={decorative ? "presentation" : "img"}
      aria-label={decorative ? undefined : `${label} medallion`}
      aria-hidden={decorative ? true : undefined}
      focusable="false"
    >
      <circle className="portrait-aura" cx="90" cy="90" r="76" />
      <circle className="portrait-disc" cx="90" cy="90" r="67" />
      <circle className="portrait-ring" cx="90" cy="90" r="67" />
      <path className="portrait-orbit" d="M27 92c12-43 45-69 86-66 24 2 35 11 40 19" />
      <path className="portrait-orbit portrait-orbit-secondary" d="M31 119c20 31 57 45 91 33 16-6 26-15 31-25" />

      {agent === "heimdall" && (
        <g className="portrait-figure">
          <path d="M58 113c4-23 13-37 32-44 19 7 29 21 32 44" />
          <path d="M65 82c-2-19 10-31 25-31 16 0 27 12 25 31l-8 16H73Z" />
          <path d="M63 73c8-17 18-25 30-25s23 8 29 25l-10-5-9 5-10-6-10 6-10-5Z" />
          <path d="M78 84c4-3 8-3 12 0M98 84c4-3 8-3 12 0" />
          <path d="M87 94c3 2 7 2 10 0" />
          <path d="M90 76v20" />
          <circle cx="83" cy="84" r="1.5" />
          <circle cx="107" cy="84" r="1.5" />
          <path d="M47 110h17M116 110h17M50 119h20M110 119h20" />
        </g>
      )}

      {agent === "thor" && (
        <g className="portrait-figure">
          <path d="M52 115c5-26 19-43 38-48 20 5 34 22 38 48" />
          <path d="M62 79c0-21 11-34 28-34s29 13 29 34l-9 29H71Z" />
          <path d="M61 72c4-17 15-28 29-28 16 0 28 11 31 28l-13-7-8 7-10-8-10 8-9-6Z" />
          <path d="M76 85c4-3 8-3 12 0M101 85c4-3 8-3 12 0" />
          <path d="M88 96c4 3 8 3 12 0" />
          <path d="M94 74v23" />
          <path d="M43 57h18v36H43zM39 65h26M47 51h10" />
          <path d="M74 110c8 5 24 5 32 0" />
        </g>
      )}

      {agent === "loki" && (
        <g className="portrait-figure">
          <path d="M57 116c8-28 18-43 33-47 17 4 29 20 34 47" />
          <path d="M66 82c1-21 9-36 24-36 17 0 26 15 27 36l-8 26H74Z" />
          <path d="M66 69 48 52l25 7c4-14 12-22 24-22s21 8 26 22l25-7-19 18-14-8-10 8-10-8Z" />
          <path d="M77 85c4-3 8-3 12 0M101 85c4-3 8-3 12 0" />
          <path d="M87 96c4-2 8-2 12 0" />
          <path d="M90 77v20" />
          <path d="M71 112c11 7 27 7 38 0" />
          <path d="M50 119c8-8 16-9 24-3M130 119c-8-8-16-9-24-3" />
        </g>
      )}

      {agent === "odin" && (
        <g className="portrait-figure">
          <path d="M55 116c4-26 17-42 35-49 19 7 32 23 35 49" />
          <path d="M64 83c0-23 10-37 26-37 17 0 27 14 27 37l-8 27H72Z" />
          <path d="M60 74c4-22 14-34 30-34 15 0 27 12 31 34l-13-10-8 9-10-9-11 9Z" />
          <path d="M77 84c4-3 8-3 12 0M101 84c4-3 8-3 12 0" />
          <path d="M88 96c4 2 8 2 12 0" />
          <path d="M90 76v22" />
          <path d="M76 111h28M67 119h46" />
          <path d="M90 112v16M74 128h32" />
          <path d="M66 128 53 138M114 128l13 10" />
        </g>
      )}
    </svg>
  );
}
