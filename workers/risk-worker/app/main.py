"""
Risk Worker — Periodically scans learner data for multi-signal risk anomalies.
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
logger = logging.getLogger("risk-worker")

SCAN_INTERVAL = int(os.getenv("RISK_SCAN_INTERVAL_SECONDS", "60"))
API_URL = os.getenv("API_SERVICE_URL", "http://api:8000")
ADMIN_EMAIL = os.getenv("RISK_SCAN_ADMIN_EMAIL", "admin@acme.com")
ADMIN_PASSWORD = os.getenv("RISK_SCAN_ADMIN_PASSWORD", "Password123!")

shutdown_event = asyncio.Event()


def handle_signal(sig, frame):
    logger.info(f'{{"event": "shutdown_signal", "service": "risk-worker", "signal": "{sig}"}}')
    shutdown_event.set()


async def run_risk_scan(client: httpx.AsyncClient):
    """Logs in as admin and invokes the organization risk scan."""
    try:
        login_res = await client.post(
            f"{API_URL}/api/v1/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10.0,
        )
        if login_res.status_code != 200:
            logger.warning(
                f'{{"event": "scan_login_failed", "service": "risk-worker", "status": {login_res.status_code}}}'
            )
            return

        token = login_res.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}

        scan_res = await client.post(
            f"{API_URL}/api/v1/risks/scan",
            headers=headers,
            timeout=30.0,
        )
        if scan_res.status_code == 200:
            data = scan_res.json()
            summary = data.get("summary", {})
            logger.info(
                f'{{"event": "risk_scan_completed", "service": "risk-worker", '
                f'"evaluated": {summary.get("evaluated_enrollments", 0)}, '
                f'"high_or_critical": {summary.get("high_or_critical_risks", 0)}}}'
            )
        else:
            logger.warning(
                f'{{"event": "scan_failed", "service": "risk-worker", "status": {scan_res.status_code}}}'
            )
    except Exception as exc:
        logger.error(
            f'{{"event": "scan_exception", "service": "risk-worker", "error": "{str(exc)}"}}'
        )


async def main():
    logger.info(
        f'{{"event": "startup", "service": "risk-worker", '
        f'"scan_interval_seconds": {SCAN_INTERVAL}, "api_target": "{API_URL}"}}'
    )

    async with httpx.AsyncClient() as client:
        # Initial scan on worker startup
        await run_risk_scan(client)

        while not shutdown_event.is_set():
            try:
                # Wait until next scan interval or shutdown
                await asyncio.sleep(SCAN_INTERVAL)
                if not shutdown_event.is_set():
                    await run_risk_scan(client)
            except asyncio.CancelledError:
                break

    logger.info('{"event": "shutdown", "service": "risk-worker", "message": "Risk worker stopped"}')


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    asyncio.run(main())
