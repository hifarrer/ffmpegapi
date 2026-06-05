# Blog Article Generator Context

## Current Blog Flow

FFMPEGAPI.net currently serves blog articles through Flask routes in `main.py`.

- `GET /blog` renders `templates/blog.html` with article metadata.
- `GET /blog/<slug>` renders `templates/blog_article.html`.
- The original articles are static Jinja partials in `templates/`, such as `blog_ffmpeg_api_guide.html`.
- Generated articles are stored in the `blog_articles` database table and merged into the same listing and article routes.
- `GET /sitemap.xml` includes static blog articles plus published generated articles.

Generated article content is stored as structured JSON and rendered by Jinja with normal escaping. The AI does not provide trusted raw HTML.

## Internal Generator Endpoint

Cron can call:

```text
GET /internal/api/generate-blog-articles?limit=3&token=YOUR_SECRET
```

Security and configuration:

- `BLOG_GENERATOR_SECRET` must be set.
- The secret can be sent as `?token=...` or `X-Internal-Token`.
- `OPENAI_API_KEY` must be set.
- `BLOG_GENERATOR_MODEL` is optional and defaults to `gpt-4o-mini`.
- `limit` defaults to `1` and is clamped from `1` to `10`.

For each generated post, the endpoint randomly picks one documented API endpoint, randomly picks one SEO topic angle, asks OpenAI for structured JSON, validates the payload, stores it as a published `BlogArticle`, and returns the created article URLs.

## AI Input Source

The generator uses `ai_discovery.ENDPOINTS` as the source of truth. This same catalog feeds `/docs.md`, `/examples.md`, `/llms.txt`, `/llms-full.txt`, and `/openapi.json`.

For the selected endpoint, the AI receives:

- endpoint name
- method and path
- summary and description
- content type
- parameters
- example request

The AI also receives FFMPEGAPI.net positioning:

- hosted REST API for FFmpeg-powered video and audio processing
- no server setup or FFmpeg infrastructure management
- API-key authentication
- useful for developers, automation, SaaS apps, content pipelines, and AI agents

The AI must return JSON with:

- `title`
- `description`
- `keywords`
- `intro`
- `sections`
- `conclusion`

## Documented Endpoint Catalog

| Operation ID | Endpoint | Summary |
| --- | --- | --- |
| `mergeImageAudio` | `POST /api/merge_image_audio` | Create an MP4 video from image/audio pairs. |
| `mergeVideos` | `POST /api/merge_videos` | Concatenate videos into a single MP4. |
| `videoLoop` | `POST /api/video_loop` | Loop a video by count or until it matches an audio track. |
| `pictureInPicture` | `POST /api/picture_in_picture` | Overlay one video on another. |
| `addWatermark` | `POST /api/add_watermark` | Overlay a watermark image onto a video. |
| `addSubtitles` | `POST /api/add_subtitles` | Burn ASS subtitles into a video. |
| `splitAudio` | `POST /api/split_audio` | Split audio into equal parts. |
| `splitAudioSegments` | `POST /api/split_audio_segments` | Split audio into fixed-duration segments. |
| `splitAudioTime` | `POST /api/split_audio_time` | Extract one audio range by millisecond timestamps. |
| `trimAudio` | `POST /api/trim_audio` | Trim audio to a desired length. |
| `trimVideo` | `POST /api/trim_video` | Trim video by start and end timestamps. |
| `splitVideo` | `POST /api/split_video` | Split a video into two parts. |
| `getFirstFrameImage` | `POST /api/get_first_frame_image` | Extract the first frame of a video as a JPEG. |
| `getLastFrameImage` | `POST /api/get_last_frame_image` | Extract the last frame of a video as a JPEG. |
| `convertToVertical` | `POST /api/convert_to_vertical` | Convert a horizontal video to vertical format. |
| `convertToTiktokPortrait` | `POST /api/convert_to_tiktok_portrait` | Convert a video to full-bleed 9:16 TikTok-style portrait. |
| `extractAudioMp3` | `POST /api/extract_audio_mp3` | Extract a video's audio track as MP3. |
| `convertVideoToGif` | `POST /api/convert_video_to_gif` | Encode a video as an animated GIF. |
| `addTiktokCaptions` | `POST /api/videos/add-tiktok-captions` | Transcribe a video and render TikTok-style captions. |
| `addTextOverlayCaptions` | `POST /api/videos/add-text-overlay-captions` | Render supplied text lines as timed caption overlays. |
| `youtubeToMp4` | `POST /api/youtube_to_mp4` | Return an MP4 download URL for a YouTube video. |
| `getJobStatus` | `GET /api/job/{job_id}/status` | Check asynchronous job status. |

`getJobStatus` is excluded from random article generation unless it is the only endpoint available, because it is a support endpoint rather than an SEO topic by itself.
