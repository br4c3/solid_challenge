from __future__ import annotations

from flask import Blueprint, jsonify, request

from .formulas import FORMULA_SLOTS, FormulaEngine, FormulaProfileRepository, validate_profile


def create_formula_blueprint(repository: FormulaProfileRepository) -> Blueprint:
    api = Blueprint("formulas", __name__)

    @api.get("/formula-profiles")
    def list_profiles():
        profiles = repository.list()
        summaries = [
            {
                key: profile[key]
                for key in ("id", "name", "description", "revision", "built_in", "created_at", "updated_at")
            } for profile in profiles
        ]
        return jsonify({"profiles": summaries, "slots": FORMULA_SLOTS})

    @api.get("/formula-profiles/<profile_id>")
    def get_profile(profile_id: str):
        revision = request.args.get("revision", type=int)
        return jsonify(repository.get(profile_id, revision))

    @api.post("/formula-profiles/validate")
    def validate():
        profile = validate_profile(request.get_json())
        FormulaEngine(profile)
        return jsonify({"valid": True, "profile": profile})

    @api.post("/formula-profiles/import")
    def import_profile():
        payload = request.get_json()
        if not isinstance(payload, dict): raise ValueError("가져온 프로필은 객체 형식이어야 합니다.")
        payload = {**payload, "name": str(payload.get("name", "가져온 프로필")).strip()}
        return jsonify(repository.create(payload)), 201

    @api.post("/formula-profiles")
    def create_profile():
        payload               = request.get_json() or {}
        source_id             = payload.get("source_id", "default-v1")
        source_revision       = payload.get("source_revision")
        source                = repository.get(source_id, source_revision)
        source["name"]        = str(payload.get("name", f"{source['name']} 복사본")).strip()
        source["description"] = str(payload.get("description", source.get("description", ""))).strip()
        return jsonify(repository.create(source)), 201

    @api.put("/formula-profiles/<profile_id>")
    def update_profile(profile_id: str):
        payload = request.get_json() or {}
        if "base_revision" not in payload: raise ValueError("base_revision 값이 필요합니다.")
        return jsonify(repository.update(profile_id, int(payload["base_revision"]), payload))

    @api.delete("/formula-profiles/<profile_id>")
    def delete_profile(profile_id: str):
        repository.delete(profile_id)
        return "", 204

    return api
