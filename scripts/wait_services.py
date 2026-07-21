from __future__ import annotations

import sys
import time

import httpx

from common import api_headers, lightrag_url, load_env, neo4j_query


def main() -> None:
    env = load_env()
    deadline = time.monotonic() + 360
    last_error = "services have not responded"
    while time.monotonic() < deadline:
        try:
            neo4j_query(env, "RETURN 1 AS ready")
            response = httpx.get(
                lightrag_url(env, "/health"), headers=api_headers(env), timeout=10
            )
            response.raise_for_status()
            health = response.json()
            if health.get("status") != "healthy":
                raise RuntimeError(f"unexpected LightRAG health response: {health}")
            graph_storage = health.get("configuration", {}).get("graph_storage")
            if graph_storage != "Neo4JStorage":
                raise RuntimeError(f"LightRAG graph storage is {graph_storage!r}, expected Neo4JStorage")
            print("services   OK (Neo4j + LightRAG)")
            return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(5)
    raise RuntimeError(f"Services did not become ready within 360 seconds: {last_error}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"services   FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)

