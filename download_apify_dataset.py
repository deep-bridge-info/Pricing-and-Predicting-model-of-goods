import os
import json
import argparse
from datetime import datetime
from apify.client import ApifyClient


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True)
    p.add_argument("--out")
    p.add_argument("--token")
    p.add_argument("--batch", type=int, default=1000)
    args = p.parse_args()

    token = args.token or os.environ.get("APIFY_TOKEN")
    if not token:
        raise SystemExit("Missing APIFY_TOKEN. Use --token or set env.")

    client = ApifyClient(api_token=token)
    items = []
    offset = 0
    while True:
        batch = client.get_dataset_items(args.dataset, limit=args.batch, offset=offset)
        if not batch:
            break
        items.extend(batch)
        offset += len(batch)

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")[:-3]
    out = args.out or f"dataset_{args.dataset}_{ts}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(out)


if __name__ == "__main__":
    main()

