from flask import Blueprint, jsonify

scenarios = Blueprint('scenarios', __name__)


@scenarios.get('/api/scenarios')
def list_scenarios():
    return jsonify(items=[])