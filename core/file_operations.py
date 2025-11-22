"""
File operations: loading, saving, folder selection
"""
import os
import json
from tkinter import filedialog, messagebox

def pick_folder(state):
    """Open folder picker and load JSON files"""
    folder = filedialog.askdirectory()
    if not folder:
        return
    state['folder_var'].set(folder)
    load_json_files(folder, state)

def load_json_files(root_folder, state):
    """Load all JSON files from folder into file tree"""
    file_tree = state.get('file_tree')
    object_list = state.get('object_list')
    text_view = state.get('text_view')
    
    if file_tree:
        file_tree.delete(*file_tree.get_children())
    if object_list:
        object_list.delete(*object_list.get_children())
    if text_view:
        text_view.delete("1.0", "end")
    
    for root, dirs, files in os.walk(root_folder):
        for f in files:
            if f.lower().endswith(".json"):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, root_folder)
                if file_tree:
                    file_tree.insert("", "end", values=(rel_path, full_path))

def load_json_objects(path, state):
    """Load JSON objects from a file"""
    object_list = state.get('object_list')
    text_view = state.get('text_view')
    
    if object_list:
        object_list.delete(*object_list.get_children())
    if text_view:
        text_view.delete("1.0", "end")
    
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        messagebox.showerror("Error", f"Failed to read file:\n{e}")
        return
    
    # Parse JSON in flexible formats
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            state['loaded_objects'] = [parsed]
        elif isinstance(parsed, list):
            state['loaded_objects'] = parsed
        else:
            state['loaded_objects'] = [parsed]
    except json.JSONDecodeError:
        state['loaded_objects'] = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                state['loaded_objects'].append(json.loads(line))
            except:
                pass
        
        if not state['loaded_objects']:
            messagebox.showerror("Error", "Could not parse JSON file.")
            return
    
    # Populate object list
    for idx, obj in enumerate(state['loaded_objects']):
        label = f"Object {idx}"
        if isinstance(obj, dict):
            for k in ("id", "finding_number", "title", "name", "type"):
                if k in obj:
                    label += f" ({k}: {obj[k]})"
                    break
        if object_list:
            object_list.insert("", "end", iid=str(idx), values=(label,))
    
    # Store original for reset
    state['original_loaded_objects'] = [json.loads(json.dumps(obj)) for obj in state['loaded_objects']]

def save_file(state):
    """Save current file content"""
    current_file_path = state.get('current_file_path')
    text_view = state.get('text_view')
    
    if not current_file_path:
        messagebox.showerror("Error", "No file loaded.")
        return
    
    try:
        content_to_save = text_view.get("1.0", "end-1c")
        with open(current_file_path, "w", encoding="utf-8") as f:
            f.write(content_to_save)
        messagebox.showinfo("Success", f"File saved: {current_file_path}")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save file:\n{str(e)}")