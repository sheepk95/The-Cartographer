#!/usr/bin/env python3
"""Create a zero-dependency HTML repeat preview for texture seam QA."""

from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
from pathlib import Path
import struct


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an HTML canvas that repeats an image for seam inspection."
    )
    parser.add_argument("image", help="Local texture image path")
    parser.add_argument("--output", help="Output HTML path")
    parser.add_argument("--tiles", type=int, default=3, help="Tiles per axis (default: 3)")
    parser.add_argument(
        "--tile-size",
        type=int,
        default=None,
        help="Displayed tile size in CSS pixels (default: native PNG width)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file when it already exists",
    )
    return parser.parse_args()


def png_width(image_path: Path) -> int:
    with image_path.open("rb") as image_file:
        header = image_file.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise SystemExit("Default native-size preview requires a PNG input; pass --tile-size for another format")
    return struct.unpack(">I", header[16:20])[0]


def main() -> int:
    args = parse_args()
    image_path = Path(args.image).expanduser().resolve()
    if not image_path.is_file():
        raise SystemExit(f"Image does not exist: {image_path}")
    if args.tiles < 2 or args.tiles > 8:
        raise SystemExit("--tiles must be between 2 and 8")
    tile_size = args.tile_size if args.tile_size is not None else png_width(image_path)
    if tile_size < 64 or tile_size > 2048:
        raise SystemExit("--tile-size must be between 64 and 2048")

    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else image_path.with_name(f"{image_path.stem}_tile_preview.html")
    )
    if output_path.exists() and not args.force:
        raise SystemExit(f"Output already exists: {output_path}. Pass --force to overwrite it.")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    canvas_size = args.tiles * tile_size
    content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    image_data = base64.b64encode(image_path.read_bytes()).decode("ascii")
    image_uri = html.escape(f"data:{content_type};base64,{image_data}", quote=True)
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Texture repeat preview — {html.escape(image_path.name)}</title>
<style>
  html, body {{ margin: 0; background: #202124; color: #f1f3f4; font: 14px system-ui, sans-serif; }}
  main {{ width: max-content; margin: 20px auto; }}
  p {{ margin: 0 0 10px; }}
  .preview {{
    width: {canvas_size}px;
    height: {canvas_size}px;
    background-image: url("{image_uri}");
    background-repeat: repeat;
    background-size: {tile_size}px {tile_size}px;
  }}
</style>
</head>
<body>
<main>
  <p>{html.escape(image_path.name)} — {args.tiles}×{args.tiles} repeat preview</p>
  <div class="preview" role="img" aria-label="Repeated texture preview"></div>
</main>
</body>
</html>
"""
    output_path.write_text(document, encoding="utf-8")
    print(
        json.dumps(
            {
                "image": str(image_path),
                "preview": str(output_path),
                "tiles": args.tiles,
                "tile_size": tile_size,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
