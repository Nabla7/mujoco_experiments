from __future__ import annotations

import time

from kitchen_usd_mujoco.env import KitchenSceneEnv


def main() -> None:
    env = KitchenSceneEnv(
        model_path="Kitchen_set/Kitchen_set.usd",
        render_mode="human",
        frame_skip=10,
    )
    obs, info = env.reset()
    print("reset:", obs.shape, info)

    try:
        while True:
            action = env.action_space.sample()
            obs, rew, term, trunc, info = env.step(action)
            if term or trunc:
                env.reset()
            time.sleep(1.0 / 60.0)
    finally:
        env.close()


if __name__ == "__main__":
    main()


