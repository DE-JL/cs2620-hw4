import yaml
import importlib.resources

config_path = importlib.resources.files(__package__) / "config.yaml"

with config_path.open() as f:
    config = yaml.safe_load(f)

PUBLIC_STATUS = config["network"]["public_status"]
NETWORK_INTERFACE = config["network"]["interface"]
LOCALHOST = config["network"]["localhost"]
SERVER_PORT = config["network"]["server_port"]
PROTOCOL_TYPE = config["protocol_type"]
DEBUG = config["debug"]
GUI_REFRESH_RATE = config["gui_refresh_rate"]

__all__ = [
    "PUBLIC_STATUS",
    "NETWORK_INTERFACE",
    "LOCALHOST",
    "SERVER_PORT",
    "PROTOCOL_TYPE",
    "DEBUG",
    "GUI_REFRESH_RATE",
]
