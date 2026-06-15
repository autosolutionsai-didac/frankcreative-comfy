import sys
from pathlib import Path

from .comfy_workflow import FrankCreateVariantNode

NODE_CLASS_MAPPINGS = {
    "FrankCreateVariant": FrankCreateVariantNode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "FrankCreateVariant": "Frank Create Variant",
}

if any(Path(arg).name == "main.py" for arg in sys.argv) or "server" in sys.modules:
    try:
        from .routes import register_routes

        register_routes()
    except Exception as exc:
        print(f"[Frank Create] Route registration skipped: {exc}")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
