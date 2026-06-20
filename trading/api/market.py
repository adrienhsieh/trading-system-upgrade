"""
trading/api/market.py — 大盤行情、新聞
"""
from flask import Blueprint, jsonify

from trading.api.auth import require_auth
from trading.services.container import container

market_bp = Blueprint("market", __name__)


@market_bp.route("/api/market")
@require_auth
def get_market():
    cache = container.market_svc.get_data()
    return jsonify({"ok": True, "market": cache, "cached": bool(cache)})


@market_bp.route("/api/news")
@require_auth
def get_news():
    return jsonify({"ok": True, "news": container.news_agg.fetch()})


@market_bp.route("/api/news/analyze")
@require_auth
def analyze_news():
    stock_map = container.scanner.get_stock_map()
    results   = container.news_agg.analyze_sentiment(stock_map)
    return jsonify({"ok": True, "results": results, "total": len(results)})
