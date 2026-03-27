import streamlit as st
from langchain_groq import ChatGroq
import os

from .agent import run_agent


def render_app() -> None:
    st.set_page_config(page_title="Order & Invoice Agent", layout="wide")

    st.title("🛒 Order & Invoice Search Agent")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_input := st.chat_input("Ask something..."):
        st.session_state.chat_history.append({"role": "user", "content": user_input})

        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    llm = ChatGroq(
                        model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
                        temperature=float(os.getenv("GROQ_TEMPERATURE", "0.1")),
                        max_tokens=int(os.getenv("GROQ_MAX_TOKENS", "400")),
                    )
                    response = run_agent(user_input, llm)
                    print(f"✅ [AGENT] Final response: {response}")
                    st.markdown(response)

                    st.session_state.chat_history.append({"role": "assistant", "content": response})
                except Exception as e:
                    error_text = str(e)
                    if "rate_limit_exceeded" in error_text or "Rate limit reached" in error_text:
                        error_msg = (
                            "Error: Daily token rate limit reached. "
                            "Try again later, or reduce token usage with a smaller model/output limit "
                            "(GROQ_MODEL, GROQ_MAX_TOKENS)."
                        )
                    else:
                        error_msg = f"Error: {error_text}"
                    st.error(error_msg)
                    print(f"❌ Agent Error: {e}")

    if st.button("Clear Chat"):
        st.session_state.chat_history = []
        st.rerun()
