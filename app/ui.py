import streamlit as st
from langchain_groq import ChatGroq

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
                    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.1)
                    response = run_agent(user_input, llm)
                    print(f"✅ [AGENT] Final response: {response}")
                    st.markdown(response)

                    st.session_state.chat_history.append({"role": "assistant", "content": response})
                except Exception as e:
                    error_msg = f"Error: {str(e)}"
                    st.error(error_msg)
                    print(f"❌ Agent Error: {e}")

    if st.button("Clear Chat"):
        st.session_state.chat_history = []
        st.rerun()
