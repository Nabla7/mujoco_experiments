from __future__ import annotations

import time
from pathlib import Path

import mujoco
import mujoco.viewer

from kitchen_usd_mujoco.loaders import load_mjmodel


def main() -> None:
    usd = Path("Kitchen_set/Kitchen_set.usd").resolve()
    model = load_mjmodel(usd)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    with mujoco.viewer.launch_passive(model, data) as viewer:
        # Auto-frame the scene.
        try:
            viewer.cam.lookat[:] = model.stat.center
            viewer.cam.distance = 3.0 * float(model.stat.extent)
            viewer.cam.azimuth = 90.0
            viewer.cam.elevation = -25.0
        except Exception:
            pass

        while True:
            viewer.sync()
            time.sleep(1.0 / 60.0)


if __name__ == "__main__":
    main()


