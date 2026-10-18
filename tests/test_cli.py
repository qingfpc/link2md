"""CLI help, init, and doctor. Save itself is covered with fakes in test_pipeline."""

from link2md.cli import main
from link2md.config import load_config


def test_help_mentions_usage():
    try:
        code = main(["--help"])
    except SystemExit as exc:
        code = exc.code
    assert code == 0


def test_init_writes_example(tmp_path, capsys):
    path = tmp_path / "config.yaml"
    assert main(["init", "--config", str(path)]) == 0
    text = path.read_text(encoding="utf-8")
    assert "vault:" in text
    assert "douyin:" in text
    config = load_config(path, environ={})
    assert config.llm.provider == "deepseek"
    assert main(["init", "--config", str(path)]) == 0
    captured = capsys.readouterr()
    assert "已存在" in captured.out


def test_doctor_reports_missing_vault(tmp_path, capsys):
    path = tmp_path / "config.yaml"
    path.write_text("vault:\n  path: ''\n", encoding="utf-8")
    code = main(["doctor", "--config", str(path)])
    output = capsys.readouterr().out
    assert code == 1
    assert "未配置" in output
    assert "faster-whisper" in output


def test_doctor_passes_when_vault_exists(tmp_path, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = tmp_path / "config.yaml"
    path.write_text(f"vault:\n  path: {vault}\ncache_dir: {tmp_path / 'cache'}\n", encoding="utf-8")
    code = main(["doctor", "--config", str(path)])
    output = capsys.readouterr().out
    assert code == 0
    assert "检查通过" in output
    assert "v2 预留" in output
