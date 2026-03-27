import os
from datetime import datetime, timezone

import requests
import streamlit as st
from dotenv import load_dotenv


load_dotenv()


def get_ct_token() -> str:
    now = datetime.now(timezone.utc).timestamp()

    if "ct_token" in st.session_state and "ct_token_expires" in st.session_state:
        if now < st.session_state["ct_token_expires"]:
            return st.session_state["ct_token"]

    auth_url = os.getenv("COMMERCETOOLS_AUTH_URL")
    client_id = os.getenv("COMMERCETOOLS_CLIENT_ID")
    client_secret = os.getenv("COMMERCETOOLS_CLIENT_SECRET")
    scope = os.getenv("COMMERCETOOLS_SCOPE")

    print(f"\n🔐 [AUTH] URL: {auth_url}")
    print(f"🔐 [AUTH] Client ID: {client_id[:10]}..." if client_id else "🔐 [AUTH] Client ID: NOT SET")
    print(f"🔐 [AUTH] Client Secret: {'*' * 10}" if client_secret else "🔐 [AUTH] Client Secret: NOT SET")
    print(f"🔐 [AUTH] Scope: {scope}")

    resp = requests.post(
        auth_url,
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials", "scope": scope},
    ).json()

    print(f"🔐 [AUTH] Response: {resp}")

    if "access_token" not in resp:
        st.error(f"Auth failed: {resp}")
        print(f"❌ [AUTH] Failed: {resp}")
        st.stop()

    token = resp["access_token"]
    expires_at = now + resp["expires_in"] - 60

    st.session_state["ct_token"] = token
    st.session_state["ct_token_expires"] = expires_at

    print(f"✅ [AUTH] Token obtained, expires in {resp['expires_in']} seconds")
    return token
