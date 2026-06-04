# Cisco Live 2026 BRKOPS-2550 Topology

This repository contains the files and documentation that were used to generate the virtual model of a physical network topology in Cisco Modeling Labs. The YAML file for the lab is included, but has no configuration.  This README will walk you through pushing the configurations to CML to start your nodes.

The bootstrap for the nodes is created by using a combination of:

- Ansible playbook and inventory
- Jinja2 templates
- A python file that deploys the lab via the virl2_client

This repository will walk you through the entire process to build your own operational version of the lab.  What do you need?

- Seven IP addresses that are reachable from a CML *bridge mode* external interface
- Your management network gateway

You will use these IP addresses to update the CML inventory and host_vars templates located in:

```
Inventory
./inventory/cml/cml.yml

host_vars
./roles/
```

You will replace the current *ansible_host:* IP addresses in the inventory file with your desired addresses.

## Documentation

The documentation contains details of both the CML and production environments.  The contents of the directory include:

- Diagram of logical device connections, IPv4/IPv6 addresses, routing protocols, and vlans.  For CML and Production.
- Mapping diagram of CML interfaces to HW interfaces

## Getting started

- Obtain a local copy of this repo.  Either by downloading as a zip and extracting to your desired directory or using:

```
git clone https://www.github.com/stayfresh_networks/cl26-brkops-2550.git
```

After unzipping or clone the repo locally.  Browse into the newly created ./cl26-brkops-2550 directory, or open the folder in your favorite IDE, like VScode.

> [!NOTE]
> ansible.cfg defaults to the CML inventory.  You do not need to set inventory in any of the commands when working with CML hosts.  To move to production, use '-i inventory/production/production.yml'.

## Update inventory

We need to update the inventory for CML with your desired IP addresses.  Browse to ./inventory/cml/ and open cml.yml:

Once opened, update the **ansible_hosts:** key with your desired IP addresses.  This will be the IP we use to connect to our device in CML.  Save the file changes.

## Generate host_vars / group_vars

At this stage, we have no group_vars or host_vars to deploy our lab.  One goal of network automation is to have a single source of truth, we want to minimize typos, misconfigurations, or have duplicate files to manage.  The group_vars and host_vars files are pushed using Jinja2 templatized versions of the files.  This allows you to maintain a single source file, make changes, and have consistency in the data.  Where changes exist, a conditional in the Jinja2 template determines how the configuration is applied for CML or production.

For things like **mgmt_ip:** or **names in p2p_interfaces*** we know there will be differences between cml and production. The template uses conditionals to set the proper variables in the host_vars in the file.  Here is an example:

```
mgmt_ip: {{ {'cml': '10.83.32.109/25', 'production': '10.82.9.129/28'}[env_name] }}
```

Similar steps are taken to manage the difference between interface names in CML and the hardware.
```
{{ {'cml': 'GigabitEthernet1/0/23', 'production': 'GigabitEthernet1/1/3'}[env_name] }}
```

To create the host_vars and group_vars files, run the following command:

```
ansible-playbook playbooks/create_hostvars.yml
```

The inventory/cml directory should now have the following folders in it:

- group_vars
  - all.yml
  - iosxe.yml
  - iosxr.yml
  - nxos.yml

- host_vars
  - s1-c9k-sw1.yml
  - s1-ncs540-rtr1.yml
  - s2-c8k-rtr1.yml
  - s2-c9k-sw1.yml
  - s3-c8k-rtr1.yml
  - s3-n9k-sw1.yml
  - s3-n9k-sw2.yml

Verify each file has your assigned mgmt_ip, mgmt_gw, and the CML interface selection.

## Push bootstrap to CML

Now that you have your **vars** files created, we can proceed with configuring the CML lab.  Execute the following command:

```
ansible-playbook playbooks/bootstrap.yml --extra-vars "user=<username> password=<yourpassword>
```
> [!WARNING]
> --extra-vars "user=<username> password=<yourpassword> will leave the password in cleartext inside your history.  The preferred way to manage > the password would be with an ansible-vault, and adding the password to the all.yml as a variable.

This will create the bootstrap directory in the root of the repo.  It will contain 7 files named after the ansible inventory_hostname.cfg.  Running the bootstrap.py command below will prompt you for your CML server (https://<yourcmlserver>), username, and password.  Alternatively, you can enter those details into the .env file in the bootstrap directory.

Once you choose how you'll manage the CML details, run:

```
python3 bootstrap/bootstrap.py
```

The bootstrap python will search the CML server for the topology name, then using the config files, push the configurations to the nodes in CML matching the config file name to device node name in CML.

## Start your CML lab

Login to your CML server, verify that the bootstrap configuration has been applied to each node.  Start the lab.  All nodes will boot up with their initial configuration.  The Catalyst 9000 devices set their license boot level, but require a second reboot to fully apply the setting.  Additionally, IOS-XRv9000 can take quite some time to fully push the configuration.  Wait until the system says "ztp" is complete.

Once the systems are booted, verify you can log into each device with the username and password you set.

## Running the playbook

If everything was successful to this point, you are free to run the playbook.  This is where the fun begins.

```
ansible-playbook playbooks/site.yml -u netadmin -k
```

This will execute the full playbook.  This will build out the complete network that matched the hardware network designed for the lab.

If you are new to network automation, I would encourage you to explore some additional options for controlling the deployment.  

**Run against a specific host**
--limit s1-c9k-sw1

**Run against multiple hosts**
--limit "s3-n9k-sw1,s3-n9k-sw2"

**Run against a specific set of tasks using tags**
--tags common

**More verbose output (you'll see everything)**
-vvv

## Genie Learn

PyATS Genie can be used to collect state data from the system.  I provided the test collections from my system and they can be found in the pyats/cml/ and pyats/production folders.

```
cd pyats/
```

From this directory run:

```
genie learn routing --testbed ./cml/cml_testbed.yaml --output ./cml/ospfv3_$(date +%Y-%m-%d)
```
This learns routing from the devices using the predefined cml_testbed.yaml file.  It outputs the data to a new folder called ospfv3_ with the current data obtained from a shell script.

You can use this output to perform a genie diff against the original CML diff collected for the Cisco Live session.  To do this:

```
genie diff ./cml/ospf_2026-04-16 ./cml/ospfv3_<your date> --exclude "outgoing_interface" "management" "Mgmt-vrf" "metric" "next_hop"
```

The exclude parameters will allow you to eliminate known differences from different management IP addresses, metrics, or IPv6 next hops

## Future add-on, final notes

I'll be working to build this into a CI/CD pipeline to demonstrate how we could demonstrate this in CML, despite not having hardware.  This will allw you to get hands on experience with how the pipeline process works.

If you have questions, feel free to reach out to me at mleuschn@cisco.com