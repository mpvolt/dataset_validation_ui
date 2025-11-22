"""
Top toolbar with buttons and folder path
"""
import tkinter as tk
from core.file_operations import pick_folder, save_file
from core.commit_operations import run_get_commit_data, fix_finding
from core.object_operations import reset_selected_object

class TopBar:
    def __init__(self, root, state):
        self.root = root
        self.state = state
        
        self.bar = tk.Frame(root, bg="#f8f9fa", relief="raised", bd=1)
        self.bar.pack(fill="x", padx=0, pady=0)
        
        self._create_file_operations()
        self._create_analysis_operations()
        self._create_reset_button()
        self._create_path_display()
    
    def _create_file_operations(self):
        file_ops_frame = tk.Frame(self.bar, bg="#f8f9fa")
        file_ops_frame.pack(side="left", padx=10, pady=8)
        
        tk.Button(
            file_ops_frame, 
            text="📁 Open Folder", 
            command=lambda: pick_folder(self.state),
            bg="#ffffff",
            fg="#212529",
            activebackground="#e9ecef",
            activeforeground="#212529",
            relief="flat",
            bd=1,
            padx=12, 
            pady=6,
            font=("Arial", 9)
        ).pack(side="left", padx=2)
        
        tk.Button(
            file_ops_frame,
            text="💾 Save File",
            command=lambda: save_file(self.state),
            bg="#ffffff",
            fg="#212529",
            activebackground="#c82333",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=12, 
            pady=6,
            font=("Arial", 9, "bold")
        ).pack(side="left", padx=2)
    
    def _create_analysis_operations(self):
        analysis_ops_frame = tk.Frame(self.bar, bg="#f8f9fa")
        analysis_ops_frame.pack(side="left", padx=5, pady=8)
        
        tk.Button(
            analysis_ops_frame,
            text="🔍 Get Commit Data",
            command=lambda: run_get_commit_data(self.state, self.root),
            bg="#ffffff",
            fg="#212529",
            activebackground="#e9ecef",
            activeforeground="#212529",
            relief="flat",
            bd=0,
            padx=12, 
            pady=6,
            font=("Arial", 9, "bold")
        ).pack(side="left", padx=2)
        
        tk.Button(
            analysis_ops_frame,
            text="✅ Fix Finding",
            command=lambda: fix_finding(self.state),
            bg="#ffffff",
            fg="#212529",
            activebackground="#e9ecef",
            activeforeground="#212529",
            relief="flat",
            bd=0,
            padx=12, 
            pady=6,
            font=("Arial", 9, "bold")
        ).pack(side="left", padx=2)
    
    def _create_reset_button(self):
        tk.Button(
            self.bar,
            text="Reset Finding",
            command=lambda: reset_selected_object(self.state),
            bg="#ffc107",
            fg="black",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=5
        ).pack(side="left", padx=5)
    
    def _create_path_display(self):
        path_frame = tk.Frame(self.bar, bg="#f8f9fa")
        path_frame.pack(side="right", padx=15, pady=8)
        
        tk.Label(path_frame, text="📂", bg="#f8f9fa", font=("Arial", 10)).pack(side="left")
        tk.Label(
            path_frame, 
            textvariable=self.state['folder_var'], 
            bg="#f8f9fa", 
            fg="#6c757d", 
            font=("Arial", 9)
        ).pack(side="left", padx=5)