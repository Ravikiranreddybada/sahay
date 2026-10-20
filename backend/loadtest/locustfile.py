"""locust -f backend/loadtest/locustfile.py --host http://localhost:8000 -u 200 -r 20

Capacity runs: start the API with SAHAY_RATE_LIMIT_PER_MIN=1000000, otherwise 3 demo personas share
3 per-user budgets and dev-login is limited per IP, so most requests measure the limiter, not the agent."""

import random
import uuid

from locust import HttpUser, between, task

USERS = ["U1001", "U1002", "U1003"]


class CareUser(HttpUser):
    wait_time = between(5, 30)  # think time between turns (see stress-1-lakh-concurrent.md)

    def on_start(self) -> None:
        self.user = random.choice(USERS)
        self.thread = f"lc-{uuid.uuid4().hex[:8]}"
        # user identity comes from a signed session, never the body (ADR-0014)
        tok = self.client.post("/v1/auth/dev-login", json={"persona": self.user}, name="/v1/auth/dev-login").json()["token"]
        self.auth = {"Authorization": f"Bearer {tok}"}

    def chat(self, message: str) -> None:
        self.client.post("/v1/chat", json={"thread_id": self.thread, "message": message}, headers=self.auth, name="/v1/chat")

    @task(35)
    def status(self) -> None:
        self.chat(random.choice(["Where is my order ORD-1042?", "Is my LAB-7781 report ready?", "status of claim CLM-55020"]))

    @task(25)
    def policy(self) -> None:
        self.chat(random.choice(["How long does a refund take for a cancelled medicine order?", "do I need to fast for HbA1c"]))

    @task(15)
    def journey(self) -> None:
        self.chat("Is Aarav's next vaccine due?")

    @task(5)
    def safety(self) -> None:
        self.chat("My father has chest pain")
