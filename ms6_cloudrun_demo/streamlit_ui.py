"""
UI -- Streamlit front end for the M6 Cloud Run demo (cloudrun_demo/main.py).

Logs in once on load via /auth/login, caches the JWT, and sends both the
X-API-Key and Authorization: Bearer headers on every /chat call -- same
dual-auth requirement as curl/Swagger, just handled automatically instead
of pasted by hand every time.

IMPORTANT: this backend only has /chat (no /sql, no /memory/{id} -- those
services were dropped when M6 simplified to one container). The response
shape is exactly cloudrun_demo/main.py's ChatResponse: reply, model,
served_by, latency_ms, blocked_by_guardrail -- nothing else. This file
does not reference session_id/version/total_latency_ms, which don't exist
on this backend and would crash an unmodified copy of the old UI.

Set BACKEND_URL to your Cloud Run service URL (the $SERVICE_URL from the
build guide) -- not a Compose service name, this app doesn't run in that
stack.
"""
import os
import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "")
API_KEY = os.environ.get("API_KEY", "change-me-api-key")
DEMO_USERNAME = os.environ.get("DEMO_USERNAME", "demo")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo123")

st.set_page_config(page_title="M6 Demo Chat", page_icon="🤖")
st.title("M6 Demo — Chat")
st.caption(f"Backend: {BACKEND_URL or '(set BACKEND_URL to your Cloud Run URL)'}")

if not BACKEND_URL:
    st.error(
        "BACKEND_URL is not set. Set it to your Cloud Run service URL "
        "(the $SERVICE_URL from the build guide) and restart, e.g.:\n\n"
        "BACKEND_URL=https://m6-demo-xxxxx-uc.a.run.app streamlit run streamlit_ui.py"
    )
    st.stop()


def _auth_headers() -> dict:
    """Log in once per Streamlit session, cache the token, reuse it."""
    if "jwt_token" not in st.session_state:
        try:
            r = requests.post(
                f"{BACKEND_URL}/auth/login",
                json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD},
                timeout=10,
            )
            r.raise_for_status()
            st.session_state.jwt_token = r.json()["access_token"]
        except Exception as exc:
            st.session_state.jwt_token = None
            st.error(f"Login to backend failed: {exc}")
    return {"X-API-Key": API_KEY, "Authorization": f"Bearer {st.session_state.get('jwt_token', '')}"}


msg = st.text_input("Say something to the assistant", key="chat_input")
if st.button("Send", key="chat_send") and msg:
    try:
        r = requests.post(
            f"{BACKEND_URL}/chat", json={"message": msg}, headers=_auth_headers(), timeout=30
        )
        r.raise_for_status()
        data = r.json()
        if data.get("blocked_by_guardrail"):
            st.warning(f"**Blocked by guardrail:** {data['reply']}")
        else:
            st.markdown(f"**Assistant ({data['served_by']}):** {data['reply']}")
            st.caption(f"model={data['model']}  latency={data['latency_ms']}ms")
    except Exception as exc:
        st.error(f"Request failed: {exc}")
