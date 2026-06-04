"""
cml_hw_validation.py

Orchestrates all environment validation tests.
Loads hw_testbed and cml_testbed separately and passes both to each test.

Usage:
    pyats run job cml_hw_validation.py \
        --hw-testbed hw_testbed.yaml \
        --cml-testbed cml_testbed.yaml \
        --html-logs results/
"""

import os
import argparse
from pyats.easypy import run
from pyats.topology import loader

TEST_DIR = os.path.join(os.path.dirname(__file__), 'tests')

# Define custom args at module level using a standalone parser.
# parse_known_args() is used so PyATS can handle its own args separately.
parser = argparse.ArgumentParser(description='CML vs HW validation job')
parser.add_argument(
    '--hw-testbed',
    required=True,
    dest='hw_testbed',
    help='Path to production hardware testbed YAML'
)
parser.add_argument(
    '--cml-testbed',
    required=True,
    dest='cml_testbed',
    help='Path to CML lab testbed YAML'
)


def main(runtime):

    # parse_known_args() takes only what this parser knows,
    # leaving PyATS args untouched
    custom_args = parser.parse_known_args()[0]

    hw_testbed  = loader.load(custom_args.hw_testbed)
    cml_testbed = loader.load(custom_args.cml_testbed)

    common_params = {
        'hw_testbed':  hw_testbed,
        'cml_testbed': cml_testbed,
    }

    run(
        testscript=os.path.join(TEST_DIR, 'test_interface_ips.py'),
        runtime=runtime,
        taskid='Layer1_InterfaceIPs',
        **common_params,
    )

    run(
        testscript=os.path.join(TEST_DIR, 'test_ospf.py'),
        runtime=runtime,
        taskid='Layer2_OSPF',
        **common_params,
    )

    run(
        testscript=os.path.join(TEST_DIR, 'test_routes.py'),
        runtime=runtime,
        taskid='Layer2_Routes',
        **common_params,
    )