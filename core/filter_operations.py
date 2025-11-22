"""
Filtering operations for commits, files, and functions
"""
import json
from tkinter import messagebox
from utils.url_helpers import add_clickable_urls

def apply_selections(state):
    """Apply current selections to filter the commit"""
    results_list = state.get('results_list')
    files_checklist = state.get('files_checklist')
    functions_before_list = state.get('functions_before_list')
    functions_after_list = state.get('functions_after_list')
    
    result_selected = results_list.selection() if results_list else None
    if not result_selected:
        messagebox.showerror("Error", "Select a ranked commit first.")
        return
    
    result_idx = int(result_selected[0])
    commit_obj = state['ranked_commits'][result_idx]
    
    if "error" in commit_obj:
        messagebox.showerror("Error", "Cannot filter error results.")
        return
    
    changes_made = False
    
    selected_files = files_checklist.selection() if files_checklist else []
    selected_funcs_before = functions_before_list.selection() if functions_before_list else []
    selected_funcs_after = functions_after_list.selection() if functions_after_list else []
    
    # Filter files
    if selected_files:
        files_to_keep = [files_checklist.item(item, "values")[0] for item in selected_files]
        
        if files_to_keep:
            all_files = commit_obj.get("files", [])
            indices_to_keep = [i for i, f in enumerate(all_files) if f in files_to_keep]
            
            commit_obj["files"] = [all_files[i] for i in indices_to_keep]
            
            if "before_blob" in commit_obj:
                before_blobs = commit_obj["before_blob"]
                commit_obj["before_blob"] = [before_blobs[i] for i in indices_to_keep if i < len(before_blobs)]
            
            if "after_blob" in commit_obj:
                after_blobs = commit_obj["after_blob"]
                commit_obj["after_blob"] = [after_blobs[i] for i in indices_to_keep if i < len(after_blobs)]
            
            # Filter functions by filename
            for func_key in ["functions_before", "functions_after"]:
                if func_key in commit_obj:
                    filtered_functions = []
                    for func in commit_obj[func_key]:
                        contract_name = extract_contract_name(func)
                        for kept_file in files_to_keep:
                            file_base = kept_file.replace(".sol", "")
                            if contract_name in file_base or file_base in contract_name:
                                filtered_functions.append(func)
                                break
                    commit_obj[func_key] = filtered_functions
            
            changes_made = True
    
    # Filter functions_before
    if selected_funcs_before:
        functions_to_keep = [functions_before_list.item(item, "values")[0] for item in selected_funcs_before]
        if functions_to_keep:
            commit_obj["functions_before"] = functions_to_keep
            changes_made = True
    
    # Filter functions_after
    if selected_funcs_after:
        functions_to_keep = [functions_after_list.item(item, "values")[0] for item in selected_funcs_after]
        if functions_to_keep:
            commit_obj["functions_after"] = functions_to_keep
            changes_made = True
    
    if not changes_made:
        messagebox.showwarning("Warning", "No items selected. Double-click items to select them, then click Apply.")
        return
    
    refresh_commit_display(state, result_idx)
    
    file_count = len(files_to_keep) if selected_files else 0
    func_before_count = len([functions_before_list.item(item, "values")[0] for item in selected_funcs_before]) if selected_funcs_before else 0
    func_after_count = len([functions_after_list.item(item, "values")[0] for item in selected_funcs_after]) if selected_funcs_after else 0
    
    summary = []
    if file_count > 0:
        summary.append(f"{file_count} file(s)")
    if func_before_count > 0:
        summary.append(f"{func_before_count} function(s) before")
    if func_after_count > 0:
        summary.append(f"{func_after_count} function(s) after")
    
    messagebox.showinfo("Success", f"Applied selections: {', '.join(summary)}")

def refresh_commit_display(state, result_idx):
    """Refresh all displays for the selected commit"""
    commit_obj = state['ranked_commits'][result_idx]
    
    # Clear search boxes
    for key in ['files_search_var', 'functions_before_search_var', 'functions_after_search_var']:
        var = state.get(key)
        if var:
            var.set("")
    
    # Refresh results text
    results_text = state.get('results_text')
    if results_text:
        results_text.delete("1.0", "end")
        pretty = json.dumps(commit_obj, indent=4, ensure_ascii=False)
        results_text.insert("end", pretty)
        add_clickable_urls(results_text, pretty)
    
    # Refresh lists
    refresh_list(state.get('files_checklist'), commit_obj.get("files", []))
    refresh_list(state.get('functions_before_list'), commit_obj.get("functions_before", []))
    refresh_list(state.get('functions_after_list'), commit_obj.get("functions_after", []))

def refresh_list(widget, items):
    """Helper to refresh a treeview widget"""
    if widget:
        widget.delete(*widget.get_children())
        for item in items:
            widget.insert("", "end", values=(item,))

def extract_contract_name(func):
    """Extract contract name from function string"""
    if "::" in func:
        return func.split("::")[0]
    elif " is " in func:
        return func.split(" is ")[0]
    else:
        return func