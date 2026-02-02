# PreviewTheStash

Generate animated tag preview images by cropping scene video clips with a visual overlay tool.

## Features

- Interactive crop overlay with drag-and-drop positioning and corner resize handles
- Independent horizontal and vertical anchor control with optional zoom
- Loop preview with time adjustment buttons (±1s, ±0.1s)
- Automatic bitrate scaling based on crop size
- Optional permanent storage with version-tracked metadata
- Mobile-friendly with touch support

## Requirements

- **FFmpeg** and **ffprobe** installed and in PATH (https://ffmpeg.org/download.html)
- **tag-video plugin** from https://feederbox826.github.io/plugins/main/index.yml

## Usage

1. Navigate to a scene and click the **TAG** button in the toolbar
2. Position playhead and adjust the green crop overlay (drag to move, corner handles to resize)
3. Click **Confirm Crop** to enter tag selection mode
4. Click any tag to set it as that tag's preview image

Press **Escape** to cancel at any time.

## Configuration

**Settings → Plugins → PreviewTheStash**

- **Default Duration**: Clip length in seconds (default: 5.4)
- **Default Max Bitrate**: Encoding bitrate, e.g., `2140k` or `2M` (default: 2140k)
- **Default Max Width**: Max upload width in pixels (default: 720)
- **Tag Output Directory**: Optional directory to save permanent WebM/JSON files (leave empty for temp files only)

## How It Works

The crop overlay uses anchor-based positioning:
- **anchor_x/anchor_y**: Position from 0.0 (edge) to 1.0 (opposite edge), 0.5 = center
- **zoom**: Crop size multiplier (1.0 = full size, 2.0 = crop to 50%, etc.)

Outputs are square VP9 WebM clips, automatically downscaled if larger than max width. Bitrate scales proportionally to crop area.

## License

AGPL-3.0
