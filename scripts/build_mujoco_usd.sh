#!/usr/bin/env bash
set -euo pipefail

# Build MuJoCo with OpenUSD enabled, entirely inside this repo, and install its
# Python package into the repo's uv venv.
#
# This script is intended for macOS/Linux. It assumes you have:
# - git
# - cmake
# - a working C/C++ toolchain (Xcode CLT on macOS)
#
# Usage:
#   cd /path/to/this/repo
#   ./scripts/build_mujoco_usd.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TP_DIR="${ROOT_DIR}/third_party"
MUJOCO_DIR="${TP_DIR}/mujoco"

USD_CMAKE_DIR="${MUJOCO_DIR}/cmake/third_party_deps/openusd"
USD_BUILD_DIR="${USD_CMAKE_DIR}/build"

# IMPORTANT:
# MuJoCo's OpenUSD helper project installs into `${MUJOCO_DIR}/build/_deps/...` via
# a relative path in `cmake/third_party_deps/openusd/CMakeLists.txt`.
# So we build MuJoCo in `${MUJOCO_DIR}/build` to match the expected location.
MUJOCO_BUILD_DIR="${MUJOCO_DIR}/build"

JOBS="${JOBS:-8}"

echo "[info] repo: ${ROOT_DIR}"
echo "[info] third_party: ${TP_DIR}"

mkdir -p "${TP_DIR}"

if [[ ! -d "${MUJOCO_DIR}/.git" ]]; then
  echo "[info] cloning MuJoCo into ${MUJOCO_DIR}"
  git clone https://github.com/google-deepmind/mujoco "${MUJOCO_DIR}"
else
  echo "[info] MuJoCo already cloned: ${MUJOCO_DIR}"
fi

echo "[info] building OpenUSD (MuJoCo helper project)"
cmake -B "${USD_BUILD_DIR}" -S "${USD_CMAKE_DIR}" -DBUILD_USD=True
cmake --build "${USD_BUILD_DIR}" -j "${JOBS}"

echo "[info] building MuJoCo with OpenUSD enabled"
cmake -B "${MUJOCO_BUILD_DIR}" -S "${MUJOCO_DIR}" -DMUJOCO_WITH_USD=True
cmake --build "${MUJOCO_BUILD_DIR}" -j "${JOBS}"

echo "[info] installing MuJoCo Python package into this repo's uv venv"
cd "${ROOT_DIR}"

# Some uv-created venvs don't include pip by default. Bootstrap it.
uv run python -m ensurepip --upgrade || true

# The MuJoCo python CMake project expects a `simulate/` subdirectory under
# `python/mujoco/`. In some source checkouts this isn't present, but the top-level
# `simulate/` directory is. Create a symlink so `add_subdirectory(simulate)` works.
if [[ ! -d "${MUJOCO_DIR}/python/mujoco/simulate" ]]; then
  echo "[info] creating python/mujoco/simulate -> ../../simulate symlink"
  (cd "${MUJOCO_DIR}/python/mujoco" && ln -s ../../simulate simulate)
fi

# The MuJoCo python source build expects these to be set so it can find the
# already-built MuJoCo library + headers + plugins.
export MUJOCO_PATH="${MUJOCO_DIR}"
export MUJOCO_PLUGIN_PATH="${MUJOCO_DIR}/build/lib"

# Work around: this MuJoCo checkout does not ship `python/mujoco/cmake/`, but
# the Python bindings' setup.py sets CMAKE_MODULE_PATH to that location.
# Provide the correct module path (top-level MuJoCo `cmake/`) via MUJOCO_CMAKE_ARGS.
export MUJOCO_CMAKE_ARGS="${MUJOCO_CMAKE_ARGS:-} -DCMAKE_MODULE_PATH:PATH=${MUJOCO_DIR}/cmake"

# Ensure we're not accidentally importing the PyPI wheel.
uv run python -m pip uninstall -y mujoco || true

# Install the source-tree python package (editable is easiest while iterating).
uv run python -m pip install -e "${MUJOCO_DIR}/python"

echo "[info] done. Probing USD support..."
uv run python scripts/probe_usd_support.py


