from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, cast

import mujoco


USD_SUFFIXES = {".usd", ".usda", ".usdc"}

# MuJoCo's Python type stubs can lag behind the runtime API; use an Any-cast for
# introspection-heavy code to keep pyright happy.
_mujoco_any = cast(Any, mujoco)


@dataclass(frozen=True)
class UsdSupport:
    """Describes whether this mujoco build can import OpenUSD into an MjModel."""

    supported: bool
    loader_name: Optional[str] = None


def detect_usd_support() -> UsdSupport:
    """Detect USD import support in the currently-imported `mujoco` package.

    The PyPI wheels typically ship without USD import enabled. Custom builds of
    MuJoCo (built with `-DMUJOCO_WITH_USD=True`) may expose additional APIs.
    """

    # Most-likely future API (mirrors from_xml_path / from_binary_path).
    if hasattr(_mujoco_any.MjModel, "from_usd_path"):
        return UsdSupport(supported=True, loader_name="mujoco.MjModel.from_usd_path")

    # Current working import path (MuJoCo 3.4.x): MjSpec can parse USD via from_file.
    if hasattr(_mujoco_any, "MjSpec") and hasattr(_mujoco_any.MjSpec, "from_file"):
        return UsdSupport(supported=True, loader_name="mujoco.MjSpec.from_file(...).compile()")

    return UsdSupport(supported=False)


def _usd_import_error(path: Path) -> RuntimeError:
    support = detect_usd_support()
    msg = (
        f"USD import is not available in the currently installed `mujoco` Python package.\n\n"
        f"Tried to load: {path}\n\n"
        f"Detected USD support: {support.supported} (loader={support.loader_name})\n\n"
        f"To load OpenUSD in MuJoCo you typically need to build MuJoCo from source with:\n"
        f"  -DMUJOCO_WITH_USD=True\n"
        f"and link it against OpenUSD (pxr).\n\n"
        f"See MuJoCo docs: https://mujoco.readthedocs.io/en/latest/OpenUSD/building.html\n\n"
        f"After installing that custom build into this uv venv, re-run this script.\n"
    )
    return RuntimeError(msg)


def load_mjmodel(model_path: str | Path) -> Any:
    """Load an `mujoco.MjModel` from MJCF/XML, MJB, or (if supported) OpenUSD."""

    path = Path(model_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(str(path))

    suffix = path.suffix.lower()
    if suffix in USD_SUFFIXES:
        # Preferred path when available.
        from_usd_path: Optional[Callable[[str], Any]] = getattr(
            _mujoco_any.MjModel, "from_usd_path", None
        )
        if callable(from_usd_path):
            return from_usd_path(str(path))

        # MuJoCo 3.4.x: parse USD into a spec, then compile to an MjModel.
        if hasattr(_mujoco_any, "MjSpec") and hasattr(_mujoco_any.MjSpec, "from_file"):
            spec = _mujoco_any.MjSpec.from_file(str(path))
            try:
                return spec.compile()
            except ValueError as e:
                # Common USD-import failure mode on large asset packs:
                # some meshes have near-zero volume, which breaks volume-based inertia.
                # Workaround: set all mesh assets to shell inertia and retry.
                msg = str(e)
                if "mesh volume is too small" in msg or "mesh volume is negative" in msg:
                    if hasattr(spec, "meshes") and hasattr(_mujoco_any, "mjtMeshInertia"):
                        shell = _mujoco_any.mjtMeshInertia.mjMESH_INERTIA_SHELL
                        for m in spec.meshes:
                            m.inertia = shell
                    return spec.compile()
                raise

        raise _usd_import_error(path)

    if suffix == ".mjb":
        return _mujoco_any.MjModel.from_binary_path(str(path))

    # Default: assume MJCF/XML.
    return _mujoco_any.MjModel.from_xml_path(str(path))


