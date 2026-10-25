/** Shared date and figure formatting for the trial record. */

export function formatDay(value?: string | null) {
  if (!value) return "—";
  const iso = value.length <= 10 ? `${value}T00:00:00Z` : value;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(date);
}

export function formatMoment(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(date);
}

export function compactNumber(value: number) {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function money(value: number | null | undefined, unit: string) {
  if (value == null) return "not fixed";
  return unit.toUpperCase() === "USD" ? `$${compactNumber(value)}` : `${compactNumber(value)} ${unit}`;
}

export function moneyTitle(value: number | null | undefined, unit: string) {
  if (value == null) return "not fixed";
  return unit.toUpperCase() === "USD" ? `$${value.toLocaleString()}` : `${value.toLocaleString()} ${unit}`;
}

export function pctLabel(value: number) {
  return `${Math.round(value * 100)}%`;
}

export function roman(value: number) {
  const numerals = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];
  return numerals[value - 1] ?? String(value);
}
