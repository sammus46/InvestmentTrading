from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib


def project_metadata() -> dict:
    return pyproject_config()["project"]


def pyproject_config() -> dict:
    return tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))


def test_streamlit_runtime_dependency_is_declared():
    dependencies = project_metadata()["dependencies"]

    assert any(dependency.startswith("streamlit>=") for dependency in dependencies)


def test_python_requirement_has_upper_bound_for_streamlit_resolver():
    requires_python = project_metadata()["requires-python"]

    assert ">=3.10" in requires_python
    assert "<4" in requires_python


def test_poetry_package_mode_is_disabled_for_streamlit_cloud():
    poetry_config = pyproject_config()["tool"]["poetry"]

    assert poetry_config["package-mode"] is False
