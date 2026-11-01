# Launch post draft (not posted)

I checked 2,082 claims coding agents made about their own work against the tool calls in the same session.

13% had no receipt behind them. "It works" was the worst at 37%, then "tests pass" at 23%. Outright
contradictions were rare, 5 in 2,082. Mostly the agent said it without current evidence.

The existing fix is a Stop hook with pattern rules. I built one, tuned it for 15 rounds, and on held-out data it
agreed with careful readers at chance. A model reading the receipts did far better.

Tool, data pipeline and paper: https://github.com/abhaymettu/receipts
