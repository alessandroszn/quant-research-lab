# Currency errors

A portfolio held in one currency often owns assets priced in another. Adding amounts in
different currencies, converting at the wrong date, or reading an asset's local return as the
investor's return all give wrong numbers that look plausible. The size of the error is the
exchange-rate move, which can be as large as the asset's own return.

## How it goes wrong

A euro investor converts EUR 10,000 into USD 11,000 at 1 EUR = 1.10 USD and buys a US stock.
Over the year the stock rises 10 % in dollars, to USD 12,100. The euro strengthens to
1 EUR = 1.20 USD.

```python
local_return = 12_100 / 11_000 - 1  # 0.1000: the return in USD
value_eur = 12_100 / 1.20  # 10,083.33 EUR
base_return = value_eur / 10_000 - 1  # 0.0083: the return in EUR
fx_return = 1.10 / 1.20 - 1  # -0.0833: EUR value of one USD
fx_effect = (1 + local_return) * fx_return  # -0.0917
```

A naive report shows +10.0 %. The investor earned +0.83 % in euros. The difference, -9.17
percentage points, is the currency effect. A second common error is to sum USD 1,000 and
EUR 1,000 into "2,000" of nothing in particular.

## How qrlab prevents it

- **Amounts carry their currency.** {py:class}`qrlab.core.Money` holds an exact `Decimal` and a
  {py:class}`qrlab.core.Currency`. Adding, subtracting or ordering two amounts in different
  currencies raises {py:class}`qrlab.core.CurrencyMismatchError`. A `float` amount is refused,
  and nothing is rounded implicitly.
- **Conversions are explicit and dated.** {py:func}`qrlab.core.convert` needs an
  {py:class}`qrlab.core.FxRate` that names both currencies and its `as_of` date. A rate that
  does not connect the two currencies raises. {py:func}`qrlab.data.fx_rate` returns the ECB
  fixing of one date and never carries a rate forward.
- **Staleness is a required limit.** {py:class}`qrlab.portfolio.EcbConverter` takes
  `max_age_days` with no default. A rate older than the limit raises; every rate carried
  forward is listed in {py:attr}`qrlab.portfolio.EcbConverter.stale_uses`. The portfolio report
  lists each one as a warning, and the `data_quality.stale_fx` health check counts those used
  on the check date.
- **The `portfolio_report` kind converts only with a stated source** (phase 7.4a). Without an
  `fx` input, every amount and price must be in the base currency and a foreign one raises.
  With the ECB `eurofxref-hist` file as `fx` and an explicit `fx_max_age_days`, the kind uses
  `EcbConverter` for the ledger, the valuation, the checks and the report. The report then
  names the FX source and its age limit and lists every rate carried forward. There is one
  extra price file per currency (`[inputs.extra_prices]`), and an ISIN in two price files
  raises.
- **The ledger keeps local and base currency apart.** {py:func}`qrlab.portfolio.replay` keeps
  cash per (account, currency), converts to the base currency only through the caller's
  converter, and raises if the converter returns another currency. An instrument bought in
  one currency cannot be bought again in another. The cost basis is kept in the base currency
  at the rate of each purchase date. An FX conversion executed away from the reference rate
  books the spread as a cost.
- **Valuation checks the price currency.** {py:func}`qrlab.portfolio.value_portfolio` raises
  when a price series is in a different currency from the position.
- **The currency effect is reported separately.** {py:func}`qrlab.portfolio.pnl_breakdown`
  has a `cash_fx` line (the currency effect on cash). {py:func}`qrlab.portfolio.currency_effect`
  splits one return into local return and currency effect (local-first convention, as in the
  example above). {py:func}`qrlab.attribution.currency_attribution` splits portfolio and
  benchmark returns into local, currency and cross parts.
- **Return series in another currency.** {py:func}`qrlab.core.convert_return_currency` needs the
  FX series at every return date plus one earlier date, and raises if the dates do not line up.
- **Comparisons refuse mixed currencies.** {py:func}`qrlab.lookthrough.tracking_difference`
  raises when fund and index differ in currency or hedging, because a currency effect would
  be read as tracking.

## What guards it

- `tests/unit/experiments/test_portfolio_report_currencies.py`:
  `test_usd_position_and_cash_by_hand` (2,000 EUR by hand),
  `test_gbp_base_uses_the_cross_rate` (1,600 GBP), `test_a_stale_rate_is_refused_or_listed`,
  `test_without_fx_a_foreign_amount_still_raises`, `test_an_isin_in_two_price_files`,
  `test_an_fx_sidecar_must_match_the_file`, `test_the_full_example_by_hand` (15,482 EUR).
- `tests/unit/core/test_money.py`: `test_mixing_currencies_raises`,
  `test_float_amounts_are_refused`, `test_arithmetic_never_rounds_implicitly`,
  `test_fx_rate_convention_and_conversion`, `test_convert_with_unrelated_rate_raises`,
  `test_fx_rate_refuses_float_same_currency_and_datetime`.
- `tests/unit/core/test_returns.py`: `test_convert_return_currency_hand_example`,
  `test_convert_return_currency_validation`, `test_convert_return_currency_index_must_follow_fx`.
- `tests/unit/data/test_ecb.py`: `test_fx_rate_bridge_to_core`,
  `test_fx_rate_is_never_forward_filled`.
- `tests/unit/portfolio/test_valuation.py`: `test_converter_staleness_and_missing_values`,
  `test_converter_cross_rate_to_non_eur_base`, `test_price_currency_must_match_position`,
  `test_converter_must_return_base_currency`, `test_multi_currency_valuation_with_ecb_converter`.
- `tests/unit/portfolio/test_ledger.py`: `test_multi_currency_cost_and_realised_gain_in_base`,
  `test_same_isin_in_another_currency_raises`, `test_fx_conversion_spread_is_a_cost`,
  `test_converter_must_return_base_currency`.
- `tests/unit/portfolio/test_performance.py`: `test_currency_effect_hand_example`,
  `test_pnl_breakdown_multi_currency_hand_example`,
  `test_contribution_multi_currency_excludes_cash_fx`.
- `tests/unit/attribution/test_factor_currency.py`: `test_currency_hand_example`,
  `test_currency_active_parts_add_up`.
- `tests/unit/lookthrough/test_tracking.py`: `test_series_must_be_comparable`.
- `tests/unit/checks/test_checks_library.py`: `test_unhedged_foreign_exposure`;
  `tests/unit/checks/test_checks_concentration_costs_data.py`:
  `test_stale_prices_and_fx_on_the_check_date`.
- `tests/unit/reporting/test_portfolio_report.py`: `test_stale_fx_and_wrong_converter_warnings`.

## Limits

- **FX from a local file only.** The `portfolio_report` kind reads the ECB file it is given;
  it does not download one.
- **The currency contribution of positions is not a separate report line.** The report shows
  the currency effect on cash (`cash_fx`). The currency part of a foreign position's gain stays
  inside realised and unrealised P&L. {py:func}`qrlab.portfolio.currency_effect` and
  {py:func}`qrlab.attribution.currency_attribution` exist as library functions, but no report
  or experiment kind calls them yet. The risk register's "currency contribution reported
  separately" holds only for cash.
- ECB reference rates are one daily fixing. They are not taken at the same moment as each
  instrument's closing price, and they have no bid/ask spread. The spread paid is captured
  only when an FX conversion transaction records the amount actually received.
- Only the currencies listed in `qrlab.core.money.MINOR_UNITS` are supported.
- Hedged share classes are handled by metadata (`hedged_to`), not by modelling the hedge.

Related: [risk register](../ARCHITECTURE.md#quantitative-risk-register)
