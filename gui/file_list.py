"""
File list component - displays JSON files from selected folder
"""
import tkinter as tk
from tkinter import ttk
from core.file_operations import load_json_objects

class FileList:
    def __init__(self, parent, state):
        self.parent = parent
        self.state = state
        self._create_ui()
    
    def _create_ui(self):
        # Container
        file_list_container = tk.Frame(self.parent, bg="#ffffff")
        file_list_container.pack(fill="x", padx=15, pady=(10, 5))
        
        # Header
        file_header = tk.Frame(file_list_container, bg="#e9ecef", relief="flat")
        file_header.pack(fill="x")
        tk.Label(
            file_header, 
            text="📄 JSON Files", 
            bg="#e9ecef", 
            fg="#495057", 
            font=("Arial", 10, "bold"), 
            anchor="w"
        ).pack(side="left", padx=10, pady=5)
        
        # Tree frame
        tree_frame = tk.Frame(file_list_container, bg="#ffffff", relief="solid", bd=1)
        tree_frame.pack(fill="x", padx=0, pady=0)
        
        # Scrollbar
        file_tree_scroll = ttk.Scrollbar(tree_frame, orient="horizontal")
        
        # Treeview
        self.file_tree = ttk.Treeview(
            tree_frame, 
            columns=("Relative", "Full"), 
            show="headings", 
            height=6, 
            xscrollcommand=file_tree_scroll.set
        )
        self.file_tree.heading("Relative", text="File Name")
        self.file_tree.heading("Full", text="Full Path")
        self.file_tree.column("Relative", width=400)
        self.file_tree.column("Full", width=800)
        self.file_tree.pack(fill="x", padx=1, pady=1)
        
        file_tree_scroll.config(command=self.file_tree.xview)
        file_tree_scroll.pack(fill="x")
        
        # Bind selection event
        self.file_tree.bind("<<TreeviewSelect>>", self._on_file_select)
        
        # Store in state for access by other components
        self.state['file_tree'] = self.file_tree
    
    def _on_file_select(self, event):
        """Handle file selection"""
        selected = self.file_tree.selection()
        if not selected:
            return
        
        _, full_path = self.file_tree.item(selected[0], "values")
        self.state['current_file_path'] = full_path
        load_json_objects(full_path, self.state)