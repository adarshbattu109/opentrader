"""Mock ledger: a dict of open positions + a list of closed trades. POC scope (§2.1).

Money is Decimal from signal-to-order-intent onward (§18 Decimal boundary);
indicator math upstream stays float/pandas.
"""

import csv
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal


def to_money(value) -> Decimal:
    """The one money constructor. Never Decimal(float) -- goes via str (§18)."""
    return Decimal(str(value))


@dataclass
class Position:
    symbol: str
    entry_time: datetime
    entry_price: Decimal
    stop_loss: Decimal
    target: Decimal
    qty: int = 1


@dataclass
class Trade:
    symbol: str
    entry_time: datetime
    entry_price: Decimal
    exit_time: datetime
    exit_price: Decimal
    exit_reason: str
    qty: int
    pnl: Decimal


class MockLedger:
    def __init__(self) -> None:
        self.open: dict[str, Position] = {}
        self.closed: list[Trade] = []

    def enter(
        self,
        symbol: str,
        time: datetime,
        price,
        stop_loss_pct: float,
        risk_reward_ratio: float,
        qty: int = 1,
    ) -> Position:
        """Long entry. Stop and target are computed once, here, and never move."""
        entry = to_money(price)
        risk = entry * to_money(stop_loss_pct) / to_money(100)
        pos = Position(
            symbol=symbol,
            entry_time=time,
            entry_price=entry,
            stop_loss=entry - risk,
            target=entry + risk * to_money(risk_reward_ratio),
            qty=qty,
        )
        self.open[symbol] = pos
        return pos

    def exit(self, symbol: str, time: datetime, price, reason: str) -> Trade:
        pos = self.open.pop(symbol)
        exit_price = to_money(price)
        trade = Trade(
            symbol=symbol,
            entry_time=pos.entry_time,
            entry_price=pos.entry_price,
            exit_time=time,
            exit_price=exit_price,
            exit_reason=reason,
            qty=pos.qty,
            pnl=(exit_price - pos.entry_price) * pos.qty,
        )
        self.closed.append(trade)
        return trade

    def to_csv(self, path: str) -> None:
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[f for f in Trade.__annotations__])
            w.writeheader()
            w.writerows(asdict(t) for t in self.closed)
