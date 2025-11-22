"""
Object-related operations: reset, context management
"""
import json
from tkinter import messagebox
from utils.url_helpers import add_clickable_urls, get_blob_url_by_function

def reset_selected_object(state):
    """Reset selected object to its original state"""
    object_list = state.get('object_list')
    text_view = state.get('text_view')
    
    selected = object_list.selection() if object_list else None
    if not selected:
        messagebox.showerror("Error", "Select an object first.")
        return
    
    idx = int(selected[0])
    
    if idx >= len(state.get('original_loaded_objects', [])):
        messagebox.showerror("Error", "Original object not found.")
        return
    
    state['loaded_objects'][idx] = json.loads(json.dumps(state['original_loaded_objects'][idx]))
    
    obj = state['loaded_objects'][idx]
    if text_view:
        text_view.delete("1.0", "end")
        text_view.insert("end", json.dumps(obj, indent=4, ensure_ascii=False))
        add_clickable_urls(text_view, json.dumps(obj, ensure_ascii=False))
    
    messagebox.showinfo("Reset", f"Object {idx} has been reset to its original state.")

def add_function_to_context(state, result_idx, selected_function, function_type):
    """Add selected function to object's context"""
    object_list = state.get('object_list')
    text_view = state.get('text_view')
    
    obj_selected = object_list.selection() if object_list else None
    if not obj_selected:
        messagebox.showerror("Error", "Select an object first.")
        return
    
    obj_idx = int(obj_selected[0])
    obj = state['loaded_objects'][obj_idx]
    commit = state['ranked_commits'][result_idx]
    
    if "error" in commit:
        messagebox.showerror("Error", "Cannot use an error result.")
        return
    
    # Determine contract name
    if "::" in selected_function:
        contract_name = selected_function.split("::")[0]
    elif " is " in selected_function:
        contract_name = selected_function.split(" is ")[0]
    else:
        contract_name = selected_function
    
    # Find matching file index
    file_index = -1
    for i, file in enumerate(commit.get("files", [])):
        base = file.replace(".sol", "")
        if contract_name in base or base in contract_name:
            file_index = i
            break
    
    if file_index == -1:
        messagebox.showwarning("Warning", f"Could not find file for: {contract_name}")
        return
    
    # Initialize or merge context
    ctx = obj.get("context")
    if (ctx is None or not isinstance(ctx, dict) or 
        not all(k in ctx for k in ("source", "fix", "functions_before", "functions_after"))):
        ctx = {
            "source": None,
            "fix": None,
            "functions_before": [],
            "functions_after": []
        }
    
    # Set blob URLs
    ctx["source"] = ctx["source"] or get_blob_url_by_function(
        commit.get("before_blob", []), selected_function, commit.get("files", [])
    )
    ctx["fix"] = ctx["fix"] or get_blob_url_by_function(
        commit.get("after_blob", []), selected_function, commit.get("files", [])
    )
    
    # Add function
    if function_type == "before":
        if selected_function not in ctx["functions_before"]:
            ctx["functions_before"].append(selected_function)
    elif function_type == "after":
        if selected_function not in ctx["functions_after"]:
            ctx["functions_after"].append(selected_function)
    
    obj["context"] = ctx
    
    if text_view:
        pretty = json.dumps(obj, indent=4, ensure_ascii=False)
        text_view.delete("1.0", "end")
        text_view.insert("end", pretty)
        add_clickable_urls(text_view, pretty)
    
    messagebox.showinfo("Success", f"Added '{selected_function}' to context.")