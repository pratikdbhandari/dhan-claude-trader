"""Pure prompt builder. Assembles the structured context the AI providers see."""
from __future__ import annotations
from core.models import ConfluenceSnapshot

_INSTRUCTION = (
    "You are a disciplined intraday/positional trading assistant for Indian markets. "
    "Given the technical confluence, news and fundamentals below, respond with STRICT "
    "JSON only (no prose) of the form: "
    '{"signal":"BUY|SELL|HOLD","confidence":0-100,"entry":number|null,'
    '"stop_loss":number|null,"target":number|null,"reasoning":"...",'
    '"risk_reward_ratio":number|null}.'
)


def build_prompt(*, symbol: str, snapshot: ConfluenceSnapshot, last_price: float,
                 indicators: dict, news: list[str], fundamentals: dict,
                 position: str) -> str:
    votes = "; ".join(f"{v.name}={v.vote.value}({v.strength})" for v in snapshot.votes)
    cats = ", ".join(f"{k}:{round(s, 2)}" for k, s in snapshot.category_scores.items())
    ind = ", ".join(f"{k}={v}" for k, v in indicators.items()) or "n/a"
    nws = " | ".join(news[:8]) or "none"
    fnd = ", ".join(f"{k}={v}" for k, v in fundamentals.items() if v is not None) or "n/a"
    return "\n".join([
        _INSTRUCTION,
        f"Instrument: {symbol}",
        f"Last price: {last_price}",
        f"Regime: {snapshot.regime.value}",
        f"Confluence bias: {snapshot.bias.value} (net_score {snapshot.net_score})",
        f"Category scores: {cats}",
        f"Votes ({snapshot.buy_count}B/{snapshot.sell_count}S/{snapshot.hold_count}H): {votes}",
        f"Indicators: {ind}",
        f"News: {nws}",
        f"Fundamentals: {fnd}",
        f"Open position: {position}",
    ])
