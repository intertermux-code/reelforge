"""
ReelForge Main Application
Initializes the CustomTkinter root and the tabbed interface.
"""
import customtkinter as ctk
from weaver_tab import WeaverTab
from extractor_tab import ExtractorTab
import settings  # <-- Import our settings module
import logging   # <-- Import logging

log = logging.getLogger(__name__)

class ReelForgeApp(ctk.CTk):
    """
    Main application class. Hosts the CTkTabview.
    """
    def __init__(self):
        super().__init__()
        log.info("ReelForgeApp initializing...")
        
        # 1. Load settings on start
        self.settings = settings.load_settings()

        # 2. Apply global settings
        ctk.set_appearance_mode(self.settings.get("theme", "dark"))
        ctk.set_default_color_theme("blue")
        
        self.title("ReelForge")
        self.geometry(self.settings.get("geometry", "750x600"))

        # Create the main tab controller
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.pack(fill="both", expand=True, padx=10, pady=10)
        self.tab_view.add("🖼️ Photo Weaver")
        self.tab_view.add("🎙️ Audio Extractor")
        
        # 3. Pass settings object to each tab
        self.weaver_frame = WeaverTab(
            self.tab_view.tab("🖼️ Photo Weaver"), 
            self.settings  # <-- This is the fix
        )
        self.weaver_frame.pack(fill="both", expand=True)
        
        self.extractor_frame = ExtractorTab(
            self.tab_view.tab("🎙️ Audio Extractor"),
            self.settings  # <-- This is the fix
        )
        self.extractor_frame.pack(fill="both", expand=True)

        # 4. Bind the save_on_close function
        self.protocol("WM_DELETE_WINDOW", self.save_on_close)
        log.info("ReelForgeApp initialized successfully.")

    def save_on_close(self):
        """
        Saves the current window geometry and then quits.
        """
        self.settings["geometry"] = self.geometry()
        self.settings["theme"] = ctk.get_appearance_mode()
        log.info("Saving settings and closing application.")
        settings.save_settings(self.settings)
        self.destroy() 

if __name__ == "__main__":
    app = ReelForgeApp()
    app.mainloop()