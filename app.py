"""Streamlit entry point for Image Gallery Browser."""


def main() -> None:
    """Render the initial application shell."""
    import streamlit as st

    st.set_page_config(page_title="Image Gallery Browser", layout="wide")
    st.title("Image Gallery Browser")
    st.info("Project scaffold ready. Implement core modules next.")


if __name__ == "__main__":
    main()
