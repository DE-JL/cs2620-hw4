import yaml
import importlib.resources

config_path = importlib.resources.files(__package__) / "config.yaml"

with config_path.open() as f:
    config = yaml.safe_load(f)

DEBUG = config["debug"]
GUI_REFRESH_RATE = config["gui_refresh_rate"]
LOCALHOST = config["network"]["localhost"]
NETWORK_INTERFACE = config["network"]["interface"]
PUBLIC_STATUS = config["network"]["public_status"]
SERVER_PORTS = config["network"]["server_ports"]

__all__ = [
    "DEBUG",
    "GUI_REFRESH_RATE",
    "LOCALHOST",
    "NETWORK_INTERFACE",
    "PUBLIC_STATUS",
    "SERVER_PORTS",
]
