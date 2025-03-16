import netifaces

from config import NETWORK_INTERFACE


def get_ipaddr():
    try:
        addrs = netifaces.ifaddresses(NETWORK_INTERFACE)

        # netifaces.AF_INET is the IPv4 family
        if netifaces.AF_INET in addrs:
            # Each entry looks like {'addr': '10.X.X.X', 'netmask': '255.255.0.0', 'broadcast': '10.250.255.255'}
            return addrs[netifaces.AF_INET][0]['addr']

    except ValueError:
        # NETWORK_INTERFACE might not exist on this machine
        return None
