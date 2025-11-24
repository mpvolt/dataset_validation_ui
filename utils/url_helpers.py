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

