from pathlib import Path


def test_streamlit_runtime_dependency_is_declared():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    requirements = Path("requirements.txt").read_text(encoding="utf-8")

    assert '"streamlit>=' in pyproject
    assert "streamlit>=" in requirements


def test_streamlit_cloud_entrypoint_delegates_to_app_module():
    entrypoint = Path("streamlit_app.py").read_text(encoding="utf-8")

    assert "from app.streamlit_app import main" in entrypoint
    assert "main()" in entrypoint
