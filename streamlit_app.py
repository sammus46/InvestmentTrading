"""Streamlit Community Cloud entry point.

The implementation lives in ``app.streamlit_app`` so the FastAPI/static app and
Streamlit app can share the same package code. Community Cloud deploy forms are
least error-prone when the entry point is a root-level ``streamlit_app.py``.
"""

from app.streamlit_app import main


if __name__ == "__main__":
    main()
