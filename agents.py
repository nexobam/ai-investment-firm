"""
第2段階：マルチAIエージェント会議モジュール
最新SDK `google-genai`（モデル: gemini-2.5-flash）および Pydantic 構造化出力を使用し、
1回のAPIコールで3役（情報収集担当・テクニカル分析担当・ファンドマネージャー）の議論と
最終意思決定（BUY / SELL / HOLD）を生成する。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SubOrderProposal(BaseModel):
    action: str = "BUY"      # "BUY" or "SELL"
    ticker: str = "NONE"     # ティッカー（例: "SCHD", "KO"）
    shares: int = 1          # 株数（1株以上の整数）
    reason_short: str = ""   # 1行の簡単な提案理由


class MeetingDecision(BaseModel):
    action: str          # "BUY", "SELL", or "HOLD"
    ticker: str          # 第1提案の対象ティッカー（HOLDの場合は "NONE"）
    shares: int          # 第1提案の売買株数（1株単位の整数、HOLDは 0）
    researcher_comment: str
    analyst_comment: str
    manager_reason: str
    sbi_order_guide: str # SBI証券での具体的な手動注文ガイド
    additional_proposals: list[SubOrderProposal] = Field(default_factory=list)


def build_meeting_prompt(
    portfolio: dict[str, Any],
    candidates: list[dict[str, Any]],
    holdings_info: dict[str, dict[str, Any]],
    owner_instruction: str = "",
) -> str:
    """
    現在のポートフォリオ状況、保有銘柄データ、一次スクリーニング上位6銘柄の
    テクニカル指標・ニュース、およびオーナー（社長）からの特別指示を統合した
    AI経営会議用プロンプトを生成する。
    """
    cash = float(portfolio.get("cash", 0.0))
    holdings_value = sum(
        float(h.get("shares", 0)) * float(h.get("current_price", h.get("avg_cost", 0.0)))
        for h in holdings_info.values()
    )
    total_equity = round(cash + holdings_value, 2)
    limit_35_val = round(total_equity * 0.35, 2)
    is_initial_phase = total_equity < 1000.0

    holdings_summary = []
    for t, h in holdings_info.items():
        shares = int(h["shares"])
        avg_cost = float(h["avg_cost"])
        cur_price = float(h["current_price"])
        mv = round(shares * cur_price, 2)
        pnl_pct = round(((cur_price - avg_cost) / avg_cost) * 100.0, 2) if avg_cost > 0 else 0.0
        weight_pct = round((mv / total_equity) * 100.0, 2) if total_equity > 0 else 0.0
        holdings_summary.append(
            {
                "ticker": t,
                "sector": h.get("sector", "Other"),
                "shares": shares,
                "avg_cost": avg_cost,
                "current_price": cur_price,
                "market_value": mv,
                "unrealized_pnl_pct": pnl_pct,
                "portfolio_weight_pct": weight_pct,
                "rsi_14": h.get("rsi_14", 50.0),
                "ma25_dev_pct": h.get("ma25_dev_pct", 0.0),
                "news": h.get("news", []),
            }
        )

    candidates_summary = []
    for c in candidates:
        price = float(c["price"])
        max_affordable_shares = int(cash // price) if price > 0 else 0
        candidates_summary.append(
            {
                "ticker": c["ticker"],
                "sector": c["sector"],
                "price": price,
                "max_affordable_shares": max_affordable_shares,
                "rsi_14": c["rsi_14"],
                "ma5_dev_pct": c["ma5_dev_pct"],
                "ma25_dev_pct": c["ma25_dev_pct"],
                "vol_ratio": c["vol_ratio"],
                "technical_score": c["score"],
                "news": c.get("news", []),
            }
        )

    owner_section = ""
    if owner_instruction and owner_instruction.strip():
        owner_section = f"""
【👑 オーナー（社長）からの直接命令（最優先で考慮すること）】
「{owner_instruction.strip()}」
※各エージェントは上記のオーナー命令に必ず言及・配慮して分析および最終決定（BUY/SELL/HOLD）を行ってください。もし「買わずに分析だけして」「様子見（HOLD）にして」等の指示がある場合は、具体的な銘柄分析を行いつつ最終actionは "HOLD" としてください。
"""

    prompt = f"""あなたは米国株を対象とした仮想投資会社のマルチAIエージェント経営会議システムです。
以下のポートフォリオ状況、現在保有中の銘柄データ、およびPython一次スクリーニングを通過した上位候補銘柄データを分析し、本日の投資意思決定をJSON（MeetingDecisionスキーマ）で出力してください。
{owner_section}
【現在の口座・資産状況】
- 現金残高 (Cash): ${cash:.2f}
- 保有株評価額合計: ${holdings_value:.2f}
- 総資産額 (Total Equity): ${total_equity:.2f}
- 1銘柄あたり35%上限基準額: ${limit_35_val:.2f}
- 初期フェーズ特例（総資産$1,000未満）適用中か: {is_initial_phase}

【厳守すべき投資ルール】
1. 現物取引のみ（空売り・信用取引なし）。
2. 1株単位の正の整数（shares >= 1）のみ売買可能（端株・小数株は禁止）。HOLDの場合は ticker="NONE", shares=0 とすること。
3. 買い注文（BUY）の場合、購入金額（株価 × 株数）が現金残高（${cash:.2f}）以下でなければならない。
4. 1銘柄の上限ロック：購入後のその銘柄の評価額が総資産の35%（${limit_35_val:.2f}）を超える追加購入は禁止。
   ※ただし、現在総資産が $1,000 未満（{is_initial_phase}）であり、未保有の銘柄を「新規に1株だけ（shares=1）」購入する場合に限り、現金残高の範囲内であれば35%制限を免除して購入可能。
5. すでに保有している銘柄と同じセクターへの偏りを避け、異なるセクターや低価格優良ETF（SPYM, SCHD, QQQM, VXUS, VTI）への分散を優先すること。
6. 売り注文（SELL）は現在保有中の銘柄のみ対象とし、保有株数以下の整数株のみ指定可能。

【現在保有中の銘柄一覧】
{json.dumps(holdings_summary, ensure_ascii=False, indent=2)}

【一次スクリーニング選出・購入候補上位銘柄（現金残高で購入可能）】
{json.dumps(candidates_summary, ensure_ascii=False, indent=2)}

【出力項目（すべて自然な日本語で具体的に記述すること）】
- action: 第1提案の "BUY", "SELL", "HOLD" のいずれか
- ticker: 第1提案の対象ティッカーシンボル（HOLDの場合は "NONE"）
- shares: 第1提案の売買株数（1株単位の整数、予算や35%上限の範囲内で2株・3株など複数株の提案も可。HOLDの場合は 0）
- additional_proposals: 社長が複数銘柄をまとめて売買したり比較検討できるよう、第2・第3のおすすめ売買プラン（SubOrderProposalのリスト：action, ticker, shares, reason_short）を1〜3件程度含めること（例：低価格株やETFの複数株買い、別セクターの分散候補など）
- researcher_comment: 情報収集担当（News Researcher）として、対象銘柄および市場の直近ニュースから好材料・悪材料を分析したコメント
- analyst_comment: テクニカル分析担当（Technical Analyst）として、14日RSI・5日/25日移動平均線乖離率・出来高変化率・セクター分散の観点から数値根拠付きで評価したコメント
- manager_reason: ファンドマネージャー（Fund Manager）として、2名の報告と現金残高・35%ルールを踏まえて最終決断（および複数候補プラン）を下した理由
- sbi_order_guide: ユーザーがSBI証券（米国株アプリ/Web）で手動注文する際の具体的な操作手順メモ（ティッカー、売買区分、株数、指値/成行の目安金額、預り区分：特定/NISAなど）
"""
    return prompt


def run_ai_meeting(prompt_text: str) -> MeetingDecision:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        return MeetingDecision(
            action="HOLD",
            ticker="NONE",
            shares=0,
            researcher_comment="[Mock] 市場ニュースは概ね中立です。",
            analyst_comment="[Mock] RSIおよび移動平均線は様子見水準です。",
            manager_reason="[Mock] APIキー未設定のため安全に現金温存（HOLD）とします。",
            sbi_order_guide="本日の注文はありません（現金温存）。"
        )
    candidate_models = [
        "gemini-2.5-flash",
        "gemini-3.5-flash",
        "gemini-3.7-flash",
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash-lite",
        "gemini-3.8-flash",
    ]
    last_exc: Exception | None = None
    for model_name in candidate_models:
        try:
            client = genai.Client(api_key=api_key)
            gen_config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MeetingDecision,
                temperature=0.2,
                http_options=types.HttpOptions(
                    timeout=15000,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
            response = client.models.generate_content(
                model=model_name,
                contents=prompt_text,
                config=gen_config,
            )
            logger.info("Geminiモデル (%s) から応答を取得しました。", model_name)
            return MeetingDecision.model_validate_json(response.text)
        except Exception as exc:
            last_exc = exc
            logger.warning("モデル %s 呼び出し失敗（次候補へ切替）: %s", model_name, exc)
            continue

    logger.warning("全Geminiモデル呼び出し例外のため安全にHOLDへフォールバックします: %s", last_exc)
    return MeetingDecision(
        action="HOLD",
        ticker="NONE",
        shares=0,
        researcher_comment="[Fallback] 外部AI通信エラーまたはレート制限のためニュース評価をスキップしました。",
        analyst_comment="[Fallback] テクニカル指標は算出済みですが、AI会議通信エラーのため中立評価とします。",
        manager_reason=f"[Fallback] API通信例外（{type(last_exc).__name__ if last_exc else 'Unknown'}）が発生したため、安全第一で現金温存（HOLD）とします。",
        sbi_order_guide="本日の注文はありません（システム安全保護による現金温存）。",
    )
