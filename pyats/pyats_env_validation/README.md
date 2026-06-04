# PyATS Environment Validation — CML vs Production

Validates that a CML lab deployment matches production hardware.
Tests interface IPs, OSPF neighbors/LSDB, and route tables.
Platform-agnostic: IOS-XE, IOS-XR, and NX-OS.

## What Is Tested

| Test | Compared | Ignored |
|---|---|---|
| Interface IPs | IP address + prefix length | Interface name |
| OSPF Neighbors | Router-IDs, adjacency state (FULL) | Interface, cost, timers |
| OSPF LSDB | Prefix existence | LSA sequence numbers, cost |
| Routes | Prefix, next-hop IP | Outgoing interface, metric, AD |

Management VRF static routes are **not tested** — they differ by design.

---

## Project Structure

```
pyats_env_validation/
├── lib/
│   ├── __init__.py
│   ├── network_collector.py    # Platform-agnostic collector (XE/XR/NX-OS)
│   └── device_pairing.py       # Pairs devices using the alias field
├── tests/
│   ├── test_interface_ips.py
│   ├── test_ospf.py
│   └── test_routes.py
├── testbeds/
│   └── combined_testbed.yaml   # Template — edit with your devices
├── results/                    # HTML reports written here
├── job.py                      # Entry point
└── README.md
```

---

## How Device Pairing Works

Device **names** stay as real hostnames so PyATS hostname matching works on connect.
Device **aliases** carry the pairing convention — `alias` is a standard PyATS field
with no schema issues.

```yaml
router1:                   # real hostname — unchanged
  alias: hw_router1        # hw_ prefix + basename "router1"
  ...

router1-cml:               # CML node name — can be anything
  alias: cml_router1       # cml_ prefix + same basename "router1"
  ...
```

`hw_router1` pairs with `cml_router1` because both share the basename `router1`.

---

## Setup

### 1. Install PyATS

```bash
pip install pyats[full]
```

### 2. Configure Your Testbed

Open `testbeds/combined_testbed.yaml` and for each device:

- **Keep the device name as the real hostname**
- **Set `alias: hw_<basename>`** for production devices
- **Set `alias: cml_<basename>`** for CML devices
- The basename must match between the pair

### 3. Using Your Existing Separate Testbed Files

Add an `alias:` line to each device in your existing files —
no other changes needed:

**hw_testbed.yaml**
```yaml
devices:
  router1:
    alias: hw_router1     # add this line
    os: iosxe
    ...
```

**cml_testbed.yaml**
```yaml
devices:
  router1-cml:
    alias: cml_router1    # add this line — basename matches hw_router1
    os: iosxe
    ...
```

Then run with both files:

```bash
pyats run job job.py \
    --testbed-file hw_testbed.yaml \
    --testbed-file cml_testbed.yaml \
    --html-logs results/
```

### 4. Encrypt Passwords (recommended)

```bash
pyats secret encode --string "your_password"
# Paste output into testbed YAML as: "%ENC{...}"
```

---

## Running Tests

### All tests

```bash
pyats run job job.py \
    --testbed-file testbeds/combined_testbed.yaml \
    --html-logs results/
```

### Individual scripts

```bash
pyats run script tests/test_interface_ips.py \
    --testbed-file testbeds/combined_testbed.yaml

pyats run script tests/test_ospf.py \
    --testbed-file testbeds/combined_testbed.yaml

pyats run script tests/test_routes.py \
    --testbed-file testbeds/combined_testbed.yaml
```

### Dry run

```bash
pyats run job job.py \
    --testbed-file testbeds/combined_testbed.yaml \
    --dry-run
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `SchemaUnsupportedKeyError` | Using `custom:` key | Use `alias:` instead — it's schema-valid |
| `No device pairs found` | Missing or wrong alias | Check aliases follow `hw_<name>` / `cml_<name>` and basenames match |
| Hostname mismatch on connect | Device name changed | Keep device name as real hostname; only alias carries the prefix |
| `Unsupported OS` error | `os:` missing or wrong | Add correct `os: iosxe/iosxr/nxos` |
| OSPF neighbor not FULL | CML adjacency stuck | Check OSPF area/network config in CML |
