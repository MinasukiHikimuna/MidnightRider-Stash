"""PreviewTheStash — generate and upload animated tag preview images."""

import base64
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from stashapi import log
from stashapi.stashapp import StashInterface


DEFAULT_DURATION = 5.4
DEFAULT_BITRATE = "2140k"
DEFAULT_UPLOAD_MAX_WIDTH = 720


def get_config(stash):
    """Read plugin settings with defaults."""
    config = stash.get_configuration()
    plugin_config = config.get("plugins", {}).get("PreviewTheStash", {})
    return {
        "tag_output_dir": plugin_config.get("tagOutputDir", ""),
        "duration": float(plugin_config.get("defaultDuration", "") or DEFAULT_DURATION),
        "bitrate": plugin_config.get("defaultBitrate", "") or DEFAULT_BITRATE,
        "upload_max_width": int(
            plugin_config.get("uploadMaxWidth", "") or DEFAULT_UPLOAD_MAX_WIDTH
        ),
    }


def format_time(seconds):
    """Format seconds to HH:MM:SS.mmm or M:SS.mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    s_int = int(s)
    ms = round((s - s_int) * 1000)
    s_part = f"{s_int:02d}.{ms:03d}"
    if h > 0:
        return f"{h}:{m:02d}:{s_part}"
    return f"{m}:{s_part}"


def probe_video_dimension(input_path, dimension="height"):
    """Get a video dimension using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", f"stream={dimension}",
            "-of", "json",
            str(input_path),
        ],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    data = json.loads(result.stdout)
    return int(data["streams"][0][dimension])


def encode_square_webm(input_path, output_path, start, duration, bitrate,
                       anchor_x, anchor_y, zoom):
    """Encode a square cropped VP9 WebM clip."""
    vf = (
        f"crop="
        f"'min(iw,ih)/{zoom}:min(iw,ih)/{zoom}"
        f":(iw-min(iw,ih)/{zoom})*{anchor_x}"
        f":(ih-min(iw,ih)/{zoom})*{anchor_y}'"
    )
    cmd = [
        "ffmpeg", "-ss", start,
        "-i", str(input_path),
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libvpx-vp9",
        "-b:v", bitrate,
        "-an", "-y",
        str(output_path),
    ]
    log.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=False)
    if result.returncode != 0:
        log.error(f"ffmpeg failed: {result.stderr}")
        sys.exit(1)
    log.info(f"Encoded WebM: {output_path}")


def write_metadata(tag_output_dir, tag_name, input_path, start, duration,
                   bitrate, anchor_x, anchor_y, zoom):
    """Write metadata JSON with version history."""
    metadata_path = Path(tag_output_dir) / f"{tag_name}.json"
    new_version = {
        "tag_name": tag_name,
        "source_video": str(input_path),
        "start": start,
        "duration": duration,
        "bitrate": bitrate,
        "anchor_x": anchor_x,
        "anchor_y": anchor_y,
        "zoom": zoom,
        "created_at": datetime.now(UTC).isoformat(),
    }
    versions = []
    if metadata_path.exists():
        existing = json.loads(metadata_path.read_text())
        versions = existing.get("versions", [])
    versions.insert(0, new_version)
    metadata_path.write_text(json.dumps({"versions": versions}, indent=2))
    log.info(f"Metadata saved to {metadata_path}")


def upload_tag_image(stash, tag_name, tag_id, webm_path, max_width):
    """Upload WebM as tag image, downscaling if needed."""
    width = probe_video_dimension(webm_path, "width")
    upload_path = webm_path
    cleanup = False

    if width > max_width:
        log.info(f"Source is {width}x{width}, creating {max_width}p version for upload")
        temp_path = Path(webm_path).parent / f"{tag_name}_upload.webm"
        half_bitrate = f"{int(DEFAULT_BITRATE.rstrip('k')) // 2}k"
        cmd = [
            "ffmpeg", "-i", str(webm_path),
            "-vf", f"scale={max_width}:{max_width}",
            "-c:v", "libvpx-vp9",
            "-b:v", half_bitrate,
            "-an", "-y",
            str(temp_path),
        ]
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
        upload_path = temp_path
        cleanup = True
    else:
        log.info(f"Source is {width}x{width}, uploading as-is")

    data = Path(upload_path).read_bytes()
    b64 = base64.b64encode(data).decode()
    data_url = f"data:video/webm;base64,{b64}"

    stash.call_GQL(
        """mutation TagUpdate($input: TagUpdateInput!) {
            tagUpdate(input: $input) { id }
        }""",
        {"input": {"id": tag_id, "image": data_url}},
    )
    log.info(f"Updated tag '{tag_name}' (id={tag_id}) with preview image")

    if cleanup:
        Path(upload_path).unlink()


def resolve_scene_path(stash, scene_id):
    """Get the file path for a scene from Stash."""
    scene = stash.find_scene(scene_id, fragment="id files { path }")
    if not scene:
        log.error(f"Scene {scene_id} not found")
        sys.exit(1)
    files = scene.get("files", [])
    if not files:
        log.error(f"Scene {scene_id} has no files")
        sys.exit(1)
    return files[0]["path"]


def set_tag_preview(stash, args, config):
    """Main task: extract clip and set as tag preview."""
    scene_id = args.get("scene_id")
    start_seconds = float(args.get("start_seconds", 0))
    tag_name = args.get("tag_name", "")
    anchor_x = float(args.get("anchor_x", 0.5))
    anchor_y = float(args.get("anchor_y", 0.5))
    zoom = float(args.get("zoom", 1.0))

    if not scene_id or not tag_name:
        log.error("scene_id and tag_name are required")
        sys.exit(1)

    tag_output_dir = config["tag_output_dir"]
    if not tag_output_dir:
        log.error("Tag Output Directory is not configured in plugin settings")
        sys.exit(1)

    # Resolve scene file path
    input_path = resolve_scene_path(stash, scene_id)
    log.info(f"Scene {scene_id} -> {input_path}")

    if not Path(input_path).exists():
        log.error(f"File not found: {input_path}")
        sys.exit(1)

    # Find tag in Stash
    tags = stash.find_tags(f={"name": {"value": tag_name, "modifier": "EQUALS"}})
    if not tags:
        log.error(f"Tag '{tag_name}' not found")
        sys.exit(1)
    tag_id = tags[0]["id"]
    tag_name = tags[0]["name"]  # Use canonical name from Stash

    # Prepare output
    output_dir = Path(tag_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{tag_name}.webm"

    start = format_time(start_seconds)
    duration = config["duration"]
    bitrate = config["bitrate"]

    # Scale bitrate proportionally to crop area.
    # Default bitrate is calibrated for 1080x1080 crops.
    # Crop size in pixels = min(w, h) / zoom.
    source_height = probe_video_dimension(input_path, "height")
    crop_size = source_height / zoom
    reference_size = 1080
    if abs(crop_size - reference_size) > 1:
        pixel_ratio = (crop_size * crop_size) / (reference_size * reference_size)
        bitrate_value = int(bitrate.rstrip("k")) * pixel_ratio
        bitrate = f"{int(bitrate_value)}k"
        log.info(f"Scaled bitrate to {bitrate} for {int(crop_size)}x{int(crop_size)} crop")

    log.info(f"Generating preview for tag '{tag_name}' from scene {scene_id} at {start}")

    encode_square_webm(
        input_path, output_path, start, duration, bitrate,
        anchor_x, anchor_y, zoom,
    )

    write_metadata(
        tag_output_dir, tag_name, input_path, start, duration,
        bitrate, anchor_x, anchor_y, zoom,
    )

    upload_tag_image(stash, tag_name, tag_id, output_path, config["upload_max_width"])
    log.info(f"Done! Tag '{tag_name}' preview updated.")


if __name__ == "__main__":
    json_input = json.loads(sys.stdin.read())
    stash = StashInterface(json_input["server_connection"])
    config = get_config(stash)
    args = json_input.get("args", {})
    mode = args.get("mode")

    if mode == "set_tag_preview":
        set_tag_preview(stash, args, config)
    else:
        log.error(f"Unknown mode: {mode}")
