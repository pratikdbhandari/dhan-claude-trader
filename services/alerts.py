"""Local alert generation: turn signals + risk state into deduplicated alerts the
UI renders as toasts + a log. Pure + testable; no notifications side-effects here."""
from __future__ import annotations
from dataclasses import dataclass
from core.models import SignalType

INFO, WARN, CRITICAL = "INFO", "WARN", "CRITICAL"


@dataclass
class Alert:
    level: str
    message: str
    key: str          # dedupe key


def signal_alerts(consensuses: list, *, min_agreement: int = 60) -> list[Alert]:
    out = []
    for cs in consensuses:
        if cs.consensus is SignalType.HOLD:
            continue
        if cs.agreement_pct < min_agreement:
            continue
        sym = cs.instrument.symbol
        out.append(Alert(level=INFO,
                         message=f"{sym}: {cs.consensus.value} signal "
                                 f"({cs.avg_confidence}% conf, {cs.agreement_pct}% agree)",
                         key=f"sig:{sym}:{cs.consensus.value}"))
    return out


def risk_alerts(risk_check) -> list[Alert]:
    if risk_check is None or risk_check.allowed:
        return []
    return [Alert(level=CRITICAL, message="Risk limit: " + "; ".join(risk_check.reasons),
                  key="risk:blocked")]


def collect(consensuses: list, risk_check=None, *, seen: set | None = None,
            min_agreement: int = 60) -> list[Alert]:
    """Combine signal + risk alerts, dropping any whose key is already in `seen`."""
    seen = seen if seen is not None else set()
    alerts = signal_alerts(consensuses, min_agreement=min_agreement) + \
        risk_alerts(risk_check)
    fresh = [a for a in alerts if a.key not in seen]
    for a in fresh:
        seen.add(a.key)
    return fresh
