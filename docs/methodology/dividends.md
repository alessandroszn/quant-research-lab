# Dividends and distributions

A price series and a total-return series of the same asset differ by the income it paid. Using
a price series where dividends matter leaves income out; adding dividend cash on top of a
total-return series counts it twice. Either way the return is wrong by roughly the dividend
yield, every year, and comparisons with a total-return benchmark become meaningless.

## How it goes wrong

A portfolio holds 100 units of a distributing fund at 100. Over the year the price rises to
102 and the fund pays 3 per unit, so EUR 300 arrives as cash. A total-return series of the
same fund, with the dividend reinvested at 102, ends at 102 x (1 + 3/102) = 105.

```python
start = 100 * 100  # 10,000
price_only = 100 * 102  # 10,200: +2.0 %, dividend missing
correct = 100 * 102 + 300  # 10,500: +5.0 %, price plus dividend cash
double_counted = 100 * 105 + 300  # 10,800: +8.0 %, total-return price plus dividend cash
```

The same mistake distorts fund comparisons. Measured on its price series (+2.0 %) against a
total-return index (+5.0 %), the fund seems to trail its index by 3.0 percentage points. That
gap is the dividend, not tracking.

## How qrlab prevents it

- **The series type is declared.** {py:class}`qrlab.data.PriceType` has `TOTAL_RETURN`
  (dividends reinvested), `PRICE` (dividends excluded) and `NAV`. In a user price file every
  column needs a `price_type` in its {py:class}`qrlab.data.ColumnSpec`; a missing or unknown
  type raises when the mapping is loaded, and the dataset notes record it.
- **Dividends are cash in the ledger.** A `DIVIDEND` transaction
  ({py:class}`qrlab.portfolio.TransactionKind`) needs an ISIN and an amount; a dividend on a
  position not held raises. {py:func}`qrlab.portfolio.replay` records it as
  {py:class}`qrlab.portfolio.Income` with gross amount, withheld tax and net amount in the base
  currency. Dividends are internal flows: they are part of the return, not deposits.
- **Valuation refuses total-return prices.** {py:class}`qrlab.portfolio.PriceSeries` raises for
  `PriceType.TOTAL_RETURN`, because the ledger already books dividends as cash. This blocks
  the double count in the example.
- **Tracking needs income on both sides.** {py:func}`qrlab.lookthrough.tracking_difference`
  and {py:func}`qrlab.lookthrough.tracking_error` accept a fund series only if it is NAV or
  total return, and an index series only if it is total return. A price-only fund series
  raises.
- **Profit and loss shows income on its own line.** {py:func}`qrlab.portfolio.pnl_breakdown`
  has an `income` term, and {py:func}`qrlab.portfolio.contribution_by_position` adds dividends
  to the position that paid them.
- **Distribution policy is master data.** {py:class}`qrlab.instruments.Instrument` has an
  optional `distribution` field ({py:class}`qrlab.instruments.Distribution`: `ACCUMULATING` or
  `DISTRIBUTING`). The `etf_quality.distribution` health check reports the weight of funds
  whose policy differs from a preferred one, and the weight whose policy is unknown.

## What guards it

- `tests/unit/portfolio/test_valuation.py`: `test_total_return_prices_are_refused_for_valuation`,
  `test_price_series_from_price_data`.
- `tests/unit/portfolio/test_ledger.py`: `test_dividend_net_of_withheld_tax_in_base`,
  `test_income_and_flows_are_recorded`, `test_impossible_states_raise` (case
  `dividend-not-held`), `test_transaction_flow_classification`.
- `tests/unit/portfolio/test_performance.py`: `test_pnl_breakdown_toy_reconciles_exactly`
  (the toy portfolio includes a dividend of 100), `test_contribution_by_position_sums_to_total`.
- `tests/unit/lookthrough/test_tracking.py`: `test_series_must_be_comparable`.
- `tests/unit/data/test_user_csv.py`: `test_column_spec_validation`,
  `test_config_with_unknown_or_missing_keys_raises`.
- `tests/unit/checks/test_checks_library.py`: `test_etf_shares_with_unknown_fields`,
  `test_etf_quality_rejects_bad_params`.

## Limits

- **The flag is required only where prices enter.** User price files, valuation and tracking
  check the series type. The `backtest`, `optimisation`, `risk_report` and `scenario_analysis`
  experiment kinds read a CSV of returns with no price-type field. Nothing checks whether those
  returns include dividends; the user must supply total returns. The risk register's
  "total- vs. price-return flag required" is therefore true for price data, not for return
  files.
- **Accumulating versus distributing is recorded, not used in calculations.** The
  `distribution` field is optional and drives only the `etf_quality.distribution` preference
  check. No calculation changes with it, and nothing checks that a distributing fund's
  dividends appear in the ledger.
- The ledger has one date per dividend: the date in the broker export. Ex-date and payment
  date are not distinguished. If the export uses the payment date, a price series that drops
  on the ex-date shows the drop before the cash arrives, so the TWR dips for those days and
  recovers on payment.
- Withheld tax is the amount the broker reports. qrlab does not compute withholding rates or
  model reclaims.
- Dividend cash is not reinvested automatically; it stays cash until a purchase is recorded.

Related: [risk register](../ARCHITECTURE.md#quantitative-risk-register)
