# paperless-tools

Open WebUI tools for searching and analyzing [paperless-ngx](https://docs.paperless-ngx.com/) documents through LLM chat.

## Tools

### paperless_search.py

A complete toolset that gives the LLM access to your paperless-ngx document library:

| Tool | Description |
|------|-------------|
| `search_documents` | Full-text search with filters (tag, correspondent, document type, date range) |
| `get_document` | Retrieve full content of a specific document by ID |
| `list_tags` | List available tags and their document counts |
| `list_correspondents` | List known correspondents/senders |
| `list_document_types` | List available document types |

## Installation

### Option 1: Open WebUI UI (recommended)

1. Open your Open WebUI instance
2. Go to **Workspace > Tools > + (New Tool)**
3. Copy the contents of `paperless_search.py` and paste into the editor
4. Click **Save**
5. Click the **gear icon** on the tool and configure:
   - **base_url**: Your paperless-ngx URL (e.g. `http://paperless-ngx:8000` or `https://paperless.example.com`)
   - **api_token**: A paperless-ngx API token (generate in Django Admin > Authorisation Tokens)
6. Enable the tool on your model: **Workspace > Models > select model > Tools > enable "Paperless-ngx Document Search"**

### Option 2: REST API

```bash
curl -X POST http://your-open-webui:3000/api/v1/tools/create \
  -H "Authorization: Bearer <admin-jwt-token>" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg content "$(cat paperless_search.py)" '{
    id: "paperless_search",
    name: "Paperless-ngx Document Search",
    content: $content,
    meta: {description: "Search and analyze paperless-ngx documents"}
  }')"
```

### Option 3: URL Import

If this repo is accessible from your Open WebUI instance:
```
POST /api/v1/tools/load/url
{"url": "https://raw.githubusercontent.com/mattr7m/paperless-tools/develop/paperless_search.py"}
```

## Configuration

### Valves (Admin Settings)

Set via Workspace > Tools > gear icon after importing:

| Setting | Description | Default |
|---------|-------------|---------|
| `base_url` | Paperless-ngx instance URL | `http://paperless-ngx:8000` |
| `api_token` | API authentication token | (empty — must set) |
| `request_timeout` | HTTP timeout in seconds | `30.0` |

### User Valves (Per-User)

Each user can adjust in the chat interface:

| Setting | Description | Default |
|---------|-------------|---------|
| `max_results` | Max documents per search | `10` |

### API Token Setup

Create a dedicated user in paperless-ngx for the Open WebUI tool:

1. In paperless-ngx UI, go to **Settings > Users & Groups**
2. Create a new user (e.g. `open-webui`)
3. Grant **Superuser status** (needs to read all documents, tags, correspondents, types)
4. Generate an API token: **Settings > Django Admin** (or `/admin/`) > **Authorisation Tokens > Add** — select the user, save, copy the token
5. Enter the token in Open WebUI: **Workspace > Tools > Paperless-ngx Document Search > gear icon > api_token**

Using a dedicated user (rather than sharing with other integrations) keeps audit trails distinct.

Without superuser, the minimum permissions are:

| Category | Permission |
|----------|-----------|
| Documents | View |
| Tags | View |
| Correspondents | View |
| Document Types | View |

**Note:** Object-level permissions in paperless-ngx mean the user must also have visibility on individual documents, tags, etc. Superuser bypasses this entirely.

## Model Configuration

### Enable Function Calling

For best results, enable native function calling on your model:

**Admin Panel > Settings > Models > (select model) > Advanced Parameters > Function Calling > Native**

This lets the model use structured tool calls instead of prompt-based invocation.

### Recommended Models

Any model with function-calling support works. Larger models produce better analysis of document content:
- Qwen 2.5+ (70B+)
- Llama 3.x (70B+)
- GPT-4+
- Claude 3+

### System Prompt (Required)

Set on the model in **Workspace > Models > (your model) > System Prompt**:

```
You have access to the user's personal document library via the Paperless-ngx search tools. When the user asks about events, purchases, bills, invoices, maintenance records, or any information that could be in their scanned documents, ALWAYS use the search tools first before answering from general knowledge. The user's documents contain receipts, mail, flyers, statements, and other scanned paperwork.

When searching, use simple keywords that would literally appear in the document text. Do not include words like "upcoming", "recent", "latest", or "my" in search queries — these words won't be in the documents.
```

Without this prompt, the model will answer from general knowledge instead of calling the tools.

### Search Tips

Paperless-ngx full-text search uses AND logic — all words must be present. The tool has a fallback that retries with individual keywords if a multi-word query returns nothing, but best results come from simple 1-2 word queries using terms that literally appear in the document.

| Works | Doesn't work | Why |
|-------|-------------|-----|
| `waterloo events` | `upcoming events waterloo` | "upcoming" isn't in the doc |
| `woodman` | `Woodman's` | Apostrophe handling |
| `oil change` | `my recent oil changes` | "my" and "recent" aren't in docs |

## Example Usage

```
You:   How much did I spend on groceries in March?
LLM:   [calls search_documents(query="grocery receipt", date_from="2026-03-01", date_to="2026-03-31")]
       Based on your receipts, you spent $342.17 on groceries in March...

You:   Show me the oil change intervals for the RAV4
LLM:   [calls search_documents(query="RAV4 oil change", tag="vehicle-maintenance")]
       Based on your service records, the RAV4 had oil changes at:
       - Jan 2024 at 45,012 mi
       - Jul 2024 at 51,230 mi (6,218 mi interval) ...

You:   What tags do I have?
LLM:   [calls list_tags()]
       You have 15 tags: invoice (23 docs), receipt (45 docs) ...

You:   Find all documents from Pacific Gas & Electric
LLM:   [calls search_documents(query="", correspondent="Pacific Gas")]
       Found 12 utility statements from PG&E...
```

## Development

### Testing Locally

The tool is a standalone Python file. You can test the API calls directly:

```python
import asyncio
import httpx

async def test():
    headers = {"Authorization": "Token YOUR_TOKEN"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "http://your-paperless:8000/api/documents/",
            params={"query": "test", "page_size": 5},
            headers=headers
        )
        print(resp.json())

asyncio.run(test())
```

### Adding New Tools

Add new `async def` methods to the `Tools` class in `paperless_search.py`. Each method needs:
- Type hints on all parameters
- A docstring with `:param name: description` for each parameter
- Return type of `str` (the text passed back to the LLM)
