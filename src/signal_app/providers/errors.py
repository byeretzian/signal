from __future__ import annotations


class ProviderError(RuntimeError):
    """Base error for an external data provider."""


class ProviderUnavailableError(ProviderError):
    """The provider could not serve a usable response."""


class ProviderResponseError(ProviderError):
    """The provider returned a response that violated its contract."""
