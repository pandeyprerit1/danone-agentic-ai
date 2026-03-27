import json
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests

from .config import get_ct_token


def _search_orders_impl(
    customer_email: Optional[str] = None,
    order_number: Optional[str] = None,
    order_state: Optional[str] = None,
    payment_state: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    min_total: Optional[float] = None,
    limit: int = 10,
) -> Dict:
    """Search orders in commercetools."""

    token = get_ct_token()

    if order_number and not any([customer_email, order_state, payment_state, min_total]):
        url = f"{os.getenv('COMMERCETOOLS_API_URL')}/{os.getenv('COMMERCETOOLS_PROJECT_KEY')}/orders/order-number={order_number}"

        print(f"\n🔍 [SEARCH_ORDERS] Direct URL: {url}")

        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
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
                "lineItemsCount": len(order.get("lineItems", [])),
            }

            result = {"total": 1, "orders": [summarized_order]}
            print(f"✅ [SEARCH_ORDERS] Found order: {order_number}")
            return result
        if resp.status_code == 404:
            print(f"⚠️ [SEARCH_ORDERS] Order {order_number} not found via direct endpoint, trying search...")
        else:
            error_msg = {"error": resp.text or resp.reason or "Unknown error", "status_code": resp.status_code}
            print(f"❌ [SEARCH_ORDERS] Error: {error_msg}")
            return error_msg

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
        filters.append(f"totalPrice.centAmount >= {int(min_total * 100)}")

    if not created_from:
        created_from = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    if not created_to:
        created_to = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    filters.append(f'createdAt >= "{created_from}" AND createdAt <= "{created_to}"')

    params = {"where": " AND ".join(filters), "sort": "createdAt desc", "limit": limit}

    print(f"\n🔍 [SEARCH_ORDERS] URL: {url}")
    print(f"🔍 [SEARCH_ORDERS] Params: {params}")

    resp = requests.get(
        url,
        params=params,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )

    print(f"🔍 [SEARCH_ORDERS] Status Code: {resp.status_code}")

    if resp.status_code != 200:
        error_msg = {"error": resp.text, "status_code": resp.status_code}
        print(f"❌ [SEARCH_ORDERS] Error: {error_msg}")
        return error_msg

    data = resp.json()

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
            "lineItemsCount": len(order.get("lineItems", [])),
        }
        summarized_orders.append(summarized_order)

    result = {"total": data.get("total", 0), "orders": summarized_orders}
    return result


def _search_orders_by_chargebee_invoice_impl(chargebee_invoice_id: str, limit: int = 10) -> Dict:
    """Search orders in commercetools by Chargebee invoice ID (cbOrderId custom field)."""

    token = get_ct_token()
    project_key = os.getenv("COMMERCETOOLS_PROJECT_KEY")
    url = f"{os.getenv('COMMERCETOOLS_API_URL')}/{project_key}/orders"

    filters = [f'custom(fields(cbOrderId = "{chargebee_invoice_id}"))']

    params = {"where": " AND ".join(filters), "sort": "createdAt desc", "limit": limit}

    print(f"\n🔍 [SEARCH_ORDERS_BY_CB_INVOICE] URL: {url}")
    print(f"🔍 [SEARCH_ORDERS_BY_CB_INVOICE] Params: {params}")

    resp = requests.get(
        url,
        params=params,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )

    print(f"🔍 [SEARCH_ORDERS_BY_CB_INVOICE] Status Code: {resp.status_code}")

    if resp.status_code != 200:
        error_msg = {"error": resp.text, "status_code": resp.status_code}
        print(f"❌ [SEARCH_ORDERS_BY_CB_INVOICE] Error: {error_msg}")
        return error_msg

    data = resp.json()

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
            "cbOrderId": custom_fields.get("cbOrderId"),
        }
        summarized_orders.append(summarized_order)

    result = {
        "total": data.get("total", 0),
        "orders": summarized_orders,
        "chargebee_invoice_id": chargebee_invoice_id,
    }

    print(
        f"✅ [SEARCH_ORDERS_BY_CB_INVOICE] Found {len(summarized_orders)} orders for Chargebee invoice {chargebee_invoice_id}"
    )
    return result


def _create_discount_impl(
    name: str,
    code: str,
    discount_type: str = "percentage",
    value: float = 10.0,
    description: Optional[str] = None,
    valid_from: Optional[str] = None,
    valid_until: Optional[str] = None,
    max_uses: Optional[int] = None,
) -> Dict:
    """Create a discount code in Commercetools with associated cart discount."""

    token = get_ct_token()
    project_key = os.getenv("COMMERCETOOLS_PROJECT_KEY")
    api_url = os.getenv("COMMERCETOOLS_API_URL")

    cart_discount_url = f"{api_url}/{project_key}/cart-discounts"

    if discount_type.lower() == "percentage":
        discount_value = {"type": "relative", "permyriad": int(value * 100)}
    elif discount_type.lower() == "absolute":
        discount_value = {
            "type": "absolute",
            "money": [{"centAmount": int(value * 100), "currencyCode": "EUR"}],
        }
    else:
        return {"error": f"Unsupported discount type: {discount_type}. Use 'percentage' or 'absolute'."}

    max_retries = 3
    for attempt in range(max_retries):
        sort_order = str(random.randint(1, 999) / 1000)
        cart_discount_payload = {
            "name": {"en": name},
            "description": {"en": description or f"Discount: {name}"},
            "value": discount_value,
            "cartPredicate": "1=1",
            "target": {"type": "lineItems", "predicate": "1=1"},
            "sortOrder": sort_order,
            "requiresDiscountCode": True,
            "isActive": True,
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
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )

        print(f"💰 [CREATE_DISCOUNT] Cart discount status: {cart_discount_resp.status_code}")

        if cart_discount_resp.status_code in (200, 201):
            cart_discount_data = cart_discount_resp.json()
            cart_discount_id = cart_discount_data.get("id")
            cart_discount_version = cart_discount_data.get("version")
            print(f"✅ [CREATE_DISCOUNT] Cart discount created: {cart_discount_id}")
            break

        try:
            error_data = cart_discount_resp.json()
            error_message = error_data.get("message", "").lower()
            if "duplicate value" in error_message and "sortorder" in error_message:
                print(f"⚠️ [CREATE_DISCOUNT] Duplicate sortOrder '{sort_order}', retrying...")
                continue
            return {
                "error": f"Failed to create cart discount: {cart_discount_resp.status_code} - {cart_discount_resp.text}"
            }
        except json.JSONDecodeError:
            return {
                "error": f"Failed to create cart discount: {cart_discount_resp.status_code} - {cart_discount_resp.text}"
            }
    else:
        return {"error": "Failed to create cart discount after 3 attempts due to duplicate sortOrder"}

    discount_code_url = f"{api_url}/{project_key}/discount-codes"

    discount_code_payload = {
        "key": f"{code.lower()}_code_{int(datetime.now(timezone.utc).timestamp())}",
        "name": {"en": name},
        "description": {"en": description or f"Discount code: {name}"},
        "code": code.upper(),
        "cartDiscounts": [{"typeId": "cart-discount", "id": cart_discount_id}],
        "isActive": True,
    }

    if max_uses:
        discount_code_payload["maxApplications"] = max_uses
        discount_code_payload["maxApplicationsPerCustomer"] = 1

    if valid_from:
        discount_code_payload["validFrom"] = valid_from
    if valid_until:
        discount_code_payload["validUntil"] = valid_until

    print("\n🎫 [CREATE_DISCOUNT] Creating discount code...")
    print(f"🎫 [CREATE_DISCOUNT] URL: {discount_code_url}")
    print(f"🎫 [CREATE_DISCOUNT] Payload: {json.dumps(discount_code_payload, indent=2)}")

    discount_code_resp = requests.post(
        discount_code_url,
        json=discount_code_payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )

    print(f"🎫 [CREATE_DISCOUNT] Discount code status: {discount_code_resp.status_code}")

    if discount_code_resp.status_code not in (200, 201):
        print(f"❌ [CREATE_DISCOUNT] Discount code error response: {discount_code_resp.text}")
        print("❌ [CREATE_DISCOUNT] Failed to create discount code, cleaning up cart discount...")
        delete_resp = requests.delete(
            f"{api_url}/{project_key}/cart-discounts/{cart_discount_id}?version={cart_discount_version}",
            headers={"Authorization": f"Bearer {token}"},
        )
        print(f"🗑️ [CREATE_DISCOUNT] Cart discount cleanup status: {delete_resp.status_code}")
        if delete_resp.status_code not in (200, 201):
            print(f"⚠️ [CREATE_DISCOUNT] Failed to cleanup cart discount: {delete_resp.text}")
        return {
            "error": f"Failed to create discount code: {discount_code_resp.status_code} - {discount_code_resp.text}"
        }

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
            "valid_until": discount_code_data.get("validUntil"),
        },
        "cart_discount": {
            "id": cart_discount_id,
            "name": cart_discount_data.get("name", {}).get("en"),
            "type": discount_type,
            "value": value,
            "is_active": cart_discount_data.get("isActive"),
        },
        "message": f"Discount code '{code.upper()}' created successfully",
    }

    print(f"✅ [CREATE_DISCOUNT] Discount created successfully: {code.upper()}")
    return result


def _create_cart_discount_only_impl(
    name: str,
    discount_type: str = "percentage",
    value: float = 10.0,
    description: Optional[str] = None,
    valid_from: Optional[str] = None,
    valid_until: Optional[str] = None,
) -> Dict:
    """Create only a cart discount in Commercetools (auto-applies, no discount code)."""

    token = get_ct_token()
    project_key = os.getenv("COMMERCETOOLS_PROJECT_KEY")
    api_url = os.getenv("COMMERCETOOLS_API_URL")
    cart_discount_url = f"{api_url}/{project_key}/cart-discounts"

    if discount_type.lower() == "percentage":
        discount_value = {"type": "relative", "permyriad": int(value * 100)}
    elif discount_type.lower() == "absolute":
        discount_value = {
            "type": "absolute",
            "money": [{"centAmount": int(value * 100), "currencyCode": "EUR"}],
        }
    else:
        return {"error": f"Unsupported discount type: {discount_type}. Use 'percentage' or 'absolute'."}

    max_retries = 3
    for attempt in range(max_retries):
        sort_order = str(random.randint(1, 999) / 1000)
        cart_discount_payload = {
            "name": {"en": name},
            "description": {"en": description or f"Cart discount: {name}"},
            "value": discount_value,
            "cartPredicate": "1=1",
            "target": {"type": "lineItems", "predicate": "1=1"},
            "sortOrder": sort_order,
            "requiresDiscountCode": False,
            "isActive": True,
        }

        if valid_from:
            cart_discount_payload["validFrom"] = valid_from
        if valid_until:
            cart_discount_payload["validUntil"] = valid_until

        print(f"\n💰 [CREATE_CART_DISCOUNT_ONLY] Creating cart discount (attempt {attempt + 1})...")
        print(f"💰 [CREATE_CART_DISCOUNT_ONLY] URL: {cart_discount_url}")
        print(f"💰 [CREATE_CART_DISCOUNT_ONLY] Payload: {json.dumps(cart_discount_payload, indent=2)}")

        cart_discount_resp = requests.post(
            cart_discount_url,
            json=cart_discount_payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )

        print(f"💰 [CREATE_CART_DISCOUNT_ONLY] Status: {cart_discount_resp.status_code}")

        if cart_discount_resp.status_code in (200, 201):
            cart_discount_data = cart_discount_resp.json()
            print(f"✅ [CREATE_CART_DISCOUNT_ONLY] Created: {cart_discount_data.get('id')}")
            cart_discount_id = cart_discount_data.get("id")
            return {
                "success": True,
                "cart_discount": {
                    "id": cart_discount_id,
                    "name": cart_discount_data.get("name", {}).get("en"),
                    "type": discount_type,
                    "value": value,
                    "is_active": cart_discount_data.get("isActive"),
                    "requires_discount_code": cart_discount_data.get("requiresDiscountCode"),
                    "valid_from": cart_discount_data.get("validFrom"),
                    "valid_until": cart_discount_data.get("validUntil"),
                },
                "message": f"Cart Discount has been created successfully with discount id {cart_discount_id}",
            }

        try:
            error_data = cart_discount_resp.json()
            error_message = error_data.get("message", "").lower()
            if "duplicate value" in error_message and "sortorder" in error_message:
                print(f"⚠️ [CREATE_CART_DISCOUNT_ONLY] Duplicate sortOrder '{sort_order}', retrying...")
                continue
        except json.JSONDecodeError:
            pass

        return {"error": f"Failed to create cart discount: {cart_discount_resp.status_code} - {cart_discount_resp.text}"}

    return {"error": "Failed to create cart discount after 3 attempts due to duplicate sortOrder"}


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

    payload = {"version": version, "actions": [{"action": "changePaymentState", "paymentState": new_state}]}

    print(f"\n💳 [CHANGE_PAYMENT_STATE] URL: {url}")
    print(f"💳 [CHANGE_PAYMENT_STATE] Payload: {payload}")

    resp = requests.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )

    print(f"💳 [CHANGE_PAYMENT_STATE] Status Code: {resp.status_code}")

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
    limit: int = 20,
) -> Dict:
    """Set matching orders to a single target payment state (Pending or Paid)."""

    normalized_target = target_payment_state.capitalize()
    if normalized_target not in ("Pending", "Paid"):
        return {
            "error": "Invalid target_payment_state. Use 'Pending' or 'Paid'.",
            "provided": target_payment_state,
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
            limit=limit,
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

        state_res = _change_payment_state(order_id, current_version, normalized_target)
        if "error" in state_res:
            details.append(
                {
                    "orderId": order_id,
                    "status": f"failed_{normalized_target.lower()}",
                    "error": state_res["error"],
                }
            )
            continue

        details.append(
            {
                "orderId": order_id,
                "status": "processed",
                "target_payment_state": normalized_target,
                "version": state_res.get("version", current_version),
            }
        )
        processed += 1

    return {"total": len(order_ids), "processed": processed, "details": details}
