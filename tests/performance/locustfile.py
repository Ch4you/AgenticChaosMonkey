"""
Locust performance test for Agent Chaos proxy.

Simulates concurrent agents making simple HTTP calls through the proxy.
"""

import os
from locust import HttpUser, task, between


TARGET_PATH = os.getenv("TARGET_PATH", "/health")


class AgentUser(HttpUser):
    wait_time = between(0.01, 0.1)

    @task
    def simple_request(self) -> None:
        self.client.get(TARGET_PATH, name=TARGET_PATH)
