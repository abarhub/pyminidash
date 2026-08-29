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
