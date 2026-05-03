# Dilapidation Report Generator

## Setup

1. Open `config.py` and fill in your project details and Anthropic API key
2. Add your photos to the correct folders:
   - `photos/northern_end/`
   - `photos/eastern_side/`
   - `photos/southern_end/`
   - `photos/western_side/`
3. Run: `python main.py`
4. Find your report in the `output/` folder

## Photo naming
Name your photos so they sort in the order you want them in the report.
Recommended: `001.jpg`, `002.jpg`, `003.jpg` etc.

## Limiting photos per folder

To cap how many photos are included from each folder, add this line to `config.py`:

```python
MAX_PHOTOS_PER_SECTION = 10  # change to any number you need
```

When a folder has more photos than this limit, the tool automatically selects photos spread evenly across the full set so the whole location is still represented. Set to `0` (or remove the line) to include all photos.

## API Key
Get your key from: https://console.anthropic.com/
