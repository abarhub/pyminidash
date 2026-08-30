import pytest

from pyminidash.__main__ import build_parser, main


def test_parser_defaults():
    args = build_parser().parse_args([])
    assert str(args.config) == "config.toml"
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.open is False


def test_main_exits_2_on_bad_config(tmp_path, capsys):
    bad = tmp_path / "c.toml"
    bad.write_text('[[groups]]\nid="g"\ntitle="G"\ntype="table"\n'
                   '  [[groups.blocks]]\n  provider="nope"\n', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["--config", str(bad)])
    assert exc.value.code == 2
    assert "nope" in capsys.readouterr().err


def test_main_starts_server(tmp_path, monkeypatch):
    started = {}

    def fake_run(app, host, port):
        started["host"] = host
        started["port"] = port

    monkeypatch.setattr("pyminidash.__main__.uvicorn.run", fake_run)
    cfg = tmp_path / "c.toml"
    cfg.write_text(
        '[[groups]]\nid="sys"\ntitle="Système"\ntype="table"\n'
        '  [[groups.blocks]]\n  provider="disk_usage"\n'
        '  params = { paths = ["."] }\n',
        encoding="utf-8",
    )
    main(["--config", str(cfg), "--port", "9123"])
    assert started == {"host": "127.0.0.1", "port": 9123}


def test_parser_has_secrets_option():
    args = build_parser().parse_args(["--secrets", "/tmp/s.toml"])
    assert str(args.secrets).endswith("s.toml")
    assert build_parser().parse_args([]).secrets is None


def test_main_starts_with_missing_token(tmp_path, monkeypatch):
    # token 'jira' absent de secrets.toml → connexion désactivée, le serveur
    # démarre quand même ; le bloc jira s'affichera en erreur au runtime.
    captured = {}
    monkeypatch.setattr("pyminidash.__main__.uvicorn.run", lambda *a, **k: None)
    monkeypatch.setattr(
        "pyminidash.__main__.create_app",
        lambda config, connections: captured.setdefault("conns", connections) or object(),
    )
    cfg = tmp_path / "c.toml"
    cfg.write_text(
        '[connections.jira]\nbase_url = "https://jira.example.com"\ntoken = "jira"\n'
        '[[groups]]\nid = "g"\ntitle = "G"\ntype = "table"\n'
        '  [[groups.blocks]]\n  provider = "jira_my_issues"\n  connection = "jira"\n',
        encoding="utf-8",
    )
    main(["--config", str(cfg)])   # ne lève pas
    assert captured["conns"] == {}


def test_main_builds_connections(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr("pyminidash.__main__.uvicorn.run", lambda *a, **k: None)
    monkeypatch.setattr(
        "pyminidash.__main__.create_app",
        lambda config, connections: captured.setdefault("conns", connections) or object(),
    )
    (tmp_path / "secrets.toml").write_text('jira = "PAT"\n', encoding="utf-8")
    cfg = tmp_path / "c.toml"
    cfg.write_text(
        '[connections.jira]\nbase_url = "https://jira.example.com"\ntoken = "jira"\n'
        '[[groups]]\nid = "g"\ntitle = "G"\ntype = "table"\n'
        '  [[groups.blocks]]\n  provider = "jira_my_issues"\n  connection = "jira"\n',
        encoding="utf-8",
    )
    main(["--config", str(cfg)])
    assert captured["conns"]["jira"].token == "PAT"
