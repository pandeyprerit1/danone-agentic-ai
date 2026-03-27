import base64
import os
from typing import Dict, Optional, Union

import requests


def _get_chargebee_headers() -> Optional[Dict[str, str]]:
    """Get headers for Chargebee API requests."""
    api_key = os.getenv("CHARGEBEE_API_KEY")
    if not api_key:
        return None
    auth = base64.b64encode(f"{api_key}:".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}


def _search_all_invoices_impl(
    limit: int = 10,
    offset: Optional[Union[str, int]] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict:
    """Search all invoices in Chargebee. Returns compact invoice summaries to minimize token usage."""

    headers = _get_chargebee_headers()
    if not headers:
        return {"error": "Chargebee API key not configured"}

    site = os.getenv("CHARGEBEE_SITE")
    if not site:
        return {"error": "Chargebee site not configured"}

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
                "email": customer.get("email"),
            }
            summarized_invoices.append(summarized_invoice)

        result = {
            "total": len(summarized_invoices),
            "invoices": summarized_invoices,
            "next_offset": data.get("next_offset"),
            "has_more": data.get("next_offset") is not None,
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
                    "amount": round(item.get("amount", 0) / 100, 2),
                }
                for item in inv.get("line_items", [])
            ],
        }

        print(f"✅ [GET_INVOICE] Retrieved invoice {invoice_id}")
        return detail

    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}


def _search_invoices_by_email_impl(
    customer_email: str,
    limit: int = 10,
    offset: Optional[Union[str, int]] = None,
    status: Optional[str] = None,
) -> Dict:
    """Search invoices for a specific customer by email. Returns compact invoice summaries to minimize token usage."""

    headers = _get_chargebee_headers()
    if not headers:
        return {"error": "Chargebee API key not configured"}

    site = os.getenv("CHARGEBEE_SITE")
    if not site:
        return {"error": "Chargebee site not configured"}

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

        invoice_url = f"https://{site}.chargebee.com/api/v2/invoices"
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
                "email": customer.get("email"),
            }
            summarized_invoices.append(summarized_invoice)

        result = {
            "total": len(summarized_invoices),
            "invoices": summarized_invoices,
            "customer_id": customer_id,
            "next_offset": invoice_data.get("next_offset"),
            "has_more": invoice_data.get("next_offset") is not None,
        }

        print(f"✅ [SEARCH_CUSTOMER_INVOICES] Found {len(summarized_invoices)} invoices for customer {customer_email}")
        return result

    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}
