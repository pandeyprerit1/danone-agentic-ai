# Danone Agentic AI

This is an AI-powered agent for managing orders and invoices across Commercetools and Chargebee.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables in `.env`:
   - Commercetools credentials (already configured)
   - Chargebee credentials: Set `CHARGEBEE_SITE` and `CHARGEBEE_API_KEY`

## Chargebee Configuration

To enable invoice search capabilities:

1. Get your Chargebee API key from your Chargebee dashboard
2. Set the following in your `.env` file:
   ```
   CHARGEBEE_SITE=your-site-name
   CHARGEBEE_API_KEY=your-api-key
   ```

## Features

- **Order Management**: Search and process orders in Commercetools
- **Invoice Search**: Search all invoices or invoices by customer email in Chargebee
- **Order-Invoice Linking**: Find Commercetools orders by Chargebee invoice ID
- **Invoice Details**: Get full details of specific invoices including line items

## Available Tools

### Commercetools
- `search_orders`: Search orders with various filters (email, order number, state, etc.)
- `search_orders_by_chargebee_invoice`: Find orders linked to specific Chargebee invoices
- `create_discount`: Create discount codes with cart discounts
- `process_orders`: Update payment states for orders

### Chargebee
- `search_all_invoices`: Search all invoices with optional filters
- `search_invoices_by_email`: Search customer invoices by email address
- `get_invoice_detail`: Get detailed information about a specific invoice

## Usage Examples

The agent can handle queries like:
- "Find all orders for customer@example.com"
- "Search invoices for customer@example.com"
- "Get details about invoice 2410"
- "Find the order linked to Chargebee invoice 2410"
- "Create a 10% discount code WELCOME10 valid for 30 days"
- "Show unpaid invoices from last month"

## Usage

Run the Streamlit app:
```bash
streamlit run AgenticAI.py
```

## Available Tools

### Commercetools
- `search_orders`: Search orders with various filters
- `process_orders`: Update payment states for orders

### Chargebee
- `search_all_invoices`: Search all invoices with optional filters
- `search_invoices_by_email`: Search invoices for a specific customer by email