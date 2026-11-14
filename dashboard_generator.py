"""
朝刊ダッシュボード画面生成モジュール（dashboard_generator.py -> docs/index.html）
Tailwind CSS（CDN）と Chart.js（CDN）を使用し、単一HTMLで美しく表示される
PC・スマートフォン対応レスポンシブUIを生成する。
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from agents import MeetingDecision

USD_TO_JPY_RATE: float = 150.0


def generate_dashboard(
    portfolio: dict[str, Any],
    decision: MeetingDecision,
    execution_result: dict[str, Any],
    trade_history: list[dict[str, str]],
    output_path: Path,
) -> Path:
    """
    最新のポートフォリオ状態、AI会議結果、執行結果、売買履歴から
    docs/index.html を生成して保存する。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cash = float(execution_result.get("cash_after", portfolio.get("cash", 0.0)))
    holdings_val = float(execution_result.get("holdings_value_after", 0.0))
    total_equity = float(execution_result.get("total_equity_after", cash + holdings_val))
    total_deposited = float(execution_result.get("total_deposited", portfolio.get("total_deposited", 330.0)))
    total_return = float(execution_result.get("total_return", total_equity - total_deposited))
    total_return_pct = float(execution_result.get("total_return_pct", 0.0))
    updated_at = html.escape(str(portfolio.get("updated_at", "")))
    market_date = html.escape(str(execution_result.get("market_date", "")))

    jpy_total_equity = int(round(total_equity * USD_TO_JPY_RATE))
    jpy_cash = int(round(cash * USD_TO_JPY_RATE))
    cash_ratio_pct = round((cash / total_equity) * 100.0, 1) if total_equity > 0 else 100.0

    return_color_class = "text-emerald-400" if total_return >= 0 else "text-rose-400"
    return_sign = "+" if total_return >= 0 else ""

    # 本日の最終結論カード用スタイル
    action = str(execution_result.get("action", "HOLD")).upper()
    if action == "BUY":
        badge_bg = "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
        card_border = "border-emerald-500/50"
        action_label = "BUY（現物買付）"
    elif action == "SELL":
        badge_bg = "bg-rose-500/20 text-rose-300 border-rose-500/40"
        card_border = "border-rose-500/50"
        action_label = "SELL（現物売却）"
    else:
        badge_bg = "bg-slate-500/20 text-slate-300 border-slate-500/40"
        card_border = "border-slate-600/60"
        action_label = "HOLD（現金温存・見送り）"

    ticker_str = html.escape(str(execution_result.get("ticker", "NONE")))
    sector_str = html.escape(str(execution_result.get("sector", "-")))
    shares_int = int(execution_result.get("shares", 0))
    price_val = float(execution_result.get("price", 0.0))
    total_amount_val = float(execution_result.get("total_amount", 0.0))
    exec_note_str = html.escape(str(execution_result.get("note", "")))
    sbi_guide_str = html.escape(decision.sbi_order_guide or "本日の注文はありません。")

    # 4体のAI社員コメント
    researcher_text = html.escape(decision.researcher_comment)
    analyst_text = html.escape(decision.analyst_comment)
    manager_text = html.escape(decision.manager_reason)
    accountant_text = html.escape(str(execution_result.get("accountant_comment", "")))

    # 保有銘柄テーブルとセクター集計
    holdings: dict[str, dict[str, Any]] = portfolio.get("holdings", {})
    holdings_rows_html: list[str] = []
    sector_totals: dict[str, float] = {}

    if holdings:
        for t, h in holdings.items():
            h_shares = int(h.get("shares", 0))
            h_sector = str(h.get("sector", "Other"))
            h_avg = float(h.get("avg_cost", 0.0))
            h_cur = float(h.get("current_price", 0.0))
            h_mv = float(h.get("market_value", h_shares * h_cur))
            h_pnl = float(h.get("unrealized_pnl", 0.0))
            h_pnl_pct = float(h.get("unrealized_pnl_pct", 0.0))
            h_weight = round((h_mv / total_equity) * 100.0, 1) if total_equity > 0 else 0.0

            sector_totals[h_sector] = round(sector_totals.get(h_sector, 0.0) + h_mv, 2)
            pnl_cls = "text-emerald-400" if h_pnl >= 0 else "text-rose-400"

            holdings_rows_html.append(
                f"""
                <tr class="border-b border-slate-800 hover:bg-slate-800/40 transition">
                    <td class="py-3 px-4 font-bold text-white">{html.escape(t)}</td>
                    <td class="py-3 px-4 text-slate-300 text-xs">{html.escape(h_sector)}</td>
                    <td class="py-3 px-4 text-right font-mono">{h_shares}株</td>
                    <td class="py-3 px-4 text-right font-mono">${h_avg:.2f}</td>
                    <td class="py-3 px-4 text-right font-mono">${h_cur:.2f}</td>
                    <td class="py-3 px-4 text-right font-mono font-semibold text-white">${h_mv:.2f}</td>
                    <td class="py-3 px-4 text-right font-mono {pnl_cls}">
                        {h_pnl:+.2f} ({h_pnl_pct:+.2f}%)
                    </td>
                    <td class="py-3 px-4 text-right font-mono text-slate-300">{h_weight:.1f}%</td>
                </tr>
                """
            )
    else:
        holdings_rows_html.append(
            """
            <tr>
                <td colspan="8" class="py-8 text-center text-slate-400">
                    現在保有している銘柄はありません（Cash 100% 温存中）
                </td>
            </tr>
            """
        )

    sector_totals["Cash (現金)"] = round(cash, 2)
    sector_labels_json = json.dumps(list(sector_totals.keys()), ensure_ascii=False)
    sector_values_json = json.dumps(list(sector_totals.values()))

    # 総資産推移データ
    asset_history: list[dict[str, Any]] = portfolio.get("asset_history", [])
    history_dates = [str(item.get("date", "")) for item in asset_history]
    history_equity = [float(item.get("total_equity", 0.0)) for item in asset_history]
    history_deposited = [float(item.get("total_deposited", 0.0)) for item in asset_history]

    history_dates_json = json.dumps(history_dates, ensure_ascii=False)
    history_equity_json = json.dumps(history_equity)
    history_deposited_json = json.dumps(history_deposited)

    # 売買履歴テーブル
    trade_rows_html: list[str] = []
    if trade_history:
        for row in trade_history:
            r_action = str(row.get("action", "HOLD")).upper()
            if r_action == "BUY":
                r_badge = '<span class="px-2 py-0.5 rounded text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">BUY</span>'
            elif r_action == "SELL":
                r_badge = '<span class="px-2 py-0.5 rounded text-xs font-bold bg-rose-500/20 text-emerald-300 border border-rose-500/30">SELL</span>'
            else:
                r_badge = '<span class="px-2 py-0.5 rounded text-xs font-bold bg-slate-600/30 text-slate-300 border border-slate-600/40">HOLD</span>'

            trade_rows_html.append(
                f"""
                <tr class="border-b border-slate-800 hover:bg-slate-800/40 transition text-sm">
                    <td class="py-3 px-4 font-mono text-slate-300">{html.escape(str(row.get('date', '')))}</td>
                    <td class="py-3 px-4">{r_badge}</td>
                    <td class="py-3 px-4 font-bold text-white">{html.escape(str(row.get('ticker', 'NONE')))}</td>
                    <td class="py-3 px-4 text-slate-400 text-xs">{html.escape(str(row.get('sector', '-')))}</td>
                    <td class="py-3 px-4 text-right font-mono">{html.escape(str(row.get('shares', '0')))}株</td>
                    <td class="py-3 px-4 text-right font-mono">${html.escape(str(row.get('price', '0.00')))}</td>
                    <td class="py-3 px-4 text-right font-mono font-semibold text-white">${html.escape(str(row.get('total_amount', '0.00')))}</td>
                    <td class="py-3 px-4 text-right font-mono text-slate-300">${html.escape(str(row.get('cash_after', '0.00')))}</td>
                    <td class="py-3 px-4 text-slate-300 text-xs">{html.escape(str(row.get('note', '')))}</td>
                </tr>
                """
            )
    else:
        trade_rows_html.append(
            """
            <tr>
                <td colspan="9" class="py-6 text-center text-slate-400">取引履歴はまだありません</td>
            </tr>
            """
        )

    html_content = f"""<!DOCTYPE html>
<html lang="ja" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Investment Firm | 朝刊ダッシュボード</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen font-sans antialiased">
    <!-- ヘッダーバー -->
    <header class="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-30">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div>
                <div class="flex items-center gap-2">
                    <span class="inline-block w-3 h-3 rounded-full bg-emerald-400 animate-pulse"></span>
                    <h1 class="text-xl sm:text-2xl font-extrabold tracking-tight text-white">
                        AI Investment Firm <span class="text-slate-400 font-normal text-base">Morning Brief</span>
                    </h1>
                </div>
                <p class="text-xs text-slate-400 mt-0.5">
                    米国株マルチAIエージェント仮想投資会社（SBI証券1株現物ルール準拠）
                </p>
            </div>
            <div class="text-left sm:text-right text-xs text-slate-400 font-mono">
                <div>対象米国市場取引日: <span class="text-slate-200 font-semibold">{market_date}</span></div>
                <div>最終更新日時: <span class="text-slate-200">{updated_at}</span></div>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-8">
        <!-- 1. サマリーヘッダーKPI -->
        <section class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                <p class="text-xs font-medium text-slate-400 uppercase tracking-wider">総資産額 (Total Equity)</p>
                <p class="text-2xl sm:text-3xl font-extrabold text-white mt-2 font-mono">${total_equity:.2f}</p>
                <p class="text-xs text-slate-400 mt-1">円換算目安: 約 ¥{jpy_total_equity:,} <span class="text-slate-500">(@150円/USD)</span></p>
            </div>
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                <p class="text-xs font-medium text-slate-400 uppercase tracking-wider">トータル損益 (Total Return)</p>
                <p class="text-2xl sm:text-3xl font-extrabold {return_color_class} mt-2 font-mono">
                    {return_sign}${total_return:.2f}
                </p>
                <p class="text-xs {return_color_class} mt-1 font-mono">
                    損益率: {return_sign}{total_return_pct:.2f}% (累計元本 ${total_deposited:.2f})
                </p>
            </div>
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                <p class="text-xs font-medium text-slate-400 uppercase tracking-wider">現在の現金残高 (Cash)</p>
                <p class="text-2xl sm:text-3xl font-extrabold text-sky-400 mt-2 font-mono">${cash:.2f}</p>
                <p class="text-xs text-slate-400 mt-1">約 ¥{jpy_cash:,} / キャッシュ比率 {cash_ratio_pct:.1f}%</p>
            </div>
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                <p class="text-xs font-medium text-slate-400 uppercase tracking-wider">保有株評価額 &amp; 積立状況</p>
                <p class="text-2xl sm:text-3xl font-extrabold text-indigo-400 mt-2 font-mono">${holdings_val:.2f}</p>
                <p class="text-xs text-slate-400 mt-1">保有銘柄数: {len(holdings)}銘柄 / 最終積立月: {html.escape(str(portfolio.get('last_deposit_month', '-')))}</p>
            </div>
        </section>

        <!-- 2. 本日の最終結論カード（最上部・強調表示） -->
        <section class="bg-slate-900/95 border-2 {card_border} rounded-2xl p-6 shadow-2xl">
            <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-800 pb-4">
                <div class="flex items-center gap-3">
                    <span class="px-4 py-1.5 rounded-full text-sm font-extrabold border {badge_bg}">
                        {action_label}
                    </span>
                    <div>
                        <h2 class="text-lg sm:text-xl font-bold text-white">本日のAI経営会議 最終結論</h2>
                        <p class="text-xs text-slate-400">{exec_note_str}</p>
                    </div>
                </div>
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 bg-slate-950/70 p-3 rounded-xl border border-slate-800 text-center">
                    <div>
                        <div class="text-[11px] text-slate-400">対象ティッカー</div>
                        <div class="text-base font-extrabold text-white font-mono">{ticker_str}</div>
                    </div>
                    <div>
                        <div class="text-[11px] text-slate-400">売買株数 (整数)</div>
                        <div class="text-base font-extrabold text-white font-mono">{shares_int} 株</div>
                    </div>
                    <div>
                        <div class="text-[11px] text-slate-400">現在株価 (終値)</div>
                        <div class="text-base font-extrabold text-white font-mono">${price_val:.2f}</div>
                    </div>
                    <div>
                        <div class="text-[11px] text-slate-400">合計金額</div>
                        <div class="text-base font-extrabold text-emerald-400 font-mono">${total_amount_val:.2f}</div>
                    </div>
                </div>
            </div>

            <!-- SBI証券での手動注文ガイドメモ -->
            <div class="mt-4 bg-indigo-950/40 border border-indigo-500/30 rounded-xl p-4">
                <div class="flex items-center gap-2 text-indigo-300 font-bold text-sm mb-1">
                    <span>📱 SBI証券（米国株アプリ/Web）手動注文操作ガイド</span>
                    <span class="text-xs font-normal text-indigo-400">（セクター: {sector_str}）</span>
                </div>
                <p class="text-sm text-slate-200 leading-relaxed whitespace-pre-line">{sbi_guide_str}</p>
            </div>
        </section>

        <!-- 3. 4体のAI社員の経営会議ルーム -->
        <section class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg">
            <h2 class="text-lg font-bold text-white mb-4 flex items-center gap-2">
                <span>💬 AI社員の朝刊経営会議ルーム</span>
                <span class="text-xs font-normal text-slate-400">（4エージェント合議ログ）</span>
            </h2>
            <div class="space-y-4">
                <!-- ① 情報収集担当 -->
                <div class="flex items-start gap-3.5">
                    <div class="w-11 h-11 rounded-full bg-sky-500/20 border border-sky-500/40 flex items-center justify-center text-xl shrink-0">
                        📰
                    </div>
                    <div class="flex-1 bg-slate-950 border border-slate-800 rounded-2xl rounded-tl-none p-4">
                        <div class="flex items-center gap-2 mb-1.5">
                            <span class="font-bold text-sm text-white">情報収集担当</span>
                            <span class="px-2 py-0.5 text-[11px] rounded bg-sky-500/20 text-sky-300 border border-sky-500/30 font-medium">
                                News Researcher
                            </span>
                        </div>
                        <p class="text-sm text-slate-300 leading-relaxed whitespace-pre-line">{researcher_text}</p>
                    </div>
                </div>

                <!-- ② テクニカル分析担当 -->
                <div class="flex items-start gap-3.5">
                    <div class="w-11 h-11 rounded-full bg-purple-500/20 border border-purple-500/40 flex items-center justify-center text-xl shrink-0">
                        📊
                    </div>
                    <div class="flex-1 bg-slate-950 border border-slate-800 rounded-2xl rounded-tl-none p-4">
                        <div class="flex items-center gap-2 mb-1.5">
                            <span class="font-bold text-sm text-white">テクニカル分析担当</span>
                            <span class="px-2 py-0.5 text-[11px] rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 font-medium">
                                Technical Analyst
                            </span>
                        </div>
                        <p class="text-sm text-slate-300 leading-relaxed whitespace-pre-line">{analyst_text}</p>
                    </div>
                </div>

                <!-- ③ ファンドマネージャー -->
                <div class="flex items-start gap-3.5">
                    <div class="w-11 h-11 rounded-full bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-xl shrink-0">
                        👑
                    </div>
                    <div class="flex-1 bg-slate-950 border border-amber-500/30 rounded-2xl rounded-tl-none p-4">
                        <div class="flex items-center gap-2 mb-1.5">
                            <span class="font-bold text-sm text-white">ファンドマネージャー</span>
                            <span class="px-2 py-0.5 text-[11px] rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 font-medium">
                                Fund Manager (最終意思決定)
                            </span>
                        </div>
                        <p class="text-sm text-slate-200 leading-relaxed whitespace-pre-line">{manager_text}</p>
                    </div>
                </div>

                <!-- ④ 執行・経理担当 -->
                <div class="flex items-start gap-3.5">
                    <div class="w-11 h-11 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-xl shrink-0">
                        🛡️
                    </div>
                    <div class="flex-1 bg-slate-950 border border-emerald-500/30 rounded-2xl rounded-tl-none p-4">
                        <div class="flex items-center gap-2 mb-1.5">
                            <span class="font-bold text-sm text-white">執行・経理担当</span>
                            <span class="px-2 py-0.5 text-[11px] rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-medium">
                                Execution &amp; Accounting (物理検証・記帳)
                            </span>
                        </div>
                        <p class="text-sm text-slate-200 leading-relaxed whitespace-pre-line">{accountant_text}</p>
                    </div>
                </div>
            </div>
        </section>

        <!-- 4. ポートフォリオ＆チャート -->
        <section class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <!-- セクター構成比ドーナツグラフ -->
            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg">
                <h3 class="text-base font-bold text-white mb-4">セクター構成比 (Cash含む)</h3>
                <div class="relative h-64 flex items-center justify-center">
                    <canvas id="sectorChart"></canvas>
                </div>
            </div>

            <!-- 総資産推移折れ線グラフ -->
            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg lg:col-span-2">
                <h3 class="text-base font-bold text-white mb-4">総資産推移 vs 累計入金額 (USD)</h3>
                <div class="relative h-64">
                    <canvas id="equityChart"></canvas>
                </div>
            </div>
        </section>

        <!-- 保有銘柄一覧テーブル -->
        <section class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg overflow-hidden">
            <h2 class="text-lg font-bold text-white mb-4">保有銘柄一覧 (Current Holdings)</h2>
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="border-b border-slate-700 text-xs uppercase text-slate-400">
                            <th class="py-3 px-4">ティッカー</th>
                            <th class="py-3 px-4">セクター</th>
                            <th class="py-3 px-4 text-right">保有株数</th>
                            <th class="py-3 px-4 text-right">平均取得単価</th>
                            <th class="py-3 px-4 text-right">現在株価</th>
                            <th class="py-3 px-4 text-right">評価額</th>
                            <th class="py-3 px-4 text-right">含み損益</th>
                            <th class="py-3 px-4 text-right">構成比</th>
                        </tr>
                    </thead>
                    <tbody class="text-sm">
                        {"".join(holdings_rows_html)}
                    </tbody>
                </table>
            </div>
        </section>

        <!-- 5. 売買履歴一覧テーブル -->
        <section class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg overflow-hidden">
            <h2 class="text-lg font-bold text-white mb-4">直近売買・執行履歴 (Trade History)</h2>
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="border-b border-slate-700 text-xs uppercase text-slate-400">
                            <th class="py-3 px-4">実行日</th>
                            <th class="py-3 px-4">アクション</th>
                            <th class="py-3 px-4">ティッカー</th>
                            <th class="py-3 px-4">セクター</th>
                            <th class="py-3 px-4 text-right">株数</th>
                            <th class="py-3 px-4 text-right">約定単価</th>
                            <th class="py-3 px-4 text-right">約定金額</th>
                            <th class="py-3 px-4 text-right">取引後現金</th>
                            <th class="py-3 px-4">執行メモ</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(trade_rows_html)}
                    </tbody>
                </table>
            </div>
        </section>
    </main>

    <footer class="border-t border-slate-800 py-6 mt-12 text-center text-xs text-slate-500">
        AI Investment Firm Simulation System — Powered by Python, yfinance &amp; Gemini 2.5 Flash
    </footer>

    <!-- Chart.js 描画スクリプト -->
    <script>
        const sectorLabels = {sector_labels_json};
        const sectorValues = {sector_values_json};

        const ctxSector = document.getElementById('sectorChart').getContext('2d');
        new Chart(ctxSector, {{
            type: 'doughnut',
            data: {{
                labels: sectorLabels,
                datasets: [{{
                    data: sectorValues,
                    backgroundColor: [
                        '#10b981', '#38bdf8', '#a855f7', '#f59e0b',
                        '#f43f5e', '#6366f1', '#14b8a6', '#64748b'
                    ],
                    borderColor: '#0f172a',
                    borderWidth: 2
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        position: 'bottom',
                        labels: {{ color: '#cbd5e1', font: {{ size: 11 }} }}
                    }}
                }}
            }}
        }});

        const historyDates = {history_dates_json};
        const historyEquity = {history_equity_json};
        const historyDeposited = {history_deposited_json};

        const ctxEquity = document.getElementById('equityChart').getContext('2d');
        new Chart(ctxEquity, {{
            type: 'line',
            data: {{
                labels: historyDates,
                datasets: [
                    {{
                        label: '総資産額 (Total Equity $)',
                        data: historyEquity,
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.15)',
                        fill: true,
                        tension: 0.25,
                        pointRadius: 4
                    }},
                    {{
                        label: '累計入金額 (Invested Capital $)',
                        data: historyDeposited,
                        borderColor: '#64748b',
                        borderDash: [5, 5],
                        fill: false,
                        tension: 0.1,
                        pointRadius: 2
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    x: {{
                        ticks: {{ color: '#94a3b8' }},
                        grid: {{ color: 'rgba(148, 163, 184, 0.1)' }}
                    }},
                    y: {{
                        ticks: {{ color: '#94a3b8' }},
                        grid: {{ color: 'rgba(148, 163, 184, 0.1)' }}
                    }}
                }},
                plugins: {{
                    legend: {{
                        labels: {{ color: '#cbd5e1' }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""
    with output_path.open("w", encoding="utf-8") as f:
        f.write(html_content)

    return output_path
