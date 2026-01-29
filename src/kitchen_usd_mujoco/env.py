from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, cast

import gymnasium as gym
import mujoco as _mujoco
import numpy as np

from .loaders import load_mjmodel

_mujoco_any = cast(Any, _mujoco)


@dataclass
class StepInfo:
    time: float
    nstep: int


class KitchenSceneEnv(gym.Env[np.ndarray, np.ndarray]):
    """A minimal Gymnasium env wrapper for stepping a MuJoCo scene/model.

    This env is intentionally lightweight: it exposes the MuJoCo state as the
    observation and accepts control inputs for actuators (if any).
    """

    metadata = {"render_modes": ["human"], "render_fps": 60}

    def __init__(
        self,
        model_path: str | Path,
        render_mode: Optional[str] = None,
        frame_skip: int = 10,
        seed: Optional[int] = None,
    ):
        super().__init__()
        self.model_path = Path(model_path)
        self.render_mode = render_mode
        self.frame_skip = int(frame_skip)
        if self.frame_skip < 1:
            raise ValueError("frame_skip must be >= 1")

        self._rng = np.random.default_rng(seed)

        self.model = load_mjmodel(self.model_path)
        self.data = _mujoco_any.MjData(self.model)

        # Action/obs spaces (simple, generic defaults).
        nu = int(self.model.nu)
        nq = int(self.model.nq)
        nv = int(self.model.nv)

        self.action_space = gym.spaces.Box(
            low=-1.0, high=1.0, shape=(nu,), dtype=np.float32
        )
        self.observation_space = gym.spaces.Box(
            low=-np.inf, high=np.inf, shape=(nq + nv,), dtype=np.float64
        )

        self._viewer: Any = None

    def _get_obs(self) -> np.ndarray:
        return np.concatenate([self.data.qpos.copy(), self.data.qvel.copy()])

    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)

        _mujoco_any.mj_resetData(self.model, self.data)
        _mujoco_any.mj_forward(self.model, self.data)
        obs = self._get_obs()
        info = {"time": float(self.data.time)}
        return obs, info

    def step(self, action: np.ndarray):
        action = np.asarray(action, dtype=np.float32)
        if action.shape != self.action_space.shape:
            raise ValueError(f"Expected action shape {self.action_space.shape}, got {action.shape}")

        # If the scene has no actuators, ignore the action.
        if self.model.nu > 0:
            self.data.ctrl[:] = action

        for _ in range(self.frame_skip):
            _mujoco_any.mj_step(self.model, self.data)

        obs = self._get_obs()
        reward = 0.0
        terminated = False
        truncated = False
        info = StepInfo(time=float(self.data.time), nstep=int(self.data.nstep)).__dict__

        if self.render_mode == "human":
            self.render()

        return obs, reward, terminated, truncated, info

    def render(self):
        if self.render_mode != "human":
            return None

        # Lazy-create viewer; keep it open across steps.
        if self._viewer is None:
            self._viewer = _mujoco_any.viewer.launch_passive(self.model, self.data)
        else:
            # passive viewer needs explicit sync
            self._viewer.sync()

        return None

    def close(self):
        if self._viewer is not None:
            try:
                self._viewer.close()
            finally:
                self._viewer = None


