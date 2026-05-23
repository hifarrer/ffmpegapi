import json


SITE_URL = "https://ffmpegapi.net"
API_BASE_URL = f"{SITE_URL}/api"


ENDPOINTS = [
    {
        "name": "Image and Audio Merge",
        "operation_id": "mergeImageAudio",
        "method": "POST",
        "path": "/api/merge_image_audio",
        "summary": "Create an MP4 video from image/audio pairs.",
        "description": "Combines one or more image/audio pairs. Each image is shown for the duration of its matching audio file, then the next image is displayed when the next audio begins. JSON requests should use image_urls and audio_urls arrays for multi-pair videos, or legacy image and audio strings for a single pair. Optional image transitions and a default slow zoom effect are supported.",
        "content_type": "application/json or multipart/form-data",
        "parameters": [
            {"name": "image_urls", "type": "array[string]", "required": False, "description": "Image URLs for multi-pair JSON requests. Use with audio_urls; both arrays must have the same item count."},
            {"name": "audio_urls", "type": "array[string]", "required": False, "description": "Audio URLs for multi-pair JSON requests. Each audio duration controls the paired image duration."},
            {"name": "image", "type": "string", "required": False, "description": "Backward-compatible single image URL for JSON requests, or image file in multipart form data. Use with audio for one image/audio pair."},
            {"name": "audio", "type": "string", "required": False, "description": "Backward-compatible single audio URL for JSON requests, or audio file in multipart form data. Use with image for one image/audio pair."},
            {"name": "transition_effect", "type": "string", "required": False, "description": "Optional image transition. Values include none, fade, wipeleft, wiperight, wipeup, wipedown, slideleft, slideright, slideup, slidedown, circlecrop, rectcrop, distance, fadeblack, fadewhite, radial, smoothleft, smoothright, smoothup, smoothdown."},
            {"name": "transition_duration", "type": "number", "required": False, "description": "Transition duration in seconds. Defaults to 0.5 when transition_effect is set. Maximum 5."},
            {"name": "dimensions", "type": "string", "required": False, "description": "Optional output dimensions such as 1280x720 or 1080x1920."},
            {"name": "zoom_effect", "type": "boolean", "required": False, "description": "Slowly zoom each image while its paired audio plays. Defaults to true."},
            {"name": "async", "type": "boolean", "required": False, "description": "Return a job_id immediately and process in the background."},
        ],
        "request_schema": {
            "type": "object",
            "oneOf": [
                {"required": ["image_urls", "audio_urls"]},
                {"required": ["image", "audio"]},
            ],
            "properties": {
                "image_urls": {
                    "type": "array",
                    "items": {"type": "string", "format": "uri"},
                    "minItems": 1,
                    "description": "Image URLs for multi-pair requests. Must align by index with audio_urls.",
                },
                "audio_urls": {
                    "type": "array",
                    "items": {"type": "string", "format": "uri"},
                    "minItems": 1,
                    "description": "Audio URLs for multi-pair requests. Must align by index with image_urls.",
                },
                "image": {
                    "type": "string",
                    "format": "uri",
                    "description": "Legacy single image URL.",
                },
                "audio": {
                    "type": "string",
                    "format": "uri",
                    "description": "Legacy single audio URL.",
                },
                "transition_effect": {
                    "type": "string",
                    "enum": ["none", "fade", "wipeleft", "wiperight", "wipeup", "wipedown", "slideleft", "slideright", "slideup", "slidedown", "circlecrop", "rectcrop", "distance", "fadeblack", "fadewhite", "radial", "smoothleft", "smoothright", "smoothup", "smoothdown"],
                    "description": "Optional transition between image changes.",
                },
                "transition_duration": {
                    "type": "number",
                    "minimum": 0.1,
                    "maximum": 5,
                    "description": "Transition duration in seconds. Defaults to 0.5 when transition_effect is set.",
                },
                "dimensions": {
                    "type": "string",
                    "pattern": "^\\d+x\\d+$",
                    "description": "Optional output dimensions such as 1280x720 or 1080x1920.",
                },
                "zoom_effect": {
                    "type": "boolean",
                    "default": True,
                    "description": "Slowly zoom each image while its paired audio plays.",
                },
                "async": {
                    "type": "boolean",
                    "description": "Return a job_id immediately and process in the background.",
                },
            },
        },
        "example": {
            "image_urls": ["https://example.com/intro.jpg", "https://example.com/chapter-1.jpg"],
            "audio_urls": ["https://example.com/intro.mp3", "https://example.com/chapter-1.mp3"],
            "transition_effect": "fade",
            "transition_duration": 0.75,
            "dimensions": "1280x720",
            "zoom_effect": True,
            "async": False,
        },
    },
    {
        "name": "Video Merge",
        "operation_id": "mergeVideos",
        "method": "POST",
        "path": "/api/merge_videos",
        "summary": "Concatenate videos into a single MP4.",
        "description": "Downloads one or more videos, normalizes them when needed, and concatenates them. Optional audio replacement, output dimensions, subtitle burn-in, and watermark overlay are supported.",
        "content_type": "application/json",
        "parameters": [
            {"name": "video_urls", "type": "array[string]", "required": True, "description": "Video URLs to merge. Use at least one URL."},
            {"name": "audio_url", "type": "string", "required": False, "description": "Optional replacement audio URL."},
            {"name": "dimensions", "type": "string", "required": False, "description": "Optional output dimensions such as 1920x1080."},
            {"name": "subtitle_url", "type": "string", "required": False, "description": "Optional ASS/SSA subtitle URL to burn into the merged video."},
            {"name": "watermark_url", "type": "string", "required": False, "description": "Optional watermark image URL."},
            {"name": "async", "type": "boolean", "required": False, "description": "Return a job_id immediately and process in the background."},
        ],
        "example": {"video_urls": ["https://example.com/intro.mp4", "https://example.com/main.mp4"], "dimensions": "1920x1080"},
    },
    {
        "name": "Video Loop",
        "operation_id": "videoLoop",
        "method": "POST",
        "path": "/api/video_loop",
        "summary": "Loop a video by count or until it matches an audio track.",
        "description": "Repeats one video a fixed number of times, or calculates the loop count needed to match a provided audio track. Optional watermark overlay is supported.",
        "content_type": "application/json or form data",
        "parameters": [
            {"name": "video_url", "type": "string", "required": True, "description": "Video URL to loop."},
            {"name": "number_of_loops", "type": "integer", "required": False, "description": "Positive number of times to repeat the video."},
            {"name": "audio_url", "type": "string", "required": False, "description": "Optional audio URL. Required if number_of_loops is omitted."},
            {"name": "watermark_url", "type": "string", "required": False, "description": "Optional watermark image URL."},
        ],
        "example": {"video_url": "https://example.com/clip.mp4", "number_of_loops": 3},
    },
    {
        "name": "Picture in Picture",
        "operation_id": "pictureInPicture",
        "method": "POST",
        "path": "/api/picture_in_picture",
        "summary": "Overlay one video on another.",
        "description": "Creates a picture-in-picture composition using a main video and an overlay video with configurable position, scale, and audio source.",
        "content_type": "application/json",
        "parameters": [
            {"name": "main_video_url", "type": "string", "required": True, "description": "Main/background video URL."},
            {"name": "pip_video_url", "type": "string", "required": True, "description": "Overlay/PiP video URL."},
            {"name": "position", "type": "string", "required": False, "description": "Overlay position. Common values: top-left, top-right, bottom-left, bottom-right, center.", "default": "bottom-right"},
            {"name": "scale", "type": "string", "required": False, "description": "FFmpeg scale expression for the overlay.", "default": "iw/4:ih/4"},
            {"name": "audio_option", "type": "string", "required": False, "description": "Audio source: video1, video2, or mute.", "default": "video1"},
            {"name": "async", "type": "boolean", "required": False, "description": "Return a job_id immediately and process in the background."},
        ],
        "example": {"main_video_url": "https://example.com/main.mp4", "pip_video_url": "https://example.com/overlay.mp4", "position": "top-right"},
    },
    {
        "name": "Add Watermark",
        "operation_id": "addWatermark",
        "method": "POST",
        "path": "/api/add_watermark",
        "summary": "Overlay a watermark image onto a video.",
        "description": "Adds a watermark image to a video with configurable placement and scale.",
        "content_type": "application/json",
        "parameters": [
            {"name": "video_url", "type": "string", "required": True, "description": "Video URL."},
            {"name": "watermark_url", "type": "string", "required": True, "description": "Watermark image URL."},
            {"name": "position", "type": "string", "required": False, "description": "One of top-left, top-center, top-right, middle-left, middle, middle-right, bottom-left, bottom-center, bottom-right.", "default": "bottom-right"},
            {"name": "scale", "type": "number", "required": False, "description": "Watermark width as a fraction of video width, from 0.05 to 1.0.", "default": 0.25},
            {"name": "async", "type": "boolean", "required": False, "description": "Return a job_id immediately and process in the background."},
        ],
        "example": {"video_url": "https://example.com/video.mp4", "watermark_url": "https://example.com/logo.png", "position": "bottom-right", "scale": 0.2},
    },
    {
        "name": "Add Subtitles",
        "operation_id": "addSubtitles",
        "method": "POST",
        "path": "/api/add_subtitles",
        "summary": "Burn ASS subtitles into a video.",
        "description": "Downloads a video and an ASS/SSA subtitle file, then burns the subtitles into the output video.",
        "content_type": "application/json",
        "parameters": [
            {"name": "video_url", "type": "string", "required": True, "description": "Video URL."},
            {"name": "subtitle_url", "type": "string", "required": True, "description": "ASS/SSA subtitle file URL."},
            {"name": "async", "type": "boolean", "required": False, "description": "Return a job_id immediately and process in the background."},
        ],
        "example": {"video_url": "https://example.com/video.mp4", "subtitle_url": "https://example.com/subtitles.ass"},
    },
    {
        "name": "Split Audio",
        "operation_id": "splitAudio",
        "method": "POST",
        "path": "/api/split_audio",
        "summary": "Split audio into equal parts.",
        "description": "Splits an audio file into a requested number of equal-duration parts.",
        "content_type": "application/json",
        "parameters": [
            {"name": "audio_url", "type": "string", "required": True, "description": "Audio URL."},
            {"name": "parts", "type": "integer", "required": False, "description": "Number of equal parts, from 2 to 20.", "default": 2},
            {"name": "async", "type": "boolean", "required": False, "description": "Return a job_id immediately and process in the background."},
        ],
        "example": {"audio_url": "https://example.com/podcast.mp3", "parts": 3},
    },
    {
        "name": "Split Audio by Segments",
        "operation_id": "splitAudioSegments",
        "method": "POST",
        "path": "/api/split_audio_segments",
        "summary": "Split audio into fixed-duration segments.",
        "description": "Creates audio segments of a specified length in seconds.",
        "content_type": "application/json",
        "parameters": [
            {"name": "audio_url", "type": "string", "required": True, "description": "Audio URL."},
            {"name": "segment_duration", "type": "number", "required": False, "description": "Segment duration in seconds, from 1 to 3600.", "default": 30},
            {"name": "async", "type": "boolean", "required": False, "description": "Return a job_id immediately and process in the background."},
        ],
        "example": {"audio_url": "https://example.com/podcast.mp3", "segment_duration": 10},
    },
    {
        "name": "Split Audio by Time",
        "operation_id": "splitAudioTime",
        "method": "POST",
        "path": "/api/split_audio_time",
        "summary": "Extract one audio range by millisecond timestamps.",
        "description": "Returns the audio between start_time and end_time, both in milliseconds.",
        "content_type": "application/json",
        "parameters": [
            {"name": "audio_url", "type": "string", "required": True, "description": "Audio URL."},
            {"name": "start_time", "type": "number", "required": True, "description": "Start time in milliseconds."},
            {"name": "end_time", "type": "number", "required": True, "description": "End time in milliseconds. Must be greater than start_time."},
            {"name": "async", "type": "boolean", "required": False, "description": "Return a job_id immediately and process in the background."},
        ],
        "example": {"audio_url": "https://example.com/audio.mp3", "start_time": 1000, "end_time": 11000},
    },
    {
        "name": "Trim Audio",
        "operation_id": "trimAudio",
        "method": "POST",
        "path": "/api/trim_audio",
        "summary": "Trim audio to a desired length.",
        "description": "Downloads an audio file and trims it to the requested duration, with optional fade-out.",
        "content_type": "application/json or form data",
        "parameters": [
            {"name": "audio_url", "type": "string", "required": True, "description": "Audio URL."},
            {"name": "desired_length", "type": "number", "required": True, "description": "Output length in seconds."},
            {"name": "fade_duration", "type": "number", "required": False, "description": "Optional fade-out duration in seconds.", "default": 0},
        ],
        "example": {"audio_url": "https://example.com/song.mp3", "desired_length": 30, "fade_duration": 2},
    },
    {
        "name": "Trim Video",
        "operation_id": "trimVideo",
        "method": "POST",
        "path": "/api/trim_video",
        "summary": "Trim video by start and end timestamps.",
        "description": "Downloads a video and returns the segment between start_time and end_time in seconds.",
        "content_type": "application/json or form data",
        "parameters": [
            {"name": "video_url", "type": "string", "required": True, "description": "Video URL."},
            {"name": "start_time", "type": "number", "required": True, "description": "Start time in seconds."},
            {"name": "end_time", "type": "number", "required": True, "description": "End time in seconds. Must be greater than start_time."},
        ],
        "example": {"video_url": "https://example.com/video.mp4", "start_time": 5, "end_time": 20},
    },
    {
        "name": "Split Video",
        "operation_id": "splitVideo",
        "method": "POST",
        "path": "/api/split_video",
        "summary": "Split a video into two parts.",
        "description": "Splits a video at split_at_seconds. If omitted, the split point defaults to half of the video duration.",
        "content_type": "application/json or form data",
        "parameters": [
            {"name": "video_url", "type": "string", "required": True, "description": "Video URL."},
            {"name": "split_at_seconds", "type": "number", "required": False, "description": "Split point in seconds."},
        ],
        "example": {"video_url": "https://example.com/video.mp4", "split_at_seconds": 12.5},
    },
    {
        "name": "Get First Frame Image",
        "operation_id": "getFirstFrameImage",
        "method": "POST",
        "path": "/api/get_first_frame_image",
        "summary": "Extract the first frame of a video as a JPEG.",
        "description": "Downloads a video and returns an image URL for the first frame.",
        "content_type": "application/json or form data",
        "parameters": [
            {"name": "video_url", "type": "string", "required": True, "description": "Video URL."},
        ],
        "example": {"video_url": "https://example.com/video.mp4"},
    },
    {
        "name": "Get Last Frame Image",
        "operation_id": "getLastFrameImage",
        "method": "POST",
        "path": "/api/get_last_frame_image",
        "summary": "Extract the last frame of a video as a JPEG.",
        "description": "Downloads a video and returns an image URL for the last frame.",
        "content_type": "application/json or form data",
        "parameters": [
            {"name": "video_url", "type": "string", "required": True, "description": "Video URL."},
        ],
        "example": {"video_url": "https://example.com/video.mp4"},
    },
    {
        "name": "Convert to Vertical",
        "operation_id": "convertToVertical",
        "method": "POST",
        "path": "/api/convert_to_vertical",
        "summary": "Convert a horizontal video to vertical format.",
        "description": "Creates a mobile-oriented vertical output and can apply an optional watermark.",
        "content_type": "application/json",
        "parameters": [
            {"name": "video_url", "type": "string", "required": True, "description": "Video URL."},
            {"name": "watermark_url", "type": "string", "required": False, "description": "Optional watermark image URL."},
            {"name": "async", "type": "boolean", "required": False, "description": "Return a job_id immediately and process in the background."},
        ],
        "example": {"video_url": "https://example.com/landscape.mp4", "watermark_url": "https://example.com/logo.png"},
    },
    {
        "name": "TikTok Portrait Converter",
        "operation_id": "convertToTiktokPortrait",
        "method": "POST",
        "path": "/api/convert_to_tiktok_portrait",
        "summary": "Convert a video to full-bleed 9:16 TikTok-style portrait.",
        "description": "Crops and scales source video into 1080x1920 portrait format, with optional watermark and outro video.",
        "content_type": "application/json",
        "parameters": [
            {"name": "video_url", "type": "string", "required": True, "description": "Video URL."},
            {"name": "watermark_url", "type": "string", "required": False, "description": "Optional watermark image URL."},
            {"name": "outro_video_url", "type": "string", "required": False, "description": "Optional outro video URL to append."},
            {"name": "async", "type": "boolean", "required": False, "description": "Return a job_id immediately and process in the background."},
        ],
        "example": {"video_url": "https://example.com/landscape.mp4", "outro_video_url": "https://example.com/outro.mp4"},
    },
    {
        "name": "Extract Audio as MP3",
        "operation_id": "extractAudioMp3",
        "method": "POST",
        "path": "/api/extract_audio_mp3",
        "summary": "Extract a video's audio track as MP3.",
        "description": "Downloads a video and returns an MP3 audio file.",
        "content_type": "application/json or form data",
        "parameters": [
            {"name": "video_url", "type": "string", "required": True, "description": "Video URL."},
            {"name": "bitrate", "type": "string", "required": False, "description": "MP3 bitrate: 96k, 128k, 192k, 256k, or 320k.", "default": "192k"},
        ],
        "example": {"video_url": "https://example.com/video.mp4", "bitrate": "192k"},
    },
    {
        "name": "Convert Video to GIF",
        "operation_id": "convertVideoToGif",
        "method": "POST",
        "path": "/api/convert_video_to_gif",
        "summary": "Encode a video as an animated GIF.",
        "description": "Downloads a video and creates a GIF. Optional chroma key transparency supports solid-color backgrounds such as green screen.",
        "content_type": "application/json or form data",
        "parameters": [
            {"name": "video_url", "type": "string", "required": True, "description": "Video URL."},
            {"name": "transparent_background", "type": "boolean", "required": False, "description": "Apply chroma key transparency.", "default": False},
            {"name": "chromakey_color", "type": "string", "required": False, "description": "Color to key out, such as 0x00FF00 or #00FF00.", "default": "0x00FF00"},
            {"name": "similarity", "type": "number", "required": False, "description": "Chroma key similarity from 0.01 to 1.0.", "default": 0.2},
            {"name": "blend", "type": "number", "required": False, "description": "Transparency edge softness from 0.0 to 1.0.", "default": 0.05},
            {"name": "fps", "type": "integer", "required": False, "description": "Output frame rate from 1 to 30.", "default": 10},
        ],
        "example": {"video_url": "https://example.com/clip.mp4", "transparent_background": True, "chromakey_color": "0x00FF00", "fps": 10},
    },
    {
        "name": "AI Captions",
        "operation_id": "addTiktokCaptions",
        "method": "POST",
        "path": "/api/videos/add-tiktok-captions",
        "summary": "Transcribe a video and render TikTok-style captions.",
        "description": "Extracts audio, transcribes it with word timestamps, and renders styled captions into a video. Also returns caption artifact URLs when available.",
        "content_type": "application/json",
        "parameters": [
            {"name": "video_url", "type": "string", "required": True, "description": "Video URL."},
            {"name": "subtitle_style", "type": "string", "required": False, "description": "plain-white, yellow-bg, pink-bg, blue-bg, or red-bg.", "default": "plain-white"},
            {"name": "language", "type": "string", "required": False, "description": "Language code or auto.", "default": "auto"},
            {"name": "aspect_ratio", "type": "string", "required": False, "description": "16:9, 9:16, 4:3, or 3:4.", "default": "9:16"},
            {"name": "max_chars_per_line", "type": "integer", "required": False, "description": "Caption wrapping limit from 5 to 80.", "default": 20},
            {"name": "max_lines", "type": "integer", "required": False, "description": "Maximum caption lines from 1 to 4.", "default": 1},
            {"name": "position", "type": "string", "required": False, "description": "top, center, or bottom.", "default": "bottom"},
        ],
        "example": {"video_url": "https://example.com/video.mp4", "subtitle_style": "yellow-bg", "position": "bottom"},
    },
    {
        "name": "Text Overlay Captions",
        "operation_id": "addTextOverlayCaptions",
        "method": "POST",
        "path": "/api/videos/add-text-overlay-captions",
        "summary": "Render supplied text lines as timed caption overlays.",
        "description": "Displays user-provided text lines over a video, one line every duration_per_line seconds.",
        "content_type": "application/json",
        "parameters": [
            {"name": "video_url", "type": "string", "required": True, "description": "Video URL."},
            {"name": "text", "type": "string", "required": True, "description": "One or more caption lines separated by newlines."},
            {"name": "subtitle_style", "type": "string", "required": False, "description": "plain-white, yellow-bg, pink-bg, blue-bg, or red-bg.", "default": "plain-white"},
            {"name": "aspect_ratio", "type": "string", "required": False, "description": "16:9, 9:16, 4:3, or 3:4.", "default": "9:16"},
            {"name": "position", "type": "string", "required": False, "description": "top, center, or bottom.", "default": "center"},
            {"name": "duration_per_line", "type": "integer", "required": False, "description": "Seconds per text line from 1 to 30.", "default": 5},
        ],
        "example": {"video_url": "https://example.com/video.mp4", "text": "First line\nSecond line", "duration_per_line": 4},
    },
    {
        "name": "YouTube to MP4",
        "operation_id": "youtubeToMp4",
        "method": "POST",
        "path": "/api/youtube_to_mp4",
        "summary": "Return an MP4 download URL for a YouTube video.",
        "description": "Accepts a standard YouTube watch URL, youtu.be URL, Shorts URL, embed URL, or /v/ URL and returns a downloadable MP4 URL.",
        "content_type": "application/json or form data",
        "parameters": [
            {"name": "youtube_url", "type": "string", "required": True, "description": "Single YouTube video URL. Playlists are not supported."},
        ],
        "example": {"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    },
    {
        "name": "Job Status",
        "operation_id": "getJobStatus",
        "method": "GET",
        "path": "/api/job/{job_id}/status",
        "summary": "Check asynchronous job status.",
        "description": "Returns pending, processing, completed, or failed status for a background job submitted with async=true.",
        "content_type": "query string or X-API-Key header",
        "parameters": [
            {"name": "job_id", "type": "string", "required": True, "description": "Job ID returned by an async request."},
        ],
        "example": None,
    },
]


def _param_lines(endpoint):
    lines = []
    for param in endpoint["parameters"]:
        required = "required" if param["required"] else "optional"
        default = f" Default: `{param['default']}`." if "default" in param else ""
        lines.append(f"- `{param['name']}` ({param['type']}, {required}): {param['description']}{default}")
    return "\n".join(lines)


def _curl_example(endpoint):
    if endpoint["method"] == "GET":
        return f'curl -X GET "{SITE_URL}{endpoint["path"].replace("{job_id}", "job_123")}?api_key=your_api_key_here"'
    body = endpoint.get("example") or {}
    return "\n".join([
        f'curl -X {endpoint["method"]} "{SITE_URL}{endpoint["path"]}" \\',
        '  -H "X-API-Key: your_api_key_here" \\',
        '  -H "Content-Type: application/json" \\',
        f"  -d '{json.dumps(body, indent=2)}'",
    ])


def generate_llms_txt():
    lines = [
        "# FFMPEG API",
        "",
        "> REST API for FFmpeg-powered video and audio processing: merge, trim, split, caption, convert, extract frames, extract audio, make GIFs, and create portrait video.",
        "",
        "Base URL: https://ffmpegapi.net",
        "API Base URL: https://ffmpegapi.net/api",
        "Authentication: include `X-API-Key: your_api_key_here`, `?api_key=...`, or an `api_key` form field.",
        "",
        "## Core Pages",
        "- [API documentation](https://ffmpegapi.net/docs)",
        "- [Markdown API documentation](https://ffmpegapi.net/docs.md)",
        "- [Examples](https://ffmpegapi.net/examples.md)",
        "- [Pricing](https://ffmpegapi.net/pricing.md)",
        "- [OpenAPI spec](https://ffmpegapi.net/openapi.json)",
        "- [Full LLM context](https://ffmpegapi.net/llms-full.txt)",
        "",
        "## API Endpoints",
    ]
    for endpoint in ENDPOINTS:
        lines.append(f"- `{endpoint['method']} {endpoint['path']}`: {endpoint['summary']}")
    return "\n".join(lines) + "\n"


def generate_docs_markdown(full=False):
    lines = [
        "# FFMPEG API Documentation",
        "",
        "FFMPEG API exposes REST endpoints for video and audio processing using FFmpeg and related rendering tooling.",
        "",
        f"Base URL: `{SITE_URL}`",
        f"API Base URL: `{API_BASE_URL}`",
        "",
        "## Authentication",
        "",
        "All documented API endpoints require an API key. Prefer the `X-API-Key` request header. Query string `api_key` and form field `api_key` are also accepted by the authentication layer.",
        "",
        "```bash",
        "X-API-Key: your_api_key_here",
        "```",
        "",
        "## Asynchronous Processing",
        "",
        "Many long-running endpoints accept `async: true`. The response includes `job_id`, `status`, and `status_url`. Poll `GET /api/job/{job_id}/status` until the status is `completed` or `failed`.",
        "",
        "## Endpoints",
    ]
    for endpoint in ENDPOINTS:
        lines.extend([
            "",
            f"### {endpoint['name']}",
            "",
            f"`{endpoint['method']} {endpoint['path']}`",
            "",
            endpoint["description"],
            "",
            f"Content type: `{endpoint['content_type']}`",
            "",
            "Parameters:",
            "",
            _param_lines(endpoint),
            "",
            "Example:",
            "",
            "```bash",
            _curl_example(endpoint),
            "```",
        ])
        if full:
            lines.extend([
                "",
                "Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.",
            ])
    lines.extend([
        "",
        "## Error Responses",
        "",
        "Errors use JSON with `success: false` and an `error` message. Common HTTP status codes are 400 for validation problems, 401 for missing or invalid API keys, 403 for job access denial, 404 for missing jobs, 500 for processing errors, and 504 for rendering timeouts.",
    ])
    return "\n".join(lines) + "\n"


def generate_examples_markdown():
    examples = [
        ("Merge videos", "POST", "/api/merge_videos", {"video_urls": ["https://example.com/intro.mp4", "https://example.com/main.mp4"], "dimensions": "1920x1080"}),
        ("Create a video from image and audio", "POST", "/api/merge_image_audio", {"image_urls": ["https://example.com/cover-1.jpg", "https://example.com/cover-2.jpg"], "audio_urls": ["https://example.com/audio-1.mp3", "https://example.com/audio-2.mp3"], "transition_effect": "fade", "zoom_effect": True}),
        ("Loop a video", "POST", "/api/video_loop", {"video_url": "https://example.com/clip.mp4", "number_of_loops": 3}),
        ("Add AI captions", "POST", "/api/videos/add-tiktok-captions", {"video_url": "https://example.com/video.mp4", "subtitle_style": "yellow-bg", "aspect_ratio": "9:16"}),
        ("Poll async job status", "GET", "/api/job/job_123/status", None),
    ]
    lines = [
        "# FFMPEG API Examples",
        "",
        "Replace `your_api_key_here` with an active key from your dashboard.",
    ]
    for title, method, path, body in examples:
        lines.extend(["", f"## {title}", "", "```bash"])
        if method == "GET":
            lines.append(f'curl -X GET "{SITE_URL}{path}?api_key=your_api_key_here"')
        else:
            lines.extend([
                f'curl -X {method} "{SITE_URL}{path}" \\',
                '  -H "X-API-Key: your_api_key_here" \\',
                '  -H "Content-Type: application/json" \\',
                f"  -d '{json.dumps(body, indent=2)}'",
            ])
        lines.append("```")
    lines.extend([
        "",
        "## Async Workflow",
        "",
        "```python",
        "import time",
        "import requests",
        "",
        'api_key = "your_api_key_here"',
        'response = requests.post(',
        '    "https://ffmpegapi.net/api/merge_videos",',
        '    headers={"X-API-Key": api_key},',
        '    json={"video_urls": ["https://example.com/a.mp4", "https://example.com/b.mp4"], "async": True},',
        ")",
        'job_id = response.json()["job_id"]',
        "",
        "while True:",
        '    status = requests.get(f"https://ffmpegapi.net/api/job/{job_id}/status", headers={"X-API-Key": api_key}).json()',
        '    if status["status"] in ("completed", "failed"):',
        "        print(status)",
        "        break",
        "    time.sleep(5)",
        "```",
    ])
    return "\n".join(lines) + "\n"


def generate_pricing_markdown(plans=None):
    lines = [
        "# FFMPEG API Pricing",
        "",
        "Pricing is available at https://ffmpegapi.net/pricing. Plans can change; use the live pricing page as the billing source of truth.",
        "",
    ]
    if plans:
        lines.append("## Active Plans")
        lines.append("")
        for plan in plans:
            monthly = getattr(plan, "monthly_price", None)
            yearly = getattr(plan, "yearly_price", None)
            calls = getattr(plan, "api_calls_per_month", None)
            features = getattr(plan, "features", "") or ""
            lines.extend([
                f"### {getattr(plan, 'name', 'Plan')}",
                "",
                f"- Monthly price: ${monthly:g}" if monthly is not None else "- Monthly price: see pricing page",
                f"- Yearly price: ${yearly:g}" if yearly is not None else "- Yearly price: see pricing page",
                f"- API calls per month: {calls}" if calls is not None else "- API calls per month: see pricing page",
            ])
            if features:
                lines.append(f"- Features: {features}")
            lines.append("")
    else:
        lines.extend([
            "## Published Plan Summary",
            "",
            "- Free plan: available for testing and small projects.",
            "- Pro plan: published page metadata describes $29/month with 100K API calls.",
            "- Enterprise plan: published page metadata describes $99/month with unlimited calls.",
            "",
        ])
    return "\n".join(lines)


def generate_llms_full_txt(plans=None):
    return "\n".join([
        generate_llms_txt().rstrip(),
        "",
        generate_docs_markdown(full=True).rstrip(),
        "",
        generate_examples_markdown().rstrip(),
        "",
        generate_pricing_markdown(plans).rstrip(),
        "",
    ])


def _schema_for_param(param):
    param_type = param["type"]
    if param_type == "array[string]":
        return {"type": "array", "items": {"type": "string", "format": "uri"}}
    if param_type == "integer":
        return {"type": "integer"}
    if param_type == "number":
        return {"type": "number"}
    if param_type == "boolean":
        return {"type": "boolean"}
    return {"type": "string"}


def generate_openapi_spec():
    paths = {}
    for endpoint in ENDPOINTS:
        method = endpoint["method"].lower()
        required = [p["name"] for p in endpoint["parameters"] if p["required"] and p["name"] != "job_id"]
        properties = {
            p["name"]: {**_schema_for_param(p), "description": p["description"]}
            for p in endpoint["parameters"]
            if p["name"] != "job_id"
        }
        operation = {
            "operationId": endpoint["operation_id"],
            "summary": endpoint["summary"],
            "description": endpoint["description"],
            "security": [{"ApiKeyAuth": []}],
            "responses": {
                "200": {
                    "description": "Successful response",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ApiResponse"}
                        }
                    },
                },
                "400": {"description": "Validation error"},
                "401": {"description": "Missing or invalid API key"},
                "500": {"description": "Processing error"},
            },
        }
        if endpoint["method"] == "GET":
            operation["parameters"] = [
                {"name": "job_id", "in": "path", "required": True, "schema": {"type": "string"}, "description": "Async job ID."},
            ]
        else:
            schema = endpoint.get("request_schema")
            if not schema:
                schema = {
                    "type": "object",
                    "required": required,
                    "properties": properties,
                }
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": schema,
                        "example": endpoint.get("example") or {},
                    }
                },
            }
        paths.setdefault(endpoint["path"], {})[method] = operation

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "FFMPEG API",
            "version": "1.0.0",
            "description": "FFmpeg-powered video and audio processing API.",
            "contact": {"url": f"{SITE_URL}/contact"},
        },
        "servers": [{"url": SITE_URL}],
        "paths": paths,
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                }
            },
            "schemas": {
                "ApiResponse": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                        "message": {"type": "string"},
                        "download_url": {"type": "string"},
                        "filename": {"type": "string"},
                        "job_id": {"type": "string"},
                        "status": {"type": "string"},
                        "error": {"type": "string"},
                    },
                    "additionalProperties": True,
                }
            },
        },
    }


def homepage_json_ld():
    graph = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": f"{SITE_URL}/#website",
                "name": "FFMPEG API",
                "url": SITE_URL,
                "description": "FFmpeg-powered video and audio processing API for developers.",
            },
            {
                "@type": "WebAPI",
                "@id": f"{SITE_URL}/#api",
                "name": "FFMPEG API",
                "url": f"{SITE_URL}/docs",
                "documentation": f"{SITE_URL}/docs",
                "termsOfService": f"{SITE_URL}/pricing",
                "description": "REST API for merging, trimming, splitting, captioning, converting, and extracting video and audio assets.",
                "provider": {"@type": "Organization", "name": "FFMPEG API", "url": SITE_URL},
            },
        ],
    }
    return json.dumps(graph, indent=2)


def docs_json_ld():
    graph = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "TechArticle",
                "@id": f"{SITE_URL}/docs#techarticle",
                "headline": "FFMPEG API Documentation",
                "url": f"{SITE_URL}/docs",
                "description": "API reference and examples for the FFMPEG API video and audio processing endpoints.",
                "about": {"@id": f"{SITE_URL}/#api"},
                "mainEntity": [
                    {
                        "@type": "WebAPI",
                        "name": endpoint["name"],
                        "url": f"{SITE_URL}{endpoint['path']}",
                        "description": endpoint["summary"],
                    }
                    for endpoint in ENDPOINTS
                ],
            },
            {
                "@type": "Dataset",
                "@id": f"{SITE_URL}/openapi.json#dataset",
                "name": "FFMPEG API OpenAPI Specification",
                "url": f"{SITE_URL}/openapi.json",
                "encodingFormat": "application/json",
            },
        ],
    }
    return json.dumps(graph, indent=2)
