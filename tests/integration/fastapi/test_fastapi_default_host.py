"""run_fastapi with no host must answer on a non-loopback address, as Docker and hosted sandboxes need."""

import os
import socket
import subprocess
import sys
import time

import httpx

SERVER_SCRIPT = """
import sys
from agency_swarm import Agency, Agent
from agency_swarm.integrations.fastapi import run_fastapi

def create_agency(load_threads_callback=None, save_threads_callback=None):
    return Agency(Agent(name="CEO", instructions="test"), name="host_agency")

run_fastapi(agencies={"host_agency": create_agency}, port=int(sys.argv[1]))
"""


def _non_loopback_address() -> str:
    # A UDP connect sends no packet; it only asks the OS which interface routes outward.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(("192.0.2.1", 80))
        address = str(sock.getsockname()[0])
    assert not address.startswith("127."), f"no non-loopback IPv4 interface found, got {address}"
    return address


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        return int(sock.getsockname()[1])


def test_run_fastapi_default_host_is_reachable_on_non_loopback_address() -> None:
    address = _non_loopback_address()
    port = _free_port()
    env = {key: value for key, value in os.environ.items() if key != "APP_TOKEN"}
    env.setdefault("OPENAI_API_KEY", "sk-test")
    server = subprocess.Popen(
        [sys.executable, "-c", SERVER_SCRIPT, str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        url = f"http://{address}:{port}/host_agency/get_metadata"
        deadline = time.monotonic() + 30
        response: httpx.Response | None = None
        while time.monotonic() < deadline and server.poll() is None:
            try:
                response = httpx.get(url, timeout=2)
                break
            except httpx.TransportError:
                time.sleep(0.2)
        assert server.poll() is None, f"server exited: {server.stderr.read().decode() if server.stderr else ''}"
        assert response is not None, f"server never answered on {url}"
        assert response.status_code == 200
        assert response.json()["metadata"]["agencyName"] == "host_agency"
    finally:
        server.terminate()
        server.wait(timeout=10)
