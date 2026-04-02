import { CheckCircle, Clock, MoreHorizontal, XCircle } from 'lucide-react';

const AGENT_DISPLAY_NAME_MAP: Record<string, string> = {
  aswath_damodaran_agent: 'Aswath Damodaran｜估值分析',
  ben_graham_agent: 'Ben Graham｜深度價值分析',
  bill_ackman_agent: 'Bill Ackman｜事件驅動分析',
  cathie_wood_agent: 'Cathie Wood｜成長創新分析',
  charlie_munger_agent: 'Charlie Munger｜優質企業分析',
  michael_burry_agent: 'Michael Burry｜逆向價值分析',
  mohnish_pabrai_agent: 'Mohnish Pabrai｜高賠率價值分析',
  nassim_taleb_agent: 'Nassim Taleb｜尾部風險分析',
  peter_lynch_agent: 'Peter Lynch｜成長選股分析',
  phil_fisher_agent: 'Phil Fisher｜企業質化分析',
  rakesh_jhunjhunwala_agent: 'Rakesh Jhunjhunwala｜趨勢成長分析',
  stanley_druckenmiller_agent: 'Stanley Druckenmiller｜總體趨勢分析',
  warren_buffett_agent: 'Warren Buffett｜護城河價值分析',
  technical_analyst_agent: 'Technical Analyst｜技術面分析',
  fundamentals_analyst_agent: 'Fundamentals Analyst｜基本面分析',
  growth_analyst_agent: 'Growth Analyst｜成長性分析',
  news_sentiment_agent: 'News Sentiment Analyst｜新聞情緒分析',
  sentiment_analyst_agent: 'Sentiment Analyst｜市場情緒分析',
  valuation_analyst_agent: 'Valuation Analyst｜估值模型分析',
  risk_management_agent: 'Risk Manager｜風險控管',
  portfolio_manager: 'Portfolio Manager｜投資組合決策',
  portfolio_management_agent: 'Portfolio Manager｜投資組合決策',
};

// Helper function to detect if content is JSON
export function isJsonString(str: string): boolean {
  try {
    const parsed = JSON.parse(str);
    return typeof parsed === 'object' && parsed !== null;
  } catch {
    return false;
  }
}

// Helper function to get display name for agent
export function getDisplayName(agentName: string): string {
  if (AGENT_DISPLAY_NAME_MAP[agentName]) {
    return AGENT_DISPLAY_NAME_MAP[agentName];
  }

  // Remove _agent suffix first
  let name = agentName.replace("_agent", "");
  
  // Remove ID suffix (everything after the last underscore if it looks like an ID)
  const lastUnderscoreIndex = name.lastIndexOf("_");
  if (lastUnderscoreIndex !== -1) {
    const potentialId = name.substring(lastUnderscoreIndex + 1);
    // If the part after the last underscore looks like an ID (alphanumeric, 5+ chars), remove it
    if (/^[a-zA-Z0-9]{5,}$/.test(potentialId)) {
      name = name.substring(0, lastUnderscoreIndex);
    }
  }
  
  // Replace remaining underscores with spaces and title case
  return name.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase());
}

// Helper function to get status icon and color
export function getStatusIcon(status: string) {
  switch (status.toLowerCase()) {
    case 'complete':
      return { icon: CheckCircle, color: 'text-green-500' };
    case 'error':
      return { icon: XCircle, color: 'text-red-500' };
    case 'in_progress':
      return { icon: MoreHorizontal, color: 'text-yellow-500' };
    default:
      return { icon: Clock, color: 'text-muted-foreground' };
  }
}

// Helper function to get signal color
export function getSignalColor(signal: string): string {
  switch (signal.toUpperCase()) {
    case 'BULLISH':
      return 'text-green-500';
    case 'BEARISH':
      return 'text-red-500';
    case 'NEUTRAL':
      return 'text-primary';
    default:
      return 'text-muted-foreground';
  }
}

// Helper function to get action color
export function getActionColor(action: string): string {
  switch (action.toUpperCase()) {
    case 'BUY':
    case 'COVER':
      return 'text-green-500';
    case 'SELL':
    case 'SHORT':
      return 'text-red-500';
    case 'HOLD':
      return 'text-primary';
    default:
      return 'text-muted-foreground';
  }
}

// Helper function to sort agents in display order
export function sortAgents(agents: [string, any][]): [string, any][] {
  return agents.sort(([agentA, dataA], [agentB, dataB]) => {
    // First, sort by agent type priority (Risk Management and Portfolio Management at bottom)
    const getPriority = (agentName: string) => {
      if (agentName.includes("risk_management")) return 3;
      if (agentName.includes("portfolio_management")) return 4;
      return 1;
    };
    
    const priorityA = getPriority(agentA);
    const priorityB = getPriority(agentB);
    
    // If different priorities, sort by priority
    if (priorityA !== priorityB) {
      return priorityA - priorityB;
    }
    
    // If same priority, sort by timestamp (ascending - oldest first)
    const timestampA = dataA.timestamp ? new Date(dataA.timestamp).getTime() : 0;
    const timestampB = dataB.timestamp ? new Date(dataB.timestamp).getTime() : 0;
    
    if (timestampA !== timestampB) {
      return timestampA - timestampB;
    }
    
    // If no timestamp difference, sort alphabetically
    return agentA.localeCompare(agentB);
  });
} 
