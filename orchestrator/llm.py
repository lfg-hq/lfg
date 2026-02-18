"""
LLM client for the orchestrator — streaming-first.

Supports Anthropic, OpenAI, and Google.  Text tokens are yielded as they
arrive so the agent can forward them to the user in real time.  Tool-call
arguments are buffered until complete so they can be JSON-parsed.

Each streaming function is an async generator that yields dicts:
    {"type": "text_delta",      "text": "..."}
    {"type": "tool_start",      "id": "...", "name": "..."}
    {"type": "tool_delta",      "id": "...", "arguments_delta": "..."}
    {"type": "tool_end",        "id": "..."}
    {"type": "done",            "text": str, "tool_calls": list,
                                 "stop_reason": str, "usage": dict}
"""
import json
import logging
import os
import uuid
from typing import List, Dict, Any, Optional, AsyncGenerator

from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error helper
# ---------------------------------------------------------------------------

def _error_done(msg: str) -> dict:
    return {
        "type": "done",
        "text": msg,
        "tool_calls": [],
        "stop_reason": "error",
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }


# ---------------------------------------------------------------------------
# API key helpers
# ---------------------------------------------------------------------------

async def _get_api_key(user, key_attr: str, env_var: str) -> Optional[str]:
    """Resolve API key: user's personal key first, then platform env var."""
    if user:
        try:
            from accounts.models import LLMApiKeys
            llm_keys = await sync_to_async(LLMApiKeys.objects.get)(user=user)
            if llm_keys.use_personal_llm_keys:
                key = getattr(llm_keys, key_attr, None)
                if key:
                    return key
        except Exception:
            pass
    return os.getenv(env_var)


# ---------------------------------------------------------------------------
# Message sanitisation (unchanged)
# ---------------------------------------------------------------------------

def _sanitize_messages_for_anthropic(messages: List[Dict]) -> tuple:
    """Separate system prompt and clean messages for Anthropic API.
    Returns (system_text, api_messages).
    """
    system = ""
    api_messages = []
    for msg in messages:
        if msg.get("role") == "system":
            system = msg.get("content", "")
            continue
        if "content" not in msg or msg["content"] is None:
            msg = {**msg, "content": ""}
        api_messages.append(msg)
    return system, api_messages


def _convert_to_openai_messages(messages: List[Dict], tools_available: bool) -> List[Dict]:
    """Convert internal message format (Anthropic-style) to OpenAI chat format."""
    openai_msgs = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content")

        if role == "system":
            openai_msgs.append({"role": "system", "content": content or ""})
            continue

        if role == "assistant":
            if isinstance(content, list):
                text_parts = []
                tool_calls = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            tool_calls.append({
                                "id": block.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                                "type": "function",
                                "function": {
                                    "name": block["name"],
                                    "arguments": json.dumps(block.get("input", {})),
                                },
                            })
                oai_msg = {"role": "assistant", "content": "\n".join(text_parts) or None}
                if tool_calls:
                    oai_msg["tool_calls"] = tool_calls
                openai_msgs.append(oai_msg)
            else:
                openai_msgs.append({"role": "assistant", "content": content or ""})
            continue

        if role == "user":
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        openai_msgs.append({
                            "role": "tool",
                            "tool_call_id": block.get("tool_use_id", ""),
                            "content": block.get("content", ""),
                        })
                    else:
                        openai_msgs.append({"role": "user", "content": json.dumps(block)})
            else:
                openai_msgs.append({"role": "user", "content": content or ""})
            continue

        openai_msgs.append({"role": role, "content": str(content or "")})
    return openai_msgs


# ---------------------------------------------------------------------------
# Streaming: Anthropic
# ---------------------------------------------------------------------------

async def _stream_anthropic(messages, tools, user, model, max_tokens) -> AsyncGenerator[dict, None]:
    import anthropic

    api_key = await _get_api_key(user, "anthropic_api_key", "ANTHROPIC_API_KEY")
    if not api_key:
        yield _error_done("No Anthropic API key available.")
        return

    client = anthropic.AsyncAnthropic(api_key=api_key)
    system, api_messages = _sanitize_messages_for_anthropic(messages)

    anthropic_tools = []
    for tool in tools:
        if tool.get("type") == "function":
            func = tool["function"]
            anthropic_tools.append({
                "name": func["name"],
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            })

    try:
        async with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=api_messages,
            tools=anthropic_tools if anthropic_tools else anthropic.NOT_GIVEN,
            tool_choice={"type": "auto"} if anthropic_tools else anthropic.NOT_GIVEN,
        ) as stream:
            # Track state for building the final summary
            full_text = []
            tool_calls = {}  # id -> {name, arguments_buffer}
            current_tool_id = None

            async for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "text":
                        pass  # text deltas come in content_block_delta
                    elif block.type == "tool_use":
                        current_tool_id = block.id
                        tool_calls[block.id] = {"name": block.name, "arguments": ""}
                        yield {"type": "tool_start", "id": block.id, "name": block.name}

                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        full_text.append(delta.text)
                        yield {"type": "text_delta", "text": delta.text}
                    elif delta.type == "input_json_delta":
                        if current_tool_id and current_tool_id in tool_calls:
                            tool_calls[current_tool_id]["arguments"] += delta.partial_json
                            yield {
                                "type": "tool_delta",
                                "id": current_tool_id,
                                "arguments_delta": delta.partial_json,
                            }

                elif event.type == "content_block_stop":
                    if current_tool_id:
                        yield {"type": "tool_end", "id": current_tool_id}
                        current_tool_id = None

            # Get final message for usage/stop_reason
            final = await stream.get_final_message()
            tc_list = []
            for tid, info in tool_calls.items():
                tc_list.append({
                    "id": tid,
                    "function": {"name": info["name"], "arguments": info["arguments"]},
                })

            yield {
                "type": "done",
                "text": "".join(full_text),
                "tool_calls": tc_list,
                "stop_reason": final.stop_reason,
                "usage": {
                    "input_tokens": final.usage.input_tokens,
                    "output_tokens": final.usage.output_tokens,
                },
            }

    except Exception as e:
        logger.error(f"Anthropic streaming error: {e}", exc_info=True)
        yield _error_done(f"LLM API error: {e}")


# ---------------------------------------------------------------------------
# Streaming: OpenAI (also used for xAI)
# ---------------------------------------------------------------------------

async def _stream_openai(messages, tools, user, model, max_tokens) -> AsyncGenerator[dict, None]:
    from openai import AsyncOpenAI

    api_key = await _get_api_key(user, "openai_api_key", "OPENAI_API_KEY")
    if not api_key:
        yield _error_done("No OpenAI API key available.")
        return

    client = AsyncOpenAI(api_key=api_key)

    openai_tools = []
    for tool in tools:
        if tool.get("type") == "function":
            openai_tools.append({"type": "function", "function": tool["function"]})

    openai_messages = _convert_to_openai_messages(messages, bool(openai_tools))

    try:
        kwargs = {
            "model": model,
            "max_completion_tokens": max_tokens,
            "messages": openai_messages,
            "stream": True,
        }
        if openai_tools:
            kwargs["tools"] = openai_tools
            kwargs["tool_choice"] = "auto"

        stream = await client.chat.completions.create(**kwargs)

        full_text = []
        tool_calls = {}  # index -> {id, name, arguments}

        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                continue

            delta = choice.delta

            # Text content
            if delta.content:
                full_text.append(delta.content)
                yield {"type": "text_delta", "text": delta.content}

            # Tool calls
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            "id": tc_delta.id or f"call_{uuid.uuid4().hex[:8]}",
                            "name": "",
                            "arguments": "",
                        }
                        if tc_delta.id:
                            tool_calls[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls[idx]["name"] = tc_delta.function.name
                            yield {
                                "type": "tool_start",
                                "id": tool_calls[idx]["id"],
                                "name": tc_delta.function.name,
                            }
                        if tc_delta.function.arguments:
                            tool_calls[idx]["arguments"] += tc_delta.function.arguments
                            yield {
                                "type": "tool_delta",
                                "id": tool_calls[idx]["id"],
                                "arguments_delta": tc_delta.function.arguments,
                            }

            # Stream done
            if choice.finish_reason:
                for idx in sorted(tool_calls.keys()):
                    yield {"type": "tool_end", "id": tool_calls[idx]["id"]}

        tc_list = []
        for idx in sorted(tool_calls.keys()):
            info = tool_calls[idx]
            tc_list.append({
                "id": info["id"],
                "function": {"name": info["name"], "arguments": info["arguments"]},
            })

        yield {
            "type": "done",
            "text": "".join(full_text),
            "tool_calls": tc_list,
            "stop_reason": "stop",
            "usage": {
                "input_tokens": getattr(chunk.usage, "prompt_tokens", 0) if hasattr(chunk, "usage") and chunk.usage else 0,
                "output_tokens": getattr(chunk.usage, "completion_tokens", 0) if hasattr(chunk, "usage") and chunk.usage else 0,
            },
        }

    except Exception as e:
        logger.error(f"OpenAI streaming error: {e}", exc_info=True)
        yield _error_done(f"LLM API error: {e}")


# ---------------------------------------------------------------------------
# Streaming: Google Gemini (OpenAI-compatible)
# ---------------------------------------------------------------------------

async def _stream_google(messages, tools, user, model, max_tokens) -> AsyncGenerator[dict, None]:
    from openai import AsyncOpenAI

    api_key = await _get_api_key(user, "google_api_key", "GOOGLE_API_KEY")
    if not api_key:
        yield _error_done("No Google API key available.")
        return

    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    openai_tools = []
    for tool in tools:
        if tool.get("type") == "function":
            openai_tools.append({"type": "function", "function": tool["function"]})

    openai_messages = _convert_to_openai_messages(messages, bool(openai_tools))

    try:
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": openai_messages,
            "stream": True,
        }
        if openai_tools:
            kwargs["tools"] = openai_tools
            kwargs["tool_choice"] = "auto"

        stream = await client.chat.completions.create(**kwargs)

        full_text = []
        tool_calls = {}

        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                continue

            delta = choice.delta

            if delta.content:
                full_text.append(delta.content)
                yield {"type": "text_delta", "text": delta.content}

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            "id": tc_delta.id or f"call_{uuid.uuid4().hex[:8]}",
                            "name": "",
                            "arguments": "",
                        }
                        if tc_delta.id:
                            tool_calls[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls[idx]["name"] = tc_delta.function.name
                            yield {"type": "tool_start", "id": tool_calls[idx]["id"], "name": tc_delta.function.name}
                        if tc_delta.function.arguments:
                            tool_calls[idx]["arguments"] += tc_delta.function.arguments
                            yield {"type": "tool_delta", "id": tool_calls[idx]["id"], "arguments_delta": tc_delta.function.arguments}

            if choice.finish_reason:
                for idx in sorted(tool_calls.keys()):
                    yield {"type": "tool_end", "id": tool_calls[idx]["id"]}

        tc_list = []
        for idx in sorted(tool_calls.keys()):
            info = tool_calls[idx]
            tc_list.append({"id": info["id"], "function": {"name": info["name"], "arguments": info["arguments"]}})

        yield {
            "type": "done",
            "text": "".join(full_text),
            "tool_calls": tc_list,
            "stop_reason": "stop",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }

    except Exception as e:
        logger.error(f"Google streaming error: {e}", exc_info=True)
        yield _error_done(f"LLM API error: {e}")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

_STREAM_PROVIDER_MAP = {
    "anthropic": (_stream_anthropic, "anthropic"),
    "openai": (_stream_openai, "openai"),
    "google": (_stream_google, "google"),
    "xai": (_stream_openai, "xai"),
}


def _resolve_model(provider_name: Optional[str], selected_model: Optional[str]) -> tuple:
    """Resolve provider + actual model name from user selection."""
    from factory.llm_config import get_model_provider_map, get_provider_model_mapping

    if not selected_model:
        return "openai", "gpt-5-mini"

    if not provider_name:
        model_to_provider = get_model_provider_map()
        provider_name = model_to_provider.get(selected_model, "openai")

    mapping = get_provider_model_mapping(provider_name)
    model_id = mapping.get(selected_model, selected_model)
    return provider_name, model_id


async def stream_orchestrator_llm(
    messages: List[Dict],
    tools: List[Dict],
    user=None,
    provider_name: Optional[str] = None,
    selected_model: Optional[str] = None,
    max_tokens: int = 4096,
) -> AsyncGenerator[dict, None]:
    """
    Stream the LLM response.  Yields dicts with type:
      text_delta, tool_start, tool_delta, tool_end, done
    """
    provider_name, model_id = _resolve_model(provider_name, selected_model)

    entry = _STREAM_PROVIDER_MAP.get(provider_name)
    if not entry:
        logger.warning(f"Unknown provider {provider_name}, falling back to openai")
        entry = _STREAM_PROVIDER_MAP["openai"]

    stream_fn = entry[0]
    logger.info(f"[orchestrator-llm] Starting stream: provider={provider_name}, model={model_id}, messages={len(messages)}, tools={len(tools)}")

    event_count = 0
    async for event in stream_fn(messages, tools, user, model_id, max_tokens):
        event_count += 1
        etype = event.get("type", "unknown")
        if etype == "text_delta":
            logger.debug(f"[orchestrator-llm] event #{event_count}: text_delta ({len(event.get('text', ''))} chars)")
        elif etype == "done":
            tc = event.get("tool_calls", [])
            logger.info(f"[orchestrator-llm] event #{event_count}: done — tool_calls={[t.get('function', {}).get('name') for t in tc]}, text={len(event.get('text', ''))} chars")
        else:
            logger.debug(f"[orchestrator-llm] event #{event_count}: {etype}")
        yield event
    logger.info(f"[orchestrator-llm] Stream complete: {event_count} events total")
