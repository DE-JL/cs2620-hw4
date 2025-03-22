import yaml
import importlib.resources

config_path = importlib.resources.files(__package__) / "config.yaml"

with config_path.open() as f:
    config = yaml.safe_load(f)

DEBUG = config["debug"]
GUI_REFRESH_RATE = config["gui_refresh_rate"]
ID_TO_ADDR_LOCAL = config["id_to_addr_local"]
ID_TO_ADDR_PUBLIC = config["id_to_addr_public"]
NETWORK_INTERFACE = config["network"]["interface"]
PUBLIC_STATUS = config["network"]["public_status"]

__all__ = [
    "DEBUG",
    "GUI_REFRESH_RATE",
    "ID_TO_ADDR_LOCAL",
    "ID_TO_ADDR_PUBLIC",
    "NETWORK_INTERFACE",
    "PUBLIC_STATUS",
]
