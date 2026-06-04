"""
tests/test_ospf.py

Validates OSPF state in CML matches production.

What is compared:    Neighbor router-IDs, adjacency state (must be FULL),
                     OSPF LSDB prefix coverage
What is ignored:     Interface names, costs/metrics, hello/dead timers,
                     LSA sequence numbers
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


class VerifyOSPFNeighbors(aetest.Testcase):

    @aetest.setup
    def setup(self, device_pairs):
        self.pairs = device_pairs

    @aetest.test
    def verify_neighbor_router_ids(self):
        overall_pass = True

        for device_name, hw_dev, cml_dev in self.pairs:
            logger.info(f"--- OSPF neighbor IDs: {device_name} ---")

            hw_neighbors  = NetworkCollector(hw_dev).get_ospf_neighbor_ids()
            cml_neighbors = NetworkCollector(cml_dev).get_ospf_neighbor_ids()

            missing = hw_neighbors - cml_neighbors
            if missing:
                logger.error(
                    f"{device_name}: OSPF neighbors in HW missing from CML:\n"
                    + "\n".join(f"  {rid}" for rid in sorted(missing))
                )
                overall_pass = False
            else:
                logger.info(f"{device_name}: All {len(hw_neighbors)} OSPF neighbors present")

        if not overall_pass:
            self.failed("One or more devices have missing OSPF neighbors")

    @aetest.test
    def verify_all_cml_neighbors_full(self):
        overall_pass = True

        for device_name, _, cml_dev in self.pairs:
            logger.info(f"--- OSPF neighbor states: {device_name} ---")

            states   = NetworkCollector(cml_dev).get_ospf_neighbor_states()
            not_full = {rid: s for rid, s in states.items() if s != 'FULL'}

            if not_full:
                logger.error(
                    f"{device_name}: OSPF neighbors not FULL:\n"
                    + "\n".join(f"  {rid}: {s}" for rid, s in not_full.items())
                )
                overall_pass = False
            else:
                logger.info(f"{device_name}: All {len(states)} OSPF neighbors are FULL")

        if not overall_pass:
            self.failed("One or more CML OSPF neighbors are not FULL")


class VerifyOSPFPrefixes(aetest.Testcase):

    @aetest.setup
    def setup(self, device_pairs):
        self.pairs = device_pairs

    @aetest.test
    def verify_lsdb_prefix_coverage(self):
        overall_pass = True

        for device_name, hw_dev, cml_dev in self.pairs:
            logger.info(f"--- OSPF LSDB prefixes: {device_name} ---")

            hw_prefixes  = NetworkCollector(hw_dev).get_ospf_prefixes()
            cml_prefixes = NetworkCollector(cml_dev).get_ospf_prefixes()

            missing = hw_prefixes - cml_prefixes
            if missing:
                logger.error(
                    f"{device_name}: OSPF prefixes in HW LSDB missing from CML:\n"
                    + "\n".join(f"  {p}" for p in sorted(missing))
                )
                overall_pass = False
            else:
                logger.info(f"{device_name}: All {len(hw_prefixes)} OSPF LSDB prefixes present")

        if not overall_pass:
            self.failed("One or more devices have missing OSPF LSDB prefixes")


class CommonCleanup(aetest.CommonCleanup):

    @aetest.subsection
    def disconnect_devices(self, hw_testbed, cml_testbed):
        for testbed in (hw_testbed, cml_testbed):
            for device in testbed.devices.values():
                try:
                    device.disconnect()
                except Exception:
                    pass
