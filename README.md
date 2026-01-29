# mujoco_experiments

### What you get

- **uv-managed Python env** (locked deps in `uv.lock`)
- **Minimal Gymnasium env** (`KitchenSceneEnv`) that attempts to load `Kitchen_set/Kitchen_set.usd`
- **Probe + runner scripts** in `scripts/`

### Quickstart

Create venv + install deps (already done in this repo, but reproducible):

```bash
cd /Users/pimvandenbosch/Desktop/mujoco_experiments
uv venv --python 3.11
uv sync
```

### Build MuJoCo with OpenUSD (inside this repo)

This will clone MuJoCo into `third_party/mujoco/`, build OpenUSD + MuJoCo, and then install the resulting **USD-enabled** MuJoCo Python package into your `uv` venv.

```bash
cd /Users/pimvandenbosch/Desktop/mujoco_experiments
chmod +x scripts/build_mujoco_usd.sh
./scripts/build_mujoco_usd.sh
```

Probe whether your installed MuJoCo build can import OpenUSD:

```bash
uv run python scripts/probe_usd_support.py
```

Run the env (opens a MuJoCo viewer if the model loads):

```bash
./.venv/bin/mjpython scripts/run_kitchen_env.py
```

View the scene (static viewer, auto-framed camera):

```bash
./.venv/bin/mjpython scripts/view_kitchen_usd.py
```

### The normal MuJoCo GUI window (recommended on macOS)

On macOS, the simplest way to get a **regular MuJoCo window** with USD support is to run the native `simulate` app we built (it supports drag-and-drop).

```bash
chmod +x scripts/run_simulate_kitchen.sh
./scripts/run_simulate_kitchen.sh
```

Then drag `Kitchen_set/Kitchen_set.usd` into the simulate window.

### World Labs: generate a Marble world from images (optional)

This repo includes a small CLI that uploads images and triggers a **multi-image** world generation job.

**Important**: do **not** hardcode your API key in code or commit it. Use an env var.

```bash
export WLT_API_KEY='YOUR_KEY_HERE'
uv run python scripts/worldlabs_from_images.py --images-dir test_pics --download-assets
```

Outputs:
- `worldlabs_out/<timestamp>/manifest.json`: operation id, media_asset ids, world id, asset URLs
- `worldlabs_out/<timestamp>/assets/`: downloaded assets (if `--download-assets`):
  - `splats_*.spz` (Gaussian splats)
  - `collider_mesh.glb`
  - `pano.jpg`
  - `thumbnail.jpg`

### Important caveat: OpenUSD import

The **PyPI `mujoco` wheel on macOS typically does not include USD import**.
This repo therefore **does not install `mujoco` from PyPI via `uv`**; instead, `scripts/build_mujoco_usd.sh` builds MuJoCo+OpenUSD and installs the resulting Python bindings into `.venv`.

So loading `Kitchen_set/Kitchen_set.usd` will fail unless you install a **custom MuJoCo build compiled with OpenUSD**:

- Build MuJoCo with `-DMUJOCO_WITH_USD=True`
- Link against OpenUSD (pxr)

MuJoCo’s official build notes are here:
`https://mujoco.readthedocs.io/en/latest/OpenUSD/building.html`

### Kitchen USD: mesh inertia workaround

This kitchen scene contains some meshes with near-zero volume (e.g. thin cables). When importing USD, MuJoCo may error:
`mesh volume is too small ... Try setting inertia to shell`

The loader in this repo automatically retries USD import with **shell inertia for all mesh assets**, via `MjSpec.meshes[*].inertia = mjMESH_INERTIA_SHELL`, then recompiles.
