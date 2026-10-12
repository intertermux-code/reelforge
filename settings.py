"""
Settings Manager for ReelForge

Handles loading and saving the application's configuration
to a 'config.json' file.
"""
import json
from pathlib import Path

CONFIG_FILE = Path("config.json")

# Define the default structure
DEFAULT_SETTINGS = {
    "theme": "dark",
    "geometry": "750x600",
    "weaver_photo_dir": "",
    "weaver_music_dir": "",
    "weaver_output_dir": "",
    "weaver_add_music": True,
    "weaver_duration": 5,
    "weaver_sticker_path": "",
    "weaver_reference_path": "",
    "weaver_save_as_image": False,
    "weaver_apply_bnw": False,
    
    # Text Overlay Settings (NEW)
    "weaver_text_enable": False,
    "weaver_text_content": "Your Text Here",
    "weaver_text_font": "",         # Path to .ttf file
    "weaver_text_size": 64,
    "weaver_text_color": "white",   # Hex or Name (e.g., 'white', '#FF0000')
    "weaver_text_opacity": 0.6,     # Background Box Opacity (0.0 to 1.0)
    "weaver_aspect_ratio": "Original",
    "weaver_ai_text_enable": False,
    "weaver_ai_prompt": "",  # Custom AI text prompt; empty = built-in generic default
    "extractor_video_dir": "",
    "extractor_output_dir": "",
    "extractor_audio_format": "mp3"
}

def load_settings() -> dict:
    """
    Loads settings from config.json.
    Returns default settings if the file doesn't exist or is corrupt.
    """
    if not CONFIG_FILE.exists():
        return DEFAULT_SETTINGS
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            settings = json.load(f)
            # Ensure all keys from default are present
            for key, value in DEFAULT_SETTINGS.items():
                if key not in settings:
                    settings[key] = value
            return settings
    except (json.JSONDecodeError, IOError):
        # Corrupt file or read error, return defaults
        return DEFAULT_SETTINGS

def save_settings(settings: dict):
    """
    Saves the provided settings dictionary to config.json.
    """
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
    except IOError as e:
        # Handle cases like permissions errors
        print(f"Error saving settings: {e}")