import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import plotly.graph_objects as go
from plotly.offline import plot
from plotly.subplots import make_subplots

from freqtrade.constants import UNLIMITED_STAKE_AMOUNT, Config
from freqtrade.ft_types import BacktestResultType
from freqtrade.optimize.optimize_reports.optimize_reports import generate_periodic_breakdown_stats
from freqtrade.util import decimals_per_coin, fmt_coin, print_rich_table


PLOTTING_AVAILABLE = True


logger = logging.getLogger(__name__)


def create_enhanced_pair_visualization(
    pair: str, trades: list[dict], stake_currency: str, config: Config, results: dict[str, Any]
) -> str:
    """
    Create an enhanced interactive visualization for a specific trading pair
    showing all entry/exit points.
    :param pair: Trading pair name
    :param trades: List of trade dictionaries for this pair
    :param stake_currency: Stake currency
    :param config: Configuration dictionary
    :param results: Backtest results for additional context
    :return: HTML string of the interactive plot
    """
    if not PLOTTING_AVAILABLE:
        logger.warning("Plotting libraries not available. Install with: pip install plotly pandas")
        return ""

    if not trades:
        logger.info(f"No trades found for pair {pair}")
        return ""

    # Convert trades to DataFrame for easier manipulation
    df_trades = pd.DataFrame(trades)
    df_trades = df_trades[df_trades["pair"] == pair].copy()

    if len(df_trades) == 0:
        return ""

    # Convert date columns to datetime
    df_trades["open_date"] = pd.to_datetime(df_trades["open_date"])
    df_trades["close_date"] = pd.to_datetime(df_trades["close_date"])

    # Create main figure with subplots
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.6, 0.25, 0.15],
        subplot_titles=[
            f"{pair} - Entry/Exit Points Analysis",
            "Profit/Loss per Trade",
            "Trade Duration Analysis",
        ],
    )

    # Plot 1: Price action with entry/exit points
    # We'll create a simplified price representation using trade data
    all_dates = list(df_trades["open_date"]) + list(df_trades["close_date"])
    all_prices = list(df_trades["open_rate"]) + list(df_trades["close_rate"])

    # Sort by date for a proper time series
    date_price_pairs = sorted(zip(all_dates, all_prices, strict=False))
    dates, prices = zip(*date_price_pairs, strict=False)

    # Add price line (simplified representation)
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=prices,
            mode="lines",
            name="Price",
            line=dict(color="lightblue", width=1),
            opacity=0.6,
        ),
        row=1,
        col=1,
    )

    # Add entry points
    fig.add_trace(
        go.Scatter(
            x=df_trades["open_date"],
            y=df_trades["open_rate"],
            mode="markers",
            name="Entry Points",
            marker=dict(
                symbol="triangle-up", size=12, color="green", line=dict(width=2, color="darkgreen")
            ),
            text=[
                (
                    f"Entry: {row['open_rate']:.4f}"
                    f"<br>Amount: {row['amount']:.4f}"
                    f"<br>Tag: {row.get('enter_tag', 'N/A')}"
                )
                for _, row in df_trades.iterrows()
            ],
            hovertemplate="<b>ENTRY</b><br>%{text}<br>Date: %{x}<extra></extra>",
        ),
        row=1,
        col=1,
    )

    # Add profitable exit points
    profitable_trades = df_trades[df_trades["profit_ratio"] > 0]
    if len(profitable_trades) > 0:
        fig.add_trace(
            go.Scatter(
                x=profitable_trades["close_date"],
                y=profitable_trades["close_rate"],
                mode="markers",
                name="Profitable Exits",
                marker=dict(
                    symbol="triangle-down",
                    size=12,
                    color="lime",
                    line=dict(width=2, color="darkgreen"),
                ),
                text=[
                    (
                        f"Exit: {row['close_rate']:.4f}"
                        f"<br>Profit: {row['profit_ratio']:.2%}"
                        f"<br>Reason: {row['exit_reason']}"
                    )
                    for _, row in profitable_trades.iterrows()
                ],
                hovertemplate="<b>PROFITABLE EXIT</b><br>%{text}<br>Date: %{x}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    # Add loss exit points
    loss_trades = df_trades[df_trades["profit_ratio"] <= 0]
    if len(loss_trades) > 0:
        fig.add_trace(
            go.Scatter(
                x=loss_trades["close_date"],
                y=loss_trades["close_rate"],
                mode="markers",
                name="Loss Exits",
                marker=dict(
                    symbol="triangle-down",
                    size=12,
                    color="red",
                    line=dict(width=2, color="darkred"),
                ),
                text=[
                    (
                        f"Exit: {row['close_rate']:.4f}"
                        f"<br>Loss: {row['profit_ratio']:.2%}"
                        f"<br>Reason: {row['exit_reason']}"
                    )
                    for _, row in loss_trades.iterrows()
                ],
                hovertemplate="<b>LOSS EXIT</b><br>%{text}<br>Date: %{x}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    # Plot 2: Profit/Loss visualization
    colors = ["green" if x > 0 else "red" for x in df_trades["profit_ratio"]]
    fig.add_trace(
        go.Bar(
            x=df_trades["close_date"],
            y=df_trades["profit_ratio"] * 100,
            name="Trade Profit %",
            marker_color=colors,
            text=[f"{x:.2%}" for x in df_trades["profit_ratio"]],
            textposition="outside",
            hovertemplate="<b>Trade Profit</b><br>%{y:.2f}%<br>Date: %{x}<extra></extra>",
        ),
        row=2,
        col=1,
    )

    # Plot 3: Trade duration
    # Convert trade_duration to hours for better visualization
    durations_hours = []
    for duration_str in df_trades["trade_duration"]:
        try:
            # Parse different duration formats
            if "days" in str(duration_str):
                # Format like "2 days, 3:45:00"
                parts = str(duration_str).split(",")
                days = int(parts[0].split()[0])
                time_part = parts[1].strip() if len(parts) > 1 else "0:00:00"
                hours, minutes, seconds = map(int, time_part.split(":"))
                total_hours = days * 24 + hours + minutes / 60 + seconds / 3600
            else:
                # Format like "3:45:00"
                time_parts = str(duration_str).split(":")
                if len(time_parts) == 3:
                    hours, minutes, seconds = map(int, time_parts)
                    total_hours = hours + minutes / 60 + seconds / 3600
                else:
                    total_hours = 0
            durations_hours.append(total_hours)
        except Exception:
            durations_hours.append(0)

    fig.add_trace(
        go.Bar(
            x=df_trades["close_date"],
            y=durations_hours,
            name="Duration (hours)",
            marker_color="lightblue",
            text=[f"{x:.1f}h" for x in durations_hours],
            textposition="outside",
            hovertemplate="<b>Trade Duration</b><br>%{y:.1f} hours<br>Date: %{x}<extra></extra>",
        ),
        row=3,
        col=1,
    )

    # Update layout
    fig.update_layout(
        title=f"Trading Analysis: {pair}", height=800, showlegend=True, hovermode="x unified"
    )

    # Update y-axis labels
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Profit %", row=2, col=1)
    fig.update_yaxes(title_text="Hours", row=3, col=1)
    fig.update_xaxes(title_text="Date", row=3, col=1)

    # Convert to HTML
    html_content = plot(fig, output_type="div", include_plotlyjs=True)
    return html_content


def create_pairs_summary_dashboard(backtest_stats: BacktestResultType, stake_currency: str) -> str:
    """
    Create a comprehensive dashboard showing all pairs performance
    :param backtest_stats: Complete backtest statistics
    :param stake_currency: Stake currency
    :return: HTML string of the dashboard
    """
    if not PLOTTING_AVAILABLE:
        return ""

    # Extract data for all strategies
    all_pair_results = []
    for strategy, results in backtest_stats["strategy"].items():
        for pair_result in results["results_per_pair"]:
            if pair_result["key"] != "TOTAL":
                pair_result["strategy"] = strategy
                all_pair_results.append(pair_result)

    if not all_pair_results:
        return ""

    df_pairs = pd.DataFrame(all_pair_results)

    # Create dashboard with multiple subplots
    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=[
            "Profit by Pair",
            "Win Rate by Pair",
            "Trade Count by Pair",
            "Risk vs Reward Analysis",
        ],
    )

    # Plot 1: Profit by pair
    colors = ["green" if x > 0 else "red" for x in df_pairs["profit_total_pct"]]
    fig.add_trace(
        go.Bar(
            x=df_pairs["key"],
            y=df_pairs["profit_total_pct"],
            name="Total Profit %",
            marker_color=colors,
            text=[f"{x:.2f}%" for x in df_pairs["profit_total_pct"]],
            textposition="outside",
        ),
        row=1,
        col=1,
    )

    # Plot 2: Win rate by pair
    win_rates = [
        row["wins"] / row["trades"] * 100 if row["trades"] > 0 else 0
        for _, row in df_pairs.iterrows()
    ]
    fig.add_trace(
        go.Bar(
            x=df_pairs["key"],
            y=win_rates,
            name="Win Rate %",
            marker_color="lightblue",
            text=[f"{x:.1f}%" for x in win_rates],
            textposition="outside",
        ),
        row=1,
        col=2,
    )

    # Plot 3: Trade count by pair
    fig.add_trace(
        go.Bar(
            x=df_pairs["key"],
            y=df_pairs["trades"],
            name="Trade Count",
            marker_color="orange",
            text=df_pairs["trades"],
            textposition="outside",
        ),
        row=2,
        col=1,
    )

    # Plot 4: Risk vs Reward scatter
    fig.add_trace(
        go.Scatter(
            x=win_rates,
            y=df_pairs["profit_total_pct"],
            mode="markers+text",
            name="Risk vs Reward",
            text=df_pairs["key"],
            textposition="top center",
            marker=dict(
                size=df_pairs["trades"],
                sizemode="diameter",
                sizeref=2.0 * max(df_pairs["trades"]) / (40.0**2),
                sizemin=4,
                color=df_pairs["profit_total_pct"],
                colorscale="RdYlGn",
                showscale=True,
                colorbar=dict(title="Profit %"),
            ),
        ),
        row=2,
        col=2,
    )

    # Update layout
    fig.update_layout(title="Trading Pairs Performance Dashboard", height=800, showlegend=False)

    # Update axes
    fig.update_yaxes(title_text="Profit %", row=1, col=1)
    fig.update_yaxes(title_text="Win Rate %", row=1, col=2)
    fig.update_yaxes(title_text="Trade Count", row=2, col=1)
    fig.update_yaxes(title_text="Profit %", row=2, col=2)
    fig.update_xaxes(title_text="Pairs", row=1, col=1)
    fig.update_xaxes(title_text="Pairs", row=1, col=2)
    fig.update_xaxes(title_text="Pairs", row=2, col=1)
    fig.update_xaxes(title_text="Win Rate %", row=2, col=2)

    # Rotate x-axis labels for better readability
    for i in range(1, 3):
        for j in range(1, 3):
            if i == 2 and j == 2:
                continue  # Skip the scatter plot
            fig.update_xaxes(tickangle=45, row=i, col=j)

    html_content = plot(fig, output_type="div", include_plotlyjs=True)
    return html_content


def _get_line_floatfmt(stake_currency: str) -> list[str]:
    """
    Generate floatformat (goes in line with _generate_result_line())
    """
    return ["s", "d", ".2f", f".{decimals_per_coin(stake_currency)}f", ".2f", "d", "s", "s"]


def _get_line_header(
    first_column: str | list[str], stake_currency: str, direction: str = "Trades"
) -> list[str]:
    """
    Generate header lines (goes in line with _generate_result_line())
    """
    return [
        *([first_column] if isinstance(first_column, str) else first_column),
        direction,
        "Avg Profit %",
        f"Tot Profit {stake_currency}",
        "Tot Profit %",
        "Avg Duration",
        "Win  Draw  Loss  Win%",
    ]


def generate_wins_draws_losses(wins, draws, losses):
    if wins > 0 and losses == 0:
        wl_ratio = "100"
    elif wins == 0:
        wl_ratio = "0"
    else:
        wl_ratio = f"{100.0 / (wins + draws + losses) * wins:.1f}" if losses > 0 else "100"
    return f"{wins:>4}  {draws:>4}  {losses:>4}  {wl_ratio:>4}"


def text_table_bt_results(
    pair_results: list[dict[str, Any]], stake_currency: str, title: str
) -> None:
    """
    Generates and returns a text table for the given backtest data and the results dataframe
    :param pair_results: List of Dictionaries - one entry per pair + final TOTAL row
    :param stake_currency: stake-currency - used to correctly name headers
    :param title: Title of the table
    """

    headers = _get_line_header("Pair", stake_currency, "Trades")
    output = [
        [
            t["key"],
            t["trades"],
            t["profit_mean_pct"],
            f"{t['profit_total_abs']:.{decimals_per_coin(stake_currency)}f}",
            t["profit_total_pct"],
            t["duration_avg"],
            generate_wins_draws_losses(t["wins"], t["draws"], t["losses"]),
        ]
        for t in pair_results
    ]
    # Ignore type as floatfmt does allow tuples but mypy does not know that
    print_rich_table(output, headers, summary=title)


def text_table_tags(
    tag_type: Literal["enter_tag", "exit_tag", "mix_tag"],
    tag_results: list[dict[str, Any]],
    stake_currency: str,
) -> None:
    """
    Generates and returns a text table for the given backtest data and the results dataframe
    :param pair_results: List of Dictionaries - one entry per pair + final TOTAL row
    :param stake_currency: stake-currency - used to correctly name headers
    """
    floatfmt = _get_line_floatfmt(stake_currency)
    fallback: str = ""
    is_list = False
    if tag_type == "enter_tag":
        title = "Enter Tag"
        headers = _get_line_header(title, stake_currency, "Entries")
    elif tag_type == "exit_tag":
        title = "Exit Reason"
        headers = _get_line_header(title, stake_currency, "Exits")
        fallback = "exit_reason"
    else:
        # Mix tag
        title = "Mixed Tag"
        headers = _get_line_header(["Enter Tag", "Exit Reason"], stake_currency, "Trades")
        floatfmt.insert(0, "s")
        is_list = True

    output = [
        [
            *(
                (
                    list(t["key"])
                    if isinstance(t["key"], list | tuple)
                    else [t["key"], ""]
                    if is_list
                    else [t["key"]]
                )
                if t.get("key") is not None and len(str(t["key"])) > 0
                else [t.get(fallback, "OTHER")]
            ),
            t["trades"],
            t["profit_mean_pct"],
            f"{t['profit_total_abs']:.{decimals_per_coin(stake_currency)}f}",
            t["profit_total_pct"],
            t.get("duration_avg"),
            generate_wins_draws_losses(t["wins"], t["draws"], t["losses"]),
        ]
        for t in tag_results
    ]
    # Ignore type as floatfmt does allow tuples but mypy does not know that
    print_rich_table(output, headers, summary=f"{title.upper()} STATS")


def text_table_periodic_breakdown(
    days_breakdown_stats: list[dict[str, Any]], stake_currency: str, period: str
) -> None:
    """
    Generate small table with Backtest results by days
    :param days_breakdown_stats: Days breakdown metrics
    :param stake_currency: Stakecurrency used
    """
    headers = [
        period.capitalize(),
        "Trades",
        f"Tot Profit {stake_currency}",
        "Profit Factor",
        "Win  Draw  Loss  Win%",
    ]
    output = [
        [
            d["date"],
            d.get("trades", "N/A"),
            fmt_coin(d["profit_abs"], stake_currency, False),
            round(d["profit_factor"], 2) if "profit_factor" in d else "N/A",
            generate_wins_draws_losses(d["wins"], d["draws"], d.get("losses", d.get("loses", 0))),
        ]
        for d in days_breakdown_stats
    ]
    print_rich_table(output, headers, summary=f"{period.upper()} BREAKDOWN")


def text_table_strategy(strategy_results, stake_currency: str, title: str):
    """
    Generate summary table per strategy
    :param strategy_results: Dict of <Strategyname: DataFrame> containing results for all strategies
    :param stake_currency: stake-currency - used to correctly name headers
    """
    headers = _get_line_header("Strategy", stake_currency, "Trades")
    # _get_line_header() is also used for per-pair summary. Per-pair drawdown is mostly useless
    # therefore we slip this column in only for strategy summary here.
    headers.append("Drawdown")

    # Align drawdown string on the center two space separator.
    if "max_drawdown_account" in strategy_results[0]:
        drawdown = [f"{t['max_drawdown_account'] * 100:.2f}" for t in strategy_results]
    else:
        # Support for prior backtest results
        drawdown = [f"{t['max_drawdown_per']:.2f}" for t in strategy_results]

    dd_pad_abs = max([len(t["max_drawdown_abs"]) for t in strategy_results])
    dd_pad_per = max([len(dd) for dd in drawdown])
    drawdown = [
        f"{t['max_drawdown_abs']:>{dd_pad_abs}} {stake_currency}  {dd:>{dd_pad_per}}%"
        for t, dd in zip(strategy_results, drawdown, strict=False)
    ]

    output = [
        [
            t["key"],
            t["trades"],
            f"{t['profit_mean_pct']:.2f}",
            f"{t['profit_total_abs']:.{decimals_per_coin(stake_currency)}f}",
            t["profit_total_pct"],
            t["duration_avg"],
            generate_wins_draws_losses(t["wins"], t["draws"], t["losses"]),
            drawdown,
        ]
        for t, drawdown in zip(strategy_results, drawdown, strict=False)
    ]
    print_rich_table(output, headers, summary=title)


def text_table_add_metrics(strat_results: dict) -> None:
    if len(strat_results["trades"]) > 0:
        best_trade = max(strat_results["trades"], key=lambda x: x["profit_ratio"])
        worst_trade = min(strat_results["trades"], key=lambda x: x["profit_ratio"])

        short_metrics = (
            [
                ("", ""),  # Empty line to improve readability
                (
                    "Long / Short",
                    f"{strat_results.get('trade_count_long', 'total_trades')} / "
                    f"{strat_results.get('trade_count_short', 0)}",
                ),
                ("Total profit Long %", f"{strat_results['profit_total_long']:.2%}"),
                ("Total profit Short %", f"{strat_results['profit_total_short']:.2%}"),
                (
                    "Absolute profit Long",
                    fmt_coin(
                        strat_results["profit_total_long_abs"], strat_results["stake_currency"]
                    ),
                ),
                (
                    "Absolute profit Short",
                    fmt_coin(
                        strat_results["profit_total_short_abs"], strat_results["stake_currency"]
                    ),
                ),
            ]
            if strat_results.get("trade_count_short", 0) > 0
            else []
        )

        drawdown_metrics = []
        if "max_relative_drawdown" in strat_results:
            # Compatibility to show old hyperopt results
            drawdown_metrics.append(
                ("Max % of account underwater", f"{strat_results['max_relative_drawdown']:.2%}")
            )
        drawdown_metrics.extend(
            [
                (
                    ("Absolute Drawdown (Account)", f"{strat_results['max_drawdown_account']:.2%}")
                    if "max_drawdown_account" in strat_results
                    else ("Drawdown", f"{strat_results['max_drawdown']:.2%}")
                ),
                (
                    "Absolute Drawdown",
                    fmt_coin(strat_results["max_drawdown_abs"], strat_results["stake_currency"]),
                ),
                (
                    "Drawdown high",
                    fmt_coin(strat_results["max_drawdown_high"], strat_results["stake_currency"]),
                ),
                (
                    "Drawdown low",
                    fmt_coin(strat_results["max_drawdown_low"], strat_results["stake_currency"]),
                ),
                ("Drawdown Start", strat_results["drawdown_start"]),
                ("Drawdown End", strat_results["drawdown_end"]),
            ]
        )

        entry_adjustment_metrics = (
            [
                ("Canceled Trade Entries", strat_results.get("canceled_trade_entries", "N/A")),
                ("Canceled Entry Orders", strat_results.get("canceled_entry_orders", "N/A")),
                ("Replaced Entry Orders", strat_results.get("replaced_entry_orders", "N/A")),
            ]
            if strat_results.get("canceled_entry_orders", 0) > 0
            else []
        )

        trading_mode = (
            (
                [
                    (
                        "Trading Mode",
                        (
                            ""
                            if not strat_results.get("margin_mode")
                            or strat_results.get("trading_mode", "spot") == "spot"
                            else f"{strat_results['margin_mode'].capitalize()} "
                        )
                        + f"{strat_results['trading_mode'].capitalize()}",
                    )
                ]
            )
            if "trading_mode" in strat_results
            else []
        )

        # Newly added fields should be ignored if they are missing in strat_results. hyperopt-show
        # command stores these results and newer version of freqtrade must be able to handle old
        # results with missing new fields.
        metrics = [
            ("Backtesting from", strat_results["backtest_start"]),
            ("Backtesting to", strat_results["backtest_end"]),
            *trading_mode,
            ("Max open trades", strat_results["max_open_trades"]),
            ("", ""),  # Empty line to improve readability
            (
                "Total/Daily Avg Trades",
                f"{strat_results['total_trades']} / {strat_results['trades_per_day']}",
            ),
            (
                "Starting balance",
                fmt_coin(strat_results["starting_balance"], strat_results["stake_currency"]),
            ),
            (
                "Final balance",
                fmt_coin(strat_results["final_balance"], strat_results["stake_currency"]),
            ),
            (
                "Absolute profit ",
                fmt_coin(strat_results["profit_total_abs"], strat_results["stake_currency"]),
            ),
            ("Total profit %", f"{strat_results['profit_total']:.2%}"),
            ("CAGR %", f"{strat_results['cagr']:.2%}" if "cagr" in strat_results else "N/A"),
            ("Sortino", f"{strat_results['sortino']:.2f}" if "sortino" in strat_results else "N/A"),
            ("Sharpe", f"{strat_results['sharpe']:.2f}" if "sharpe" in strat_results else "N/A"),
            ("Calmar", f"{strat_results['calmar']:.2f}" if "calmar" in strat_results else "N/A"),
            ("SQN", f"{strat_results['sqn']:.2f}" if "sqn" in strat_results else "N/A"),
            (
                "Profit factor",
                (
                    f"{strat_results['profit_factor']:.2f}"
                    if "profit_factor" in strat_results
                    else "N/A"
                ),
            ),
            (
                "Expectancy (Ratio)",
                (
                    f"{strat_results['expectancy']:.2f} ({strat_results['expectancy_ratio']:.2f})"
                    if "expectancy_ratio" in strat_results
                    else "N/A"
                ),
            ),
            (
                "Avg. daily profit",
                fmt_coin(
                    (strat_results["profit_total_abs"] / strat_results["backtest_days"]),
                    strat_results["stake_currency"],
                ),
            ),
            (
                "Avg. stake amount",
                fmt_coin(strat_results["avg_stake_amount"], strat_results["stake_currency"]),
            ),
            (
                "Total trade volume",
                fmt_coin(strat_results["total_volume"], strat_results["stake_currency"]),
            ),
            *short_metrics,
            ("", ""),  # Empty line to improve readability
            (
                "Best Pair",
                f"{strat_results['best_pair']['key']} "
                f"{strat_results['best_pair']['profit_total']:.2%}",
            ),
            (
                "Worst Pair",
                f"{strat_results['worst_pair']['key']} "
                f"{strat_results['worst_pair']['profit_total']:.2%}",
            ),
            ("Best trade", f"{best_trade['pair']} {best_trade['profit_ratio']:.2%}"),
            ("Worst trade", f"{worst_trade['pair']} {worst_trade['profit_ratio']:.2%}"),
            (
                "Best day",
                fmt_coin(strat_results["backtest_best_day_abs"], strat_results["stake_currency"]),
            ),
            (
                "Worst day",
                fmt_coin(strat_results["backtest_worst_day_abs"], strat_results["stake_currency"]),
            ),
            (
                "Days win/draw/lose",
                f"{strat_results['winning_days']} / "
                f"{strat_results['draw_days']} / {strat_results['losing_days']}",
            ),
            (
                "Min/Max/Avg. Duration Winners",
                f"{strat_results.get('winner_holding_min', 'N/A')} / "
                f"{strat_results.get('winner_holding_max', 'N/A')} / "
                f"{strat_results.get('winner_holding_avg', 'N/A')}",
            ),
            (
                "Min/Max/Avg. Duration Losers",
                f"{strat_results.get('loser_holding_min', 'N/A')} / "
                f"{strat_results.get('loser_holding_max', 'N/A')} / "
                f"{strat_results.get('loser_holding_avg', 'N/A')}",
            ),
            (
                "Max Consecutive Wins / Loss",
                (
                    (
                        f"{strat_results['max_consecutive_wins']} / "
                        f"{strat_results['max_consecutive_losses']}"
                    )
                    if "max_consecutive_losses" in strat_results
                    else "N/A"
                ),
            ),
            ("Rejected Entry signals", strat_results.get("rejected_signals", "N/A")),
            (
                "Entry/Exit Timeouts",
                f"{strat_results.get('timedout_entry_orders', 'N/A')} / "
                f"{strat_results.get('timedout_exit_orders', 'N/A')}",
            ),
            *entry_adjustment_metrics,
            ("", ""),  # Empty line to improve readability
            ("Min balance", fmt_coin(strat_results["csum_min"], strat_results["stake_currency"])),
            ("Max balance", fmt_coin(strat_results["csum_max"], strat_results["stake_currency"])),
            *drawdown_metrics,
            ("Market change", f"{strat_results['market_change']:.2%}"),
        ]
        print_rich_table(metrics, ["Metric", "Value"], summary="SUMMARY METRICS", justify="left")

    else:
        start_balance = fmt_coin(strat_results["starting_balance"], strat_results["stake_currency"])
        stake_amount = (
            fmt_coin(strat_results["stake_amount"], strat_results["stake_currency"])
            if strat_results["stake_amount"] != UNLIMITED_STAKE_AMOUNT
            else "unlimited"
        )

        message = (
            "No trades made. "
            f"Your starting balance was {start_balance}, "
            f"and your stake was {stake_amount}."
        )
        print(message)


def _show_tag_subresults(results: dict[str, Any], stake_currency: str):
    """
    Print tag subresults (enter_tag, exit_reason_summary, mix_tag_stats)
    """
    if (enter_tags := results.get("results_per_enter_tag")) is not None:
        text_table_tags("enter_tag", enter_tags, stake_currency)

    if (exit_reasons := results.get("exit_reason_summary")) is not None:
        text_table_tags("exit_tag", exit_reasons, stake_currency)

    if (mix_tag := results.get("mix_tag_stats")) is not None:
        text_table_tags("mix_tag", mix_tag, stake_currency)


def show_backtest_result(
    strategy: str, results: dict[str, Any], stake_currency: str, backtest_breakdown: list[str]
):
    """
    Print results for one strategy
    """
    # Print results
    print(f"Result for strategy {strategy}")
    text_table_bt_results(
        results["results_per_pair"], stake_currency=stake_currency, title="BACKTESTING REPORT"
    )
    text_table_bt_results(
        results["left_open_trades"], stake_currency=stake_currency, title="LEFT OPEN TRADES REPORT"
    )

    _show_tag_subresults(results, stake_currency)

    for period in backtest_breakdown:
        if period in results.get("periodic_breakdown", {}):
            days_breakdown_stats = results["periodic_breakdown"][period]
        else:
            days_breakdown_stats = generate_periodic_breakdown_stats(
                trade_list=results["trades"], period=period
            )
        text_table_periodic_breakdown(
            days_breakdown_stats=days_breakdown_stats, stake_currency=stake_currency, period=period
        )

    text_table_add_metrics(results)

    print()


def show_backtest_results(
    config: Config, backtest_stats: BacktestResultType, *, skip_console_markdown: bool = False
):
    stake_currency = config["stake_currency"]

    for strategy, results in backtest_stats["strategy"].items():
        show_backtest_result(
            strategy, results, stake_currency, config.get("backtest_breakdown", [])
        )

    if len(backtest_stats["strategy"]) > 0:
        # Print Strategy summary table

        print(
            f"Backtested {results['backtest_start']} -> {results['backtest_end']} |"
            f" Max open trades : {results['max_open_trades']}"
        )
        text_table_strategy(
            backtest_stats["strategy_comparison"], stake_currency, "STRATEGY SUMMARY"
        )

    # Additionally save console output as Markdown files per strategy
    # Skip if console markdown was already generated during storage phase
    if not skip_console_markdown:
        try:
            write_backtest_console_markdown(config, backtest_stats)
        except Exception as e:
            logger.warning(f"Failed to write console markdown: {e}")


def show_sorted_pairlist(config: Config, backtest_stats: BacktestResultType):
    if config.get("backtest_show_pair_list", False):
        for strategy, results in backtest_stats["strategy"].items():
            print(f"Pairs for Strategy {strategy}: \n[")
            for result in results["results_per_pair"]:
                if result["key"] != "TOTAL":
                    print(f'"{result["key"]}",  // {result["profit_mean"]:.2%}')
            print("]")


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """
    Render a simple GitHub-flavored Markdown table.
    Align headers left for text columns and right for others for readability.
    """
    # Header row
    lines: list[str] = ["| " + " | ".join(headers) + " |"]
    # Alignment row: left-align the first column, right-align the rest
    aligns = [":-" if i == 0 else "-:" for i in range(len(headers))]
    lines.append("| " + " | ".join(aligns) + " |")
    # Data rows
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def _export_base_dir(config: Config) -> Path:
    """
    Determine the base directory to write exported markdown files to, based on
    the existing exportfilename configuration.
    """
    recordfilename: Path = config["exportfilename"]
    return recordfilename if recordfilename.is_dir() else recordfilename.parent


def _bt_results_rows(pair_results: list[dict[str, Any]], stake_currency: str) -> list[list[str]]:
    return [
        [
            str(t["key"]),
            str(t["trades"]),
            f"{t['profit_mean_pct']}",
            f"{t['profit_total_abs']:.{decimals_per_coin(stake_currency)}f}",
            f"{t['profit_total_pct']}",
            str(t.get("duration_avg", "N/A")),
            generate_wins_draws_losses(t["wins"], t["draws"], t["losses"]),
        ]
        for t in pair_results
    ]


def _tag_results_rows(
    tag_type: Literal["enter_tag", "exit_tag", "mix_tag"],
    tag_results: list[dict[str, Any]],
    stake_currency: str,
) -> tuple[list[str], list[list[str]]]:
    if tag_type == "enter_tag":
        title = "Enter Tag"
        headers = _get_line_header(title, stake_currency, "Entries")
        is_list = False
        fallback = ""
    elif tag_type == "exit_tag":
        title = "Exit Reason"
        headers = _get_line_header(title, stake_currency, "Exits")
        is_list = False
        fallback = "exit_reason"
    else:
        title = "Mixed Tag"
        headers = _get_line_header(["Enter Tag", "Exit Reason"], stake_currency, "Trades")
        is_list = True
        fallback = ""

    rows: list[list[str]] = [
        [
            *(
                (
                    [str(x) for x in list(t["key"])]
                    if isinstance(t["key"], list | tuple)
                    else [str(t["key"]), ""]
                )
                if is_list
                else [str(t["key"])]
                if t.get("key") is not None and len(str(t["key"])) > 0
                else [str(t.get(fallback, "OTHER"))]
            ),
            str(t["trades"]),
            f"{t['profit_mean_pct']}",
            f"{t['profit_total_abs']:.{decimals_per_coin(stake_currency)}f}",
            f"{t['profit_total_pct']}",
            str(t.get("duration_avg", "N/A")),
            generate_wins_draws_losses(t["wins"], t["draws"], t["losses"]),
        ]
        for t in tag_results
    ]
    return headers, rows


def _periodic_breakdown_rows(
    days_breakdown_stats: list[dict[str, Any]], stake_currency: str, period: str
) -> tuple[list[str], list[list[str]]]:
    headers = [
        period.capitalize(),
        "Trades",
        f"Tot Profit {stake_currency}",
        "Profit Factor",
        "Win  Draw  Loss  Win%",
    ]
    rows = [
        [
            d["date"],
            d.get("trades", "N/A"),
            fmt_coin(d["profit_abs"], stake_currency, False),
            round(d["profit_factor"], 2) if "profit_factor" in d else "N/A",
            generate_wins_draws_losses(d["wins"], d["draws"], d.get("losses", d.get("loses", 0))),
        ]
        for d in days_breakdown_stats
    ]
    return headers, rows


def _strategy_summary_rows(
    strategy_results: list[dict[str, Any]], stake_currency: str
) -> tuple[list[str], list[list[str]]]:
    headers = _get_line_header("Strategy", stake_currency, "Trades")
    headers.append("Drawdown")

    if "max_drawdown_account" in strategy_results[0]:
        dd_values = [f"{t['max_drawdown_account'] * 100:.2f}" for t in strategy_results]
    else:
        dd_values = [f"{t['max_drawdown_per']:.2f}" for t in strategy_results]

    dd_pad_abs = max([len(t["max_drawdown_abs"]) for t in strategy_results])
    dd_pad_per = max([len(dd) for dd in dd_values])
    dd_joined = [
        f"{t['max_drawdown_abs']:>{dd_pad_abs}} {stake_currency}  {dd:>{dd_pad_per}}%"
        for t, dd in zip(strategy_results, dd_values, strict=False)
    ]

    rows = [
        [
            str(t["key"]),
            str(t["trades"]),
            f"{t['profit_mean_pct']:.2f}",
            f"{t['profit_total_abs']:.{decimals_per_coin(stake_currency)}f}",
            f"{t['profit_total_pct']}",
            str(t.get("duration_avg", "N/A")),
            generate_wins_draws_losses(t["wins"], t["draws"], t["losses"]),
            dd,
        ]
        for t, dd in zip(strategy_results, dd_joined, strict=False)
    ]
    return headers, rows


def _format_signal_summary(results: dict[str, Any]) -> str:  # noqa: C901
    """
    Format a summary of entry/exit signals and tags used by the strategy.
    """
    signal_parts = []

    # Entry tags summary
    if results.get("results_per_enter_tag"):
        enter_tags = [
            tag["key"] for tag in results["results_per_enter_tag"] if tag["key"] != "TOTAL"
        ]
        if enter_tags:
            # Remove 'OTHER' and None entries, clean up the list
            clean_enter_tags = [tag for tag in enter_tags if tag and tag != "OTHER"]
            if clean_enter_tags:
                signal_parts.append(f"**Entry Signals**: {', '.join(clean_enter_tags)}")
            elif "OTHER" in enter_tags:
                signal_parts.append("**Entry Signals**: Default (no custom tags)")

    # Exit reasons summary
    if results.get("exit_reason_summary"):
        exit_reasons = [
            reason["key"] if reason.get("key") else reason.get("exit_reason", "unknown")
            for reason in results["exit_reason_summary"]
            if reason.get("key", reason.get("exit_reason")) != "TOTAL"
        ]
        if exit_reasons:
            # Clean up exit reasons
            clean_exit_reasons = [
                reason for reason in exit_reasons if reason and reason != "unknown"
            ]
            if clean_exit_reasons:
                signal_parts.append(f"**Exit Reasons**: {', '.join(clean_exit_reasons)}")

    # Entry/exit distribution
    if results.get("exit_reason_summary"):
        exit_stats = []
        for reason in results["exit_reason_summary"]:
            if reason.get("key", reason.get("exit_reason")) != "TOTAL":
                reason_name = (
                    reason.get("key") if reason.get("key") else reason.get("exit_reason", "unknown")
                )
                trades = reason.get("trades", 0)
                if trades > 0 and reason_name != "unknown":
                    exit_stats.append(f"{reason_name}: {trades}")

        if exit_stats:
            signal_parts.append(f"**Exit Distribution**: {', '.join(exit_stats)}")

    if signal_parts:
        return f"""### Strategy Signals & Tags
{chr(10).join(f"- {part}" for part in signal_parts)}"""

    return ""


def _generate_strategy_overview(strategy: str, results: dict[str, Any], stake_currency: str) -> str:
    """
    Generate a high-level strategy overview section for the markdown report.
    """
    if len(results["trades"]) == 0:
        return f"""## Strategy Overview

**{strategy}** - No trades executed during the backtest period.

- **Starting Balance**: {fmt_coin(results["starting_balance"], stake_currency)}
- **Period**: {results["backtest_start"]} → {results["backtest_end"]}
- **Market Change**: {results["market_change"]:.2%}
"""

    total_trades = results.get("total_trades", 0)
    win_rate = (results.get("wins", 0) / total_trades * 100) if total_trades > 0 else 0
    profit_pct = results.get("profit_total", 0)
    cagr = results.get("cagr", 0)
    sharpe = results.get("sharpe", "N/A")
    max_dd = results.get("max_drawdown_account", results.get("max_drawdown", 0))

    # Performance assessment
    if profit_pct > 0.5:  # > 50% profit
        perf_emoji = "🚀"
        perf_desc = "Excellent"
    elif profit_pct > 0.2:  # > 20% profit
        perf_emoji = "📈"
        perf_desc = "Good"
    elif profit_pct > 0:  # Profitable
        perf_emoji = "✅"
        perf_desc = "Profitable"
    elif profit_pct > -0.1:  # Small loss
        perf_emoji = "⚠️"
        perf_desc = "Break-even"
    else:  # Significant loss
        perf_emoji = "📉"
        perf_desc = "Underperforming"

    return f"""## Strategy Overview

**{strategy}** {perf_emoji} *{perf_desc}*

### Key Performance Metrics
- **Total Return**: {profit_pct:.2%} ({
        fmt_coin(results.get("profit_total_abs", 0), stake_currency)
    })
- **CAGR**: {cagr:.2%}
- **Win Rate**: {win_rate:.1f}% ({results.get("wins", 0)}/{total_trades} trades)
- **Sharpe Ratio**: {sharpe if isinstance(sharpe, str) else f"{sharpe:.2f}"}
- **Max Drawdown**: {max_dd:.2%} ({fmt_coin(results.get("max_drawdown_abs", 0), stake_currency)})

### Trading Activity
- **Total Trades**: {total_trades}
- **Daily Avg**: {results.get("trades_per_day", 0):.1f} trades/day
- **Avg Duration**: {results.get("duration_avg", "N/A")}
- **Best Pair**: {results.get("best_pair", {}).get("key", "N/A")}
  ({results.get("best_pair", {}).get("profit_total", 0):.2%})
- **Worst Pair**: {results.get("worst_pair", {}).get("key", "N/A")}
  ({results.get("worst_pair", {}).get("profit_total", 0):.2%})

{_format_signal_summary(results)}

### Period & Market
- **Backtest Period**: {results.get("backtest_start", "N/A")} →
  {results.get("backtest_end", "N/A")} ({results.get("backtest_days", 0)} days)
- **Market Change**: {results.get("market_change", 0):.2%}
- **Starting Balance**: {fmt_coin(results.get("starting_balance", 0), stake_currency)}
- **Final Balance**: {fmt_coin(results.get("final_balance", 0), stake_currency)}
"""


def _metrics_rows(strat_results: dict) -> list[list[str]]:
    if len(strat_results["trades"]) == 0:
        start_balance = fmt_coin(strat_results["starting_balance"], strat_results["stake_currency"])
        stake_amount = (
            fmt_coin(strat_results["stake_amount"], strat_results["stake_currency"])
            if strat_results["stake_amount"] != UNLIMITED_STAKE_AMOUNT
            else "unlimited"
        )
        message = (
            "No trades made. "
            f"Your starting balance was {start_balance}, "
            f"and your stake was {stake_amount}."
        )
        return [["Info", message]]

    best_trade = (
        max(strat_results["trades"], key=lambda x: x["profit_ratio"])
        if len(strat_results["trades"]) > 0
        else None
    )
    worst_trade = (
        min(strat_results["trades"], key=lambda x: x["profit_ratio"])
        if len(strat_results["trades"]) > 0
        else None
    )

    short_metrics: list[tuple[str, str]] = (
        [
            ("", ""),
            (
                "Long / Short",
                f"{strat_results.get('trade_count_long', 'total_trades')} / "
                f"{strat_results.get('trade_count_short', 0)}",
            ),
            ("Total profit Long %", f"{strat_results['profit_total_long']:.2%}"),
            ("Total profit Short %", f"{strat_results['profit_total_short']:.2%}"),
            (
                "Absolute profit Long",
                fmt_coin(strat_results["profit_total_long_abs"], strat_results["stake_currency"]),
            ),
            (
                "Absolute profit Short",
                fmt_coin(strat_results["profit_total_short_abs"], strat_results["stake_currency"]),
            ),
        ]
        if strat_results.get("trade_count_short", 0) > 0
        else []
    )

    drawdown_metrics: list[tuple[str, str]] = []
    if "max_relative_drawdown" in strat_results:
        drawdown_metrics.append(
            ("Max % of account underwater", f"{strat_results['max_relative_drawdown']:.2%}")
        )
    drawdown_metrics.extend(
        [
            (
                ("Absolute Drawdown (Account)", f"{strat_results['max_drawdown_account']:.2%}")
                if "max_drawdown_account" in strat_results
                else ("Drawdown", f"{strat_results['max_drawdown']:.2%}")
            ),
            (
                "Absolute Drawdown",
                fmt_coin(strat_results["max_drawdown_abs"], strat_results["stake_currency"]),
            ),
            (
                "Drawdown high",
                fmt_coin(strat_results["max_drawdown_high"], strat_results["stake_currency"]),
            ),
            (
                "Drawdown low",
                fmt_coin(strat_results["max_drawdown_low"], strat_results["stake_currency"]),
            ),
            ("Drawdown Start", strat_results["drawdown_start"]),
            ("Drawdown End", strat_results["drawdown_end"]),
        ]
    )

    trading_mode: list[tuple[str, str]] = []
    if "trading_mode" in strat_results:
        trading_mode_val = (
            ""
            if not strat_results.get("margin_mode")
            or strat_results.get("trading_mode", "spot") == "spot"
            else f"{strat_results['margin_mode'].capitalize()} "
        ) + f"{strat_results['trading_mode'].capitalize()}"
        trading_mode = [("Trading Mode", trading_mode_val)]

    metrics: list[tuple[str, str]] = [
        ("Backtesting from", strat_results["backtest_start"]),
        ("Backtesting to", strat_results["backtest_end"]),
        *trading_mode,
        ("Max open trades", strat_results["max_open_trades"]),
        ("", ""),
        (
            "Total/Daily Avg Trades",
            f"{strat_results['total_trades']} / {strat_results['trades_per_day']}",
        ),
        (
            "Starting balance",
            fmt_coin(strat_results["starting_balance"], strat_results["stake_currency"]),
        ),
        (
            "Final balance",
            fmt_coin(strat_results["final_balance"], strat_results["stake_currency"]),
        ),
        (
            "Absolute profit ",
            fmt_coin(strat_results["profit_total_abs"], strat_results["stake_currency"]),
        ),
        ("Total profit %", f"{strat_results['profit_total']:.2%}"),
        ("CAGR %", f"{strat_results['cagr']:.2%}" if "cagr" in strat_results else "N/A"),
        ("Sortino", f"{strat_results['sortino']:.2f}" if "sortino" in strat_results else "N/A"),
        ("Sharpe", f"{strat_results['sharpe']:.2f}" if "sharpe" in strat_results else "N/A"),
        ("Calmar", f"{strat_results['calmar']:.2f}" if "calmar" in strat_results else "N/A"),
        ("SQN", f"{strat_results['sqn']:.2f}" if "sqn" in strat_results else "N/A"),
        (
            "Profit factor",
            (
                f"{strat_results['profit_factor']:.2f}"
                if "profit_factor" in strat_results
                else "N/A"
            ),
        ),
        (
            "Expectancy (Ratio)",
            (
                f"{strat_results['expectancy']:.2f} ({strat_results['expectancy_ratio']:.2f})"
                if "expectancy_ratio" in strat_results
                else "N/A"
            ),
        ),
        (
            "Avg. daily profit",
            fmt_coin(
                (strat_results["profit_total_abs"] / strat_results["backtest_days"]),
                strat_results["stake_currency"],
            ),
        ),
        (
            "Avg. stake amount",
            fmt_coin(strat_results["avg_stake_amount"], strat_results["stake_currency"]),
        ),
        (
            "Total trade volume",
            fmt_coin(strat_results["total_volume"], strat_results["stake_currency"]),
        ),
        *short_metrics,
        ("", ""),
        (
            "Best Pair",
            (
                f"{strat_results['best_pair']['key']} "
                f"{strat_results['best_pair']['profit_total']:.2%}"
            ),
        ),
        (
            "Worst Pair",
            (
                f"{strat_results['worst_pair']['key']} "
                f"{strat_results['worst_pair']['profit_total']:.2%}"
            ),
        ),
        (
            "Best trade",
            f"{best_trade['pair']} {best_trade['profit_ratio']:.2%}" if best_trade else "N/A",
        ),
        (
            "Worst trade",
            f"{worst_trade['pair']} {worst_trade['profit_ratio']:.2%}" if worst_trade else "N/A",
        ),
        (
            "Best day",
            fmt_coin(strat_results["backtest_best_day_abs"], strat_results["stake_currency"]),
        ),
        (
            "Worst day",
            fmt_coin(strat_results["backtest_worst_day_abs"], strat_results["stake_currency"]),
        ),
        (
            "Days win/draw/lose",
            (
                f"{strat_results['winning_days']} / "
                f"{strat_results['draw_days']} / "
                f"{strat_results['losing_days']}"
            ),
        ),
        (
            "Min/Max/Avg. Duration Winners",
            (
                f"{strat_results.get('winner_holding_min', 'N/A')} / "
                f"{strat_results.get('winner_holding_max', 'N/A')} / "
                f"{strat_results.get('winner_holding_avg', 'N/A')}"
            ),
        ),
        (
            "Min/Max/Avg. Duration Losers",
            (
                f"{strat_results.get('loser_holding_min', 'N/A')} / "
                f"{strat_results.get('loser_holding_max', 'N/A')} / "
                f"{strat_results.get('loser_holding_avg', 'N/A')}"
            ),
        ),
        (
            "Max Consecutive Wins / Loss",
            (
                (
                    f"{strat_results['max_consecutive_wins']} / "
                    f"{strat_results['max_consecutive_losses']}"
                )
                if "max_consecutive_losses" in strat_results
                else "N/A"
            ),
        ),
        ("Rejected Entry signals", strat_results.get("rejected_signals", "N/A")),
        (
            "Entry/Exit Timeouts",
            (
                f"{strat_results.get('timedout_entry_orders', 'N/A')} / "
                f"{strat_results.get('timedout_exit_orders', 'N/A')}"
            ),
        ),
        ("", ""),
        ("Min balance", fmt_coin(strat_results["csum_min"], strat_results["stake_currency"])),
        ("Max balance", fmt_coin(strat_results["csum_max"], strat_results["stake_currency"])),
        *drawdown_metrics,
        ("Market change", f"{strat_results['market_change']:.2%}"),
    ]
    return [[k, v] for k, v in metrics]


def _generate_markdown_sections(
    strategy: str, results: dict, config: Config, stake_currency: str
) -> list[str]:
    """Generate all markdown sections for a strategy report."""
    sections: list[str] = []

    # Header
    sections.append(f"# Backtest Report: {strategy}")

    # Strategy summary overview
    sections.append(_generate_strategy_overview(strategy, results, stake_currency))

    # Backtesting report per pair
    headers = _get_line_header("Pair", stake_currency, "Trades")
    rows = _bt_results_rows(results["results_per_pair"], stake_currency)
    sections.append(f"### BACKTESTING REPORT\n{_markdown_table(headers, rows)}")

    # Left open trades report
    headers = _get_line_header("Pair", stake_currency, "Trades")
    rows = _bt_results_rows(results["left_open_trades"], stake_currency)
    sections.append(f"### LEFT OPEN TRADES REPORT\n{_markdown_table(headers, rows)}")

    # Tag subresults
    _add_tag_sections(sections, results, stake_currency)

    # Periodic breakdowns
    _add_periodic_breakdowns(sections, config, results, stake_currency)

    # Summary metrics
    metrics_rows = _metrics_rows(results)
    headers_metrics = ["Metric", "Value"]
    sections.append(f"### SUMMARY METRICS\n{_markdown_table(headers_metrics, metrics_rows)}")

    return sections


def _add_tag_sections(sections: list[str], results: dict, stake_currency: str) -> None:
    """Add tag-related sections to the markdown report."""
    if (enter_tags := results.get("results_per_enter_tag")) is not None:
        headers, rows = _tag_results_rows("enter_tag", enter_tags, stake_currency)
        sections.append(f"### ENTER TAG STATS\n{_markdown_table(headers, rows)}")
    if (exit_reasons := results.get("exit_reason_summary")) is not None:
        headers, rows = _tag_results_rows("exit_tag", exit_reasons, stake_currency)
        sections.append(f"### EXIT REASON STATS\n{_markdown_table(headers, rows)}")
    if (mix_tag := results.get("mix_tag_stats")) is not None:
        headers, rows = _tag_results_rows("mix_tag", mix_tag, stake_currency)
        sections.append(f"### MIXED TAG STATS\n{_markdown_table(headers, rows)}")


def _add_periodic_breakdowns(
    sections: list[str], config: Config, results: dict, stake_currency: str
) -> None:
    """Add periodic breakdown sections to the markdown report."""
    for period in config.get("backtest_breakdown", []):
        if period in results.get("periodic_breakdown", {}):
            days_breakdown_stats = results["periodic_breakdown"][period]
        else:
            days_breakdown_stats = generate_periodic_breakdown_stats(
                trade_list=results["trades"], period=period
            )
        headers, rows = _periodic_breakdown_rows(days_breakdown_stats, stake_currency, period)
        sections.append(f"### {period.upper()} BREAKDOWN\n{_markdown_table(headers, rows)}")


def _generate_enhanced_visualizations(
    config: Config,
    strategy: str,
    results: dict,
    outdir: Path,
    timeframe: str,
    dtappendix: str,
    stake_currency: str,
    backtest_stats: BacktestResultType,
) -> list[Path]:
    """Generate enhanced visual analysis files."""
    visual_paths: list[Path] = []

    if not (PLOTTING_AVAILABLE and config.get("enable_enhanced_plots", True)):
        return visual_paths

    try:
        # Create visual analysis directory
        visual_dir = outdir / "visual_analysis"
        visual_dir.mkdir(exist_ok=True)

        # Generate dashboard for all pairs
        dashboard_html = create_pairs_summary_dashboard(backtest_stats, stake_currency)
        if dashboard_html:
            dashboard_file = visual_dir / f"dashboard-{strategy}-{timeframe}-{dtappendix}.html"
            dashboard_file.write_text(dashboard_html, encoding="utf-8")
            visual_paths.append(dashboard_file)
            logger.info(f"Generated dashboard: {dashboard_file}")

        # Generate individual pair visualizations
        if "trades" in results and len(results["trades"]) > 0:
            visual_paths.extend(
                _generate_pair_visualizations(
                    results, visual_dir, strategy, timeframe, dtappendix, stake_currency, config
                )
            )

    except Exception as e:
        logger.warning(f"Failed to generate enhanced visualizations: {e}")

    return visual_paths


def _generate_pair_visualizations(
    results: dict,
    visual_dir: Path,
    strategy: str,
    timeframe: str,
    dtappendix: str,
    stake_currency: str,
    config: Config,
) -> list[Path]:
    """Generate individual pair visualization files."""
    visual_paths: list[Path] = []

    trades_list = (
        results["trades"]
        if isinstance(results["trades"], list)
        else results["trades"].to_dict("records")
    )

    # Get unique pairs from trades
    unique_pairs = set(trade.get("pair", "") for trade in trades_list)
    unique_pairs.discard("")  # Remove empty strings

    for pair in unique_pairs:
        pair_html = create_enhanced_pair_visualization(
            pair, trades_list, stake_currency, config, results
        )
        if pair_html:
            # Clean pair name for filename
            safe_pair = pair.replace("/", "_").replace(":", "_")
            pair_file = visual_dir / f"pair-{safe_pair}-{strategy}-{timeframe}-{dtappendix}.html"
            pair_file.write_text(pair_html, encoding="utf-8")
            visual_paths.append(pair_file)
            logger.info(f"Generated pair analysis: {pair_file}")

    return visual_paths


def write_backtest_console_markdown(
    config: Config, backtest_stats: BacktestResultType, *, results_folder: Path | None = None
) -> list[Path]:
    """
    Write the same information shown in the terminal during backtesting into Markdown files
    under the backtest results directory. One file per strategy will be created.
    Additionally generates enhanced visual analysis files.
    Returns list of generated file paths.
    """
    stake_currency = config["stake_currency"]
    timeframe = str(config.get("timeframe", ""))
    dtappendix = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    outdir = results_folder if results_folder is not None else _export_base_dir(config)
    out_paths: list[Path] = []

    for strategy, results in backtest_stats["strategy"].items():
        outfile = outdir / f"console-{strategy}-{timeframe}-{dtappendix}.md"

        # Generate all markdown sections
        sections = _generate_markdown_sections(strategy, results, config, stake_currency)

        # Combined content
        content = "\n\n".join(sections) + "\n\n"

        # Strategy summary table (global) printed once per file for convenience
        if len(backtest_stats["strategy"]) > 0:
            content += (
                f"Backtested {results['backtest_start']} -> {results['backtest_end']} | "
                f"Max open trades : {results['max_open_trades']}\n\n"
            )
            sh, sr = _strategy_summary_rows(backtest_stats["strategy_comparison"], stake_currency)
            content += f"### STRATEGY SUMMARY\n{_markdown_table(sh, sr)}\n"

        outfile.parent.mkdir(parents=True, exist_ok=True)
        outfile.write_text(content, encoding="utf-8")
        out_paths.append(outfile)

        # Generate enhanced visual analysis
        visual_paths = _generate_enhanced_visualizations(
            config, strategy, results, outdir, timeframe, dtappendix, stake_currency, backtest_stats
        )
        out_paths.extend(visual_paths)

    return out_paths


def generate_enhanced_backtest_report(
    config: Config, backtest_stats: BacktestResultType
) -> list[Path]:
    """
    Generate enhanced visual backtest reports with interactive charts
    :param config: Configuration dictionary
    :param backtest_stats: Backtest results
    :return: List of generated file paths
    """
    if not PLOTTING_AVAILABLE:
        logger.error(
            "Enhanced reports require plotly and pandas. Install with: pip install plotly pandas"
        )
        return []

    stake_currency = config["stake_currency"]
    timeframe = str(config.get("timeframe", ""))
    dtappendix = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    outdir = _export_base_dir(config)
    visual_dir = outdir / "enhanced_analysis"
    visual_dir.mkdir(exist_ok=True)

    generated_files: list[Path] = []

    try:
        # Generate comprehensive dashboard
        dashboard_html = create_pairs_summary_dashboard(backtest_stats, stake_currency)
        if dashboard_html:
            dashboard_file = visual_dir / f"comprehensive-dashboard-{timeframe}-{dtappendix}.html"
            dashboard_file.write_text(dashboard_html, encoding="utf-8")
            generated_files.append(dashboard_file)
            logger.info(f"✓ Generated comprehensive dashboard: {dashboard_file}")

        # Generate individual strategy reports
        for strategy, results in backtest_stats["strategy"].items():
            if "trades" in results and len(results["trades"]) > 0:
                trades_list = (
                    results["trades"]
                    if isinstance(results["trades"], list)
                    else results["trades"].to_dict("records")
                )

                # Get unique pairs from trades
                unique_pairs = set(trade.get("pair", "") for trade in trades_list)
                unique_pairs.discard("")  # Remove empty strings

                # Generate detailed pair analysis
                for pair in unique_pairs:
                    pair_html = create_enhanced_pair_visualization(
                        pair, trades_list, stake_currency, config, results
                    )
                    if pair_html:
                        safe_pair = pair.replace("/", "_").replace(":", "_")
                        pair_file = (
                            visual_dir
                            / f"{safe_pair}-{strategy}-analysis-{timeframe}-{dtappendix}.html"
                        )
                        pair_file.write_text(pair_html, encoding="utf-8")
                        generated_files.append(pair_file)
                        logger.info(f"✓ Generated {pair} analysis: {pair_file}")

        # Generate summary index file
        index_html = _create_analysis_index(generated_files, backtest_stats, stake_currency)
        index_file = visual_dir / f"index-{dtappendix}.html"
        index_file.write_text(index_html, encoding="utf-8")
        generated_files.append(index_file)
        logger.info(f"✓ Generated analysis index: {index_file}")

        logger.info(
            f"🎉 Enhanced backtest analysis complete! Generated {len(generated_files)} files."
        )
        logger.info(f"📊 Open the index file to access all reports: {index_file}")

    except Exception as e:
        logger.error(f"Failed to generate enhanced reports: {e}")

    return generated_files


def _create_analysis_index(
    generated_files: list[Path], backtest_stats: BacktestResultType, stake_currency: str
) -> str:
    """
    Create an HTML index file linking to all generated analysis files
    """
    html_content = f"""{""}
    <!DOCTYPE html>
    <html>
    <head>
        <title>Freqtrade Enhanced Backtest Analysis</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px;
                         border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
            h2 {{ color: #34495e; margin-top: 30px; }}
            .summary {{ background: #ecf0f1; padding: 20px; border-radius: 5px; margin: 20px 0; }}
            .file-list {{ list-style: none; padding: 0; }}
            .file-list li {{ margin: 10px 0; padding: 15px; background: #f8f9fa;
                            border-left: 4px solid #3498db; border-radius: 5px; }}
            .file-list a {{ text-decoration: none; color: #2c3e50; font-weight: bold; }}
            .file-list a:hover {{ color: #3498db; }}
            .description {{ color: #7f8c8d; font-size: 0.9em; margin-top: 5px; }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                     gap: 20px; margin: 20px 0; }}
            .stat-card {{ background: #3498db; color: white; padding: 20px; border-radius: 5px;
                          text-align: center; }}
            .stat-value {{ font-size: 2em; font-weight: bold; }}
            .stat-label {{ font-size: 0.9em; opacity: 0.9; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 Freqtrade Enhanced Backtest Analysis</h1>

            <div class="summary">
                <h2>📊 Analysis Summary</h2>
                <p>This report contains enhanced visual analysis of your backtest results with
                interactive charts showing entry/exit points, profit analysis, and performance
                metrics.</p>

                <div class="stats">
    """

    # Add summary statistics
    # Totals could be used for additional summary cards later

    for strategy, results in backtest_stats.get("strategy", {}).items():
        total_trades = results.get("total_trades", 0)
        profit_pct = results.get("profit_total", 0) * 100
        win_rate = (results.get("wins", 0) / total_trades * 100) if total_trades > 0 else 0

        html_content += f"""
                    <div class="stat-card">
                        <div class="stat-value">{total_trades}</div>
                        <div class="stat-label">Total Trades ({strategy})</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{profit_pct:.1f}%</div>
                        <div class="stat-label">Total Profit ({strategy})</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{win_rate:.1f}%</div>
                        <div class="stat-label">Win Rate ({strategy})</div>
                    </div>
        """

    html_content += f"""{""}
                </div>
            </div>

            <h2>📈 Available Reports</h2>
            <ul class="file-list">
    """

    # Categorize files
    dashboard_files = [f for f in generated_files if "dashboard" in f.name]
    pair_files = [f for f in generated_files if "analysis" in f.name and "dashboard" not in f.name]

    # Add dashboard links
    for file_path in dashboard_files:
        html_content += f"""
                <li>
                    <a href="{file_path.name}" target="_blank">📊 Performance Dashboard</a>
                    <div class="description">Comprehensive overview of all trading pairs with
                    profit analysis, win rates, and risk/reward metrics</div>
                </li>
        """

    # Add pair analysis links
    for file_path in pair_files:
        pair_name = file_path.name.split("-")[0].replace("_", "/")
        html_content += f"""
                <li>
                    <a href="{file_path.name}" target="_blank">🎯 {pair_name} Analysis</a>
                    <div class="description">Detailed entry/exit point analysis with profit
                    tracking and trade duration metrics</div>
                </li>
        """

    html_content += """
            </ul>

            <div class="summary">
                <h2>💡 How to Use These Reports</h2>
                <ul>
                    <li><strong>Dashboard:</strong> Start here for an overview of all pairs'
                        performance</li>
                    <li><strong>Pair Analysis:</strong> Click on individual pair reports to see
                        detailed entry/exit points</li>
                    <li><strong>Interactive Charts:</strong> Hover over points for detailed
                        information, zoom and pan to explore</li>
                    <li><strong>Trade Points:</strong> Green triangles = entries, Green/Red
                        triangles down = profitable/loss exits</li>
                </ul>
            </div>
        </div>
    </body>
    </html>
    """

    return html_content


def main():
    """
    Simple command line interface for testing the enhanced visualization
    """
    import json
    import sys

    from freqtrade.constants import Config

    if len(sys.argv) < 2:
        print("Usage: python bt_output.py <backtest_results.json> [config.json]")
        print("Example: python bt_output.py user_data/backtest_results/backtest-result.json")
        return

    # Load backtest results
    results_file = Path(sys.argv[1])
    if not results_file.exists():
        print(f"Error: Backtest results file not found: {results_file}")
        return

    try:
        with results_file.open() as f:
            backtest_stats = json.load(f)
    except Exception as e:
        print(f"Error loading backtest results: {e}")
        return

    # Basic config
    config: Config = {
        "stake_currency": "USDT",
        "timeframe": "1m",
        "exportfilename": results_file.parent,
        "enable_enhanced_plots": True,
    }

    # Load additional config if provided
    if len(sys.argv) > 2:
        config_file = Path(sys.argv[2])
        if config_file.exists():
            try:
                with config_file.open() as f:
                    user_config = json.load(f)
                    config.update(user_config)
            except Exception as e:
                print(f"Warning: Could not load config file: {e}")

    # Generate enhanced reports
    print("🚀 Generating enhanced backtest visualization...")
    generated_files = generate_enhanced_backtest_report(config, backtest_stats)

    if generated_files:
        print(f"\n✅ Successfully generated {len(generated_files)} files:")
        for file_path in generated_files:
            print(f"   📄 {file_path}")

        # Find and highlight the index file
        index_files = [f for f in generated_files if "index" in f.name]
        if index_files:
            print(f"\n🌟 Start here: {index_files[0]}")
            print("   Open this file in your browser to access all reports!")
    else:
        print("❌ No files were generated. Check the logs for errors.")


if __name__ == "__main__":
    main()
