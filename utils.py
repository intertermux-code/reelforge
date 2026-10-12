"""
Utility functions for file discovery.
"""
import os
from pathlib import Path
from typing import List
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import pillow_heif

# Register HEIC opener with Pillow
pillow_heif.register_heif_opener()

# Define supported file types
SUPPORTED_IMAGE_FORMATS = ('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.heic', '.heif')
SUPPORTED_AUDIO_FORMATS = ('.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg')
SUPPORTED_VIDEO_FORMATS = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv')

# Create a combined tuple for the new input
SUPPORTED_MEDIA_FORMATS = SUPPORTED_IMAGE_FORMATS + SUPPORTED_VIDEO_FORMATS

def find_files(directory: Path, file_formats: tuple) -> List[Path]:
    """
    Recursively finds all files of the specified formats in a directory.
    
    Args:
        directory: The pathlib.Path object of the directory to search.
        file_formats: A tuple of lowercase file extensions (e.g., ('.jpg', '.png')).
        
    Returns:
        A list of pathlib.Path objects for all matching files.
    """
    if not directory or not directory.is_dir():
        return []
        
    files = []
    for ext in file_formats:
        files.extend(directory.rglob(f'*{ext}'))
        # Check uppercase too
        files.extend(directory.rglob(f'*{ext.upper()}'))
        
    return list(set(files))

def find_object_in_media(media_path: Path, target_reference_path: Path):
    """
    Scans the media (image or first frame of video) for the target_reference image.
    Returns (x, y, w, h) if found, else None.
    """
    try:
        # 1. Load the Target Reference (The thing to hide)
        target_img = cv2.imread(str(target_reference_path), 0) # Grayscale
        if target_img is None: return None
        t_h, t_w = target_img.shape[:2]

        # 2. Load the Media (Handling HEIC special case)
        search_img = None
        ext = media_path.suffix.lower()

        if ext in ('.heic', '.heif'):
            # OpenCV cannot read HEIC directly. Use Pillow -> Numpy.
            try:
                pil_img = Image.open(media_path)
                pil_img = pil_img.convert('L') # Convert to Grayscale
                search_img = np.array(pil_img)
            except Exception as e:
                print(f"HEIC Load Error: {e}")
                return None

        elif ext in SUPPORTED_VIDEO_FORMATS:
            # Extract first frame from video
            cap = cv2.VideoCapture(str(media_path))
            ret, frame = cap.read()
            cap.release()
            if not ret: return None
            search_img = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        else:
            # Standard Image (JPG/PNG)
            search_img = cv2.imread(str(media_path), 0)

        if search_img is None: return None

        # 3. Match Template (The Scan)
        # We search for the target inside the media
        result = cv2.matchTemplate(search_img, target_img, cv2.TM_CCOEFF_NORMED)
        
        # 4. Check Confidence
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        # Threshold: 0.7 means 70% match confidence. 
        if max_val >= 0.7: 
            return (max_loc[0], max_loc[1], t_w, t_h)
        
        return None

    except Exception as e:
        print(f"CV Scan Error: {e}")
        return None

def create_rounded_text_image(
    text: str,
    font_path: str,
    font_size: int,
    text_color: str,
    box_opacity: float,
    output_path: Path,
    max_width: int = 900 # <-- New Argument
):
    """
    Generates a transparent image with wrapped text inside a rounded box.
    """
    try:
        # 1. Smart Dynamic Font Sizing & macOS Fallbacks
        # Dynamic TTF font path resolver for macOS to bypass pixelated default PIL font
        resolved_font_path = font_path
        if not resolved_font_path or not Path(resolved_font_path).exists():
            mac_fallbacks = [
                "/System/Library/Fonts/Helvetica.ttc",
                "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/System/Library/Fonts/Supplemental/Verdana.ttf",
                "/Library/Fonts/Arial.ttf",
                "/Library/Fonts/Helvetica.ttc"
            ]
            for p in mac_fallbacks:
                if Path(p).exists():
                    resolved_font_path = p
                    break

        user_font_size = font_size if font_size > 0 else 64
        
        # Calculate base font size relative to max_width (e.g. 7.5% of max_width)
        base_size = max_width * 0.075
        
        # Apply scaling factor based on text length to keep it balanced
        char_count = len(text)
        if char_count < 25:
            length_factor = 1.3
        elif char_count < 40:
            length_factor = 1.15
        elif char_count > 180:
            length_factor = 0.7
        elif char_count > 120:
            length_factor = 0.8
        elif char_count > 80:
            length_factor = 0.9
        else:
            length_factor = 1.0
            
        # Scale based on user choice relative to standard default 64
        user_factor = user_font_size / 64.0
        
        # Calculate final optimal font size
        optimal_font_size = int(base_size * length_factor * user_factor)
        optimal_font_size = max(18, min(optimal_font_size, 150)) # Clamp to safe bounds
        
        try:
            font = ImageFont.truetype(resolved_font_path, optimal_font_size) if resolved_font_path else ImageFont.load_default()
        except Exception as e:
            print(f"Failed to load custom font, falling back to default PIL font: {e}")
            font = ImageFont.load_default()

        # 2. Smart Word Wrapping
        dummy_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
        words = text.split()
        lines = []
        current_line = []

        for word in words:
            # Test if adding this word exceeds max_width
            test_line = ' '.join(current_line + [word])
            bbox = dummy_draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
            
            if w <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    # Case: Single word is longer than max_width
                    lines.append(word)
                    current_line = []
        
        if current_line:
            lines.append(' '.join(current_line))
        
        if not lines: lines = [text] # Safety fallback

        # 3. Calculate Dimensions
        # Get height metrics
        ascent, descent = font.getmetrics()
        line_height = ascent + descent
        line_spacing = int(line_height * 0.2) # 20% spacing between lines
        
        # Total text block height
        total_text_height = (len(lines) * line_height) + ((len(lines) - 1) * line_spacing)
        
        # Max line width found
        max_line_width = 0
        for line in lines:
            bbox = dummy_draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            if w > max_line_width: max_line_width = w

        # 4. Define Box Dimensions with Padding
        padding_x = 40
        padding_y = 30
        box_width = max_line_width + (padding_x * 2)
        box_height = total_text_height + (padding_y * 2)

        # 5. Draw Canvas & Rounded Box
        img = Image.new('RGBA', (box_width, box_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        radius = 40 # Fixed nice corner radius
        alpha = int(float(box_opacity) * 255)
        box_color = (0, 0, 0, alpha)

        draw.rounded_rectangle(
            [(0, 0), (box_width, box_height)],
            radius=radius,
            fill=box_color,
            outline=None
        )

        # 6. Draw Each Line Centered with Smart Legibility Outlines
        y_cursor = padding_y # Start drawing text after top padding
        
        # Calculate dynamic stroke parameters based on text color and box transparency
        stroke_w = 0
        stroke_c = None
        
        normalized_color = text_color.strip().lower()
        if normalized_color in ["white", "#fff", "#ffffff", "255,255,255", "rgb(255,255,255)"]:
            if alpha < 90:  # Very transparent or no box background
                stroke_w = max(2, int(optimal_font_size * 0.045))  # Proportional thicker stroke
                stroke_c = "black"
            else:
                stroke_w = max(1, int(optimal_font_size * 0.02))  # Proportional thin crisp stroke
                stroke_c = "black"
        elif normalized_color in ["black", "#000", "#000000", "0,0,0", "rgb(0,0,0)"]:
            if alpha < 90:
                stroke_w = max(2, int(optimal_font_size * 0.045))
                stroke_c = "white"
            else:
                stroke_w = max(1, int(optimal_font_size * 0.02))
                stroke_c = "white"

        for line in lines:
            # Measure this specific line to center it horizontally
            bbox = dummy_draw.textbbox((0, 0), line, font=font)
            lw = bbox[2] - bbox[0]
            lx = (box_width - lw) / 2 
            
            # Correction for font vertical alignment
            ly = y_cursor - bbox[1] 
            
            if stroke_c:
                draw.text((lx, ly), line, font=font, fill=text_color, stroke_width=stroke_w, stroke_fill=stroke_c)
            else:
                draw.text((lx, ly), line, font=font, fill=text_color)
            
            # Move cursor down
            y_cursor += line_height + line_spacing

        img.save(output_path, "PNG")
        return True

    except Exception as e:
        print(f"Error creating text image: {e}")
        return False