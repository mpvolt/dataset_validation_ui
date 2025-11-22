"""
Results panel - displays ranked commits and filtering options
"""
import json
import tkinter as tk
from tkinter import ttk, scrolledtext
from gui.filter_widgets import FilterWidgets
from utils.url_helpers import add_clickable_urls

class ResultsPanel:
    def __init__(self, parent_paned, state):
        self.parent_paned = parent_paned
        self.state = state
        self._create_ui()
    
    def _create_ui(self):
        # Right card - Ranked commits
        right_card = tk.Frame(self.parent_paned, bg="#ffffff", relief="solid", bd=1)
        self.parent_paned.add(right_card, weight=2)
        
        right_header = tk.Frame(right_card, bg="#e9ecef", relief="flat")
        right_header.pack(fill="x")
        tk.Label(
            right_header, 
            text="🎯 Ranked Commits", 
            bg="#e9ecef", 
            fg="#495057", 
            font=("Arial", 10, "bold"), 
            anchor="w"
        ).pack(side="left", padx=10, pady=8)
        
        # Vertical PanedWindow for resizable sections
        results_paned = ttk.PanedWindow(right_card, orient=tk.VERTICAL)
        results_paned.pack(fill="both", expand=True, padx=1, pady=1)
        
        # Results list
        results_list_container = tk.Frame(results_paned, bg="#ffffff")
        results_paned.add(results_list_container, weight=1)
        
        self.results_list = ttk.Treeview(results_list_container, columns=("Result",), show="headings")
        self.results_list.heading("Result", text="Commits (click to view details)")
        self.results_list.column("Result", width=380)
        self.results_list.pack(fill="both", expand=True, padx=2, pady=2)
        self.results_list.bind("<<TreeviewSelect>>", self._on_result_select)
        
        # Filter widgets (files, functions before/after)
        self.filter_widgets = FilterWidgets(results_paned, self.state)
        
        # Results text view
        results_text_container = tk.Frame(results_paned, bg="#ffffff", relief="solid", bd=1)
        results_paned.add(results_text_container, weight=2)
        
        results_text_header = tk.Frame(results_text_container, bg="#e9ecef")
        results_text_header.pack(fill="x")
        tk.Label(
            results_text_header, 
            text="📄 Commit Details", 
            bg="#e9ecef", 
            fg="#495057", 
            font=("Arial", 9, "bold")
        ).pack(side="left", padx=8, pady=6)
        
        self.results_text = scrolledtext.ScrolledText(
            results_text_container, 
            wrap="word", 
            bg="#ffffff", 
            fg="#212529", 
            relief="flat", 
            font=("Consolas", 9), 
            insertbackground="#212529"
        )
        self.results_text.pack(fill="both", expand=True, padx=2, pady=2)
        
        # Store in state
        self.state['results_list'] = self.results_list
        self.state['results_text'] = self.results_text
    
    def _on_result_select(self, event):
        """Handle result selection"""
        selected = self.results_list.selection()
        if not selected:
            return
        
        idx = int(selected[0])
        
        # Restore from cache if switching to a different commit
        if idx in self.state['ranked_commits_cache']:
            self.state['ranked_commits'][idx] = json.loads(
                json.dumps(self.state['ranked_commits_cache'][idx])
            )
        else:
            # First time selecting - cache it
            self.state['ranked_commits_cache'][idx] = json.loads(
                json.dumps(self.state['ranked_commits'][idx])
            )
        
        commit_obj = self.state['ranked_commits'][idx]
        
        # Clear search boxes
        for key in ['files_search_var', 'functions_before_search_var', 'functions_after_search_var']:
            var = self.state.get(key)
            if var:
                var.set("")
        
        # Update filter widgets
        self.filter_widgets.populate_from_commit(commit_obj)
        
        # Update results text
        self.results_text.delete("1.0", tk.END)
        pretty = json.dumps(commit_obj, indent=4, ensure_ascii=False)
        self.results_text.insert(tk.END, pretty)
        add_clickable_urls(self.results_text, pretty)