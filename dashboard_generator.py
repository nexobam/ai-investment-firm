"""
朝刊ダッシュボード画面生成モジュール（dashboard_generator.py -> docs/index.html）
Tailwind CSS（CDN）と Chart.js（CDN）を使用し、単一HTMLで美しく表示される
PC・スマートフォン対応レスポンシブUI（完全日本語表記・社長決裁ボタン付き）を生成する。
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from agents import MeetingDecision
from screener import FALLBACK_PRICES

USD_TO_JPY_RATE: float = 150.0

# 英語セクター名 -> 分かりやすい日本語業種名マップ
SECTOR_JA_MAP: dict[str, str] = {
    "Technology": "IT・半導体（テクノロジー）",
    "Financials": "銀行・金融",
    "Healthcare": "医療・製薬（ヘルスケア）",
    "Consumer Discretionary": "自動車・小売（一般消費財）",
    "Consumer Staples": "食品・日用品（生活必需品）",
    "Energy": "石油・エネルギー",
    "Industrials": "機械・重工・輸送",
    "Materials": "素材・資源・化学",
    "Utilities": "電力・インフラ（公益）",
    "Real Estate": "不動産・REIT",
    "Communication Services": "通信・ネットメディア",
    "Broad Market ETF": "米国株全体パック（ETF）",
    "Dividend ETF": "高配当株パック（ETF）",
    "Growth/Tech ETF": "ハイテク成長株パック（ETF）",
    "International ETF": "全世界株パック（ETF）",
    "Cash Deposit": "現金入金",
    "Other": "その他業種",
    "-": "取引なし（様子見）",
}

# ティッカー -> 日本語の会社名・銘柄名マップ
TICKER_NAME_JA_MAP: dict[str, str] = {
    "AAPL": "アップル",
    "MSFT": "マイクロソフト",
    "NVDA": "エヌビディア",
    "GOOGL": "グーグル（アルファベット）",
    "INTC": "インテル",
    "CSCO": "シスコシステムズ",
    "JPM": "JPモルガン・チェース",
    "BAC": "バンク・オブ・アメリカ",
    "WFC": "ウェルズ・ファーゴ",
    "C": "シティグループ",
    "SOFI": "ソーファイ・テクノロジーズ",
    "JNJ": "ジョンソン・エンド・ジョンソン",
    "PFE": "ファイザー",
    "MRK": "メルク",
    "ABBV": "アッヴィ",
    "BMY": "ブリストル・マイヤーズ",
    "AMZN": "アマゾン",
    "TSLA": "テスラ",
    "F": "フォード・モーター",
    "NKE": "ナイキ",
    "PG": "P&G（プロクター＆ギャンブル）",
    "KO": "コカ・コーラ",
    "PEP": "ペプシコ",
    "WMT": "ウォルマート",
    "KHC": "クラフト・ハインツ",
    "XOM": "エクソンモービル",
    "CVX": "シェブロン",
    "OXY": "オクシデンタル・ペトロリアム",
    "SLB": "シュルンベルジェ",
    "GE": "GEエアロスペース",
    "CAT": "キャタピラー",
    "BA": "ボーイング",
    "CSX": "CSX（鉄道輸送）",
    "FCX": "フリーポート・マクモラン",
    "NEM": "ニューモント（金鉱株）",
    "DOW": "ダウ・ケミカル",
    "NEE": "ネクステラ・エナジー",
    "SO": "サザン（電力）",
    "AES": "AES（電力）",
    "PLD": "プロロジス（物流不動産）",
    "O": "リアルティ・インカム（毎月配当REIT）",
    "VICI": "VICIプロパティーズ（REIT）",
    "META": "メタ（旧フェイスブック）",
    "VZ": "ベライゾン（通信）",
    "T": "AT&T（通信）",
    "SPYM": "S&P500連動 米国株ETF",
    "SCHD": "米国高配当株ETF",
    "QQQM": "ナスダック100連動ETF",
    "VXUS": "米国除く全世界株ETF",
    "VTI": "全米株式まるごとETF",
    "CASH": "現金（ドル）",
    "NONE": "対象なし（様子見）",
}


def to_sector_ja(sector: str) -> str:
    return SECTOR_JA_MAP.get(sector, sector)


def to_ticker_display(ticker: str) -> str:
    t = (ticker or "NONE").upper().strip()
    ja_name = TICKER_NAME_JA_MAP.get(t)
    if ja_name and t not in ("NONE", "CASH"):
        return f"{t}（{ja_name}）"
    if t == "CASH":
        return "現金入金"
    if t == "NONE":
        return "なし（見送り）"
    return t


def _get_rpg_avatar_svg(role: str) -> str:
    """
    ドラクエ・レトロRPG風の可愛いドット絵（16x16ピクセルアート）人形アイコンSVGを返す。
    """
    if role == "researcher":
        # ① ニュース調査担当：羽根つき帽子＆巻物を持った可愛い吟遊詩人・情報屋キャラ
        return """
        <svg viewBox="0 0 16 16" class="w-12 h-12 rpg-pixel-doll" shape-rendering="crispEdges">
            <!-- 白い羽根飾り -->
            <rect x="10" y="0" width="2" height="1" fill="#ffffff"/>
            <rect x="11" y="1" width="2" height="1" fill="#e2e8f0"/>
            <!-- 青い冒険者ベレー帽 -->
            <rect x="4" y="1" width="6" height="1" fill="#0284c7"/>
            <rect x="3" y="2" width="9" height="2" fill="#38bdf8"/>
            <rect x="3" y="4" width="10" height="1" fill="#0369a1"/>
            <rect x="7" y="3" width="2" height="1" fill="#fbbf24"/>
            <!-- 髪と可愛い顔 -->
            <rect x="3" y="5" width="2" height="3" fill="#92400e"/>
            <rect x="11" y="5" width="2" height="3" fill="#92400e"/>
            <rect x="5" y="5" width="6" height="4" fill="#fde68a"/>
            <!-- キラキラの目とピンクのほっぺ -->
            <rect x="6" y="6" width="1" height="2" fill="#0f172a"/>
            <rect x="9" y="6" width="1" height="2" fill="#0f172a"/>
            <rect x="6" y="6" width="1" height="1" fill="#ffffff"/>
            <rect x="9" y="6" width="1" height="1" fill="#ffffff"/>
            <rect x="5" y="7" width="1" height="1" fill="#fb7185"/>
            <rect x="10" y="7" width="1" height="1" fill="#fb7185"/>
            <rect x="7" y="8" width="2" height="1" fill="#f43f5e"/>
            <!-- 水色の旅人マントと服 -->
            <rect x="4" y="9" width="8" height="4" fill="#0ea5e9"/>
            <rect x="6" y="9" width="4" height="1" fill="#fef08a"/>
            <rect x="5" y="10" width="6" height="2" fill="#0284c7"/>
            <!-- 手に持ったニュースの巻物 -->
            <rect x="11" y="9" width="3" height="3" fill="#fef3c7"/>
            <rect x="11" y="10" width="3" height="1" fill="#d97706"/>
            <!-- ブーツ -->
            <rect x="5" y="13" width="2" height="2" fill="#78350f"/>
            <rect x="9" y="13" width="2" height="2" fill="#78350f"/>
        </svg>
        """
    if role == "analyst":
        # ② チャート・数値分析担当：とんがり帽子＆光る水晶玉を持った可愛い魔法使い・賢者キャラ
        return """
        <svg viewBox="0 0 16 16" class="w-12 h-12 rpg-pixel-doll" shape-rendering="crispEdges">
            <!-- とんがり魔法使い帽子 -->
            <rect x="7" y="0" width="2" height="1" fill="#7e22ce"/>
            <rect x="6" y="1" width="4" height="1" fill="#9333ea"/>
            <rect x="5" y="2" width="6" height="2" fill="#a855f7"/>
            <rect x="4" y="3" width="8" height="1" fill="#fbbf24"/>
            <rect x="2" y="4" width="12" height="1" fill="#6b21a8"/>
            <!-- 銀髪と可愛い顔 -->
            <rect x="3" y="5" width="2" height="4" fill="#e2e8f0"/>
            <rect x="11" y="5" width="2" height="4" fill="#e2e8f0"/>
            <rect x="5" y="5" width="6" height="4" fill="#fde68a"/>
            <!-- 知的なメガネ＆目・ほっぺ -->
            <rect x="5" y="6" width="2" height="2" fill="#38bdf8"/>
            <rect x="9" y="6" width="2" height="2" fill="#38bdf8"/>
            <rect x="6" y="6" width="1" height="2" fill="#0f172a"/>
            <rect x="9" y="6" width="1" height="2" fill="#0f172a"/>
            <rect x="7" y="6" width="2" height="1" fill="#cbd5e1"/>
            <rect x="5" y="8" width="1" height="1" fill="#fb7185"/>
            <rect x="10" y="8" width="1" height="1" fill="#fb7185"/>
            <!-- 紫の賢者ローブ -->
            <rect x="4" y="9" width="8" height="4" fill="#9333ea"/>
            <rect x="7" y="9" width="2" height="4" fill="#fbbf24"/>
            <!-- 光るチャート水晶玉 -->
            <rect x="11" y="9" width="3" height="3" fill="#22d3ee"/>
            <rect x="12" y="9" width="1" height="1" fill="#ffffff"/>
            <!-- 靴 -->
            <rect x="5" y="13" width="2" height="2" fill="#581c87"/>
            <rect x="9" y="13" width="2" height="2" fill="#581c87"/>
        </svg>
        """
    if role == "manager":
        # ③ ファンドマネージャー：金の王冠＆赤いマント＆黄金の剣を持った可愛い勇者・王様キャラ
        return """
        <svg viewBox="0 0 16 16" class="w-12 h-12 rpg-pixel-doll" shape-rendering="crispEdges">
            <!-- 黄金の王冠とルビー -->
            <rect x="4" y="1" width="1" height="1" fill="#fbbf24"/>
            <rect x="7" y="0" width="2" height="2" fill="#fbbf24"/>
            <rect x="11" y="1" width="1" height="1" fill="#fbbf24"/>
            <rect x="4" y="2" width="8" height="2" fill="#f59e0b"/>
            <rect x="7" y="2" width="2" height="1" fill="#f43f5e"/>
            <!-- 勇者の髪と可愛い顔 -->
            <rect x="3" y="4" width="10" height="1" fill="#b45309"/>
            <rect x="3" y="5" width="2" height="3" fill="#b45309"/>
            <rect x="11" y="5" width="2" height="3" fill="#b45309"/>
            <rect x="5" y="5" width="6" height="4" fill="#fde68a"/>
            <!-- キリッとした目とピンクのほっぺ -->
            <rect x="6" y="6" width="1" height="2" fill="#0f172a"/>
            <rect x="9" y="6" width="1" height="2" fill="#0f172a"/>
            <rect x="6" y="6" width="1" height="1" fill="#ffffff"/>
            <rect x="9" y="6" width="1" height="1" fill="#ffffff"/>
            <rect x="5" y="7" width="1" height="1" fill="#fb7185"/>
            <rect x="10" y="7" width="1" height="1" fill="#fb7185"/>
            <rect x="7" y="8" width="2" height="1" fill="#ef4444"/>
            <!-- 王様の赤いマントと黄金アーマー -->
            <rect x="3" y="9" width="10" height="4" fill="#e11d48"/>
            <rect x="5" y="9" width="6" height="4" fill="#fbbf24"/>
            <rect x="6" y="10" width="4" height="2" fill="#2563eb"/>
            <!-- 黄金の指揮剣 -->
            <rect x="13" y="6" width="1" height="4" fill="#fef08a"/>
            <rect x="12" y="9" width="3" height="1" fill="#f59e0b"/>
            <!-- ブーツ -->
            <rect x="5" y="13" width="2" height="2" fill="#92400e"/>
            <rect x="9" y="13" width="2" height="2" fill="#92400e"/>
        </svg>
        """
    # ④ 資金・ルール管理担当：エメラルドの兜＆大きな盾を持った可愛い重装ナイト・パラディンキャラ
    return """
    <svg viewBox="0 0 16 16" class="w-12 h-12 rpg-pixel-doll" shape-rendering="crispEdges">
        <!-- ナイトの羽根飾り＆エメラルド兜 -->
        <rect x="7" y="0" width="2" height="2" fill="#10b981"/>
        <rect x="4" y="2" width="8" height="2" fill="#cbd5e1"/>
        <rect x="3" y="4" width="10" height="1" fill="#94a3b8"/>
        <rect x="7" y="3" width="2" height="1" fill="#10b981"/>
        <!-- 兜から覗く可愛い顔 -->
        <rect x="3" y="5" width="2" height="4" fill="#64748b"/>
        <rect x="11" y="5" width="2" height="4" fill="#64748b"/>
        <rect x="5" y="5" width="6" height="4" fill="#fde68a"/>
        <rect x="6" y="6" width="1" height="2" fill="#0f172a"/>
        <rect x="9" y="6" width="1" height="2" fill="#0f172a"/>
        <rect x="6" y="6" width="1" height="1" fill="#ffffff"/>
        <rect x="9" y="6" width="1" height="1" fill="#ffffff"/>
        <rect x="5" y="7" width="1" height="1" fill="#fb7185"/>
        <rect x="10" y="7" width="1" height="1" fill="#fb7185"/>
        <!-- エメラルド＆シルバーの鎧 -->
        <rect x="4" y="9" width="8" height="4" fill="#10b981"/>
        <rect x="5" y="9" width="6" height="3" fill="#e2e8f0"/>
        <rect x="7" y="10" width="2" height="2" fill="#059669"/>
        <!-- 鉄壁のガード盾 -->
        <rect x="1" y="8" width="4" height="5" fill="#fbbf24"/>
        <rect x="2" y="9" width="2" height="3" fill="#059669"/>
        <!-- 鎧ブーツ -->
        <rect x="5" y="13" width="2" height="2" fill="#475569"/>
        <rect x="9" y="13" width="2" height="2" fill="#475569"/>
    </svg>
    """


def _analyze_agent_condition(
    role: str,
    comment_raw: str,
    display_action: str,
    ticker_ja: str,
) -> dict[str, Any]:
    """
    長い文章を読まなくても「好調（チャンス）」「普通（様子見）」「不調（警戒）」が
    アイコンと1行要約で直感的にわかるよう、各社員のコンディション情報を生成する。
    """
    text = (comment_raw or "").strip()
    is_mock = "[Mock]" in text or "APIキー未設定" in text

    # 判定ロジック
    if is_mock:
        state = "normal"
    elif role == "researcher":
        if any(w in text for w in ["好調", "期待", "強力", "過剰反応", "追い風", "成長", "堅調", "ポジティブ", "買い"]) or display_action == "BUY":
            state = "good"
        elif any(w in text for w in ["悪化", "暴落", "懸念", "危険", "売り圧力", "下落リスク", "警戒", "ネガティブ"]) and display_action != "BUY":
            state = "bad"
        else:
            state = "normal"
    elif role == "analyst":
        if any(w in text for w in ["最適", "売られすぎ", "押し目", "反発", "割安", "買い場", "上昇", "好機"]) or display_action == "BUY":
            state = "good"
        elif any(w in text for w in ["買われすぎ", "過熱", "下落トレンド", "危険", "割高", "警戒", "崩れ"]) or display_action == "SELL":
            state = "bad"
        else:
            state = "normal"
    elif role == "manager":
        if display_action == "BUY":
            state = "good"
        elif display_action == "SELL":
            state = "bad"
        else:
            state = "normal"
    else:
        # accountant (経理・リスク管理)
        if any(w in text for w in ["違反", "不足", "却下", "フォールバック", "超過", "エラー", "不可"]):
            state = "bad"
        elif any(w in text for w in ["クリア", "検証OK", "買付", "成功", "承認"]) or display_action == "BUY":
            state = "good"
        else:
            state = "normal"

    # 状態ごとの見た目＆1行超要約テキスト
    if state == "good":
        summaries = {
            "researcher": f"「ニュース面は好調！{ticker_ja}の将来性に期待できる明るい状況です✨」",
            "analyst": "「チャートにお買い得サイン点灯！今から反発が狙える絶好調な買い場です📈」",
            "manager": f"「今は攻めるチャンス！自信を持って『{ticker_ja}』の購入を提案します👑」",
            "accountant": "「予算も安全ルールも100点クリア！安心して決定ボタンを押せます🛡️」",
        }
        return {
            "state": "good",
            "label": "🌞 好調（買いチャンス！）" if role != "accountant" else "🌞 好調（ルール合格！）",
            "short_label": "🌞 好調！",
            "face_icon": "😆✨",
            "gauge_pct": 92,
            "badge_cls": "bg-emerald-500/25 text-emerald-200 border-emerald-400/60 shadow-[0_0_12px_rgba(16,185,129,0.3)]",
            "card_cls": "border-emerald-500/50 bg-gradient-to-br from-slate-950 via-slate-950 to-emerald-950/30",
            "bar_cls": "bg-gradient-to-r from-emerald-500 to-teal-300",
            "summary_box_cls": "bg-emerald-950/50 border-emerald-500/40 text-emerald-200",
            "summary_ja": summaries.get(role, "「状況は好調です！」"),
        }

    if state == "bad":
        summaries = {
            "researcher": "「ちょっと嫌なニュースが多めの不調ムード…今は無理せず警戒が必要です💦」",
            "analyst": "「株価チャートが危険水域（過熱または下落中）…今は手出し注意です⚠️」",
            "manager": "「リスクが高い不調相場のため、売却または厳重な守りを提案します🚨」",
            "accountant": "「予算オーバーまたは35%集中投資ルール違反のため、安全装置でストップしました🛑」",
        }
        return {
            "state": "bad",
            "label": "🌧️ 不調（警戒・ストップ）",
            "short_label": "🌧️ 不調…",
            "face_icon": "💦⚠️",
            "gauge_pct": 25,
            "badge_cls": "bg-rose-500/25 text-rose-200 border-rose-400/60 shadow-[0_0_12px_rgba(244,63,94,0.3)]",
            "card_cls": "border-rose-500/50 bg-gradient-to-br from-slate-950 via-slate-950 to-rose-950/30",
            "bar_cls": "bg-gradient-to-r from-rose-600 to-orange-400",
            "summary_box_cls": "bg-rose-950/50 border-rose-500/40 text-rose-200",
            "summary_ja": summaries.get(role, "「今は警戒モードです」"),
        }

    summaries = {
        "researcher": "「良いニュースと悪いニュースが半々の『普通』の状況。焦らず見守り中です🍵」",
        "analyst": "「株価は高すぎず安すぎずの普通水準。無理に買わず次のチャンス待ちです📊」",
        "manager": "「今は無理に動かず、現金を温存して様子を見る（キープ）のが一番安全です✋」",
        "accountant": "「現金は100%安全にキープ中！無駄遣いせずガッチリお財布を守っています💰」",
    }
    return {
        "state": "normal",
        "label": "⛅ 普通（様子見モード）",
        "short_label": "⛅ 普通",
        "face_icon": "🙂🍵",
        "gauge_pct": 58,
        "badge_cls": "bg-amber-500/20 text-amber-200 border-amber-400/50",
        "card_cls": "border-slate-700 bg-slate-950",
        "bar_cls": "bg-gradient-to-r from-amber-400 to-sky-400",
        "summary_box_cls": "bg-slate-900/90 border-slate-700 text-amber-200",
        "summary_ja": summaries.get(role, "「現在は様子見モードです」"),
    }


def generate_dashboard(
    portfolio: dict[str, Any],
    decision: MeetingDecision,
    execution_result: dict[str, Any],
    trade_history: list[dict[str, str]],
    output_path: Path,
) -> Path:
    """
    最新のポートフォリオ状態、AI会議結果、執行結果、売買履歴から
    完全日本語表記・社長決裁ボタン付きの docs/index.html を生成して保存する。
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

    # AI提案アクションと実際の執行状態を確認
    # 提案モード（社長の決定待ち）の場合は requested_action または decision.action を強調表示する
    is_proposal_pending = bool(
        execution_result.get("is_proposal_only", False)
        or execution_result.get("proposal_only", False)
    )
    display_action = (
        str(decision.action or "HOLD").upper()
        if is_proposal_pending
        else str(execution_result.get("action", execution_result.get("executed_action", "HOLD"))).upper()
    )
    raw_ticker = (
        str(decision.ticker or "NONE").upper()
        if is_proposal_pending
        else str(execution_result.get("ticker", "NONE")).upper()
    )
    shares_int = (
        int(decision.shares or 0)
        if is_proposal_pending
        else int(execution_result.get("shares", 0))
    )
    price_val = float(
        execution_result.get("proposal_price", execution_result.get("price", 0.0))
    )
    total_amount_val = round(price_val * shares_int, 2) if shares_int > 0 else float(execution_result.get("total_amount", 0.0))

    raw_sector = str(execution_result.get("proposal_sector", execution_result.get("sector", "-")))
    sector_ja_str = html.escape(to_sector_ja(raw_sector))
    ticker_display_str = html.escape(to_ticker_display(raw_ticker))
    raw_ticker_escaped = html.escape(raw_ticker)

    if display_action == "BUY":
        badge_bg = "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
        card_border = "border-emerald-500/50"
        action_label = "BUY（現物買付の提案）" if is_proposal_pending else "BUY（現物買付）"
    elif display_action == "SELL":
        badge_bg = "bg-rose-500/20 text-rose-300 border-rose-500/40"
        card_border = "border-rose-500/50"
        action_label = "SELL（現物売却の提案）" if is_proposal_pending else "SELL（現物売却）"
    else:
        badge_bg = "bg-slate-500/20 text-slate-300 border-slate-500/40"
        card_border = "border-slate-600/60"
        action_label = "HOLD（現金温存・見送り）"

    exec_note_str = html.escape(
        str(execution_result.get("note") or execution_result.get("execution_note") or "")
    )
    sbi_guide_str = html.escape(decision.sbi_order_guide or "本日の注文はありません。")

    # 全銘柄の参照株価マップ（フロントエンドでの自動計算＆ワンクリック銘柄選択用）
    known_prices: dict[str, float] = {k: float(v) for k, v in FALLBACK_PRICES.items()}
    for k, v in (execution_result.get("all_prices") or {}).items():
        if float(v or 0.0) > 0:
            known_prices[str(k).upper()] = round(float(v), 2)
    for c in (execution_result.get("candidates") or []):
        c_tkr = str(c.get("ticker", "")).upper()
        c_prc = float(c.get("price", c.get("close", 0.0)) or 0.0)
        if c_tkr and c_prc > 0:
            known_prices[c_tkr] = round(c_prc, 2)
    for t_held, h_held in (portfolio.get("holdings") or {}).items():
        h_prc = float(h_held.get("current_price", h_held.get("avg_cost", 0.0)) or 0.0)
        if h_prc > 0:
            known_prices[str(t_held).upper()] = round(h_prc, 2)
    if raw_ticker not in ("NONE", "CASH", "") and price_val > 0:
        known_prices[raw_ticker] = round(price_val, 2)

    # AIの追加提案＋一次スクリーニング上位候補（複数銘柄まとめ買い・比較用リスト）
    multi_candidates: list[dict[str, Any]] = []
    seen_multi: set[str] = set()
    if display_action in ("BUY", "SELL") and raw_ticker not in ("NONE", "CASH", "") and shares_int >= 1:
        seen_multi.add(raw_ticker)
        multi_candidates.append(
            {
                "action": display_action,
                "ticker": raw_ticker,
                "name_ja": to_ticker_display(raw_ticker),
                "shares": shares_int,
                "price": price_val,
                "reason": "👑 AI第1提案（メイン推奨）",
                "checked": True,
            }
        )
    for sub in getattr(decision, "additional_proposals", []) or []:
        s_tkr = str(getattr(sub, "ticker", "") or "").upper().strip()
        s_act = str(getattr(sub, "action", "BUY") or "BUY").upper().strip()
        s_sh = max(1, int(getattr(sub, "shares", 1) or 1))
        if s_tkr and s_tkr not in ("NONE", "CASH") and s_tkr not in seen_multi:
            s_prc = known_prices.get(s_tkr, 50.0)
            seen_multi.add(s_tkr)
            multi_candidates.append(
                {
                    "action": s_act if s_act in ("BUY", "SELL") else "BUY",
                    "ticker": s_tkr,
                    "name_ja": to_ticker_display(s_tkr),
                    "shares": s_sh,
                    "price": s_prc,
                    "reason": str(getattr(sub, "reason_short", "") or "✨ AI同時おすすめ候補"),
                    "checked": False,
                }
            )
    for c in (execution_result.get("candidates") or [])[:5]:
        c_tkr = str(c.get("ticker", "")).upper().strip()
        if c_tkr and c_tkr not in seen_multi:
            c_prc = round(float(c.get("price", c.get("close", known_prices.get(c_tkr, 50.0)))), 2)
            seen_multi.add(c_tkr)
            multi_candidates.append(
                {
                    "action": "BUY",
                    "ticker": c_tkr,
                    "name_ja": to_ticker_display(c_tkr),
                    "shares": 1,
                    "price": c_prc,
                    "reason": f"📊 スクリーニング上位（RSI {float(c.get('rsi_14', 50.0)):.1f}）",
                    "checked": False,
                }
            )

    # 社長決裁エリア（株数の自由変更ステッパー ＆ 複数銘柄まとめて一括決定機能付き）
    approval_button_html = ""
    if display_action in ("BUY", "SELL") and raw_ticker not in ("NONE", "CASH", "") and shares_int >= 1:
        btn_color = "bg-emerald-600 hover:bg-emerald-500 shadow-emerald-900/50" if display_action == "BUY" else "bg-rose-600 hover:bg-rose-500 shadow-rose-900/50"
        act_word = "買付" if display_action == "BUY" else "売却"

        multi_rows_html = ""
        for idx, mc in enumerate(multi_candidates[:4]):
            mc_tkr = html.escape(mc["ticker"])
            mc_name = html.escape(mc["name_ja"])
            mc_act = html.escape(mc["action"])
            mc_sh = int(mc["shares"])
            mc_prc = float(mc["price"])
            mc_reason = html.escape(mc["reason"])
            mc_chk = "checked" if mc["checked"] else ""
            act_pill = (
                '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">買い</span>'
                if mc_act == "BUY"
                else '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">売り</span>'
            )
            multi_rows_html += f"""
            <div class="flex flex-wrap items-center justify-between gap-2 p-2.5 rounded-xl bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition">
                <label class="flex items-center gap-2.5 cursor-pointer select-none min-w-0 flex-1">
                    <input type="checkbox" class="multi-prop-check w-4 h-4 rounded bg-slate-950 border-slate-600 text-emerald-500 focus:ring-0"
                        data-idx="{idx}" data-action="{mc_act}" data-ticker="{mc_tkr}" data-price="{mc_prc:.2f}" onchange="updateMultiProposalSummary()" {mc_chk}>
                    {act_pill}
                    <span class="font-bold text-xs sm:text-sm text-white truncate">{mc_name}</span>
                    <span class="text-[11px] text-slate-400 hidden sm:inline">（{mc_reason}）</span>
                </label>
                <div class="flex items-center gap-2 shrink-0">
                    <span class="text-xs font-mono text-slate-300">${mc_prc:.2f}/株</span>
                    <div class="flex items-center bg-slate-950 border border-slate-700 rounded-lg overflow-hidden">
                        <button type="button" onclick="stepMultiShare({idx}, -1)" class="px-2 py-1 text-xs font-bold text-slate-300 hover:bg-slate-800">−</button>
                        <input type="number" id="multiPropShares_{idx}" value="{mc_sh}" min="1" step="1" onchange="updateMultiProposalSummary()"
                            class="w-11 text-center bg-transparent text-white text-xs font-mono font-bold focus:outline-none">
                        <button type="button" onclick="stepMultiShare({idx}, 1)" class="px-2 py-1 text-xs font-bold text-slate-300 hover:bg-slate-800">＋</button>
                    </div>
                    <span id="multiPropSub_{idx}" class="text-xs font-mono font-bold text-emerald-400 w-16 text-right">${mc_prc * mc_sh:.2f}</span>
                </div>
            </div>
            """

        approval_button_html = f"""
        <div class="mt-4 pt-4 border-t border-slate-800 space-y-4">
            <!-- 1銘柄でも複数株（2株・3株）にすぐ変更して決定できるメインバー -->
            <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3 bg-slate-950/80 p-3.5 rounded-2xl border border-emerald-500/30">
                <div class="text-xs text-amber-300 font-medium">
                    👑 <b>社長の最終決定（株数の変更・複数株買いもOK）：</b><br>
                    <span class="text-slate-300">1株だけでなく「− / ＋」で2株・3株に増やして決定したり、下のリストから複数銘柄をまとめて決定できます！</span>
                </div>
                <div class="flex flex-wrap items-center gap-2.5 shrink-0">
                    <div class="flex items-center gap-1.5 bg-slate-900 border border-slate-700 rounded-xl px-2.5 py-1.5">
                        <span class="text-[11px] text-slate-400">株数:</span>
                        <button type="button" onclick="adjustMainProposalShares(-1, {price_val:.2f})" class="w-6 h-6 rounded bg-slate-800 hover:bg-slate-700 text-white font-bold text-xs">−</button>
                        <input type="number" id="mainProposalSharesInput" value="{shares_int}" min="1" step="1"
                            onchange="adjustMainProposalShares(0, {price_val:.2f})"
                            class="w-12 text-center bg-transparent text-white font-mono font-extrabold text-sm focus:outline-none">
                        <button type="button" onclick="adjustMainProposalShares(1, {price_val:.2f})" class="w-6 h-6 rounded bg-slate-800 hover:bg-slate-700 text-white font-bold text-xs">＋</button>
                        <span class="text-xs text-slate-300">株</span>
                    </div>
                    <button type="button" onclick="approveMainProposalWithCustomShares('{display_action}', '{raw_ticker_escaped}', {price_val:.2f})"
                        class="{btn_color} text-white font-extrabold text-xs sm:text-sm px-4 py-2.5 rounded-xl shadow-lg transition flex items-center justify-center gap-2">
                        <span id="mainProposalApproveBtnText">✅ このAI提案を決定（{raw_ticker_escaped} {shares_int}株 = ${total_amount_val:.2f}）</span>
                    </button>
                </div>
            </div>

            <!-- 複数銘柄の同時選択・まとめ買いボックス -->
            <div class="bg-slate-950/60 border border-slate-800 rounded-2xl p-4">
                <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-2.5">
                    <div class="text-xs font-bold text-sky-300 flex items-center gap-1.5">
                        <span>🧺 複数銘柄・複数株をまとめて決定したい場合（チェックを入れて一括反映）</span>
                    </div>
                    <div id="multiProposalTotalBadge" class="text-xs font-mono text-emerald-300 font-bold">
                        選択中: 1銘柄（合計 ${total_amount_val:.2f} / 残り現金目安 ${max(0.0, cash - total_amount_val):.2f}）
                    </div>
                </div>
                <div class="space-y-2 mb-3">
                    {multi_rows_html}
                </div>
                <div class="flex justify-end">
                    <button type="button" onclick="approveSelectedMultiProposals()"
                        class="bg-sky-600 hover:bg-sky-500 text-white font-bold text-xs px-4 py-2 rounded-xl shadow transition flex items-center gap-1.5">
                        <span>✅ チェックした銘柄・株数をまとめて口座データに反映する</span>
                    </button>
                </div>
            </div>
        </div>
        """

    # 4体のAI社員コメント＆ドラクエ風ドット絵アイコン＆好調・普通・不調ステータス判定
    raw_accountant_comment = str(
        execution_result.get("accountant_comment")
        or execution_result.get("executor_comment")
        or ""
    )
    researcher_text = html.escape(decision.researcher_comment)
    analyst_text = html.escape(decision.analyst_comment)
    manager_text = html.escape(decision.manager_reason)
    accountant_text = html.escape(raw_accountant_comment)

    svg_researcher = _get_rpg_avatar_svg("researcher")
    svg_analyst = _get_rpg_avatar_svg("analyst")
    svg_manager = _get_rpg_avatar_svg("manager")
    svg_accountant = _get_rpg_avatar_svg("accountant")

    cond_researcher = _analyze_agent_condition("researcher", decision.researcher_comment, display_action, ticker_display_str)
    cond_analyst = _analyze_agent_condition("analyst", decision.analyst_comment, display_action, ticker_display_str)
    cond_manager = _analyze_agent_condition("manager", decision.manager_reason, display_action, ticker_display_str)
    cond_accountant = _analyze_agent_condition("accountant", raw_accountant_comment, display_action, ticker_display_str)

    # 保有銘柄テーブルと日本語セクター集計
    holdings: dict[str, dict[str, Any]] = portfolio.get("holdings", {})
    holdings_rows_html: list[str] = []
    sector_totals: dict[str, float] = {}

    if holdings:
        for t, h in holdings.items():
            h_shares = int(h.get("shares", 0))
            h_sector_raw = str(h.get("sector", "Other"))
            h_sector_ja = to_sector_ja(h_sector_raw)
            h_avg = float(h.get("avg_cost", 0.0))
            h_cur = float(h.get("current_price", 0.0))
            h_mv = float(h.get("market_value", h_shares * h_cur))
            h_pnl = float(h.get("unrealized_pnl", 0.0))
            h_pnl_pct = float(h.get("unrealized_pnl_pct", 0.0))
            h_weight = round((h_mv / total_equity) * 100.0, 1) if total_equity > 0 else 0.0

            sector_totals[h_sector_ja] = round(sector_totals.get(h_sector_ja, 0.0) + h_mv, 2)
            pnl_cls = "text-emerald-400" if h_pnl >= 0 else "text-rose-400"

            holdings_rows_html.append(
                f"""
                <tr class="border-b border-slate-800 hover:bg-slate-800/40 transition">
                    <td class="py-3 px-4 font-bold text-white">{html.escape(to_ticker_display(t))}</td>
                    <td class="py-3 px-4 text-slate-300 text-xs">{html.escape(h_sector_ja)}</td>
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
                    現在持っている株はありません（全額 現金で温存中）
                </td>
            </tr>
            """
        )

    sector_totals["使える現金（ドル）"] = round(cash, 2)
    sector_labels_json = json.dumps(list(sector_totals.keys()), ensure_ascii=False)
    sector_values_json = json.dumps(list(sector_totals.values()))

    # ワンクリック銘柄選択ボタン＆プルダウン生成（キーボード入力不要で選べるUI用）
    quick_buy_tickers: list[str] = []
    for mc in multi_candidates:
        if mc["ticker"] not in quick_buy_tickers:
            quick_buy_tickers.append(mc["ticker"])
    for default_tkr in ["SCHD", "SPYM", "KO", "NVDA", "OXY", "KHC", "QQQM", "VXUS"]:
        if default_tkr not in quick_buy_tickers:
            quick_buy_tickers.append(default_tkr)

    quick_buy_chips_list: list[str] = []
    for qt in quick_buy_tickers[:8]:
        q_prc = known_prices.get(qt, 50.0)
        q_disp = html.escape(to_ticker_display(qt))
        quick_buy_chips_list.append(
            f'<button type="button" onclick="selectQuickTicker(\'{html.escape(qt)}\', {q_prc:.2f}, 1)" '
            f'class="px-2.5 py-1 rounded-lg text-[11px] font-bold bg-slate-800 hover:bg-emerald-900/60 text-slate-200 hover:text-emerald-200 border border-slate-700 hover:border-emerald-500/50 transition">'
            f'{q_disp} <span class="text-emerald-400 font-mono">${q_prc:.2f}</span></button>'
        )
    quick_buy_chips_html = "\n".join(quick_buy_chips_list)

    quick_sell_chips_list: list[str] = []
    held_shares_map: dict[str, int] = {}
    if holdings:
        for ht, hh in holdings.items():
            h_sh = int(hh.get("shares", 0))
            held_shares_map[ht] = h_sh
            h_prc = float(hh.get("current_price", hh.get("avg_cost", known_prices.get(ht, 50.0))))
            h_disp = html.escape(to_ticker_display(ht))
            quick_sell_chips_list.append(
                f'<button type="button" onclick="selectQuickTicker(\'{html.escape(ht)}\', {h_prc:.2f}, {h_sh})" '
                f'class="px-2.5 py-1.5 rounded-lg text-xs font-bold bg-rose-950/60 hover:bg-rose-900/80 text-rose-200 border border-rose-500/40 transition">'
                f'💼 {h_disp}（保有:{h_sh}株 @ ${h_prc:.2f}）を選ぶ</button>'
            )
    else:
        quick_sell_chips_list.append(
            '<span class="text-xs text-slate-400">※ 現在保有している株はありません</span>'
        )
    quick_sell_chips_html = "\n".join(quick_sell_chips_list)

    universe_options_list: list[str] = [
        '<option value="">▼ ここをクリックして全55銘柄の一覧から選ぶ（入力不要）</option>'
    ]
    for t_code, t_ja in TICKER_NAME_JA_MAP.items():
        if t_code in ("CASH", "NONE"):
            continue
        t_prc = known_prices.get(t_code, 0.0)
        prc_str = f"（目安 ${t_prc:.2f}）" if t_prc > 0 else ""
        universe_options_list.append(
            f'<option value="{html.escape(t_code)}">{html.escape(t_code)}：{html.escape(t_ja)}{prc_str}</option>'
        )
    universe_select_options_html = "\n".join(universe_options_list)

    known_prices_json = json.dumps(known_prices)
    held_shares_json = json.dumps(held_shares_map)
    ticker_ja_json = json.dumps(TICKER_NAME_JA_MAP, ensure_ascii=False)

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
                r_badge = '<span class="px-2 py-0.5 rounded text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">買付 (BUY)</span>'
            elif r_action == "SELL":
                r_badge = '<span class="px-2 py-0.5 rounded text-xs font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">売却 (SELL)</span>'
            else:
                r_badge = '<span class="px-2 py-0.5 rounded text-xs font-bold bg-slate-600/30 text-slate-300 border border-slate-600/40">見送り / 提案</span>'

            r_ticker_raw = str(row.get("ticker", "NONE"))
            r_sector_raw = str(row.get("sector", "-"))

            trade_rows_html.append(
                f"""
                <tr class="border-b border-slate-800 hover:bg-slate-800/40 transition text-sm">
                    <td class="py-3 px-4 font-mono text-slate-300">{html.escape(str(row.get('date', '')))}</td>
                    <td class="py-3 px-4">{r_badge}</td>
                    <td class="py-3 px-4 font-bold text-white">{html.escape(to_ticker_display(r_ticker_raw))}</td>
                    <td class="py-3 px-4 text-slate-400 text-xs">{html.escape(to_sector_ja(r_sector_raw))}</td>
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
    <title>AI投資会社 | 朝刊ダッシュボード＆社長室</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        @keyframes spinSlow {{
            from {{ transform: rotate(0deg); }}
            to {{ transform: rotate(360deg); }}
        }}
        @keyframes spinReverse {{
            from {{ transform: rotate(360deg); }}
            to {{ transform: rotate(0deg); }}
        }}
        @keyframes shimmerMove {{
            0% {{ background-position: 200% 0; }}
            100% {{ background-position: -200% 0; }}
        }}
        .ring-spin-slow {{
            animation: spinSlow 2.6s linear infinite;
        }}
        .ring-spin-reverse {{
            animation: spinReverse 1.9s linear infinite;
        }}
        .progress-shimmer {{
            background: linear-gradient(90deg, #10b981 0%, #38bdf8 50%, #6366f1 100%);
            background-size: 200% 100%;
            animation: shimmerMove 2.2s linear infinite;
        }}
        @keyframes rpgBob {{
            0%, 100% {{ transform: translateY(0px); }}
            50% {{ transform: translateY(-4px); }}
        }}
        .rpg-pixel-doll {{
            image-rendering: pixelated;
            animation: rpgBob 1.8s ease-in-out infinite;
            filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.55));
        }}
        .dq-window {{
            border: 2px solid rgba(226, 232, 240, 0.75);
            box-shadow: inset 0 0 0 2px #0f172a, 0 6px 18px rgba(0, 0, 0, 0.5);
        }}
    </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen font-sans antialiased">
    <!-- ★ フルスクリーン・スタイリッシュAIローディングオーバーレイ（ドラクエ風4人パーティー演出） -->
    <div id="aiLoadingOverlay" class="fixed inset-0 z-50 hidden items-center justify-center bg-slate-950/85 backdrop-blur-md px-4 transition-opacity duration-300">
        <div class="relative w-full max-w-lg rounded-3xl bg-gradient-to-b from-slate-900/95 via-slate-900 to-slate-950 border border-sky-500/40 p-6 sm:p-8 shadow-[0_0_60px_rgba(14,165,233,0.25)] overflow-hidden">
            <!-- 背景の淡いネオン装飾 -->
            <div class="pointer-events-none absolute -top-24 -left-24 w-48 h-48 rounded-full bg-sky-500/15 blur-3xl"></div>
            <div class="pointer-events-none absolute -bottom-24 -right-24 w-48 h-48 rounded-full bg-emerald-500/15 blur-3xl"></div>

            <!-- ドラクエ風・AI社員4人パーティー行進ステージ＆ネオンリング -->
            <div class="relative mx-auto flex items-center justify-center gap-3 mb-5 py-2 px-4 rounded-2xl bg-slate-950/90 dq-window w-fit">
                <div id="modalHero1" class="w-12 h-12 rounded-xl bg-sky-950/90 border-2 border-sky-400 flex items-center justify-center transition-all scale-110 shadow-[0_0_15px_rgba(56,189,248,0.5)]">
                    {svg_researcher}
                </div>
                <div id="modalHero2" class="w-12 h-12 rounded-xl bg-purple-950/90 border border-purple-500/40 flex items-center justify-center transition-all opacity-60">
                    {svg_analyst}
                </div>
                <div id="modalHero3" class="w-12 h-12 rounded-xl bg-amber-950/90 border border-amber-500/40 flex items-center justify-center transition-all opacity-60">
                    {svg_manager}
                </div>
                <div id="modalHero4" class="w-12 h-12 rounded-xl bg-emerald-950/90 border border-emerald-500/40 flex items-center justify-center transition-all opacity-60">
                    {svg_accountant}
                </div>
            </div>

            <!-- タイトル・サブテキスト -->
            <div class="text-center">
                <div class="inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full text-[11px] font-bold bg-sky-500/15 text-sky-300 border border-sky-500/30 mb-2">
                    <span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                    <span id="loadingBadgeText">AI PARTY QUEST IN PROGRESS</span>
                </div>
                <h3 id="loadingTitle" class="text-lg sm:text-xl font-extrabold text-white tracking-tight">
                    AI社員4人が緊急経営会議を行っています...
                </h3>
                <p id="loadingSubtitle" class="text-xs text-slate-400 mt-1">
                    米国市場データの取得とGemini AI合議を実行中です（所要目安：約15〜20秒）
                </p>
            </div>

            <!-- プログレスバー＆経過秒数 -->
            <div class="mt-5">
                <div class="flex items-center justify-between text-xs font-mono mb-1.5">
                    <span id="loadingStepSummary" class="text-sky-300 font-semibold">STEP 1 / 4 実行中...</span>
                    <div class="flex items-center gap-3">
                        <span id="loadingTimer" class="text-slate-400">0.0 秒</span>
                        <span id="loadingPercent" class="text-emerald-400 font-bold">8%</span>
                    </div>
                </div>
                <div class="w-full h-2.5 bg-slate-800/90 rounded-full overflow-hidden p-0.5 border border-slate-700/70">
                    <div id="loadingProgressBar" class="h-full rounded-full progress-shimmer transition-all duration-300" style="width: 8%"></div>
                </div>
            </div>

            <!-- 4ステップ・ライブ進行インジケーター（各社員のドット絵アイコン付き） -->
            <div id="loadingStepsContainer" class="mt-5 space-y-2 text-left">
                <div id="loadStep1" class="flex items-center justify-between px-3 py-2 rounded-xl border border-sky-500/50 bg-sky-950/30 text-xs transition-all">
                    <div class="flex items-center gap-2.5">
                        <div class="w-8 h-8 rounded-lg bg-sky-950 border border-sky-400/50 flex items-center justify-center shrink-0 overflow-hidden">
                            {svg_researcher}
                        </div>
                        <span class="font-bold text-white">1. 情報屋が米国50銘柄の最新株価・ニュースを収集中</span>
                    </div>
                    <span id="loadStep1State" class="text-[11px] font-mono text-sky-300 font-bold shrink-0">⏳ 実行中...</span>
                </div>
                <div id="loadStep2" class="flex items-center justify-between px-3 py-2 rounded-xl border border-slate-800 bg-slate-900/50 text-xs opacity-50 transition-all">
                    <div class="flex items-center gap-2.5">
                        <div class="w-8 h-8 rounded-lg bg-purple-950 border border-purple-400/50 flex items-center justify-center shrink-0 overflow-hidden">
                            {svg_analyst}
                        </div>
                        <span class="font-medium text-slate-200">2. 大賢者がチャート・RSIでお買い得な株を計算中</span>
                    </div>
                    <span id="loadStep2State" class="text-[11px] font-mono text-slate-400 shrink-0">待機中</span>
                </div>
                <div id="loadStep3" class="flex items-center justify-between px-3 py-2 rounded-xl border border-slate-800 bg-slate-900/50 text-xs opacity-50 transition-all">
                    <div class="flex items-center gap-2.5">
                        <div class="w-8 h-8 rounded-lg bg-amber-950 border border-amber-400/50 flex items-center justify-center shrink-0 overflow-hidden">
                            {svg_manager}
                        </div>
                        <span class="font-medium text-slate-200">3. 勇者リーダーを中心にAI社員4人が徹底議論中</span>
                    </div>
                    <span id="loadStep3State" class="text-[11px] font-mono text-slate-400 shrink-0">待機中</span>
                </div>
                <div id="loadStep4" class="flex items-center justify-between px-3 py-2 rounded-xl border border-slate-800 bg-slate-900/50 text-xs opacity-50 transition-all">
                    <div class="flex items-center gap-2.5">
                        <div class="w-8 h-8 rounded-lg bg-emerald-950 border border-emerald-400/50 flex items-center justify-center shrink-0 overflow-hidden">
                            {svg_accountant}
                        </div>
                        <span class="font-medium text-slate-200">4. 金庫番パラディンが予算チェック＆提案書作成中</span>
                    </div>
                    <span id="loadStep4State" class="text-[11px] font-mono text-slate-400 shrink-0">待機中</span>
                </div>
            </div>

            <p class="text-[11px] text-center text-slate-400 mt-4">
                ※ 勝手に株が売買されることはありません。完了すると自動で画面が切り替わります。
            </p>
        </div>
    </div>
    <!-- ヘッダーバー -->
    <header class="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-30">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div>
                <div class="flex items-center gap-2">
                    <span class="inline-block w-3 h-3 rounded-full bg-emerald-400 animate-pulse"></span>
                    <h1 class="text-xl sm:text-2xl font-extrabold tracking-tight text-white">
                        AI投資会社 朝刊ダッシュボード <span class="text-slate-400 font-normal text-sm">（AI Investment Firm Morning Brief）</span>
                    </h1>
                </div>
                <p class="text-xs text-slate-400 mt-0.5">
                    AI社員4人が毎朝9時に投資方針を提案し、社長（あなた）が最終決定・売買報告を行うコックピット
                </p>
            </div>
            <div class="text-left sm:text-right text-xs text-slate-400 font-mono">
                <div>分析した米国市場の日付: <span class="text-slate-200 font-semibold">{market_date}</span></div>
                <div>画面の最終更新日時: <span class="text-slate-200">{updated_at}</span></div>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-8">
        <!-- 1. サマリーヘッダーKPI -->
        <section class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                <p class="text-xs font-bold text-slate-300">💰 現在の総資産額（株＋現金） <span class="hidden">Total Equity</span></p>
                <p class="text-2xl sm:text-3xl font-extrabold text-white mt-2 font-mono">${total_equity:.2f}</p>
                <p class="text-xs text-slate-400 mt-1">日本円目安: 約 ¥{jpy_total_equity:,} <span class="text-slate-500">(@150円換算)</span></p>
            </div>
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                <p class="text-xs font-bold text-slate-300">📈 トータル損益（もうけ・損） <span class="hidden">Total Return</span></p>
                <p class="text-2xl sm:text-3xl font-extrabold {return_color_class} mt-2 font-mono">
                    {return_sign}${total_return:.2f}
                </p>
                <p class="text-xs {return_color_class} mt-1 font-mono">
                    損益率: {return_sign}{total_return_pct:.2f}% （入金した元本合計 ${total_deposited:.2f}）
                </p>
            </div>
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                <p class="text-xs font-bold text-slate-300">💵 使える現金残高（買付余力） <span class="hidden">Cash</span></p>
                <p class="text-2xl sm:text-3xl font-extrabold text-sky-400 mt-2 font-mono">${cash:.2f}</p>
                <p class="text-xs text-slate-400 mt-1">約 ¥{jpy_cash:,} / 現金の割合 {cash_ratio_pct:.1f}%</p>
            </div>
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                <p class="text-xs font-bold text-slate-300">🏢 持っている株の評価額</p>
                <p class="text-2xl sm:text-3xl font-extrabold text-indigo-400 mt-2 font-mono">${holdings_val:.2f}</p>
                <p class="text-xs text-slate-400 mt-1">保有中の株: {len(holdings)}銘柄 / 最終積立月: {html.escape(str(portfolio.get('last_deposit_month', '-')))}</p>
            </div>
        </section>

        <!-- 2. 本日のAI経営会議 最終提案・結論カード（最上部・強調表示） -->
        <section class="bg-slate-900/95 border-2 {card_border} rounded-2xl p-6 shadow-2xl">
            <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-800 pb-4">
                <div class="flex items-center gap-3">
                    <span class="px-4 py-1.5 rounded-full text-sm font-extrabold border {badge_bg}">
                        {action_label}
                    </span>
                    <div>
                        <h2 class="text-lg sm:text-xl font-bold text-white">本日のAI経営会議 おすすめ方針・結論</h2>
                        <p class="text-xs text-slate-400">{exec_note_str}</p>
                    </div>
                </div>
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 bg-slate-950/70 p-3 rounded-xl border border-slate-800 text-center">
                    <div>
                        <div class="text-[11px] text-slate-400">おすすめ銘柄</div>
                        <div class="text-sm sm:text-base font-extrabold text-white">{ticker_display_str}</div>
                    </div>
                    <div>
                        <div class="text-[11px] text-slate-400">株数（1株単位）</div>
                        <div class="text-base font-extrabold text-white font-mono">{shares_int} 株</div>
                    </div>
                    <div>
                        <div class="text-[11px] text-slate-400">1株あたりの株価</div>
                        <div class="text-base font-extrabold text-white font-mono">${price_val:.2f}</div>
                    </div>
                    <div>
                        <div class="text-[11px] text-slate-400">必要な合計金額</div>
                        <div class="text-base font-extrabold text-emerald-400 font-mono">${total_amount_val:.2f}</div>
                    </div>
                </div>
            </div>

            <!-- SBI証券での手動注文ガイドメモ -->
            <div class="mt-4 bg-indigo-950/40 border border-indigo-500/30 rounded-xl p-4">
                <div class="flex items-center gap-2 text-indigo-300 font-bold text-sm mb-1">
                    <span>📱 SBI証券（米国株アプリ/Web）での具体的な注文手順ガイド</span>
                    <span class="text-xs font-normal text-indigo-400">（業種: {sector_ja_str}）</span>
                </div>
                <p class="text-sm text-slate-200 leading-relaxed whitespace-pre-line">{sbi_guide_str}</p>
            </div>

            {approval_button_html}
        </section>

        <!-- ★オーナー（社長）指令室 ＆ 実売買報告パネル -->
        <section class="bg-gradient-to-br from-slate-900 via-slate-900 to-indigo-950/40 border border-indigo-500/40 rounded-2xl p-6 shadow-xl">
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-slate-800 pb-4 mb-5">
                <div class="flex items-center gap-2.5">
                    <span class="text-2xl">👑</span>
                    <div>
                        <h2 class="text-lg font-extrabold text-white">オーナー（社長）指令室 ＆ 売買報告パネル</h2>
                        <p class="text-xs text-slate-400">
                            毎朝9時の会議も、このボタンからの会議も、AIは「方針の提案」だけを行います。実際に買う・売るの決定ボタンを押すのはあなた（社長）です！
                        </p>
                    </div>
                </div>
                <span id="serverStatusBadge" class="px-3 py-1 rounded-full text-xs font-bold bg-slate-800 text-slate-300 border border-slate-700 self-start sm:self-center">
                    接続確認中...
                </span>
            </div>

            <!-- ステータスメッセージ表示欄 -->
            <div id="ownerStatusAlert" class="hidden mb-5 p-4 rounded-xl border text-sm font-medium"></div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <!-- 左パネル：AI社員に今すぐ分析・会議を命令する -->
                <div class="bg-slate-950/80 border border-slate-800 rounded-xl p-5 flex flex-col justify-between">
                    <div>
                        <div class="flex items-center justify-between mb-3">
                            <h3 class="text-sm font-bold text-sky-300 flex items-center gap-2">
                                <span>🗣️ 1. AI社員に「今すぐ分析・会議して！」と命令する</span>
                            </h3>
                            <span class="text-[11px] text-slate-400">所要時間: 約15〜20秒</span>
                        </div>
                        <p class="text-xs text-slate-400 mb-3">
                            下のボタンを押すか指示を入力して「会議を招集」を押すと、AI社員4人が今すぐ最新株価とニュースを調べておすすめ方針を提案します（勝手に買われることはありません）。
                        </p>

                        <!-- ワンクリック定型命令タグ（複数銘柄・まとめ買い指示も追加） -->
                        <div class="flex flex-wrap gap-1.5 mb-3">
                            <button type="button" onclick="setPresetInstruction('予算内で2〜3銘柄に分散して、複数銘柄・複数株の買い組み合わせプランを提案して', false)"
                                class="px-2.5 py-1 rounded-lg text-xs bg-emerald-950/70 hover:bg-emerald-900 text-emerald-200 border border-emerald-500/40 font-bold transition">
                                🧺 予算内で2〜3銘柄をまとめ買い提案して
                            </button>
                            <button type="button" onclick="setPresetInstruction('1株あたりが安くて優秀な株やETFを、複数株（2〜4株など）まとめて買うプランを提案して', false)"
                                class="px-2.5 py-1 rounded-lg text-xs bg-sky-950/70 hover:bg-sky-900 text-sky-200 border border-sky-500/40 font-bold transition">
                                📦 お手頃な株を複数株まとめて提案して
                            </button>
                            <button type="button" onclick="setPresetInstruction('今は売買せず、現在の保有株と注目候補銘柄の詳しい分析だけ報告して', true)"
                                class="px-2.5 py-1 rounded-lg text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition">
                                📊 今の市場と注目株を分析して
                            </button>
                            <button type="button" onclick="setPresetInstruction('高配当ETF（SCHD）やS&P500（SPYM）など安全なETFを優先しておすすめを提案して', false)"
                                class="px-2.5 py-1 rounded-lg text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition">
                                🛡️ 安全なETF優先で提案して
                            </button>
                            <button type="button" onclick="setPresetInstruction('現在持っている株を今売るべきか（利益確定・損切り）、持ち続けるべきか診断して', false)"
                                class="px-2.5 py-1 rounded-lg text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition">
                                💰 持っている株の売り時を診断して
                            </button>
                            <button type="button" onclick="setPresetInstruction('値下がりしていて反発しそうな「お買い得（押し目）」の株を探して提案して', false)"
                                class="px-2.5 py-1 rounded-lg text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition">
                                🚀 お買い得な押し目株を探して
                            </button>
                        </div>

                        <textarea id="ownerInstructionInput" rows="3"
                            placeholder="自由入力（例：OXYとSCHDを両方買いたいけど何株ずつがいい？ / エヌビディアを売って別の株にすべき？）※空欄のままでも実行できます"
                            class="w-full rounded-xl bg-slate-900 border border-slate-700 text-slate-100 text-sm p-3 focus:outline-none focus:border-sky-500"></textarea>

                        <label class="flex items-center gap-2 mt-2.5 text-xs text-slate-300 cursor-pointer select-none">
                            <input type="checkbox" id="analysisOnlyCheck" class="rounded bg-slate-900 border-slate-700 text-sky-500 focus:ring-0">
                            <span>買い・売りの提案は出さず「市場の解説だけ（様子見固定）」にする</span>
                        </label>
                    </div>

                    <button type="button" id="runMeetingBtn" onclick="triggerInstantMeeting()"
                        class="mt-4 w-full py-3 px-4 rounded-xl font-extrabold text-sm bg-sky-600 hover:bg-sky-500 text-white shadow-lg shadow-sky-900/40 transition flex items-center justify-center gap-2">
                        <span>🚀 AI社員を集めて今すぐ会議させる（方針提案のみ）</span>
                    </button>
                </div>

                <!-- 右パネル：実際に買った・売った・入金した報告（文字入力不要＆複数株・複数銘柄まとめ対応） -->
                <div class="bg-slate-950/80 border border-slate-800 rounded-xl p-5 flex flex-col justify-between">
                    <div class="space-y-3">
                        <div class="flex items-center justify-between">
                            <h3 class="text-sm font-bold text-emerald-300 flex items-center gap-2">
                                <span>📝 2. 社長の決定・報告（「これ買った／売った／複数まとめ」）</span>
                            </h3>
                            <span class="text-[11px] font-mono text-sky-300">使える現金: ${cash:.2f}</span>
                        </div>

                        <!-- STEP A: どうしましたか？（大きな3択タブボタン） -->
                        <div>
                            <label class="block text-[11px] text-slate-400 mb-1">① なにをしましたか？（ボタンで選択）</label>
                            <select id="reportActionSelect" onchange="toggleReportFields()" class="hidden">
                                <option value="BUY">BUY</option>
                                <option value="SELL">SELL</option>
                                <option value="DEPOSIT">DEPOSIT</option>
                            </select>
                            <div class="grid grid-cols-3 gap-2">
                                <button type="button" id="actBtn_BUY" onclick="setReportActionMode('BUY')"
                                    class="py-2 px-2 rounded-xl text-xs font-extrabold border-2 border-emerald-500 bg-emerald-500/20 text-emerald-200 transition">
                                    🟢 株を買った
                                </button>
                                <button type="button" id="actBtn_SELL" onclick="setReportActionMode('SELL')"
                                    class="py-2 px-2 rounded-xl text-xs font-bold border border-slate-700 bg-slate-900 text-slate-400 hover:text-white transition">
                                    🔴 株を売った
                                </button>
                                <button type="button" id="actBtn_DEPOSIT" onclick="setReportActionMode('DEPOSIT')"
                                    class="py-2 px-2 rounded-xl text-xs font-bold border border-slate-700 bg-slate-900 text-slate-400 hover:text-white transition">
                                    💵 現金を入金
                                </button>
                            </div>
                        </div>

                        <!-- STEP B: 銘柄をワンクリック選択 または 一覧から選択 -->
                        <div id="reportTickerWrap" class="space-y-2">
                            <!-- 買うときのワンクリック注目銘柄ボタン -->
                            <div id="quickBuyChipsBox">
                                <div class="text-[11px] text-slate-400 mb-1">② どの銘柄ですか？（ボタンを押すだけで自動入力されます）</div>
                                <div class="flex flex-wrap gap-1.5">
                                    {quick_buy_chips_html}
                                </div>
                            </div>
                            <!-- 売るときの保有株ワンクリックボタン -->
                            <div id="quickSellChipsBox" class="hidden">
                                <div class="text-[11px] text-rose-300 font-bold mb-1">② どの保有株を売りましたか？（押すだけで保有株数も自動セット）</div>
                                <div class="flex flex-wrap gap-1.5">
                                    {quick_sell_chips_html}
                                </div>
                            </div>

                            <!-- 55銘柄の日本語一覧プルダウン ＋ 直接入力欄 -->
                            <div class="grid grid-cols-1 sm:grid-cols-5 gap-2">
                                <select id="quickUniverseSelect" onchange="onSelectUniverseDropdown(this.value)"
                                    class="sm:col-span-3 w-full rounded-lg bg-slate-900 border border-slate-700 text-slate-100 text-xs p-2 focus:outline-none focus:border-emerald-500">
                                    {universe_select_options_html}
                                </select>
                                <input type="text" id="reportTickerInput" oninput="updateLiveTradeCalc()" placeholder="直接入力(例: NVDA)"
                                    class="sm:col-span-2 w-full rounded-lg bg-slate-900 border border-slate-700 text-white text-xs p-2 uppercase font-mono font-bold focus:outline-none focus:border-emerald-500">
                            </div>
                        </div>

                        <!-- STEP C: 株数ステッパー（複数株対応）＆ 単価 ＆ メモ -->
                        <div class="grid grid-cols-1 sm:grid-cols-12 gap-2.5 items-end">
                            <div id="reportSharesWrap" class="sm:col-span-6">
                                <label class="block text-[11px] text-slate-400 mb-1">③ 株数（複数株まとめ買いOK）</label>
                                <div class="flex items-center gap-1">
                                    <button type="button" onclick="stepReportShares(-1)" class="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-white font-bold text-xs border border-slate-700">−1</button>
                                    <input type="number" id="reportSharesInput" value="1" min="1" step="1" oninput="updateLiveTradeCalc()"
                                        class="w-14 text-center rounded-lg bg-slate-900 border border-slate-700 text-white text-sm p-1.5 font-mono font-extrabold focus:outline-none focus:border-emerald-500">
                                    <button type="button" onclick="stepReportShares(1)" class="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-white font-bold text-xs border border-slate-700">＋1</button>
                                    <button type="button" onclick="stepReportShares(2)" class="px-2 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-sky-300 font-bold text-[11px] border border-slate-700">＋2</button>
                                    <button type="button" onclick="setMaxReportShares()" class="px-2 py-1.5 rounded-lg bg-indigo-950 hover:bg-indigo-900 text-indigo-200 font-bold text-[11px] border border-indigo-500/40">最大</button>
                                </div>
                            </div>
                            <div class="sm:col-span-3">
                                <label id="reportPriceLabel" class="block text-[11px] text-slate-400 mb-1">1株の価格($)</label>
                                <input type="number" id="reportPriceInput" placeholder="自動取得" min="0.01" step="0.01" oninput="updateLiveTradeCalc()"
                                    class="w-full rounded-lg bg-slate-900 border border-slate-700 text-slate-100 text-xs p-2 font-mono focus:outline-none focus:border-emerald-500">
                            </div>
                            <div class="sm:col-span-3">
                                <label class="block text-[11px] text-slate-400 mb-1">メモ（任意）</label>
                                <input type="text" id="reportNoteInput" placeholder="NISA等"
                                    class="w-full rounded-lg bg-slate-900 border border-slate-700 text-slate-100 text-xs p-2 focus:outline-none focus:border-emerald-500">
                            </div>
                        </div>

                        <!-- リアルタイム計算プレビュー ＆ 複数銘柄カート追加ボタン -->
                        <div class="flex flex-wrap items-center justify-between gap-2 px-3 py-2 rounded-xl bg-slate-900/90 border border-slate-800 text-xs">
                            <div id="liveTradeCostPreview" class="text-slate-300 font-mono">
                                💡 銘柄ボタンを押すと合計金額と残り現金が自動計算されます
                            </div>
                            <button type="button" id="addBatchBtn" onclick="addCurrentToTradeCart()"
                                class="px-2.5 py-1 rounded-lg bg-sky-500/20 hover:bg-sky-500/30 text-sky-300 border border-sky-500/40 font-bold text-[11px] transition">
                                ➕ まとめリストに追加（別銘柄も続けて選ぶ）
                            </button>
                        </div>

                        <!-- 複数銘柄まとめリスト（2銘柄以上選んだ時に表示） -->
                        <div id="tradeCartBox" class="hidden p-3 rounded-xl bg-indigo-950/40 border border-indigo-500/40 space-y-2">
                            <div class="flex items-center justify-between text-xs">
                                <span class="font-bold text-indigo-200">🧺 まとめ報告リスト（複数売買を一括反映）</span>
                                <button type="button" onclick="clearTradeCart()" class="text-[11px] text-rose-300 hover:underline">すべてクリア</button>
                            </div>
                            <div id="tradeCartItems" class="space-y-1 text-xs"></div>
                        </div>
                    </div>

                    <button type="button" id="submitReportBtn" onclick="submitManualTradeReport()"
                        class="mt-4 w-full py-3 px-4 rounded-xl font-extrabold text-sm bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/40 transition flex items-center justify-center gap-2">
                        <span id="submitReportBtnText">✅ 決定！この内容を口座データに反映する</span>
                    </button>
                </div>
            </div>
        </section>

        <!-- 3. 4体のAI社員の経営会議ルーム（ドラクエ風キャラ＆好調・普通・不調が一目でわかるステータス付き） -->
        <section class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg">
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-4">
                <div>
                    <h2 class="text-lg font-bold text-white flex items-center gap-2">
                        <span>🎮 AI社員4人の朝刊会議ルーム（パーティーステータス＆議論ログ）</span>
                    </h2>
                    <p class="text-xs text-slate-400 mt-0.5">
                        難しい専門用語を読まなくても、上の「🌞好調 / ⛅普通 / 🌧️不調」アイコンと「💡1行まとめ」を見るだけで今の状況が3秒でわかります！
                    </p>
                </div>
                <div class="flex items-center gap-2 text-[11px] bg-slate-950/80 px-3 py-1.5 rounded-xl border border-slate-800 self-start sm:self-center">
                    <span class="text-emerald-300 font-bold">🌞 好調＝買いチャンス</span>
                    <span class="text-slate-600">|</span>
                    <span class="text-amber-300 font-bold">⛅ 普通＝様子見</span>
                    <span class="text-slate-600">|</span>
                    <span class="text-rose-300 font-bold">🌧️ 不調＝警戒・ストップ</span>
                </div>
            </div>

            <!-- ★ ドラクエ風・AI社員4人のコンディション早見ボード -->
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-6 p-3.5 rounded-2xl bg-slate-950/90 dq-window">
                <!-- パーティー①：ニュース調査担当 -->
                <div class="rounded-xl p-3 border {cond_researcher['card_cls']} flex flex-col justify-between">
                    <div class="flex items-center gap-3">
                        <div class="w-14 h-14 rounded-xl bg-sky-950/80 border-2 border-sky-400/50 flex items-center justify-center shrink-0">
                            {svg_researcher}
                        </div>
                        <div class="min-w-0 flex-1">
                            <div class="text-[10px] text-sky-300 font-bold">Lv.99 情報屋（吟遊詩人）</div>
                            <div class="text-xs font-extrabold text-white truncate">ニュース調査担当</div>
                            <span class="inline-block mt-1 px-2 py-0.5 rounded-full text-[11px] font-extrabold border {cond_researcher['badge_cls']}">
                                {cond_researcher['short_label']} {cond_researcher['face_icon']}
                            </span>
                        </div>
                    </div>
                    <div class="mt-2.5">
                        <div class="flex justify-between text-[10px] font-mono text-slate-400 mb-1">
                            <span>好調度（テンション）</span>
                            <span class="text-white font-bold">{cond_researcher['gauge_pct']}%</span>
                        </div>
                        <div class="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                            <div class="h-full {cond_researcher['bar_cls']}" style="width: {cond_researcher['gauge_pct']}%"></div>
                        </div>
                    </div>
                </div>

                <!-- パーティー②：チャート分析担当 -->
                <div class="rounded-xl p-3 border {cond_analyst['card_cls']} flex flex-col justify-between">
                    <div class="flex items-center gap-3">
                        <div class="w-14 h-14 rounded-xl bg-purple-950/80 border-2 border-purple-400/50 flex items-center justify-center shrink-0">
                            {svg_analyst}
                        </div>
                        <div class="min-w-0 flex-1">
                            <div class="text-[10px] text-purple-300 font-bold">Lv.99 分析官（大賢者）</div>
                            <div class="text-xs font-extrabold text-white truncate">チャート分析担当</div>
                            <span class="inline-block mt-1 px-2 py-0.5 rounded-full text-[11px] font-extrabold border {cond_analyst['badge_cls']}">
                                {cond_analyst['short_label']} {cond_analyst['face_icon']}
                            </span>
                        </div>
                    </div>
                    <div class="mt-2.5">
                        <div class="flex justify-between text-[10px] font-mono text-slate-400 mb-1">
                            <span>お買い得サイン度</span>
                            <span class="text-white font-bold">{cond_analyst['gauge_pct']}%</span>
                        </div>
                        <div class="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                            <div class="h-full {cond_analyst['bar_cls']}" style="width: {cond_analyst['gauge_pct']}%"></div>
                        </div>
                    </div>
                </div>

                <!-- パーティー③：ファンドマネージャー -->
                <div class="rounded-xl p-3 border {cond_manager['card_cls']} flex flex-col justify-between">
                    <div class="flex items-center gap-3">
                        <div class="w-14 h-14 rounded-xl bg-amber-950/80 border-2 border-amber-400/60 flex items-center justify-center shrink-0">
                            {svg_manager}
                        </div>
                        <div class="min-w-0 flex-1">
                            <div class="text-[10px] text-amber-300 font-bold">Lv.99 リーダー（勇者）</div>
                            <div class="text-xs font-extrabold text-white truncate">ファンドマネージャー</div>
                            <span class="inline-block mt-1 px-2 py-0.5 rounded-full text-[11px] font-extrabold border {cond_manager['badge_cls']}">
                                {cond_manager['short_label']} {cond_manager['face_icon']}
                            </span>
                        </div>
                    </div>
                    <div class="mt-2.5">
                        <div class="flex justify-between text-[10px] font-mono text-slate-400 mb-1">
                            <span>おすすめ自信度</span>
                            <span class="text-white font-bold">{cond_manager['gauge_pct']}%</span>
                        </div>
                        <div class="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                            <div class="h-full {cond_manager['bar_cls']}" style="width: {cond_manager['gauge_pct']}%"></div>
                        </div>
                    </div>
                </div>

                <!-- パーティー④：資金・ルール管理担当 -->
                <div class="rounded-xl p-3 border {cond_accountant['card_cls']} flex flex-col justify-between">
                    <div class="flex items-center gap-3">
                        <div class="w-14 h-14 rounded-xl bg-emerald-950/80 border-2 border-emerald-400/50 flex items-center justify-center shrink-0">
                            {svg_accountant}
                        </div>
                        <div class="min-w-0 flex-1">
                            <div class="text-[10px] text-emerald-300 font-bold">Lv.99 金庫番（パラディン）</div>
                            <div class="text-xs font-extrabold text-white truncate">資金・ルール管理担当</div>
                            <span class="inline-block mt-1 px-2 py-0.5 rounded-full text-[11px] font-extrabold border {cond_accountant['badge_cls']}">
                                {cond_accountant['short_label']} {cond_accountant['face_icon']}
                            </span>
                        </div>
                    </div>
                    <div class="mt-2.5">
                        <div class="flex justify-between text-[10px] font-mono text-slate-400 mb-1">
                            <span>お財布の安全度</span>
                            <span class="text-white font-bold">{cond_accountant['gauge_pct']}%</span>
                        </div>
                        <div class="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                            <div class="h-full {cond_accountant['bar_cls']}" style="width: {cond_accountant['gauge_pct']}%"></div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 各社員の詳しい発言カード（1行の超要約つき） -->
            <div class="space-y-4">
                <!-- ① 情報収集担当 -->
                <div class="flex items-start gap-3.5">
                    <div class="flex flex-col items-center gap-1 shrink-0">
                        <div class="w-16 h-16 rounded-2xl bg-sky-950/80 dq-window flex items-center justify-center">
                            {svg_researcher}
                        </div>
                        <span class="px-2 py-0.5 rounded-full text-[10px] font-extrabold border {cond_researcher['badge_cls']}">
                            {cond_researcher['short_label']}
                        </span>
                    </div>
                    <div class="flex-1 {cond_researcher['card_cls']} border rounded-2xl rounded-tl-none p-4">
                        <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
                            <div class="flex flex-wrap items-center gap-2">
                                <span class="font-extrabold text-sm text-white">ニュース調査担当</span>
                                <span class="px-2 py-0.5 text-[11px] rounded bg-sky-500/20 text-sky-300 border border-sky-500/30 font-medium">
                                    世界の経済ニュース・好悪材料の分析（情報収集担当）
                                </span>
                            </div>
                            <span class="px-3 py-1 rounded-full text-xs font-extrabold border {cond_researcher['badge_cls']}">
                                状況判定：{cond_researcher['label']}
                            </span>
                        </div>
                        <!-- 専門用語なしの1行まとめボックス -->
                        <div class="mb-2.5 px-3 py-2 rounded-xl border text-xs font-bold {cond_researcher['summary_box_cls']}">
                            💡 つまり一言でいうと：{cond_researcher['summary_ja']}
                        </div>
                        <p class="text-xs sm:text-sm text-slate-300 leading-relaxed whitespace-pre-line">{researcher_text}</p>
                    </div>
                </div>

                <!-- ② テクニカル分析担当 -->
                <div class="flex items-start gap-3.5">
                    <div class="flex flex-col items-center gap-1 shrink-0">
                        <div class="w-16 h-16 rounded-2xl bg-purple-950/80 dq-window flex items-center justify-center">
                            {svg_analyst}
                        </div>
                        <span class="px-2 py-0.5 rounded-full text-[10px] font-extrabold border {cond_analyst['badge_cls']}">
                            {cond_analyst['short_label']}
                        </span>
                    </div>
                    <div class="flex-1 {cond_analyst['card_cls']} border rounded-2xl rounded-tl-none p-4">
                        <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
                            <div class="flex flex-wrap items-center gap-2">
                                <span class="font-extrabold text-sm text-white">チャート・数値分析担当</span>
                                <span class="px-2 py-0.5 text-[11px] rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 font-medium">
                                    株価の割安度・買い時タイミングの計算（テクニカル分析担当）
                                </span>
                            </div>
                            <span class="px-3 py-1 rounded-full text-xs font-extrabold border {cond_analyst['badge_cls']}">
                                状況判定：{cond_analyst['label']}
                            </span>
                        </div>
                        <!-- 専門用語なしの1行まとめボックス -->
                        <div class="mb-2.5 px-3 py-2 rounded-xl border text-xs font-bold {cond_analyst['summary_box_cls']}">
                            💡 つまり一言でいうと：{cond_analyst['summary_ja']}
                        </div>
                        <p class="text-xs sm:text-sm text-slate-300 leading-relaxed whitespace-pre-line">{analyst_text}</p>
                    </div>
                </div>

                <!-- ③ ファンドマネージャー -->
                <div class="flex items-start gap-3.5">
                    <div class="flex flex-col items-center gap-1 shrink-0">
                        <div class="w-16 h-16 rounded-2xl bg-amber-950/80 dq-window flex items-center justify-center">
                            {svg_manager}
                        </div>
                        <span class="px-2 py-0.5 rounded-full text-[10px] font-extrabold border {cond_manager['badge_cls']}">
                            {cond_manager['short_label']}
                        </span>
                    </div>
                    <div class="flex-1 {cond_manager['card_cls']} border rounded-2xl rounded-tl-none p-4">
                        <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
                            <div class="flex flex-wrap items-center gap-2">
                                <span class="font-extrabold text-sm text-white">ファンドマネージャー（投資判断リーダー）</span>
                                <span class="px-2 py-0.5 text-[11px] rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 font-medium">
                                    社長へのおすすめ方針提案
                                </span>
                            </div>
                            <span class="px-3 py-1 rounded-full text-xs font-extrabold border {cond_manager['badge_cls']}">
                                状況判定：{cond_manager['label']}
                            </span>
                        </div>
                        <!-- 専門用語なしの1行まとめボックス -->
                        <div class="mb-2.5 px-3 py-2 rounded-xl border text-xs font-bold {cond_manager['summary_box_cls']}">
                            💡 つまり一言でいうと：{cond_manager['summary_ja']}
                        </div>
                        <p class="text-xs sm:text-sm text-slate-200 leading-relaxed whitespace-pre-line">{manager_text}</p>
                    </div>
                </div>

                <!-- ④ 執行・経理担当 -->
                <div class="flex items-start gap-3.5">
                    <div class="flex flex-col items-center gap-1 shrink-0">
                        <div class="w-16 h-16 rounded-2xl bg-emerald-950/80 dq-window flex items-center justify-center">
                            {svg_accountant}
                        </div>
                        <span class="px-2 py-0.5 rounded-full text-[10px] font-extrabold border {cond_accountant['badge_cls']}">
                            {cond_accountant['short_label']}
                        </span>
                    </div>
                    <div class="flex-1 {cond_accountant['card_cls']} border rounded-2xl rounded-tl-none p-4">
                        <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
                            <div class="flex flex-wrap items-center gap-2">
                                <span class="font-extrabold text-sm text-white">資金・ルール管理担当（経理）</span>
                                <span class="px-2 py-0.5 text-[11px] rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-medium">
                                    予算オーバーや危険な集中投資のチェック（執行・経理担当）
                                </span>
                            </div>
                            <span class="px-3 py-1 rounded-full text-xs font-extrabold border {cond_accountant['badge_cls']}">
                                状況判定：{cond_accountant['label']}
                            </span>
                        </div>
                        <!-- 専門用語なしの1行まとめボックス -->
                        <div class="mb-2.5 px-3 py-2 rounded-xl border text-xs font-bold {cond_accountant['summary_box_cls']}">
                            💡 つまり一言でいうと：{cond_accountant['summary_ja']}
                        </div>
                        <p class="text-xs sm:text-sm text-slate-200 leading-relaxed whitespace-pre-line">{accountant_text}</p>
                    </div>
                </div>
            </div>
        </section>

        <!-- 4. ポートフォリオ＆チャート -->
        <section class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <!-- セクター構成比ドーナツグラフ -->
            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg">
                <h3 class="text-base font-bold text-white mb-1">🍩 資産の内訳（業種別・現金の割合）</h3>
                <p class="text-xs text-slate-400 mb-4">どの業種の株をどれくらい持っているか・現金がいくらかのバランスです</p>
                <div class="relative h-64 flex items-center justify-center">
                    <canvas id="sectorChart"></canvas>
                </div>
            </div>

            <!-- 総資産推移折れ線グラフ -->
            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg lg:col-span-2">
                <h3 class="text-base font-bold text-white mb-1">📈 資産の増え方グラフ（総資産 vs 入金した元本）</h3>
                <p class="text-xs text-slate-400 mb-4">緑の実線（総資産）がグレーの点線（元本）より上にあればプラス（利益）です</p>
                <div class="relative h-64">
                    <canvas id="equityChart"></canvas>
                </div>
            </div>
        </section>

        <!-- 保有銘柄一覧テーブル -->
        <section class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg overflow-hidden">
            <h2 class="text-lg font-bold text-white mb-4">📋 現在持っている株の一覧</h2>
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="border-b border-slate-700 text-xs text-slate-400">
                            <th class="py-3 px-4">銘柄名（ティッカー）</th>
                            <th class="py-3 px-4">業種（セクター）</th>
                            <th class="py-3 px-4 text-right">持っている株数</th>
                            <th class="py-3 px-4 text-right">買った時の平均価格</th>
                            <th class="py-3 px-4 text-right">今の株価</th>
                            <th class="py-3 px-4 text-right">現在の価値合計</th>
                            <th class="py-3 px-4 text-right">含み損益（もうけ）</th>
                            <th class="py-3 px-4 text-right">資産に占める割合</th>
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
            <h2 class="text-lg font-bold text-white mb-4">🕒 これまでの会議提案・売買・入金の履歴</h2>
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="border-b border-slate-700 text-xs text-slate-400">
                            <th class="py-3 px-4">日付</th>
                            <th class="py-3 px-4">種類</th>
                            <th class="py-3 px-4">銘柄名</th>
                            <th class="py-3 px-4">業種</th>
                            <th class="py-3 px-4 text-right">株数</th>
                            <th class="py-3 px-4 text-right">1株価格</th>
                            <th class="py-3 px-4 text-right">合計金額</th>
                            <th class="py-3 px-4 text-right">残った現金</th>
                            <th class="py-3 px-4">内容メモ</th>
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
        AI投資会社シミュレーションシステム — Powered by Python, yfinance &amp; Gemini Flash
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
                        '#38bdf8', '#10b981', '#a855f7', '#f59e0b',
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
                        labels: {{ color: '#cbd5e1', font: {{ size: 12 }} }}
                    }},
                    tooltip: {{
                        callbacks: {{
                            label: function(ctx) {{
                                const val = ctx.parsed || 0;
                                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                                const pct = total > 0 ? ((val / total) * 100).toFixed(1) : 0;
                                return ctx.label + ': $' + val.toFixed(2) + ' (' + pct + '%)';
                            }}
                        }}
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
                        label: '現在の総資産額 ($)',
                        data: historyEquity,
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.15)',
                        fill: true,
                        tension: 0.25,
                        pointRadius: 4
                    }},
                    {{
                        label: '入金した元本合計 ($)',
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

        // =====================================================================
        // オーナー（社長）指令室 ＆ 実売買報告パネル 操作スクリプト
        // file:// で直接開いている場合でも http://127.0.0.1:8000 のローカルサーバーへ自動接続する
        // =====================================================================
        const API_BASE = (window.location.protocol.startsWith('http') && window.location.port === '8000')
            ? ''
            : 'http://127.0.0.1:8000';
        const statusBadge = document.getElementById('serverStatusBadge');
        const statusAlert = document.getElementById('ownerStatusAlert');
        const KNOWN_PRICES = {known_prices_json};
        const HELD_SHARES = {held_shares_json};
        const TICKER_JA_MAP = {ticker_ja_json};
        const CURRENT_CASH = {cash:.2f};
        let tradeCart = [];

        function showOwnerAlert(message, isError = false) {{
            statusAlert.classList.remove('hidden', 'bg-rose-950/60', 'border-rose-500/50', 'text-rose-200', 'bg-emerald-950/60', 'border-emerald-500/50', 'text-emerald-200', 'bg-sky-950/60', 'border-sky-500/50', 'text-sky-200');
            if (isError) {{
                statusAlert.classList.add('bg-rose-950/60', 'border-rose-500/50', 'text-rose-200');
            }} else {{
                statusAlert.classList.add('bg-emerald-950/60', 'border-emerald-500/50', 'text-emerald-200');
            }}
            statusAlert.innerHTML = message;
        }}

        function setPresetInstruction(text, analysisOnly) {{
            document.getElementById('ownerInstructionInput').value = text;
            document.getElementById('analysisOnlyCheck').checked = analysisOnly;
        }}

        // ---------------------------------------------------------------------
        // 上部AI提案カード：株数変更ステッパー ＆ 複数銘柄まとめて一括決定
        // ---------------------------------------------------------------------
        function adjustMainProposalShares(delta, unitPrice) {{
            const inp = document.getElementById('mainProposalSharesInput');
            if (!inp) return;
            let val = parseInt(inp.value || '1', 10) + delta;
            if (isNaN(val) || val < 1) val = 1;
            inp.value = val;
            const total = (val * unitPrice).toFixed(2);
            const btnText = document.getElementById('mainProposalApproveBtnText');
            if (btnText) {{
                const tkr = '{raw_ticker_escaped}';
                btnText.textContent = '✅ このAI提案を決定（' + tkr + ' ' + val + '株 = $' + total + '）';
            }}
        }}

        async function approveMainProposalWithCustomShares(action, ticker, price) {{
            const inp = document.getElementById('mainProposalSharesInput');
            const shares = inp ? Math.max(1, parseInt(inp.value || '1', 10)) : 1;
            await approveAiProposal(action, ticker, shares, price);
        }}

        function stepMultiShare(idx, delta) {{
            const inp = document.getElementById('multiPropShares_' + idx);
            if (!inp) return;
            let val = parseInt(inp.value || '1', 10) + delta;
            if (isNaN(val) || val < 1) val = 1;
            inp.value = val;
            updateMultiProposalSummary();
        }}

        function updateMultiProposalSummary() {{
            const checks = document.querySelectorAll('.multi-prop-check');
            let count = 0;
            let totalUsd = 0.0;
            checks.forEach((chk) => {{
                const idx = chk.getAttribute('data-idx');
                const price = parseFloat(chk.getAttribute('data-price') || '0');
                const act = chk.getAttribute('data-action') || 'BUY';
                const shInp = document.getElementById('multiPropShares_' + idx);
                const sh = shInp ? Math.max(1, parseInt(shInp.value || '1', 10)) : 1;
                const subEl = document.getElementById('multiPropSub_' + idx);
                const subVal = price * sh;
                if (subEl) subEl.textContent = '$' + subVal.toFixed(2);
                if (chk.checked) {{
                    count += 1;
                    totalUsd += (act === 'SELL' ? -subVal : subVal);
                }}
            }});
            const badge = document.getElementById('multiProposalTotalBadge');
            if (badge) {{
                const remCash = CURRENT_CASH - totalUsd;
                badge.textContent = '選択中: ' + count + '銘柄（必要額 $' + Math.max(0, totalUsd).toFixed(2) + ' / 反映後の現金目安 $' + remCash.toFixed(2) + '）';
                badge.className = remCash >= 0
                    ? 'text-xs font-mono text-emerald-300 font-bold'
                    : 'text-xs font-mono text-rose-400 font-bold';
            }}
        }}

        async function approveSelectedMultiProposals() {{
            const online = await checkLocalServer();
            if (!online) {{
                showOwnerAlert(
                    '💡 <b>社長室サーバーが起動していません：</b><br>フォルダ内の <code>start_dashboard.command</code> をダブルクリックしてください！',
                    true
                );
                return;
            }}
            const checks = document.querySelectorAll('.multi-prop-check');
            const selectedTrades = [];
            checks.forEach((chk) => {{
                if (!chk.checked) return;
                const idx = chk.getAttribute('data-idx');
                const action = chk.getAttribute('data-action') || 'BUY';
                const ticker = chk.getAttribute('data-ticker') || '';
                const price = parseFloat(chk.getAttribute('data-price') || '0');
                const shInp = document.getElementById('multiPropShares_' + idx);
                const shares = shInp ? Math.max(1, parseInt(shInp.value || '1', 10)) : 1;
                if (ticker) {{
                    selectedTrades.push({{
                        action: action,
                        ticker: ticker,
                        shares: shares,
                        price: price,
                        note: 'AI提案リストから一括決定（' + ticker + ' ' + shares + '株 @ $' + price.toFixed(2) + '）'
                    }});
                }}
            }});
            if (selectedTrades.length === 0) {{
                showOwnerAlert('⚠️ 反映したい銘柄に1つ以上チェックを入れてください。', true);
                return;
            }}
            startLoadingOverlay('trade', '選んだ ' + selectedTrades.length + ' 銘柄をまとめて口座へ反映中...', '複数銘柄の保有データと現金残高を一括計算しています');
            try {{
                const res = await fetch(API_BASE + '/api/manual_trade', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ trades: selectedTrades }})
                }});
                const data = await res.json();
                if (!res.ok || data.status !== 'ok') {{
                    throw new Error(data.message || '一括反映に失敗しました');
                }}
                stopLoadingOverlay(true, '✅ ' + selectedTrades.length + '銘柄の一括反映が完了しました！');
                showOwnerAlert('✅ <b>' + data.message + '</b>', false);
                setTimeout(() => reloadDashboardFresh(), 700);
            }} catch (err) {{
                stopLoadingOverlay(false);
                showOwnerAlert('❌ エラー: ' + err.message, true);
            }}
        }}

        // ---------------------------------------------------------------------
        // 右側「社長の決定・報告パネル」：ワンクリック選択＆リアルタイム金額計算＆複数まとめカート
        // ---------------------------------------------------------------------
        function setReportActionMode(mode) {{
            const sel = document.getElementById('reportActionSelect');
            if (sel) sel.value = mode;
            const modes = ['BUY', 'SELL', 'DEPOSIT'];
            modes.forEach((m) => {{
                const btn = document.getElementById('actBtn_' + m);
                if (!btn) return;
                if (m === mode) {{
                    if (m === 'BUY') btn.className = 'py-2 px-2 rounded-xl text-xs font-extrabold border-2 border-emerald-500 bg-emerald-500/20 text-emerald-200 transition';
                    if (m === 'SELL') btn.className = 'py-2 px-2 rounded-xl text-xs font-extrabold border-2 border-rose-500 bg-rose-500/20 text-rose-200 transition';
                    if (m === 'DEPOSIT') btn.className = 'py-2 px-2 rounded-xl text-xs font-extrabold border-2 border-sky-500 bg-sky-500/20 text-sky-200 transition';
                }} else {{
                    btn.className = 'py-2 px-2 rounded-xl text-xs font-bold border border-slate-700 bg-slate-900 text-slate-400 hover:text-white transition';
                }}
            }});
            toggleReportFields();
            updateLiveTradeCalc();
        }}

        function toggleReportFields() {{
            const act = document.getElementById('reportActionSelect').value;
            const tickerWrap = document.getElementById('reportTickerWrap');
            const sharesWrap = document.getElementById('reportSharesWrap');
            const buyBox = document.getElementById('quickBuyChipsBox');
            const sellBox = document.getElementById('quickSellChipsBox');
            const priceLabel = document.getElementById('reportPriceLabel');
            const priceInput = document.getElementById('reportPriceInput');
            if (act === 'DEPOSIT') {{
                tickerWrap.classList.add('hidden');
                sharesWrap.classList.add('hidden');
                priceLabel.textContent = '追加入金額 (ドル)';
                priceInput.placeholder = '例: 100.00';
                if (!priceInput.value) priceInput.value = '100.00';
            }} else {{
                tickerWrap.classList.remove('hidden');
                sharesWrap.classList.remove('hidden');
                priceLabel.textContent = '1株の価格($)';
                priceInput.placeholder = '自動取得';
                if (act === 'SELL') {{
                    if (buyBox) buyBox.classList.add('hidden');
                    if (sellBox) sellBox.classList.remove('hidden');
                }} else {{
                    if (buyBox) buyBox.classList.remove('hidden');
                    if (sellBox) sellBox.classList.add('hidden');
                }}
            }}
        }}

        function selectQuickTicker(ticker, price, defaultShares = 1) {{
            const tInp = document.getElementById('reportTickerInput');
            const pInp = document.getElementById('reportPriceInput');
            const sInp = document.getElementById('reportSharesInput');
            const uSel = document.getElementById('quickUniverseSelect');
            if (tInp) tInp.value = ticker;
            if (pInp && price > 0) pInp.value = price.toFixed(2);
            if (sInp && defaultShares >= 1) sInp.value = defaultShares;
            if (uSel) uSel.value = ticker;
            updateLiveTradeCalc();
        }}

        function onSelectUniverseDropdown(ticker) {{
            if (!ticker) return;
            const prc = KNOWN_PRICES[ticker] || 0.0;
            selectQuickTicker(ticker, prc, 1);
        }}

        function stepReportShares(delta) {{
            const sInp = document.getElementById('reportSharesInput');
            if (!sInp) return;
            let val = parseInt(sInp.value || '1', 10) + delta;
            if (isNaN(val) || val < 1) val = 1;
            sInp.value = val;
            updateLiveTradeCalc();
        }}

        function setMaxReportShares() {{
            const act = document.getElementById('reportActionSelect').value;
            const ticker = (document.getElementById('reportTickerInput').value || '').trim().toUpperCase();
            const sInp = document.getElementById('reportSharesInput');
            const pInp = document.getElementById('reportPriceInput');
            if (!sInp) return;
            if (act === 'SELL') {{
                const held = HELD_SHARES[ticker] || 1;
                sInp.value = Math.max(1, held);
            }} else {{
                const prc = parseFloat(pInp.value || '0') || KNOWN_PRICES[ticker] || 0;
                if (prc > 0) {{
                    const maxBuy = Math.max(1, Math.floor(CURRENT_CASH / prc));
                    sInp.value = maxBuy;
                }}
            }}
            updateLiveTradeCalc();
        }}

        function updateLiveTradeCalc() {{
            const act = document.getElementById('reportActionSelect').value;
            const ticker = (document.getElementById('reportTickerInput').value || '').trim().toUpperCase();
            const shares = Math.max(1, parseInt(document.getElementById('reportSharesInput').value || '1', 10));
            const priceRaw = document.getElementById('reportPriceInput').value.trim();
            let price = priceRaw ? parseFloat(priceRaw) : (KNOWN_PRICES[ticker] || 0.0);
            const preview = document.getElementById('liveTradeCostPreview');
            if (!preview) return;

            if (act === 'DEPOSIT') {{
                const dep = price > 0 ? price : 100.0;
                preview.innerHTML = '💵 追加入金: <b class="text-sky-300">+$' + dep.toFixed(2) + '</b>（入金後の現金: <b class="text-white">$' + (CURRENT_CASH + dep).toFixed(2) + '</b>）';
                return;
            }}
            if (!ticker) {{
                preview.innerHTML = '💡 上の銘柄ボタンを押すか一覧から選ぶと、ここに合計金額が自動計算されます';
                return;
            }}
            const jaName = TICKER_JA_MAP[ticker] ? ticker + '（' + TICKER_JA_MAP[ticker] + '）' : ticker;
            if (price <= 0) {{
                preview.innerHTML = '📌 選択中: <b class="text-white">' + jaName + ' × ' + shares + '株</b>（決定時に最新株価を自動取得します）';
                return;
            }}
            const total = price * shares;
            const jpy = Math.round(total * 150).toLocaleString();
            if (act === 'BUY') {{
                const rem = CURRENT_CASH - total;
                const remCls = rem >= 0 ? 'text-emerald-300' : 'text-rose-400';
                const maxAffordable = Math.floor(CURRENT_CASH / price);
                preview.innerHTML = '🟢 買付: <b class="text-white">' + jaName + ' × ' + shares + '株</b> ＝ 合計 <b class="text-emerald-400">$' + total.toFixed(2) + '</b> (約¥' + jpy + ') ｜ 残り現金: <b class="' + remCls + '">$' + rem.toFixed(2) + '</b> <span class="text-slate-400">(最大' + maxAffordable + '株買えます)</span>';
            }} else {{
                const held = HELD_SHARES[ticker] || 0;
                const remCash = CURRENT_CASH + total;
                preview.innerHTML = '🔴 売却: <b class="text-white">' + jaName + ' × ' + shares + '株</b> ＝ 受取 <b class="text-amber-300">+$' + total.toFixed(2) + '</b> (約¥' + jpy + ') ｜ 売却後の現金: <b class="text-sky-300">$' + remCash.toFixed(2) + '</b> <span class="text-slate-400">(現在保有:' + held + '株)</span>';
            }}
        }}

        function addCurrentToTradeCart() {{
            const action = document.getElementById('reportActionSelect').value;
            const ticker = document.getElementById('reportTickerInput').value.trim().toUpperCase();
            const shares = Math.max(1, parseInt(document.getElementById('reportSharesInput').value || '1', 10));
            const priceRaw = document.getElementById('reportPriceInput').value.trim();
            const price = priceRaw ? parseFloat(priceRaw) : (KNOWN_PRICES[ticker] || 0.0);
            const note = document.getElementById('reportNoteInput').value.trim();

            if (action !== 'DEPOSIT' && !ticker) {{
                showOwnerAlert('⚠️ まず上のボタンまたは一覧から銘柄を選んでください。', true);
                return;
            }}
            tradeCart.push({{
                action: action,
                ticker: action === 'DEPOSIT' ? 'CASH' : ticker,
                shares: action === 'DEPOSIT' ? 1 : shares,
                price: price,
                note: note
            }});
            document.getElementById('reportTickerInput').value = '';
            document.getElementById('reportSharesInput').value = '1';
            document.getElementById('quickUniverseSelect').value = '';
            renderTradeCart();
            updateLiveTradeCalc();
        }}

        function removeTradeCartItem(idx) {{
            tradeCart.splice(idx, 1);
            renderTradeCart();
        }}

        function clearTradeCart() {{
            tradeCart = [];
            renderTradeCart();
        }}

        function renderTradeCart() {{
            const box = document.getElementById('tradeCartBox');
            const listEl = document.getElementById('tradeCartItems');
            const btnText = document.getElementById('submitReportBtnText');
            if (!box || !listEl) return;
            if (tradeCart.length === 0) {{
                box.classList.add('hidden');
                if (btnText) btnText.textContent = '✅ 決定！この内容を口座データに反映する';
                return;
            }}
            box.classList.remove('hidden');
            listEl.innerHTML = tradeCart.map((item, i) => {{
                const actBadge = item.action === 'BUY'
                    ? '<span class="text-emerald-300 font-bold">🟢買付</span>'
                    : (item.action === 'SELL' ? '<span class="text-rose-300 font-bold">🔴売却</span>' : '<span class="text-sky-300 font-bold">💵入金</span>');
                const sub = (item.price * item.shares).toFixed(2);
                return '<div class="flex items-center justify-between bg-slate-950/80 px-2.5 py-1.5 rounded-lg border border-slate-800">'
                    + '<div>' + actBadge + ' <b class="text-white font-mono ml-1">' + item.ticker + '</b> × ' + item.shares + '株 <span class="text-slate-400 font-mono">($' + sub + ')</span></div>'
                    + '<button type="button" onclick="removeTradeCartItem(' + i + ')" class="text-slate-400 hover:text-rose-400 font-bold px-1">✕</button>'
                    + '</div>';
            }}).join('');
            if (btnText) {{
                btnText.textContent = '✅ まとめリストの ' + tradeCart.length + ' 件（＋入力中の内容）を一括反映する';
            }}
        }}

        // =====================================================================
        // スタイリッシュ・フルスクリーンAIローディングオーバーレイ制御
        // =====================================================================
        let loadingTimerId = null;
        let loadingStartMs = 0;

        function setStepVisual(stepNum, status) {{
            const row = document.getElementById('loadStep' + stepNum);
            const state = document.getElementById('loadStep' + stepNum + 'State');
            const hero = document.getElementById('modalHero' + stepNum);
            if (!row || !state) return;

            if (status === 'done') {{
                row.className = 'flex items-center justify-between px-3 py-2 rounded-xl border border-emerald-500/40 bg-emerald-950/25 text-xs transition-all';
                state.textContent = '✅ 完了';
                state.className = 'text-[11px] font-mono text-emerald-400 font-bold shrink-0';
                if (hero) {{
                    hero.className = 'w-12 h-12 rounded-xl bg-emerald-950/90 border-2 border-emerald-400 flex items-center justify-center transition-all opacity-95';
                }}
            }} else if (status === 'active') {{
                row.className = 'flex items-center justify-between px-3 py-2 rounded-xl border border-sky-500/60 bg-sky-950/40 text-xs shadow-[0_0_20px_rgba(14,165,233,0.18)] transition-all';
                state.textContent = '⏳ 実行中...';
                state.className = 'text-[11px] font-mono text-sky-300 font-bold animate-pulse shrink-0';
                if (hero) {{
                    hero.className = 'w-12 h-12 rounded-xl bg-sky-950/90 border-2 border-amber-300 flex items-center justify-center transition-all scale-115 shadow-[0_0_18px_rgba(251,191,36,0.65)]';
                }}
            }} else {{
                row.className = 'flex items-center justify-between px-3 py-2 rounded-xl border border-slate-800 bg-slate-900/50 text-xs opacity-50 transition-all';
                state.textContent = '待機中';
                state.className = 'text-[11px] font-mono text-slate-400 shrink-0';
                if (hero) {{
                    hero.className = 'w-12 h-12 rounded-xl bg-slate-900/90 border border-slate-700 flex items-center justify-center transition-all opacity-50';
                }}
            }}
        }}

        function startLoadingOverlay(mode = 'meeting', customTitle = '', customSub = '') {{
            const overlay = document.getElementById('aiLoadingOverlay');
            const titleEl = document.getElementById('loadingTitle');
            const subEl = document.getElementById('loadingSubtitle');
            const badgeEl = document.getElementById('loadingBadgeText');
            const stepsContainer = document.getElementById('loadingStepsContainer');
            const stepSummary = document.getElementById('loadingStepSummary');
            const timerEl = document.getElementById('loadingTimer');
            const pctEl = document.getElementById('loadingPercent');
            const barEl = document.getElementById('loadingProgressBar');

            if (loadingTimerId) clearInterval(loadingTimerId);
            loadingStartMs = Date.now();
            timerEl.textContent = '0.0 秒';
            pctEl.textContent = '8%';
            barEl.style.width = '8%';

            if (mode === 'trade') {{
                badgeEl.textContent = 'PORTFOLIO SYNCING';
                titleEl.textContent = customTitle || '社長の決定を口座データへ反映しています...';
                subEl.textContent = customSub || '保有株・現金残高・最新ダッシュボードを更新中です';
                stepSummary.textContent = '口座データ・グラフ更新中...';
                stepsContainer.classList.add('hidden');
                setStepVisual(1, 'done');
                setStepVisual(2, 'done');
                setStepVisual(3, 'done');
                setStepVisual(4, 'active');
            }} else {{
                badgeEl.textContent = 'AI PARTY QUEST IN PROGRESS';
                titleEl.textContent = customTitle || 'AI社員4人が緊急経営会議を行っています...';
                subEl.textContent = customSub || '米国50銘柄の最新データ取得とGemini AI合議を実行中です（約15〜20秒）';
                stepSummary.textContent = 'STEP 1 / 4 : 米国市場データ取得中...';
                stepsContainer.classList.remove('hidden');
                setStepVisual(1, 'active');
                setStepVisual(2, 'pending');
                setStepVisual(3, 'pending');
                setStepVisual(4, 'pending');
            }}

            overlay.classList.remove('hidden');
            overlay.classList.add('flex');

            loadingTimerId = setInterval(() => {{
                const elapsedSec = (Date.now() - loadingStartMs) / 1000;
                timerEl.textContent = elapsedSec.toFixed(1) + ' 秒';

                if (mode === 'trade') {{
                    const pct = Math.min(92, Math.round(25 + elapsedSec * 25));
                    pctEl.textContent = pct + '%';
                    barEl.style.width = pct + '%';
                    stepSummary.textContent = '口座データ・グラフ更新中...';
                    return;
                }}

                // 20秒想定のスムーズな進捗演出（最大95%で完了待機）
                const pct = Math.min(95, Math.max(6, Math.round((1 - Math.exp(-elapsedSec / 9.5)) * 100)));
                pctEl.textContent = pct + '%';
                barEl.style.width = pct + '%';

                if (elapsedSec < 4.2) {{
                    stepSummary.textContent = 'STEP 1 / 4 : 情報屋が市場データ取得中...';
                    setStepVisual(1, 'active');
                    setStepVisual(2, 'pending');
                    setStepVisual(3, 'pending');
                    setStepVisual(4, 'pending');
                }} else if (elapsedSec < 8.5) {{
                    stepSummary.textContent = 'STEP 2 / 4 : 大賢者がお買い得株を計算中...';
                    setStepVisual(1, 'done');
                    setStepVisual(2, 'active');
                    setStepVisual(3, 'pending');
                    setStepVisual(4, 'pending');
                }} else if (elapsedSec < 15.0) {{
                    stepSummary.textContent = 'STEP 3 / 4 : 勇者リーダーと全員が徹底議論中...';
                    setStepVisual(1, 'done');
                    setStepVisual(2, 'done');
                    setStepVisual(3, 'active');
                    setStepVisual(4, 'pending');
                }} else {{
                    stepSummary.textContent = 'STEP 4 / 4 : 金庫番パラディンが提案書作成中...';
                    setStepVisual(1, 'done');
                    setStepVisual(2, 'done');
                    setStepVisual(3, 'done');
                    setStepVisual(4, 'active');
                }}
            }}, 100);
        }}

        function stopLoadingOverlay(isSuccess = true, doneTitle = '') {{
            if (loadingTimerId) {{
                clearInterval(loadingTimerId);
                loadingTimerId = null;
            }}
            const overlay = document.getElementById('aiLoadingOverlay');
            if (!isSuccess) {{
                overlay.classList.add('hidden');
                overlay.classList.remove('flex');
                return;
            }}
            document.getElementById('loadingPercent').textContent = '100%';
            document.getElementById('loadingProgressBar').style.width = '100%';
            document.getElementById('loadingStepSummary').textContent = 'COMPLETE! 画面を更新します...';
            if (doneTitle) {{
                document.getElementById('loadingTitle').textContent = doneTitle;
            }}
            setStepVisual(1, 'done');
            setStepVisual(2, 'done');
            setStepVisual(3, 'done');
            setStepVisual(4, 'done');
        }}

        function reloadDashboardFresh() {{
            const baseUrl = window.location.href.split('?')[0].split('#')[0];
            window.location.replace(baseUrl + '?t=' + Date.now());
        }}

        async function checkLocalServer() {{
            try {{
                const res = await fetch(API_BASE + '/api/ping');
                if (res.ok) {{
                    statusBadge.textContent = '🟢 社長室サーバー接続中（ボタン操作・決定 可能）';
                    statusBadge.className = 'px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 self-start sm:self-center';
                    return true;
                }}
            }} catch (e) {{}}
            statusBadge.textContent = '📖 閲覧モード (start_dashboard.command でボタン操作起動)';
            statusBadge.className = 'px-3 py-1 rounded-full text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 self-start sm:self-center';
            return false;
        }}

        async function approveAiProposal(action, ticker, shares, price) {{
            const online = await checkLocalServer();
            if (!online) {{
                showOwnerAlert(
                    '💡 <b>社長室サーバーが起動していません：</b><br>フォルダ内の <code>start_dashboard.command</code> をダブルクリックしてください！',
                    true
                );
                return;
            }}
            startLoadingOverlay('trade', 'AI提案（' + ticker + ' ' + shares + '株）を決定・反映中...', '保有株データと現金残高を最新状態に更新しています');
            showOwnerAlert('⏳ <b>AI提案（' + ticker + ' ' + shares + '株）を口座データへ反映しています...</b>', false);
            try {{
                const res = await fetch(API_BASE + '/api/manual_trade', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        action: action,
                        ticker: ticker,
                        shares: shares,
                        price: price,
                        note: 'AI提案を社長が承認・決定（' + ticker + ' ' + shares + '株 @ $' + price.toFixed(2) + '）'
                    }})
                }});
                const data = await res.json();
                if (!res.ok || data.status !== 'ok') {{
                    throw new Error(data.message || '反映に失敗しました');
                }}
                stopLoadingOverlay(true, '✅ 社長の決定を口座データに反映しました！');
                showOwnerAlert('✅ <b>決定を反映しました！</b>（' + data.message + '）画面を更新します...', false);
                setTimeout(() => reloadDashboardFresh(), 700);
            }} catch (err) {{
                stopLoadingOverlay(false);
                showOwnerAlert('❌ エラー: ' + err.message, true);
            }}
        }}

        async function triggerInstantMeeting() {{
            const online = await checkLocalServer();
            if (!online) {{
                showOwnerAlert(
                    '💡 <b>社長室サーバーが起動していません：</b><br>フォルダ内の <code>start_dashboard.command</code> をダブルクリックしてください！',
                    true
                );
                return;
            }}

            const instruction = document.getElementById('ownerInstructionInput').value.trim();
            const analysisOnly = document.getElementById('analysisOnlyCheck').checked;
            const btn = document.getElementById('runMeetingBtn');
            btn.disabled = true;
            btn.innerHTML = '<span>⏳ AI社員4人が最新株価を取得して会議中... (約15〜20秒)</span>';
            startLoadingOverlay(
                'meeting',
                instruction ? '社長の指示でAI社員4人が緊急会議中...' : 'AI社員4人が最新データで経営会議中...',
                instruction ? '指示内容：「' + instruction + '」' : '米国50銘柄の最新データ取得とGemini AI合議を実行中です（約15〜20秒）'
            );
            showOwnerAlert('⏳ <b>AI経営会議を実行中です...</b> 50銘柄の最新データ取得とGemini AI合議を行っています（勝手に売買は行いません）。そのまま20秒ほどお待ちください。', false);

            try {{
                const res = await fetch(API_BASE + '/api/meeting', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ instruction: instruction, analysis_only: analysisOnly }})
                }});
                const data = await res.json();
                if (!res.ok || data.status !== 'ok') {{
                    throw new Error(data.message || '会議の実行に失敗しました');
                }}
                stopLoadingOverlay(true, '✅ AI経営会議が完了！新しい提案が届きました');
                showOwnerAlert('✅ <b>AI経営会議が完了し、新しい方針提案が届きました！</b> 画面を更新します...', false);
                setTimeout(() => reloadDashboardFresh(), 700);
            }} catch (err) {{
                stopLoadingOverlay(false);
                showOwnerAlert('❌ エラー: ' + err.message, true);
                btn.disabled = false;
                btn.innerHTML = '<span>🚀 AI社員を集めて今すぐ会議させる（方針提案のみ）</span>';
            }}
        }}

        async function submitManualTradeReport() {{
            const online = await checkLocalServer();
            if (!online) {{
                showOwnerAlert(
                    '💡 <b>社長室サーバーが起動していません：</b><br>フォルダ内の <code>start_dashboard.command</code> をダブルクリックしてください！',
                    true
                );
                return;
            }}

            const action = document.getElementById('reportActionSelect').value;
            const ticker = document.getElementById('reportTickerInput').value.trim().toUpperCase();
            const shares = Math.max(1, parseInt(document.getElementById('reportSharesInput').value || '1', 10));
            const priceRaw = document.getElementById('reportPriceInput').value.trim();
            const price = priceRaw ? parseFloat(priceRaw) : 0.0;
            const note = document.getElementById('reportNoteInput').value.trim();

            const itemsToSubmit = [...tradeCart];
            if (action === 'DEPOSIT' && (itemsToSubmit.length === 0 || price > 0)) {{
                itemsToSubmit.push({{ action: 'DEPOSIT', ticker: 'CASH', shares: 1, price: price > 0 ? price : 100.0, note: note }});
            }} else if (ticker) {{
                itemsToSubmit.push({{ action: action, ticker: ticker, shares: shares, price: price, note: note }});
            }}

            if (itemsToSubmit.length === 0) {{
                showOwnerAlert('⚠️ 銘柄ボタンを押すか、一覧から銘柄を選択してください。', true);
                return;
            }}

            const btn = document.getElementById('submitReportBtn');
            btn.disabled = true;
            btn.innerHTML = '<span>⏳ 口座データへ反映中...</span>';
            startLoadingOverlay(
                'trade',
                itemsToSubmit.length > 1
                    ? itemsToSubmit.length + '件の売買・入金をまとめて口座へ反映中...'
                    : '売買・入金報告を口座データへ反映中...',
                '最新株価の照合とポートフォリオの再計算を行っています'
            );

            try {{
                const res = await fetch(API_BASE + '/api/manual_trade', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ trades: itemsToSubmit }})
                }});
                const data = await res.json();
                if (!res.ok || data.status !== 'ok') {{
                    throw new Error(data.message || '報告の反映に失敗しました');
                }}
                tradeCart = [];
                stopLoadingOverlay(true, '✅ 口座データの更新が完了しました！');
                showOwnerAlert('✅ <b>' + data.message + '</b> 画面を最新状態に更新します...', false);
                setTimeout(() => reloadDashboardFresh(), 700);
            }} catch (err) {{
                stopLoadingOverlay(false);
                showOwnerAlert('❌ エラー: ' + err.message, true);
                btn.disabled = false;
                btn.innerHTML = '<span id="submitReportBtnText">✅ 決定！この内容を口座データに反映する</span>';
                renderTradeCart();
            }}
        }}

        checkLocalServer();
    </script>
</body>
</html>
"""
    with output_path.open("w", encoding="utf-8") as f:
        f.write(html_content)

    return output_path
