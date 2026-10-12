"""
The core media processing engines.
Contains worker threads for all app functions.
"""
import random
import threading
import queue
import ffmpeg
import re
from pathlib import Path
from typing import List, Dict, Any, Callable
import logging
# import subprocess  # <-- No longer needed

# Get a logger for this module
log = logging.getLogger(__name__)

# --- CLASS 1: VIDEO PROCESSOR (Now with Corrected run_async args) ---

class VideoProcessor(threading.Thread):
    """
    Runs the Photo-to-Video processing in a background thread.
    """
    def __init__(
        self,
        media_list: List[Path],
        music_list: List[Path],
        output_dir: Path,
        message_queue: queue.Queue,
        add_music: bool = True,
        manual_duration: int = 5,
        sticker_path: Path = None,
        reference_path: Path = None,
        save_as_image: bool = False,
        apply_bnw: bool = False,
        # NEW ARGS
        text_enable: bool = False,
        text_content: str = "",
        text_font: str = "",
        text_size: str = "64",
        text_color: str = "white",
        text_opacity: str = "0.6",
        aspect_ratio: str = "Original",
        ai_text_enable: bool = False,
        ai_prompt: str = ""
    ):
        super().__init__(daemon=True)
        self.media_list = media_list
        self.music_list = music_list
        self.output_dir = output_dir
        self.message_queue = message_queue
        self.add_music = add_music
        self.manual_duration = manual_duration
        self.sticker_path = sticker_path
        self.reference_path = reference_path
        self.save_as_image = save_as_image
        self.apply_bnw = apply_bnw
        self.text_enable = text_enable
        self.text_content = text_content
        self.text_font = text_font
        self.text_size = text_size
        self.text_color = text_color
        self.text_opacity = text_opacity
        self.aspect_ratio = aspect_ratio
        self.ai_text_enable = ai_text_enable
        self.ai_prompt = ai_prompt
        self.is_running = True
        self.current_process = None
        log.info("VideoProcessor thread initialized.")

    def _send_message(self, msg_type: str, data: Dict[str, Any]):
        data['type'] = msg_type
        self.message_queue.put(data)

    def _generate_ai_insight(self) -> str:
        """
        Generates a short AI-generated text insight for overlaying on videos.
        The topic/prompt is configurable via the `ai_prompt` setting; a generic
        educational default is used when no custom prompt is provided.
        Uses a Gemini-compatible model via direct HTTPS POST.
        Falls back to a local `gemini` CLI on PATH (authenticated via
        the GEMINI_API_KEY environment variable).
        Falls back to a local predefined list if both fail.
        Ensures strict uniqueness by matching against a persistent history log.
        """
        import urllib.request
        import json
        import subprocess
        import shutil
        import os
        import random
        from pathlib import Path

        # 1. Load History Log (bounded to 300 items to prevent storage bloat)
        history_file = Path(__file__).parent / "weaver_history.json"
        history = []
        if history_file.exists():
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                    if not isinstance(history, list):
                        history = []
            except Exception:
                history = []

        # 2. Similarity Helper to detect duplicate meanings
        def is_too_similar(new_text: str, history_list: list) -> bool:
            # Clean and tokenize words
            def tokenize(text: str):
                import re
                words = re.findall(r'\b\w+\b', text.lower())
                # filter out small common stop words to focus on real semantic content
                stops = {"the", "a", "an", "is", "are", "of", "to", "and", "in", "or", "for", "on", "with", "about"}
                return {w for w in words if w not in stops}

            new_tokens = tokenize(new_text)
            if not new_tokens:
                return False

            for past in history_list:
                past_tokens = tokenize(past)
                if not past_tokens:
                    continue
                intersection = new_tokens.intersection(past_tokens)
                union = new_tokens.union(past_tokens)
                similarity = len(intersection) / len(union)
                # If more than 55% similarity, reject it as a duplicate
                if similarity > 0.55:
                    return True
            return False

        # 3. Dynamic Prompt Construction with Negative Prompts
        # Take up to the last 15 entries to use as negative prompt context (stops LLM from recycling ideas)
        recent_insights = history[-15:]
        avoid_clause = ""
        if recent_insights:
            avoid_clause = "\nCRITICAL: Do not generate anything similar to these recently generated insights:\n" + "\n".join(f"- {item}" for item in recent_insights)

        base_prompt = self.ai_prompt.strip() or (
            "Generate one extremely concise, engaging, and accurate educational insight "
            "or tip. Keep it strictly under 15-20 words so it fits on an "
            "Instagram post. Do not include any intros, markdown, quotes, emojis, hashtags, or formatting. "
            "Return only the plain text message itself."
        )
        prompt = base_prompt + avoid_clause

        # API key is never hardcoded: provide it via the GEMINI_API_KEY env var.
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        fallback_insights = [
            "Small consistent habits compound into remarkable long-term results.",
            "Drinking enough water daily improves focus, energy, and overall health.",
            "Taking short breaks during deep work boosts productivity and creativity.",
            "Reading just 20 minutes a day builds knowledge faster than you expect.",
            "Good sleep is the foundation of memory, mood, and immune health.",
            "Walking daily is one of the simplest boosts for body and mind.",
            "Writing down your goals makes you significantly more likely to achieve them.",
            "Learning a new skill keeps your brain sharp at any age.",
            "Gratitude journaling is linked to lower stress and better sleep.",
            "Eating more whole foods and fewer processed ones improves energy levels.",
            "Deep breathing for two minutes can quickly calm a stressed mind.",
            "Regular stretching prevents injury and improves posture over time.",
            "Limiting screen time before bed leads to measurably better sleep.",
            "Teaching someone else is the fastest way to master a topic yourself.",
            "A tidy workspace reduces distractions and improves concentration.",
        ]

        # 4. Generation Loop with Deduplication Retry (up to 3 attempts)
        for attempt in range(3):
            self._send_message("log", {"message": f"  -> AI insight generation attempt {attempt + 1}/3..."})
            text = None

            # Attempt 1: Direct HTTPS Request (skipped when no API key is configured)
            if api_key:
                url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
                payload = {
                    "contents": [{
                        "parts": [{"text": prompt}]
                    }]
                }
                try:
                    req = urllib.request.Request(
                        url,
                        headers={
                            "Content-Type": "application/json",
                            "x-goog-api-key": api_key,
                        },
                        data=json.dumps(payload).encode("utf-8"),
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=10) as response:
                        res_data = json.loads(response.read().decode("utf-8"))
                        candidates = res_data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                raw_text = parts[0].get("text", "").strip()
                                if raw_text:
                                    text = raw_text.replace('"', '').replace("'", "").strip()
                except Exception as e:
                    self._send_message("log", {"message": f"     [API Attempt Failed: {e}]"})

            # Attempt 2: CLI Fallback (if HTTP failed or returned empty)
            # Uses a `gemini` CLI on PATH, authenticated via GEMINI_API_KEY env var.
            if not text:
                cli_path = shutil.which("gemini")
                if cli_path:
                    try:
                        env = os.environ.copy()
                        env["TERM"] = "dumb"
                        cmd = [cli_path, "-p", prompt]
                        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
                        if proc.returncode == 0:
                            lines = proc.stdout.split("\n")
                            clean_lines = [
                                l.strip() for l in lines
                                if l.strip()
                                and not l.strip().startswith("Warning:")
                                and "Ripgrep is not available" not in l
                                and not l.strip().startswith(">")
                                and "workspace" not in l
                            ]
                            if clean_lines:
                                raw_text = clean_lines[-1].replace('"', '').replace("'", "").strip()
                                if raw_text:
                                    text = raw_text
                    except Exception as e:
                        self._send_message("log", {"message": f"     [CLI Fallback Failed: {e}]"})
                elif not api_key:
                    self._send_message("log", {"message": "     [AI text skipped: set GEMINI_API_KEY or install a gemini CLI]"})

            # If we got a text, check for similarity
            if text:
                if is_too_similar(text, history):
                    self._send_message("log", {"message": f"     [Warning: AI generated a duplicate/similar insight: \"{text}\". Retrying...]"})
                    # Modify avoid_clause dynamically for next iteration to prevent same result
                    recent_insights.append(text)
                    avoid_clause = "\nCRITICAL: Do not generate anything similar to these recently generated insights:\n" + "\n".join(f"- {item}" for item in recent_insights)
                    prompt = base_prompt + avoid_clause
                    continue
                else:
                    # Found a perfectly unique one! Save and return.
                    history.append(text)
                    if len(history) > 300:
                        history = history[-300:] # Bounded FIFO queue
                    
                    try:
                        with open(history_file, 'w', encoding='utf-8') as f:
                            json.dump(history, f, indent=4, ensure_ascii=False)
                    except Exception as hist_err:
                        self._send_message("log", {"message": f"     [Error saving history log: {hist_err}]"})
                    
                    self._send_message("log", {"message": f"  -> AI generated unique insight: \"{text}\""})
                    return text

        # 5. Static Fallback: Predefined List Deduplication
        self._send_message("log", {"message": "  -> AI loops timed out or duplicated. Selecting a unique static fallback..."})
        unused_fallbacks = [item for item in fallback_insights if not is_too_similar(item, history)]
        
        if not unused_fallbacks:
            # If all fallbacks have been used, flush history partially to allow reuse or take oldest
            self._send_message("log", {"message": "  -> All predefined insights have been used recently. Recycling oldest entries..."})
            unused_fallbacks = fallback_insights

        selected = random.choice(unused_fallbacks)
        
        # Save fallback to history to prevent immediate reuse
        history.append(selected)
        if len(history) > 300:
            history = history[-300:]
        try:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

        self._send_message("log", {"message": f"  -> Dynamic Predefined insight selected: \"{selected}\""})
        return selected

    def run(self):
        total_files = len(self.media_list)
        log.info(f"Starting VideoProcessor job for {total_files} files.")
        self._send_message("log", {"message": f"Starting batch processing of {total_files} files..."})
        
        from utils import SUPPORTED_IMAGE_FORMATS, find_object_in_media, create_rounded_text_image
        from PIL import Image
        import os

        for i, original_file_path in enumerate(self.media_list):
            if not self.is_running:
                log.info("VideoProcessor 'is_running' flag set to False. Exiting loop.")
                self._send_message("log", {"message": "Processing cancelled by user."})
                break
            
            # --- HEIC PRE-PROCESSING ---
            # Default to using the original file
            file_path = original_file_path
            temp_file_created = None

            # Check if HEIC
            if file_path.suffix.lower() in ('.heic', '.heif'):
                try:
                    self._send_message("log", {"message": f"  -> Converting HEIC to JPG for processing..."})
                    img = Image.open(file_path)
                    # Create a temp filename
                    temp_jpg = file_path.with_suffix('.temp.jpg')
                    img.save(temp_jpg, "JPEG")
                    
                    # SWAP: Use the temp JPG for all processing below
                    file_path = temp_jpg
                    temp_file_created = temp_jpg
                except Exception as e:
                    log.error(f"HEIC Conversion failed: {e}")
                    self._send_message("error", {"message": f"Skipping {original_file_path.name}: Could not convert HEIC."})
                    continue
            
            try:
                is_image = file_path.suffix.lower() in SUPPORTED_IMAGE_FORMATS or file_path.suffix.lower() == '.temp.jpg'
                
                # --- SCENARIO 1: IMAGE MODE ---
                # Smart Logic: Save as Image if:
                # 1. User checked "Save as Image" OR
                # 2. B&W filter is ON and Music is OFF (Smart Auto-Detect)
                should_save_as_image = self.save_as_image or (is_image and self.apply_bnw and not self.add_music)

                if should_save_as_image:
                    self._send_message("log", {"message": f"({i+1}) Watermarking Image (Smart Mode): {original_file_path.name}"})
                    
                    sanitized_stem = re.sub(r'[^\w\.-]', '_', original_file_path.stem)
                    output_filename = self.output_dir / f"{sanitized_stem}_marked.jpg" 
                    
                    # Simple Overlay Command for Images
                    stream = ffmpeg.input(str(file_path))
                    
                    # Aspect Ratio Scaling & Cropping (NEW)
                    tw, th = 1080, 1080  # Default fallback if needed
                    has_custom_aspect = (self.aspect_ratio != "Original")
                    if has_custom_aspect:
                        if self.aspect_ratio == "9:16 (Reels)":
                            tw, th = 1080, 1920
                        elif self.aspect_ratio == "16:9 (Landscape)":
                            tw, th = 1920, 1080
                        
                        stream = stream.filter('scale', w=f"if(gte(iw/ih,{tw}/{th}),-2,{tw})", h=f"if(gte(iw/ih,{tw}/{th}),{th},-2)")
                        stream = stream.filter('crop', tw, th)
                    else:
                        # Probe the image to get original width and height
                        try:
                            with Image.open(file_path) as img_probe:
                                tw, th = img_probe.size
                        except:
                            tw, th = 1080, 1080  # fallback
                    
                    # 1. Apply B&W Filter (High Contrast "Inkwell" style)
                    if self.apply_bnw:
                        stream = stream.filter('eq', saturation=0, contrast=1.2)

                    # 2. Apply Sticker (After filter, so sticker keeps color)
                    if self.sticker_path:
                        sticker = ffmpeg.input(str(self.sticker_path))
                        stream = ffmpeg.overlay(stream, sticker, x='W-w-10', y='H-h-10')

                    # 3. Apply Text Overlay if enabled (NEW)
                    temp_text_img = None
                    if self.text_enable:
                        text_to_draw = self._generate_ai_insight() if self.ai_text_enable else self.text_content
                        if text_to_draw:
                            safe_max_width = int(tw * 0.85)
                            temp_text_img = self.output_dir / f"{sanitized_stem}_textoverlay.png"
                            
                            success = create_rounded_text_image(
                                text=text_to_draw,
                                font_path=self.text_font,
                                font_size=int(self.text_size),
                                text_color=self.text_color,
                                box_opacity=float(self.text_opacity),
                                output_path=temp_text_img,
                                max_width=safe_max_width
                            )
                            if success and temp_text_img.exists():
                                text_overlay_stream = ffmpeg.input(str(temp_text_img))
                                
                                # Positioning: Bottom center (specifically 250px up for Reels, 150px for others)
                                if self.aspect_ratio == "9:16 (Reels)":
                                    selected_y = "H-h-250"
                                else:
                                    selected_y = "H-h-150"
                                    
                                stream = ffmpeg.overlay(stream, text_overlay_stream, x="(W-w)/2", y=selected_y)
                            else:
                                log.error("Failed to generate rounded text image for image.")
                    
                    cmd = ffmpeg.output(stream, str(output_filename)).overwrite_output()
                    self.current_process = cmd.run_async(pipe_stdout=True, pipe_stderr=True)
                    self.current_process.communicate()
                    
                    # Clean up temp text image in image mode
                    if temp_text_img and temp_text_img.exists():
                        try: os.remove(temp_text_img)
                        except: pass
                    
                    # CLEANUP TEMP converted HEIC file
                    if temp_file_created:
                        try: os.remove(temp_file_created)
                        except: pass

                    self._send_message("progress", {"current": i + 1, "total": total_files})
                    continue # Skip to next file

                # --- SCENARIO 2 & 3: VIDEO MODE (Image/Video -> MP4) ---
                
                # 1. Determine Duration AND WIDTH
                audio_input = None
                input_duration = None
                video_width = 1080 # Default fallback
                
                if not is_image:
                    # If it's a video, probe it to know its length and width
                    try:
                        probe = ffmpeg.probe(str(file_path))
                        input_duration = float(probe['format']['duration'])
                        
                        # Get Width (Smart Wrap Logic)
                        video_stream_info = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
                        if video_stream_info:
                            video_width = int(video_stream_info['width'])
                    except:
                        input_duration = self.manual_duration # Fallback
                else:
                    input_duration = self.manual_duration # Default for images

                # 2. Handle Music (Overrides duration if added)
                if self.add_music and self.music_list:
                    song_path = random.choice(self.music_list)
                    try:
                        probe = ffmpeg.probe(str(song_path))
                        song_duration = float(probe['format']['duration'])
                        
                        # If input is image, video length = song length
                        # If input is video, usually we keep video length, but let's loop/cut audio to fit video
                        if is_image:
                            input_duration = song_duration
                        
                        # Use 'apad' (pad with silence) or 'atrim' to match lengths? 
                        # Simplest: Cut audio to match visual duration
                        audio_input = ffmpeg.input(str(song_path), t=input_duration)
                    except:
                        audio_input = None

                self._send_message("log", {"message": f"({i+1}) Processing Video: {file_path.name}"})

                # 3. Setup Visual Input
                if is_image:
                    # Loop image
                    visual_stream = ffmpeg.input(str(file_path), loop=1, t=input_duration)
                else:
                    # Real video
                    visual_stream = ffmpeg.input(str(file_path))

                # Aspect Ratio Scaling & Cropping (NEW)
                tw, th = 1080, 1080  # Default fallback if needed
                has_custom_aspect = (self.aspect_ratio != "Original")
                if has_custom_aspect:
                    if self.aspect_ratio == "9:16 (Reels)":
                        tw, th = 1080, 1920
                    elif self.aspect_ratio == "16:9 (Landscape)":
                        tw, th = 1920, 1080
                    
                    visual_stream = visual_stream.filter('scale', w=f"if(gte(iw/ih,{tw}/{th}),-2,{tw})", h=f"if(gte(iw/ih,{tw}/{th}),{th},-2)")
                    visual_stream = visual_stream.filter('crop', tw, th)
                    video_width = tw
                else:
                    # Keep probed width
                    tw = video_width

                # 4. Apply B&W Filter (High Contrast "Inkwell" style)
                # We apply this BEFORE the sticker, so the sticker stays colored.
                if self.apply_bnw:
                    visual_stream = visual_stream.filter('eq', saturation=0, contrast=1.2)

                # 5. Apply Smart Sticker Overlay
                if self.sticker_path:
                    sticker_inp = ffmpeg.input(str(self.sticker_path), loop=1, t=input_duration)
                    
                    # Variables for overlay
                    overlay_x = "W-w-1"  # Default X
                    overlay_y = "H-h-1"  # Default Y
                    sticker_processed = sticker_inp # Start with raw sticker

                    # Check Scan
                    scan_success = False
                    if self.reference_path:
                        found_rect = find_object_in_media(file_path, self.reference_path)
                        if found_rect:
                            fx, fy, fw, fh = found_rect
                            self._send_message("log", {"message": f"  -> Covered target at: {fx}x{fy}"})
                            
                            # Resize sticker to EXACTLY cover the found object
                            sticker_processed = sticker_inp.filter('scale', fw, fh)
                            overlay_x = str(fx)
                            overlay_y = str(fy)
                            scan_success = True
                    
                    if not scan_success:
                        # FALLBACK: Consistent Relative Size (15% of Main Video Height)
                        # We use 'scale2ref' filter which scales input 2 (sticker) relative to input 1 (video)
                        # scale2ref outputs [sticker_scaled] [main_video_unchanged]
                        sticker_processed_out = ffmpeg.filter_multi_output([sticker_inp, visual_stream], 'scale2ref', w='oh*mdar', h='ih*0.15')
                        
                        sticker_scaled = sticker_processed_out[0]
                        visual_stream = sticker_processed_out[1] # We must use this passed-through stream
                        
                        # Use the scaled sticker
                        visual_stream = ffmpeg.overlay(visual_stream, sticker_scaled, x=overlay_x, y=overlay_y)
                    else:
                        # Scan success: Just overlay the explicitly sized sticker
                        visual_stream = ffmpeg.overlay(visual_stream, sticker_processed, x=overlay_x, y=overlay_y)

                # 6. Apply Random/AI Text Overlay (Rounded Box Style) (UPDATED)
                temp_text_img = None
                if self.text_enable:
                    # Decide what text content to use
                    text_to_draw = self._generate_ai_insight() if self.ai_text_enable else self.text_content
                    
                    if text_to_draw:
                        # Calculate safe max width (e.g., 85% of screen width)
                        safe_max_width = int(video_width * 0.85)
                        
                        sanitized_stem = re.sub(r'[^\w\.-]', '_', original_file_path.stem)
                        temp_text_img = self.output_dir / f"{sanitized_stem}_textoverlay.png"
                        
                        success = create_rounded_text_image(
                            text=text_to_draw,
                            font_path=self.text_font,
                            font_size=int(self.text_size),
                            text_color=self.text_color,
                            box_opacity=float(self.text_opacity),
                            output_path=temp_text_img,
                            max_width=safe_max_width
                        )

                        if success and temp_text_img.exists():
                            # B. Create Input Stream for the Text Image
                            # Loop it to match the video duration
                            text_overlay_stream = ffmpeg.input(str(temp_text_img), loop=1, t=input_duration)

                            # C. Determine Y Position (Optimized for Reels & AI bottom placement)
                            if self.ai_text_enable or self.aspect_ratio == "9:16 (Reels)":
                                if self.aspect_ratio == "9:16 (Reels)":
                                    selected_y = "H-h-250"  # Reels safe area
                                else:
                                    selected_y = "H-h-150"  # Bottom safe area
                            else:
                                possible_y_positions = [
                                    "100",              # Top
                                    "(H-h)/2",          # Center
                                    "H-h-100"           # Bottom
                                ]
                                selected_y = random.choice(possible_y_positions)

                            # D. Overlay the Text Image
                            # x=(W-w)/2 centers it horizontally
                            visual_stream = ffmpeg.overlay(
                                visual_stream,
                                text_overlay_stream,
                                x="(W-w)/2",
                                y=selected_y
                            )
                        else:
                            log.error("Failed to generate rounded text image. Skipping text overlay.")

                # 5. Output
                # Ensure dimensions are divisible by 2 for libx264 (H.264) compatibility
                visual_stream = visual_stream.filter('scale', 'trunc(iw/2)*2', 'trunc(ih/2)*2')

                # Use original_file_path.stem so output doesn't say ".temp"
                sanitized_stem = re.sub(r'[^\w\.-]', '_', original_file_path.stem)
                output_filename = self.output_dir / f"{sanitized_stem}_video.mp4"

                out_args = {'vcodec': 'libx264', 'pix_fmt': 'yuv420p', 't': input_duration}
                if audio_input:
                    out_args['acodec'] = 'aac'
                    # If input was video, we map the NEW audio, discarding old audio
                    cmd = ffmpeg.output(visual_stream, audio_input, str(output_filename), **out_args)
                else:
                    # If input was video and we added no music, should we keep original audio?
                    # Generally yes. If is_image, there is no audio.
                    # ffmpeg-python maps audio automatically if we don't specify.
                    # But 'visual_stream' (overlay output) usually loses audio track in filter graph.
                    # For simplicity in this bulk tool: No Music selected = Silent Output (if image) or Original Audio (if video, requires complex mapping).
                    # Let's keep it simple: Silent if no music added.
                    cmd = ffmpeg.output(visual_stream, str(output_filename), **out_args)

                cmd = cmd.overwrite_output()
                self.current_process = cmd.run_async(pipe_stdout=True, pipe_stderr=True)
                
                stdout, stderr = self.current_process.communicate()
                
                if self.current_process.returncode != 0:
                    raise ffmpeg.Error('ffmpeg', stdout, stderr)
                
                self.current_process = None
                self._send_message("progress", {"current": i + 1, "total": total_files})

                # CLEANUP TEMP FILE
                if temp_file_created:
                    try: 
                        os.remove(temp_file_created)
                    except: 
                        pass
                
                # Add this new cleanup for the text image
                if temp_text_img and temp_text_img.exists():
                    try: os.remove(temp_text_img)
                    except: pass

            except ffmpeg.Error as e:
                # CLEANUP TEMP FILE
                if temp_file_created:
                    try: os.remove(temp_file_created)
                    except: pass
                
                if temp_text_img and temp_text_img.exists():
                    try: os.remove(temp_text_img)
                    except: pass
                
                if not self.is_running:
                    log.info(f"ffmpeg process terminated by user for {file_path.name}")
                    self._send_message("log", {"message": f"Stopped processing {file_path.name}."})
                else:
                    log.exception(f"ffmpeg.Error on {file_path.name}")
                    error_message = e.stderr.decode() if e.stderr else 'Unknown ffmpeg error'
                    self._send_message("error", {"message": f"--- FAILED ON {file_path.name} ---\n{error_message}\n--------------------"})
            except Exception as e:
                # CLEANUP TEMP FILE
                if temp_file_created:
                    try: os.remove(temp_file_created)
                    except: pass

                if temp_text_img and temp_text_img.exists():
                    try: os.remove(temp_text_img)
                    except: pass

                if not self.is_running:
                     log.info(f"Process skipped by user for {file_path.name}")
                     self._send_message("log", {"message": f"Stopped processing {file_path.name}."})
                else:
                    log.exception(f"Unknown error on {file_path.name}")
                    self._send_message("error", {"message": f"An unknown error occurred on {file_path.name}: {e}"})

        if self.is_running:
            log.info("VideoProcessor job completed successfully.")
            self._send_message("complete", {"message": "Batch processing complete."})
        
        self.current_process = None
        
    def stop(self):
        log.info("VideoProcessor.stop() called.")
        self._send_message("log", {"message": "-> Sending cancellation signal..."})
        self.is_running = False
        if self.current_process:
            try:
                self.current_process.terminate()
                log.info("ffmpeg process terminated.")
                self._send_message("log", {"message": "-> ffmpeg process terminated."})
            except Exception as e:
                log.error("Error during process termination", exc_info=True)
                self._send_message("error", {"message": f"Could not terminate process: {e}"})

# --- CLASS 2: AUDIO EXTRACTOR (Now with Corrected run_async args) ---

class AudioExtractor(threading.Thread):
    """
    Runs the Video-to-Audio extraction in a background thread.
    """
    def __init__(
        self,
        video_list: List[Path],
        output_dir: Path,
        audio_format: str,
        message_queue: queue.Queue
    ):
        super().__init__(daemon=True)
        self.video_list = video_list
        self.output_dir = output_dir
        self.audio_format = audio_format
        self.message_queue = message_queue
        self.is_running = True
        self.current_process = None
        log.info("AudioExtractor thread initialized.")

    def _send_message(self, msg_type: str, data: Dict[str, Any]):
        data['type'] = msg_type
        self.message_queue.put(data)

    def run(self):
        total_files = len(self.video_list)
        log.info(f"Starting AudioExtractor job for {total_files} files.")
        self._send_message("log", {"message": f"Starting audio extraction for {total_files} videos..."})
        
        acodec = 'libmp3lame' if self.audio_format == 'mp3' else 'pcm_s16le' if self.audio_format == 'wav' else 'aac'

        for i, video_path in enumerate(self.video_list):
            if not self.is_running:
                log.info("AudioExtractor 'is_running' flag set to False. Exiting loop.")
                self._send_message("log", {"message": "Processing cancelled by user."})
                break
            
            try:
                log.debug(f"Extracting from: {video_path.name}")
                self._send_message("log", {"message": f"({i+1}/{total_files}) Extracting from: {video_path.name}"})

                input_video = ffmpeg.input(str(video_path))
                sanitized_stem = re.sub(r'[^\w\.-]', '_', video_path.stem)
                output_filename = self.output_dir / f"{sanitized_stem}.{self.audio_format}"
                
                log.debug(f"Output: {str(output_filename)}")
                self._send_message("log", {"message": f"  -> Output: {str(output_filename)}"})

                cmd = (
                    ffmpeg
                    .output(
                        input_video, 
                        str(output_filename), 
                        vn=None,
                        acodec=acodec
                    )
                    .overwrite_output()
                )
                
                # ** THE FINAL FIX **
                # Use the library-specific 'pipe_stdout' and 'pipe_stderr'
                self.current_process = cmd.run_async(
                    pipe_stdout=True, 
                    pipe_stderr=True
                )
                stdout, stderr = self.current_process.communicate()
                
                if self.current_process.returncode != 0:
                    raise ffmpeg.Error('ffmpeg', stdout, stderr)
                
                self.current_process = None
                self._send_message("progress", {"current": i + 1, "total": total_files})

            except ffmpeg.Error as e:
                if not self.is_running:
                    log.info(f"ffmpeg process terminated by user for {video_path.name}")
                    self._send_message("log", {"message": f"Stopped processing {video_path.name}."})
                else:
                    log.exception(f"ffmpeg.Error on {video_path.name}")
                    error_message = e.stderr.decode()
                    self._send_message("error", {"message": f"--- FAILED ON {video_path.name} ---\n{error_message}\n--------------------"})
            except Exception as e:
                if not self.is_running:
                     log.info(f"Process skipped by user for {video_path.name}")
                     self._send_message("log", {"message": f"Stopped processing {video_path.name}."})
                else:
                    log.exception(f"Unknown error on {video_path.name}")
                    self._send_message("error", {"message": f"An unknown error occurred on {video_path.name}: {e}"})

        if self.is_running:
            log.info("AudioExtractor job completed successfully.")
            self._send_message("complete", {"message": "Audio extraction complete."})
        
        self.current_process = None

    def stop(self):
        log.info("AudioExtractor.stop() called.")
        self._send_message("log", {"message": "-> Sending cancellation signal..."})
        self.is_running = False
        if self.current_process:
            try:
                self.current_process.terminate()
                log.info("ffmpeg process terminated.")
                self._send_message("log", {"message": "-> ffmpeg process terminated."})
            except Exception as e:
                log.error("Error during process termination", exc_info=True)
                self.message_queue.put({"type": "error", "message": f"Could not terminate process: {e}"})