import datetime
import logging
import os
import time
from typing import Protocol
from urllib.parse import urlencode

import pandas as pd
import requests

from src.data.cache import get_cache
from src.data.models import (
    CompanyFactsResponse,
    CompanyNews,
    CompanyNewsResponse,
    FinancialMetrics,
    FinancialMetricsResponse,
    InsiderTrade,
    InsiderTradeResponse,
    LineItem,
    LineItemResponse,
    Price,
    PriceResponse,
)

logger = logging.getLogger(__name__)

# Global cache instance
_cache = get_cache()
_preloaded_data: dict[str, dict] = {}


def _make_api_request(
    url: str,
    headers: dict,
    method: str = "GET",
    json_data: dict = None,
    max_retries: int = 3,
) -> requests.Response:
    """
    Make an API request with rate limiting handling and moderate backoff.
    """
    for attempt in range(max_retries + 1):
        if method.upper() == "POST":
            response = requests.post(url, headers=headers, json=json_data)
        else:
            response = requests.get(url, headers=headers)

        if response.status_code == 429 and attempt < max_retries:
            delay = 60 + (30 * attempt)
            print(
                f"Rate limited (429). Attempt {attempt + 1}/{max_retries + 1}. "
                f"Waiting {delay}s before retrying..."
            )
            time.sleep(delay)
            continue

        return response


def clear_preloaded_market_data() -> None:
    _preloaded_data.clear()


def _date_only(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).split("T")[0].split(" ")[0]


def _slice_preloaded_by_end_date(items: list, end_date: str, limit: int | None = None):
    filtered = [item for item in items if not getattr(item, "report_period", None) or _date_only(getattr(item, "report_period", None)) <= end_date]
    return filtered[:limit] if limit is not None else filtered


def _slice_preloaded_by_date_range(items: list, end_date: str, start_date: str | None = None, limit: int | None = None, attr_name: str = "date"):
    filtered = []
    for item in items:
        item_date = _date_only(getattr(item, attr_name, None))
        if not item_date:
            continue
        if start_date and item_date < start_date:
            continue
        if end_date and item_date > end_date:
            continue
        filtered.append(item)
    return filtered[:limit] if limit is not None else filtered


def _preloaded_line_items_match(preloaded_items: list[LineItem], requested_line_items: list[str]) -> bool:
    if not preloaded_items:
        return False
    for item in requested_line_items:
        if not hasattr(preloaded_items[0], item):
            return False
    return True


def _project_line_items(preloaded_items: list[LineItem], requested_line_items: list[str], limit: int) -> list[LineItem]:
    projected = []
    for item in preloaded_items[:limit]:
        payload = {
            "ticker": item.ticker,
            "report_period": item.report_period,
            "period": item.period,
            "currency": item.currency,
        }
        for line_item in requested_line_items:
            payload[line_item] = getattr(item, line_item, None)
        projected.append(LineItem(**payload))
    return projected


def get_preloaded_market_data() -> dict[str, dict]:
    return _preloaded_data


def prepare_preloaded_market_data(
    tickers: list[str],
    start_date: str,
    end_date: str,
    api_key: str | None = None,
) -> None:
    """Warm a per-run in-memory cache so all agents can reuse the same fetched data."""
    clear_preloaded_market_data()
    provider = get_financial_data_provider()
    supports_line_items = getattr(provider, "supports_line_items", True)
    supports_insider_trades = getattr(provider, "supports_insider_trades", True)
    supports_company_news = getattr(provider, "supports_company_news", True)
    supports_multiple_metric_periods = getattr(provider, "supports_multiple_metric_periods", True)

    preload_start_date = min(
        start_date,
        (datetime.datetime.fromisoformat(end_date) - datetime.timedelta(days=365)).date().isoformat(),
    )
    common_line_items = sorted(
        {
            "book_value_per_share",
            "capital_expenditure",
            "cash_and_equivalents",
            "current_assets",
            "current_liabilities",
            "debt_to_equity",
            "depreciation_and_amortization",
            "dividends_and_other_cash_distributions",
            "earnings_per_share",
            "ebit",
            "ebitda",
            "free_cash_flow",
            "gross_margin",
            "interest_expense",
            "issuance_or_purchase_of_equity_shares",
            "net_income",
            "operating_income",
            "operating_margin",
            "outstanding_shares",
            "research_and_development",
            "revenue",
            "shareholders_equity",
            "total_assets",
            "total_debt",
            "total_liabilities",
            "working_capital",
        }
    )

    for ticker in tickers:
        ticker_bucket = {
            "prices": provider.get_prices(ticker, start_date, end_date, api_key=api_key),
            "financial_metrics": {},
            "line_items": {},
            "insider_trades": [],
            "company_news": [],
        }
        ticker_bucket["financial_metrics"]["ttm"] = provider.get_financial_metrics(
            ticker,
            end_date,
            period="ttm",
            limit=10,
            api_key=api_key,
        )
        if supports_multiple_metric_periods:
            ticker_bucket["financial_metrics"]["annual"] = provider.get_financial_metrics(
                ticker,
                end_date,
                period="annual",
                limit=10,
                api_key=api_key,
            )

        if supports_line_items:
            ticker_bucket["line_items"]["ttm"] = provider.search_line_items(
                ticker,
                common_line_items,
                end_date,
                period="ttm",
                limit=10,
                api_key=api_key,
            )
            ticker_bucket["line_items"]["annual"] = provider.search_line_items(
                ticker,
                common_line_items,
                end_date,
                period="annual",
                limit=10,
                api_key=api_key,
            )

        if supports_insider_trades:
            ticker_bucket["insider_trades"] = provider.get_insider_trades(
                ticker,
                end_date=end_date,
                start_date=preload_start_date,
                limit=1000,
                api_key=api_key,
            )

        if supports_company_news:
            ticker_bucket["company_news"] = provider.get_company_news(
                ticker,
                end_date=end_date,
                start_date=preload_start_date,
                limit=250,
                api_key=api_key,
            )
        ticker_bucket["market_cap"] = provider.get_market_cap(ticker, end_date, api_key=api_key)
        _preloaded_data[ticker] = ticker_bucket


class FinancialDataProvider(Protocol):
    name: str

    def get_prices(self, ticker: str, start_date: str, end_date: str, api_key: str = None) -> list[Price]:
        ...

    def get_financial_metrics(
        self,
        ticker: str,
        end_date: str,
        period: str = "ttm",
        limit: int = 10,
        api_key: str = None,
    ) -> list[FinancialMetrics]:
        ...

    def search_line_items(
        self,
        ticker: str,
        line_items: list[str],
        end_date: str,
        period: str = "ttm",
        limit: int = 10,
        api_key: str = None,
    ) -> list[LineItem]:
        ...

    def get_insider_trades(
        self,
        ticker: str,
        end_date: str,
        start_date: str | None = None,
        limit: int = 1000,
        api_key: str = None,
    ) -> list[InsiderTrade]:
        ...

    def get_company_news(
        self,
        ticker: str,
        end_date: str,
        start_date: str | None = None,
        limit: int = 1000,
        api_key: str = None,
    ) -> list[CompanyNews]:
        ...

    def get_market_cap(
        self,
        ticker: str,
        end_date: str,
        api_key: str = None,
    ) -> float | None:
        ...


class FinancialDatasetsProvider:
    """Current production provider backed by financialdatasets.ai."""

    name = "financialdatasets"
    api_key_env_var = "FINANCIAL_DATASETS_API_KEY"

    def _headers(self, api_key: str | None = None) -> dict:
        resolved_api_key = api_key or os.environ.get(self.api_key_env_var)
        return {"X-API-KEY": resolved_api_key} if resolved_api_key else {}

    def get_prices(self, ticker: str, start_date: str, end_date: str, api_key: str = None) -> list[Price]:
        cache_key = f"{ticker}_{start_date}_{end_date}"
        if cached_data := _cache.get_prices(cache_key):
            return [Price(**price) for price in cached_data]

        url = (
            "https://api.financialdatasets.ai/prices/"
            f"?ticker={ticker}&interval=day&interval_multiplier=1"
            f"&start_date={start_date}&end_date={end_date}"
        )
        response = _make_api_request(url, self._headers(api_key))
        if response.status_code != 200:
            logger.warning("Could not fetch prices for %s (HTTP %s)", ticker, response.status_code)
            return []

        try:
            prices = PriceResponse(**response.json()).prices
        except (ValueError, KeyError) as exc:
            logger.warning("Failed to parse price data for %s: %s", ticker, exc)
            return []

        if not prices:
            return []

        _cache.set_prices(cache_key, [price.model_dump() for price in prices])
        return prices

    def get_financial_metrics(
        self,
        ticker: str,
        end_date: str,
        period: str = "ttm",
        limit: int = 10,
        api_key: str = None,
    ) -> list[FinancialMetrics]:
        cache_key = f"{ticker}_{period}_{end_date}_{limit}"
        if cached_data := _cache.get_financial_metrics(cache_key):
            return [FinancialMetrics(**metric) for metric in cached_data]

        url = (
            "https://api.financialdatasets.ai/financial-metrics/"
            f"?ticker={ticker}&report_period_lte={end_date}&limit={limit}&period={period}"
        )
        response = _make_api_request(url, self._headers(api_key))
        if response.status_code != 200:
            logger.warning("Could not fetch financial metrics for %s (HTTP %s)", ticker, response.status_code)
            return []

        try:
            financial_metrics = FinancialMetricsResponse(**response.json()).financial_metrics
        except (ValueError, KeyError) as exc:
            logger.warning("Failed to parse financial metrics for %s: %s", ticker, exc)
            return []

        if not financial_metrics:
            return []

        _cache.set_financial_metrics(cache_key, [metric.model_dump() for metric in financial_metrics])
        return financial_metrics

    def search_line_items(
        self,
        ticker: str,
        line_items: list[str],
        end_date: str,
        period: str = "ttm",
        limit: int = 10,
        api_key: str = None,
    ) -> list[LineItem]:
        url = "https://api.financialdatasets.ai/financials/search/line-items"
        body = {
            "tickers": [ticker],
            "line_items": line_items,
            "end_date": end_date,
            "period": period,
            "limit": limit,
        }
        response = _make_api_request(url, self._headers(api_key), method="POST", json_data=body)
        if response.status_code != 200:
            logger.warning("Could not fetch line items for %s (HTTP %s)", ticker, response.status_code)
            return []

        try:
            search_results = LineItemResponse(**response.json()).search_results
        except (ValueError, KeyError) as exc:
            logger.warning("Failed to parse line items for %s: %s", ticker, exc)
            return []

        return search_results[:limit] if search_results else []

    def get_insider_trades(
        self,
        ticker: str,
        end_date: str,
        start_date: str | None = None,
        limit: int = 1000,
        api_key: str = None,
    ) -> list[InsiderTrade]:
        cache_key = f"{ticker}_{start_date or 'none'}_{end_date}_{limit}"
        if cached_data := _cache.get_insider_trades(cache_key):
            return [InsiderTrade(**trade) for trade in cached_data]

        all_trades = []
        current_end_date = end_date
        headers = self._headers(api_key)

        while True:
            url = (
                "https://api.financialdatasets.ai/insider-trades/"
                f"?ticker={ticker}&filing_date_lte={current_end_date}"
            )
            if start_date:
                url += f"&filing_date_gte={start_date}"
            url += f"&limit={limit}"

            response = _make_api_request(url, headers)
            if response.status_code != 200:
                logger.warning("Could not fetch insider trades for %s (HTTP %s)", ticker, response.status_code)
                break

            try:
                insider_trades = InsiderTradeResponse(**response.json()).insider_trades
            except (ValueError, KeyError) as exc:
                logger.warning("Failed to parse insider trades for %s: %s", ticker, exc)
                break

            if not insider_trades:
                break

            all_trades.extend(insider_trades)

            if not start_date or len(insider_trades) < limit:
                break

            current_end_date = min(trade.filing_date for trade in insider_trades).split("T")[0]
            if current_end_date <= start_date:
                break

        if not all_trades:
            return []

        _cache.set_insider_trades(cache_key, [trade.model_dump() for trade in all_trades])
        return all_trades

    def get_company_news(
        self,
        ticker: str,
        end_date: str,
        start_date: str | None = None,
        limit: int = 1000,
        api_key: str = None,
    ) -> list[CompanyNews]:
        cache_key = f"{ticker}_{start_date or 'none'}_{end_date}_{limit}"
        if cached_data := _cache.get_company_news(cache_key):
            return [CompanyNews(**news) for news in cached_data]

        all_news = []
        current_end_date = end_date
        headers = self._headers(api_key)

        while True:
            url = f"https://api.financialdatasets.ai/news/?ticker={ticker}&end_date={current_end_date}"
            if start_date:
                url += f"&start_date={start_date}"
            url += f"&limit={limit}"

            response = _make_api_request(url, headers)
            if response.status_code != 200:
                logger.warning("Could not fetch company news for %s (HTTP %s)", ticker, response.status_code)
                break

            try:
                company_news = CompanyNewsResponse(**response.json()).news
            except (ValueError, KeyError) as exc:
                logger.warning("Failed to parse company news for %s: %s", ticker, exc)
                break

            if not company_news:
                break

            all_news.extend(company_news)

            if not start_date or len(company_news) < limit:
                break

            current_end_date = min(news.date for news in company_news).split("T")[0]
            if current_end_date <= start_date:
                break

        if not all_news:
            return []

        _cache.set_company_news(cache_key, [news.model_dump() for news in all_news])
        return all_news

    def get_market_cap(
        self,
        ticker: str,
        end_date: str,
        api_key: str = None,
    ) -> float | None:
        headers = self._headers(api_key)
        if end_date == datetime.datetime.now().strftime("%Y-%m-%d"):
            url = f"https://api.financialdatasets.ai/company/facts/?ticker={ticker}"
            response = _make_api_request(url, headers)
            if response.status_code != 200:
                logger.warning("Could not fetch company facts for %s (HTTP %s)", ticker, response.status_code)
                return None

            try:
                return CompanyFactsResponse(**response.json()).company_facts.market_cap
            except (ValueError, KeyError) as exc:
                logger.warning("Failed to parse company facts for %s: %s", ticker, exc)
                return None

        financial_metrics = self.get_financial_metrics(ticker, end_date, api_key=api_key)
        if not financial_metrics:
            return None
        return financial_metrics[0].market_cap


class FinancialModelingPrepProvider:
    """
    Scaffold provider for future source replacement.
    We wire the switch now so the rest of the codebase no longer depends on one API.
    """

    name = "fmp"
    api_key_env_var = "FMP_API_KEY"
    supports_line_items = False
    supports_insider_trades = False
    supports_company_news = False
    supports_multiple_metric_periods = False

    def _get(self, path: str, query: dict | None = None, api_key: str | None = None) -> list[dict] | dict:
        query = query or {}
        resolved_api_key = api_key or os.environ.get(self.api_key_env_var)
        if resolved_api_key:
            query["apikey"] = resolved_api_key
        query_string = urlencode({key: value for key, value in query.items() if value is not None})
        url = f"https://financialmodelingprep.com{path}"
        if query_string:
            url = f"{url}?{query_string}"
        response = _make_api_request(url, headers={})
        if response.status_code != 200:
            raise ValueError(f"FMP request failed: {path} (HTTP {response.status_code})")
        return response.json()

    def _pick(self, payload: dict, *keys):
        for key in keys:
            if key in payload and payload[key] is not None:
                return payload[key]
        return None

    def _as_float(self, value):
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    def _as_int(self, value):
        try:
            return None if value is None else int(float(value))
        except (TypeError, ValueError):
            return None

    def _map_period(self, period: str) -> str:
        if period == "annual":
            return "annual"
        if period == "quarter":
            return "quarter"
        return "quarter"

    def _normalize_time(self, value: str | None) -> str:
        if not value:
            return ""
        return f"{value}T00:00:00Z" if "T" not in value else value

    def get_prices(self, ticker: str, start_date: str, end_date: str, api_key: str = None) -> list[Price]:
        cache_key = f"fmp_{ticker}_{start_date}_{end_date}"
        if cached_data := _cache.get_prices(cache_key):
            return [Price(**price) for price in cached_data]

        try:
            payload = self._get(
                "/stable/historical-price-eod/full",
                {"symbol": ticker, "from": start_date, "to": end_date},
                api_key=api_key,
            )
        except Exception as exc:
            logger.warning("FMP could not fetch prices for %s: %s", ticker, exc)
            return []

        rows = payload if isinstance(payload, list) else payload.get("historical", []) or payload.get("prices", [])
        prices: list[Price] = []
        for row in rows:
            date_value = self._pick(row, "date", "time")
            open_value = self._as_float(self._pick(row, "open", "openPrice"))
            close_value = self._as_float(self._pick(row, "close", "closePrice"))
            high_value = self._as_float(self._pick(row, "high", "highPrice"))
            low_value = self._as_float(self._pick(row, "low", "lowPrice"))
            volume_value = self._as_int(self._pick(row, "volume"))
            if None in (date_value, open_value, close_value, high_value, low_value, volume_value):
                continue
            prices.append(
                Price(
                    time=self._normalize_time(date_value),
                    open=open_value,
                    close=close_value,
                    high=high_value,
                    low=low_value,
                    volume=volume_value,
                )
            )

        if prices:
            _cache.set_prices(cache_key, [price.model_dump() for price in prices])
        return prices

    def get_financial_metrics(
        self,
        ticker: str,
        end_date: str,
        period: str = "ttm",
        limit: int = 10,
        api_key: str = None,
    ) -> list[FinancialMetrics]:
        cache_key = f"fmp_{ticker}_{period}_{end_date}_{limit}"
        if cached_data := _cache.get_financial_metrics(cache_key):
            return [FinancialMetrics(**metric) for metric in cached_data]

        try:
            key_metrics_payload = self._get("/stable/key-metrics-ttm", {"symbol": ticker}, api_key=api_key)
            ratios_payload = self._get("/stable/ratios-ttm", {"symbol": ticker}, api_key=api_key)
        except Exception as exc:
            logger.warning("FMP could not fetch financial metrics for %s: %s", ticker, exc)
            return []

        key_metrics = key_metrics_payload[0] if isinstance(key_metrics_payload, list) and key_metrics_payload else {}
        ratios = ratios_payload[0] if isinstance(ratios_payload, list) and ratios_payload else {}

        metrics = [
            FinancialMetrics(
                ticker=ticker,
                report_period=str(end_date),
                period=period,
                currency=str(self._pick(key_metrics, "reportedCurrency") or "USD"),
                market_cap=self._as_float(self._pick(key_metrics, "marketCapTTM", "marketCap")),
                enterprise_value=self._as_float(self._pick(key_metrics, "enterpriseValueTTM", "enterpriseValue")),
                price_to_earnings_ratio=self._as_float(self._pick(key_metrics, "peRatioTTM", "peRatio")),
                price_to_book_ratio=self._as_float(self._pick(key_metrics, "pbRatioTTM", "pbRatio")),
                price_to_sales_ratio=self._as_float(self._pick(key_metrics, "priceToSalesRatioTTM", "priceToSalesRatio")),
                enterprise_value_to_ebitda_ratio=self._as_float(self._pick(key_metrics, "enterpriseValueOverEBITDATTM", "evToEbitda")),
                enterprise_value_to_revenue_ratio=self._as_float(self._pick(key_metrics, "enterpriseValueOverRevenueTTM", "evToSales")),
                free_cash_flow_yield=self._as_float(self._pick(key_metrics, "freeCashFlowYieldTTM", "freeCashFlowYield")),
                peg_ratio=self._as_float(self._pick(key_metrics, "pegRatioTTM", "pegRatio")),
                gross_margin=self._as_float(self._pick(ratios, "grossProfitMarginTTM", "grossProfitMargin")),
                operating_margin=self._as_float(self._pick(ratios, "operatingProfitMarginTTM", "operatingProfitMargin")),
                net_margin=self._as_float(self._pick(ratios, "netProfitMarginTTM", "netProfitMargin")),
                return_on_equity=self._as_float(self._pick(ratios, "returnOnEquityTTM", "returnOnEquity")),
                return_on_assets=self._as_float(self._pick(ratios, "returnOnAssetsTTM", "returnOnAssets")),
                return_on_invested_capital=self._as_float(self._pick(key_metrics, "roicTTM", "roic")),
                asset_turnover=self._as_float(self._pick(ratios, "assetTurnoverTTM", "assetTurnover")),
                inventory_turnover=self._as_float(self._pick(ratios, "inventoryTurnoverTTM", "inventoryTurnover")),
                receivables_turnover=self._as_float(self._pick(ratios, "receivablesTurnoverTTM", "receivablesTurnover")),
                days_sales_outstanding=self._as_float(self._pick(ratios, "daysOfSalesOutstandingTTM", "daysOfSalesOutstanding")),
                operating_cycle=self._as_float(self._pick(ratios, "operatingCycleTTM", "operatingCycle")),
                working_capital_turnover=self._as_float(self._pick(ratios, "workingCapitalTurnoverTTM", "workingCapitalTurnover")),
                current_ratio=self._as_float(self._pick(ratios, "currentRatioTTM", "currentRatio")),
                quick_ratio=self._as_float(self._pick(ratios, "quickRatioTTM", "quickRatio")),
                cash_ratio=self._as_float(self._pick(ratios, "cashRatioTTM", "cashRatio")),
                operating_cash_flow_ratio=self._as_float(self._pick(ratios, "operatingCashFlowRatioTTM", "operatingCashFlowRatio")),
                debt_to_equity=self._as_float(self._pick(ratios, "debtEquityRatioTTM", "debtEquityRatio")),
                debt_to_assets=self._as_float(self._pick(ratios, "debtRatioTTM", "debtRatio")),
                interest_coverage=self._as_float(self._pick(ratios, "interestCoverageTTM", "interestCoverage")),
                revenue_growth=None,
                earnings_growth=None,
                book_value_growth=None,
                earnings_per_share_growth=None,
                free_cash_flow_growth=None,
                operating_income_growth=None,
                ebitda_growth=None,
                payout_ratio=self._as_float(self._pick(ratios, "payoutRatioTTM", "payoutRatio")),
                earnings_per_share=self._as_float(self._pick(key_metrics, "netIncomePerShareTTM", "netIncomePerShare")),
                book_value_per_share=self._as_float(self._pick(key_metrics, "bookValuePerShareTTM", "bookValuePerShare")),
                free_cash_flow_per_share=self._as_float(self._pick(key_metrics, "freeCashFlowPerShareTTM", "freeCashFlowPerShare")),
            )
        ]

        if metrics:
            _cache.set_financial_metrics(cache_key, [metric.model_dump() for metric in metrics])
        return metrics

    def search_line_items(
        self,
        ticker: str,
        line_items: list[str],
        end_date: str,
        period: str = "ttm",
        limit: int = 10,
        api_key: str = None,
    ) -> list[LineItem]:
        logger.info("FMP free-plan mode skips paid financial statements for %s; returning empty line items.", ticker)
        return []

    def get_insider_trades(
        self,
        ticker: str,
        end_date: str,
        start_date: str | None = None,
        limit: int = 1000,
        api_key: str = None,
    ) -> list[InsiderTrade]:
        # FMP insider endpoints vary by plan/version; return an empty set instead of hard-failing.
        logger.info("FMP insider trades are not wired yet for %s; returning empty results.", ticker)
        return []

    def get_company_news(
        self,
        ticker: str,
        end_date: str,
        start_date: str | None = None,
        limit: int = 1000,
        api_key: str = None,
    ) -> list[CompanyNews]:
        logger.info("FMP free-plan mode skips paid news feed for %s; returning empty news.", ticker)
        return []

    def get_market_cap(
        self,
        ticker: str,
        end_date: str,
        api_key: str = None,
    ) -> float | None:
        metrics = self.get_financial_metrics(ticker, end_date, api_key=api_key)
        if metrics and metrics[0].market_cap is not None:
            return metrics[0].market_cap
        return None


class YahooFinanceProvider:
    """Free, no-key provider backed by yfinance."""

    name = "yfinance"
    supports_line_items = True
    supports_insider_trades = False
    supports_company_news = True
    supports_multiple_metric_periods = False

    def _load_module(self):
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance is not installed. Run `poetry install` or `pip install yfinance` to use the free provider.")
            return None
        return yf

    def _ticker(self, ticker: str):
        yf = self._load_module()
        return yf.Ticker(ticker) if yf else None

    def _normalize_timestamp(self, value) -> str | None:
        if value is None:
            return None
        if hasattr(value, "to_pydatetime"):
            value = value.to_pydatetime()
        if isinstance(value, datetime.datetime):
            return value.date().isoformat()
        if isinstance(value, datetime.date):
            return value.isoformat()
        return str(value).split(" ")[0].split("T")[0]

    def _safe_value(self, data: dict, *keys):
        for key in keys:
            value = data.get(key)
            if value is not None:
                return value
        return None

    def _to_float(self, value):
        try:
            if pd.isna(value):
                return None
        except TypeError:
            pass
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    def _statement_value(self, frame: pd.DataFrame | None, labels: list[str], column) -> float | None:
        if frame is None or frame.empty:
            return None
        for label in labels:
            if label in frame.index:
                return self._to_float(frame.at[label, column])
        return None

    def _statement_columns(self, frame: pd.DataFrame | None, limit: int) -> list:
        if frame is None or frame.empty:
            return []
        return list(frame.columns[:limit])

    def get_prices(self, ticker: str, start_date: str, end_date: str, api_key: str = None) -> list[Price]:
        cache_key = f"yf_{ticker}_{start_date}_{end_date}"
        if cached_data := _cache.get_prices(cache_key):
            return [Price(**price) for price in cached_data]

        yf_ticker = self._ticker(ticker)
        if yf_ticker is None:
            return []

        end_exclusive = (datetime.date.fromisoformat(end_date) + datetime.timedelta(days=1)).isoformat()
        try:
            history = yf_ticker.history(start=start_date, end=end_exclusive, interval="1d", auto_adjust=False)
        except Exception as exc:
            logger.warning("Yahoo Finance could not fetch prices for %s: %s", ticker, exc)
            return []

        if history is None or history.empty:
            return []

        prices: list[Price] = []
        for idx, row in history.iterrows():
            open_value = self._to_float(row.get("Open"))
            close_value = self._to_float(row.get("Close"))
            high_value = self._to_float(row.get("High"))
            low_value = self._to_float(row.get("Low"))
            volume_value = row.get("Volume")
            if None in (open_value, close_value, high_value, low_value) or pd.isna(volume_value):
                continue
            prices.append(
                Price(
                    open=open_value,
                    close=close_value,
                    high=high_value,
                    low=low_value,
                    volume=int(volume_value),
                    time=f"{self._normalize_timestamp(idx)}T00:00:00Z",
                )
            )

        if prices:
            _cache.set_prices(cache_key, [price.model_dump() for price in prices])
        return prices

    def get_financial_metrics(
        self,
        ticker: str,
        end_date: str,
        period: str = "ttm",
        limit: int = 10,
        api_key: str = None,
    ) -> list[FinancialMetrics]:
        cache_key = f"yf_{ticker}_{period}_{end_date}_{limit}"
        if cached_data := _cache.get_financial_metrics(cache_key):
            return [FinancialMetrics(**metric) for metric in cached_data]

        yf_ticker = self._ticker(ticker)
        if yf_ticker is None:
            return []

        try:
            info = yf_ticker.info or {}
            fast_info = getattr(yf_ticker, "fast_info", {}) or {}
        except Exception as exc:
            logger.warning("Yahoo Finance could not fetch summary metrics for %s: %s", ticker, exc)
            return []

        market_cap = self._to_float(self._safe_value(info, "marketCap") or getattr(fast_info, "get", lambda *args, **kwargs: None)("market_cap"))
        free_cash_flow = self._to_float(self._safe_value(info, "freeCashflow", "freeCashFlow"))
        shares_outstanding = self._to_float(self._safe_value(info, "sharesOutstanding"))
        metrics = [
            FinancialMetrics(
                ticker=ticker,
                report_period=end_date,
                period=period,
                currency=str(self._safe_value(info, "financialCurrency", "currency") or "USD"),
                market_cap=market_cap,
                enterprise_value=self._to_float(self._safe_value(info, "enterpriseValue")),
                price_to_earnings_ratio=self._to_float(self._safe_value(info, "trailingPE", "forwardPE")),
                price_to_book_ratio=self._to_float(self._safe_value(info, "priceToBook")),
                price_to_sales_ratio=self._to_float(self._safe_value(info, "priceToSalesTrailing12Months")),
                enterprise_value_to_ebitda_ratio=self._to_float(self._safe_value(info, "enterpriseToEbitda")),
                enterprise_value_to_revenue_ratio=self._to_float(self._safe_value(info, "enterpriseToRevenue")),
                free_cash_flow_yield=(free_cash_flow / market_cap) if free_cash_flow and market_cap else None,
                peg_ratio=self._to_float(self._safe_value(info, "pegRatio")),
                gross_margin=self._to_float(self._safe_value(info, "grossMargins")),
                operating_margin=self._to_float(self._safe_value(info, "operatingMargins")),
                net_margin=self._to_float(self._safe_value(info, "profitMargins")),
                return_on_equity=self._to_float(self._safe_value(info, "returnOnEquity")),
                return_on_assets=self._to_float(self._safe_value(info, "returnOnAssets")),
                return_on_invested_capital=None,
                asset_turnover=None,
                inventory_turnover=None,
                receivables_turnover=None,
                days_sales_outstanding=None,
                operating_cycle=None,
                working_capital_turnover=None,
                current_ratio=self._to_float(self._safe_value(info, "currentRatio")),
                quick_ratio=self._to_float(self._safe_value(info, "quickRatio")),
                cash_ratio=None,
                operating_cash_flow_ratio=None,
                debt_to_equity=self._to_float(self._safe_value(info, "debtToEquity")),
                debt_to_assets=None,
                interest_coverage=None,
                revenue_growth=self._to_float(self._safe_value(info, "revenueGrowth")),
                earnings_growth=self._to_float(self._safe_value(info, "earningsGrowth")),
                book_value_growth=None,
                earnings_per_share_growth=None,
                free_cash_flow_growth=None,
                operating_income_growth=None,
                ebitda_growth=self._to_float(self._safe_value(info, "ebitdaMargins")),
                payout_ratio=self._to_float(self._safe_value(info, "payoutRatio")),
                earnings_per_share=self._to_float(self._safe_value(info, "trailingEps", "currentEps")),
                book_value_per_share=self._to_float(self._safe_value(info, "bookValue")),
                free_cash_flow_per_share=(free_cash_flow / shares_outstanding) if free_cash_flow and shares_outstanding else None,
            )
        ]

        _cache.set_financial_metrics(cache_key, [metric.model_dump() for metric in metrics])
        return metrics

    def search_line_items(
        self,
        ticker: str,
        line_items: list[str],
        end_date: str,
        period: str = "ttm",
        limit: int = 10,
        api_key: str = None,
    ) -> list[LineItem]:
        yf_ticker = self._ticker(ticker)
        if yf_ticker is None:
            return []

        try:
            income = yf_ticker.quarterly_income_stmt if period != "annual" else yf_ticker.income_stmt
            balance = yf_ticker.quarterly_balance_sheet if period != "annual" else yf_ticker.balance_sheet
            cashflow = yf_ticker.quarterly_cashflow if period != "annual" else yf_ticker.cashflow
        except Exception as exc:
            logger.warning("Yahoo Finance could not fetch statements for %s: %s", ticker, exc)
            return []

        statement_map = {
            "revenue": (income, ["Total Revenue", "Operating Revenue", "Revenue"]),
            "earnings_per_share": (income, ["Basic EPS", "Diluted EPS"]),
            "net_income": (income, ["Net Income", "Net Income Common Stockholders"]),
            "operating_income": (income, ["Operating Income"]),
            "gross_margin": (income, ["Gross Margin"]),
            "operating_margin": (income, ["Operating Margin"]),
            "free_cash_flow": (cashflow, ["Free Cash Flow"]),
            "capital_expenditure": (cashflow, ["Capital Expenditure"]),
            "cash_and_equivalents": (balance, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"]),
            "total_debt": (balance, ["Total Debt"]),
            "shareholders_equity": (balance, ["Stockholders Equity", "Total Equity Gross Minority Interest"]),
            "outstanding_shares": (income, ["Diluted Average Shares", "Basic Average Shares"]),
            "book_value_per_share": (balance, ["Tangible Book Value", "Common Stock Equity"]),
            "total_assets": (balance, ["Total Assets"]),
            "total_liabilities": (balance, ["Total Liabilities Net Minority Interest", "Total Liabilities"]),
            "current_assets": (balance, ["Current Assets", "Total Current Assets"]),
            "current_liabilities": (balance, ["Current Liabilities", "Total Current Liabilities"]),
            "dividends_and_other_cash_distributions": (cashflow, ["Cash Dividends Paid"]),
            "depreciation_and_amortization": (cashflow, ["Depreciation And Amortization", "Depreciation Amortization Depletion"]),
            "working_capital": (balance, ["Working Capital"]),
            "interest_expense": (income, ["Interest Expense"]),
            "ebit": (income, ["EBIT"]),
            "ebitda": (income, ["EBITDA"]),
            "research_and_development": (income, ["Research And Development"]),
        }

        columns = []
        for frame in (income, balance, cashflow):
            frame_columns = self._statement_columns(frame, limit)
            if frame_columns:
                columns = frame_columns
                break
        if not columns:
            return []

        results: list[LineItem] = []
        for column in columns[:limit]:
            payload = {
                "ticker": ticker,
                "report_period": self._normalize_timestamp(column) or end_date,
                "period": period,
                "currency": "USD",
            }
            for line_item in line_items:
                frame, labels = statement_map.get(line_item, (None, []))
                payload[line_item] = self._statement_value(frame, labels, column)
            results.append(LineItem(**payload))
        return results

    def get_insider_trades(
        self,
        ticker: str,
        end_date: str,
        start_date: str | None = None,
        limit: int = 1000,
        api_key: str = None,
    ) -> list[InsiderTrade]:
        logger.info("Yahoo Finance provider does not preload insider trades for %s; returning empty results.", ticker)
        return []

    def get_company_news(
        self,
        ticker: str,
        end_date: str,
        start_date: str | None = None,
        limit: int = 1000,
        api_key: str = None,
    ) -> list[CompanyNews]:
        cache_key = f"yf_{ticker}_{start_date or 'none'}_{end_date}_{limit}"
        if cached_data := _cache.get_company_news(cache_key):
            return [CompanyNews(**news) for news in cached_data]

        yf_ticker = self._ticker(ticker)
        if yf_ticker is None:
            return []

        try:
            payload = yf_ticker.news or []
        except Exception as exc:
            logger.warning("Yahoo Finance could not fetch news for %s: %s", ticker, exc)
            return []

        results: list[CompanyNews] = []
        for row in payload[:limit]:
            content = row.get("content", {}) if isinstance(row, dict) else {}
            title = content.get("title") or row.get("title")
            provider = (content.get("provider") or {}).get("displayName") if isinstance(content.get("provider"), dict) else None
            url = ((content.get("canonicalUrl") or {}).get("url") if isinstance(content.get("canonicalUrl"), dict) else None) or row.get("link")
            pub_date = content.get("pubDate") or row.get("providerPublishTime") or row.get("published")
            normalized_date = self._normalize_timestamp(pub_date)
            if not title or not url or not normalized_date:
                continue
            if start_date and normalized_date < start_date:
                continue
            if normalized_date > end_date:
                continue
            results.append(
                CompanyNews(
                    ticker=ticker,
                    title=str(title),
                    author=None,
                    source=str(provider or "Yahoo Finance"),
                    date=f"{normalized_date}T00:00:00Z",
                    url=str(url),
                    sentiment=None,
                )
            )

        if results:
            _cache.set_company_news(cache_key, [news.model_dump() for news in results])
        return results

    def get_market_cap(
        self,
        ticker: str,
        end_date: str,
        api_key: str = None,
    ) -> float | None:
        metrics = self.get_financial_metrics(ticker, end_date, api_key=api_key)
        if metrics and metrics[0].market_cap is not None:
            return metrics[0].market_cap
        return None


_PROVIDERS: dict[str, FinancialDataProvider] = {
    "free": YahooFinanceProvider(),
    "yfinance": YahooFinanceProvider(),
    "yahoo": YahooFinanceProvider(),
    "yahoo_finance": YahooFinanceProvider(),
    "financialdatasets": FinancialDatasetsProvider(),
    "financial_datasets": FinancialDatasetsProvider(),
    "fmp": FinancialModelingPrepProvider(),
    "financialmodelingprep": FinancialModelingPrepProvider(),
}


def get_financial_data_provider_name() -> str:
    return os.getenv("FINANCIAL_DATA_PROVIDER", "free").strip().lower()


def get_financial_data_provider() -> FinancialDataProvider:
    provider_name = get_financial_data_provider_name()
    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        supported = ", ".join(sorted(_PROVIDERS.keys()))
        raise ValueError(
            f"Unsupported FINANCIAL_DATA_PROVIDER='{provider_name}'. "
            f"Supported values: {supported}"
        )
    return provider


def get_prices(ticker: str, start_date: str, end_date: str, api_key: str = None) -> list[Price]:
    if ticker in _preloaded_data:
        preloaded_prices = _preloaded_data[ticker].get("prices", [])
        sliced = _slice_preloaded_by_date_range(preloaded_prices, end_date=end_date, start_date=start_date, attr_name="time")
        if sliced:
            return sliced
    return get_financial_data_provider().get_prices(ticker, start_date, end_date, api_key=api_key)


def get_financial_metrics(
    ticker: str,
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
    api_key: str = None,
) -> list[FinancialMetrics]:
    if ticker in _preloaded_data:
        preloaded_metrics = _preloaded_data[ticker].get("financial_metrics", {}).get(period, [])
        sliced = _slice_preloaded_by_end_date(preloaded_metrics, end_date=end_date, limit=limit)
        if sliced:
            return sliced
    return get_financial_data_provider().get_financial_metrics(
        ticker=ticker,
        end_date=end_date,
        period=period,
        limit=limit,
        api_key=api_key,
    )


def search_line_items(
    ticker: str,
    line_items: list[str],
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
    api_key: str = None,
) -> list[LineItem]:
    if ticker in _preloaded_data:
        preloaded_items = _preloaded_data[ticker].get("line_items", {}).get(period, [])
        if _preloaded_line_items_match(preloaded_items, line_items):
            sliced = _slice_preloaded_by_end_date(preloaded_items, end_date=end_date, limit=limit)
            if sliced:
                return _project_line_items(sliced, line_items, limit)
    return get_financial_data_provider().search_line_items(
        ticker=ticker,
        line_items=line_items,
        end_date=end_date,
        period=period,
        limit=limit,
        api_key=api_key,
    )


def get_insider_trades(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
    api_key: str = None,
) -> list[InsiderTrade]:
    if ticker in _preloaded_data:
        preloaded_trades = _preloaded_data[ticker].get("insider_trades", [])
        sliced = _slice_preloaded_by_date_range(
            preloaded_trades,
            end_date=end_date,
            start_date=start_date,
            limit=limit,
            attr_name="filing_date",
        )
        if sliced:
            return sliced
    return get_financial_data_provider().get_insider_trades(
        ticker=ticker,
        end_date=end_date,
        start_date=start_date,
        limit=limit,
        api_key=api_key,
    )


def get_company_news(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
    api_key: str = None,
) -> list[CompanyNews]:
    if ticker in _preloaded_data:
        preloaded_news = _preloaded_data[ticker].get("company_news", [])
        sliced = _slice_preloaded_by_date_range(
            preloaded_news,
            end_date=end_date,
            start_date=start_date,
            limit=limit,
            attr_name="date",
        )
        if sliced:
            return sliced
    return get_financial_data_provider().get_company_news(
        ticker=ticker,
        end_date=end_date,
        start_date=start_date,
        limit=limit,
        api_key=api_key,
    )


def get_market_cap(
    ticker: str,
    end_date: str,
    api_key: str = None,
) -> float | None:
    if ticker in _preloaded_data and _preloaded_data[ticker].get("market_cap") is not None:
        return _preloaded_data[ticker]["market_cap"]
    return get_financial_data_provider().get_market_cap(
        ticker=ticker,
        end_date=end_date,
        api_key=api_key,
    )


def prices_to_df(prices: list[Price]) -> pd.DataFrame:
    """Convert prices to a DataFrame."""
    df = pd.DataFrame([price.model_dump() for price in prices])
    df["Date"] = pd.to_datetime(df["time"])
    df.set_index("Date", inplace=True)
    numeric_cols = ["open", "close", "high", "low", "volume"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.sort_index(inplace=True)
    return df


def get_price_data(ticker: str, start_date: str, end_date: str, api_key: str = None) -> pd.DataFrame:
    prices = get_prices(ticker, start_date, end_date, api_key=api_key)
    return prices_to_df(prices)
