"""
UI helper functions
"""

def filter_tree(tree, search_text, all_items):
    """Filter a treeview based on search text"""
    tree.delete(*tree.get_children())
    
    search_lower = search_text.lower()
    for item_value in all_items:
        if search_lower in item_value.lower():
            tree.insert("", "end", values=(item_value,))

def select_all_items(widget):
    """Select all visible items in a treeview"""
    for item in widget.get_children():
        widget.selection_add(item)