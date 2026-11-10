"""Signal-to-portfolio simulation with explicit timing.

Core rule: a signal observed at the close of period *t* can only determine
weights traded at *t+1* or later; the execution lag is a required parameter.
Transaction costs, rebalancing schedule, missing prices and cash treatment are
explicit inputs. Gross and net results are always reported side by side.
"""
