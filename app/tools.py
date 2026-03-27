from typing import Dict, List, Optional, Union

from langchain_core.tools import tool

from .chargebee import _get_invoice_detail_impl, _search_all_invoices_impl, _search_invoices_by_email_impl
from .commercetools import (
    _create_cart_discount_only_impl,
    _create_discount_impl,
    _process_orders_impl,
    _search_orders_by_chargebee_invoice_impl,
    _search_orders_impl,
)


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
    limit: int = 20,
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
        limit=limit,
    )


@tool
def search_orders(
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
    return _search_orders_impl(
        customer_email=customer_email,
        order_number=order_number,
        order_state=order_state,
        payment_state=payment_state,
        created_from=created_from,
        created_to=created_to,
        min_total=min_total,
        limit=limit,
    )


@tool
def search_orders_by_chargebee_invoice(chargebee_invoice_id: str, limit: int = 10) -> Dict:
    """Search orders in commercetools by Chargebee invoice ID (cbOrderId custom field). Links orders to their corresponding Chargebee invoices."""
    return _search_orders_by_chargebee_invoice_impl(chargebee_invoice_id=chargebee_invoice_id, limit=limit)


@tool
def create_discount(
    name: str,
    code: str,
    discount_type: str = "percentage",
    value: float = 10.0,
    description: Optional[str] = None,
    valid_from: Optional[str] = None,
    valid_until: Optional[str] = None,
    max_uses: Optional[int] = None,
) -> Dict:
    """Create a discount code in Commercetools. Type can be 'percentage' (e.g., 10.0 for 10%) or 'absolute' (e.g., 5.0 for EUR5). Dates in ISO format (YYYY-MM-DDTHH:MM:SS)."""
    return _create_discount_impl(
        name=name,
        code=code,
        discount_type=discount_type,
        value=value,
        description=description,
        valid_from=valid_from,
        valid_until=valid_until,
        max_uses=max_uses,
    )


@tool
def create_cart_discount_only(
    name: str,
    discount_type: str = "percentage",
    value: float = 10.0,
    description: Optional[str] = None,
    valid_from: Optional[str] = None,
    valid_until: Optional[str] = None,
) -> Dict:
    """Create only a cart discount that auto-applies (no discount code)."""
    return _create_cart_discount_only_impl(
        name=name,
        discount_type=discount_type,
        value=value,
        description=description,
        valid_from=valid_from,
        valid_until=valid_until,
    )


@tool
def search_all_invoices(
    limit: int = 10,
    offset: Optional[Union[str, int]] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict:
    """Search all invoices in Chargebee. Status can be 'paid', 'posted', 'payment_due', 'not_paid', 'voided'. Dates in YYYY-MM-DD. Max 20 results per query (for token efficiency)."""
    return _search_all_invoices_impl(
        limit=limit,
        offset=offset,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )


@tool
def search_invoices_by_email(
    customer_email: str,
    limit: int = 10,
    offset: Optional[Union[str, int]] = None,
    status: Optional[str] = None,
) -> Dict:
    """Search invoices for a specific customer by email. Status: 'paid', 'posted', 'payment_due', 'not_paid', 'voided'. Max 20 results per query."""
    return _search_invoices_by_email_impl(
        customer_email=customer_email,
        limit=limit,
        offset=offset,
        status=status,
    )


@tool
def get_invoice_detail(invoice_id: str) -> Dict:
    """Get detailed information about a specific invoice by ID. Use this to get full line items and details about an invoice."""
    return _get_invoice_detail_impl(invoice_id)
