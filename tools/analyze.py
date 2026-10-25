"""Usage: python -I analyze.py <pack_dir> <text_dir>"""
import re, sys, json, hashlib, difflib
from pathlib import Path
from collections import defaultdict

pack, text = Path(sys.argv[1]), Path(sys.argv[2])
man = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
AS_OF = man["as_of"]
docs = {d["DOC_ID"]: d for d in man["documents"]}
T = {p.stem: p.read_text(encoding="utf-8") for p in text.glob("*.txt")}

def header(t):
    h = {}
    for line in t.splitlines()[:20]:
        m = re.match(r"\s*([A-Z_]+):\s*(.*)", line)
        if m: h[m.group(1)] = m.group(2).strip()
        if line.strip() == "---": break
    return h

def body(t):
    return t.split("---", 1)[1] if "---" in t else t

print("== 0. manifest sanity ==")
print("count field", man["count"], "document_count", man["document_count"], "actual entries", len(man["documents"]))
files = {p.name for p in (pack / "docs").iterdir()}
print("files on disk", len(files), "| in manifest not on disk:", {d["file"] for d in docs.values()} - files, "| on disk not in manifest:", files - {d["file"] for d in docs.values()})
keysets = defaultdict(list)
for k, d in docs.items(): keysets[tuple(sorted(d))].append(k)
for ks, ids in keysets.items(): print(f"  schema variant ({len(ids)} docs, e.g. {ids[0]}): {ks}")
print("  RELIABILITY types:", {type(d['RELIABILITY']).__name__ for d in docs.values()})

print("\n== 0b. sha256 ==")
bad = []
for line in (pack / "hashes.sha256").read_text().splitlines():
    if not line.strip(): continue
    h, name = line.split(None, 1); name = name.strip().lstrip("*")
    p = pack / name if (pack / name).exists() else pack / "docs" / Path(name).name
    if not p.exists(): bad.append((name, "MISSING")); continue
    if hashlib.sha256(p.read_bytes()).hexdigest() != h.lower(): bad.append((name, "MISMATCH"))
print("hash lines:", sum(1 for l in (pack / 'hashes.sha256').read_text().splitlines() if l.strip()), "problems:", bad or "none")

print("\n== 1. header vs manifest, and sector vs title/content ==")
for k, d in sorted(docs.items()):
    t = T.get(k, "")
    h = header(t)
    if not h:
        print(f"  {k}: NO HEADER PARSED (chars={len(t)})"); continue
    for f in ["DOC_ID", "EVENT_ID", "TITLE", "SOURCE_NAME", "SOURCE_TYPE", "RELIABILITY", "PUB_DATE", "PUB_TIME", "COUNTRY", "SECTOR"]:
        if f in h and str(d.get(f)) != h[f]:
            print(f"  {k}: header {f}={h[f]!r} != manifest {d.get(f)!r}")
    missing = [f for f in ["DOC_ID","EVENT_ID","TITLE","PUB_DATE","COUNTRY","SECTOR","RELIABILITY","SOURCE_TYPE"] if f not in h]
    if missing: print(f"  {k}: header missing {missing}")
    title = d["TITLE"].lower(); b = body(t).lower(); sec = d["SECTOR"].lower()
    nw, nm = b.count("wheat"), b.count("maize")
    tw, tm = "wheat" in title, "maize" in title
    flag = ""
    if sec == "wheat" and tm and not tw: flag = "TITLE says maize, SECTOR=Wheat"
    elif sec == "maize" and tw and not tm: flag = "TITLE says wheat, SECTOR=Maize"
    elif sec == "wheat" and nm > nw: flag = "body maize-dominant, SECTOR=Wheat"
    elif sec == "maize" and nw > nm: flag = "body wheat-dominant, SECTOR=Maize"
    elif sec == "general" and (nw or nm) and k.startswith("ORV"): flag = "SECTOR=general"
    elif sec == "wheat" and nw == 0: flag = "SECTOR=Wheat but body never says wheat"
    if flag: print(f"  {k}: {flag}  [wheat={nw} maize={nm}] {d['TITLE']}")

print("\n== 2. title+date duplicates and content similarity ==")
grp = defaultdict(list)
for k, d in docs.items(): grp[(d["TITLE"].strip().lower(), d["PUB_DATE"])].append(k)
for (ti, dt), ids in grp.items():
    if len(ids) > 1:
        a, b2 = (body(T[i]) for i in ids[:2])
        r = difflib.SequenceMatcher(None, re.sub(r"\s+", " ", a), re.sub(r"\s+", " ", b2)).ratio()
        print(f"  {ids} {dt} '{ti}' formats={[docs[i]['file'][-4:] for i in ids]} chars={[len(T[i]) for i in ids]} body_similarity={r:.2f}")
# near-dup bodies with different titles
ids = sorted(k for k in T if T[k].strip())
for i, a in enumerate(ids):
    for b2 in ids[i+1:]:
        if grp[(docs[a]["TITLE"].strip().lower(), docs[a]["PUB_DATE"])] == grp[(docs[b2]["TITLE"].strip().lower(), docs[b2]["PUB_DATE"])]: continue
        r = difflib.SequenceMatcher(None, body(T[a]), body(T[b2])).quick_ratio()
        if r > 0.9:
            r = difflib.SequenceMatcher(None, body(T[a]), body(T[b2])).ratio()
            if r > 0.8: print(f"  near-dup body, different title/date: {a} {b2} {r:.2f}")
# same title, different date
tg = defaultdict(list)
for k, d in docs.items(): tg[d["TITLE"].strip().lower()].append(k)
for ti, v in tg.items():
    if len(v) > 1 and len({docs[x]['PUB_DATE'] for x in v}) > 1: print("  same title diff date:", v, ti)

print("\n== 3. instruction-like text ==")
pat = re.compile(r"(?i)\b(assistant|system|user)\s*:|ignore (all|your|previous|the)|disregard|you are (an?|now)|as an ai|\bAI\b|language model|approve all|skip (the )?cross|override|jailbreak|new instructions|do not (cite|challenge)|must (approve|accept)|rate this|judge should|odin should|thor should|loki should|heimdall|<\s*/?\s*(system|instructions?)|\bprompt\b")
for k in sorted(T):
    for ln in T[k].splitlines():
        if pat.search(ln): print(f"  {k}: {ln.strip()[:160]}")

print("\n== 4. clock ==")
for k, d in sorted(docs.items()):
    if d["PUB_DATE"] > AS_OF: print(f"  FUTURE {k} {d['PUB_DATE']} {d['TITLE']}")
print("  latest eligible:", max((d["PUB_DATE"], k) for k, d in docs.items() if d["PUB_DATE"] <= AS_OF))
# in-body mentions of dates/months after as-of in eligible docs
for k, d in sorted(docs.items()):
    if d["PUB_DATE"] > AS_OF: continue
    for m in re.finditer(r"20\d\d-\d\d-\d\d|(?:January|February|March|April|May|June|July|August|September|October|November|December) 2027", body(T[k])):
        print(f"  eligible {k} ({d['PUB_DATE']}) mentions {m.group(0)}")

print("\n== 5. Tolan x maize ==")
for k in sorted(T):
    b = body(T[k]); bl = b.lower()
    if "tolan" in bl and "maize" in bl:
        print(f"  {k} [{docs[k]['PUB_DATE']} {docs[k]['SOURCE_TYPE']}] {docs[k]['TITLE']}")
        for para in re.split(r"\n\s*\n|\n(?=\[P\d+\])", b):
            pl = para.lower()
            if "maize" in pl or "tolan" in pl:
                nums = re.findall(r"USD\s*[\d.,]+\s*[MB]?|[\d,]{4,}\s*tonnes|\d+(?:\.\d+)?\s*%", para)
                print(f"     {'TOLAN+MAIZE' if 'tolan' in pl and 'maize' in pl else ('maize' if 'maize' in pl else 'tolan')} nums={nums}: {para.strip()[:230]}")
print("  trade notes by route:")
for k, d in sorted(docs.items()):
    if d.get("SOURCE_TYPE") == "trade_note": print(f"    {k} {d['PUB_DATE']} {d['file'][-4:]} SECTOR={d['SECTOR']}: {d['TITLE']}")

print("\n== 6. paragraph labels & structure ==")
for k in sorted(T):
    b = body(T[k])
    if not b.strip(): continue
    labs = [int(x) for x in re.findall(r"\[P(\d+)\]", b)]
    if not labs: print(f"  {k}: NO [Pn] labels"); continue
    if labs != list(range(1, len(labs)+1)): print(f"  {k}: label sequence {labs}")
    last = b.strip().splitlines()[-1].strip()
    if not re.search(r"[.!?\"')\]]$", last): print(f"  {k}: ends mid-sentence: ...{last[-80:]!r}")
