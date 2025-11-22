# Installation Guide

## Directory Setup

Create the following directory structure:

```
json_explorer/
├── main.py
├── gui/
│   ├── __init__.py
│   ├── main_window.py
│   ├── top_bar.py
│   ├── file_list.py
│   ├── content_panel.py
│   ├── object_panel.py
│   ├── results_panel.py
│   └── filter_widgets.py
├── core/
│   ├── __init__.py
│   ├── file_operations.py
│   ├── commit_operations.py
│   ├── object_operations.py
│   └── filter_operations.py
├── utils/
│   ├── __init__.py
│   ├── url_helpers.py
│   └── ui_helpers.py
├── parse_all_commits.py          # Your existing file
└── compute_relevance_gpt.py      # Your existing file
```

## Step-by-Step Installation

### 1. Create Directory Structure

```bash
mkdir -p json_explorer/gui json_explorer/core json_explorer/utils
cd json_explorer
```

### 2. Copy Files

Copy all the provided Python files into their respective directories:

- Place `main.py` in the root `json_explorer/` directory
- Place GUI files in `gui/` directory
- Place core files in `core/` directory
- Place utility files in `utils/` directory
- Copy your existing `parse_all_commits.py` and `compute_relevance_gpt.py` to the root

### 3. Verify Structure

Run this command to verify your structure:

```bash
tree json_explorer/
```

You should see all files in their correct locations.

### 4. Set Environment Variable

Make sure you have your GitHub API key set:

```bash
export GITHUB_API_KEY="your_token_here"
```

Or on Windows:
```cmd
set GITHUB_API_KEY=your_token_here
```

### 5. Run the Application

From the `json_explorer/` directory:

```bash
python main.py
```

Or:
```bash
python3 main.py
```

## Dependencies

The application requires:
- Python 3.6+
- tkinter (usually included with Python)
- Any dependencies from `parse_all_commits.py` and `compute_relevance_gpt.py`

If you're missing tkinter, install it:

**Ubuntu/Debian:**
```bash
sudo apt-get install python3-tk
```

**macOS:**
```bash
brew install python-tk
```

**Windows:**
Tkinter is usually included with Python installation.

## Troubleshooting

### Import Errors

If you get `ModuleNotFoundError`, ensure:
1. You're running from the correct directory
2. All `__init__.py` files exist
3. The directory structure matches exactly

### File Not Found

If the original files (`parse_all_commits.py`, `compute_relevance_gpt.py`) aren't found:
1. Verify they're in the root `json_explorer/` directory
2. Check if they have different names in your setup
3. Update imports in `core/commit_operations.py` if needed

### GitHub API Issues

If commit fetching fails:
1. Verify `GITHUB_API_KEY` environment variable is set
2. Check your API token has the correct permissions
3. Verify network connectivity

## Quick Test

After installation, test the application:

1. Click "Open Folder" and select a folder with JSON files
2. Select a JSON file from the list
3. Select an object from the object list
4. Verify the object content displays correctly

If all these work, your installation is successful!

## Migration from Original File

If you're migrating from the original single-file version:

1. **Backup your original file**
2. Install the new modular version
3. Test with sample data
4. Once verified, you can remove the original file

The new version has identical functionality but is organized into logical modules for better maintainability.