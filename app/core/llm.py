"""Thin wrapper around the Claude API. One place for model, effort, fallbacks and refusal handling."""
import json
import os
import anthropic

MODEL = "claude-sonnet-5-5"  # half the per-token price of Opus 5.5; stored demo readings were made with claude-opus-5-5
_client = None


def client():
    global _client
    if _client is None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        try:  # Streamlit Cloud secrets
            import streamlit as st
            key = key or st.secrets.get("ANTHROPIC_API_KEY")
        except Exception:
            pass
        _client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
    return _client


class LLMError(RuntimeError):
    pass


def create(messages, system=None, tools=None, schema=None, effort="medium", max_tokens=16000):
    """One Messages API call. Returns the full response. Raises LLMError on refusal / truncation."""
    output_config = {"effort": effort}
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    kwargs = dict(model=MODEL, max_tokens=max_tokens, messages=messages, output_config=output_config,
                  betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    if system:
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = tools
    try:
        if max_tokens > 16000:
            with client().beta.messages.stream(**kwargs) as s:
                resp = s.get_final_message()
        else:
            resp = client().beta.messages.create(**kwargs)
    except anthropic.AuthenticationError:
        raise LLMError("No valid ANTHROPIC_API_KEY configured.")
    except anthropic.RateLimitError:
        raise LLMError("Rate limited by the API. Wait a few seconds and retry.")
    except anthropic.APIStatusError as e:
        raise LLMError(f"API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        raise LLMError("Network error reaching the API.")
    if resp.stop_reason == "refusal":
        raise LLMError("The model declined this request.")
    if resp.stop_reason == "max_tokens":
        raise LLMError("Response was cut off (max_tokens). Try a smaller input.")
    return resp


def text_of(resp):
    return "".join(b.text for b in resp.content if b.type == "text")


def structured(messages, schema, system=None, effort="high", max_tokens=32000):
    """Call with a JSON schema and return the parsed object."""
    resp = create(messages, system=system, schema=schema, effort=effort, max_tokens=max_tokens)
    return json.loads(text_of(resp)), resp
