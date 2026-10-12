"""
WeaverTab: The UI and logic for the Photo-to-Video tool.
"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
import queue
import os
from pathlib import Path

from utils import find_files, SUPPORTED_IMAGE_FORMATS, SUPPORTED_AUDIO_FORMATS
from processor import VideoProcessor
import settings # <-- Import settings

class WeaverTab(ctk.CTkFrame):
    """
    Houses all widgets and logic for the Photo Weaver.
    """
    def __init__(self, parent, settings_obj: dict): # <-- Accept settings
        super().__init__(parent, fg_color="transparent")
        
        self.settings = settings_obj # <-- Store settings
        
        # Data storage
        # Load values directly from settings
        self.photo_dir = ctk.StringVar(value=self.settings.get("weaver_photo_dir", ""))
        self.music_dir = ctk.StringVar(value=self.settings.get("weaver_music_dir", ""))
        self.output_dir = ctk.StringVar(value=self.settings.get("weaver_output_dir", ""))
        self.sticker_path = ctk.StringVar(value=self.settings.get("weaver_sticker_path", ""))
        self.reference_path = ctk.StringVar(value=self.settings.get("weaver_reference_path", ""))
        self.add_music_var = ctk.BooleanVar(value=self.settings.get("weaver_add_music", True))
        self.save_as_image_var = ctk.BooleanVar(value=self.settings.get("weaver_save_as_image", False))
        self.apply_bnw_var = ctk.BooleanVar(value=self.settings.get("weaver_apply_bnw", False))
        
        # Text Vars
        self.text_enable_var = ctk.BooleanVar(value=self.settings.get("weaver_text_enable", False))
        self.text_content_var = ctk.StringVar(value=self.settings.get("weaver_text_content", "Your Text Here"))
        self.text_font_path = ctk.StringVar(value=self.settings.get("weaver_text_font", ""))
        self.text_size_var = ctk.StringVar(value=str(self.settings.get("weaver_text_size", "64")))
        self.text_color_var = ctk.StringVar(value=self.settings.get("weaver_text_color", "white"))
        self.text_opacity_var = ctk.StringVar(value=str(self.settings.get("weaver_text_opacity", "0.6")))
        self.aspect_ratio_var = ctk.StringVar(value=self.settings.get("weaver_aspect_ratio", "Original"))
        self.ai_text_enable_var = ctk.BooleanVar(value=self.settings.get("weaver_ai_text_enable", False))
        
        # Worker thread management
        self.message_queue = queue.Queue()
        self.worker_thread = None
        self.processing_active = False

        self._create_widgets()
        self._start_queue_monitor()

    # ... (widget creation remains the same) ...
    def _create_widgets(self):
        """Lays out all the GUI components."""
        # --- 1. Folder Selection Frame ---
        folder_frame = ctk.CTkFrame(self, fg_color="transparent")
        folder_frame.pack(fill="x", expand=True, pady=5)
        folder_frame.columnconfigure(1, weight=1)
        
        self.photo_button = ctk.CTkButton(folder_frame, text="Select Input Folder (Img/Vid)...", command=self._select_photos)
        self.photo_button.grid(row=0, column=0, sticky="w", pady=4)
        ctk.CTkLabel(folder_frame, textvariable=self.photo_dir, anchor="w").grid(row=0, column=1, sticky="ew", padx=10)
        
        self.music_button = ctk.CTkButton(folder_frame, text="Select Music Folder...", command=self._select_music)
        self.music_button.grid(row=1, column=0, sticky="w", pady=4)
        ctk.CTkLabel(folder_frame, textvariable=self.music_dir, anchor="w").grid(row=1, column=1, sticky="ew", padx=10)
        
        self.output_button = ctk.CTkButton(folder_frame, text="Select Output Folder...", command=self._select_output)
        self.output_button.grid(row=2, column=0, sticky="w", pady=4)
        ctk.CTkLabel(folder_frame, textvariable=self.output_dir, anchor="w").grid(row=2, column=1, sticky="ew", padx=10)

        # Sticker (NEW)
        # Sticker
        ctk.CTkButton(folder_frame, text="1. Select Sticker (Overlay)...", command=self._select_sticker, fg_color="#E07A5F", hover_color="#C0583E").grid(row=3, column=0, sticky="w", pady=4)
        ctk.CTkLabel(folder_frame, textvariable=self.sticker_path, anchor="w", text_color="#E07A5F").grid(row=3, column=1, sticky="ew", padx=10)

        # Reference (NEW)
        ctk.CTkButton(folder_frame, text="2. Select Object to Cover (Scan)...", command=self._select_reference, fg_color="#5F9EA0", hover_color="#4F8E90").grid(row=4, column=0, sticky="w", pady=4)
        ctk.CTkLabel(folder_frame, textvariable=self.reference_path, anchor="w", text_color="#5F9EA0").grid(row=4, column=1, sticky="ew", padx=10)


        # --- 1.5 Configuration Frame ---
        config_frame = ctk.CTkFrame(self, fg_color="transparent")
        config_frame.pack(fill="x", expand=True, pady=5)
        
        # Add Music Checkbox
        self.music_checkbox = ctk.CTkCheckBox(
            config_frame, 
            text="Add Music", 
            variable=self.add_music_var, 
            command=self._on_music_toggle
        )
        self.music_checkbox.pack(side="left", padx=5)

        # Save as Image Checkbox (NEW)
        self.image_mode_checkbox = ctk.CTkCheckBox(
            config_frame, 
            text="Save as Image (Sticker Only)", 
            variable=self.save_as_image_var, 
            command=self._on_image_mode_toggle
        )
        self.image_mode_checkbox.pack(side="left", padx=5)

        # B&W Filter Checkbox (NEW)
        self.bnw_checkbox = ctk.CTkCheckBox(
            config_frame,
            text="B&W Filter",
            variable=self.apply_bnw_var,
            command=self._on_bnw_toggle
        )
        self.bnw_checkbox.pack(side="left", padx=5)

        # Aspect Ratio Dropdown (NEW)
        ctk.CTkLabel(config_frame, text="Aspect Ratio:").pack(side="left", padx=5)
        self.aspect_ratio_combo = ctk.CTkComboBox(
            config_frame,
            variable=self.aspect_ratio_var,
            values=["Original", "9:16 (Reels)", "1:1 (Square)", "16:9 (Landscape)"],
            state="readonly",
            command=self._on_aspect_ratio_change,
            width=120
        )
        self.aspect_ratio_combo.pack(side="left", padx=5)

        # Duration Entry (Implicit requirement for toggle logic)
        ctk.CTkLabel(config_frame, text="Duration (s):").pack(side="left", padx=5)
        self.duration_entry = ctk.CTkEntry(config_frame, width=50)
        self.duration_entry.insert(0, str(self.settings.get("weaver_duration", 5)))
        self.duration_entry.pack(side="left", padx=5)

        # --- 3. Text Overlay Frame (NEW) ---
        text_frame = ctk.CTkFrame(self, fg_color="transparent")
        text_frame.pack(fill="x", expand=True, pady=5)
        
        # Enable Checkbox
        self.text_checkbox = ctk.CTkCheckBox(
            text_frame, 
            text="Add Random Text Overlay", 
            variable=self.text_enable_var, 
            command=self._on_text_toggle
        )
        self.text_checkbox.grid(row=0, column=0, sticky="w", padx=5, pady=2)
        
        # AI Generated Text Checkbox (NEW)
        self.ai_text_checkbox = ctk.CTkCheckBox(
            text_frame,
            text="Generate AI text overlay",
            variable=self.ai_text_enable_var,
            command=self._on_ai_text_toggle
        )
        self.ai_text_checkbox.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        
        # Text Content Entry
        self.text_entry = ctk.CTkEntry(text_frame, textvariable=self.text_content_var, placeholder_text="Enter text here...", width=200)
        self.text_entry.grid(row=0, column=2, sticky="w", padx=5)

        # Settings Row (Font, Size, Color, Opacity)
        settings_subframe = ctk.CTkFrame(text_frame, fg_color="transparent")
        settings_subframe.grid(row=1, column=0, columnspan=2, sticky="ew", pady=2)
        
        # Font Button
        self.font_btn = ctk.CTkButton(settings_subframe, text="Font (.ttf)...", width=80, command=self._select_font)
        self.font_btn.pack(side="left", padx=2)
        
        # Size
        ctk.CTkLabel(settings_subframe, text="Size:").pack(side="left", padx=2)
        self.size_entry = ctk.CTkEntry(settings_subframe, textvariable=self.text_size_var, width=40)
        self.size_entry.pack(side="left", padx=2)
        
        # Color
        ctk.CTkLabel(settings_subframe, text="Color:").pack(side="left", padx=2)
        self.color_entry = ctk.CTkEntry(settings_subframe, textvariable=self.text_color_var, width=60)
        self.color_entry.pack(side="left", padx=2)
        
        # Opacity
        ctk.CTkLabel(settings_subframe, text="Box Opacity (0-1):").pack(side="left", padx=2)
        self.opacity_entry = ctk.CTkEntry(settings_subframe, textvariable=self.text_opacity_var, width=40)
        self.opacity_entry.pack(side="left", padx=2)
        
        # Initial State Update
        self._on_text_toggle()

        # --- 2. Control & Progress Frame ---
        control_frame = ctk.CTkFrame(self, fg_color="transparent")
        control_frame.pack(fill="x", expand=True, pady=5)
        control_frame.columnconfigure(0, weight=1)
        control_frame.columnconfigure(1, weight=1)
        
        self.start_button = ctk.CTkButton(control_frame, text="Start Generation", command=self._start_processing)
        self.start_button.grid(row=0, column=0, sticky="ew", ipady=5, padx=2)
        
        self.cancel_button = ctk.CTkButton(control_frame, text="Cancel", command=self._cancel_processing, state="disabled", fg_color="gray")
        self.cancel_button.grid(row=0, column=1, sticky="ew", ipady=5, padx=2)

        self.progress_bar = ctk.CTkProgressBar(self, mode='determinate')
        self.progress_bar.set(0) # Set to 0%
        self.progress_bar.pack(fill="x", expand=True, pady=10)
        
        # --- 3. Log Window ---
        self.log_window = ctk.CTkTextbox(self, height=150, state="disabled")
        self.log_window.pack(fill="both", expand=True)
        
        self.log_window.tag_config('INFO', foreground='white')
        self.log_window.tag_config('ERROR', foreground='red')
        self.log_window.tag_config('SUCCESS', foreground='cyan')

    def _log_message(self, message: str, tag: str = 'INFO'):
        self.log_window.configure(state="normal")
        self.log_window.insert("end", f"{message}\n", (tag,))
        self.log_window.configure(state="disabled")
        self.log_window.see("end")

    def _select_photos(self):
        path = filedialog.askdirectory()
        if path: 
            self.photo_dir.set(path)
            self.settings["weaver_photo_dir"] = path
            settings.save_settings(self.settings) # <-- Save immediately

    def _select_music(self):
        path = filedialog.askdirectory()
        if path: 
            self.music_dir.set(path)
            self.settings["weaver_music_dir"] = path
            settings.save_settings(self.settings) # <-- Save immediately
            
    def _select_output(self):
        path = filedialog.askdirectory()
        if path: 
            self.output_dir.set(path)
            self.settings["weaver_output_dir"] = path
            settings.save_settings(self.settings) # <-- Save immediately

    def _select_sticker(self):
        """Allows user to pick a PNG/JPG sticker."""
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
        if path:
            self.sticker_path.set(path)
            self.settings["weaver_sticker_path"] = path
            self.settings["weaver_sticker_path"] = path
            settings.save_settings(self.settings)

    def _select_reference(self):
        """Pick the image of the object/watermark you want to HIDE."""
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg")])
        if path:
            self.reference_path.set(path)
            self.settings["weaver_reference_path"] = path
            settings.save_settings(self.settings)

    def _on_music_toggle(self):
        """Enable/Disable music features based on checkbox."""
        if self.add_music_var.get():
            self.music_button.configure(state="normal")
            self.settings["weaver_add_music"] = True
        else:
            self.music_button.configure(state="disabled")
            self.settings["weaver_add_music"] = False
        settings.save_settings(self.settings)

    def _on_bnw_toggle(self):
        """Saves the B&W preference."""
        self.settings["weaver_apply_bnw"] = self.apply_bnw_var.get()
        settings.save_settings(self.settings)

    def _on_image_mode_toggle(self):
        """Disables Music/Duration if we are only saving images."""
        is_image_mode = self.save_as_image_var.get()
        self.settings["weaver_save_as_image"] = is_image_mode
        settings.save_settings(self.settings)

        if is_image_mode:
            # If Image Mode is ON, force Music OFF and disable it
            self.add_music_var.set(False)
            self.music_checkbox.configure(state="disabled")
            self.music_button.configure(state="disabled")
            self.duration_entry.configure(state="disabled", fg_color="gray")
        else:
            # Restore controls
            self.music_checkbox.configure(state="normal")
            self._on_music_toggle() # Re-evaluate music state

    # ... (all other methods like _start_processing, _set_ui_state, etc. remain unchanged) ...
    def _on_aspect_ratio_change(self, choice: str):
        """Saves the aspect ratio choice."""
        self.settings["weaver_aspect_ratio"] = choice
        settings.save_settings(self.settings)

    def _on_ai_text_toggle(self):
        """Enable/Disable manual text entry based on AI text checkbox."""
        is_ai_enabled = self.ai_text_enable_var.get()
        self.settings["weaver_ai_text_enable"] = is_ai_enabled
        settings.save_settings(self.settings)
        
        # If AI text is enabled, disable manual entry
        if is_ai_enabled:
            self.text_entry.configure(state="disabled")
        else:
            if self.text_enable_var.get():
                self.text_entry.configure(state="normal")

    def _on_text_toggle(self):
        """Enable/Disable text widgets."""
        is_text_enabled = self.text_enable_var.get()
        state = "normal" if is_text_enabled else "disabled"
        
        self.ai_text_checkbox.configure(state=state)
        self.font_btn.configure(state=state)
        self.size_entry.configure(state=state)
        self.color_entry.configure(state=state)
        self.opacity_entry.configure(state=state)
        
        # Text entry state depends on both Enable Text AND AI Text
        if is_text_enabled:
            if self.ai_text_enable_var.get():
                self.text_entry.configure(state="disabled")
            else:
                self.text_entry.configure(state="normal")
        else:
            self.text_entry.configure(state="disabled")
        
        # Save setting
        self.settings["weaver_text_enable"] = is_text_enabled
        settings.save_settings(self.settings)

    def _select_font(self):
        path = filedialog.askopenfilename(filetypes=[("Font Files", "*.ttf *.otf")])
        if path:
            self.text_font_path.set(path)
            self.settings["weaver_text_font"] = path
            settings.save_settings(self.settings)

    def _start_processing(self):
        photo_path = Path(self.photo_dir.get())
        music_path = Path(self.music_dir.get())
        output_path = Path(self.output_dir.get())
        
        if not (photo_path.is_dir() and output_path.is_dir()):
            messagebox.showerror("Error", "Please select valid Input and Output folders.")
            return

        # CHANGED: Use SUPPORTED_MEDIA_FORMATS to find both images and videos
        from utils import SUPPORTED_MEDIA_FORMATS
        media_files = find_files(photo_path, SUPPORTED_MEDIA_FORMATS)
        
        if not media_files:
            messagebox.showerror("Error", "No supported images or videos found.")
            return
        
        music = []
        if self.add_music_var.get():
             music = find_files(music_path, SUPPORTED_AUDIO_FORMATS)
             if not music:
                 messagebox.showerror("Error", f"No supported music files found in:\n{music_path}")
                 return
            
        self._set_ui_state(processing=True)
        self._log_message("Scanning complete. Starting processor thread...", "INFO")

        # Validate Sticker (Add this before starting thread)
        sticker_file = self.sticker_path.get()
        final_sticker_path = None
        if sticker_file and Path(sticker_file).exists():
            final_sticker_path = Path(sticker_file)

        # Validate Reference (Optional)
        ref_file = self.reference_path.get()
        final_ref_path = Path(ref_file) if ref_file and os.path.exists(ref_file) else None
        
        try:
            manual_duration = float(self.duration_entry.get())
            self.settings["weaver_duration"] = manual_duration
            
            # Save Text Settings before starting
            self.settings["weaver_text_content"] = self.text_content_var.get()
            self.settings["weaver_text_size"] = self.text_size_var.get()
            self.settings["weaver_text_color"] = self.text_color_var.get()
            self.settings["weaver_text_opacity"] = self.text_opacity_var.get()
            
            settings.save_settings(self.settings)
        except ValueError:
            manual_duration = 5

        self.worker_thread = VideoProcessor(
            media_list=media_files,   # <-- Renamed arg
            music_list=music,
            output_dir=output_path, 
            message_queue=self.message_queue,
            add_music=self.add_music_var.get(),
            manual_duration=manual_duration,
            sticker_path=final_sticker_path,
            reference_path=final_ref_path,
            save_as_image=self.save_as_image_var.get(),
            apply_bnw=self.apply_bnw_var.get(),
            # NEW TEXT ARGS
            text_enable=self.text_enable_var.get(),
            text_content=self.text_content_var.get(),
            text_font=self.text_font_path.get(),
            text_size=self.text_size_var.get(),
            text_color=self.text_color_var.get(),
            text_opacity=self.text_opacity_var.get(),
            aspect_ratio=self.aspect_ratio_var.get(),
            ai_text_enable=self.ai_text_enable_var.get(),
            ai_prompt=self.settings.get("weaver_ai_prompt", "")
        )
        self.worker_thread.start()

    def _cancel_processing(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.stop()
            self.cancel_button.configure(state="disabled")
            self.processing_active = False 

    def _set_ui_state(self, processing: bool):
        self.processing_active = processing
        start_state = "disabled" if processing else "normal"
        cancel_state = "normal" if processing else "disabled"
        
        self.start_button.configure(state=start_state)
        self.cancel_button.configure(state=cancel_state)
        self.photo_button.configure(state=start_state)
        self.music_button.configure(state=start_state)
        self.output_button.configure(state=start_state)


    def _start_queue_monitor(self):
        self.after(100, self._process_queue)

    def _process_queue(self):
        try:
            while not self.message_queue.empty():
                message = self.message_queue.get_nowait()
                msg_type = message.get('type')
                
                if msg_type == 'log':
                    self._log_message(message.get('message', ''), 'INFO')
                elif msg_type == 'error':
                    self._log_message(message.get('message', 'Unknown error'), 'ERROR')
                elif msg_type == 'progress':
                    current = message.get('current', 0); total = message.get('total', 1)
                    self.progress_bar.set(current / total)
                elif msg_type == 'complete':
                    if self.processing_active:
                        self._log_message(message.get('message', 'Done!'), 'SUCCESS')
                        self.progress_bar.set(1)
                        messagebox.showinfo("Success", "All videos have been generated!")
                    
                    self.worker_thread = None
                    self.progress_bar.set(0)
                    self._set_ui_state(processing=False)
        finally:
            self.after(100, self._process_queue)