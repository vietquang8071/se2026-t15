"""Deterministic fake for callers of the provider protocol."""

from app.providers.errors import ProviderError
from app.providers.models import ProviderRequest, ProviderResult


class FakeProvider:
    def __init__(self, *, result: ProviderResult | None = None, error: ProviderError | None = None) -> None:
        if (result is None) == (error is None):
            raise ValueError("Provide exactly one result or error.")
        self.result = result
        self.error = error
        self.requests: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result
