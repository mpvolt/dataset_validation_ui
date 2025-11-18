# Enhanced JSON Explorer with Side-by-Side Layout
# - Object list and file contents side by side
# - Results in separate window with clickable URLs
# - Highlighting and deletion capabilities
# - Move URL between fields

import os
import json
import threading
import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext, messagebox
from process_audit_changes import AuditChangesProcessor
import webbrowser
import re


current_file_path = None
loaded_objects = []
results_objects = []


def pick_folder():
    folder = filedialog.askdirectory()
    if not folder:
        return
    folder_var.set(folder)
    load_json_files(folder)


def load_json_files(root_folder):
    file_tree.delete(*file_tree.get_children())
    object_list.delete(*object_list.get_children())
    text_view.delete("1.0", tk.END)

    for root, dirs, files in os.walk(root_folder):
        for f in files:
            if f.lower().endswith(".json"):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, root_folder)
                file_tree.insert("", "end", values=(rel_path, full_path))


def on_file_select(event):
    global current_file_path, loaded_objects

    selected = file_tree.selection()
    if not selected:
        return

    _, full_path = file_tree.item(selected[0], "values")
    current_file_path = full_path
    load_json_objects(full_path)


def load_json_objects(path):
    global loaded_objects

    object_list.delete(*object_list.get_children())
    text_view.delete("1.0", tk.END)

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        messagebox.showerror("Error", f"Failed to read file:\n{e}")
        return

    # Parse JSON flexible formats
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            loaded_objects = [parsed]
        elif isinstance(parsed, list):
            loaded_objects = parsed
        else:
            loaded_objects = [parsed]

    except json.JSONDecodeError:
        loaded_objects = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                loaded_objects.append(json.loads(line))
            except:
                pass

        if not loaded_objects:
            messagebox.showerror("Error", "Could not parse JSON file.")
            return

    for idx, obj in enumerate(loaded_objects):
        label = f"Object {idx}"
        if isinstance(obj, dict):
            for k in ("id", "finding_number", "title", "name", "type"):
                if k in obj:
                    label += f" ({k}: {obj[k]})"
                    break
        object_list.insert("", "end", iid=str(idx), values=(label,))


def on_object_select(event):
    selected = object_list.selection()
    if not selected:
        return

    idx = int(selected[0])
    obj = loaded_objects[idx]

    text_view.delete("1.0", tk.END)
    pretty = json.dumps(obj, indent=4, ensure_ascii=False)
    text_view.insert(tk.END, pretty)
    text_view.tag_remove("highlight", "1.0", tk.END)

    # --- URL detection + tagging ---
    add_clickable_urls(text_view, pretty)


def add_clickable_urls(text_widget, content):
    """Add clickable URL tags to a text widget"""
    url_pattern = r"https?://[^\s\"']+"
    for match in re.finditer(url_pattern, content):
        start = f"1.0+{match.start()}c"
        end = f"1.0+{match.end()}c"

        url = match.group(0)
        tagname = f"url_{url}"
        text_widget.tag_add(tagname, start, end)
        text_widget.tag_config(tagname, foreground="blue", underline=True)
        text_widget.tag_bind(tagname, "<Button-1>", lambda e, u=url: webbrowser.open(u))


def highlight_selection():
    try:
        start = text_view.index("sel.first")
        end = text_view.index("sel.last")
        text_view.tag_add("highlight", start, end)
    except tk.TclError:
        pass


def delete_selection(event=None):
    try:
        start = text_view.index("sel.first")
        end = text_view.index("sel.last")
        text_view.delete(start, end)
        return "break"
    except tk.TclError:
        return


def move_url():
    selected = object_list.selection()
    if not selected:
        messagebox.showerror("Error", "Select an object first.")
        return

    idx = int(selected[0])
    obj = loaded_objects[idx]

    # Get highlighted text in the text window
    try:
        start = text_view.index("sel.first")
        end = text_view.index("sel.last")
        selected_text = text_view.get(start, end).strip()
    except tk.TclError:
        messagebox.showerror("Error", "Highlight the URL you want to move.")
        return

    if not selected_text:
        messagebox.showerror("Error", "You must highlight part of a URL.")
        return

    # --- Validate fields ---
    if "source_code_url" not in obj or not isinstance(obj["source_code_url"], list):
        messagebox.showerror("Error", "source_code_url must be a list.")
        return

    if "fix_commit_url" not in obj or not isinstance(obj.get("fix_commit_url", []), list):
        obj["fix_commit_url"] = []

    # --- Try to locate which URL contains the selected text ---
    matching_urls = [
        url for url in obj["source_code_url"]
        if selected_text in url
    ]

    if not matching_urls:
        messagebox.showerror("Error", "No URL in source_code_url contains the highlighted text.")
        return

    if len(matching_urls) > 1:
        messagebox.showerror("Error", "Selected text appears in multiple URLs. Highlight more text.")
        return

    # Exactly one match → move it
    url_to_move = matching_urls[0]

    obj["source_code_url"].remove(url_to_move)
    obj["fix_commit_url"].append(url_to_move)

    # --- Refresh display ---
    pretty = json.dumps(obj, indent=4, ensure_ascii=False)
    text_view.delete("1.0", tk.END)
    text_view.insert(tk.END, pretty)
    add_clickable_urls(text_view, pretty)


results_objects = []


def on_result_select(event):
    selected = results_list.selection()
    if not selected:
        return

    idx = int(selected[0])
    obj = results_objects[idx]

    results_text.delete("1.0", tk.END)
    pretty = json.dumps(obj, indent=4, ensure_ascii=False)
    results_text.insert(tk.END, pretty)
    
    # Add clickable URLs to results
    add_clickable_urls(results_text, pretty)


def run_get_commit_data():
    selected = object_list.selection()
    if not selected:
        messagebox.showerror("Error", "Select an object first.")
        return

    idx = int(selected[0])
    obj = loaded_objects[idx]
    
    # Clear results
    results_list.delete(*results_list.get_children())
    results_text.delete("1.0", tk.END)
    results_text.insert("1.0", "⏳ Fetching commit data... please wait...\n")
    results_text.update()

    def worker():
        try:
            github_token = os.getenv("GITHUB_API_KEY")
            processor = AuditChangesProcessor(github_token)
            result = processor.get_finding_commit_data(obj)

        except Exception as e:
            result = {"error": str(e)}

        # Update UI safely from main thread
        def update_ui():
            global results_objects
            
            results_text.delete("1.0", tk.END)
            results_list.delete(*results_list.get_children())
            
            # Parse result into objects
            if isinstance(result, list):
                results_objects = result
            elif isinstance(result, dict):
                results_objects = [result]
            else:
                results_objects = [result]
            
            # Populate results list
            for idx, obj in enumerate(results_objects):
                label = f"Result {idx}"
                if isinstance(obj, dict):
                    for k in ("id", "finding_number", "title", "name", "type", "commit_hash"):
                        if k in obj:
                            label += f" ({k}: {obj[k]})"
                            break
                results_list.insert("", "end", iid=str(idx), values=(label,))
            
            # Show message if no results
            if not results_objects:
                results_text.insert("1.0", "No results returned")

        root.after(0, update_ui)

    threading.Thread(target=worker).start()


# --- UI Setup ---
root = tk.Tk()
root.title("JSON Explorer + Editor")
root.geometry("1600x800")

folder_var = tk.StringVar()

# Top bar
bar = tk.Frame(root)
bar.pack(fill="x", padx=10, pady=5)

tk.Button(bar, text="Open Folder", command=pick_folder).pack(side="left")
tk.Button(bar, text="Highlight Selection", command=highlight_selection).pack(side="left", padx=5)
tk.Button(bar, text="Move URL to fix_commit_url", command=move_url).pack(side="left", padx=5)
tk.Button(bar, text="Get Commit Data", command=run_get_commit_data).pack(side="left", padx=5)

tk.Label(bar, textvariable=folder_var).pack(side="left", padx=10)

# JSON file list
tree_frame = tk.Frame(root)
tree_frame.pack(fill="x", padx=10, pady=5)

file_tree = ttk.Treeview(tree_frame, columns=("Relative", "Full"), show="headings", height=8)
file_tree.heading("Relative", text="JSON File")
file_tree.heading("Full", text="Full Path")
file_tree.column("Relative", width=350)
file_tree.column("Full", width=700)
file_tree.pack(fill="x")
file_tree.bind("<<TreeviewSelect>>", on_file_select)

# Main content area - three columns
content_frame = tk.Frame(root)
content_frame.pack(fill="both", expand=True, padx=10, pady=5)

# Left side - Object list
left_frame = tk.Frame(content_frame)
left_frame.pack(side="left", fill="both", expand=False, padx=(0, 5))

tk.Label(left_frame, text="JSON Objects", font=("Arial", 10, "bold")).pack(anchor="w")

object_list = ttk.Treeview(left_frame, columns=("Object",), show="headings")
object_list.heading("Object", text="Objects")
object_list.column("Object", width=250)
object_list.pack(fill="both", expand=True)
object_list.bind("<<TreeviewSelect>>", on_object_select)

# Middle - Text viewer
middle_frame = tk.Frame(content_frame)
middle_frame.pack(side="left", fill="both", expand=True, padx=5)

tk.Label(middle_frame, text="Object Contents", font=("Arial", 10, "bold")).pack(anchor="w")

text_view = scrolledtext.ScrolledText(middle_frame, wrap="none")
text_view.tag_config("highlight", background="yellow")
text_view.pack(fill="both", expand=True)

# Delete key binding
text_view.bind("<Delete>", delete_selection)

# Right side - Results
results_frame = tk.Frame(content_frame)
results_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))

tk.Label(results_frame, text="Commit Data Results", font=("Arial", 10, "bold")).pack(anchor="w")

# Results list (top)
results_list_frame = tk.Frame(results_frame)
results_list_frame.pack(fill="x", pady=(0, 5))

results_list = ttk.Treeview(results_list_frame, columns=("Result",), show="headings", height=6)
results_list.heading("Result", text="Results")
results_list.column("Result", width=350)
results_list.pack(fill="x")
results_list.bind("<<TreeviewSelect>>", on_result_select)

# Results text view (bottom)
results_text = scrolledtext.ScrolledText(results_frame, wrap="word")
results_text.pack(fill="both", expand=True)

root.mainloop()