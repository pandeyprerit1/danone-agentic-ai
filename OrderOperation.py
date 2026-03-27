import os
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Any, List, Union
import json
import base64
import random

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


def _search_orders_by_chargebee_invoice_impl(
    chargebee_invoice_id: str,
    limit: int = 10
) -> Dict:
    """Search orders in commercetools by Chargebee invoice ID (cbOrderId custom field)."""
    
    token = get_ct_token()
    project_key = os.getenv("COMMERCETOOLS_PROJECT_KEY")
    url = f"{os.getenv('COMMERCETOOLS_API_URL')}/{project_key}/orders"
    
    # Search for orders where custom field cbOrderId matches the Chargebee invoice ID
    filters = [
        f'custom(fields(cbOrderId = "{chargebee_invoice_id}"))'
    ]
    
    params = {
        "where": " AND ".join(filters),
        "sort": "createdAt desc",
        "limit": limit
    }
    
    print(f"\n🔍 [SEARCH_ORDERS_BY_CB_INVOICE] URL: {url}")
    print(f"🔍 [SEARCH_ORDERS_BY_CB_INVOICE] Params: {params}")
    
    resp = requests.get(
        url,
        params=params,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    )
    
    print(f"🔍 [SEARCH_ORDERS_BY_CB_INVOICE] Status Code: {resp.status_code}")
    
    if resp.status_code != 200:
        error_msg = {"error": resp.text, "status_code": resp.status_code}
        print(f"❌ [SEARCH_ORDERS_BY_CB_INVOICE] Error: {error_msg}")
        return error_msg
    
    data = resp.json()
    
    # Summarize orders
    summarized_orders = []
    for order in data.get("results", []):
        custom_fields = order.get("custom", {}).get("fields", {})
        summarized_order = {
            "id": order.get("id"),
            "orderNumber": order.get("orderNumber"),
            "createdAt": order.get("createdAt"),
            "totalPrice": order.get("totalPrice", {}).get("centAmount", 0) / 100,
            "currency": order.get("totalPrice", {}).get("currencyCode", "EUR"),
            "orderState": order.get("orderState"),
            "paymentState": order.get("paymentState"),
            "customerEmail": order.get("customerEmail"),
            "lineItemsCount": len(order.get("lineItems", [])),
            "cbOrderId": custom_fields.get("cbOrderId")
        }
        summarized_orders.append(summarized_order)
    
    result = {
        "total": data.get("total", 0),
        "orders": summarized_orders,
        "chargebee_invoice_id": chargebee_invoice_id
    }
    
    print(f"✅ [SEARCH_ORDERS_BY_CB_INVOICE] Found {len(summarized_orders)} orders for Chargebee invoice {chargebee_invoice_id}")
    return result


def _create_discount_impl(
    name: str,
    code: str,
    discount_type: str = "percentage",
    value: float = 10.0,
    description: Optional[str] = None,
    valid_from: Optional[str] = None,
    valid_until: Optional[str] = None,
    max_uses: Optional[int] = None
) -> Dict:
    """Create a discount code in Commercetools with associated cart discount."""
    
    token = get_ct_token()
    project_key = os.getenv("COMMERCETOOLS_PROJECT_KEY")
    api_url = os.getenv("COMMERCETOOLS_API_URL")
    
    # First, create the cart discount
    cart_discount_url = f"{api_url}/{project_key}/cart-discounts"
    
    # Build the cart discount payload based on type
    if discount_type.lower() == "percentage":
        discount_value = {
            "type": "relative",
            "permyriad": int(value * 100)  # Convert percentage to permyriad (0.1 = 1000)
        }
    elif discount_type.lower() == "absolute":
        discount_value = {
            "type": "absolute",
            "money": [
                {
                    "centAmount": int(value * 100),  # Convert to cents
                    "currencyCode": "EUR"
                }
            ]
        }
    else:
        return {"error": f"Unsupported discount type: {discount_type}. Use 'percentage' or 'absolute'."}
    
    # Retry logic for sortOrder
    max_retries = 3
    for attempt in range(max_retries):
        sort_order = str(random.randint(1, 999) / 1000)  # Generate decimal string without trailing zeros
        cart_discount_payload = {
            "name": {"en": name},
            "description": {"en": description or f"Discount: {name}"},
            "value": discount_value,
            "cartPredicate": "1=1",  # Apply to all carts
            "target": {"type": "lineItems", "predicate": "1=1"},  # Apply to all line items
            "sortOrder": sort_order,
            "isActive": True
        }
        
        if valid_from:
            cart_discount_payload["validFrom"] = valid_from
        if valid_until:
            cart_discount_payload["validUntil"] = valid_until
        
        print(f"\n💰 [CREATE_DISCOUNT] Creating cart discount (attempt {attempt + 1})...")
        print(f"💰 [CREATE_DISCOUNT] URL: {cart_discount_url}")
        print(f"💰 [CREATE_DISCOUNT] Payload: {json.dumps(cart_discount_payload, indent=2)}")
        
        cart_discount_resp = requests.post(
            cart_discount_url,
            json=cart_discount_payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        
        print(f"💰 [CREATE_DISCOUNT] Cart discount status: {cart_discount_resp.status_code}")
        
        if cart_discount_resp.status_code in (200, 201):
            cart_discount_data = cart_discount_resp.json()
            cart_discount_id = cart_discount_data.get("id")
            cart_discount_version = cart_discount_data.get("version")
            print(f"✅ [CREATE_DISCOUNT] Cart discount created: {cart_discount_id}")
            break  # success
        
        # Check if it's the duplicate sortOrder error
        try:
            error_data = cart_discount_resp.json()
            error_message = error_data.get("message", "").lower()
            if "duplicate value" in error_message and "sortorder" in error_message:
                print(f"⚠️ [CREATE_DISCOUNT] Duplicate sortOrder '{sort_order}', retrying...")
                continue
            else:
                return {"error": f"Failed to create cart discount: {cart_discount_resp.status_code} - {cart_discount_resp.text}"}
        except json.JSONDecodeError:
            return {"error": f"Failed to create cart discount: {cart_discount_resp.status_code} - {cart_discount_resp.text}"}
    else:
        return {"error": "Failed to create cart discount after 3 attempts due to duplicate sortOrder"}
    
    # Now create the discount code
    discount_code_url = f"{api_url}/{project_key}/discount-codes"
    
    discount_code_payload = {
        "key": f"{code.lower()}_code_{int(datetime.now(timezone.utc).timestamp())}",  # Required unique key with timestamp
        "name": {"en": name},
        "description": {"en": description or f"Discount code: {name}"},
        "code": code.upper(),  # Discount codes are typically uppercase
        "cartDiscounts": [{"typeId": "cart-discount", "id": cart_discount_id}],
        "isActive": True
    }
    
    if max_uses:
        discount_code_payload["maxApplications"] = max_uses
        discount_code_payload["maxApplicationsPerCustomer"] = 1
    
    if valid_from:
        discount_code_payload["validFrom"] = valid_from
    if valid_until:
        discount_code_payload["validUntil"] = valid_until
    
    print(f"\n🎫 [CREATE_DISCOUNT] Creating discount code...")
    print(f"🎫 [CREATE_DISCOUNT] URL: {discount_code_url}")
    print(f"🎫 [CREATE_DISCOUNT] Payload: {json.dumps(discount_code_payload, indent=2)}")
    
    discount_code_resp = requests.post(
        discount_code_url,
        json=discount_code_payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    )
    
    print(f"🎫 [CREATE_DISCOUNT] Discount code status: {discount_code_resp.status_code}")
    
    if discount_code_resp.status_code not in (200, 201):
        print(f"❌ [CREATE_DISCOUNT] Discount code error response: {discount_code_resp.text}")
        # Try to clean up the cart discount if discount code creation failed
        print(f"❌ [CREATE_DISCOUNT] Failed to create discount code, cleaning up cart discount...")
        delete_resp = requests.delete(
            f"{api_url}/{project_key}/cart-discounts/{cart_discount_id}?version={cart_discount_version}",
            headers={"Authorization": f"Bearer {token}"}
        )
        print(f"🗑️ [CREATE_DISCOUNT] Cart discount cleanup status: {delete_resp.status_code}")
        if delete_resp.status_code not in (200, 201):
            print(f"⚠️ [CREATE_DISCOUNT] Failed to cleanup cart discount: {delete_resp.text}")
        return {"error": f"Failed to create discount code: {discount_code_resp.status_code} - {discount_code_resp.text}"}
    
    discount_code_data = discount_code_resp.json()
    
    result = {
        "success": True,
        "discount_code": {
            "id": discount_code_data.get("id"),
            "code": discount_code_data.get("code"),
            "name": discount_code_data.get("name", {}).get("en"),
            "is_active": discount_code_data.get("isActive"),
            "max_applications": discount_code_data.get("maxApplications"),
            "valid_from": discount_code_data.get("validFrom"),
            "valid_until": discount_code_data.get("validUntil")
        },
        "cart_discount": {
            "id": cart_discount_id,
            "name": cart_discount_data.get("name", {}).get("en"),
            "type": discount_type,
            "value": value,
            "is_active": cart_discount_data.get("isActive")
        },
        "message": f"Discount code '{code.upper()}' created successfully"
    }
    
    print(f"✅ [CREATE_DISCOUNT] Discount created successfully: {code.upper()}")
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


# ====================== CHARGEBEE FUNCTIONS ======================

def _get_chargebee_headers():
    """Get headers for Chargebee API requests."""
    api_key = os.getenv("CHARGEBEE_API_KEY")
    if not api_key:
        return None
    import base64
    auth = base64.b64encode(f"{api_key}:".encode()).decode()
    return {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json"
    }

def _search_all_invoices_impl(
    limit: int = 10,
    offset: Optional[Union[str, int]] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> Dict:
    """Search all invoices in Chargebee. Returns compact invoice summaries to minimize token usage."""
    
    headers = _get_chargebee_headers()
    if not headers:
        return {"error": "Chargebee API key not configured"}
    
    site = os.getenv("CHARGEBEE_SITE")
    if not site:
        return {"error": "Chargebee site not configured"}
    
    # Enforce maximum limit of 20 to prevent token explosion
    limit = min(limit, 20)
    
    url = f"https://{site}.chargebee.com/api/v2/invoices"
    
    params = {"limit": limit}
    if offset is not None and str(offset).strip():
        params["offset"] = str(offset)
    if status:
        params["status[is]"] = status
    if date_from:
        params["date[after]"] = date_from
    if date_to:
        params["date[before]"] = date_to
    
    print(f"\n📄 [SEARCH_INVOICES] URL: {url}")
    print(f"📄 [SEARCH_INVOICES] Params: {params}")
    
    try:
        resp = requests.get(url, headers=headers, params=params)
        print(f"📄 [SEARCH_INVOICES] Status Code: {resp.status_code}")
        
        if resp.status_code != 200:
            return {"error": f"Chargebee API error: {resp.status_code} - {resp.text}"}
        
        data = resp.json()
        
        # Minimal invoice summary to save tokens
        summarized_invoices = []
        for invoice in data.get("list", []):
            inv = invoice.get("invoice", {})
            customer = invoice.get("customer", {})
            
            summarized_invoice = {
                "id": inv.get("id"),
                "status": inv.get("status"),
                "total": round(inv.get("total", 0) / 100, 2),
                "due": round(inv.get("amount_due", 0) / 100, 2),
                "date": inv.get("date"),
                "email": customer.get("email")
            }
            summarized_invoices.append(summarized_invoice)
        
        result = {
            "total": len(summarized_invoices),
            "invoices": summarized_invoices,
            "next_offset": data.get("next_offset"),
            "has_more": data.get("next_offset") is not None
        }
        
        print(f"✅ [SEARCH_INVOICES] Found {len(summarized_invoices)} invoices")
        return result
        
    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}

def _get_invoice_detail_impl(invoice_id: str) -> Dict:
    """Get detailed information about a specific invoice by ID."""
    
    headers = _get_chargebee_headers()
    if not headers:
        return {"error": "Chargebee API key not configured"}
    
    site = os.getenv("CHARGEBEE_SITE")
    if not site:
        return {"error": "Chargebee site not configured"}
    
    url = f"https://{site}.chargebee.com/api/v2/invoices/{invoice_id}"
    
    print(f"\n📋 [GET_INVOICE] URL: {url}")
    
    try:
        resp = requests.get(url, headers=headers)
        print(f"📋 [GET_INVOICE] Status Code: {resp.status_code}")
        
        if resp.status_code == 404:
            return {"error": f"Invoice not found: {invoice_id}"}
        if resp.status_code != 200:
            return {"error": f"Chargebee API error: {resp.status_code} - {resp.text}"}
        
        data = resp.json()
        inv = data.get("invoice", {})
        customer = data.get("customer", {})
        
        # Build detailed invoice response
        detail = {
            "id": inv.get("id"),
            "customer_id": inv.get("customer_id"),
            "customer_email": customer.get("email"),
            "customer_name": f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip(),
            "status": inv.get("status"),
            "invoice_number": inv.get("number"),
            "total": round(inv.get("total", 0) / 100, 2),
            "amount_paid": round(inv.get("amount_paid", 0) / 100, 2),
            "amount_due": round(inv.get("amount_due", 0) / 100, 2),
            "currency": inv.get("currency_code", "USD"),
            "date": inv.get("date"),
            "due_date": inv.get("due_date"),
            "subscription_id": inv.get("subscription_id"),
            "description": inv.get("description"),
            "line_items_count": len(inv.get("line_items", [])),
            "line_items": [
                {
                    "description": item.get("description"),
                    "qty": item.get("quantity"),
                    "amount": round(item.get("amount", 0) / 100, 2)
                }
                for item in inv.get("line_items", [])
            ]
        }
        
        print(f"✅ [GET_INVOICE] Retrieved invoice {invoice_id}")
        return detail
        
    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}

def _search_invoices_by_email_impl(
    customer_email: str,
    limit: int = 10,
    offset: Optional[Union[str, int]] = None,
    status: Optional[str] = None
) -> Dict:
    """Search invoices for a specific customer by email. Returns compact invoice summaries to minimize token usage."""
    
    headers = _get_chargebee_headers()
    if not headers:
        return {"error": "Chargebee API key not configured"}
    
    site = os.getenv("CHARGEBEE_SITE")
    if not site:
        return {"error": "Chargebee site not configured"}
    
    # First, find the customer by email
    customer_url = f"https://{site}.chargebee.com/api/v2/customers"
    customer_params = {"email[is]": customer_email}
    
    print(f"\n👤 [FIND_CUSTOMER] URL: {customer_url}")
    print(f"👤 [FIND_CUSTOMER] Params: {customer_params}")
    
    try:
        customer_resp = requests.get(customer_url, headers=headers, params=customer_params)
        print(f"👤 [FIND_CUSTOMER] Status Code: {customer_resp.status_code}")
        
        if customer_resp.status_code != 200:
            return {"error": f"Failed to find customer: {customer_resp.status_code} - {customer_resp.text}"}
        
        customer_data = customer_resp.json()
        customers = customer_data.get("list", [])
        
        if not customers:
            return {"total": 0, "invoices": [], "message": f"No customer found with email: {customer_email}"}
        
        customer_id = customers[0].get("customer", {}).get("id")
        if not customer_id:
            return {"error": "Customer found but no ID available"}
        
        print(f"👤 [FIND_CUSTOMER] Found customer ID: {customer_id}")
        
        # Now get invoices for this customer
        invoice_url = f"https://{site}.chargebee.com/api/v2/invoices"
        # Enforce maximum limit of 20 to prevent token explosion
        safe_limit = min(limit, 20)
        invoice_params = {"customer_id[is]": customer_id, "limit": safe_limit}
        
        if offset is not None and str(offset).strip():
            invoice_params["offset"] = str(offset)
        if status:
            invoice_params["status[is]"] = status
        
        print(f"\n📄 [SEARCH_CUSTOMER_INVOICES] URL: {invoice_url}")
        print(f"📄 [SEARCH_CUSTOMER_INVOICES] Params: {invoice_params}")
        
        invoice_resp = requests.get(invoice_url, headers=headers, params=invoice_params)
        print(f"📄 [SEARCH_CUSTOMER_INVOICES] Status Code: {invoice_resp.status_code}")
        
        if invoice_resp.status_code != 200:
            return {"error": f"Failed to get invoices: {invoice_resp.status_code} - {invoice_resp.text}"}
        
        invoice_data = invoice_resp.json()
        
        # Minimal invoice summary to save tokens
        summarized_invoices = []
        for invoice in invoice_data.get("list", []):
            inv = invoice.get("invoice", {})
            customer = invoice.get("customer", {})
            
            summarized_invoice = {
                "id": inv.get("id"),
                "status": inv.get("status"),
                "total": round(inv.get("total", 0) / 100, 2),
                "due": round(inv.get("amount_due", 0) / 100, 2),
                "date": inv.get("date"),
                "email": customer.get("email")
            }
            summarized_invoices.append(summarized_invoice)
        
        result = {
            "total": len(summarized_invoices),
            "invoices": summarized_invoices,
            "customer_id": customer_id,
            "next_offset": invoice_data.get("next_offset"),
            "has_more": invoice_data.get("next_offset") is not None
        }
        
        print(f"✅ [SEARCH_CUSTOMER_INVOICES] Found {len(summarized_invoices)} invoices for customer {customer_email}")
        return result
        
    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}


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

@tool
def search_orders_by_chargebee_invoice(
    chargebee_invoice_id: str,
    limit: int = 10
) -> Dict:
    """Search orders in commercetools by Chargebee invoice ID (cbOrderId custom field). Links orders to their corresponding Chargebee invoices."""
    return _search_orders_by_chargebee_invoice_impl(
        chargebee_invoice_id=chargebee_invoice_id,
        limit=limit
    )

@tool
def create_discount(
    name: str,
    code: str,
    discount_type: str = "percentage",
    value: float = 10.0,
    description: Optional[str] = None,
    valid_from: Optional[str] = None,
    valid_until: Optional[str] = None,
    max_uses: Optional[int] = None
) -> Dict:
    """Create a discount code in Commercetools. Type can be 'percentage' (e.g., 10.0 for 10%) or 'absolute' (e.g., 5.0 for €5). Dates in ISO format (YYYY-MM-DDTHH:MM:SS)."""
    return _create_discount_impl(
        name=name,
        code=code,
        discount_type=discount_type,
        value=value,
        description=description,
        valid_from=valid_from,
        valid_until=valid_until,
        max_uses=max_uses
    )

# Chargebee Tools
@tool
def search_all_invoices(
    limit: int = 10,
    offset: Optional[Union[str, int]] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> Dict:
    """Search all invoices in Chargebee. Status can be 'paid', 'posted', 'payment_due', 'not_paid', 'voided'. Dates in YYYY-MM-DD. Max 20 results per query (for token efficiency)."""
    return _search_all_invoices_impl(
        limit=limit,
        offset=offset,
        status=status,
        date_from=date_from,
        date_to=date_to
    )

@tool
def search_invoices_by_email(
    customer_email: str,
    limit: int = 10,
    offset: Optional[Union[str, int]] = None,
    status: Optional[str] = None
) -> Dict:
    """Search invoices for a specific customer by email. Status: 'paid', 'posted', 'payment_due', 'not_paid', 'voided'. Max 20 results per query."""
    return _search_invoices_by_email_impl(
        customer_email=customer_email,
        limit=limit,
        offset=offset,
        status=status
    )

@tool
def get_invoice_detail(invoice_id: str) -> Dict:
    """Get detailed information about a specific invoice by ID. Use this to get full line items and details about an invoice."""
    return _get_invoice_detail_impl(invoice_id)

# ====================== AGENT ======================
def run_agent(user_input: str, llm: ChatGroq) -> str:
    """Simple agent loop that handles tool calls."""
    
    # Map tool names to actual implementations
    tools_impl = {
        "search_orders": _search_orders_impl,
        "search_orders_by_chargebee_invoice": _search_orders_by_chargebee_invoice_impl,
        "create_discount": _create_discount_impl,
        "process_orders": _process_orders_impl,
        "search_all_invoices": _search_all_invoices_impl,
        "search_invoices_by_email": _search_invoices_by_email_impl,
        "get_invoice_detail": _get_invoice_detail_impl
    }
    
    # Bind tools to LLM
    llm_with_tools = llm.bind_tools([search_orders, search_orders_by_chargebee_invoice, create_discount, process_orders, search_all_invoices, search_invoices_by_email, get_invoice_detail])
    
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
st.set_page_config(page_title="Order & Invoice Agent", layout="wide")

st.title("🛒 Order & Invoice Search Agent")

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