import netifaces

from config import ID_TO_ADDR_LOCAL, ID_TO_ADDR_PUBLIC, NETWORK_INTERFACE, PUBLIC_STATUS


def get_ipaddr() -> str | None:
    """
    Retrieve the IPv4 address of the specified network interface.

    :return: The IPv4 address as a string or None if not found.
    """
    try:
        addrs = netifaces.ifaddresses(NETWORK_INTERFACE)

        # netifaces.AF_INET is the IPv4 family
        if netifaces.AF_INET in addrs:
            # Each entry looks like {'addr': '10.X.X.X', 'netmask': '255.255.0.0', 'broadcast': '10.250.255.255'}
            return addrs[netifaces.AF_INET][0]['addr']

    except ValueError:
        # NETWORK_INTERFACE might not exist on this machine
        return None


def get_id_to_addr_map() -> dict[int, str]:
    """
    Generates and returns a mapping of server IDs to their corresponding IP addresses and ports.

    :return: A map from server ID to their address.
    """
    return ID_TO_ADDR_PUBLIC if PUBLIC_STATUS else ID_TO_ADDR_LOCAL
