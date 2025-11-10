import json
import logging
import time
from typing import Any, Dict, Iterable, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

class RequestHandler:
    """
    Thin wrapper around requests.Session that adds retries, basic logging,
    and JSON parsing.
    """

    def __init__(
        self,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff_factor: float = 1.5,
    ) -> None:
        self.session = requests.Session()
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        expected_status_codes: Iterable[int] = (200,),
    ) -> Optional[Dict[str, Any]]:
        """
        Perform a GET request and return the parsed JSON response.

        If the response status code is in `expected_status_codes`,
        attempts to parse JSON; otherwise logs and returns None.
        """
        attempt = 0
        expected_set = set(expected_status_codes)

        while attempt < self.max_retries:
            attempt += 1
            try:
                logger.debug("GET %s params=%s (attempt %s)", url, params, attempt)
                resp = self.session.get(url, params=params, timeout=self.timeout)
                status = resp.status_code

                if status not in expected_set:
                    # For some endpoints (like commentThreads), 403/404 are expected failures.
                    logger.warning(
                        "Unexpected status %s from %s (attempt %s): %s",
                        status,
                        resp.url,
                        attempt,
                        resp.text[:500],
                    )
                    if status >= 500 and attempt < self.max_retries:
                        self._sleep_backoff(attempt)
                        continue
                    try:
                        return resp.json()
                    except json.JSONDecodeError:
                        return None

                try:
                    return resp.json()
                except json.JSONDecodeError:
                    logger.error("Failed to parse JSON from %s", resp.url)
                    return None

            except requests.RequestException as exc:
                logger.warning(
                    "Request error on %s (attempt %s): %s", url, attempt, exc
                )
                if attempt >= self.max_retries:
                    break
                self._sleep_backoff(attempt)

        logger.error("Giving up on %s after %s attempts", url, self.max_retries)
        return None

    def _sleep_backoff(self, attempt: int) -> None:
        delay = self.backoff_factor * (2 ** (attempt - 1))
        logger.debug("Sleeping for %.2f seconds before retry", delay)
        time.sleep(delay)