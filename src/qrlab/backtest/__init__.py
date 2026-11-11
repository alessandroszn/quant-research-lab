"""Signal-to-portfolio simulation with explicit timing.

Core rule: a signal observed at the close of period *t* can only determine
weights traded at *t+1* or later; the execution lag is a required parameter.
Transaction costs, rebalancing policy, taxes and cash treatment are explicit
inputs. Gross and net results are always reported side by side.
"""

from qrlab.backtest.engine import (
    BacktestResult,
    Execution,
    Strategy,
    TradeOnSignal,
    run_backtest,
    run_backtest_targets,
)

__all__ = [
    "BacktestResult",
    "Execution",
    "Strategy",
    "TradeOnSignal",
    "run_backtest",
    "run_backtest_targets",
]
