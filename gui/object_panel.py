"""
Object panel - displays object list and content viewer
"""
import json
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from utils.url_helpers import add_clickable_urls

class ObjectPanel:
    def __init__(self, parent_paned, state):
        self.parent_paned = parent_paned
        self.state = state
        self._create_ui()
    
    def _create_ui(self):
        # Left card - Object list
        left_card = tk.Frame(self.parent_paned, bg="#ffffff", relief="solid", bd=1)
        self.parent_paned.add(left_card, weight=1)
        
        left_header = tk.Frame(left_card, bg="#e9ecef", relief="flat")
        left_header.pack(fill="x")
        tk.Label(
            left_header, 
            text="📋 JSON Objects", 
            bg="#e9ecef", 
            fg="#495057", 
            font=("Arial", 10, "bold"), 
            anchor="w"
        ).pack(side="left", padx=10, pady=8)
        
        self.object_list = ttk.Treeview(left_card, columns=("Object",), show="headings")
        self.object_list.heading("Object", text="Objects")
        self.object_list.column("Object", width=280)
        self.object_list.pack(fill="both", expand=True, padx=1, pady=1)
        self.object_list.bind("<<TreeviewSelect>>", self._on_object_select)
        
        # Middle card - Object contents
        middle_card = tk.Frame(self.parent_paned, bg="#ffffff", relief="solid", bd=1)
        self.parent_paned.add(middle_card, weight=2)
        
        middle_header = tk.Frame(middle_card, bg="#e9ecef", relief="flat")
        middle_header.pack(fill="x")
        tk.Label(
            middle_header, 
            text="📝 Object Contents", 
            bg="#e9ecef", 
            fg="#495057", 
            font=("Arial", 10, "bold"), 
            anchor="w"
        ).pack(side="left", padx=10, pady=8)
        
        # Add editing buttons
        btn_frame = tk.Frame(middle_header, bg="#e9ecef")
        btn_frame.pack(side="right", padx=10)
        
        self.text_view = scrolledtext.ScrolledText(
            middle_card, 
            wrap="none", 
            bg="#ffffff", 
            fg="#212529", 
            relief="flat", 
            font=("Consolas", 9), 
            insertbackground="#212529"
        )
        self.text_view.tag_config("highlight", background="#fff3cd")
        self.text_view.pack(fill="both", expand=True, padx=1, pady=1)
        self.text_view.bind("<Delete>", self._delete_selection)
        
        # Store in state
        self.state['object_list'] = self.object_list
        self.state['text_view'] = self.text_view
    
    def _on_object_select(self, event):
        """Handle object selection"""
        selected = self.object_list.selection()
        if not selected:
            return
        
        idx = int(selected[0])
        obj = self.state['loaded_objects'][idx]
        
        self.text_view.delete("1.0", tk.END)
        pretty = json.dumps(obj, indent=4, ensure_ascii=False)
        self.text_view.insert(tk.END, pretty)
        self.text_view.tag_remove("highlight", "1.0", tk.END)
        
        add_clickable_urls(self.text_view, pretty)
    
    def _highlight_selection(self):
        """Highlight selected text"""
        try:
            start = self.text_view.index("sel.first")
            end = self.text_view.index("sel.last")
            self.text_view.tag_add("highlight", start, end)
        except tk.TclError:
            pass
    
    def _delete_selection(self, event=None):
        """Delete selected text"""
        try:
            start = self.text_view.index("sel.first")
            end = self.text_view.index("sel.last")
            self.text_view.delete(start, end)
            return "break"
        except tk.TclError:
            return
    
    def _move_url(self):
        """Move URL from source_code_url to fix_commit_url"""
        selected = self.object_list.selection()
        if not selected:
            messagebox.showerror("Error", "Select an object first.")
            return
        
        idx = int(selected[0])
        obj = self.state['loaded_objects'][idx]
        
        # Get highlighted text
        try:
            start = self.text_view.index("sel.first")
            end = self.text_view.index("sel.last")
            selected_text = self.text_view.get(start, end).strip()
        except tk.TclError:
            messagebox.showerror("Error", "Highlight the URL you want to move.")
            return
        
        if not selected_text:
            messagebox.showerror("Error", "You must highlight part of a URL.")
            return
        
        # Validate fields
        if "source_code_url" not in obj or not isinstance(obj["source_code_url"], list):
            messagebox.showerror("Error", "source_code_url must be a list.")
            return
        
        if "fix_commit_url" not in obj or not isinstance(obj.get("fix_commit_url", []), list):
            obj["fix_commit_url"] = []
        
        # Find matching URL
        matching_urls = [url for url in obj["source_code_url"] if selected_text in url]
        
        if not matching_urls:
            messagebox.showerror("Error", "No URL in source_code_url contains the highlighted text.")
            return
        
        if len(matching_urls) > 1:
            messagebox.showerror("Error", "Selected text appears in multiple URLs. Highlight more text.")
            return
        
        # Move URL
        url_to_move = matching_urls[0]
        obj["source_code_url"].remove(url_to_move)
        obj["fix_commit_url"].append(url_to_move)
        
        # Refresh display
        pretty = json.dumps(obj, indent=4, ensure_ascii=False)
        self.text_view.delete("1.0", tk.END)
        self.text_view.insert(tk.END, pretty)
        add_clickable_urls(self.text_view, pretty)