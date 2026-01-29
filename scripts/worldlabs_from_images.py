from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from kitchen_usd_mujoco.worldlabs_marble import (
    WorldLabsError,
    _guess_mime_type,
    prepare_upload,
    upload_bytes,
    wait_for_operation,
    worlds_get,
    worlds_generate,
)


def _now_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _iter_images(folder: Path) -> list[Path]:
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    paths = [p for p in sorted(folder.iterdir()) if p.is_file() and p.suffix.lower() in exts]
    return paths


def _azimuths(n: int) -> list[float]:
    if n <= 0:
        return []
    step = 360.0 / float(n)
    return [round(i * step, 3) for i in range(n)]


def _download(url: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=300.0) as resp:
        out_path.write_bytes(resp.read())


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Upload images to World Labs (Marble) and generate a world (multi-image)."
    )
    parser.add_argument(
        "--images-dir",
        default=str(Path("test_pics").resolve()),
        help="Directory containing input images (jpg/jpeg/png/webp).",
    )
    parser.add_argument(
        "--out-dir",
        default=str(Path("worldlabs_out").resolve() / _now_slug()),
        help="Output directory for manifest + optional downloaded assets.",
    )
    parser.add_argument("--display-name", default=None, help="Optional world display name.")
    parser.add_argument(
        "--text-prompt",
        default=None,
        help="Optional text guidance; if omitted World Labs may auto-caption/recaption.",
    )
    parser.add_argument(
        "--model",
        default="Marble 0.1-plus",
        choices=["Marble 0.1-plus", "Marble 0.1-mini"],
        help="Model to use (mini is cheaper/faster).",
    )
    parser.add_argument(
        "--n-images",
        type=int,
        default=4,
        help="How many images to use (max 4 normally; max 8 with --reconstruct-images).",
    )
    parser.add_argument(
        "--reconstruct-images",
        action="store_true",
        help="Enable reconstruction mode (allows up to 8 images per docs).",
    )
    parser.add_argument(
        "--public",
        action="store_true",
        help="Make the generated world public (default: private).",
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=900.0,
        help="Operation timeout in seconds.",
    )
    parser.add_argument(
        "--download-assets",
        action="store_true",
        help="Download returned assets (SPZ/GLB/pano/thumbnail) into --out-dir.",
    )
    args = parser.parse_args(argv)

    api_key = os.environ.get("WLT_API_KEY", "").strip()
    if not api_key:
        print("Missing WLT_API_KEY env var. Example:\n  export WLT_API_KEY='...'\n", file=sys.stderr)
        return 2

    images_dir = Path(args.images_dir).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    images = _iter_images(images_dir)
    if not images:
        print(f"No images found in {images_dir}", file=sys.stderr)
        return 2

    max_n = 8 if args.reconstruct_images else 4
    n = max(1, min(int(args.n_images), max_n, len(images)))
    selected = images[:n]
    az = _azimuths(n)

    manifest: dict[str, Any] = {
        "images_dir": str(images_dir),
        "out_dir": str(out_dir),
        "selected_images": [str(p) for p in selected],
        "model": args.model,
        "public": bool(args.public),
        "reconstruct_images": bool(args.reconstruct_images),
        "text_prompt": args.text_prompt,
        "uploads": [],
    }

    try:
        media_items = []
        for p, a in zip(selected, az, strict=True):
            ext = p.suffix.lower().lstrip(".")
            prep = prepare_upload(
                api_key=api_key,
                file_name=p.name,
                kind="image",
                extension=ext,
                metadata={"source_path": str(p), "azimuth": a},
            )
            media_asset = prep.get("media_asset", {}) if isinstance(prep.get("media_asset"), dict) else {}
            upload_info = prep.get("upload_info", {}) if isinstance(prep.get("upload_info"), dict) else {}

            media_asset_id = media_asset.get("media_asset_id")
            upload_url = upload_info.get("upload_url")
            required_headers = upload_info.get("required_headers")

            if not isinstance(media_asset_id, str) or not isinstance(upload_url, str):
                raise WorldLabsError(f"Unexpected prepare_upload response: {json.dumps(prep)}")

            data = p.read_bytes()
            upload_bytes(
                upload_url=upload_url,
                data=data,
                required_headers=required_headers if isinstance(required_headers, dict) else None,
                content_type=_guess_mime_type(ext),
            )

            manifest["uploads"].append(
                {
                    "path": str(p),
                    "azimuth": a,
                    "media_asset_id": media_asset_id,
                    "prepare_upload": prep,
                }
            )

            media_items.append(
                {"azimuth": a, "content": {"source": "media_asset", "media_asset_id": media_asset_id}}
            )

        world_prompt: dict[str, Any] = {
            "type": "multi-image",
            "multi_image_prompt": media_items,
            "reconstruct_images": bool(args.reconstruct_images),
        }
        if args.text_prompt is not None:
            world_prompt["text_prompt"] = args.text_prompt

        gen = worlds_generate(
            api_key=api_key,
            display_name=args.display_name,
            model=args.model,
            public=bool(args.public),
            world_prompt=world_prompt,
        )
        operation_id = gen.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            raise WorldLabsError(f"Unexpected worlds_generate response: {json.dumps(gen)}")

        manifest["generate_response"] = gen
        manifest_path = out_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Started generation. operation_id={operation_id}")
        print(f"Wrote manifest: {manifest_path}")

        op = wait_for_operation(api_key=api_key, operation_id=operation_id, timeout_s=float(args.timeout_s))
        manifest["operation_result"] = asdict(op)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Done. world_id={op.world_id}")

        # Fetch full world (more complete fields).
        if op.world_id:
            world = worlds_get(api_key=api_key, world_id=op.world_id)
            manifest["world_get"] = world
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            world_url = None
            if isinstance(world.get("world"), dict):
                world_url = world["world"].get("world_marble_url")
            elif isinstance(world.get("world_marble_url"), str):
                world_url = world.get("world_marble_url")
            if isinstance(world_url, str) and world_url:
                print(f"Marble URL: {world_url}")

            if args.download_assets:
                # Assets can appear either under world["world"]["assets"] or op.response["assets"] snapshot.
                assets = None
                if isinstance(world.get("world"), dict) and isinstance(world["world"].get("assets"), dict):
                    assets = world["world"]["assets"]
                elif op.response and isinstance(op.response.get("assets"), dict):
                    assets = op.response.get("assets")

                if isinstance(assets, dict):
                    thumb = assets.get("thumbnail_url")
                    if isinstance(thumb, str) and thumb:
                        _download(thumb, out_dir / "assets" / "thumbnail.jpg")

                    imagery = assets.get("imagery")
                    if isinstance(imagery, dict):
                        pano = imagery.get("pano_url")
                        if isinstance(pano, str) and pano:
                            _download(pano, out_dir / "assets" / "pano.jpg")

                    mesh = assets.get("mesh")
                    if isinstance(mesh, dict):
                        glb = mesh.get("collider_mesh_url")
                        if isinstance(glb, str) and glb:
                            _download(glb, out_dir / "assets" / "collider_mesh.glb")

                    splats = assets.get("splats")
                    if isinstance(splats, dict):
                        spz_urls = splats.get("spz_urls")
                        if isinstance(spz_urls, dict):
                            for k, u in spz_urls.items():
                                if isinstance(k, str) and isinstance(u, str) and u:
                                    _download(u, out_dir / "assets" / f"splats_{k}.spz")

                print(f"Downloaded assets under: {out_dir / 'assets'}")

        return 0
    except WorldLabsError as e:
        print(f"WorldLabsError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


