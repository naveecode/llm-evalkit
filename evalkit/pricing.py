"""List-price helpers.

Unknown models return no price. A missing price is left blank rather than guessed.
The built-in catalog is OpenAI standard short-context input/output only, copied from
https://developers.openai.com/api/docs/pricing on 2026-10-14. Cached-input discounts
and long-context tiers are not applied, so a known-model cost is the standard list
price and can overstate a bill that received a cache discount.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

SOURCE = "https://developers.openai.com/api/docs/pricing"
AS_OF = "2026-10-14"


class ModelPrice(BaseModel):
    input_per_million: float = Field(ge=0)
    output_per_million: float = Field(ge=0)
    source: str | None = None
    as_of: str | None = None


# USD per 1M tokens. Standard tier, short context, input and output columns.
_OPENAI: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    "o4-mini": (1.10, 4.40),
    "o3-mini": (1.10, 4.40),
    "gpt-3.5-turbo": (0.50, 1.50),
}


def catalog_price(model: str) -> ModelPrice | None:
    pair = _OPENAI.get(model)
    if pair is None:
        return None
    return ModelPrice(
        input_per_million=pair[0],
        output_per_million=pair[1],
        source=SOURCE,
        as_of=AS_OF,
    )


def resolve_price(model: str, overrides: dict[str, ModelPrice] | None) -> ModelPrice | None:
    if overrides and model in overrides:
        price = overrides[model]
        if price.source is None:
            return price.model_copy(update={"source": "task pricing"})
        return price
    return catalog_price(model)


def cost_usd(
    prompt_tokens: int | None,
    completion_tokens: int | None,
    price: ModelPrice | None,
) -> float | None:
    """Return USD for one completion, or None when usage or a price is missing."""
    if price is None or prompt_tokens is None or completion_tokens is None:
        return None
    return (
        prompt_tokens * price.input_per_million + completion_tokens * price.output_per_million
    ) / 1_000_000
