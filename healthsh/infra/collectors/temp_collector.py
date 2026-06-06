"""Hardware temperature sensors via ``psutil.sensors_temperatures``.

Returns a flat mapping ``{sensor_chip: current_celsius}`` keeping the **most
representative** entry per chip (package / composite / first available). The
collector never raises for routine failures — on bare-metal it gives real
readings, on VMs that expose no sensors it returns an empty dict.

Sensor names vary by vendor — Intel uses ``coretemp``, AMD ``k10temp``, many
laptops also surface ``acpitz`` — so this module never hard-codes a key, it
just iterates whatever psutil reports.
"""

from __future__ import annotations

import logging

import psutil

_LOG = logging.getLogger(__name__)

# Substrings (lowercase) we prefer as the per-chip "representative" entry, in
# priority order. ``Package id 0`` is the Intel canonical chip-wide temp;
# ``Composite`` is the NVMe / SoC equivalent; ``Tctl`` is AMD's reporting
# temperature; ``Tdie`` is the silicon junction temp.
_PREFERRED_LABEL_HINTS: tuple[str, ...] = (
    "package id 0",
    "package",
    "composite",
    "tctl",
    "tdie",
)


def _pick_representative(entries: list) -> float | None:
    """Return the representative ``current`` value from a chip's entry list.

    Priority: a label matching :data:`_PREFERRED_LABEL_HINTS`, then the first
    entry with a non-zero ``current`` reading, then the first entry overall.
    Returns ``None`` if the list is empty or no entry has a numeric ``current``.
    """
    if not entries:
        return None

    for hint in _PREFERRED_LABEL_HINTS:
        for entry in entries:
            label = (getattr(entry, "label", "") or "").lower()
            if hint in label:
                current = getattr(entry, "current", None)
                if current is not None:
                    return float(current)

    for entry in entries:
        current = getattr(entry, "current", None)
        if current is not None and float(current) != 0.0:
            return float(current)

    first = entries[0]
    current = getattr(first, "current", None)
    return float(current) if current is not None else None


def collect_temps() -> dict[str, float]:
    """Return a ``{chip_name: current_celsius}`` map for every available sensor.

    The mapping is empty on hardware (most VMs, headless containers, some
    Apple-silicon Linux installs) where no sensors are exposed. The function
    swallows :class:`AttributeError` (older psutil without
    ``sensors_temperatures``) and any sensor-read exception — the worst case
    is an empty dict, never a raise.
    """
    sensors_fn = getattr(psutil, "sensors_temperatures", None)
    if sensors_fn is None:
        return {}

    try:
        raw = sensors_fn()
    except Exception:  # noqa: BLE001 — temp sensors are best-effort
        _LOG.debug("sensors_temperatures raised; reporting no temps", exc_info=True)
        return {}

    out: dict[str, float] = {}
    for chip, entries in (raw or {}).items():
        value = _pick_representative(list(entries))
        if value is None:
            continue
        out[chip] = value
    return out
