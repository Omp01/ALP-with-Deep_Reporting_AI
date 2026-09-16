"""
Health check script for all Adaptive LMS services.

Usage:
    python scripts/healthcheck.py [--wait]

Checks health endpoints for: API, Adaptive Engine, Reporting Engine, Ingestion.
With --wait, retries until all services are healthy (useful for CI/CD).
"""
import argparse
import sys
import time

import requests

SERVICES = {
    "API Service": "http://localhost:8000/health",
    "Adaptive Engine": "http://localhost:8001/health",
    "Reporting Engine": "http://localhost:8002/health",
    "Ingestion Service": "http://localhost:8003/health",
    "Frontend": "http://localhost:3000",
}


def check_service(name: str, url: str) -> bool:
    """Check if a service is healthy."""
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            print(f"  [OK] {name}: healthy")
            return True
        else:
            print(f"  [FAIL] {name}: unhealthy (status {r.status_code})")
            return False
    except requests.exceptions.ConnectionError:
        print(f"  [FAIL] {name}: unreachable")
        return False
    except Exception as e:
        print(f"  [FAIL] {name}: error ({e})")
        return False


def main():
    parser = argparse.ArgumentParser(description="Check Adaptive LMS service health")
    parser.add_argument("--wait", action="store_true", help="Wait until all services are healthy")
    parser.add_argument("--timeout", type=int, default=120, help="Max wait time in seconds")
    args = parser.parse_args()

    if args.wait:
        print("Waiting for all services to become healthy...")
        start = time.time()
        while time.time() - start < args.timeout:
            print(f"\n[{int(time.time() - start)}s] Checking services...")
            results = [check_service(name, url) for name, url in SERVICES.items()]
            if all(results):
                print("\n[OK] All services healthy!")
                sys.exit(0)
            time.sleep(5)
        print(f"\n[FAIL] Timeout after {args.timeout}s — not all services are healthy.")
        sys.exit(1)
    else:
        print("Checking Adaptive LMS services...\n")
        results = [check_service(name, url) for name, url in SERVICES.items()]
        healthy = sum(results)
        total = len(results)
        print(f"\n{healthy}/{total} services healthy")
        sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
