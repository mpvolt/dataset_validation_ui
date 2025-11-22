"""
URL handling utilities
"""
import re
import webbrowser

def transform_blob_to_commit(url):
    """Transform blob URL to commit URL"""
    return re.sub(r"/blob/([^/]+)", r"/commit/\1", url)

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
        text_widget.tag_bind(
            tagname,
            "<Button-1>",
            lambda e, u=url: webbrowser.open(transform_blob_to_commit(u))
        )

def get_blob_url_by_function(blob_list, function_name, files_list):
    """
    Find the correct blob URL for a function.
    Handles formats like:
    - ContractName::functionName
    - filename.sol::functionName
    """
    if "::" in function_name:
        prefix = function_name.split("::")[0]
    elif " is " in function_name:
        prefix = function_name.split(" is ")[0]
    else:
        prefix = function_name
    
    for i, file in enumerate(files_list):
        file_base = file.replace(".sol", "")
        
        if (prefix.lower() == file_base.lower() or 
            prefix.lower() == file.lower() or
            file_base.lower() in prefix.lower() or
            prefix.lower() in file_base.lower()):
            
            if i < len(blob_list):
                return blob_list[i]
    
    # Fallback: return first blob if only one exists
    if len(blob_list) == 1:
        return blob_list[0]
    
    return None