from dataclasses import asdict

from flask import Blueprint, jsonify, request

from .crawler import CrawlManager
from .repository import ComponentRepository


def create_catalog_blueprint(repository: ComponentRepository, crawler: CrawlManager) -> Blueprint:
    api = Blueprint("catalog", __name__)

    @api.get("/health")
    def health():
        return jsonify({
            "status": "ok",
            "components": len(repository.list()),
            "mcs": len(repository.list_mcs()),
        })

    @api.get("/components")
    def components():
        category = request.args.get("category") or None
        return jsonify({"components": [asdict(component) for component in repository.list(category)]})

    @api.post("/crawl")
    def start_crawl():
        if not crawler.start(): return jsonify({"error": "A crawl is already running."}), 409
        return jsonify(crawler.snapshot()), 202

    @api.get("/crawl")
    def crawl_status():
        after = request.args.get("after", default=0, type=int)
        return jsonify(crawler.snapshot(after))

    return api
