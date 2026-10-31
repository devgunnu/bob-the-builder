"""aws mode reads no .env file; provider keys come only from Secrets Manager (config.py)."""

import pytest

from bob import config


def test_aws_settings_ignore_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("JEV_API_KEY=from-dotenv\nKEEP_P=0.5\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("KEEP_P", raising=False)
    monkeypatch.setenv("BOB_ENV", "aws")

    aws = config.build_settings("aws")
    assert aws.jev_api_key == ""  # the .env value is not read
    assert aws.keep_p == 0.9
    assert aws.env == "aws"

    # the same folder in local mode reads the .env file (proves the file is valid)
    monkeypatch.setenv("BOB_ENV", "local")
    local = config.build_settings("local")
    assert local.jev_api_key == "from-dotenv"
    assert local.keep_p == 0.5


def test_aws_mode_needs_secret_arn(monkeypatch):
    monkeypatch.setenv("BOB_ENV", "aws")
    monkeypatch.delenv("BOB_SECRET_ARN", raising=False)
    config.get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="BOB_SECRET_ARN"):
            config.get_settings()
    finally:
        monkeypatch.setenv("BOB_ENV", "local")
        config.get_settings.cache_clear()


def test_local_dotenv_cannot_switch_to_aws(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("BOB_ENV=aws\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BOB_ENV", raising=False)
    assert config.process_env_mode() == "local"
    with pytest.raises(RuntimeError, match="process env"):
        config.build_settings("local")
