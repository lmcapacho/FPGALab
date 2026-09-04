"""Lab-independent observed-bit policy for the temporal LED probe."""

from __future__ import annotations

from .profile import BoardProfile


class ObservedProbeTooWide(ValueError):
    """Raised when LED-mapped ports expand to more than 64 probe bits."""


def apply_led_observed(profile: BoardProfile, led_sources: dict[int, tuple[str, int]]) -> BoardProfile:
    """Keep every ABI port; observe the full width of PCF-mapped LED ports only."""
    observed = {
        name: profile.outputs[name]
        for name, _bit in led_sources.values()
        if name in profile.outputs
    }
    narrowed = BoardProfile(
        profile.board_name,
        profile.inputs,
        profile.outputs,
        observed,
        profile.clock_name,
    )
    narrowed.validate()
    bits = narrowed.observed_bits
    if len(bits) > 64:
        ports = ", ".join(f"{name}:{narrowed.outputs[name]}" for name in observed)
        raise ObservedProbeTooWide(
            f"The temporal probe supports at most 64 bits; LED-mapped ports expand to "
            f"{len(bits)} bits ({ports})."
        )
    return narrowed
