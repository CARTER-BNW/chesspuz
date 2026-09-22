"""Core logic for chesspuz.

Keep this module importable without side effects (no windows, no network) so tests stay fast.
"""


def hello(name: str = "chesspuz") -> str:
    return f"Hello from {name}"
