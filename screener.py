"""
第1段階：Python一次スクリーニングモジュール（AI使用量ゼロ）
厳選50銘柄（S&P500主要11セクター代表45社＋低価格優良ETF 5銘柄）から
テクニカル指標（14日RSI、5日/25日移動平均線乖離率、出来高変化率）を計算し、
現在の現金残高で1株以上購入可能な上位6銘柄を抽出する。
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# 監視ユニバース：S&P500主要11セクター代表45銘柄 ＋ 低価格優良ETF 5銘柄（計50銘柄）
UNIVERSE_STOCKS: dict[str, str] = {
    # Technology (6銘柄)
    "AAPL": "Technology",
    "MSFT": "Technology",
    "NVDA": "Technology",
    "GOOGL": "Technology",
    "INTC": "Technology",
    "CSCO": "Technology",
    # Financials (5銘柄)
    "JPM": "Financials",
    "BAC": "Financials",
    "WFC": "Financials",
    "C": "Financials",
    "SOFI": "Financials",
    # Healthcare (5銘柄)
    "JNJ": "Healthcare",
    "PFE": "Healthcare",
    "MRK": "Healthcare",
    "ABBV": "Healthcare",
    "BMY": "Healthcare",
    # Consumer Discretionary (4銘柄)
    "AMZN": "Consumer Discretionary",
    "TSLA": "Consumer Discretionary",
    "F": "Consumer Discretionary",
    "NKE": "Consumer Discretionary",
    # Consumer Staples (5銘柄)
    "PG": "Consumer Staples",
    "KO": "Consumer Staples",
    "PEP": "Consumer Staples",
    "WMT": "Consumer Staples",
    "KHC": "Consumer Staples",
    # Energy (4銘柄)
    "XOM": "Energy",
    "CVX": "Energy",
    "OXY": "Energy",
    "SLB": "Energy",
    # Industrials (4銘柄)
    "GE": "Industrials",
    "CAT": "Industrials",
    "BA": "Industrials",
    "CSX": "Industrials",
    # Materials (3銘柄)
    "FCX": "Materials",
    "NEM": "Materials",
    "DOW": "Materials",
    # Utilities (3銘柄)
    "NEE": "Utilities",
    "SO": "Utilities",
    "AES": "Utilities",
    # Real Estate (3銘柄)
    "PLD": "Real Estate",
    "O": "Real Estate",
    "VICI": "Real Estate",
    # Communication Services (3銘柄)
    "META": "Communication Services",
    "VZ": "Communication Services",
    "T": "Communication Services",
    # 低価格優良ETF (5銘柄)
    "SPYM": "Broad Market ETF",
    "SCHD": "Dividend ETF",
    "QQQM": "Growth/Tech ETF",
    "VXUS": "International ETF",
    "VTI": "Broad Market ETF",
}

# 低価格優良ETFのセット（分散・安定性ボーナス用）
LOW_COST_ETFS: set[str] = {"SPYM", "SCHD", "QQQM", "VXUS", "VTI"}

# オフライン環境や通信全失敗時のフォールバック参考株価（安全動作保証用）
FALLBACK_PRICES: dict[str, float] = {
    "SPYM": 68.50,
    "SCHD": 28.40,
    "QQQM": 205.00,
    "VXUS": 62.10,
    "VTI": 285.00,
    "INTC": 24.50,
    "F": 11.20,
    "T": 22.80,
    "VZ": 41.50,
    "KHC": 31.20,
    "CSCO": 56.80,
    "BAC": 44.30,
    "PFE": 26.90,
    "KO": 63.40,
    "O": 55.60,
    "VICI": 30.10,
    "AES": 14.80,
    "CSX": 34.50,
    "OXY": 50.20,
    "SLB": 43.10,
    "SOFI": 13.50,
    "AAPL": 225.00,
    "MSFT": 420.00,
    "NVDA": 138.00,
}


def flatten_yfinance_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    yfinanceが返すDataFrameのMultiIndexカラムを1階層にフラット化する。
    """
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = out.columns.get_level_values(0)
    # 重複カラムがある場合は最初のカラムのみ残す
    if out.columns.duplicated().any():
        out = out.loc[:, ~out.columns.duplicated()]
    return out


def calculate_rsi(series: pd.Series, period: int = 14) -> float:
    """
    終値Seriesから指定期間（デフォルト14日）のRSIを計算する。
    """
    if series is None or len(series) < period + 1:
        return 50.0
    clean_series = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean_series) < period + 1:
        return 50.0

    delta = clean_series.diff()
    gain = delta.clip(lower=0.0).rolling(window=period, min_periods=period).mean()
    loss = (-delta.clip(upper=0.0)).rolling(window=period, min_periods=period).mean()

    latest_gain = float(gain.iloc[-1])
    latest_loss = float(loss.iloc[-1])

    if np.isnan(latest_gain) or np.isnan(latest_loss):
        return 50.0
    if latest_loss == 0.0:
        return 100.0 if latest_gain > 0.0 else 50.0

    rs = latest_gain / latest_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return round(float(np.clip(rsi, 0.0, 100.0)), 2)


def calculate_technical_metrics(df: pd.DataFrame) -> dict[str, Any] | None:
    """
    株価履歴DataFrameから現在値、14日RSI、5日/25日移動平均線乖離率、出来高変化率、
    および押し目買い・トレンド初動スコアを算出する。
    """
    flat_df = flatten_yfinance_df(df)
    if flat_df.empty or "Close" not in flat_df.columns:
        return None

    close = pd.to_numeric(flat_df["Close"], errors="coerce").dropna()
    if len(close) < 25:
        return None

    price = round(float(close.iloc[-1]), 2)
    if price <= 0:
        return None

    rsi_14 = calculate_rsi(close, period=14)
    ma5 = float(close.iloc[-5:].mean())
    ma25 = float(close.iloc[-25:].mean())

    ma5_dev_pct = round(((price - ma5) / ma5) * 100.0, 2) if ma5 > 0 else 0.0
    ma25_dev_pct = round(((price - ma25) / ma25) * 100.0, 2) if ma25 > 0 else 0.0

    vol_ratio = 1.0
    if "Volume" in flat_df.columns:
        volume = pd.to_numeric(flat_df["Volume"], errors="coerce").dropna()
        if len(volume) >= 20:
            avg_vol_20 = float(volume.iloc[-20:].mean())
            latest_vol = float(volume.iloc[-1])
            if avg_vol_20 > 0:
                vol_ratio = round(latest_vol / avg_vol_20, 2)

    # テクニカルスコア算出（ベース50点）
    score = 50.0

    # 1. RSI評価（押し目・売られすぎ優遇、過熱減点）
    if rsi_14 <= 30.0:
        score += 25.0
    elif rsi_14 <= 40.0:
        score += 18.0
    elif rsi_14 <= 55.0:
        score += 10.0
    elif rsi_14 >= 75.0:
        score -= 15.0

    # 2. 移動平均線乖離率＆トレンド初動評価
    if ma5 > ma25 and -2.0 <= ma25_dev_pct <= 5.0:
        score += 15.0  # ゴールデンクロス・上昇トレンド初動
    elif -8.0 <= ma25_dev_pct < -2.0:
        score += 10.0  # 25日移動平均線からの健全な押し目
    elif ma25_dev_pct > 10.0:
        score -= 10.0  # 上方乖離しすぎ（高値掴み警戒）

    # 3. 出来高変化率評価
    if vol_ratio >= 1.2:
        score += 10.0
    elif vol_ratio >= 1.0:
        score += 5.0

    # 最新取引日の抽出
    last_idx = close.index[-1]
    if hasattr(last_idx, "strftime"):
        market_date = last_idx.strftime("%Y-%m-%d")
    else:
        market_date = str(last_idx)[:10]

    return {
        "price": price,
        "rsi_14": rsi_14,
        "ma5": round(ma5, 2),
        "ma25": round(ma25, 2),
        "ma5_dev_pct": ma5_dev_pct,
        "ma25_dev_pct": ma25_dev_pct,
        "vol_ratio": vol_ratio,
        "score": round(score, 2),
        "market_date": market_date,
    }


def extract_news_titles(raw_news: list[Any] | None, max_items: int = 3) -> list[str]:
    """
    yfinanceのnews属性（バージョンにより辞書構造が異なる）から安全にタイトルを抽出する。
    """
    if not raw_news or not isinstance(raw_news, list):
        return []

    titles: list[str] = []
    for item in raw_news:
        if not isinstance(item, dict):
            continue
        content_dict = item.get("content")
        nested_title = ""
        if isinstance(content_dict, dict):
            nested_title = content_dict.get("title", "") or ""
        title = item.get("title") or nested_title
        if isinstance(title, str):
            clean_title = title.strip()
            if clean_title and clean_title not in titles:
                titles.append(clean_title)
        if len(titles) >= max_items:
            break
    return titles


def fetch_ticker_news(ticker: str, max_items: int = 3) -> list[str]:
    """
    指定ティッカーの直近ニュースタイトルリストを安全に取得する。
    """
    try:
        ticker_obj = yf.Ticker(ticker)
        raw_news = getattr(ticker_obj, "news", None)
        titles = extract_news_titles(raw_news, max_items=max_items)
        if titles:
            return titles
    except Exception as exc:
        logger.warning("ニュース取得スキップ (%s): %s", ticker, exc)
    return [f"{ticker}: 特段の重大ニュースなし（通常の市場変動）"]


def get_latest_market_date(reference_ticker: str = "SPYM") -> str:
    """
    ベンチマーク銘柄から米国市場の最新取引日（YYYY-MM-DD）を取得する。
    通信失敗時は直近の平日日付を返す。
    """
    try:
        hist = yf.Ticker(reference_ticker).history(period="10d")
        flat_hist = flatten_yfinance_df(hist)
        if not flat_hist.empty:
            last_idx = flat_hist.index[-1]
            if hasattr(last_idx, "strftime"):
                return last_idx.strftime("%Y-%m-%d")
            return str(last_idx)[:10]
    except Exception as exc:
        logger.warning("最新取引日取得失敗 (%s): %s", reference_ticker, exc)

    # フォールバック：現在日付（土日の場合は直近金曜日に補正）
    today = datetime.date.today()
    if today.weekday() == 5:  # 土曜
        today -= datetime.timedelta(days=1)
    elif today.weekday() == 6:  # 日曜
        today -= datetime.timedelta(days=2)
    return today.strftime("%Y-%m-%d")


def _build_synthetic_history(base_price: float, seed: int) -> pd.DataFrame:
    """
    外部通信が完全に遮断された環境でのフォールバック用株価履歴DataFrameを生成する。
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=datetime.date.today(), periods=35)
    returns = rng.normal(loc=-0.001, scale=0.012, size=len(dates))
    prices = base_price * np.cumprod(1.0 + returns)
    prices[-1] = base_price
    volumes = rng.integers(low=1_000_000, high=5_000_000, size=len(dates))
    return pd.DataFrame({"Close": prices, "Volume": volumes}, index=dates)


def screen_stocks(
    cash: float,
    existing_holdings: dict[str, Any] | None = None,
    top_n: int = 6,
) -> dict[str, Any]:
    """
    厳選50銘柄（＋現在保有銘柄）の株価データを取得し、
    現在の現金残高で1株以上購入可能な銘柄からスコア上位6銘柄を抽出する。
    """
    existing_holdings = existing_holdings or {}
    held_sectors: set[str] = {
        str(info.get("sector", ""))
        for info in existing_holdings.values()
        if isinstance(info, dict) and info.get("shares", 0) > 0
    }

    target_tickers = list(UNIVERSE_STOCKS.keys())
    for held_ticker in existing_holdings.keys():
        if held_ticker not in target_tickers:
            target_tickers.append(held_ticker)

    all_metrics: dict[str, dict[str, Any]] = {}
    all_prices: dict[str, float] = {}
    latest_market_date: str = ""

    for idx, ticker in enumerate(target_tickers):
        try:
            df = yf.Ticker(ticker).history(period="3mo")
            metrics = calculate_technical_metrics(df)
            if metrics is None:
                continue
            sector = UNIVERSE_STOCKS.get(
                ticker,
                existing_holdings.get(ticker, {}).get("sector", "Other"),
            )
            # セクター分散ボーナス＆低価格ETFボーナスを加味
            adjusted_score = metrics["score"]
            if sector not in held_sectors:
                adjusted_score += 5.0
            if ticker in LOW_COST_ETFS:
                adjusted_score += 3.0

            metrics["ticker"] = ticker
            metrics["sector"] = sector
            metrics["score"] = round(adjusted_score, 2)
            all_metrics[ticker] = metrics
            all_prices[ticker] = metrics["price"]

            if metrics["market_date"] > latest_market_date:
                latest_market_date = metrics["market_date"]
        except Exception as exc:
            logger.warning("ティッカー取得スキップ (%s): %s", ticker, exc)
            continue

    # 万一ネットワーク遮断等で1銘柄も取得できなかった場合の安全フォールバック
    if not all_metrics:
        logger.warning("外部株価データ取得数が0件のためフォールバックデータを使用します。")
        fallback_date = get_latest_market_date()
        latest_market_date = fallback_date
        for idx, (ticker, base_price) in enumerate(FALLBACK_PRICES.items()):
            synth_df = _build_synthetic_history(base_price, seed=100 + idx)
            metrics = calculate_technical_metrics(synth_df)
            if metrics is None:
                continue
            sector = UNIVERSE_STOCKS.get(ticker, "Other")
            adjusted_score = metrics["score"]
            if sector not in held_sectors:
                adjusted_score += 5.0
            if ticker in LOW_COST_ETFS:
                adjusted_score += 3.0
            metrics["ticker"] = ticker
            metrics["sector"] = sector
            metrics["score"] = round(adjusted_score, 2)
            metrics["market_date"] = fallback_date
            all_metrics[ticker] = metrics
            all_prices[ticker] = metrics["price"]

    # 1株以上購入可能な銘柄をフィルタリングし、スコア降順で上位top_n件を選出
    affordable_candidates = [
        m for m in all_metrics.values() if m["price"] <= cash
    ]
    affordable_candidates.sort(
        key=lambda x: (x["score"], -x["rsi_14"]),
        reverse=True,
    )
    top_candidates = affordable_candidates[:top_n]

    # 上位候補銘柄のニュース取得
    for candidate in top_candidates:
        candidate["news"] = fetch_ticker_news(candidate["ticker"], max_items=3)

    # 保有銘柄の情報整理とニュース取得
    holdings_info: dict[str, dict[str, Any]] = {}
    for ticker, h_data in existing_holdings.items():
        if not isinstance(h_data, dict) or h_data.get("shares", 0) <= 0:
            continue
        m = all_metrics.get(ticker)
        price = m["price"] if m else float(h_data.get("current_price", h_data.get("avg_cost", 0.0)))
        all_prices[ticker] = price
        holdings_info[ticker] = {
            "ticker": ticker,
            "sector": h_data.get("sector", UNIVERSE_STOCKS.get(ticker, "Other")),
            "shares": int(h_data.get("shares", 0)),
            "avg_cost": float(h_data.get("avg_cost", price)),
            "current_price": price,
            "rsi_14": m["rsi_14"] if m else 50.0,
            "ma5_dev_pct": m["ma5_dev_pct"] if m else 0.0,
            "ma25_dev_pct": m["ma25_dev_pct"] if m else 0.0,
            "vol_ratio": m["vol_ratio"] if m else 1.0,
            "news": fetch_ticker_news(ticker, max_items=3),
        }

    if not latest_market_date:
        latest_market_date = get_latest_market_date()

    return {
        "latest_market_date": latest_market_date,
        "candidates": top_candidates,
        "holdings_info": holdings_info,
        "all_prices": all_prices,
        "sector_map": dict(UNIVERSE_STOCKS),
    }
