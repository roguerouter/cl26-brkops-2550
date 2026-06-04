"""
tests/test_interface_ips.py

Validates that all IP addresses present in production
exist in CML, regardless of which physical interface they sit on.

What is compared:    IP address + prefix length
What is ignored:     Interface name, interface state, description

Result logic:
    PASSED  — all HW IPs found in CML
    PASSX   — only missing IPs are management IPs (testbed connection IPs).
              These differ by design between production and CML.
    FAILED  — one or more non-management IPs are missing from CML
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


class VerifyInterfaceIPs(aetest.Testcase):

    @aetest.setup
    def setup(self, device_pairs):
        self.pairs = device_pairs

    @aetest.test
    def verify_all_prod_ips_exist_in_cml(self):
        real_missing   = {}   # device_name -> set of non-mgmt IPs missing from CML
        mgmt_excluded  = {}   # device_name -> set of mgmt IPs intentionally excluded

        for device_name, hw_dev, cml_dev in self.pairs:
            logger.info(f"--- Interface IPs: {device_name} ---")

            hw_collector  = NetworkCollector(hw_dev)
            cml_collector = NetworkCollector(cml_dev)

            hw_prefixes  = hw_collector.get_interface_prefixes()
            cml_prefixes = cml_collector.get_interface_prefixes()

            missing = hw_prefixes - cml_prefixes
            extra   = cml_prefixes - hw_prefixes

            if not missing:
                logger.info(f"{device_name}: All {len(hw_prefixes)} HW IPs present in CML")
                if extra:
                    logger.info(
                        f"{device_name}: Extra IPs in CML (not a failure):\n"
                        + "\n".join(f"  {p}" for p in sorted(extra))
                    )
                continue

            # Classify each missing IP — is it a management (connection) IP?
            hw_mgmt_ips  = hw_collector.get_connection_ips()
            cml_mgmt_ips = cml_collector.get_connection_ips()
            all_mgmt_ips = hw_mgmt_ips | cml_mgmt_ips

            mgmt_missing = {p for p in missing
                            if p.split('/')[0] in all_mgmt_ips}
            real_missing_ips = missing - mgmt_missing

            if mgmt_missing:
                mgmt_excluded[device_name] = mgmt_missing
                logger.info(
                    f"{device_name}: Excluding management IPs (differ by design):\n"
                    + "\n".join(f"  {p}" for p in sorted(mgmt_missing))
                )

            if real_missing_ips:
                real_missing[device_name] = real_missing_ips
                logger.error(
                    f"{device_name}: IPs in HW MISSING from CML (not management):\n"
                    + "\n".join(f"  {p}" for p in sorted(real_missing_ips))
                )
            else:
                logger.info(f"{device_name}: All non-management HW IPs present in CML")

            if extra:
                logger.info(
                    f"{device_name}: Extra IPs in CML (not a failure):\n"
                    + "\n".join(f"  {p}" for p in sorted(extra))
                )

        # --- Determine final result ---

        if real_missing:
            # Real mismatches exist — hard failure regardless of mgmt exclusions
            self.failed(
                "One or more devices have non-management IP mismatches:\n"
                + "\n".join(
                    f"  {dev}: {sorted(ips)}"
                    for dev, ips in sorted(real_missing.items())
                )
            )

        elif mgmt_excluded:
            # Only management IPs were different — passx with full details
            exclusion_summary = "\n".join(
                f"  {dev}: {sorted(ips)}"
                for dev, ips in sorted(mgmt_excluded.items())
            )
            self.passx(
                "All non-management IPs match. Management IPs excluded — "
                "they differ by design between production and CML.\n"
                "Excluded IPs (testbed connection addresses):\n"
                + exclusion_summary
            )

        # else: everything matched — implicit PASSED


class CommonCleanup(aetest.CommonCleanup):

    @aetest.subsection
    def disconnect_devices(self, hw_testbed, cml_testbed):
        for testbed in (hw_testbed, cml_testbed):
            for device in testbed.devices.values():
                try:
                    device.disconnect()
                except Exception:
                    pass