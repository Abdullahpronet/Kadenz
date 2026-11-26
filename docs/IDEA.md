# BeatForge: Idea & Architecture

## 🎯 The vision

> Anyone with a folder of clips and a song should get a beat-synced edit in minutes, **on their own machine**, without uploading anything, and keep full creative control afterward.

### Who it's for
- **Gaming and esports editors:** kill montages, clan highlight reels, tournament recaps
- **Short-form creators:** TikTok, Reels and Shorts edits
- **Video editors:** a fast first rough cut they can polish

### What makes it different
| Other tools | BeatForge |
|---|---|
| Cloud upload, subscription | **100% local**, free and open source |
| Output is a flat rendered video | Output is an **editable AE / Resolve project** |
| Black-box AI | Readable **edit plan JSON**: inspect, tweak, version it |
| One style | **Style presets** anyone can write and share |

---

## 🏗️ Architecture

BeatForge is a pipeline of **4 independent stages**. Each stage reads and writes plain data, so each one can be built, tested and improved on its own.

```
song.mp3 ──► [1] Audio Analyzer ──┐
                                   ├──► [3] Director ──► edit_plan.json ──► [4] Exporters
clips/   ──► [2] Clip Analyzer  ──┘                                         ├─ After Effects (.jsx)
                                                                            ├─ DaVinci Resolve
                                                                            └─ ffmpeg (quick render)
```

### [1] Audio Analyzer: `beatforge/audio/`
**Input:** song file. **Output:** `music_map.json`

- Tempo (BPM) and **beat** timestamps
- **Downbeats** (the first beat of each bar), which make stronger cut points
- **Onset strength / energy curve**, which shows where the song hits hard
- **Sections:** intro, build-up, drop, breakdown, outro

Tools: `librosa` (MVP), optionally `madmom` or `beat_this` for better accuracy.

### [2] Clip Analyzer: `beatforge/vision/`
**Input:** folder of clips. **Output:** `shots.json`

- **Shot detection:** split each clip into shots (`PySceneDetect`)
- **Motion score:** how much action happens, measured with optical flow / frame difference
- **AI tags (v0.2):** a local vision model labels each shot, e.g. `action`, `calm`, `highlight`, `crowd`, `text-on-screen`
- **Best moment:** the peak timestamp inside each shot

Tools: `PySceneDetect`, `OpenCV`, CLIP / a small local VLM.

### [3] Director: `beatforge/brain/`
**Input:** `music_map.json` + `shots.json` + style preset. **Output:** `edit_plan.json`

Decides **which shot goes where**:
- High-energy shots on drops, calm shots in the intro and breakdowns
- Cut frequency follows energy (every beat on the drop, every bar in calm parts)
- Avoids repeating the same shot back to back
- Picks effects per cut based on the style preset

**v0.1:** rule-based (fast, predictable, no AI needed).
**v0.2:** a local LLM (via Ollama / llama.cpp) gets a compact summary of the song and shots and returns the plan. The rule engine validates the plan and repairs it if needed.

### [4] Exporters: `beatforge/exporters/`
**Input:** `edit_plan.json`. **Output:** a project for your editor.

- **After Effects:** generates an ExtendScript `.jsx` that imports footage, creates the comp, places and trims layers on the beats, and adds effect keyframes. Can run headless through `aerender`.
- **DaVinci Resolve (v0.3):** uses Resolve's Python scripting API.
- **ffmpeg (v0.3):** a quick preview render without any editor.

---

## 📄 The edit plan: the heart of BeatForge

Everything flows through one simple, human-readable file. See [`examples/edit_plan.example.json`](../examples/edit_plan.example.json).

```json
{
  "version": "0.1",
  "comp": { "width": 1920, "height": 1080, "fps": 60, "duration": 30.0 },
  "song": { "path": "track.mp3", "bpm": 140, "start": 0.0 },
  "cuts": [
    {
      "start": 0.000, "end": 1.714,
      "clip": "clips/clutch_1v3.mp4", "in": 12.40,
      "speed": 1.0,
      "effects": [{ "type": "zoom_punch", "at": 0.0, "strength": 0.15 }]
    }
  ]
}
```

Because the plan is plain JSON:
- Anyone can write a **new exporter** (Premiere, CapCut, Blender…)
- Anyone can write a **new director** (a different AI, different rules)
- Users can **hand-edit** the plan before building

---

## 🎨 Style presets

Styles are small config files that steer the director:

| Style | Cut rhythm | Effects |
|---|---|---|
| **Velocity** | every beat on drops | speed ramps, zoom punches, flashes |
| **Cinematic** | every bar, long holds | slow fades, subtle zoom, letterbox |
| **Esports Montage** | beat-synced, hits on kills | shake, flash, impact frames |
| **Chill** | every 2 bars | crossfades, gentle pans |

---

## 🧪 Tech stack

| Part | Tech |
|---|---|
| Core | Python 3.10+ |
| Audio | librosa → madmom / beat_this |
| Video | PySceneDetect, OpenCV, ffmpeg |
| Vision AI | CLIP / small local VLM |
| LLM | Ollama / llama.cpp (any local model) |
| AE bridge | ExtendScript `.jsx` + `aerender` |
| GUI (v0.4) | TBD: Tauri or PySide6 |

---

## ⚠️ Known challenges

- **AE scripting speed:** long timelines with many layers build slowly, so the focus is on 15–90 s edits.
- **Codec support:** AE dislikes some codecs (e.g. variable frame rate phone footage). An optional ffmpeg pre-transcode step fixes this.
- **LLM reliability:** LLMs can return invalid timings, so the rule engine always validates and repairs the plan.
- **No AE?** Resolve and ffmpeg exporters keep the tool useful for everyone.

---

## 🚀 Launch plan (goal: 5K ⭐)

1. Ship **v0.1** with a killer **demo GIF**: clips in, AE timeline building itself on the beat
2. README polished, one-command install
3. Same-day launch: Show HN, r/AfterEffects, r/editors, r/LocalLLaMA, r/VideoEditing, X / TikTok (post an edit *made by BeatForge*)
4. Ship visibly afterward: weekly releases, community style presets, a showcase of user edits
