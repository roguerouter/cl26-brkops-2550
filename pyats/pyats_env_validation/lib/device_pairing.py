"""
lib/device_pairing.py

Builds HW/CML device pairs by loading the two testbed files directly.

The hw_testbed and cml_testbed are passed in separately.
Devices are paired by matching hostname (device name) across the two testbeds.

Usage in job.py:
    from lib.device_pairing import build_device_pairs
    pairs = build_device_pairs(hw_testbed, cml_testbed)
"""

import logging
logger = logging.getLogger(__name__)


def build_device_pairs(hw_testbed, cml_testbed) -> list:
    """
    Pairs devices by name across two testbeds.
    Returns list of (device_name, hw_device, cml_device) tuples.
    Logs a warning for any device in HW with no CML match.
    """
    pairs = []

    for name, hw_dev in hw_testbed.devices.items():
        if name in cml_testbed.devices:
            cml_dev = cml_testbed.devices[name]
            pairs.append((name, hw_dev, cml_dev))
            logger.info(f"Paired: {name}")
        else:
            logger.warning(f"No CML match for HW device: {name}")

    return pairs
