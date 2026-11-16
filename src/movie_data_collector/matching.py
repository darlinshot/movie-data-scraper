from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz

from .config import AUTO_MATCH_THRESHOLD, REVIEW_THRESHOLD
from .utils import normalize_title, split_titles, strip_accents


@dataclass
class MatchResult:
    status: str  # matched | needs_review | not_found
    score: float
    candidate: dict[str, Any] | None
    reason: str


def _candidate_strings(movie: dict[str, Any]) -> list[str]:
    vals: list[str] = []
    for key in ["movie_name", "original_title", "detail_title", "bov_title_hint"]:
        v = movie.get(key)
        if isinstance(v, str) and v.strip():
            vals.append(v)
    # split combined titles
    extra: list[str] = []
    for v in list(vals):
        a, b = split_titles(v)
        if a:
            extra.append(a)
        if b:
            extra.append(b)
    vals.extend(extra)
    # dedupe preserving order
    seen = set()
    out = []
    for v in vals:
        n = normalize_title(v)
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(v)
    return out


def _sequel_digits(text: str | None) -> str | None:
    """Extract a short sequel number (e.g. 'Lật Mặt 7' -> '7'), ignoring years."""
    if not text:
        return None
    t = strip_accents(str(text).lower())
    nums = re.findall(r"\b(\d{1,2})\b", t)
    return nums[-1] if nums else None


def score_pair(source: dict[str, Any], candidate: dict[str, Any]) -> float:
    src_names = _candidate_strings(source)
    cand_names = []
    for key in ["title", "bov_title", "original_title"]:
        v = candidate.get(key)
        if isinstance(v, str) and v.strip():
            cand_names.append(v)
            a, b = split_titles(v)
            if a:
                cand_names.append(a)
            if b:
                cand_names.append(b)
    context = str(candidate.get("context") or "")
    if not src_names or not cand_names:
        return 0.0
    best = 0.0
    for s in src_names:
        ns = normalize_title(s)
        for c in cand_names:
            nc = normalize_title(c)
            if not ns or not nc:
                continue
            tsr = fuzz.token_set_ratio(ns, nc)
            tsor = fuzz.token_sort_ratio(ns, nc)
            ratio = fuzz.ratio(ns, nc)
            score = max(tsor, ratio)
            # token_set can over-match when one title is subset of another ("mai" vs "mai no mot loi tam biet")
            if ns == nc:
                score = 100.0
            else:
                # allow token_set influence but penalize extra/missing tokens
                len_penalty = abs(len(ns) - len(nc)) / max(len(ns), len(nc), 1)
                token_bonus = tsr * (1 - 0.45 * len_penalty)
                score = max(score, token_bonus)
            # Different sequel numbers are a strong signal of different films
            sn = _sequel_digits(s)
            cn = _sequel_digits(c)
            if sn and cn and sn != cn:
                score = max(0.0, score - 35.0)
            if score > best:
                best = score
    # year hint from source vs candidate context/release
    sy = str(source.get("release_year") or "")
    m = re.search(r"\b(19\d{2}|20\d{2})\b", sy)
    sy4 = m.group(1) if m else None
    cand_text = " ".join([str(candidate.get("context") or ""), str(candidate.get("release_info") or ""), str(candidate.get("release_year") or "")])
    if sy4:
        if sy4 in cand_text:
            best = min(100.0, best + 4.0)
        elif re.search(r"\b(19\d{2}|20\d{2})\b", cand_text):
            best = max(0.0, best - 6.0)
    return float(best)


def _exact_title_match(source: dict[str, Any], candidate: dict[str, Any]) -> bool:
    src = {normalize_title(s) for s in _candidate_strings(source)}
    src.discard("")
    for key in ["title", "bov_title", "original_title"]:
        v = candidate.get(key)
        if isinstance(v, str) and normalize_title(v) in src:
            return True
    return False


def _year_match(source: dict[str, Any], candidate: dict[str, Any]) -> bool:
    m = re.search(r"\b(19\d{2}|20\d{2})\b", str(source.get("release_year") or ""))
    if not m:
        return False
    year = m.group(1)
    cand_text = " ".join(
        [
            str(candidate.get("context") or ""),
            str(candidate.get("release_info") or ""),
            str(candidate.get("release_year") or ""),
        ]
    )
    return year in cand_text


def choose_best_match(source: dict[str, Any], candidates: list[dict[str, Any]]) -> MatchResult:
    if not candidates:
        return MatchResult("not_found", 0.0, None, "no_candidates")
    scored = [(score_pair(source, c), c) for c in candidates]
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else -1.0
    margin = best_score - second_score

    # Exact title + matching year is strong enough even when a duplicate page exists.
    exact_and_dated = _exact_title_match(source, best) and _year_match(source, best)
    second_exact_and_dated = (
        len(scored) > 1
        and _exact_title_match(source, scored[1][1])
        and _year_match(source, scored[1][1])
    )
    if best_score >= AUTO_MATCH_THRESHOLD and (
        margin >= 3.0 or (exact_and_dated and not second_exact_and_dated)
    ):
        return MatchResult("matched", best_score, best, "auto")
    if best_score >= REVIEW_THRESHOLD:
        return MatchResult("needs_review", best_score, best, "ambiguous_or_low_confidence")
    return MatchResult("not_found", best_score, best if best_score >= 60 else None, "below_threshold")
