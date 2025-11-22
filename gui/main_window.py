"""
Main window and UI layout
"""
import tkinter as tk
from tkinter import ttk
from gui.top_bar import TopBar
from gui.file_list import FileList
from gui.content_panel import ContentPanel

class MainWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("JSON Explorer + Editor")
        self.root.geometry("1800x900")
        
        # Configure style
        style = ttk.Style()
        style.theme_use('clam')
        
        # Shared state
        self.state = {
            'folder_var': tk.StringVar(),
            'current_file_path': None,
            'loaded_objects': [],
            'original_loaded_objects': [],
            'ranked_commits': [],
            'ranked_commits_cache': {},
            'filtered_results': {}
        }
        
        # Create UI components
        self.top_bar = TopBar(self.root, self.state)
        self.file_list = FileList(self.root, self.state)
        self.content_panel = ContentPanel(self.root, self.state)