import httpx
import respx
from fastapi.testclient import TestClient

from pyminidash.config import Config
from pyminidash.connection import build_connections
from pyminidash.web.app import create_app

_ISSUE = {
    "key": "ABC-1",
    "fields": {"summary": "Bug critique", "status": {"name": "To Do"}},
}


def _client():
    config = Config.model_validate({
        "connections": {"jira": {"base_url": "https://jira.example.com", "token": "jira"}},
        "groups": [{
            "id": "jira", "title": "Jira", "type": "table",
            "blocks": [{
                "provider": "jira_jql", "connection": "jira", "title": "Ouvertes",
                "params": {"jql": "project = ABC", "fields": ["key", "summary", "status"]},
            }],
        }],
    })
    connections = build_connections(config, {"jira": "PAT"})
    return TestClient(create_app(config, connections))


@respx.mock
def test_jira_block_renders_table_fragment():
    respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=httpx.Response(200, json={"issues": [_ISSUE], "total": 1})
    )
    html = _client().get("/groups/jira/blocks/0").text
    assert "<th>Clé</th>" in html
    assert "ABC-1" in html
    assert "https://jira.example.com/browse/ABC-1" in html
    assert "Bug critique" in html


@respx.mock
def test_jira_block_auth_error_renders_error_frame():
    respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=httpx.Response(401)
    )
    html = _client().get("/groups/jira/blocks/0").text
    assert "Erreur" in html
    assert "authentification refusée" in html
    assert "PAT" not in html
