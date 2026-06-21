"""B2 end-to-end: candles -> confluence -> signal_engine consensus (mock + api)."""
import services.strategies.trend  # noqa: F401
import services.strategies.mean_reversion  # noqa: F401
import services.strategies.breakout  # noqa: F401
import services.strategies.volume  # noqa: F401
import services.strategies.structure  # noqa: F401
from services.strategies.engine import build_confluence
from services.signal_engine import generate
from core.models import Instrument, ConsensusSignal, SignalType


def _instr():
    return Instrument(symbol="X", exchange_segment="NSE_EQ", security_id="1",
                      kind="EQUITY")


def test_pipeline_mock(trending_candles):
    snap = build_confluence(trending_candles, regime=None, style="positional",
                            active_ids=list(range(1, 30)))
    cs = generate(_instr(), snap, last_price=float(trending_candles["close"].iloc[-1]),
                  atr=1.5, mode="mock")
    assert isinstance(cs, ConsensusSignal)
    assert cs.consensus in (SignalType.BUY, SignalType.SELL, SignalType.HOLD)
    assert cs.providers[0].provider == "mock"


def test_pipeline_api_fake_providers(trending_candles):
    snap = build_confluence(trending_candles, regime=None, style="positional",
                            active_ids=list(range(1, 30)))
    specs = [{"name": "groq", "model": "m"}, {"name": "mistral", "model": "m"}]
    factory = lambda spec: (lambda prompt:
        '{"signal":"BUY","confidence":75,"entry":100,"stop_loss":98,'
        '"target":104,"reasoning":"ok","risk_reward_ratio":2.0}')
    cs = generate(_instr(), snap, last_price=100.0, atr=1.5, mode="api",
                  providers=specs, client_factory=factory)
    assert cs.consensus is SignalType.BUY and len(cs.providers) == 2
    assert cs.agreement_pct == 100
