"""Bedrock access: the one place a model identifier is resolved and a client is built.

See ``server/AGENTS.md`` for why ``BEDROCK_MODEL`` has no default in code.
"""

import os
from functools import lru_cache

from anthropic import AsyncAnthropicBedrockMantle

# The two places the model is called. They have different latency budgets: a parse happens
# while the user watches a spinner, an action fallback happens mid-flow with a return
# half-driven, so the two may want different models. Both fall back to BEDROCK_MODEL.
CALL_SITES = ("parse", "action")


def _require_model(call_site: str = "") -> str:
    """Resolve the Bedrock model identifier, failing loudly if it is unset.

    There is deliberately no default. Recent Anthropic models on Bedrock are invocable
    only through a *regional inference profile* — an identifier carrying a geography
    prefix, e.g. ``us.anthropic.<model>``. A bare ``anthropic.<model>`` ID raises a
    validation error at invoke time, which means a wrong default fails on the first
    real request rather than at startup, in a Lambda, behind a user waiting on a parse.

    The correct string for a given region is whatever ``ListInferenceProfiles`` returns
    there; it is environment-specific, so it belongs in configuration rather than here.
    """
    if call_site:
        if call_site not in CALL_SITES:
            msg = f"unknown call site {call_site!r}; expected one of {CALL_SITES}"
            raise ValueError(msg)
        override = os.getenv(f"BEDROCK_MODEL_{call_site.upper()}")
        if override:
            return override
    model = os.getenv("BEDROCK_MODEL")
    if not model:
        msg = (
            "BEDROCK_MODEL is not set. Recent Anthropic models on Bedrock are invocable "
            "only through a regional inference profile (a 'us.'-prefixed identifier); a "
            "bare model ID fails at invoke, not at startup. Run "
            "`aws bedrock list-inference-profiles --region $AWS_REGION` and set the "
            "inferenceProfileId for the model you want. See server/.env.example."
        )
        raise RuntimeError(msg)
    return model


def model(call_site: str = "") -> str:
    """The configured model identifier for a call site. Prefer this to a module constant.

    ``call_site`` is one of ``CALL_SITES``. A per-call-site override
    (``BEDROCK_MODEL_PARSE``, ``BEDROCK_MODEL_ACTION``) wins when set; otherwise the
    single ``BEDROCK_MODEL`` applies to both. Resolved per call so importing this module
    never depends on the environment, and validated once at application startup by
    ``verify_config`` — see ``app.main``.
    """
    return _require_model(call_site)


def verify_config() -> None:
    """Fail fast at startup on a misconfigured model.

    Called from the FastAPI lifespan startup, which Mangum runs on cold start. A wrong
    or missing model must surface as a cold-start failure, not as a validation error on
    the first user request.
    """
    for call_site in CALL_SITES:
        _require_model(call_site)


# dev-note: a cost control, not tuning. The Function URL is unauthenticated, so bounded
# output tokens (with the short timeout and reserved concurrency) is what caps the bill.
# See infra/AGENTS.md.
MAX_TOKENS = int(os.getenv("BEDROCK_MAX_TOKENS", "4096"))


@lru_cache(maxsize=1)
def client() -> AsyncAnthropicBedrockMantle:
    """Shared Bedrock client.

    Credentials resolve through the standard AWS chain: env vars locally,
    the Lambda execution role in production (see infra/AGENTS.md).

    Usage:
        resp = await client().messages.create(
            model=model(), max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": "hi"}],
        )
    """
    # dev-note: one shared client, no pooling knobs. Pass max_retries/timeout here if needed.
    return AsyncAnthropicBedrockMantle(aws_region=os.getenv("AWS_REGION", "us-east-1"))
