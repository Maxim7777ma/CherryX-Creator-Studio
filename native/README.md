# Native Helpers

This folder contains small C++ executables for CPU-heavy media analysis.

Build on Windows:

```powershell
.\native\build_native.ps1
```

Current helpers:

- `audio_rms`: reads signed 16-bit little-endian PCM from stdin and emits RMS windows. Python uses it automatically when `native/bin/audio_rms.exe` exists, with a pure-Python fallback when it does not.
- `media_analyzer`: reads resized RGB video frames from stdin and emits JSONL visual scores for motion, scene change, sharpness, contrast, saturation, exposure, and total score.
- `cover_pick`: reads resized RGB video frames from stdin and emits the best frame index for cover selection.
- `face_track`: optional capability. The default build keeps Python OpenCV face tracking active unless an OpenCV-backed native helper is enabled.

The build writes `native/capabilities.json`; Python reads it to decide which helpers are available. Missing or failing helpers never break jobs: Python fallbacks stay active.
