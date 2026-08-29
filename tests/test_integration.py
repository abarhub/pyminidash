"""Test d'intégration : un vrai provider (`disk_usage`) traversé de bout en bout
par une route, du registre jusqu'au template. Pas de réseau, pas de mock."""
from fastapi.testclient import TestClient

from pyminidash.config import Config
from pyminidash.web.app import create_app


def _client() -> TestClient:
    config = Config.model_validate({
        "groups": [
            {"id": "disk-table", "title": "Disques (table)", "type": "table",
             "blocks": [{"provider": "disk_usage", "params": {"paths": ["."]}}]},
            {"id": "disk-cards", "title": "Disques (cards)", "type": "cards",
             "blocks": [{"provider": "disk_usage", "params": {"paths": ["."]}}]},
        ],
    })
    return TestClient(create_app(config))


def test_disk_usage_table_route_end_to_end():
    html = _client().get("/groups/disk-table/blocks/0")
    assert html.status_code == 200
    body = html.text
    assert "<th>Disque</th>" in body
    assert "<td>" in body and "status status-" in body


def test_disk_usage_cards_route_end_to_end():
    html = _client().get("/groups/disk-cards/blocks/0")
    assert html.status_code == 200
    body = html.text
    assert 'class="card-fields more"' in body
    assert "afficher plus (" in body
