"""
Digest Worker — Periodically generates scheduled narrative learning intelligence digests.
"""
import asyncio
import logging
import os
import signal
import sys
import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("digest-worker")

DIGEST_INTERVAL = int(os.getenv("DIGEST_INTERVAL_SECONDS", "120"))
API_URL = os.getenv("API_SERVICE_URL", "http://api:8000")
ADMIN_EMAIL = os.getenv("DIGEST_ADMIN_EMAIL", "admin@acme.com")
ADMIN_PASSWORD = os.getenv("DIGEST_ADMIN_PASSWORD", "Password123!")

shutdown_event = asyncio.Event()


def handle_signal(sig, frame):
    logger.info(f'{{"event": "shutdown_signal", "service": "digest-worker", "signal": "{sig}"}}')
    shutdown_event.set()


async def run_digest_cycle(client: httpx.AsyncClient):
    """Logs in as admin and generates scheduled digests."""
    try:
        login_res = await client.post(
            f"{API_URL}/api/v1/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10.0,
        )
        if login_res.status_code != 200:
            logger.warning(f'{{"event": "digest_login_failed", "status": {login_res.status_code}}}')
            return

        token = login_res.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}

        digest_res = await client.post(
            f"{API_URL}/api/v1/reports/digest/generate",
            headers=headers,
            timeout=30.0,
        )
        if digest_res.status_code == 200:
            data = digest_res.json()
            logger.info(
                f'{{"event": "digest_generated", "digest_id": "{data.get("digest_id")}", '
                f'"recipients": {data.get("sent_to")}}}'
            )
        else:
            logger.warning(f'{{"event": "digest_failed", "status": {digest_res.status_code}}}')
    except Exception as exc:
        logger.error(f'{{"event": "digest_exception", "error": "{str(exc)}"}}')


async def main():
    logger.info(
        f'{{"event": "startup", "service": "digest-worker", '
        f'"interval_seconds": {DIGEST_INTERVAL}, "api_target": "{API_URL}"}}'
    )

    async with httpx.AsyncClient() as client:
        # Initial run
        await run_digest_cycle(client)

        while not shutdown_event.is_set():
            try:
                await asyncio.sleep(DIGEST_INTERVAL)
                if not shutdown_event.is_set():
                    await run_digest_cycle(client)
            except asyncio.CancelledError:
                break

    logger.info('{"event": "shutdown", "service": "digest-worker", "message": "Digest worker stopped"}')


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    asyncio.run(main())
