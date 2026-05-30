# Tools Reference

This document provides a comprehensive reference for all tools available in Omen.

## Tool Categories

| Category | Module | Description |
|----------|--------|-------------|
| [Web Tools](#web-tools) | `tools/web_tools.py` | Browser, scraping, downloads |
| [Search Tools](#search-tools) | `tools/search_tools.py` | Web and YouTube search |
| [Filesystem Tools](#filesystem-tools) | `tools/filesystem_tools.py` | File operations |
| [Data Tools](#data-tools) | `tools/data_tools.py` | Dataset analysis |
| [Automation Tools](#automation-tools) | `tools/automation_tools.py` | Code execution, ML pipelines |
| [Task Tools](#task-tools) | `tools/task_tools.py` | Task management |
| [Context Tools](#context-tools) | `tools/context_manager_tools.py` | Memory storage |
| [UI Tools](#ui-tools) | `tools/ui_tools.py` | Display formatting |
| [Misc Tools](#misc-tools) | `tools/misc_tools.py` | Utilities |

---

## Web Tools

Location: `tools/web_tools.py`

### `open_url_in_browser`

Opens a URL in the default web browser.

```python
open_url_in_browser(link: str) -> str
```

**Parameters:**
- `link`: The URL to open

**Returns:** Status message

---

### `get_weather_info`

Get weather information for a location.

```python
get_weather_info(location: str) -> str
```

**Parameters:**
- `location`: Location name (city, region)

**Returns:** Weather data dictionary

---

### `scrape_url`

Scrape a webpage and extract content.

```python
scrape_url(
    url: str,
    summarise: bool = True,
    instructions: str = ""
) -> str
```

**Parameters:**
- `url`: Webpage URL
- `summarise`: Use LLM to summarize content (default: True)
- `instructions`: Special extraction instructions

**Returns:** Scraped/summarized content

---

### `download_audio`

Download audio from a video URL.

```python
download_audio(url: str) -> str
```

**Parameters:**
- `url`: Video URL (YouTube, etc.)

**Returns:** Download status/path

**Output Location:** `root/downloads/audio/`

---

### `download_video`

Download video from a URL.

```python
download_video(url: str) -> str
```

**Parameters:**
- `url`: Video URL

**Returns:** Download status/path

**Output Location:** `root/downloads/video/`

---

## Search Tools

Location: `tools/search_tools.py`

### `web_search`

Perform a web search using Searx.

```python
web_search(query: str, num_results: int = 5) -> str
```

**Parameters:**
- `query`: Search query
- `num_results`: Maximum results (default: 5)

**Returns:** Formatted search results with titles and links

---

### `duckduckgo_web_search`

Search using DuckDuckGo.

```python
duckduckgo_web_search(query: str, max_results: int = 5) -> str
```

**Parameters:**
- `query`: Search query
- `max_results`: Maximum results (default: 5)

**Returns:** Formatted search results

---

### `search_youtube_videos`

Search for YouTube videos.

```python
search_youtube_videos(query: str, num_results: int = 5) -> str
```

**Parameters:**
- `query`: Search query
- `num_results`: Maximum results (default: 5)

**Returns:** Video list with title, URL, channel, duration, views, publish date

---

## Filesystem Tools

Location: `tools/filesystem_tools.py`

> **Note:** All paths are relative to the `root/` sandbox directory.

### `list_files`

List files and directories.

```python
list_files(relative_path: str = "") -> str
```

**Returns:** Newline-separated list of files/directories

---

### `read_file`

Read file content.

```python
read_file(relative_path: str) -> str
```

**Returns:** File content as string

---

### `write_file`

Write content to a file (creates or overwrites).

```python
write_file(relative_path: str, content: str) -> str
```

**Returns:** Success/error message

---

### `edit_file_section`

Edit a specific section of a file.

```python
edit_file_section(
    relative_path: str,
    old_content: str,
    new_content: str
) -> str
```

**Parameters:**
- `relative_path`: File path
- `old_content`: Text to replace
- `new_content`: Replacement text

**Returns:** Success/error message

---

### `append_to_file`

Append content to a file.

```python
append_to_file(relative_path: str, content: str) -> str
```

**Returns:** Success/error message

---

### `create_directory`

Create a directory (with parents).

```python
create_directory(relative_path: str) -> str
```

**Returns:** Success/error message

---

### `delete_file`

Delete a file.

```python
delete_file(relative_path: str) -> str
```

**Returns:** Success/error message

---

### `delete_directory`

Delete an empty directory.

```python
delete_directory(relative_path: str) -> str
```

**Returns:** Success/error message

---

### `move_file`

Move or rename a file.

```python
move_file(src_relative_path: str, dst_relative_path: str) -> str
```

**Returns:** Success/error message

---

### `copy_file`

Copy a file.

```python
copy_file(src_relative_path: str, dst_relative_path: str) -> str
```

**Returns:** Success/error message

---

### `grep_file_content`

Search for regex pattern in a file.

```python
grep_file_content(relative_path: str, pattern: str) -> str
```

**Parameters:**
- `relative_path`: File path
- `pattern`: Regex pattern

**Returns:** Matching lines

---

## Data Tools

Location: `tools/data_tools.py`

### `dataset_overview`

Quick dataset inspection.

```python
dataset_overview(relative_path: str, sample_rows: int = 5) -> str
```

**Returns:**
- Path, format, file size
- Row/column counts
- Schema preview (column types)
- Sample rows

---

### `dataset_quality_report`

Generate quality analysis report.

```python
dataset_quality_report(relative_path: str, sample_rows: int = 5000) -> str
```

**Returns:**
- Missing value analysis
- Cardinality (unique counts)
- Numeric summary statistics
- Categorical summaries

---

### `dataset_correlation_report`

Compute correlation analysis.

```python
dataset_correlation_report(
    relative_path: str,
    target_column: str | None = None,
    sample_rows: int = 5000
) -> str
```

**Parameters:**
- `relative_path`: Dataset path
- `target_column`: Target variable for correlation (optional)
- `sample_rows`: Sample limit

**Returns:** Correlation strengths and predictive signals

---

## Automation Tools

Location: `tools/automation_tools.py`

### `run_auto_eda`

Automated exploratory data analysis.

```python
run_auto_eda(
    relative_path: str,
    output_dir: str | None = None
) -> str
```

**Returns:** EDA report with visualizations

---

### `run_auto_modeling`

Automated machine learning pipeline.

```python
run_auto_modeling(
    relative_path: str,
    target_column: str,
    task_type: Literal["classification", "regression"],
    output_dir: str | None = None
) -> str
```

**Parameters:**
- `relative_path`: Dataset path
- `target_column`: Target variable
- `task_type`: "classification" or "regression"
- `output_dir`: Output directory (optional)

**Returns:** Model metrics and artifacts

---

### `run_script`

Execute a Python script.

```python
run_script(script_path: str) -> str
```

**Returns:** Script output

---

### `execute_code`

Run arbitrary Python code.

```python
execute_code(code: str) -> str
```

**Returns:** Code execution output

---

## Task Tools

Location: `tools/task_tools.py`

### `create_task`

Create a new tracked task.

```python
create_task(
    title: str,
    description: str = "",
    steps: str = "",           # Pipe-separated: "Step 1|Step 2|Step 3"
    priority: str = "medium",  # low, medium, high, critical
    tags: str = "",            # Comma-separated
) -> str
```

**Returns:** Task details with ID

---

### `add_task_step`

Add a step to existing task.

```python
add_task_step(
    task_id: str,
    step_title: str,
    step_description: str = ""
) -> str
```

---

### `start_step`

Mark a step as in-progress.

```python
start_step(task_id: str, step_id: str) -> str
```

---

### `complete_step`

Mark a step as completed.

```python
complete_step(task_id: str, step_id: str, result: str = "") -> str
```

---

### `fail_step`

Mark a step as failed.

```python
fail_step(task_id: str, step_id: str, reason: str = "") -> str
```

---

### `save_task_context`

Save intermediate context for task resumption.

```python
save_task_context(task_id: str, context: str) -> str
```

---

### `get_active_tasks`

List all active (non-completed) tasks.

```python
get_active_tasks() -> str
```

---

### `resume_task`

Resume work on a task.

```python
resume_task(task_id: str) -> str
```

---

## Context Tools

Location: `tools/context_manager_tools.py`

### `save_context_topic`

Save or update a conversation context.

```python
save_context_topic(
    topic_name: str,
    content: str,
    is_new_topic: bool = False
) -> str
```

**Storage:** `memory_store/memories/{topic_name}.md`

---

### `load_context_topic`

Load a saved context.

```python
load_context_topic(topic_name: str) -> str
```

---

### `list_context_topics`

List all available memory topics.

```python
list_context_topics() -> str
```

---

### `update_context_content`

Update specific content within a topic.

```python
update_context_content(
    topic_name: str,
    old_content: str,
    new_content: str
) -> str
```

---

### `delete_context_topic`

Remove a memory topic.

```python
delete_context_topic(topic_name: str) -> str
```

---

## UI Tools

Location: `tools/ui_tools.py`

Tools for rich terminal output formatting and display.

---

## Misc Tools

Location: `tools/misc_tools.py`

### `get_current_datetime`

Get current date and time.

```python
get_current_datetime() -> str
```

**Returns:** Formatted datetime string

---

## Creating Custom Tools

### Basic Tool Definition

```python
from agents import function_tool

@function_tool
def my_custom_tool(param1: str, param2: int = 10) -> str:
    """
    Brief description of what the tool does.
    
    Args:
        param1: Description of param1
        param2: Description of param2 (default: 10)
    
    Returns:
        Description of return value
    """
    # Implementation
    result = f"Processed {param1} with {param2}"
    return result
```

### Adding to Tool Lists

```python
# In your tools module
MY_CUSTOM_TOOLS = [
    my_custom_tool,
    another_tool,
]

# In agent definition
from tools.my_tools import MY_CUSTOM_TOOLS

my_agent = my_agent(
    ...
    tools=MY_CUSTOM_TOOLS,
)
```

### Best Practices

1. **Clear Docstrings**: Include detailed Args and Returns sections
2. **Type Hints**: Use proper typing for parameters
3. **Error Handling**: Return meaningful error messages
4. **Sandbox Safety**: Validate paths and inputs
5. **Consistent Returns**: Always return strings for agent consumption
