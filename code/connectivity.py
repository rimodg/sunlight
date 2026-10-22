"""Explicit offline policy. Local analysis never requires remote availability."""
import ipaddress
import os
import sys

_installed = False


def offline_enabled():
    return os.environ.get('SUNLIGHT_OFFLINE', '').lower() in {'1','true','yes'}


def state_directory():
    from pathlib import Path
    return Path(os.environ.get('SUNLIGHT_CALIBRATION_DIR', Path(__file__).resolve().parents[1]/'calibration'))


def _local(host):
    if host is None or host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(str(host).split('%')[0]).is_loopback
    except ValueError:
        return False


def install_offline_guard():
    """Block non-loopback Python socket traffic, including proxy and DNS calls.

    This is an application runtime policy, not an operating-system firewall.
    Local browser/API and Unix-domain sockets remain usable.
    """
    global _installed
    if _installed:
        return
    def audit(event, args):
        if not offline_enabled():
            return
        if event in {'socket.getaddrinfo','socket.gethostbyname','socket.gethostbyaddr'}:
            if not _local(args[0]):
                raise OSError('SUNLIGHT offline policy blocks external name resolution')
        elif event in {'socket.connect','socket.sendto'}:
            address = args[1] if event == 'socket.connect' else args[-1]
            if isinstance(address, tuple) and not _local(address[0]):
                raise OSError('SUNLIGHT offline policy blocks external network connections')
    sys.addaudithook(audit)
    _installed = True
