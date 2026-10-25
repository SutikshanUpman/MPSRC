"""Local BM25 over paragraph spans, with metadata filters (SYSTEM_ARCHITECTURE 15).

The index is built per case from records that already passed the as-of gate
and event scope, so nothing post-as-of or out-of-scope is ever indexed.
Sector is a ranking boost, never a filter. Tokens are whole words, so `Orvan`
never matches inside `Corvan`; `mentions()` gives the same rule for regex use.
"""
import math
import re
from collections import Counter

from ..ingestion.pipeline import case_scope

TOKEN_RE = re.compile(r"[a-z]+-\d+|\d+(?:[.,]\d+)*%?|[a-z]+")
SECTOR_CONTENT_BOOST = 0.30
SECTOR_DECLARED_BOOST = 0.10


def tokenize(text):
    return [t[:-2] if t.endswith("'s") else t for t in TOKEN_RE.findall(text.lower().replace("’", "'"))]


def mentions(text, name):
    """Case-insensitive whole-word match: mentions('Corvan Grain', 'Orvan') is False."""
    return re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", text or "", re.I) is not None


class CaseIndex:
    def __init__(self, corpus, as_of, event_id, k1=1.5, b=0.75, allow_hash_mismatch=()):
        self.corpus, self.as_of, self.event_id, self.k1, self.b = corpus, as_of, event_id, k1, b
        self.eligible, self.excluded = case_scope(corpus, as_of, event_id, allow_hash_mismatch)
        self.eligible_ids = {rec["doc_id"] for rec in self.eligible}
        self.units = []
        for rec in self.eligible:
            for p in rec["paragraphs"]:
                tokens = tokenize(rec["agent_title"] + " " + p["text_masked"])
                self.units.append({"rec": rec, "para": p, "tf": Counter(tokens), "len": len(tokens)})
        self.N = len(self.units)
        self.avgdl = sum(u["len"] for u in self.units) / self.N if self.N else 0.0
        self.df = Counter()
        for u in self.units:
            self.df.update(u["tf"].keys())

    def _idf(self, term):
        n = self.df.get(term, 0)
        return math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def _bm25(self, u, terms):
        score = 0.0
        for t in terms:
            f = u["tf"].get(t, 0)
            if f:
                score += self._idf(t) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * u["len"] / (self.avgdl or 1)))
        return score

    @staticmethod
    def _passes(rec, countries, max_tier, tiers, source_types):
        if countries:
            wanted = {c.lower() for c in countries}
            route = rec["route"] or {}
            places = {(rec["country"] or "").lower(), (route.get("origin") or "").lower(), (route.get("destination") or "").lower()}
            if not wanted & places:
                return False
        if max_tier is not None and (rec["reliability"] is None or rec["reliability"] > max_tier):
            return False
        if tiers is not None and rec["reliability"] not in set(tiers):
            return False
        if source_types is not None and rec["source_type"] not in set(source_types):
            return False
        return True

    @staticmethod
    def _sector_boost(rec, sectors):
        best = 0.0
        for s in sectors or []:
            s = s.lower()
            if s in rec["content_sectors"] or mentions(rec["agent_title"], s):
                best = max(best, SECTOR_CONTENT_BOOST)
            elif (rec["declared_sector"] or "").lower() == s:
                best = max(best, SECTOR_DECLARED_BOOST)
        return best

    def search(self, query, countries=None, max_tier=None, tiers=None, source_types=None,
               sectors=None, limit=10, collapse_families=True):
        terms = tokenize(query)
        hits = []
        for u in self.units:
            rec, p = u["rec"], u["para"]
            # The mandatory filters were applied at build time; re-check them here.
            if rec["pub_date"] > self.as_of or rec["event_id"] not in (self.event_id, "NONE"):
                continue
            if not self._passes(rec, countries, max_tier, tiers, source_types):
                continue
            base = self._bm25(u, terms)
            if base <= 0:
                continue
            boost = self._sector_boost(rec, sectors)
            hits.append({
                "doc_id": rec["doc_id"], "paragraph": p["id"], "score": base * (1 + boost),
                "bm25": base, "sector_boost": boost, "title": rec["agent_title"], "text": p["text_masked"],
                "citation": f"[{rec['doc_id']}, {p['id']}, {rec['pub_date']} {rec['pub_time']}]",
                "status": rec["status"], "flags": list(rec["flags"]), "reliability": rec["reliability"],
                "source_type": rec["source_type"], "event_id": rec["event_id"],
                "context_only": rec["background_only"], "evidence_family_id": rec["evidence_family_id"],
                "preferred_in_family": rec["preferred_in_family"],
                "metadata_conflicts": rec["metadata_conflicts"], "duplicates": [],
            })
        hits.sort(key=lambda h: (-h["score"], h["doc_id"], h["paragraph"]))
        if collapse_families:
            kept, seen = [], {}
            for h in hits:
                key = (h["evidence_family_id"], h["paragraph"])
                if key in seen:
                    first = seen[key]
                    first["duplicates"].append(h["doc_id"])
                    if h["preferred_in_family"] and not first["preferred_in_family"]:
                        h["duplicates"] = first["duplicates"] + [first["doc_id"]]
                        h["duplicates"].remove(h["doc_id"])
                        kept[kept.index(first)] = h
                        seen[key] = h
                    continue
                seen[key] = h
                kept.append(h)
            hits = kept
        return hits[:limit]

    def search_docs(self, query, limit=10, **kw):
        """Best paragraph per document, ranked."""
        out, seen = [], set()
        for h in self.search(query, limit=10 ** 6, **kw):
            if h["doc_id"] not in seen:
                seen.add(h["doc_id"])
                out.append(h)
        return out[:limit]
