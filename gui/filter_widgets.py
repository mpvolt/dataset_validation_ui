"""
Filter widgets - file and function filtering UI
"""
import tkinter as tk
from tkinter import ttk
from utils.ui_helpers import filter_tree, select_all_items
from core.filter_operations import apply_selections
from core.object_operations import add_function_to_context

class FilterWidgets:
    def __init__(self, parent_paned, state):
        self.parent_paned = parent_paned
        self.state = state
        #self._create_ui()
    
    def _create_ui(self):
        # Files section
        self._create_files_section()
        
        # Combined Functions Before + After
        self._create_functions_sections()
    
    def _create_files_section(self):
        """Create files filter section"""
        files_container = tk.Frame(self.parent_paned, bg="#f8f9fa", relief="solid", bd=1)
        self.parent_paned.add(files_container, weight=1)
        
        files_header = tk.Frame(files_container, bg="#ffffff")
        files_header.pack(fill="x", padx=1, pady=1)
        
        tk.Label(
            files_header, 
            text="📁 Files", 
            bg="#ffffff", 
            fg="#495057", 
            font=("Arial", 9, "bold")
        ).pack(side="left", padx=8, pady=6)
        
        files_btn_frame = tk.Frame(files_header, bg="#ffffff")
        files_btn_frame.pack(side="right", padx=8, pady=4)
        
        tk.Button(
            files_btn_frame,
            text="Select All",
            command=lambda: select_all_items(self.files_checklist),
            bg="#e9ecef",
            fg="#212529",
            activebackground="#dee2e6",
            activeforeground="#212529",
            relief="flat",
            bd=0,
            padx=8,
            pady=4,
            font=("Arial", 8)
        ).pack(side="left", padx=2)
        
        tk.Button(
            files_btn_frame,
            text="Apply Selections",
            command=lambda: apply_selections(self.state),
            bg="#28a745",
            fg="white",
            activebackground="#218838",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=8,
            pady=4,
            font=("Arial", 8, "bold")
        ).pack(side="left", padx=2)
        
        self.files_search_var = tk.StringVar()
        self.files_search_var.trace("w", self._on_files_search)
        files_search_entry = tk.Entry(
            files_container, 
            textvariable=self.files_search_var, 
            bg="#ffffff", 
            fg="#212529", 
            relief="solid", 
            bd=1, 
            font=("Arial", 9), 
            insertbackground="#212529"
        )
        files_search_entry.pack(fill="x", padx=6, pady=(0, 4))
        
        self.files_checklist = ttk.Treeview(
            files_container, 
            columns=("File",), 
            show="headings", 
            selectmode="extended"
        )
        self.files_checklist.heading("File", text="Double-click to select files")
        self.files_checklist.column("File", width=380)
        self.files_checklist.pack(fill="both", expand=True, padx=2, pady=2)
        self.files_checklist.bind("<Double-Button-1>", self._on_file_double_click)
        
        # Store in state
        self.state['files_checklist'] = self.files_checklist
        self.state['files_search_var'] = self.files_search_var
    
    def _create_functions_sections(self):
        """Create functions before/after sections"""
        functions_combined = tk.PanedWindow(self.parent_paned, orient="horizontal")
        self.parent_paned.add(functions_combined, weight=2)
        
        # Functions Before
        self._create_function_list(
            functions_combined,
            "⚙️ Functions Before",
            "functions_before_list",
            "functions_before_search_var",
            self._on_functions_before_search,
            self._on_function_before_double_click
        )
        
        # Functions After
        self._create_function_list(
            functions_combined,
            "⚙️ Functions After",
            "functions_after_list",
            "functions_after_search_var",
            self._on_functions_after_search,
            self._on_function_after_double_click
        )
    
    def _create_function_list(self, parent, title, list_key, search_var_key, search_callback, double_click_callback):
        """Helper to create a function list widget"""
        container = tk.Frame(parent, bg="#f8f9fa", relief="solid", bd=1)
        parent.add(container, stretch="always")
        
        # Header
        header = tk.Frame(container, bg="#ffffff")
        header.pack(fill="x", padx=1, pady=1)
        
        tk.Label(
            header,
            text=title,
            bg="#ffffff",
            fg="#495057",
            font=("Arial", 9, "bold")
        ).pack(side="left", padx=8, pady=6)
        
        # Buttons
        btn_frame = tk.Frame(header, bg="#ffffff")
        btn_frame.pack(side="right", padx=8, pady=4)
        
        widget_ref = [None]  # Use list to capture widget reference
        
        tk.Button(
            btn_frame,
            text="Select All",
            command=lambda: select_all_items(widget_ref[0]) if widget_ref[0] else None,
            bg="#e9ecef",
            fg="#212529",
            activebackground="#dee2e6",
            activeforeground="#212529",
            relief="flat",
            bd=0,
            padx=8,
            pady=4,
            font=("Arial", 8)
        ).pack(side="left", padx=2)
        
        # Search bar
        search_var = tk.StringVar()
        search_var.trace("w", search_callback)
        search_entry = tk.Entry(
            container,
            textvariable=search_var,
            bg="#ffffff",
            fg="#212529",
            relief="solid",
            bd=1,
            font=("Arial", 9),
            insertbackground="#212529"
        )
        search_entry.pack(fill="x", padx=6, pady=(0, 4))
        
        # Treeview
        func_list = ttk.Treeview(
            container,
            columns=("Function",),
            show="headings",
            selectmode="extended"
        )
        func_list.heading("Function", text="Double-click to select functions")
        func_list.column("Function", width=380)
        func_list.pack(fill="both", expand=True, padx=2, pady=2)
        func_list.bind("<Double-Button-1>", double_click_callback)
        
        widget_ref[0] = func_list
        
        # Store in state
        self.state[list_key] = func_list
        self.state[search_var_key] = search_var
    
    def populate_from_commit(self, commit_obj):
        """Populate filter widgets from a single commit object."""

        if not isinstance(commit_obj, dict):
            return

        # --- Populate Files ---
        file_tree = self.state.get('files_checklist')
        if file_tree:
            file_tree.delete(*file_tree.get_children())
            for f in commit_obj.get("files", []):
                file_tree.insert("", "end", values=(f,))

        # --- Populate Functions Before ---
        before_tree = self.state.get('functions_before_list')
        if before_tree:
            before_tree.delete(*before_tree.get_children())
            for fn in commit_obj.get("functions_before", []):
                before_tree.insert("", "end", values=(fn,))

        # --- Populate Functions After ---
        after_tree = self.state.get('functions_after_list')
        if after_tree:
            after_tree.delete(*after_tree.get_children())
            for fn in commit_obj.get("functions_after", []):
                after_tree.insert("", "end", values=(fn,))


    
    def _on_files_search(self, *args):
        """Search files list"""
        results_list = self.state.get('results_list')
        if not results_list:
            return
        
        result_selected = results_list.selection()
        if not result_selected:
            return
        
        idx = int(result_selected[0])
        commit_obj = self.state['ranked_commits'][idx]
        
        search_text = self.files_search_var.get()
        all_files = commit_obj.get("files", [])
        filter_tree(self.files_checklist, search_text, all_files)
    
    def _on_functions_before_search(self, *args):
        """Search functions_before list"""
        results_list = self.state.get('results_list')
        if not results_list:
            return
        
        result_selected = results_list.selection()
        if not result_selected:
            return
        
        idx = int(result_selected[0])
        commit_obj = self.state['ranked_commits'][idx]
        
        search_var = self.state.get('functions_before_search_var')
        if not search_var:
            return
        
        search_text = search_var.get()
        all_functions = commit_obj.get("functions_before", [])
        functions_before_list = self.state.get('functions_before_list')
        if functions_before_list:
            filter_tree(functions_before_list, search_text, all_functions)
    
    def _on_functions_after_search(self, *args):
        """Search functions_after list"""
        results_list = self.state.get('results_list')
        if not results_list:
            return
        
        result_selected = results_list.selection()
        if not result_selected:
            return
        
        idx = int(result_selected[0])
        commit_obj = self.state['ranked_commits'][idx]
        
        search_var = self.state.get('functions_after_search_var')
        if not search_var:
            return
        
        search_text = search_var.get()
        all_functions = commit_obj.get("functions_after", [])
        functions_after_list = self.state.get('functions_after_list')
        if functions_after_list:
            filter_tree(functions_after_list, search_text, all_functions)
    
    def _on_file_double_click(self, event):
        """Double-click a file to keep only that file"""
        item = self.files_checklist.identify_row(event.y)
        if not item:
            return
        
        results_list = self.state.get('results_list')
        if not results_list:
            return
        
        result_selected = results_list.selection()
        if not result_selected:
            return
        
        result_idx = int(result_selected[0])
        commit_obj = self.state['ranked_commits'][result_idx]
        
        if "error" in commit_obj:
            return
        
        # Get the clicked file
        file_to_keep = self.files_checklist.item(item, "values")[0]
        
        # This would trigger the file filtering logic
        # For now, just select the item
        self.files_checklist.selection_set(item)
    
    def _on_function_before_double_click(self, event):
        """Double-click a function in functions_before to add to context"""
        functions_before_list = self.state.get('functions_before_list')
        if not functions_before_list:
            return
        
        item = functions_before_list.identify_row(event.y)
        if not item:
            return
        
        results_list = self.state.get('results_list')
        if not results_list:
            return
        
        result_selected = results_list.selection()
        if not result_selected:
            return
        
        result_idx = int(result_selected[0])
        function_to_add = functions_before_list.item(item, "values")[0]
        
        add_function_to_context(self.state, result_idx, function_to_add, "before")
    
    def _on_function_after_double_click(self, event):
        """Double-click a function in functions_after to add to context"""
        functions_after_list = self.state.get('functions_after_list')
        if not functions_after_list:
            return
        
        item = functions_after_list.identify_row(event.y)
        if not item:
            return
        
        results_list = self.state.get('results_list')
        if not results_list:
            return
        
        result_selected = results_list.selection()
        if not result_selected:
            return
        
        result_idx = int(result_selected[0])
        function_to_add = functions_after_list.item(item, "values")[0]
        
        add_function_to_context(self.state, result_idx, function_to_add, "after")