#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SIMULATE="${ROOT_DIR}/third_party/mujoco/install/bin/simulate"
USD="${ROOT_DIR}/Kitchen_set/Kitchen_set.usd"
LIB="${ROOT_DIR}/third_party/mujoco/install/lib"
MJB="${ROOT_DIR}/generated/kitchen_shell.mjb"
MJB_COLLIDE="${ROOT_DIR}/generated/kitchen_proxy_collide.mjb"

export DYLD_LIBRARY_PATH="${LIB}${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
export MUJOCO_PLUGIN_PATH="${ROOT_DIR}/third_party/mujoco/install/bin/mujoco_plugin"

mkdir -p "${ROOT_DIR}/generated"

COLLISIONS="${COLLISIONS:-1}"
OUT="${MJB}"
if [[ "${COLLISIONS}" != "0" ]]; then
  OUT="${MJB_COLLIDE}"
fi

echo "[info] compiling USD -> MJB"
echo "[info] input : ${USD}"
echo "[info] output: ${OUT}"
echo "[info] collisions: ${COLLISIONS} (1=enable simple proxy collisions; 0=visual-only)"
uv run python - <<PY
from pathlib import Path
import mujoco

usd = Path("${USD}")
out = "${OUT}"

spec = mujoco.MjSpec.from_file(str(usd))

# Workaround for thin meshes (e.g. cables): use shell inertia for all mesh assets.
shell = mujoco.mjtMeshInertia.mjMESH_INERTIA_SHELL
for m in spec.meshes:
    m.inertia = shell

model0 = spec.compile()

# Collisions: this USD asset pack imports as visual mesh geoms (contype/conaffinity=0),
# and turning mesh collisions on globally can fail on degenerate/planar meshes (qhull).
# So we keep imported meshes visual-only and add a few simple box colliders.
if int("${COLLISIONS}") != 0:
    center = model0.stat.center.copy()
    extent = float(model0.stat.extent)
    wb = spec.worldbody

    def add_box(name, pos, size):
        g = wb.add_geom()
        g.name = name
        g.type = mujoco.mjtGeom.mjGEOM_BOX
        g.pos[:] = pos
        g.size[:] = size
        g.contype = 1
        g.conaffinity = 1
        g.condim = 3
        return g

    # Floor plate.
    floor_th = max(0.05, extent * 0.02)
    add_box(
        "proxy_floor",
        [center[0], center[1], center[2] - extent * 0.6],
        [extent * 1.6, extent * 1.6, floor_th],
    )

    # Simple boundary walls so you can see contact behavior immediately.
    wall_th = max(0.05, extent * 0.02)
    wall_h = max(0.3, extent * 0.8)
    r = extent * 1.2
    add_box("proxy_wall_px", [center[0] + r, center[1], center[2]], [wall_th, r, wall_h])
    add_box("proxy_wall_nx", [center[0] - r, center[1], center[2]], [wall_th, r, wall_h])
    add_box("proxy_wall_py", [center[0], center[1] + r, center[2]], [r, wall_th, wall_h])
    add_box("proxy_wall_ny", [center[0], center[1] - r, center[2]], [r, wall_th, wall_h])

    for g in spec.geoms:
        if not g.name.startswith("proxy_"):
            g.contype = 0
            g.conaffinity = 0

model = spec.compile()
mujoco.mj_saveModel(model, out)
print("saved:", out)
PY

echo "[info] launching: ${SIMULATE}"
echo "[info] opening: ${OUT}"

exec "${SIMULATE}" "${OUT}"


