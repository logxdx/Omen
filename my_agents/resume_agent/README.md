# Resume Agent

The Resume Agent is a specialized AI agent that optimizes resumes by tailoring them to specific job descriptions. It intelligently incorporates relevant keywords and phrases from job postings while maintaining the authenticity and readability of the original resume.

## Features

- **Keyword Extraction**: Automatically identifies important keywords and requirements from job descriptions
- **Strategic Integration**: Naturally incorporates keywords into appropriate resume sections
- **ATS Optimization**: Ensures resumes are optimized for Applicant Tracking Systems
- **Authenticity Preservation**: Never adds false information or fabricates experience
- **Timestamp Management**: Saves optimized resumes with timestamps to avoid confusion

## Directory Structure

```
root/
  resume/
    original/    # Place your original resume here
    new/         # Optimized resumes are saved here with timestamps
```

## Usage

1. **Place Your Original Resume**: Put your resume file in `root/resume/original/`
   - Supported formats: `.txt`, `.md`, `.docx`

2. **Provide Job Description**: Give the agent either:
   - Direct text of the job description
   - Path to a file containing the job description

3. **Agent Workflow**: The agent will:
   - Read your original resume from `root/resume/original/`
   - Analyze the job description for key requirements and keywords
   - Identify strategic places to integrate keywords naturally
   - Rewrite relevant sections while preserving your authentic experience
   - Save the optimized resume to `root/resume/new/` with a timestamp

## Example Interaction

```
User: "I have a resume in root/resume/original/my_resume.txt. Can you optimize it for this job description: [paste job description]"

Agent: 
- Reads original resume
- Analyzes job requirements
- Extracts key skills and keywords
- Optimizes resume sections
- Saves to root/resume/new/resume_optimized_2025_12_05_14_30_00.txt
- Provides summary of changes made
```

## Tools Available

The Resume Agent has access to the following tools:
- `read_file()`: Read files from the root directory
- `write_file()`: Write optimized resumes to the new directory
- `list_files()`: List files in directories
- `get_current_datetime()`: Generate timestamps for unique filenames

## Best Practices

- Keep your original resume in `root/resume/original/` unchanged
- Each optimization creates a new timestamped file
- The agent maintains factual accuracy - it won't add skills or experience you don't have
- Keywords are integrated naturally within the context of your existing experience
- Original formatting and structure are preserved

## Configuration

The Resume Agent is configured in `config/agent_config.py` with both local and online model options.
