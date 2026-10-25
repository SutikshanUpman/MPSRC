"use strict";
// Trial of the Nine Realms dashboard. No framework; every string from the API goes in through textContent.

const $ = (id) => document.getElementById(id);
const CITE = /\[([A-Z][A-Z0-9]*-\d+), (P\d+), [^\]]+\]/g;
const state = { cases: [], id: null, bundle: null, events: [], pos: 0, timer: null };

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

function put(el, ...kids) {
  el.replaceChildren(...kids.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false));
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || res.statusText);
  return body;
}

function pending(what) {
  return h("div", { class: "pending" }, h("strong", {}, "Pending"), ` ${what} is not available for this case yet.`);
}

/* ---------- citations and the source drawer ---------- */

function cite(doc, p, label, extra) {
  return h("button", { class: "cite", type: "button", "data-doc": doc, "data-p": p,
    onclick: () => openSource(doc, p, extra || {}) }, label);
}

function linkify(text, extra) {
  const frag = document.createDocumentFragment();
  let last = 0;
  String(text || "").replace(CITE, (m, doc, p, idx) => {
    if (idx > last) frag.append(text.slice(last, idx));
    frag.append(cite(doc, p, m, extra));
    last = idx + m.length;
    return m;
  });
  if (last < text.length) frag.append(text.slice(last));
  return frag;
}

function citeList(list, extra) {
  return h("span", { class: "cites" }, (list || []).map((c) => [linkify(c, extra), " "]));
}

async function openSource(doc, p, opts) {
  const q = new URLSearchParams({ doc_id: doc, p, case: state.id || "" });
  if (opts.table_id) q.set("table_id", opts.table_id);
  if (opts.row) q.set("row", opts.row);
  const body = $("drawer-body");
  $("drawer").hidden = false;
  $("drawer-title").textContent = `${doc} ${p}`;
  put(body, h("p", {}, "Loading…"));
  try {
    const s = await api("/api/source?" + q);
    const text = h("p", { class: "para" });
    let rest = s.text;
    const marks = (s.highlight || []).filter((t) => rest.includes(t));
    if (marks.length) {
      const m = marks[0], i = rest.indexOf(m);
      text.append(rest.slice(0, i), h("mark", { id: "hl" }, m), rest.slice(i + m.length));
    } else text.append(rest);
    put(body, 
      h("h3", {}, s.title),
      h("div", { class: "chips" }, chip(`tier ${s.tier}`), chip(s.source_type), chip(s.source_name), chip(`${s.pub_date} ${s.pub_time || ""}`),
        chip(`event ${s.event_id}`), s.masked ? chip("masked lines removed", "warn") : null,
        ...s.flags.map((f) => chip(f, "warn"))),
      text,
      s.rows ? h("p", { class: "note" }, "Row: ", s.rows.map((r) => `${r.row_key}${r.table_id ? ` (table ${r.table_id}, row ${r.native_row_number})` : ""}${r.flags.length ? " [" + r.flags.join(", ") + "]" : ""}`).join("; ")) : null,
      h("p", { class: "note" }, "Paragraphs: ", s.paragraphs.map((x) => cite(doc, x, x))),
    );
    const hl = $("hl");
    if (hl) hl.scrollIntoView({ block: "center" });
    $("drawer").focus();
  } catch (e) {
    put(body, pending(`${doc} ${p}`), h("p", { class: "note" }, e.message));
  }
}

function chip(text, kind) {
  return text ? h("span", { class: "chip " + (kind || "") }, text) : null;
}

/* ---------- cases ---------- */

async function loadCases(select) {
  state.cases = await api("/api/cases");
  const pick = $("case-pick");
  pick.replaceChildren(...state.cases.map((c) => h("option", { value: c.id }, `${c.id} · ${c.provider} · ${c.completion || c.status}`)));
  if (!state.cases.length) { $("status").textContent = "No saved case yet. Run one, or: python scripts/run_case.py --demo"; return; }
  await loadCase(select || state.id || (state.cases.find((c) => c.id === "demo_E5") || state.cases[0]).id);
}

async function loadCase(id) {
  stopFeed();
  state.id = id;
  $("case-pick").value = id;
  state.bundle = await api("/api/cases/" + encodeURIComponent(id));
  const b = state.bundle;
  if (b.case_file && b.case_file.question) $("question").value = b.case_file.question.replace(/^QUESTION[^\n]*\n/, "").trim();
  try { state.events = await api(`/api/cases/${encodeURIComponent(id)}/events`); } catch (e) { state.events = []; }
  state.pos = 0;
  put($("feed"));
  renderMeter(); renderTrial(); renderExposure(); renderBriefing(); renderInsight(); updateFeedPos();
  playFeed();
}

$("case-pick").addEventListener("change", (e) => loadCase(e.target.value));

$("run").addEventListener("click", async () => {
  const q = $("question").value.trim();
  if (!q) { $("status").textContent = "Type a question first."; return; }
  $("status").textContent = "Running (mock)…";
  $("run").disabled = true;
  try {
    const r = await api("/api/cases", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q, provider: "mock" }) });
    $("status").textContent = `Done: ${r.status}, briefing ${r.completion || "none"}.`;
    await loadCases(r.id);
  } catch (e) { $("status").textContent = "Failed: " + e.message; } finally { $("run").disabled = false; }
});

$("replay").addEventListener("click", async () => {
  if (!state.id) return;
  $("status").textContent = "Replaying recorded calls…";
  try {
    const r = await api("/api/cases", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: "replay", from: state.id.replace(/__replay$/, "") }) });
    $("status").textContent = `Replay done at $${r.spend.case_spent_usd.toFixed(2)}: briefing hash ${r.replay_matches_original ? "MATCHES the original" : "DIFFERS"}.`;
    await loadCases(r.id);
  } catch (e) { $("status").textContent = "Replay failed: " + e.message; }
});

/* ---------- tabs ---------- */

function selectTab(name) {
  const b = document.querySelector(`#tabs button[data-tab="${name}"]`);
  if (b) b.click();
}
$("tabs").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-tab]");
  if (!b) return;
  for (const t of document.querySelectorAll("#tabs button")) t.setAttribute("aria-selected", String(t === b));
  for (const p of document.querySelectorAll(".panel")) p.hidden = p.id !== "tab-" + b.dataset.tab;
});
$("drawer-close").addEventListener("click", () => { $("drawer").hidden = true; });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("drawer").hidden = true; });

/* ---------- cost meter ---------- */

function renderMeter() {
  const r = state.bundle.run_record, cfg = state.bundle.config;
  const el = $("meter");
  if (!r) { put(el, h("span", {}, "cost: pending")); return; }
  const cap = (cfg && cfg.per_case_cap_usd) || 0.5, s = r.spend;
  const used = Math.max(s.case_spent_usd, s.shadow_spent_usd);
  put(el, 
    h("div", {}, `${r.provider} · ${s.model_calls} model calls`),
    h("div", { class: "bar", role: "img", "aria-label": `${used.toFixed(3)} of ${cap} dollars` }, h("span", { style: `width:${Math.min(100, (used / cap) * 100)}%` })),
    h("div", { class: "note" }, s.billable ? `spent $${s.case_spent_usd.toFixed(4)}` : `$0 spent (estimated at configured prices: $${s.shadow_spent_usd.toFixed(4)})`, ` · case cap $${cap.toFixed(2)} · project so far $${s.project_total_after_usd.toFixed(2)} of $4.00`));
}

/* ---------- live feed ---------- */

function eventLine(e) {
  const p = JSON.stringify(e.payload);
  return h("li", { class: "ev " + e.level.toLowerCase() },
    h("span", { class: "seq" }, e.sequence), chip(e.actor, "actor-" + e.actor), h("strong", {}, e.event_type),
    h("span", { class: "payload" }, p.length > 170 ? p.slice(0, 170) + "…" : p));
}
function updateFeedPos() { $("feed-pos").textContent = state.events.length ? `${state.pos} / ${state.events.length} events` : "no events"; }
function stepFeed() {
  if (state.pos >= state.events.length) { stopFeed(); return; }
  const li = eventLine(state.events[state.pos++]);
  $("feed").append(li);
  li.scrollIntoView({ block: "nearest" });
  updateFeedPos();
}
function playFeed() {
  stopFeed();
  if (!state.events.length) { put($("feed"), h("li", {}, pending("The event log"))); return; }
  state.timer = setInterval(stepFeed, Number($("speed").value));
}
function stopFeed() { if (state.timer) clearInterval(state.timer); state.timer = null; }
$("play").addEventListener("click", playFeed);
$("pause").addEventListener("click", stopFeed);
$("rewind").addEventListener("click", () => { stopFeed(); state.pos = 0; put($("feed")); updateFeedPos(); });
$("speed").addEventListener("change", () => { if (state.timer) playFeed(); });

/* ---------- trial view ---------- */

function pct(e) { return e ? `${e.low}% to ${e.high}%` : "no range"; }

function renderTrial() {
  const b = state.bundle, cf = b.case_file, root = $("trial");
  if (!cf) { put(root, pending("The Case File")); return; }
  const rulings = Object.fromEntries((b.rulings || []).map((r) => [r.claim_id, r]));
  const xe = {};
  for (const e of cf.cross_examination || []) (xe[e.target_claim_id] = xe[e.target_claim_id] || []).push(e);
  const cells = cf.exposure_cells.length ? cf.exposure_cells : [];
  if (!cells.length) { put(root, pending("Cells for this case")); return; }
  put(root, ...[
    cf.status !== "OPEN" ? h("div", { class: "banner warn" }, `${cf.status}: ${(cf.rejection || {}).detail || ""}`) : null,
    ...cells.map((cell) => {
      const claims = cf.claim_ledger.filter((c) => c.country === cell.country && c.sector === cell.sector);
      const col = (agent) => h("div", { class: "side " + agent },
        h("h4", {}, agent === "thor" ? "Thor (high exposure)" : "Loki (limited exposure)"),
        ...claims.filter((c) => c.agent === agent).map((c) => claimCard(c, rulings[c.claim_id], xe[c.claim_id] || [])));
      return h("section", { class: "card cell" }, h("h3", {}, `${cell.country} · ${cell.sector}`),
        cellOdin(b, cell), h("div", { class: "cols" }, col("thor"), col("loki")));
    })].filter(Boolean));
}

function cellOdin(b, cell) {
  const row = ((b.briefing || {}).exposure_table || []).find((r) => r.country === cell.country && r.sector === cell.sector);
  if (!row) return h("p", { class: "note" }, "Odin: pending");
  return h("p", { class: "odin" }, h("strong", {}, "Odin: "), row.odin ? `${row.odin.low}% to ${row.odin.high}%` : "Insufficient evidence (no number given)", " ", chip(row.status, row.odin ? "ok" : "warn"));
}

function claimCard(c, ruling, challenges) {
  const state_ = c.status !== "submitted" ? chip(c.status + (c.superseded_by ? " → " + c.superseded_by : ""), "muted") : null;
  return h("article", { class: "claim " + (c.status !== "submitted" ? "old" : "") },
    h("div", { class: "chips" }, chip(c.claim_id), chip(`run ${c.run} · round ${c.round}`), chip(c.claim_type === "CELL_ESTIMATE" ? c.estimate_status : c.claim_kind), state_,
      ruling ? chip(`Odin: ${ruling.decision} · ${ruling.classification}`, ruling.decision === "REJECTED" ? "bad" : ruling.classification === "ESTABLISHED" ? "ok" : "warn") : null),
    h("p", {}, linkify(c.claim_text)),
    c.estimate ? h("p", { class: "range" }, pct(c.estimate)) : null,
    h("p", { class: "note" }, "Cites: ", citeList(c.citations)),
    ruling ? h("p", { class: "ruling" }, h("strong", {}, "Odin: "), ruling.rationale, ruling.decided_by === "MODEL" ? " (model)" : "") : null,
    ...challenges.map((ch) => h("div", { class: "challenge" },
      h("p", {}, h("strong", {}, `${ch.challenger} challenges (${ch.challenge_kind}): `), linkify(ch.challenge_text)),
      ch.response ? h("p", {}, h("strong", {}, `${ch.response.responder}: ${ch.response.response_type}. `), linkify(ch.response.response_text || ch.response.reason || "")) : h("p", { class: "note" }, "no response"))));
}

/* ---------- exposure ---------- */

function renderExposure() {
  const b = state.bundle.briefing, root = $("exposure");
  if (!b) { put(root, pending("The exposure table")); return; }
  const rows = b.exposure_table;
  if (!rows.length) { put(root, h("div", { class: "banner warn" }, b.executive_summary.text)); return; }
  const money = (p) => p ? `${p.low.toLocaleString("en-US")} to ${p.high.toLocaleString("en-US")} ${p.unit || ""}` : "–";
  put(root, 
    h("div", { class: "scroll" }, h("table", {},
      h("thead", {}, h("tr", {}, ["Cell", "Thor", "Loki", "Odin range", "Odin value", "Odin volume", "Status"].map((t) => h("th", { scope: "col" }, t)))),
      h("tbody", {}, rows.map((r) => {
        const side = (s) => !s ? "–" : s.low === null ? s.status : `${s.low}% to ${s.high}%`;
        const o = r.odin;
        return h("tr", { class: o ? "" : "insufficient" }, h("th", { scope: "row" }, `${r.country} · ${r.sector}`), h("td", {}, side(r.thor)), h("td", {}, side(r.loki)),
          h("td", {}, o ? `${o.low}% to ${o.high}%` : "Insufficient evidence"), h("td", {}, money(o && o.value)), h("td", {}, money(o && o.volume)),
          h("td", {}, chip(r.status, o ? "ok" : "warn")));
      })))),
    ...rows.map((r) => h("details", { class: "card" }, h("summary", {}, `${r.country} · ${r.sector}: why this range, and where it comes from`),
      h("p", {}, r.calibration_text),
      r.targeted_queries ? h("p", { class: "note" }, "Targeted queries tried: ", r.targeted_queries.join("; ")) : null,
      h("p", {}, h("strong", {}, "Citations: "), citeList(r.citation_refs)),
      h("p", {}, h("strong", {}, "Rows: "), (r.row_refs || []).map((x) => [h("button", { class: "cite", type: "button",
        onclick: () => openSource(x.doc_id, x.paragraph, { table_id: x.table_id, row: x.native_row_number || x.row_key }) }, `${x.row_key}${x.table_id ? ` (table ${x.table_id}, row ${x.native_row_number})` : ""}`), " "])),
      (r.calc_refs || []).map((id) => calcExplain(id)))));
}

function calcExplain(id) {
  const rec = (state.bundle.calcs || []).find((c) => c.calc_id === id);
  if (!rec || !rec.calc_explain) return h("p", { class: "note" }, `${id}: pending`);
  const e = rec.calc_explain;
  const sc = (x) => x ? Object.entries(x.scenarios || {}).map(([k, v]) => `${k.replace("_", " ")} ${v}%`).join(" · ") : "n/a";
  return h("details", { class: "calc" }, h("summary", {}, `${id} · ${e.status}`),
    h("p", { class: "note" }, e.formula), h("p", {}, e.baseline_rule),
    h("p", {}, "With repeated rows: ", sc(e.with_repeated_rows), h("br"), "Without repeated rows: ", sc(e.without_repeated_rows)),
    h("ul", {}, e.inputs.map((i) => h("li", {}, `${i.role} `, h("button", { class: "cite", type: "button",
      onclick: () => openSource(i.doc_id, i.paragraph, { table_id: i.table_id, row: i.native_row_number || i.row_key }) }, i.row_key),
      i.repeated_row ? chip("repeated row", "warn") : null))));
}

/* ---------- briefing ---------- */

function inline(text) {
  const frag = document.createDocumentFragment();
  const parts = String(text).split(/(\*\*[^*]+\*\*)/);
  for (const p of parts) {
    if (p.startsWith("**") && p.endsWith("**")) frag.append(h("strong", {}, linkify(p.slice(2, -2))));
    else frag.append(linkify(p));
  }
  return frag;
}

function markdown(md) {
  const out = [];
  const lines = md.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (/^# /.test(l)) out.push(h("h2", {}, l.slice(2)));
    else if (/^## /.test(l)) out.push(h("h3", {}, l.slice(3)));
    else if (/^\|/.test(l)) {
      const rows = [];
      while (i < lines.length && /^\|/.test(lines[i])) rows.push(lines[i++]);
      i--;
      const cells = (r) => r.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const head = cells(rows[0]), body = rows.slice(2).map(cells);
      out.push(h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, head.map((c) => h("th", { scope: "col" }, c)))),
        h("tbody", {}, body.map((r) => h("tr", {}, r.map((c) => h("td", {}, inline(c)))))))));
    } else if (/^\s*- /.test(l)) {
      const items = [];
      while (i < lines.length && /^\s*- /.test(lines[i])) items.push(h("li", {}, inline(lines[i++].replace(/^\s*- /, ""))));
      i--;
      out.push(h("ul", {}, items));
    } else if (l.trim()) out.push(h("p", {}, inline(l)));
  }
  return out;
}

function renderBriefing() {
  const { briefing: b, briefing_md: md } = state.bundle, root = $("briefing");
  if (!md) { put(root, pending("The briefing")); return; }
  const hd = b && b.header;
  put(root, 
    hd ? h("div", { class: "chips" }, chip(hd.completion_status, hd.completion_status === "COMPLETE" ? "ok" : "warn"), chip(hd.ruling_mode),
      hd.flagged_cells.length ? chip(`${hd.flagged_cells.length} flagged cell(s)`, "warn") : null,
      chip(`${hd.removed_numbers} number(s) removed by validator`, hd.removed_numbers ? "bad" : "ok")) : null,
    ...markdown(md));
}

/* ---------- traps, numbers, cost ---------- */

function renderInsight() {
  const t = state.bundle.trap_report, r = state.bundle.run_record, root = $("insight");
  const parts = [];
  parts.push(h("section", { class: "card" }, h("h3", {}, "Trap report"),
    !t ? pending("The trap report") : h("div", { class: "traps" }, t.traps.map((x) => h("details", { class: x.count ? "" : "zero" },
      h("summary", {}, `${x.type.replaceAll("_", " ").toLowerCase()} `, chip(String(x.count), x.count ? "ok" : "muted")),
      h("p", { class: "note" }, x.description),
      h("ul", {}, x.items.slice(0, 12).map((it) => h("li", {}, JSON.stringify(it))))))) ));
  if (r) {
    parts.push(h("section", { class: "card" }, h("h3", {}, "Acceptance evidence in this run"),
      h("ul", {},
        h("li", {}, `Cross-examinations: ${r.ac.cross_examinations}`),
        h("li", {}, `Claims rejected or conceded: ${r.ac.rejected_or_conceded}`),
        h("li", {}, `Sent back once: ${r.ac.sent_back ? "yes" : "no"}; new evidence families in Run 2: ${r.ac.run2_new_evidence_families.join(", ") || "none"}`),
        h("li", {}, `Memory changed a decision: ${r.ac.memory_decisions_changed}`),
        h("li", {}, `Briefing hash: ${r.briefing_hash || "none"}`)),
      h("p", { class: "note" }, "Replay at $0 re-runs the saved case from its recorded model calls and must reproduce this hash.")));
  }
  put(root, ...parts);
}

$("question").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("run").click(); });
const wanted = new URLSearchParams(location.hash.slice(1));
loadCases(wanted.get("case") || undefined).then(() => { if (wanted.get("tab")) selectTab(wanted.get("tab")); if (wanted.get("source")) { const [d, p] = wanted.get("source").split(":"); openSource(d, p, {}); } }).catch((e) => { $("status").textContent = "Could not load cases: " + e.message; });
