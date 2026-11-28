# Contributing to Kadenz

Thanks for your interest! Kadenz is early, so this is the best time to shape it. 🎬

## Ways to help
- 🐛 **Report bugs:** open an issue with your clips' format, AE version and the error
- 💡 **Suggest ideas:** new effects, styles or exporters
- 🎨 **Share style presets:** the easiest first contribution
- 🧩 **Build an exporter:** Premiere, CapCut, Blender… anything that can read `edit_plan.json`
- 🎞️ **Show your edits:** post them in Discussions → Showcase

## Project layout
```
kadenz/
  audio/       # [1] song → music_map.json
  vision/      # [2] clips → shots.json
  brain/       # [3] director → edit_plan.json
  exporters/   # [4] edit_plan.json → AE / Resolve / ffmpeg
docs/          # idea & architecture
examples/      # example edit plans and styles
```

## Dev setup
```bash
git clone https://github.com/Abdullahpronet/Kadenz.git
cd Kadenz
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Pull requests
1. Fork and create a branch: `feat/my-feature`
2. Keep PRs focused on one thing
3. Describe what changed and how you tested it (a short clip or GIF is great)
