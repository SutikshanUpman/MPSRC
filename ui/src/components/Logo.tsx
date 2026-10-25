/**
 * The Trial of the Nine Realms mark: Tiwaz, the rune of law and the spear, cut in one stroke
 * inside a hairline square.
 */
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label="Trial of the Nine Realms mark, the Tiwaz rune"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.4}
      strokeLinecap="square"
      strokeLinejoin="miter"
    >
      <rect x="0.55" y="0.55" width="30.9" height="30.9" strokeWidth={1} />
      <path d="M16 24.6V7.4M10.6 12.8 16 7.4l5.4 5.4" />
    </svg>
  );
}
