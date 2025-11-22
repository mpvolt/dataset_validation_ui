"""
Content panel - manages the three-panel layout
"""
import tkinter as tk
from tkinter import ttk
from gui.object_panel import ObjectPanel
from gui.results_panel import ResultsPanel

class ContentPanel:
    def __init__(self, parent, state):
        self.parent = parent
        self.state = state
        self._create_ui()
    
    def _create_ui(self):
        # Main content container
        content_container = tk.Frame(self.parent, bg="#f8f9fa")
        content_container.pack(fill="both", expand=True, padx=15, pady=(5, 15))
        
        # Horizontal PanedWindow for three-panel layout
        self.content_paned = ttk.PanedWindow(content_container, orient=tk.HORIZONTAL)
        self.content_paned.pack(fill="both", expand=True)
        
        # Left panel - Object list and viewer
        self.object_panel = ObjectPanel(self.content_paned, self.state)
        
        # Right panel - Results
        self.results_panel = ResultsPanel(self.content_paned, self.state)