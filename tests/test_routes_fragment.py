import pytest
from fastapi.testclient import TestClient

from pyminidash.config import Config
from pyminidash.web.app import create_app


@pytest.fixture
def client(dummy_providers):
    config = Config.model_validate({
        "groups": [
            {"id": "sys", "title": "Système", "type": "table",
             "blocks": [{"provider": "dummy_rows", "params": {"n": 2}},
                        {"provider": "dummy_empty"},
                        {"provider": "dummy_boom"}]},
            {"id": "apis", "title": "APIs", "type": "cards",
             "blocks": [{"provider": "dummy_rows", "params": {"n": 1}}]},
        ],
    })
    return TestClient(create_app(config))


def test_table_fragment_has_headers_and_rows(client):
    html = client.get("/groups/sys/blocks/0").text
    assert "<table" in html
    assert "<th>Nom</th>" in html
    assert html.count("<tr>") == 3           # 1 en-tête + 2 lignes
    assert 'hx-get="/groups/sys/blocks/0"' in html   # bouton ↻ du bloc


def test_empty_table_fragment_shows_no_data(client):
    html = client.get("/groups/sys/blocks/1").text
    assert "aucune donnée" in html
    assert "<table" not in html


def test_provider_exception_renders_error_frame(client):
    html = client.get("/groups/sys/blocks/2").text
    assert "Erreur" in html
    assert "RuntimeError" in html


def test_cards_fragment_splits_summary_and_hidden(client):
    html = client.get("/groups/apis/blocks/0").text
    assert "item0" in html                    # titre de la card
    assert "afficher plus (1)" in html        # 1 champ caché (detail)
    assert "ligne cachée 0" in html           # présent dans le HTML, masqué en CSS
    assert 'class="card-fields more"' in html


def test_out_of_range_index_is_404(client):
    assert client.get("/groups/sys/blocks/9").status_code == 404
    assert client.get("/groups/sys/blocks/-1").status_code == 404


def test_unknown_group_fragment_is_404(client):
    assert client.get("/groups/nope/blocks/0").status_code == 404
