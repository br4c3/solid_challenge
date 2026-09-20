from __future__ import annotations

from pathlib import Path
from typing import Optional

from flask import Flask, jsonify

from .catalog.importer import import_mcs
from .catalog.repository import ComponentRepository
from .catalog.routes import create_catalog_blueprint
from .design.routes import create_design_blueprint

ROOT = Path(__file__).resolve().parents[2]


def initialize_mcs(repository: ComponentRepository) -> None:
    if repository.list_mcs(): return
    workbook = next((ROOT / "references").glob("4-*.xlsx"), None)
    if workbook: import_mcs(workbook, repository)


def create_app(repository: Optional[ComponentRepository] = None) -> Flask:
    app        = Flask(__name__)
    repository = repository or ComponentRepository()
    initialize_mcs(repository)
    app.register_blueprint(create_catalog_blueprint(repository), url_prefix="/api")
    app.register_blueprint(create_design_blueprint(repository), url_prefix="/api")

    @app.errorhandler(ValueError)
    def invalid_request(error):
        return jsonify({"error": str(error)}), 400

    @app.errorhandler(400)
    def bad_request(_error):
        return jsonify({"error": "Request body must contain valid JSON."}), 400

    return app


__all__ = ["create_app"]
