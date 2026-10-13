from __future__ import annotations

import atexit
import os
from typing import Optional

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from .catalog.importer import import_mcs
from .catalog.crawler import CrawlManager
from .catalog.repository import ComponentRepository
from .catalog.routes import create_catalog_blueprint
from .design.routes import create_design_blueprint
from .formula_routes import create_formula_blueprint
from .formulas import FormulaProfileRepository
from .preferences import PreferenceRepository
from ..runtime import reference_dir


def initialize_mcs(repository: ComponentRepository) -> None:
    if repository.list_mcs(): return
    workbook = next(reference_dir().glob("4-*.xlsx"), None)
    if workbook: import_mcs(workbook, repository)


def create_app(
    repository: Optional[ComponentRepository] = None,
    crawler: Optional[CrawlManager] = None,
) -> Flask:
    app                   = Flask(__name__)
    repository            = repository or ComponentRepository()
    preference_repository = PreferenceRepository(repository.path)
    formula_repository    = FormulaProfileRepository(repository.path)
    crawler               = crawler or CrawlManager()
    atexit.register(crawler.stop)
    initialize_mcs(repository)
    app.register_blueprint(create_catalog_blueprint(repository, crawler, preference_repository), url_prefix="/api")
    app.register_blueprint(create_formula_blueprint(formula_repository), url_prefix="/api")
    app.register_blueprint(
        create_design_blueprint(repository, preference_repository, formula_repository), url_prefix="/api"
    )

    @app.before_request
    def authenticate_desktop_request():
        token = os.environ.get("RF_DESIGN_API_TOKEN")
        if token and request.method != "OPTIONS" and request.headers.get("X-RF-Design-Token") != token:
            return jsonify({"error": "데스크톱 API 인증에 실패했습니다."}), 401

    @app.after_request
    def allow_desktop_renderer(response):
        origin          = request.headers.get("Origin")
        allowed_origins = {"null", "http://127.0.0.1:5173", "http://localhost:5173"}
        if os.environ.get("RF_DESIGN_DESKTOP") == "1" and origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"]          = origin
            response.headers["Access-Control-Allow-Headers"]         = "Content-Type, X-RF-Design-Token"
            response.headers["Access-Control-Allow-Methods"]         = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response

    @app.errorhandler(ValueError)
    def invalid_request(error):
        return jsonify({"error": str(error)}), 400

    @app.errorhandler(400)
    def bad_request(_error):
        return jsonify({"error": "요청 본문에 올바른 JSON이 필요합니다."}), 400

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify({"error": error.description}), error.code

    @app.errorhandler(Exception)
    def internal_error(error):
        app.logger.exception("Unhandled API error", exc_info=error)
        return jsonify({"error": "서버가 요청을 처리하지 못했습니다."}), 500

    return app


__all__ = ["create_app"]
