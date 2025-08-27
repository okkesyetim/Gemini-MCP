# Gemini-MCP Project

A simple client-server application that uses the Google Gemini API to interact with local tools.

## Setup

1. **Clone the repository**

```bash
git clone https://github.com/okkesyetim/Gemini-MCP.git
cd Gemini-MCP
```

2. **Create a virtual environment and activate it**

*For macOS/Linux:*

```bash
python3 -m venv .venv
source .venv/bin/activate
```

*For Windows:*

```bash
python -m venv .venv
.\.venv\Scripts\activate
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

## Configuration

Create a file named `.env` in the project root and add your Google Gemini API key:

```env
GEMINI_API_KEY="YOUR_API_KEY_HERE"
```

## How to Run

Simply run the main client script. It will handle starting the server in the background.

**Terminal: Start the Server and Client**

```bash
cd client_host
python run_chat.py
```

Now you can start typing requests in the client terminal.

## Dependencies

* `mcp[cli]`
* `google-generativeai`
* `python-dotenv`
* `httpx`
