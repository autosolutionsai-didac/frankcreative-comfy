import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from custom_nodes.frank_create.demo_seed import reset_and_seed_demo
from custom_nodes.frank_create.store import FrankCreateStore


def main():
    parser = argparse.ArgumentParser(description="Reset and seed Frank Create demo data.")
    parser.add_argument("--root", help="Optional Frank Create user data root for tests or isolated demos.")
    parser.add_argument("--no-assets", action="store_true", help="Seed the session and prompt only, without local images.")
    args = parser.parse_args()

    store = FrankCreateStore(root_dir=args.root) if args.root else FrankCreateStore()
    result = reset_and_seed_demo(store, create_assets=not args.no_assets)
    session = result["session"]
    turn = result["turn"]
    image_count = len(result.get("assets") or [])
    motion_count = len(result.get("video_assets") or [])
    print(f"Reset Frank Create demo data: {session['name']} ({session['id']})")
    print(f"Seeded prompt turn: {turn['id']}")
    print(f"Seeded demo assets: {image_count + motion_count}")
    print(f"Seeded demo image assets: {image_count}")
    print(f"Seeded demo motion assets: {motion_count}")


if __name__ == "__main__":
    main()
