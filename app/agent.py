import json
from typing import Dict

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_groq import ChatGroq

from .chargebee import _get_invoice_detail_impl, _search_all_invoices_impl, _search_invoices_by_email_impl
from .commercetools import (
    _create_cart_discount_only_impl,
    _create_discount_impl,
    _process_orders_impl,
    _search_orders_by_chargebee_invoice_impl,
    _search_orders_impl,
)
from .tools import (
    create_cart_discount_only,
    create_discount,
    get_invoice_detail,
    process_orders,
    search_all_invoices,
    search_invoices_by_email,
    search_orders,
    search_orders_by_chargebee_invoice,
)


def run_agent(user_input: str, llm: ChatGroq) -> str:
    """Simple agent loop that handles tool calls."""

    tools_impl: Dict[str, object] = {
        "search_orders": _search_orders_impl,
        "search_orders_by_chargebee_invoice": _search_orders_by_chargebee_invoice_impl,
        "create_discount": _create_discount_impl,
        "create_cart_discount_only": _create_cart_discount_only_impl,
        "process_orders": _process_orders_impl,
        "search_all_invoices": _search_all_invoices_impl,
        "search_invoices_by_email": _search_invoices_by_email_impl,
        "get_invoice_detail": _get_invoice_detail_impl,
    }

    llm_with_tools = llm.bind_tools(
        [
            search_orders,
            search_orders_by_chargebee_invoice,
            create_discount,
            create_cart_discount_only,
            process_orders,
            search_all_invoices,
            search_invoices_by_email,
            get_invoice_detail,
        ]
    )

    messages = [HumanMessage(content=user_input)]

    print(f"\n🤖 [AGENT] Starting with input: {user_input}")

    max_iterations = 5
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        print(f"\n📍 [AGENT] Iteration {iteration}")

        response = llm_with_tools.invoke(messages)
        messages.append(response)

        print(f"📍 [AGENT] Response type: {type(response)}")
        print(f"📍 [AGENT] Has tool_calls: {hasattr(response, 'tool_calls')}")

        if not hasattr(response, "tool_calls") or not response.tool_calls:
            if hasattr(response, "content"):
                print(f"✅ [AGENT] Final response: {response.content}")
                return response.content
            return str(response)

        for tool_call in response.tool_calls:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("args", {})

            print(f"\n🔧 [AGENT] Calling tool: {tool_name} with args: {tool_args}")

            if tool_name in tools_impl:
                try:
                    tool_result = tools_impl[tool_name](**tool_args)
                    messages.append(
                        ToolMessage(content=json.dumps(tool_result), tool_call_id=tool_call.get("id", ""))
                    )
                except Exception as e:
                    error_result = {"error": str(e)}
                    print(f"❌ [AGENT] Tool execution error: {e}")
                    messages.append(
                        ToolMessage(content=json.dumps(error_result), tool_call_id=tool_call.get("id", ""))
                    )
            else:
                print(f"❌ [AGENT] Unknown tool: {tool_name}")
                messages.append(
                    ToolMessage(
                        content=json.dumps({"error": f"Unknown tool: {tool_name}"}),
                        tool_call_id=tool_call.get("id", ""),
                    )
                )

    return "Max iterations reached without final response"
