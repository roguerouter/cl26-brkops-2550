"""
lib/network_collector.py

Platform-agnostic network state collector.
Supports: IOS-XE, IOS-XR, NX-OS

Usage:
    from lib.network_collector import NetworkCollector

    collector = NetworkCollector(device)
    collector.get_interface_prefixes()   # excludes management interfaces
    collector.get_ospf_neighbor_ids()
    collector.get_ospf_neighbor_states()
    collector.get_ospf_prefixes()
    collector.get_route_pairs()

Notes:
    - Management interfaces are excluded from IP comparisons.
    - Devices with no OSPF or no routes return empty sets gracefully.
    - Only default VRF is tested for routing.
    - Outgoing interfaces and metrics are excluded from all comparisons.
"""

import logging
from genie.metaparser.util.exceptions import SchemaEmptyParserError

logger = logging.getLogger(__name__)


class NetworkCollector:

    SUPPORTED = ('iosxe', 'iosxr', 'nxos')

    # Management interface name fragments — matched case-insensitively.
    # Covers: GigabitEthernet0 (XE mgmt), MgmtEth (XR), mgmt0 (NX-OS),
    #         Management0/Management1 (XE/XR)
    MGMT_KEYWORDS = ('mgmt', 'management', 'mgmteth')

    def __init__(self, device):
        self.device  = device
        self.os_type = device.os.lower()
        if self.os_type not in self.SUPPORTED:
            raise ValueError(
                f"Unsupported OS '{self.os_type}' on device '{device.name}'. "
                f"Supported: {list(self.SUPPORTED)}"
            )
        logger.info(f"{device.name}: NetworkCollector using [{self.os_type}] backend")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_interface_prefixes(self) -> set:
        """
        Returns set of 'x.x.x.x/prefix_len' strings assigned to any
        non-management interface. Returns empty set if no IPs found.
        """
        return {
            'iosxe': self._iosxe_interface_prefixes,
            'iosxr': self._iosxr_interface_prefixes,
            'nxos':  self._nxos_interface_prefixes,
        }[self.os_type]()

    def get_ospf_neighbor_ids(self) -> set:
        """
        Returns set of OSPF neighbor router-ID strings.
        Returns empty set if OSPF is not running on this device.
        """
        return {
            'iosxe': self._iosxe_ospf_neighbor_ids,
            'iosxr': self._iosxr_ospf_neighbor_ids,
            'nxos':  self._nxos_ospf_neighbor_ids,
        }[self.os_type]()

    def get_ospf_neighbor_states(self) -> dict:
        """
        Returns {router_id: state}. State normalized to adjacency word only
        e.g. 'FULL/DR' -> 'FULL'. Returns empty dict if OSPF not running.
        """
        return {
            'iosxe': self._iosxe_ospf_neighbor_states,
            'iosxr': self._iosxr_ospf_neighbor_states,
            'nxos':  self._nxos_ospf_neighbor_states,
        }[self.os_type]()

    def get_ospf_prefixes(self) -> set:
        """
        Returns set of prefixes in the OSPF LSDB (default VRF).
        Returns empty set if OSPF is not running on this device.
        """
        return {
            'iosxe': self._iosxe_ospf_prefixes,
            'iosxr': self._iosxr_ospf_prefixes,
            'nxos':  self._nxos_ospf_prefixes,
        }[self.os_type]()

    def get_route_pairs(self) -> set:
        """
        Returns set of (prefix, next_hop_ip) tuples from the default VRF.
        next_hop_ip is None for connected/local routes.
        Returns empty set if the routing table is empty.
        Outgoing interface and metric are intentionally excluded.
        Management VRF is excluded entirely.
        """
        return {
            'iosxe': self._iosxe_route_pairs,
            'iosxr': self._iosxr_route_pairs,
            'nxos':  self._nxos_route_pairs,
        }[self.os_type]()

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _safe_parse(self, command: str) -> dict:
        """
        Runs device.parse() and returns the result.
        Catches two exceptions and returns {} in both cases:
          - SchemaEmptyParserError: command ran but returned no output
            (e.g. OSPF not running, empty routing table)
          - ParserNotFound: Genie has no parser for this command on
            this platform/revision combination
        """
        try:
            return self.device.parse(command)
        except SchemaEmptyParserError:
            logger.warning(
                f"{self.device.name}: '{command}' returned no parseable output "
                f"— device may not be running this feature. Returning empty result."
            )
            return {}
        except Exception as e:
            if 'ParserNotFound' in type(e).__name__:
                logger.warning(
                    f"{self.device.name}: No Genie parser found for '{command}' "
                    f"on {self.os_type}. Returning empty result."
                )
                return {}
            raise

    def get_connection_ips(self) -> set:
        """
        Reads all IPs used to connect to this device from the testbed
        connection block. These are the management IPs — they differ
        between production and CML by design and should be excluded.

        Handles both forms:
            connections:
              cli:
                ip: 10.1.2.3          # single string
              cli:
                ip: [10.1.2.3, ...]   # list (rare but valid)
        """
        mgmt_ips = set()
        for conn in self.device.connections.values():
            ip = getattr(conn, 'ip', None)
            if ip is None:
                continue
            if isinstance(ip, (list, tuple)):
                for addr in ip:
                    mgmt_ips.add(str(addr))
            else:
                mgmt_ips.add(str(ip))
        if mgmt_ips:
            logger.debug(f"{self.device.name}: excluding connection IPs: {mgmt_ips}")
        return mgmt_ips

    def _is_mgmt_interface(self, intf_name: str) -> bool:
        """
        Returns True if the interface name contains a known management
        keyword. Used as a secondary filter alongside connection IP matching.
        """
        name_lower = intf_name.lower()
        return any(kw in name_lower for kw in self.MGMT_KEYWORDS)

    def _extract_prefixes_from_interfaces(self, output: dict) -> set:
        """
        Iterate parsed interface output and return IP/prefix strings,
        skipping any interface that:
          1. Has a name matching a management keyword (Mgmt, Management, etc.)
          2. Has an IP that matches one of the testbed connection IPs

        Both checks are needed because some platforms use regular interface
        names (e.g. GigabitEthernet0/0) for out-of-band management.
        """
        mgmt_ips = self.get_connection_ips()
        prefixes = set()

        for intf, data in output.items():
            if self._is_mgmt_interface(intf):
                logger.debug(f"{self.device.name}: skipping mgmt interface by name: {intf}")
                continue
            for ip, ip_data in data.get('ipv4', {}).items():
                if ip in mgmt_ips:
                    logger.debug(
                        f"{self.device.name}: skipping {intf} — "
                        f"IP {ip} matches testbed connection IP"
                    )
                    continue
                prefix_len = ip_data.get('prefix_length')
                if prefix_len:
                    prefixes.add(f"{ip}/{prefix_len}")
        return prefixes

    def _extract_route_pairs(self, routes: dict) -> set:
        """
        Common route extraction logic once routes dict is normalized.
        Shared across all platforms.
        Returns set of (prefix, next_hop_ip) tuples.
        """
        pairs = set()
        for prefix, data in routes.items():
            next_hops = data.get('next_hop', {})
            if next_hops.get('outgoing_interface'):
                pairs.add((prefix, None))
            for nh in next_hops.get('next_hop_list', {}).values():
                nh_ip = nh.get('next_hop')
                if nh_ip:
                    pairs.add((prefix, nh_ip))
        return pairs

    # ------------------------------------------------------------------
    # IOS-XE implementations
    # ------------------------------------------------------------------

    def _iosxe_interface_prefixes(self) -> set:
        output = self._safe_parse('show interfaces')
        return self._extract_prefixes_from_interfaces(output)

    def _iosxe_ospf_neighbor_ids(self) -> set:
        output = self._safe_parse('show ip ospf neighbor')
        return {
            rid
            for intf in output.get('interfaces', {}).values()
            for rid in intf.get('neighbors', {}).keys()
        }

    def _iosxe_ospf_neighbor_states(self) -> dict:
        output = self._safe_parse('show ip ospf neighbor')
        states = {}
        for intf in output.get('interfaces', {}).values():
            for rid, data in intf.get('neighbors', {}).items():
                states[rid] = data.get('state', '').upper().split('/')[0].strip()
        return states

    def _iosxe_ospf_prefixes(self) -> set:
        output = self._safe_parse('show ip ospf database')
        prefixes = set()
        for instance in output.get('vrf', {}).get('default', {}) \
                               .get('address_family', {}).get('ipv4', {}) \
                               .get('instance', {}).values():
            for area in instance.get('areas', {}).values():
                for lsa_type in area.get('database', {}) \
                                    .get('lsa_types', {}).values():
                    for lsa in lsa_type.get('lsas', {}).values():
                        prefix = lsa.get('ospfv2', {}).get('body', {}) \
                                    .get('summary', {}).get('network', {}) \
                                    .get('prefix')
                        if prefix:
                            prefixes.add(prefix)
        return prefixes

    def _iosxe_route_pairs(self) -> set:
        output = self._safe_parse('show ip route')
        routes = output.get('vrf', {}).get('default', {}) \
                       .get('address_family', {}).get('ipv4', {}) \
                       .get('routes', {})
        return self._extract_route_pairs(routes)

    # ------------------------------------------------------------------
    # IOS-XR implementations
    # ------------------------------------------------------------------

    def _iosxr_interface_prefixes(self) -> set:
        output = self._safe_parse('show interfaces')
        return self._extract_prefixes_from_interfaces(output)

    def _iosxr_ospf_neighbor_ids(self) -> set:
        output = self._safe_parse('show ospf neighbor')
        return {
            rid
            for intf in output.get('interfaces', {}).values()
            for rid in intf.get('neighbors', {}).keys()
        }

    def _iosxr_ospf_neighbor_states(self) -> dict:
        output = self._safe_parse('show ospf neighbor')
        states = {}
        for intf in output.get('interfaces', {}).values():
            for rid, data in intf.get('neighbors', {}).items():
                states[rid] = data.get('state', '').upper().split('/')[0].strip()
        return states

    def _iosxr_ospf_prefixes(self) -> set:
        output = self._safe_parse('show ospf database')
        prefixes = set()
        for instance in output.get('vrf', {}).get('default', {}) \
                               .get('address_family', {}).get('ipv4', {}) \
                               .get('instance', {}).values():
            for area in instance.get('areas', {}).values():
                for lsa_type in area.get('database', {}) \
                                    .get('lsa_types', {}).values():
                    for lsa in lsa_type.get('lsas', {}).values():
                        prefix = lsa.get('ospfv2', {}).get('body', {}) \
                                    .get('summary', {}).get('network', {}) \
                                    .get('prefix')
                        if prefix:
                            prefixes.add(prefix)
        return prefixes

    def _iosxr_route_pairs(self) -> set:
        output = self._safe_parse('show route ipv4')
        routes = output.get('vrf', {}).get('default', {}) \
                       .get('address_family', {}).get('ipv4', {}) \
                       .get('routes', {})
        return self._extract_route_pairs(routes)

    # ------------------------------------------------------------------
    # NX-OS implementations
    # ------------------------------------------------------------------

    def _nxos_interface_prefixes(self) -> set:
        output = self._safe_parse('show interface')
        return self._extract_prefixes_from_interfaces(output)

    def _nxos_ospf_neighbor_ids(self) -> set:
        # NX-OS: 'show ip ospf neighbors' has no Genie parser.
        # 'show ip ospf neighbors detail' is the parseable variant.
        output = self._safe_parse('show ip ospf neighbors detail')
        return {
            rid
            for vrf in output.get('vrf', {}).values()
            for intf in vrf.get('interfaces', {}).values()
            for rid in intf.get('neighbors', {}).keys()
        }

    def _nxos_ospf_neighbor_states(self) -> dict:
        output = self._safe_parse('show ip ospf neighbors detail')
        states = {}
        for vrf in output.get('vrf', {}).values():
            for intf in vrf.get('interfaces', {}).values():
                for rid, data in intf.get('neighbors', {}).items():
                    states[rid] = data.get('state', '').upper().split('/')[0].strip()
        return states

    def _nxos_ospf_prefixes(self) -> set:
        # NX-OS: 'show ip ospf database' may lack a parser; use vrf all variant
        output = self._safe_parse('show ip ospf database vrf all')
        prefixes = set()
        for vrf in output.get('vrf', {}).values():
            for instance in vrf.get('address_family', {}) \
                               .get('ipv4', {}).get('instance', {}).values():
                for area in instance.get('areas', {}).values():
                    for lsa_type in area.get('database', {}) \
                                        .get('lsa_types', {}).values():
                        for lsa in lsa_type.get('lsas', {}).values():
                            prefix = lsa.get('ospfv2', {}).get('body', {}) \
                                        .get('summary', {}).get('network', {}) \
                                        .get('prefix')
                            if prefix:
                                prefixes.add(prefix)
        return prefixes

    def _nxos_route_pairs(self) -> set:
        output = self._safe_parse('show ip route')
        routes = output.get('vrf', {}).get('default', {}) \
                       .get('address_family', {}).get('ipv4', {}) \
                       .get('routes', {})
        return self._extract_route_pairs(routes)