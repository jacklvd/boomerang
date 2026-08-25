import os
from functools import lru_cache

from anthropic import AsyncAnthropicBedrockMantle

# Bedrock model IDs carry an "anthropic." prefix (first-party IDs do not).
MODEL = os.getenv("BEDROCK_MODEL", "anthropic.claude-opus-5")


@lru_cache(maxsize=1)
def client() -> AsyncAnthropicBedrockMantle:
    """Shared Bedrock client.

    Credentials resolve through the standard AWS chain: env vars locally,
    the EC2 instance role in production (see infra/main.tf).

    Usage:
        resp = await client().messages.create(
            model=MODEL, max_tokens=16000,
            messages=[{"role": "user", "content": "hi"}],
        )
    """
    # dev-note: one shared client, no pooling knobs. Pass max_retries/timeout here if needed.
    return AsyncAnthropicBedrockMantle(aws_region=os.getenv("AWS_REGION", "us-east-1"))
