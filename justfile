start:
  uv lock
  uv sync
  uv run get_root
  uv run streamlit run src/uiya/ui.py