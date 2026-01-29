from __future__ import annotations

from pathlib import Path

import mujoco

from kitchen_usd_mujoco.loaders import detect_usd_support, load_mjmodel


def main() -> None:
    print("mujoco version:", mujoco.__version__)
    print("mujoco module:", getattr(mujoco, "__file__", None))
    print("MjModel from_*:", [m for m in dir(mujoco.MjModel) if m.startswith("from_")])
    print("detect_usd_support:", detect_usd_support())

    kitchen = Path("Kitchen_set/Kitchen_set.usd").resolve()
    print("kitchen exists:", kitchen.exists(), kitchen)

    if kitchen.exists():
        try:
            _ = load_mjmodel(kitchen)
            print("Loaded kitchen USD successfully.")
        except Exception as e:
            print("Loading kitchen USD failed:")
            print(type(e).__name__ + ":", e)


if __name__ == "__main__":
    main()


