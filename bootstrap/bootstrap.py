from virl2_client import ClientLibrary
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

client = ClientLibrary(
    url=os.getenv("VIRL_URL"),
    username=os.getenv("VIRL_USERNAME"),
    password=os.getenv("VIRL_PASSWORD"),
    ssl_verify=False
)

lab = client.find_labs_by_title("BRKOPS-2550 Topology")[0]

config_dir = Path(__file__).resolve().parent

for config_file in config_dir.glob("*.cfg"):
    node_label = config_file.stem  # Gets filename without extension
    node = lab.get_node_by_label(node_label)

    if node:
        node.configuration = config_file.read_text()
        print(f"✅ Config pushed to {node_label}")
    else:
        print(f"❌ Node '{node_label}' not found in lab")