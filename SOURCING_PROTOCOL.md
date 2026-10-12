# Clip Sourcing Protocol

How to source video clips for the visual rig.

## Trigger
Request clips by vibe/theme ("something cloudy"), by reference
("like the GitS montage"), or by direct YouTube URL. If given a vibe,
first review the repertoire and propose thematically extended picks
before downloading.

## Download
YouTube bot-checks datacenter IPs; pull from a residential connection.
Tools: `yt-dlp` + `ffmpeg`.

```
yt-dlp -f "bv*[height<=720]+ba/b[height<=720]/b" \
  -o "<slug>-temp.mp4" "<youtube-url>"
```
Then merge video+audio parts manually (auto-merge is unreliable):
```
ffmpeg -y -v error \
  -i "<slug>-temp.f398.mp4" -i "<slug>-temp.f251.webm" \
  -c:v copy -c:a aac "sourced-<slug>.mp4"
```
Notes:
- 720p cap: plenty for datamosh/mosaic work, keeps transfers fast.
- If formats differ, list the actual part filenames before merging.

## Index (standing rule: never delete sources)
Append to the repertoire under a dated heading:
- filename, content description, duration, resolution
- source (YouTube ID or site)
- one-line thematic note (why this clip, which thread it extends)

## Cleanup
Delete `*-temp*` parts after a successful transfer. Keep `yt-dlp`
and `ffmpeg` handy for the next pull.

## Compute
Run heavy work (renders, datamosh, audio processing) on the most
capable local machine available; the orchestrator stays lightweight.
