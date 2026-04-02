"""Shared display names for agent labels shown in the UI and progress output."""

DISPLAY_NAME_MAP = {
    "aswath_damodaran_agent": "Aswath Damodaran｜估值分析",
    "ben_graham_agent": "Ben Graham｜深度價值分析",
    "bill_ackman_agent": "Bill Ackman｜事件驅動分析",
    "cathie_wood_agent": "Cathie Wood｜成長創新分析",
    "charlie_munger_agent": "Charlie Munger｜優質企業分析",
    "michael_burry_agent": "Michael Burry｜逆向價值分析",
    "mohnish_pabrai_agent": "Mohnish Pabrai｜高賠率價值分析",
    "nassim_taleb_agent": "Nassim Taleb｜尾部風險分析",
    "peter_lynch_agent": "Peter Lynch｜成長選股分析",
    "phil_fisher_agent": "Phil Fisher｜企業質化分析",
    "rakesh_jhunjhunwala_agent": "Rakesh Jhunjhunwala｜趨勢成長分析",
    "stanley_druckenmiller_agent": "Stanley Druckenmiller｜總體趨勢分析",
    "warren_buffett_agent": "Warren Buffett｜護城河價值分析",
    "technical_analyst_agent": "Technical Analyst｜技術面分析",
    "fundamentals_analyst_agent": "Fundamentals Analyst｜基本面分析",
    "growth_analyst_agent": "Growth Analyst｜成長性分析",
    "news_sentiment_agent": "News Sentiment Analyst｜新聞情緒分析",
    "news_sentiment_analyst_agent": "News Sentiment Analyst｜新聞情緒分析",
    "sentiment_analyst_agent": "Sentiment Analyst｜市場情緒分析",
    "valuation_analyst_agent": "Valuation Analyst｜估值模型分析",
    "risk_management_agent": "Risk Manager｜風險控管",
    "portfolio_manager": "Portfolio Manager｜投資組合決策",
    "portfolio_management_agent": "Portfolio Manager｜投資組合決策",
}


def get_agent_display_name(agent_name: str) -> str:
    """Convert internal agent ids into user-friendly labels."""
    return DISPLAY_NAME_MAP.get(
        agent_name,
        agent_name.replace("_agent", "").replace("_", " ").title(),
    )
