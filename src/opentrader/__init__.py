"""OpenTrader — trading strategies defined as JSON, evaluated by one shared engine.

Drivers: `opentrader.backtest` (historical replay) and `opentrader.live_paper`
(live poll). Both call `engine.step()`; neither reimplements it.
"""

__version__ = "0.1.0"
