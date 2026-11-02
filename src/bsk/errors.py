class BSKError(Exception):
    """Base error for user-actionable BINA SHOR KE failures."""


class ConfigurationError(BSKError):
    pass


class GateError(BSKError):
    pass


class ProviderError(BSKError):
    pass


class StateError(BSKError):
    pass
