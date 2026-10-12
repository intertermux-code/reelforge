"""
ExtractorTab: The UI and logic for the Video-to-Audio tool.
"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
import queue
from pathlib import Path

from utils import find_files, SUPPORTED_VIDEO_FORMATS
from processor import AudioExtractor
import settings # <-- Import settings

class ExtractorTab(ctk.CTkFrame):
    """
    Houses all widgets and logic for the Audio Extractor.
    """
    def __init__(self, parent, settings_obj: dict): # <-- Accept settings
        super().__init__(parent, fg_color="transparent")
        
        self.settings = settings_obj # <-- Store settings
        
        # Data storage
        # Load values from settings
        self.video_dir = ctk.StringVar(value=self.settings.get("extractor_video_dir", ""))
        self.output_dir = ctk.StringVar(value=self.settings.get("extractor_output_dir", ""))
        self.audio_format = ctk.StringVar(value=self.settings.get("extractor_audio_format", "mp3"))
        
        # Worker thread management
        self.message_queue = queue.Queue()
        self.worker_thread = None
        self.processing_active = False

        self._create_widgets()
        self._start_queue_monitor()

    def _create_widgets(self):
        """Lays out all the GUI components."""
        # --- 1. Folder Selection Frame ---
        folder_frame = ctk.CTkFrame(self, fg_color="transparent")
        folder_frame.pack(fill="x", expand=True, pady=5)
        folder_frame.columnconfigure(1, weight=1)
        
        self.video_button = ctk.CTkButton(folder_frame, text="Select Videos Folder...", command=self._select_videos)
        self.video_button.grid(row=0, column=0, sticky="w", pady=4)
        ctk.CTkLabel(folder_frame, textvariable=self.video_dir, anchor="w").grid(row=0, column=1, sticky="ew", padx=10)
        
        self.output_button = ctk.CTkButton(folder_frame, text="Select Output Folder...", command=self._select_output)
        self.output_button.grid(row=1, column=0, sticky="w", pady=4)
        ctk.CTkLabel(folder_frame, textvariable=self.output_dir, anchor="w").grid(row=1, column=1, sticky="ew", padx=10)

        # --- 2. Configuration Frame ---
        config_frame = ctk.CTkFrame(self, fg_color="transparent")
        config_frame.pack(fill="x", expand=True, pady=5)
        
        ctk.CTkLabel(config_frame, text="Output Format:").pack(side="left")
        self.format_combo = ctk.CTkComboBox(
            config_frame, 
            variable=self.audio_format, 
            values=['mp3', 'wav', 'aac'],
            state="readonly",
            command=self._on_format_change # <-- Add save callback
        )
        self.format_combo.pack(side="left", padx=5)

        # --- 3. Control & Progress Frame ---
        control_frame = ctk.CTkFrame(self, fg_color="transparent")
        control_frame.pack(fill="x", expand=True, pady=5)
        control_frame.columnconfigure(0, weight=1)
        control_frame.columnconfigure(1, weight=1)
        
        self.start_button = ctk.CTkButton(control_frame, text="Start Extraction", command=self._start_processing)
        self.start_button.grid(row=0, column=0, sticky="ew", ipady=5, padx=2)

        self.cancel_button = ctk.CTkButton(control_frame, text="Cancel", command=self._cancel_processing, state="disabled", fg_color="gray")
        self.cancel_button.grid(row=0, column=1, sticky="ew", ipady=5, padx=2)

        self.progress_bar = ctk.CTkProgressBar(self, mode='determinate')
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", expand=True, pady=10)
        
        # --- 4. Log Window ---
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

    def _select_videos(self):
        path = filedialog.askdirectory()
        if path: 
            self.video_dir.set(path)
            self.settings["extractor_video_dir"] = path
            settings.save_settings(self.settings) # <-- Save immediately
            
    def _select_output(self):
        path = filedialog.askdirectory()
        if path: 
            self.output_dir.set(path)
            self.settings["extractor_output_dir"] = path
            settings.save_settings(self.settings) # <-- Save immediately
            
    def _on_format_change(self, choice: str):
        """Called when the combobox value changes."""
        self.settings["extractor_audio_format"] = choice
        settings.save_settings(self.settings) # <-- Save immediately

    # ... (all other methods like _start_processing, _set_ui_state, etc. remain unchanged) ...
    def _start_processing(self):
        video_path = Path(self.video_dir.get())
        output_path = Path(self.output_dir.get())
        
        if not (video_path.is_dir() and output_path.is_dir()):
            messagebox.showerror("Error", "Please select valid Video and Output folders.")
            return

        videos = find_files(video_path, SUPPORTED_VIDEO_FORMATS)
        if not videos:
            messagebox.showerror("Error", f"No supported videos found in:\n{video_path}")
            return
            
        self._set_ui_state(processing=True)
        self._log_message("Scanning complete. Starting extractor thread...", "INFO")
        
        self.worker_thread = AudioExtractor(
            video_list=videos,
            output_dir=output_path,
            audio_format=self.audio_format.get(),
            message_queue=self.message_queue
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
        self.video_button.configure(state=start_state)
        self.output_button.configure(state=start_state)
        self.format_combo.configure(state=start_state)

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
                        messagebox.showinfo("Success", "All audio has been extracted!")
                    
                    self.worker_thread = None
                    self.progress_bar.set(0)
                    self._set_ui_state(processing=False)
        finally:
            self.after(100, self._process_queue)