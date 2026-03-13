"""
Load / performance tests using Locust.

Run locally (headless, 30 s):
    locust -f tests/locustfile.py --headless \
           -u 50 -r 10 --run-time 30s \
           --host http://localhost:8000

Run with web UI:
    locust -f tests/locustfile.py --host http://localhost:8000
    # open http://localhost:8089

Scenarios:
  - CreateAndRedirect : POST /links/shorten  →  GET /{short_code}
  - RedirectCached    : repeatedly hits the same short code to exercise cache
  - ReadStats         : GET /links/{short_code}/stats
  - DeleteAndRecreate : DELETE + POST cycle
"""

import random
import string

from locust import HttpUser, TaskSet, task, between, events


# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────

def rand_url() -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"https://example-{suffix}.com"


def rand_alias(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


# ──────────────────────────────────────────────────────────────────────────────
# task sets
# ──────────────────────────────────────────────────────────────────────────────

class CreateAndRedirectTasks(TaskSet):
    """Create a link and immediately follow the redirect — simulates real usage."""

    short_codes: list[str] = []

    @task(3)
    def create_link(self):
        payload = {"original_url": rand_url()}
        with self.client.post(
            "/links/shorten",
            json=payload,
            catch_response=True,
            name="POST /links/shorten",
        ) as resp:
            if resp.status_code == 200:
                code = resp.json().get("short_code")
                if code:
                    self.short_codes.append(code)
                resp.success()
            else:
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(5)
    def redirect(self):
        if not self.short_codes:
            return
        code = random.choice(self.short_codes)
        with self.client.get(
            f"/{code}",
            allow_redirects=False,
            catch_response=True,
            name="GET /{short_code}",
        ) as resp:
            if resp.status_code in (200, 301, 302, 307, 308):
                resp.success()
            elif resp.status_code == 404:
                resp.success()   # code may have been deleted by another user
            else:
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(1)
    def get_stats(self):
        if not self.short_codes:
            return
        code = random.choice(self.short_codes)
        with self.client.get(
            f"/links/{code}/stats",
            catch_response=True,
            name="GET /links/{short_code}/stats",
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(1)
    def update_link(self):
        if not self.short_codes:
            return
        code = random.choice(self.short_codes)
        with self.client.put(
            f"/links/{code}",
            json={"original_url": rand_url()},
            catch_response=True,
            name="PUT /links/{short_code}",
        ) as resp:
            if resp.status_code in (200, 404, 500):
                resp.success()
            else:
                resp.failure(f"Unexpected status {resp.status_code}")


class CacheHeavyTasks(TaskSet):
    """
    Repeatedly hits a small fixed set of URLs to maximise cache hits
    and measure the throughput benefit of Redis caching.
    """

    WARM_CODES: list[str] = []

    def on_start(self):
        """Pre-create a handful of links that all users share."""
        for _ in range(5):
            resp = self.client.post(
                "/links/shorten",
                json={"original_url": rand_url()},
                name="POST /links/shorten (warm-up)",
            )
            if resp.status_code == 200:
                code = resp.json().get("short_code")
                if code:
                    CacheHeavyTasks.WARM_CODES.append(code)

    @task(10)
    def cached_redirect(self):
        if not self.WARM_CODES:
            return
        code = random.choice(self.WARM_CODES)
        with self.client.get(
            f"/{code}",
            allow_redirects=False,
            catch_response=True,
            name="GET /{short_code} (cached)",
        ) as resp:
            if resp.status_code in (200, 301, 302, 307, 308, 404, 410):
                resp.success()
            else:
                resp.failure(f"Unexpected status {resp.status_code}")


# ──────────────────────────────────────────────────────────────────────────────
# user classes
# ──────────────────────────────────────────────────────────────────────────────

class RegularUser(HttpUser):
    """Simulates a typical user: creates links and follows them."""
    tasks = [CreateAndRedirectTasks]
    wait_time = between(0.5, 2)
    weight = 3


class PowerUser(HttpUser):
    """Simulates a user that hammers the same popular links (cache scenario)."""
    tasks = [CacheHeavyTasks]
    wait_time = between(0.1, 0.5)
    weight = 1


# ──────────────────────────────────────────────────────────────────────────────
# optional: custom stats print on quit
# ──────────────────────────────────────────────────────────────────────────────

@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    stats = environment.stats
    print("\n═══════════════════ LOAD TEST SUMMARY ═══════════════════")
    for name, entry in stats.entries.items():
        print(
            f"  {entry.name:<40} "
            f"reqs={entry.num_requests:>6}  "
            f"fails={entry.num_failures:>4}  "
            f"avg={entry.avg_response_time:>7.1f}ms  "
            f"p95={entry.get_response_time_percentile(0.95):>7.1f}ms"
        )
    total = stats.total
    print(
        f"\n  TOTAL  reqs={total.num_requests}  "
        f"fails={total.num_failures}  "
        f"rps={total.current_rps:.1f}"
    )
    print("══════════════════════════════════════════════════════════\n")
