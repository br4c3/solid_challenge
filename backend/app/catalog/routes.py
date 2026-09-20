from dataclasses import asdict

from flask import Blueprint, jsonify, request

from .repository import ComponentRepository


def create_catalog_blueprint(repository: ComponentRepository) -> Blueprint:
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

    return api
