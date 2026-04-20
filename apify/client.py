"""
Apify API client for running actors and retrieving results.
"""
import os
import time
from pathlib import Path
import requests
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

# Load .env if not already loaded
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
except ImportError:
    pass


@dataclass
class ActorRun:
    """Result of an actor run."""
    run_id: str
    status: str
    dataset_id: Optional[str] = None
    items: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.items is None:
            self.items = []


class ApifyClient:
    """Client for Apify API."""

    BASE_URL = "https://api.apify.com/v2"

    def __init__(self, api_token: Optional[str] = None):
        """
        Initialize client with API token.

        Args:
            api_token: Apify API token. If not provided, reads from APIFY_TOKEN env var.
        """
        self.api_token = api_token or os.environ.get("APIFY_TOKEN")
        if not self.api_token:
            raise ValueError(
                "Apify API token required. Set APIFY_TOKEN env var or pass api_token."
            )

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_token}"}

    def run_actor(
        self,
        actor_id: str,
        run_input: Dict[str, Any],
        wait_for_finish: bool = True,
        timeout_secs: int = 99999999999999999,
    ) -> ActorRun:
        """
        Run an Apify actor and optionally wait for completion.

        Args:
            actor_id: Actor ID (e.g., "shareze001/scrape-alibaba-products-by-keywords")
            run_input: Input for the actor
            wait_for_finish: Whether to wait for the run to complete
            timeout_secs: Maximum time to wait for completion

        Returns:
            ActorRun with status and items (if completed)
        """
        # Start the actor run
        url = f"{self.BASE_URL}/acts/{actor_id}/runs"
        response = requests.post(
            url,
            headers=self._headers(),
            json=run_input,
            params={"timeout": timeout_secs} if wait_for_finish else {},
        )
        response.raise_for_status()
        data = response.json()["data"]

        run_id = data["id"]
        status = data["status"]
        dataset_id = data.get("defaultDatasetId")

        if not wait_for_finish:
            return ActorRun(run_id=run_id, status=status, dataset_id=dataset_id)

        # Poll for completion if not using sync endpoint
        if status not in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            run = self._wait_for_run(run_id, timeout_secs)
            status = run["status"]
            dataset_id = run.get("defaultDatasetId")

        # Get dataset items if successful
        items = []
        if status == "SUCCEEDED" and dataset_id:
            items = self.get_dataset_items(dataset_id)

        return ActorRun(
            run_id=run_id,
            status=status,
            dataset_id=dataset_id,
            items=items,
        )

    def run_actor_sync(
        self,
        actor_id: str,
        run_input: Dict[str, Any],
        timeout_secs: int = 99999999999999999,
    ) -> List[Dict[str, Any]]:
        """
        Run actor and wait for completion, then return dataset items.

        Args:
            actor_id: Actor ID
            run_input: Input for the actor
            timeout_secs: Maximum time to wait

        Returns:
            List of dataset items
        """
        # Start the run
        result = self.run_actor(
            actor_id=actor_id,
            run_input=run_input,
            wait_for_finish=True,
            timeout_secs=timeout_secs,
        )

        if result.status != "SUCCEEDED":
            raise RuntimeError(f"Actor run failed with status: {result.status}")

        return result.items

    def _wait_for_run(
        self, run_id: str, timeout_secs: int, poll_interval: int = 5
    ) -> Dict[str, Any]:
        """Poll for run completion."""
        url = f"{self.BASE_URL}/actor-runs/{run_id}"
        start_time = time.time()

        while time.time() - start_time < timeout_secs:
            response = requests.get(url, headers=self._headers())
            response.raise_for_status()
            data = response.json()["data"]

            if data["status"] in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                return data

            time.sleep(poll_interval)

        raise TimeoutError(f"Actor run {run_id} did not complete within {timeout_secs}s")

    def get_dataset_items(
        self,
        dataset_id: str,
        limit: int = 9999999999999,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Get items from a dataset.

        Args:
            dataset_id: Dataset ID
            limit: Maximum number of items to return
            offset: Starting offset

        Returns:
            List of dataset items
        """
        url = f"{self.BASE_URL}/datasets/{dataset_id}/items"
        response = requests.get(
            url,
            headers=self._headers(),
            params={"limit": limit, "offset": offset},
        )
        response.raise_for_status()
        return response.json()

    def get_run_status(self, run_id: str) -> Dict[str, Any]:
        """Get status of an actor run."""
        url = f"{self.BASE_URL}/actor-runs/{run_id}"
        response = requests.get(url, headers=self._headers())
        response.raise_for_status()
        return response.json()["data"]
