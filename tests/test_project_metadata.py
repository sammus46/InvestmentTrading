from pathlib import Path


def test_streamlit_runtime_dependency_is_declared():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert '"streamlit>=' in pyproject
