# FFMPEG API Documentation

FFMPEG API exposes REST endpoints for video and audio processing using FFmpeg and related rendering tooling.

Base URL: `https://ffmpegapi.net`
API Base URL: `https://ffmpegapi.net/api`

## Authentication

All documented API endpoints require an API key. Prefer the `X-API-Key` request header. Query string `api_key` and form field `api_key` are also accepted by the authentication layer.

```bash
X-API-Key: your_api_key_here
```

## Asynchronous Processing

Every locally processed FFmpeg and Remotion endpoint may either complete immediately with its existing endpoint-specific response or return HTTP `202 Accepted` when all configured processing slots are occupied. Setting `async: true` always requests the queued response path and returns `202`.

A queued response includes `success`, `job_id`, `status`, `status_url`, `queue_position`, and `message`. `queue_position` may be null if processing has already started. Poll the returned `status_url` until the job is `completed` or `failed`. The externally processed `POST /api/youtube_to_mp4` endpoint is outside this queue.

Authentication errors are returned before queueing. For most local endpoints, validation occurs when processing starts; consequently, a request accepted under load can later report `failed` rather than returning an immediate validation error.

## Endpoints

### Image and Audio Merge

`POST /api/merge_image_audio`

Combines one or more image/audio pairs. Each image is shown for the duration of its matching audio file, then the next image is displayed when the next audio begins. JSON requests should use image_urls and audio_urls arrays for multi-pair videos, or legacy image and audio strings for a single pair. Optional image transitions and a default slow zoom effect are supported.

Content type: `application/json or multipart/form-data`

Parameters:

- `image_urls` (array[string], optional): Image URLs for multi-pair JSON requests. Use with audio_urls; both arrays must have the same item count.
- `audio_urls` (array[string], optional): Audio URLs for multi-pair JSON requests. Each audio duration controls the paired image duration.
- `image` (string, optional): Backward-compatible single image URL for JSON requests, or image file in multipart form data. Use with audio for one image/audio pair.
- `audio` (string, optional): Backward-compatible single audio URL for JSON requests, or audio file in multipart form data. Use with image for one image/audio pair.
- `transition_effect` (string, optional): Optional image transition. Values include none, fade, wipeleft, wiperight, wipeup, wipedown, slideleft, slideright, slideup, slidedown, circlecrop, rectcrop, distance, fadeblack, fadewhite, radial, smoothleft, smoothright, smoothup, smoothdown.
- `transition_duration` (number, optional): Transition duration in seconds. Defaults to 0.5 when transition_effect is set. Maximum 5.
- `dimensions` (string, optional): Optional output dimensions such as 1280x720 or 1080x1920.
- `zoom_effect` (boolean, optional): Slowly zoom each image while its paired audio plays. Defaults to true.
- `async` (boolean, optional): Return a job_id immediately and process in the background.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/merge_image_audio" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "image_urls": [
    "https://example.com/intro.jpg",
    "https://example.com/chapter-1.jpg"
  ],
  "audio_urls": [
    "https://example.com/intro.mp3",
    "https://example.com/chapter-1.mp3"
  ],
  "transition_effect": "fade",
  "transition_duration": 0.75,
  "dimensions": "1280x720",
  "zoom_effect": true,
  "async": false
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Video Merge

`POST /api/merge_videos`

Downloads one or more videos, normalizes them when needed, and concatenates them. Optional audio replacement, output dimensions, subtitle burn-in, and watermark overlay are supported.

Content type: `application/json`

Parameters:

- `video_urls` (array[string], required): Video URLs to merge. Use at least one URL.
- `audio_url` (string, optional): Optional replacement audio URL.
- `dimensions` (string, optional): Optional output dimensions such as 1920x1080.
- `subtitle_url` (string, optional): Optional ASS/SSA subtitle URL to burn into the merged video.
- `watermark_url` (string, optional): Optional watermark image URL.
- `async` (boolean, optional): Return a job_id immediately and process in the background.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/merge_videos" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "video_urls": [
    "https://example.com/intro.mp4",
    "https://example.com/main.mp4"
  ],
  "dimensions": "1920x1080"
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Neonvideo Merge Videos

`POST /api/neonvideo_merge_videos`

Downloads one or more videos, normalizes and concatenates them, and can append an outro video that keeps its own audio. Optional audio replacement, output dimensions, subtitle burn-in, and watermark overlay are supported.

Content type: `application/json`

Parameters:

- `video_urls` (array[string], required): Video URLs to merge. Use at least one URL.
- `audio_url` (string, optional): Optional replacement audio URL for the main merged video. Not used during outro playback.
- `outro_url` (string, optional): Optional outro video URL to append. The outro keeps its own audio.
- `dimensions` (string, optional): Optional output dimensions such as 1920x1080.
- `subtitle_url` (string, optional): Optional ASS/SSA subtitle URL to burn into the merged video.
- `watermark_url` (string, optional): Optional watermark image URL.
- `async` (boolean, optional): Return a job_id immediately and process in the background.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/neonvideo_merge_videos" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "video_urls": [
    "https://example.com/intro.mp4",
    "https://example.com/main.mp4"
  ],
  "outro_url": "https://example.com/outro.mp4",
  "dimensions": "1920x1080"
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Video Loop

`POST /api/video_loop`

Repeats one video a fixed number of times, or calculates the loop count needed to match a provided audio track. Optional watermark overlay is supported.

Content type: `application/json or form data`

Parameters:

- `video_url` (string, required): Video URL to loop.
- `number_of_loops` (integer, optional): Positive number of times to repeat the video.
- `audio_url` (string, optional): Optional audio URL. Required if number_of_loops is omitted.
- `watermark_url` (string, optional): Optional watermark image URL.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/video_loop" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "video_url": "https://example.com/clip.mp4",
  "number_of_loops": 3
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Endless Loop

`POST /api/endless_loop`

Repeats one video until a requested duration in seconds is reached. If the duration is not an exact multiple of the source video length, the final loop is trimmed to the exact target duration. Optional watermark overlay is supported.

Content type: `application/json or form data`

Parameters:

- `video_url` (string, required): Video URL to loop.
- `duration` (number, required): Target output duration in seconds. Must be positive; fractional seconds are supported.
- `watermark_url` (string, optional): Optional watermark image URL.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/endless_loop" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "video_url": "https://example.com/clip.mp4",
  "duration": 1205
}'
```

Typical successful response fields include `success`, `message`, `download_url`, `filename`, `loops_required`, `video_duration_seconds`, `target_duration_seconds`, `estimated_full_loops`, and `partial_final_loop_seconds`.

### Picture in Picture

`POST /api/picture_in_picture`

Creates a picture-in-picture composition using a main video and an overlay video with configurable position, scale, and audio source.

Content type: `application/json`

Parameters:

- `main_video_url` (string, required): Main/background video URL.
- `pip_video_url` (string, required): Overlay/PiP video URL.
- `position` (string, optional): Overlay position. Common values: top-left, top-right, bottom-left, bottom-right, center. Default: `bottom-right`.
- `scale` (string, optional): FFmpeg scale expression for the overlay. Default: `iw/4:ih/4`.
- `audio_option` (string, optional): Audio source: video1, video2, or mute. Default: `video1`.
- `async` (boolean, optional): Return a job_id immediately and process in the background.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/picture_in_picture" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "main_video_url": "https://example.com/main.mp4",
  "pip_video_url": "https://example.com/overlay.mp4",
  "position": "top-right"
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Add Watermark

`POST /api/add_watermark`

Adds a watermark image to a video with configurable placement and scale.

Content type: `application/json`

Parameters:

- `video_url` (string, required): Video URL.
- `watermark_url` (string, required): Watermark image URL.
- `position` (string, optional): One of top-left, top-center, top-right, middle-left, middle, middle-right, bottom-left, bottom-center, bottom-right. Default: `bottom-right`.
- `scale` (number, optional): Watermark width as a fraction of video width, from 0.05 to 1.0. Default: `0.25`.
- `async` (boolean, optional): Return a job_id immediately and process in the background.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/add_watermark" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "video_url": "https://example.com/video.mp4",
  "watermark_url": "https://example.com/logo.png",
  "position": "bottom-right",
  "scale": 0.2
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Add Subtitles

`POST /api/add_subtitles`

Downloads a video and an ASS/SSA subtitle file, then burns the subtitles into the output video.

Content type: `application/json`

Parameters:

- `video_url` (string, required): Video URL.
- `subtitle_url` (string, required): ASS/SSA subtitle file URL.
- `async` (boolean, optional): Return a job_id immediately and process in the background.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/add_subtitles" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "video_url": "https://example.com/video.mp4",
  "subtitle_url": "https://example.com/subtitles.ass"
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Split Audio

`POST /api/split_audio`

Splits an audio file into a requested number of equal-duration parts.

Content type: `application/json`

Parameters:

- `audio_url` (string, required): Audio URL.
- `parts` (integer, optional): Number of equal parts, from 2 to 20. Default: `2`.
- `async` (boolean, optional): Return a job_id immediately and process in the background.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/split_audio" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "audio_url": "https://example.com/podcast.mp3",
  "parts": 3
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Split Audio by Segments

`POST /api/split_audio_segments`

Creates audio segments of a specified length in seconds.

Content type: `application/json`

Parameters:

- `audio_url` (string, required): Audio URL.
- `segment_duration` (number, optional): Segment duration in seconds, from 1 to 3600. Default: `30`.
- `async` (boolean, optional): Return a job_id immediately and process in the background.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/split_audio_segments" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "audio_url": "https://example.com/podcast.mp3",
  "segment_duration": 10
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Split Audio by Time

`POST /api/split_audio_time`

Returns the audio between start_time and end_time, both in milliseconds.

Content type: `application/json`

Parameters:

- `audio_url` (string, required): Audio URL.
- `start_time` (number, required): Start time in milliseconds.
- `end_time` (number, required): End time in milliseconds. Must be greater than start_time.
- `async` (boolean, optional): Return a job_id immediately and process in the background.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/split_audio_time" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "audio_url": "https://example.com/audio.mp3",
  "start_time": 1000,
  "end_time": 11000
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Trim Audio

`POST /api/trim_audio`

Downloads an audio file and trims it to the requested duration, with optional fade-out.

Content type: `application/json or form data`

Parameters:

- `audio_url` (string, required): Audio URL.
- `desired_length` (number, required): Output length in seconds.
- `fade_duration` (number, optional): Optional fade-out duration in seconds. Default: `0`.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/trim_audio" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "audio_url": "https://example.com/song.mp3",
  "desired_length": 30,
  "fade_duration": 2
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Trim Video

`POST /api/trim_video`

Downloads a video and returns the segment between start_time and end_time in seconds.

Content type: `application/json or form data`

Parameters:

- `video_url` (string, required): Video URL.
- `start_time` (number, required): Start time in seconds.
- `end_time` (number, required): End time in seconds. Must be greater than start_time.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/trim_video" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "video_url": "https://example.com/video.mp4",
  "start_time": 5,
  "end_time": 20
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Split Video

`POST /api/split_video`

Splits a video at split_at_seconds. If omitted, the split point defaults to half of the video duration.

Content type: `application/json or form data`

Parameters:

- `video_url` (string, required): Video URL.
- `split_at_seconds` (number, optional): Split point in seconds.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/split_video" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "video_url": "https://example.com/video.mp4",
  "split_at_seconds": 12.5
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Get First Frame Image

`POST /api/get_first_frame_image`

Downloads a video and returns an image URL for the first frame.

Content type: `application/json or form data`

Parameters:

- `video_url` (string, required): Video URL.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/get_first_frame_image" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "video_url": "https://example.com/video.mp4"
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Get Last Frame Image

`POST /api/get_last_frame_image`

Downloads a video and returns an image URL for the last frame.

Content type: `application/json or form data`

Parameters:

- `video_url` (string, required): Video URL.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/get_last_frame_image" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "video_url": "https://example.com/video.mp4"
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Convert to Vertical

`POST /api/convert_to_vertical`

Creates a mobile-oriented vertical output and can apply an optional watermark.

Content type: `application/json`

Parameters:

- `video_url` (string, required): Video URL.
- `watermark_url` (string, optional): Optional watermark image URL.
- `async` (boolean, optional): Return a job_id immediately and process in the background.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/convert_to_vertical" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "video_url": "https://example.com/landscape.mp4",
  "watermark_url": "https://example.com/logo.png"
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### TikTok Portrait Converter

`POST /api/convert_to_tiktok_portrait`

Crops and scales source video into 1080x1920 portrait format, with optional watermark and outro video.

Content type: `application/json`

Parameters:

- `video_url` (string, required): Video URL.
- `watermark_url` (string, optional): Optional watermark image URL.
- `outro_video_url` (string, optional): Optional outro video URL to append.
- `async` (boolean, optional): Return a job_id immediately and process in the background.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/convert_to_tiktok_portrait" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "video_url": "https://example.com/landscape.mp4",
  "outro_video_url": "https://example.com/outro.mp4"
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Extract Audio as MP3

`POST /api/extract_audio_mp3`

Downloads a video and returns an MP3 audio file.

Content type: `application/json or form data`

Parameters:

- `video_url` (string, required): Video URL.
- `bitrate` (string, optional): MP3 bitrate: 96k, 128k, 192k, 256k, or 320k. Default: `192k`.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/extract_audio_mp3" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "video_url": "https://example.com/video.mp4",
  "bitrate": "192k"
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Convert Video to GIF

`POST /api/convert_video_to_gif`

Downloads a video and creates a GIF. Optional chroma key transparency supports solid-color backgrounds such as green screen.

Content type: `application/json or form data`

Parameters:

- `video_url` (string, required): Video URL.
- `transparent_background` (boolean, optional): Apply chroma key transparency. Default: `False`.
- `chromakey_color` (string, optional): Color to key out, such as 0x00FF00 or #00FF00. Default: `0x00FF00`.
- `similarity` (number, optional): Chroma key similarity from 0.01 to 1.0. Default: `0.2`.
- `blend` (number, optional): Transparency edge softness from 0.0 to 1.0. Default: `0.05`.
- `fps` (integer, optional): Output frame rate from 1 to 30. Default: `10`.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/convert_video_to_gif" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "video_url": "https://example.com/clip.mp4",
  "transparent_background": true,
  "chromakey_color": "0x00FF00",
  "fps": 10
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### AI Captions

`POST /api/videos/add-tiktok-captions`

Extracts audio, transcribes it with word timestamps, and renders styled captions into a video. Also returns caption artifact URLs when available.

Content type: `application/json`

Parameters:

- `video_url` (string, required): Video URL.
- `subtitle_style` (string, optional): plain-white, yellow-bg, pink-bg, blue-bg, or red-bg. Default: `plain-white`.
- `language` (string, optional): Language code or auto. Default: `auto`.
- `aspect_ratio` (string, optional): 16:9, 9:16, 4:3, or 3:4. Default: `9:16`.
- `max_chars_per_line` (integer, optional): Caption wrapping limit from 5 to 80. Default: `20`.
- `max_lines` (integer, optional): Maximum caption lines from 1 to 4. Default: `1`.
- `position` (string, optional): top, center, or bottom. Default: `bottom`.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/videos/add-tiktok-captions" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "video_url": "https://example.com/video.mp4",
  "subtitle_style": "yellow-bg",
  "position": "bottom"
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Text Overlay Captions

`POST /api/videos/add-text-overlay-captions`

Displays user-provided text lines over a video, one line every duration_per_line seconds.

Content type: `application/json`

Parameters:

- `video_url` (string, required): Video URL.
- `text` (string, required): One or more caption lines separated by newlines.
- `subtitle_style` (string, optional): plain-white, yellow-bg, pink-bg, blue-bg, or red-bg. Default: `plain-white`.
- `aspect_ratio` (string, optional): 16:9, 9:16, 4:3, or 3:4. Default: `9:16`.
- `position` (string, optional): top, center, or bottom. Default: `center`.
- `duration_per_line` (integer, optional): Seconds per text line from 1 to 30. Default: `5`.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/videos/add-text-overlay-captions" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "video_url": "https://example.com/video.mp4",
  "text": "First line\nSecond line",
  "duration_per_line": 4
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### YouTube to MP4

`POST /api/youtube_to_mp4`

Accepts a standard YouTube watch URL, youtu.be URL, Shorts URL, embed URL, or /v/ URL and returns a downloadable MP4 URL.

Content type: `application/json or form data`

Parameters:

- `youtube_url` (string, required): Single YouTube video URL. Playlists are not supported.

Example:

```bash
curl -X POST "https://ffmpegapi.net/api/youtube_to_mp4" \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
  "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
}'
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

### Job Status

`GET /api/job/{job_id}/status`

Returns pending, processing, completed, or failed status for an explicitly asynchronous or automatically queued job. Pending responses include `queue_position`.

Content type: `query string or X-API-Key header`

Parameters:

- `job_id` (string, required): Job ID returned by a `202 Accepted` response.

Example:

```bash
curl -X GET "https://ffmpegapi.net/api/job/job_123/status?api_key=your_api_key_here"
```

Typical successful response fields include `success`, `message`, `download_url`, and `filename` for file-producing endpoints. Split endpoints may return arrays of part or segment URLs. Caption endpoints may return caption artifact URLs.

## Error Responses

Errors use JSON with `success: false` and an `error` message. Common HTTP status codes are 400 for validation problems, 401 for missing or invalid API keys, 403 for job access denial, 404 for missing jobs, 500 for processing errors, and 504 for rendering timeouts.
