"""
tests/test_routes.py

Validates that the default VRF routing table in CML matches production.

What is compared:    Prefix existence, next-hop IP address
What is ignored:     Outgoing interface, metric, admin distance,
                     route age, protocol source
                     Management VRF excluded entirely.
"""

import logging
from pyats import aetest
from lib.network_collector import NetworkCollector
from lib.device_pairing import build_device_pairs

logger = logging.getLogger(__name__)


class CommonSetup(aetest.CommonSetup):

    @aetest.subsection
    def connect_devices(self, hw_testbed, cml_testbed):
        for testbed in (hw_testbed, cml_testbed):
            for name, device in testbed.devices.items():
                try:
                    device.connect(log_stdout=False)
                    logger.info(f"Connected: {name}")
                except Exception as e:
                    self.failed(f"Could not connect to {name}: {e}")

    @aetest.subsection
    def build_pairs(self, hw_testbed, cml_testbed):
        pairs = build_device_pairs(hw_testbed, cml_testbed)
        if not pairs:
            self.failed(
                "No device pairs found. Ensure device names match "
                "between hw_testbed.yaml and cml_testbed.yaml."
            )
        self.parent.parameters['device_pairs'] = pairs


class VerifyRoutes(aetest.Testcase):

    @aetest.setup
    def setup(self, device_pairs):
        self.pairs = device_pairs

    @aetest.test
    def verify_prefix_coverage(self):
        overall_pass = True

        for device_name, hw_dev, cml_dev in self.pairs:
            logger.info(f"--- Route prefix coverage: {device_name} ---")

            hw_prefixes  = {p for p, _ in NetworkCollector(hw_dev).get_route_pairs()}
            cml_prefixes = {p for p, _ in NetworkCollector(cml_dev).get_route_pairs()}

            missing = hw_prefixes - cml_prefixes
            if missing:
                logger.error(
                    f"{device_name}: Prefixes in HW missing from CML:\n"
                    + "\n".join(f"  {p}" for p in sorted(missing))
                )
                overall_pass = False
            else:
                logger.info(f"{device_name}: All {len(hw_prefixes)} prefixes present in CML")

        if not overall_pass:
            self.failed("One or more devices have missing prefixes")

    @aetest.test
    def verify_next_hops(self):
        overall_pass = True

        for device_name, hw_dev, cml_dev in self.pairs:
            logger.info(f"--- Route next-hops: {device_name} ---")

            hw_routed  = {(p, nh) for p, nh in NetworkCollector(hw_dev).get_route_pairs()
                          if nh is not None}
            cml_routed = {(p, nh) for p, nh in NetworkCollector(cml_dev).get_route_pairs()
                          if nh is not None}

            missing = hw_routed - cml_routed
            if missing:
                logger.error(
                    f"{device_name}: Prefix/next-hop pairs in HW missing from CML:\n"
                    + "\n".join(f"  {p} via {nh}" for p, nh in sorted(missing))
                )
                overall_pass = False
            else:
                logger.info(f"{device_name}: All {len(hw_routed)} next-hop relationships match")

        if not overall_pass:
            self.failed("One or more devices have next-hop mismatches")


class CommonCleanup(aetest.CommonCleanup):

    @aetest.subsection
    def disconnect_devices(self, hw_testbed, cml_testbed):
        for testbed in (hw_testbed, cml_testbed):
            for device in testbed.devices.values():
                try:
                    device.disconnect()
                except Exception:
                    pass
