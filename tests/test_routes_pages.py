import pytest
from fastapi.testclient import TestClient

from pyminidash.config import Config
from pyminidash.web.app import create_app


@pytest.fixture
def client(dummy_providers):
    config = Config.model_validate({
        "app": {"title": "Test Dash"},
        "groups": [
            {"id": "sys", "title": "Système", "type": "table",
             "blocks": [{"provider": "dummy_rows", "params": {"n": 2}},
                        {"provider": "dummy_empty"}]},
            {"id": "apis", "title": "APIs", "type": "cards",
             "blocks": [{"provider": "dummy_rows"}]},
        ],
    })
    return TestClient(create_app(config))


def test_root_redirects_to_default_group(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/groups/sys"


def test_group_page_lists_groups_in_sidebar(client):
    html = client.get("/groups/sys").text
    assert "Système" in html and "APIs" in html
    assert "Test Dash" in html


def test_group_page_has_one_placeholder_per_block(client):
    html = client.get("/groups/sys").text
    assert html.count('hx-get="/groups/sys/blocks/0"') == 1
    assert html.count('hx-get="/groups/sys/blocks/1"') == 1
    assert 'hx-trigger="load, refresh"' in html
    assert 'id="recalc-all"' in html


def test_unknown_group_is_404(client):
    assert client.get("/groups/nope").status_code == 404
