"""
title: Paperless-ngx Document Search
author: mattr7m
description: Search, retrieve, and analyze documents from a paperless-ngx instance
required_open_webui_version: 0.4.0
requirements: httpx
version: 0.1.0
licence: MIT
"""

import httpx
import json
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Tools:
    def __init__(self):
        self.valves = self.Valves()

    class Valves(BaseModel):
        """Admin-configurable settings — set via Workspace > Tools > gear icon."""

        base_url: str = Field(
            "http://paperless-ngx:8000",
            description="Paperless-ngx instance URL (no trailing slash)",
        )
        api_token: str = Field(
            "",
            description="Paperless-ngx API token",
            json_schema_extra={"input": {"type": "password"}},
        )
        request_timeout: float = Field(
            30.0,
            description="HTTP request timeout in seconds",
        )

    class UserValves(BaseModel):
        """Per-user settings — each user can adjust these in the chat interface."""

        max_results: int = Field(
            10,
            description="Maximum number of documents to return per search (1-25)",
            ge=1,
            le=25,
        )

    # -------------------------------------------------------------------------
    # Tool: search_documents
    # -------------------------------------------------------------------------
    async def search_documents(
        self,
        query: str,
        tag: Optional[str] = None,
        correspondent: Optional[str] = None,
        document_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        __user__: dict = {},
        __event_emitter__=None,
    ) -> str:
        """
        Search paperless-ngx documents by full-text query with optional filters.
        Use this to find documents matching keywords, filtered by tag, sender,
        type, or date range. Returns document titles, dates, and content excerpts.

        :param query: Full-text search term (e.g. "oil change", "grocery receipt", "electric bill")
        :param tag: Optional tag name to filter by (e.g. "invoice", "vehicle-maintenance")
        :param correspondent: Optional correspondent/sender name to filter by (e.g. "Valvoline", "PG&E")
        :param document_type: Optional document type to filter by (e.g. "Invoice", "Receipt", "Statement")
        :param date_from: Optional start date in YYYY-MM-DD format (e.g. "2026-03-01")
        :param date_to: Optional end date in YYYY-MM-DD format (e.g. "2026-03-31")
        """
        user_valves = __user__.get("valves", self.UserValves())

        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": f"Searching paperless-ngx for '{query}'...",
                        "done": False,
                    },
                }
            )

        params = {"query": query, "page_size": user_valves.max_results}
        if tag:
            params["tags__name__icontains"] = tag
        if correspondent:
            params["correspondent__name__icontains"] = correspondent
        if document_type:
            params["document_type__name__icontains"] = document_type
        if date_from:
            params["created__date__gt"] = date_from
        if date_to:
            params["created__date__lt"] = date_to

        data = await self._api_get("/api/documents/", params, __event_emitter__)
        if isinstance(data, str):
            return data  # error message

        results = data.get("results", [])

        # Emit citations for each document
        if __event_emitter__:
            for doc in results:
                doc_url = f"{self.valves.base_url}/documents/{doc['id']}/details"
                await __event_emitter__(
                    {
                        "type": "citation",
                        "data": {
                            "document": [doc.get("content", "")[:500]],
                            "metadata": [
                                {
                                    "date_accessed": datetime.now().isoformat(),
                                    "source": doc.get("title", f"Document {doc['id']}"),
                                    "url": doc_url,
                                }
                            ],
                            "source": {
                                "name": doc.get("title", f"Document {doc['id']}"),
                                "url": doc_url,
                            },
                        },
                    }
                )
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": f"Found {data.get('count', 0)} documents",
                        "done": True,
                    },
                }
            )

        if not results:
            filters = []
            if tag:
                filters.append(f"tag '{tag}'")
            if correspondent:
                filters.append(f"correspondent '{correspondent}'")
            if document_type:
                filters.append(f"type '{document_type}'")
            if date_from or date_to:
                filters.append(f"date range {date_from or '...'} to {date_to or '...'}")
            filter_str = f" with filters: {', '.join(filters)}" if filters else ""
            return f"No documents found matching '{query}'{filter_str}."

        lines = [f"Found {data['count']} document(s) (showing {len(results)}):"]
        for doc in results:
            title = doc.get("title", f"Document {doc['id']}")
            created = doc.get("created", "unknown date")[:10]
            correspondent_name = ""
            if doc.get("correspondent"):
                correspondent_name = f" | from: correspondent ID {doc['correspondent']}"
            content = doc.get("content", "")[:2000]

            lines.append(f"\n### {title}")
            lines.append(f"**Date:** {created}{correspondent_name}")
            lines.append(f"**Content:**\n{content}")
            lines.append("---")

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Tool: get_document
    # -------------------------------------------------------------------------
    async def get_document(
        self,
        document_id: int,
        __event_emitter__=None,
    ) -> str:
        """
        Retrieve the full content of a specific paperless-ngx document by its ID.
        Use this when you need the complete text of a document found in a previous search.

        :param document_id: The numeric ID of the document to retrieve
        """
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": f"Retrieving document {document_id}...",
                        "done": False,
                    },
                }
            )

        data = await self._api_get(
            f"/api/documents/{document_id}/", {}, __event_emitter__
        )
        if isinstance(data, str):
            return data

        title = data.get("title", f"Document {document_id}")
        created = data.get("created", "unknown")[:10]
        content = data.get("content", "(no content)")

        if __event_emitter__:
            doc_url = f"{self.valves.base_url}/documents/{document_id}/details"
            await __event_emitter__(
                {
                    "type": "citation",
                    "data": {
                        "document": [content[:500]],
                        "metadata": [
                            {
                                "date_accessed": datetime.now().isoformat(),
                                "source": title,
                                "url": doc_url,
                            }
                        ],
                        "source": {"name": title, "url": doc_url},
                    },
                }
            )
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {"description": f"Retrieved: {title}", "done": True},
                }
            )

        return f"# {title}\n**Date:** {created}\n\n{content}"

    # -------------------------------------------------------------------------
    # Tool: list_tags
    # -------------------------------------------------------------------------
    async def list_tags(
        self,
        __event_emitter__=None,
    ) -> str:
        """
        List all tags available in paperless-ngx. Use this to discover
        what tags exist before filtering a search by tag name.
        """
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {"description": "Fetching tags...", "done": False},
                }
            )

        data = await self._api_get(
            "/api/tags/", {"page_size": 100}, __event_emitter__
        )
        if isinstance(data, str):
            return data

        results = data.get("results", [])

        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": f"Found {len(results)} tags",
                        "done": True,
                    },
                }
            )

        if not results:
            return "No tags found in paperless-ngx."

        lines = [f"Available tags ({len(results)}):"]
        for tag in sorted(results, key=lambda t: t.get("name", "")):
            count = tag.get("document_count", 0)
            lines.append(f"- **{tag['name']}** ({count} documents)")

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Tool: list_correspondents
    # -------------------------------------------------------------------------
    async def list_correspondents(
        self,
        __event_emitter__=None,
    ) -> str:
        """
        List all correspondents (senders/organizations) in paperless-ngx.
        Use this to discover known correspondents before filtering a search.
        """
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": "Fetching correspondents...",
                        "done": False,
                    },
                }
            )

        data = await self._api_get(
            "/api/correspondents/", {"page_size": 100}, __event_emitter__
        )
        if isinstance(data, str):
            return data

        results = data.get("results", [])

        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": f"Found {len(results)} correspondents",
                        "done": True,
                    },
                }
            )

        if not results:
            return "No correspondents found in paperless-ngx."

        lines = [f"Known correspondents ({len(results)}):"]
        for c in sorted(results, key=lambda c: c.get("name", "")):
            count = c.get("document_count", 0)
            lines.append(f"- **{c['name']}** ({count} documents)")

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Tool: list_document_types
    # -------------------------------------------------------------------------
    async def list_document_types(
        self,
        __event_emitter__=None,
    ) -> str:
        """
        List all document types in paperless-ngx. Use this to discover
        available document types before filtering a search.
        """
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": "Fetching document types...",
                        "done": False,
                    },
                }
            )

        data = await self._api_get(
            "/api/document_types/", {"page_size": 100}, __event_emitter__
        )
        if isinstance(data, str):
            return data

        results = data.get("results", [])

        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": f"Found {len(results)} document types",
                        "done": True,
                    },
                }
            )

        if not results:
            return "No document types found in paperless-ngx."

        lines = [f"Document types ({len(results)}):"]
        for dt in sorted(results, key=lambda d: d.get("name", "")):
            count = dt.get("document_count", 0)
            lines.append(f"- **{dt['name']}** ({count} documents)")

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Internal helper
    # -------------------------------------------------------------------------
    async def _api_get(self, path: str, params: dict, event_emitter=None) -> dict:
        """Make an authenticated GET request to the paperless-ngx API."""
        headers = {
            "Authorization": f"Token {self.valves.api_token}",
            "Accept": "application/json",
        }
        url = f"{self.valves.base_url}{path}"

        try:
            async with httpx.AsyncClient(
                timeout=self.valves.request_timeout
            ) as client:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            msg = f"Paperless API error: HTTP {e.response.status_code}"
            if e.response.status_code == 403:
                msg += " (check API token permissions)"
            if event_emitter:
                await event_emitter(
                    {
                        "type": "status",
                        "data": {"description": msg, "done": True},
                    }
                )
            return msg
        except httpx.ConnectError:
            msg = f"Cannot connect to paperless-ngx at {self.valves.base_url}"
            if event_emitter:
                await event_emitter(
                    {
                        "type": "status",
                        "data": {"description": msg, "done": True},
                    }
                )
            return msg
        except Exception as e:
            msg = f"Error querying paperless-ngx: {e}"
            if event_emitter:
                await event_emitter(
                    {
                        "type": "status",
                        "data": {"description": msg, "done": True},
                    }
                )
            return msg
