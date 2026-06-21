"""Morning briefing orchestration: context -> selection -> narrative.
AI only narrates; rules decide. Narrative falls back to a deterministic template."""
from __future__ import annotations
from services.market_context import MarketContext, build_context
from services.strategy_selector import Selection, select
from services.providers import call_provider


def _template(ctx: MarketContext, sel: Selection) -> str:
    vix = f"VIX {ctx.vix}" if ctx.vix is not None else "VIX n/a"
    rsi = f"RSI {ctx.index_rsi} ({ctx.rsi_state})" if ctx.index_rsi is not None else "RSI n/a"
    caut = (" Caution: " + " ".join(sel.cautions)) if sel.cautions else ""
    return (f"Market regime is {ctx.regime} with {vix} and {rsi}. "
            f"Recommended preset for today: {sel.preset}.{caut}")


def narrative(ctx: MarketContext, sel: Selection, *, mode: str = "mock",
              provider: dict | None = None, client=None) -> str:
    if mode != "api" or provider is None or client is None:
        return _template(ctx, sel)
    prompt = (
        "Write a concise 2-3 sentence pre-market trading briefing for an Indian-market "
        "operator. Be plain, no hype, no guarantees.\n"
        f"Regime: {ctx.regime}\nVIX: {ctx.vix}\nIndex RSI: {ctx.index_rsi} ({ctx.rsi_state})\n"
        f"Events: {', '.join(ctx.event_flags) or 'none'}\n"
        f"News: {' | '.join(ctx.headlines[:5]) or 'none'}\n"
        f"Recommended preset: {sel.preset}\nReasons: {'; '.join(sel.reasons)}\n"
        f"Cautions: {'; '.join(sel.cautions) or 'none'}")
    sig = call_provider(provider, prompt, client=client)
    if sig.error or not sig.reasoning:
        return _template(ctx, sel)
    return sig.reasoning


def morning_briefing(index_instrument, vix_instrument=None, *, dhan_client,
                     mode: str = "mock", provider=None, client=None,
                     news_fetch=None, today=None) -> dict:
    ctx = build_context(index_instrument, vix_instrument, dhan_client=dhan_client,
                        news_fetch=news_fetch, today=today)
    sel = select(ctx)
    text = narrative(ctx, sel, mode=mode, provider=provider, client=client)
    return {"context": ctx, "selection": sel, "narrative": text}
