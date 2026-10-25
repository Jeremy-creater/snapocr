"""WI-6 / Gap3: the pure RapidOCR parameter mapping (unit lane, no models loaded)."""

from snapocr.engines.config import OcrEngineConfig, resolve_model_paths
from snapocr.engines.rapidocr_engine import build_rapidocr_params


def _no_state_switches(params: dict) -> bool:
    return not any(
        key.startswith("Global.use_") or key.split(".", 1)[-1].startswith("use_") for key in params
    )


def test_build_params_for_default_config():
    paths = resolve_model_paths(OcrEngineConfig())
    d = build_rapidocr_params(paths)

    assert d.get("Det.model_path") == str(paths.det)
    assert d.get("Cls.model_path") == str(paths.cls)
    assert d.get("Rec.model_path") == str(paths.rec)
    assert d.get("Global.text_score") == 0.0
    assert d.get("Global.log_level") == "warning"
    assert _no_state_switches(d), sorted(d)


def test_build_params_follows_explicit_model_dir(tmp_path):
    model_dir = tmp_path / "中文 目录"
    paths = resolve_model_paths(OcrEngineConfig(model_dir=model_dir))
    d = build_rapidocr_params(paths)

    for key, path in (
        ("Det.model_path", paths.det),
        ("Cls.model_path", paths.cls),
        ("Rec.model_path", paths.rec),
    ):
        assert d.get(key) == str(path)
        assert str(d.get(key)).startswith(str(model_dir))
    assert "中文 目录" in str(d.get("Rec.model_path"))
    assert _no_state_switches(d), sorted(d)
