from pathlib import Path

from l2l3_protocol.tui.cockpit import parse_args


def test_web_cockpit_static_assets_exist() -> None:
    web_dir = Path("src/l2l3_protocol/web")

    js = (web_dir / "cockpit.js").read_text(encoding="utf-8")

    assert js.count("/runs") >= 3
    assert "Synthetic data is not allowed" in js
    assert "L2 <span>&lt;-&gt;</span> L3 Cockpit" in (web_dir / "cockpit.html").read_text(encoding="utf-8")


def test_cockpit_launcher_args_default_to_web_url(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["l2l3-cockpit", "--no-open"])

    args = parse_args()

    assert args.api_url == "http://localhost:8080"
    assert args.no_open is True
