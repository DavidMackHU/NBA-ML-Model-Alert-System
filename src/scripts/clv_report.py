"""Print a markdown CLV report ready to paste into the README.

Usage:
    uv run python -m src.scripts.clv_report
    uv run python -m src.scripts.clv_report --days 90
"""

import argparse
import datetime

from src.db.session import get_session_factory
from src.tracker.live_clv import live_clv_series, live_clv_summary


def _sign(v: float) -> str:
    return "+" if v >= 0 else ""


def _pct(v: float, decimals: int = 2) -> str:
    return f"{_sign(v)}{v * 100:.{decimals}f}%"


def _fmt(v: float, decimals: int = 3) -> str:
    return f"{_sign(v)}{v:.{decimals}f}"


def main(
    days: int = 30,
    now: datetime.datetime | None = None,
) -> None:
    if now is None:
        now = datetime.datetime.utcnow()
    session_factory = get_session_factory()

    with session_factory() as session:
        summary_30 = live_clv_summary(session, days=30, now=now)
        summary_90 = live_clv_summary(session, days=90, now=now)
        _, breakdown = live_clv_series(session, days=days, now=now)

    date_str = now.strftime("%Y-%m-%d")
    window = f"last {days} days"

    print(f"<!-- CLV report generated {date_str} — {window} -->")
    print()
    print("## Live vs Backtest Comparison")
    print()
    print(f"_Last updated: {date_str}_")
    print()

    # ── Rolling summary table ─────────────────────────────────────────────────
    print("### Rolling CLV Summary")
    print()
    print("| Window | Bets | Settled | Mean CLV | Mean EV (model) | ROI | Win Rate |")
    print("|--------|------|---------|----------|-----------------|-----|----------|")

    for label, s in [("30 days", summary_30), ("90 days", summary_90)]:
        clv = _fmt(s.mean_clv)
        ev = _fmt(s.mean_ev)
        roi = _pct(s.roi)
        wr = f"{s.win_rate * 100:.1f}%"
        print(f"| {label} | {s.n_bets} | {s.n_settled} | {clv} | {ev} | {roi} | {wr} |")

    print()
    print(
        "> **Mean CLV** = mean(pin_closing_fair_p − dk_fair_p) per settled bet, "
        "expressed in probability points. Positive = beat Pinnacle closing line on average."
    )
    print()

    # ── Market breakdown ──────────────────────────────────────────────────────
    if breakdown:
        print("### By Market")
        print()
        print("| Market | Bets | Settled | Mean CLV | Mean EV |")
        print("|--------|------|---------|----------|---------|")
        for m in breakdown:
            print(
                f"| {m.market} | {m.n_bets} | {m.n_settled} "
                f"| {_fmt(m.mean_clv)} | {_fmt(m.mean_ev)} |"
            )
        print()

    # ── Interpretation guidance ───────────────────────────────────────────────
    if summary_30.n_settled == 0:
        print("_No settled bets yet — rerun after the first games complete._")
    elif summary_30.n_settled < 50:
        print(
            f"_Sample size is small ({summary_30.n_settled} settled bets). "
            "CLV estimates carry wide confidence intervals at this stage. "
            "Recheck after ≥50 settled bets._"
        )
    else:
        gap = summary_30.mean_clv - summary_30.mean_ev
        direction = "below" if gap < 0 else "above"
        print(
            f"Mean realized CLV ({_fmt(summary_30.mean_clv)}) is "
            f"{abs(gap) * 100:.2f} pp {direction} mean model EV ({_fmt(summary_30.mean_ev)}). "
            "A gap larger than ±1.5 pp warrants investigating line-movement timing, "
            "model staleness, or data feed latency."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Print a README-ready CLV report.")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Window for market breakdown (default: 30)",
    )
    args = parser.parse_args()
    main(days=args.days)
