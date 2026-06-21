"""Tri-Factor signal quality gate: fuse technical confluence + fundamentals + news
into a 0-100 quality score and a pass/block decision. Turns fundamentals/news from
context into HARD filters so only high-quality signals surface. Pure + testable.

Honest: a high score means 'cleaner setup', NOT a profit guarantee."""
from __future__ import annotations
from dataclasses import dataclass, field

QUALITY_THRESHOLD = 50.0


@dataclass
class GateResult:
    passed: bool
    score: float
    reasons: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    vetoed: bool = False


def fundamental_gate(fundamentals: dict, side: str, kind: str) -> tuple[bool, list[str]]:
    """Equities only. Veto longs on broken fundamentals; flag earnings proximity.
    Non-equity (index/options) → always pass."""
    reasons: list[str] = []
    if kind.upper() != "EQUITY" or not fundamentals:
        return True, reasons
    pe = fundamentals.get("pe")
    if side.upper() == "BUY" and pe is not None and (pe < 0 or pe > 120):
        reasons.append(f"weak fundamentals for long (P/E {pe})")
        return False, reasons
    return True, reasons


def news_gate(event_flags: list[str]) -> tuple[bool, list[str]]:
    """Hard-veto on the highest-risk event windows; flag the rest as caution."""
    cautions: list[str] = []
    flags = set(event_flags or [])
    if "RESULTS" in flags:
        return False, ["earnings/results imminent — single-stock event risk"]
    if "RBI" in flags:
        cautions.append("policy/RBI event — expect whipsaw")
    if "EXPIRY" in flags:
        cautions.append("expiry day — theta/whipsaw risk")
    return True, cautions


def quality_score(net_score: float, agreement_pct: int, fund_ok: bool,
                  news_ok: bool, has_event: bool) -> float:
    """0-100. Technical strength + provider agreement, penalised by event/news/fundamentals."""
    technical = min(60.0, abs(net_score) * 120.0)      # net_score 0.5 => 60
    agree = agreement_pct * 0.4                         # up to 40
    score = technical + agree
    if not fund_ok:
        score -= 25
    if not news_ok:
        score -= 25
    if has_event:
        score -= 10
    return round(max(0.0, min(100.0, score)), 1)


def apply_gate(consensus, fundamentals: dict, event_flags: list[str], *,
               kind: str, threshold: float = QUALITY_THRESHOLD) -> GateResult:
    side = consensus.consensus.value
    net = consensus.indicator_snapshot.get("net_score", 0.0)
    fund_ok, fund_reasons = fundamental_gate(fundamentals, side, kind)
    news_ok, news_msgs = news_gate(event_flags)
    has_event = bool(event_flags)
    score = quality_score(net, consensus.agreement_pct, fund_ok, news_ok, has_event)

    reasons = [f"technical net_score {net}", f"agreement {consensus.agreement_pct}%"]
    cautions = list(news_msgs)
    vetoed = (not fund_ok) or (not news_ok)
    if not fund_ok:
        cautions += fund_reasons
    passed = (not vetoed) and score >= threshold
    return GateResult(passed=passed, score=score, reasons=reasons,
                      cautions=cautions, vetoed=vetoed)
