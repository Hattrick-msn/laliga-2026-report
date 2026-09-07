"""Build the LaLiga edition from the existing report layout and current snapshot."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
html = (ROOT / "2026-2027-swiss-super-league-second-yellow-report.html").read_text(encoding="utf-8")
report = json.loads((ROOT / "report-assets/laliga-report.json").read_text(encoding="utf-8"))
if not report.get("lastSync"):
    raise SystemExit("Refresh a valid LaLiga snapshot before building")

replacements = {
    "<h1>两黄变红比赛实时核对报告</h1>": "<h1>西甲两黄变红实时报告</h1>",
    "瑞士超": "西甲",
    "Brack Super League": "LALIGA EA SPORTS",
    "瑞士足球联赛官网": "西甲官网",
    "瑞士当地时间": "北京时间",
    "Europe/Zurich": "Asia/Shanghai",
    "（瑞士）": "（北京）",
    "SFL": "LALIGA",
    "report-assets/sfl-logo.png": "report-assets/laliga-logo.png",
    "swiss-super-league-report.json": "laliga-report.json",
    "https://sfl.ch/dashboard-stats/stats-superleague?tab=player&type=total+second+yellow&cursor=0": "https://www.laliga.com/en-GB/stats/laliga-easports/yellow-cards",
    "https://sfl.ch/match-center/${encodeURIComponent(String(matchId))}": "https://www.laliga.com/en-GB/match/${encodeURIComponent(String(matchId))}",
    "officialUrl(match.id)": "officialUrl(match.slug)",
    "黄红牌": "两黄离场",
    "例如：Imourane Hassane、Grasshopper、1kfz06": "例如：Adrià Alti、RC Deportivo、102271",
    "font-size: clamp(25px, 3vw, 42px)": "font-size: 34px",
    'location.hostname.endsWith(".github.io")': '!(["127.0.0.1", "localhost"].includes(location.hostname))',
    'const newest = Math.max(...report.matches.map(item => new Date(`${item.date}T23:59:59`).getTime()));': 'const newest = Date.now();',
    'new Date(`${match.date}T00:00:00`).getTime()': 'new Date(match.kickoff || `${match.date}T${match.time}:00+08:00`).getTime()',
    "当前官网口径下，两黄变红球员在赛季牌榜记": "已核对 Alti 实例在赛季累计栏显示",
    "0黄、1黄红、1红": "0黄、1次两黄离场、1红",
    "逐场记录出现 <code>secondyellow card</code> 即收录。": "官网比赛事件出现 <code>Second Yellow</code> 即收录。",
    "罚下判定采用 Opta 的 <code>secondyellow card</code> 事件，第一张黄牌按同一球员 ID 回溯。": "罚下判定采用官网 Second Yellow 事件，第一张黄牌按球队及球员姓名回溯；缺失时显示待核实。",
    "页面每60秒读取本地服务；服务复核官网已开始或已结束的比赛。": "本地版约每60秒复核赛果，牌榜约每10分钟复核，已结束比赛约每6小时复核；刷新按钮可强制复核。",
    "LALIGA 官网当前比赛中心和统计页使用 Opta。": "牌榜以西甲官网赛季累计为准，比赛事件保留官网原始分钟。",
    "本报告读取官网公开调用的赛程、球员统计与逐场解说数据，不混用博彩牌数规则。Opta 将普通黄牌、第二黄牌和红牌分别采集。": "数据读取西甲官网公开页面的结构化统计与比赛事件。Opta 对照仅覆盖下列已核实球员，不代表全榜逐人一致。赛季累计与单场出牌展示分开列示。",
    "公开数据由 GitHub Actions 定时更新，页面每60秒检查一次。": "页面每60秒检查已发布快照，数据时间以最近同步为准。",
    "时间待定": "未找到，待核实",
}
for source, target in replacements.items():
    html = html.replace(source, target)

start = html.index("    const seedReport = {")
end = html.index("    const list =", start)
html = html[:start] + "    const seedReport = " + json.dumps(report, ensure_ascii=False).replace("<", "\\u003c") + ";\n\n" + html[end:]
html = html.replace('id="metric-checked">14', 'id="metric-checked">' + str(report["checkedMatches"]))
html = html.replace('内置快照日期：2026-08-09', '内置快照日期：' + report["lastSync"][:10])
html = html.replace('已读取的官网比赛记录', '已读取的官网比赛记录 / 已赛')
html = html.replace('report.checkedMatches ?? "-";', '`${report.checkedMatches ?? 0} / ${report.eligibleMatches ?? 0}`;')
html = html.replace('class="ranking-table-wrap"', 'class="ranking-table-wrap" tabindex="0" aria-label="球员牌榜，可滚动"')
html = html.replace('<span class="ranking-player">${escapeHtml(row.name)}</span>', '<a class="ranking-player" href="https://www.laliga.com/en-GB/player/${encodeURIComponent(row.playerSlug)}" target="_blank" rel="noopener noreferrer">${escapeHtml(row.name)}</a>')
html = html.replace('<span class="team">${escapeHtml(match.home)}</span>', '<span class="team"><img class="team-badge" src="${escapeHtml(match.homeShield)}" alt="">${escapeHtml(match.home)}</span>')
html = html.replace('<span class="team away">${escapeHtml(match.away)}</span>', '<span class="team away"><img class="team-badge" src="${escapeHtml(match.awayShield)}" alt="">${escapeHtml(match.away)}</span>')
html = html.replace('    .ranking-table-wrap { overflow: auto;', '    .ranking-table-wrap { max-height: 390px; overflow: auto;')
html = html.replace('  </style>', '''
    .brand img { width: 72px; height: 72px; object-fit: contain; background: white; border-radius: 4px; padding: 8px; }
    .team-badge { width: 25px; height: 25px; object-fit: contain; vertical-align: middle; margin-right: 6px; }
    .ranking-table thead { position: sticky; top: 0; z-index: 1; background: #f3f5f6; }
    .comparison { padding: 18px 0; border-top: 1px solid var(--line); margin-top: 20px; }
    .comparison h2 { font-size: 20px; margin: 0 0 10px; }
    .comparison p { margin: 8px 0; }
    .comparison a { color: #007f79; }
    .comparison table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
    .comparison th, .comparison td { text-align: left; border-bottom: 1px solid var(--line); padding: 9px; }
    .comparison-note { color: var(--muted); font-size: 13px; }
    .team, .person, .ranking-player { overflow-wrap: anywhere; }
    .record-id { overflow-wrap: anywhere; }
    @media (max-width: 720px) {
      h1 { font-size: 25px; }
      .brand { gap: 12px; }
      .brand img { width: 52px; height: 52px; }
      .comparison { overflow-x: auto; }
      .metric-value { font-size: 28px; }
      .search-wrap { flex: 0 0 auto; }
      .ranking-table { min-width: 0; table-layout: fixed; font-size: 12px; }
      .ranking-table th, .ranking-table td { padding: 8px 4px; overflow-wrap: anywhere; }
      .ranking-table th { font-size: 11px; }
      .ranking-table th:first-child { width: 36px; }
      .ranking-table th:nth-child(3), .ranking-table th:nth-child(5) { width: 43px; }
      .ranking-table th:nth-child(4) { width: 65px; }
      .ranking-table .card-chip { width: 8px; height: 12px; margin-right: 3px; }
      .ranking-team { font-size: 11px; }
    }
    @media print { .ranking-table-wrap { max-height: none; overflow: visible; } .ranking-table thead { position: static; } }
  </style>''')
html = html.replace('      <section class="methodology"', '''      <section class="comparison" aria-labelledby="comparison-title">
        <h2 id="comparison-title">Opta 实例核对</h2>
        <div id="comparison-body"></div>
      </section>

      <section class="methodology"''')
html = html.replace('      renderRankings();\n    }', '''      renderRankings();
      renderComparison();
    }''', 1)
insert = '''
    function renderComparison() {
      const opta = report.optaComparison;
      const official = Object.values(report.cardLeaderboards || {}).flat().find(p=>p.playerSlug === "adria-altimira");
      const box = document.getElementById("comparison-body");
      if (!opta || !official) { box.textContent = "对照数据暂不可用。"; return; }
      const equal = ["yellow", "doubleYellow", "red"].every(k=>official[k] === opta[k]);
      box.innerHTML = `<p><strong>Adrià Alti · RC Deportivo</strong> · ${equal ? "本次读取的赛季累计一致" : "两处累计存在差异，待复核"}</p>
        <table><thead><tr><th>数据来源</th><th>黄牌</th><th>两黄离场</th><th>红牌</th></tr></thead><tbody>
        <tr><td><a href="https://www.laliga.com/en-GB/player/adria-altimira" target="_blank" rel="noopener noreferrer">西甲官网</a></td><td>${official.yellow}</td><td>${official.doubleYellow}</td><td>${official.red}</td></tr>
        <tr><td><a href="https://theanalyst.com/players/1295/adria-alti/stats" target="_blank" rel="noopener noreferrer">Opta Analyst</a></td><td>${opta.yellow}</td><td>${opta.doubleYellow}</td><td>${opta.red}</td></tr></tbody></table>
        <p class="comparison-note">Opta 对照读取时间：${escapeHtml(formatSyncTime(opta.checkedOn))}。2026年8月31日对瓦伦西亚的单场记录显示两张黄牌及一张红牌；上述表格是赛季累计，不能将两者直接相加。</p>`;
    }
'''
html = html.replace('    function setSyncState(', insert + '\n    function setSyncState(')
html = html.replace('已显示最近一次有效数据', '部分数据待复核，已保留快照')
html = html.replace('if (nextReport.lastSync && Array.isArray(nextReport.matches)) report = nextReport;', 'if (!nextReport.lastSync || !Array.isArray(nextReport.matches)) throw new Error("有效快照缺失");\n        report = nextReport;')
html = html.replace('fetch(endpoint,{cache:"no-store"})', 'fetch(endpoint,{cache:"no-store",signal:AbortSignal.timeout(20000)})')
html = html.replace('      const players = new Set(matches.flatMap(match=>match.events.map(event=>event.playerId)));', '      const players = new Set(matches.flatMap(match=>match.events.map(event=>event.person)));')
html = html.replace('第一次普通黄牌和第二次黄牌的实际分钟', '第一张黄牌和第二张黄牌的官网分钟')
(ROOT / "2026-2027-laliga-second-yellow-report.html").write_text(html, encoding="utf-8")
print("Built LaLiga report")
