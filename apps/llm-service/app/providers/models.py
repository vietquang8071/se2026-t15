"""Small, provider-neutral generation models; content is unverified candidate data."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

StructuredOutputMode = Literal["text", "json_object"]
NonNegativeInt = Annotated[StrictInt, Field(ge=0)]


class ProviderModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class ProviderMessage(ProviderModel):
    role: Literal["system", "user", "assistant"]
    content: StrictStr = Field(repr=False)


class ProviderRequest(ProviderModel):
    messages: list[ProviderMessage] = Field(min_length=1, repr=False)
    structured_output_mode: StructuredOutputMode | None = None
    max_output_tokens: Annotated[StrictInt, Field(gt=0)] | None = None
    temperature: Annotated[float, Field(ge=0, le=2, allow_inf_nan=False)] | None = None


class ProviderUsage(ProviderModel):
    input_tokens: NonNegativeInt
    output_tokens: NonNegativeInt


class ProviderResult(ProviderModel):
    content: StrictStr = Field(repr=False)
    model_id: Annotated[StrictStr, Field(min_length=1)]
    finish_reason: StrictStr | None
    usage: ProviderUsage | None = None
