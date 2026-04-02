from colorama import Fore, Style
from tabulate import tabulate
from .analysts import ANALYST_ORDER
from .agent_display import get_agent_display_name
import os
import json
import unicodedata


TECHNICAL_SECTION_LABELS = {
    "trend_following": "順勢策略",
    "mean_reversion": "均值回歸",
    "momentum": "動能策略",
    "volatility": "波動分析",
    "statistical_arbitrage": "統計套利",
}

TECHNICAL_METRIC_LABELS = {
    "adx": "ADX(趨勢強度)",
    "trend_strength": "trend_strength(趨勢強弱分數)",
    "z_score": "z_score(離均值距離)",
    "price_vs_bb": "price_vs_bb(布林帶位置)",
    "rsi_14": "RSI14(短線強弱)",
    "rsi_28": "RSI28(中線強弱)",
    "momentum_1m": "momentum_1m(1個月動能)",
    "momentum_3m": "momentum_3m(3個月動能)",
    "momentum_6m": "momentum_6m(6個月動能)",
    "volume_momentum": "volume_momentum(量能是否放大)",
    "historical_volatility": "historical_volatility(歷史波動)",
    "volatility_regime": "volatility_regime(波動環境)",
    "volatility_z_score": "volatility_z_score(波動偏離程度)",
    "atr_ratio": "atr_ratio(日波幅比例)",
    "hurst_exponent": "hurst_exponent(趨勢或均值回歸傾向)",
    "skewness": "skewness(報酬偏態)",
    "kurtosis": "kurtosis(尾部風險)",
}

TECHNICAL_SECTION_EXPLANATIONS = {
    "trend_following": "看價格是否已形成明確上升或下降趨勢。",
    "mean_reversion": "看股價是否偏離均值太遠，可能出現反彈或拉回。",
    "momentum": "看最近一段時間的漲跌動能是否延續。",
    "volatility": "看目前波動是否異常放大，風險是否升高。",
    "statistical_arbitrage": "看價格型態更像延續趨勢，還是回到平均。",
}

TECHNICAL_METRIC_EXPLANATIONS = {
    "adx": "數值越高代表趨勢越明確，通常 25 以上可視為有趨勢。",
    "trend_strength": "把趨勢強度標準化到 0 到 1，越高代表越偏向順勢判讀。",
    "z_score": "負值代表比均值低，正值代表比均值高，絕對值越大表示偏離越多。",
    "price_vs_bb": "越接近 0 表示靠近布林帶下緣，越接近 1 表示靠近上緣。",
    "rsi_14": "短線 RSI，低於 30 常見超賣，高於 70 常見超買。",
    "rsi_28": "中線 RSI，用來輔助判斷不是只有一天兩天的過熱或過冷。",
    "momentum_1m": "近 1 個月報酬動能，正值偏多，負值偏空。",
    "momentum_3m": "近 3 個月報酬動能，反映中期強弱。",
    "momentum_6m": "近 6 個月報酬動能，反映較長週期方向。",
    "volume_momentum": "大於 1 代表成交量高於近期均量，訊號可信度通常較高。",
    "historical_volatility": "近期價格波動幅度，越高代表震盪越大。",
    "volatility_regime": "用來判斷市場現在處於高波動還是低波動環境。",
    "volatility_z_score": "看目前波動相對歷史是否異常。",
    "atr_ratio": "每日真實波幅占價格比例，越高代表短線震盪越大。",
    "hurst_exponent": "偏高常代表趨勢延續，偏低常代表較像均值回歸。",
    "skewness": "看報酬分布偏向大漲還是大跌。",
    "kurtosis": "看極端波動是否比常態分布更常出現。",
}


def sort_agent_signals(signals):
    """Sort agent signals in a consistent order."""
    analyst_order = {display: idx for idx, (display, _) in enumerate(ANALYST_ORDER)}
    analyst_order["Risk Management"] = len(ANALYST_ORDER)
    return sorted(signals, key=lambda x: analyst_order.get(x[0], 999))


def _format_scalar(value):
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _format_metric(key: str, value) -> str:
    metric_label = TECHNICAL_METRIC_LABELS.get(key, key)
    return f"{metric_label}: {_format_scalar(value)}"


def _format_metrics(metrics: dict) -> str:
    items = [_format_metric(key, value) for key, value in metrics.items()]
    return "，".join(items)


def _summarize_technical_section(section: str, payload: dict) -> str:
    label = TECHNICAL_SECTION_LABELS.get(section, section)
    explanation = TECHNICAL_SECTION_EXPLANATIONS.get(section, "")
    signal = payload.get("signal")
    confidence = payload.get("confidence")
    metrics = payload.get("metrics", {})

    parts = [f"{label}: 訊號={signal}；信心={_format_scalar(confidence)}"]
    if explanation:
        parts.append(explanation)
    if isinstance(metrics, dict) and metrics:
        parts.append(_format_metrics(metrics))

        metric_explanations = []
        for metric_key in metrics.keys():
            meaning = TECHNICAL_METRIC_EXPLANATIONS.get(metric_key)
            if meaning:
                metric_explanations.append(
                    f"{TECHNICAL_METRIC_LABELS.get(metric_key, metric_key)}: {meaning}"
                )
        if metric_explanations:
            parts.append("指標解讀: " + " ".join(metric_explanations))

    return "\n".join(parts)


def _summarize_reasoning(reasoning) -> str:
    """Render agent reasoning into a compact, readable CLI string."""
    if not reasoning:
        return ""

    if isinstance(reasoning, str):
        return reasoning

    if isinstance(reasoning, dict):
        parts = []
        for section, payload in reasoning.items():
            if isinstance(payload, dict) and "signal" in payload:
                if section in TECHNICAL_SECTION_LABELS:
                    parts.append(_summarize_technical_section(section, payload))
                    continue

                signal = payload.get("signal")
                confidence = payload.get("confidence")
                metrics = payload.get("metrics")
                details = []
                if signal:
                    details.append(f"訊號={signal}")
                if confidence is not None:
                    details.append(f"信心={_format_scalar(confidence)}")
                if isinstance(metrics, dict) and metrics:
                    details.append(_format_metrics(metrics))

                if details:
                    parts.append(f"{section}: " + "；".join(details))
                    continue

            parts.append(f"{section}: {_format_scalar(payload)}")

        if parts:
            return "\n\n".join(parts)

        return json.dumps(reasoning, ensure_ascii=False, indent=2)

    return str(reasoning)


def _wrap_text(text: str, max_line_length: int = 60) -> str:
    if not text:
        return ""

    def char_width(char: str) -> int:
        if unicodedata.east_asian_width(char) in ("W", "F"):
            return 2
        return 1

    def wrap_line(line: str) -> list[str]:
        wrapped_lines = []
        current = ""
        current_width = 0

        for char in line:
            width = char_width(char)
            if current and current_width + width > max_line_length:
                wrapped_lines.append(current.rstrip())
                current = char
                current_width = width
            else:
                current += char
                current_width += width

        if current or not wrapped_lines:
            wrapped_lines.append(current.rstrip())

        return wrapped_lines

    wrapped = []
    for line in str(text).splitlines():
        wrapped.extend(wrap_line(line))

    return "\n".join(wrapped)


def print_trading_output(result: dict) -> None:
    """Print formatted trading results with colored tables for multiple tickers."""
    decisions = result.get("decisions")
    if not decisions:
        print(f"{Fore.RED}No trading decisions available{Style.RESET_ALL}")
        return

    for ticker, decision in decisions.items():
        print(f"\n{Fore.WHITE}{Style.BRIGHT}Analysis for {Fore.CYAN}{ticker}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}{Style.BRIGHT}{'=' * 50}{Style.RESET_ALL}")

        table_data = []
        for agent, signals in result.get("analyst_signals", {}).items():
            if ticker not in signals or agent == "risk_management_agent":
                continue

            signal = signals[ticker]
            agent_name = get_agent_display_name(agent)
            signal_type = signal.get("signal", "").upper()
            confidence = signal.get("confidence", 0)

            signal_color = {
                "BULLISH": Fore.GREEN,
                "BEARISH": Fore.RED,
                "NEUTRAL": Fore.YELLOW,
            }.get(signal_type, Fore.WHITE)

            reasoning_str = ""
            if signal.get("reasoning"):
                reasoning_str = _wrap_text(_summarize_reasoning(signal["reasoning"]))

            table_data.append(
                [
                    f"{Fore.CYAN}{agent_name}{Style.RESET_ALL}",
                    f"{signal_color}{signal_type}{Style.RESET_ALL}",
                    f"{Fore.WHITE}{confidence}%{Style.RESET_ALL}",
                    f"{Fore.WHITE}{reasoning_str}{Style.RESET_ALL}",
                ]
            )

        table_data = sort_agent_signals(table_data)

        print(f"\n{Fore.WHITE}{Style.BRIGHT}Agent 分析:{Style.RESET_ALL} [{Fore.CYAN}{ticker}{Style.RESET_ALL}]")
        print(
            tabulate(
                table_data,
                headers=[f"{Fore.WHITE}Agent", "訊號", "信心", "分析說明"],
                tablefmt="grid",
                colalign=("left", "center", "right", "left"),
            )
        )

        action = decision.get("action", "").upper()
        action_color = {
            "BUY": Fore.GREEN,
            "SELL": Fore.RED,
            "HOLD": Fore.YELLOW,
            "COVER": Fore.GREEN,
            "SHORT": Fore.RED,
        }.get(action, Fore.WHITE)

        wrapped_reasoning = _wrap_text(decision.get("reasoning", ""))

        decision_data = [
            ["動作", f"{action_color}{action}{Style.RESET_ALL}"],
            ["數量", f"{action_color}{decision.get('quantity')}{Style.RESET_ALL}"],
            ["信心", f"{Fore.WHITE}{decision.get('confidence'):.1f}%{Style.RESET_ALL}"],
            ["分析說明", f"{Fore.WHITE}{wrapped_reasoning}{Style.RESET_ALL}"],
        ]

        print(f"\n{Fore.WHITE}{Style.BRIGHT}交易決策:{Style.RESET_ALL} [{Fore.CYAN}{ticker}{Style.RESET_ALL}]")
        print(tabulate(decision_data, tablefmt="grid", colalign=("left", "left")))

    print(f"\n{Fore.WHITE}{Style.BRIGHT}投資組合摘要:{Style.RESET_ALL}")

    report_meta = result.get("report", {})
    report_date = report_meta.get("generated_at")
    data_start_date = report_meta.get("start_date")
    data_end_date = report_meta.get("end_date")
    if report_date or data_start_date or data_end_date:
        meta_lines = []
        if report_date:
            meta_lines.append(f"報告日期: {report_date}")
        if data_start_date:
            meta_lines.append(f"資料起始日: {data_start_date}")
        if data_end_date:
            meta_lines.append(f"資料截止日: {data_end_date}")
        print(f"{Fore.CYAN}" + " | ".join(meta_lines) + f"{Style.RESET_ALL}")

    portfolio_data = []
    portfolio_manager_reasoning = None
    for ticker, decision in decisions.items():
        if decision.get("reasoning"):
            portfolio_manager_reasoning = decision.get("reasoning")
            break

    analyst_signals = result.get("analyst_signals", {})
    for ticker, decision in decisions.items():
        action = decision.get("action", "").upper()
        action_color = {
            "BUY": Fore.GREEN,
            "SELL": Fore.RED,
            "HOLD": Fore.YELLOW,
            "COVER": Fore.GREEN,
            "SHORT": Fore.RED,
        }.get(action, Fore.WHITE)

        bullish_count = 0
        bearish_count = 0
        neutral_count = 0
        if analyst_signals:
            for _, signals in analyst_signals.items():
                if ticker in signals:
                    signal = signals[ticker].get("signal", "").upper()
                    if signal == "BULLISH":
                        bullish_count += 1
                    elif signal == "BEARISH":
                        bearish_count += 1
                    elif signal == "NEUTRAL":
                        neutral_count += 1

        portfolio_data.append(
            [
                f"{Fore.CYAN}{ticker}{Style.RESET_ALL}",
                f"{action_color}{action}{Style.RESET_ALL}",
                f"{action_color}{decision.get('quantity')}{Style.RESET_ALL}",
                f"{Fore.WHITE}{decision.get('confidence'):.1f}%{Style.RESET_ALL}",
                f"{Fore.GREEN}{bullish_count}{Style.RESET_ALL}",
                f"{Fore.RED}{bearish_count}{Style.RESET_ALL}",
                f"{Fore.YELLOW}{neutral_count}{Style.RESET_ALL}",
            ]
        )

    headers = [
        f"{Fore.WHITE}Ticker",
        f"{Fore.WHITE}動作",
        f"{Fore.WHITE}數量",
        f"{Fore.WHITE}信心",
        f"{Fore.WHITE}Bullish",
        f"{Fore.WHITE}Bearish",
        f"{Fore.WHITE}Neutral",
    ]

    print(
        tabulate(
            portfolio_data,
            headers=headers,
            tablefmt="grid",
            colalign=("left", "center", "right", "right", "center", "center", "center"),
        )
    )

    if portfolio_manager_reasoning:
        reasoning_str = _summarize_reasoning(portfolio_manager_reasoning)
        wrapped_reasoning = _wrap_text(reasoning_str)
        print(f"\n{Fore.WHITE}{Style.BRIGHT}投資組合策略:{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{wrapped_reasoning}{Style.RESET_ALL}")


def print_backtest_results(table_rows: list) -> None:
    """Print the backtest results in a nicely formatted table."""
    os.system("cls" if os.name == "nt" else "clear")

    ticker_rows = []
    summary_rows = []

    for row in table_rows:
        if isinstance(row[1], str) and "PORTFOLIO SUMMARY" in row[1]:
            summary_rows.append(row)
        else:
            ticker_rows.append(row)

    if summary_rows:
        latest_summary = max(summary_rows, key=lambda r: r[0])
        print(f"\n{Fore.WHITE}{Style.BRIGHT}PORTFOLIO SUMMARY:{Style.RESET_ALL}")

        position_str = latest_summary[7].split("$")[1].split(Style.RESET_ALL)[0].replace(",", "")
        cash_str = latest_summary[8].split("$")[1].split(Style.RESET_ALL)[0].replace(",", "")
        total_str = latest_summary[9].split("$")[1].split(Style.RESET_ALL)[0].replace(",", "")

        print(f"Cash Balance: {Fore.CYAN}${float(cash_str):,.2f}{Style.RESET_ALL}")
        print(f"Total Position Value: {Fore.YELLOW}${float(position_str):,.2f}{Style.RESET_ALL}")
        print(f"Total Value: {Fore.WHITE}${float(total_str):,.2f}{Style.RESET_ALL}")
        print(f"Portfolio Return: {latest_summary[10]}")
        if len(latest_summary) > 14 and latest_summary[14]:
            print(f"Benchmark Return: {latest_summary[14]}")

        if latest_summary[11]:
            print(f"Sharpe Ratio: {latest_summary[11]}")
        if latest_summary[12]:
            print(f"Sortino Ratio: {latest_summary[12]}")
        if latest_summary[13]:
            print(f"Max Drawdown: {latest_summary[13]}")

    print("\n" * 2)

    print(
        tabulate(
            ticker_rows,
            headers=[
                "Date",
                "Ticker",
                "Action",
                "Quantity",
                "Price",
                "Long Shares",
                "Short Shares",
                "Position Value",
            ],
            tablefmt="grid",
            colalign=("left", "left", "center", "right", "right", "right", "right", "right"),
        )
    )

    print("\n" * 4)


def format_backtest_row(
    date: str,
    ticker: str,
    action: str,
    quantity: float,
    price: float,
    long_shares: float = 0,
    short_shares: float = 0,
    position_value: float = 0,
    is_summary: bool = False,
    total_value: float = None,
    return_pct: float = None,
    cash_balance: float = None,
    total_position_value: float = None,
    sharpe_ratio: float = None,
    sortino_ratio: float = None,
    max_drawdown: float = None,
    benchmark_return_pct: float | None = None,
) -> list[any]:
    """Format a row for the backtest results table."""
    action_color = {
        "BUY": Fore.GREEN,
        "COVER": Fore.GREEN,
        "SELL": Fore.RED,
        "SHORT": Fore.RED,
        "HOLD": Fore.WHITE,
    }.get(action.upper(), Fore.WHITE)

    if is_summary:
        return_color = Fore.GREEN if return_pct >= 0 else Fore.RED
        benchmark_str = ""
        if benchmark_return_pct is not None:
            bench_color = Fore.GREEN if benchmark_return_pct >= 0 else Fore.RED
            benchmark_str = f"{bench_color}{benchmark_return_pct:+.2f}%{Style.RESET_ALL}"
        return [
            date,
            f"{Fore.WHITE}{Style.BRIGHT}PORTFOLIO SUMMARY{Style.RESET_ALL}",
            "",
            "",
            "",
            "",
            "",
            f"{Fore.YELLOW}${total_position_value:,.2f}{Style.RESET_ALL}",
            f"{Fore.CYAN}${cash_balance:,.2f}{Style.RESET_ALL}",
            f"{Fore.WHITE}${total_value:,.2f}{Style.RESET_ALL}",
            f"{return_color}{return_pct:+.2f}%{Style.RESET_ALL}",
            f"{Fore.YELLOW}{sharpe_ratio:.2f}{Style.RESET_ALL}" if sharpe_ratio is not None else "",
            f"{Fore.YELLOW}{sortino_ratio:.2f}{Style.RESET_ALL}" if sortino_ratio is not None else "",
            f"{Fore.RED}{max_drawdown:.2f}%{Style.RESET_ALL}" if max_drawdown is not None else "",
            benchmark_str,
        ]

    return [
        date,
        f"{Fore.CYAN}{ticker}{Style.RESET_ALL}",
        f"{action_color}{action.upper()}{Style.RESET_ALL}",
        f"{action_color}{quantity:,.0f}{Style.RESET_ALL}",
        f"{Fore.WHITE}{price:,.2f}{Style.RESET_ALL}",
        f"{Fore.GREEN}{long_shares:,.0f}{Style.RESET_ALL}",
        f"{Fore.RED}{short_shares:,.0f}{Style.RESET_ALL}",
        f"{Fore.YELLOW}{position_value:,.2f}{Style.RESET_ALL}",
    ]
