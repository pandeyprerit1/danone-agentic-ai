import json
import os
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
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


MAX_TOOL_RESULT_CHARS = int(os.getenv("AGENT_MAX_TOOL_RESULT_CHARS", "2500"))
MAX_TOOL_LIST_ITEMS = int(os.getenv("AGENT_MAX_TOOL_LIST_ITEMS", "5"))
MAX_AGENT_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "3"))


def _compact_for_llm(value):
    """Shrink tool payloads so we do not spend tokens on verbose JSON."""
    if isinstance(value, list):
        trimmed = value[:MAX_TOOL_LIST_ITEMS]
        result = [_compact_for_llm(item) for item in trimmed]
        if len(value) > MAX_TOOL_LIST_ITEMS:
            result.append({"truncated": f"{len(value) - MAX_TOOL_LIST_ITEMS} additional items omitted"})
        return result
    if isinstance(value, dict):
        return {k: _compact_for_llm(v) for k, v in value.items()}
    if isinstance(value, str) and len(value) > 300:
        return value[:300] + "..."
    return value


def _serialize_tool_result_for_llm(tool_result: Any) -> str:
    compact_result = _compact_for_llm(tool_result)
    payload = json.dumps(compact_result, ensure_ascii=True, separators=(",", ":"))
    if len(payload) <= MAX_TOOL_RESULT_CHARS:
        return payload
    fallback = {
        "truncated": True,
        "original_size": len(payload),
        "preview": payload[:MAX_TOOL_RESULT_CHARS],
    }
    return json.dumps(fallback, ensure_ascii=True, separators=(",", ":"))


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

    messages = [
        SystemMessage(
            content=(
                "Be concise and tool-efficient. "
                "Call tools only when required and summarize results briefly."
            )
        ),
        HumanMessage(content=user_input),
    ]

    print(f"\n🤖 [AGENT] Starting with input: {user_input}")

    max_iterations = max(1, MAX_AGENT_ITERATIONS)
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
                    compact_tool_payload = _serialize_tool_result_for_llm(tool_result)
                    messages.append(
                        ToolMessage(content=compact_tool_payload, tool_call_id=tool_call.get("id", ""))
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
