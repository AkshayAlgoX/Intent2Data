"""Compact runtime index: the only representation of the codebook the request
path ever touches.

Built once (startup or offline `scripts/build_index.py`) from the raw
metadata JSONL, projected down to the handful of fields the pipeline needs,
and optionally cached as gzip JSON. The raw 261 MB file is never read during a
request.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional

from app.retrieval.bm25 import BM25Index
from app.retrieval.families import family_key, normalize_code

INDEX_FORMAT_VERSION = "runtime_index_v1"
# Fields projected from the raw record. Everything else (raw_block, value
# labels, URLs) stays on disk.
_PROJECTED = ("variable_label", "question_text", "product_key", "product_title", "product_family",
              "section", "section_title", "year")
_MAX_QUESTION_TEXT = 1800


@dataclass(frozen=True)
class VariableRecord:
    code: str
    label: str
    question_text: str
    module_id: str
    product_key: str
    product_title: str
    product_family: str
    section: str
    section_title: str
    year: str
    family_id: str

    def compact_line(self) -> str:
        """The candidate representation shown to the LLM: code | label | question text."""
        return f"{self.code} | {self.label} | {self.question_text}"


@dataclass(frozen=True)
class ModuleHit:
    module_id: str
    rank: int
    score: float


def module_id_of(record: dict) -> str:
    return f"{record.get('product_key', '')}::{record.get('section', '')}"


class RuntimeIndex:
    def __init__(
        self,
        variables: dict[str, VariableRecord],
        module_members: dict[str, list[str]],
        module_docs: dict[str, str],
        family_members: dict[str, list[str]],
        fingerprint: str,
        source: str = "",
    ):
        self.variables = variables
        self.module_members = module_members
        self.family_members = family_members
        self.fingerprint = fingerprint
        self.source = source
        ids = sorted(module_docs)
        self._bm25 = BM25Index(ids, [module_docs[m] for m in ids])
        self._module_docs = module_docs

    # ---- construction -----------------------------------------------------
    @classmethod
    def from_records(cls, records: Iterable[dict], source: str = "") -> "RuntimeIndex":
        variables: dict[str, VariableRecord] = {}
        module_members: dict[str, list[str]] = defaultdict(list)
        module_text: dict[str, list[str]] = {}
        family_members: dict[str, list[str]] = defaultdict(list)
        digest = hashlib.sha256()
        for raw in records:
            code = normalize_code(raw.get("variable_code", ""))
            if not code:
                continue
            mid = module_id_of(raw)
            fid = family_key(raw)
            rec = VariableRecord(
                code=code,
                label=str(raw.get("variable_label", "") or ""),
                question_text=str(raw.get("question_text", "") or "")[:_MAX_QUESTION_TEXT],
                module_id=mid,
                product_key=str(raw.get("product_key", "") or ""),
                product_title=str(raw.get("product_title", "") or ""),
                product_family=str(raw.get("product_family", "") or ""),
                section=str(raw.get("section", "") or ""),
                section_title=str(raw.get("section_title", "") or ""),
                year=str(raw.get("year", "") or ""),
                family_id=fid,
            )
            # Codes collide across product files (e.g. HHID). Last record wins
            # for the variable itself; every occurrence stays a module member.
            # This mirrors the validated offline candidate generation.
            variables[code] = rec
            module_members[mid].append(code)
            if mid not in module_text:
                module_text[mid] = [rec.product_title, rec.section_title]
            module_text[mid].append(rec.label)
            if code not in family_members[fid]:
                family_members[fid].append(code)
            digest.update(f"{code}\x1f{mid}\x1f{fid}\n".encode("utf-8"))
        module_docs = {m: " ".join(parts) for m, parts in module_text.items()}
        for fid, members in family_members.items():
            members.sort(key=lambda c: (_year_sort(variables[c].year), c))
        return cls(variables, dict(module_members), module_docs, dict(family_members),
                   fingerprint=digest.hexdigest()[:16], source=source)

    @classmethod
    def from_metadata(cls, path: Path) -> "RuntimeIndex":
        def _iter():
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        yield json.loads(line)
        return cls.from_records(_iter(), source=str(path))

    # ---- cache --------------------------------------------------------------
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": INDEX_FORMAT_VERSION,
            "fingerprint": self.fingerprint,
            "source": self.source,
            "variables": [asdict(v) for v in self.variables.values()],
            "module_members": self.module_members,
            "module_docs": self._module_docs,
            "family_members": self.family_members,
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "RuntimeIndex":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload.get("format") != INDEX_FORMAT_VERSION:
            raise ValueError(f"index cache format mismatch: {payload.get('format')}")
        variables = {v["code"]: VariableRecord(**v) for v in payload["variables"]}
        return cls(variables, payload["module_members"], payload["module_docs"],
                   payload["family_members"], payload["fingerprint"], payload.get("source", ""))

    @classmethod
    def load_or_build(cls, metadata_path: Path, cache_path: Optional[Path]) -> tuple["RuntimeIndex", dict]:
        """Prefer the cache; fall back to building from metadata and refresh the cache."""
        timings: dict = {}
        if cache_path and cache_path.exists():
            t = time.perf_counter()
            try:
                index = cls.load(cache_path)
                timings["load_cache_s"] = round(time.perf_counter() - t, 3)
                return index, timings
            except Exception as exc:  # corrupt/old cache: rebuild
                timings["cache_error"] = f"{exc.__class__.__name__}: {exc}"
        t = time.perf_counter()
        index = cls.from_metadata(metadata_path)
        timings["build_s"] = round(time.perf_counter() - t, 3)
        if cache_path:
            t = time.perf_counter()
            index.save(cache_path)
            timings["save_cache_s"] = round(time.perf_counter() - t, 3)
        return index, timings

    # ---- queries ------------------------------------------------------------
    def search_modules(self, query: str, k: int) -> list[ModuleHit]:
        return [ModuleHit(mid, rank, round(score, 6)) for rank, (mid, score) in enumerate(self._bm25.search(query, k), 1)]

    def module_codes(self, module_id: str) -> list[str]:
        return list(self.module_members.get(module_id, []))

    def family_codes(self, code: str) -> list[str]:
        rec = self.variables.get(normalize_code(code))
        if rec is None:
            return []
        return list(self.family_members.get(rec.family_id, [rec.code]))

    def get(self, code: str) -> Optional[VariableRecord]:
        return self.variables.get(normalize_code(code))

    def module_summary(self, module_id: str) -> dict:
        members = self.module_members.get(module_id, [])
        first = self.variables.get(members[0]) if members else None
        return {
            "module_id": module_id,
            "product_key": first.product_key if first else module_id.split("::")[0],
            "product_title": first.product_title if first else "",
            "section": first.section if first else module_id.split("::")[-1],
            "section_title": first.section_title if first else "",
            "variable_count": len(members),
        }

    def stats(self) -> dict:
        return {
            "variables": len(self.variables),
            "modules": len(self.module_members),
            "families": len(self.family_members),
            "fingerprint": self.fingerprint,
        }


def _year_sort(year: str) -> int:
    return int(year) if year.isdigit() else 99999
