from caixa_inteligente.cli import image_samples, main


def test_help_does_not_load_model_or_database(capsys):
    import pytest

    with pytest.raises(SystemExit) as result:
        main(["--help"])
    assert result.value.code == 0
    assert "dataset-download" in capsys.readouterr().out


def test_image_samples_preserves_sku_and_filters_files(tmp_path):
    folder = tmp_path / "banana"
    folder.mkdir()
    image = folder / "1.JPG"
    image.write_bytes(b"fixture")
    (folder / "notes.txt").write_text("ignored", encoding="utf-8")
    assert image_samples(tmp_path) == [("banana", image)]


def test_missing_database_configuration_is_actionable(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("caixa_inteligente.config.load_dotenv", lambda: None)
    monkeypatch.setattr("caixa_inteligente.cli.load_dotenv", lambda: None)
    assert main(["init-db"]) == 1
    assert "DATABASE_URL" in capsys.readouterr().err
