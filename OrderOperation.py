import os
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Any, List
import json

import streamlit as st
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# ====================== LOAD ENV ======================
load_dotenv()

# ====================== TOKEN ======================
def get_ct_token() -> str:
    now = datetime.now(timezone.utc).timestamp()

    # Use Streamlit session state for token caching
    if "ct_token" in st.session_state and "ct_token_expires" in st.session_state:
        if now < st.session_state["ct_token_expires"]:
            return st.session_state["ct_token"]

    # Token expired or not set, get new one
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
        data={
            "grant_type": "client_credentials",
            "scope": scope
        }
    ).json()

    print(f"🔐 [AUTH] Response: {resp}")

    if "access_token" not in resp:
        st.error(f"Auth failed: {resp}")
        print(f"❌ [AUTH] Failed: {resp}")
        st.stop()

    token = resp["access_token"]
    expires_at = now + resp["expires_in"] - 60
    
    # Cache in session state
    st.session_state["ct_token"] = token
    st.session_state["ct_token_expires"] = expires_at
    
    print(f"✅ [AUTH] Token obtained, expires in {resp['expires_in']} seconds")
    return token

# ====================== TOOL ======================
# Original function
def _search_orders_impl(
    customer_email: Optional[str] = None,
    order_number: Optional[str] = None,
    order_state: Optional[str] = None,
    payment_state: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    min_total: Optional[float] = None,
    limit: int = 10
) -> Dict:
    """Search orders in commercetools."""

    token = get_ct_token()

    # If only order_number is provided, use the direct order-number endpoint
    if order_number and not any([customer_email, order_state, payment_state, min_total]):
        url = f"{os.getenv('COMMERCETOOLS_API_URL')}/{os.getenv('COMMERCETOOLS_PROJECT_KEY')}/orders/order-number={order_number}"

        print(f"\n🔍 [SEARCH_ORDERS] Direct URL: {url}")

        resp = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )

        print(f"🔍 [SEARCH_ORDERS] Status Code: {resp.status_code}")

        if resp.status_code == 200:
            order = resp.json()
            summarized_order = {
                "id": order.get("id"),
                "orderNumber": order.get("orderNumber"),
                "createdAt": order.get("createdAt"),
                "totalPrice": order.get("totalPrice", {}).get("centAmount", 0) / 100,
                "currency": order.get("totalPrice", {}).get("currencyCode", "EUR"),
                "orderState": order.get("orderState"),
                "paymentState": order.get("paymentState"),
                "customerEmail": order.get("customerEmail"),
                "lineItemsCount": len(order.get("lineItems", []))
            }

            result = {
                "total": 1,
                "orders": [summarized_order]
            }
            print(f"✅ [SEARCH_ORDERS] Found order: {order_number}")
            return result
        elif resp.status_code == 404:
            # Order not found via direct endpoint, fall back to search
            print(f"⚠️ [SEARCH_ORDERS] Order {order_number} not found via direct endpoint, trying search...")
        else:
            error_msg = {"error": resp.text or resp.reason or "Unknown error", "status_code": resp.status_code}
            print(f"❌ [SEARCH_ORDERS] Error: {error_msg}")
            return error_msg

    # Otherwise, use the search endpoint with filters
    url = f"{os.getenv('COMMERCETOOLS_API_URL')}/{os.getenv('COMMERCETOOLS_PROJECT_KEY')}/orders"

    filters = []

    if customer_email:
        filters.append(f'customerEmail = "{customer_email}"')
    if order_number:
        filters.append(f'orderNumber = "{order_number}"')
    if order_state:
        filters.append(f'orderState = "{order_state}"')
    if payment_state:
        filters.append(f'paymentState = "{payment_state}"')
    if min_total:
        filters.append(f'totalPrice.centAmount >= {int(min_total * 100)}')

    if not created_from:
        created_from = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    if not created_to:
        created_to = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    filters.append(
        f'createdAt >= "{created_from}" AND createdAt <= "{created_to}"'
    )

    params = {
        "where": " AND ".join(filters),
        "sort": "createdAt desc",
        "limit": limit
    }

    print(f"\n🔍 [SEARCH_ORDERS] URL: {url}")
    print(f"🔍 [SEARCH_ORDERS] Params: {params}")

    resp = requests.get(
        url,
        params=params,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    )

    print(f"🔍 [SEARCH_ORDERS] Status Code: {resp.status_code}")
    #print(f"🔍 [SEARCH_ORDERS] Response: {resp.text}")

    if resp.status_code != 200:
        error_msg = {"error": resp.text, "status_code": resp.status_code}
        print(f"❌ [SEARCH_ORDERS] Error: {error_msg}")
        return error_msg

    data = resp.json()
    #print(f"✅ [SEARCH_ORDERS] Parsed Data: {data}")

    # Summarize orders to reduce token usage
    summarized_orders = []
    for order in data.get("results", []):
        summarized_order = {
            "id": order.get("id"),
            "orderNumber": order.get("orderNumber"),
            "createdAt": order.get("createdAt"),
            "totalPrice": order.get("totalPrice", {}).get("centAmount", 0) / 100,
            "currency": order.get("totalPrice", {}).get("currencyCode", "EUR"),
            "orderState": order.get("orderState"),
            "paymentState": order.get("paymentState"),
            "customerEmail": order.get("customerEmail"),
            "lineItemsCount": len(order.get("lineItems", []))
        }
        summarized_orders.append(summarized_order)

    result = {
        "total": data.get("total", 0),
        "orders": summarized_orders
    }
    #print(f"✅ [SEARCH_ORDERS] Final Result: {result}")
    return result


def _get_order(order_id: str) -> Dict:
    token = get_ct_token()
    project_key = os.getenv("COMMERCETOOLS_PROJECT_KEY")
    url = f"{os.getenv('COMMERCETOOLS_API_URL')}/{project_key}/orders/{order_id}"

    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        return {"error": f"{resp.status_code} - {resp.text}"}
    return resp.json()


def _change_payment_state(order_id: str, version: int, new_state: str) -> Dict:
    token = get_ct_token()
    project_key = os.getenv("COMMERCETOOLS_PROJECT_KEY")
    url = f"{os.getenv('COMMERCETOOLS_API_URL')}/{project_key}/orders/{order_id}"

    payload = {
        "version": version,
        "actions": [{"action": "changePaymentState", "paymentState": new_state}]
    }

    print(f"\n💳 [CHANGE_PAYMENT_STATE] URL: {url}")
    print(f"💳 [CHANGE_PAYMENT_STATE] Payload: {payload}")

    resp = requests.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )

    print(f"💳 [CHANGE_PAYMENT_STATE] Status Code: {resp.status_code}")
    #print(f"💳 [CHANGE_PAYMENT_STATE] Response: {resp.text}")

    if resp.status_code not in (200, 201):
        return {"error": f"{resp.status_code} - {resp.text}", "orderId": order_id}

    return resp.json()


def _process_orders_impl(
    order_ids: Optional[List[str]] = None,
    customer_email: Optional[str] = None,
    order_number: Optional[str] = None,
    order_state: Optional[str] = None,
    payment_state: Optional[str] = None,
    target_payment_state: str = "Pending",
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    min_total: Optional[float] = None,
    limit: int = 20
) -> Dict:
    """Set matching orders to a single target payment state (Pending or Paid)."""

    normalized_target = target_payment_state.capitalize()
    if normalized_target not in ("Pending", "Paid"):
        return {
            "error": "Invalid target_payment_state. Use 'Pending' or 'Paid'.",
            "provided": target_payment_state
        }

    if not order_ids:
        search_result = _search_orders_impl(
            customer_email=customer_email,
            order_number=order_number,
            order_state=order_state,
            payment_state=payment_state,
            created_from=created_from,
            created_to=created_to,
            min_total=min_total,
            limit=limit
        )
        if "error" in search_result:
            return search_result

        order_ids = [o.get("id") for o in search_result.get("orders", []) if o.get("id")]

    if not order_ids:
        return {"total": 0, "processed": 0, "details": [], "message": "No orders found to process."}

    details = []
    processed = 0

    for order_id in order_ids:
        order_data = _get_order(order_id)
        if "error" in order_data:
            details.append({"orderId": order_id, "status": "error", "error": order_data["error"]})
            continue

        current_version = order_data.get("version")
        if current_version is None:
            details.append({"orderId": order_id, "status": "error", "error": "Missing order version"})
            continue

        # single-action change to requested target state
        state_res = _change_payment_state(order_id, current_version, normalized_target)
        if "error" in state_res:
            details.append({"orderId": order_id, "status": f"failed_{normalized_target.lower()}", "error": state_res["error"]})
            continue

        details.append({
            "orderId": order_id,
            "status": "processed",
            "target_payment_state": normalized_target,
            "version": state_res.get("version", current_version)
        })
        processed += 1

    return {
        "total": len(order_ids),
        "processed": processed,
        "details": details
    }


@tool
def process_orders(
    order_ids: Optional[List[str]] = None,
    customer_email: Optional[str] = None,
    order_number: Optional[str] = None,
    order_state: Optional[str] = None,
    payment_state: Optional[str] = None,
    target_payment_state: str = "Pending",
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    min_total: Optional[float] = None,
    limit: int = 20
) -> Dict:
    """Set matching orders to a single target payment state (Pending or Paid)."""
    return _process_orders_impl(
        order_ids=order_ids,
        customer_email=customer_email,
        order_number=order_number,
        order_state=order_state,
        payment_state=payment_state,
        target_payment_state=target_payment_state,
        created_from=created_from,
        created_to=created_to,
        min_total=min_total,
        limit=limit
    )

# Decorated version for LLM
@tool
def search_orders(
    customer_email: Optional[str] = None,
    order_number: Optional[str] = None,
    order_state: Optional[str] = None,
    payment_state: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    min_total: Optional[float] = None,
    limit: int = 10
) -> Dict:
    """Search orders in commercetools."""
    return _search_orders_impl(
        customer_email=customer_email,
        order_number=order_number,
        order_state=order_state,
        payment_state=payment_state,
        created_from=created_from,
        created_to=created_to,
        min_total=min_total,
        limit=limit
    )

# ====================== AGENT ======================
def run_agent(user_input: str, llm: ChatGroq) -> str:
    """Simple agent loop that handles tool calls."""
    
    # Map tool names to actual implementations
    tools_impl = {
        "search_orders": _search_orders_impl,
        "process_orders": _process_orders_impl
    }
    
    # Bind tools to LLM
    llm_with_tools = llm.bind_tools([search_orders, process_orders])
    
    messages = [HumanMessage(content=user_input)]
    
    print(f"\n🤖 [AGENT] Starting with input: {user_input}")
    
    # Agentic loop
    max_iterations = 5
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        print(f"\n📍 [AGENT] Iteration {iteration}")
        
        # Get response from LLM
        response = llm_with_tools.invoke(messages)
        messages.append(response)
        
        print(f"📍 [AGENT] Response type: {type(response)}")
        print(f"📍 [AGENT] Has tool_calls: {hasattr(response, 'tool_calls')}")
        
        # Check if there are tool calls
        if not hasattr(response, 'tool_calls') or not response.tool_calls:
            # No tool calls, return final response
            if hasattr(response, 'content'):
                print(f"✅ [AGENT] Final response: {response.content}")
                return response.content
            return str(response)
        
        # Process tool calls
        for tool_call in response.tool_calls:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("args", {})
            
            print(f"\n🔧 [AGENT] Calling tool: {tool_name} with args: {tool_args}")
            
            if tool_name in tools_impl:
                try:
                    # Call the actual implementation function
                    tool_result = tools_impl[tool_name](**tool_args)
                    #print(f"✅ [AGENT] Tool result: {tool_result}")
                    
                    # Add tool result to messages
                    messages.append(ToolMessage(
                        content=json.dumps(tool_result),
                        tool_call_id=tool_call.get("id", "")
                    ))
                except Exception as e:
                    error_result = {"error": str(e)}
                    print(f"❌ [AGENT] Tool execution error: {e}")
                    messages.append(ToolMessage(
                        content=json.dumps(error_result),
                        tool_call_id=tool_call.get("id", "")
                    ))
            else:
                print(f"❌ [AGENT] Unknown tool: {tool_name}")
                messages.append(ToolMessage(
                    content=json.dumps({"error": f"Unknown tool: {tool_name}"}),
                    tool_call_id=tool_call.get("id", "")
                ))
    
    return "Max iterations reached without final response"

# ====================== UI ======================
st.set_page_config(page_title="Order Agent", layout="wide")

st.title("🛒 Order Search Agent")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Display chat history
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Input
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

                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": response
                })

            except Exception as e:
                error_msg = f"Error: {str(e)}"
                st.error(error_msg)
                print(f"❌ Agent Error: {e}")

# Clear
if st.button("Clear Chat"):
    st.session_state.chat_history = []
    st.rerun()