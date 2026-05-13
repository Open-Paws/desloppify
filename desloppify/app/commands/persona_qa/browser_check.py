"""Check for browser automation tools available to the agent.

Detects Playwright MCP, browser-use, or other browser tools and provides
install instructions if none are found.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)


class BrowserCheckResult(TypedDict, total=False):
    available: bool
    tool: str | None
    install_instructions: str
    npx_available: bool

_PLAYWRIGHT_MCP_INSTALL = """\
Browser tools required for persona QA. Install Playwright MCP server:

# For Claude Code: add to your MCP config (~/.claude/settings.json or project .claude/settings.json)
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@anthropic-ai/mcp-playwright"]
    }
  }
}

# Or install globally:
npm install -g @anthropic-ai/mcp-playwright

# For other agents with existing browser tools (Playwright, Puppeteer, Selenium):
# persona-qa will generate instructions compatible with any browser automation tool.
# Just ensure your agent has browser navigation, clicking, and screenshot capabilities.
"""


def check_browser_tools() -> BrowserCheckResult:
    """Check if browser automation tools are available.

    Returns a dict with:
      - available: bool — whether any browser tool was detected
      - tool: str | None — name of the detected tool
      - install_instructions: str — instructions to install if missing
    """
    # Check for Playwright MCP in Claude settings
    claude_settings_paths = [
        Path.home() / ".claude" / "settings.json",
        Path.home() / ".claude" / "settings.local.json",
        Path(".claude") / "settings.json",
        Path(".claude") / "settings.local.json",
    ]

    for settings_path in claude_settings_paths:
        if settings_path.exists():
            try:
                settings = json.loads(
                    settings_path.read_text(encoding="utf-8", errors="replace")
                )
                mcp_servers = settings.get("mcpServers", {})
                if any(
                    "playwright" in name.lower() for name in mcp_servers
                ):
                    return {
                        "available": True,
                        "tool": "playwright-mcp",
                        "install_instructions": "",
                    }
            except (OSError, json.JSONDecodeError) as exc:
                logger.debug("Could not read %s: %s", settings_path, exc)
                continue

    # Check for Playwright Python package
    try:
        import importlib

        importlib.import_module("playwright")
        return {
            "available": True,
            "tool": "playwright-python",
            "install_instructions": "",
        }
    except ImportError:
        logger.debug("playwright Python package not installed")

    # Check for npx availability (for Playwright MCP)
    if shutil.which("npx"):
        return {
            "available": False,
            "tool": None,
            "install_instructions": _PLAYWRIGHT_MCP_INSTALL,
            "npx_available": True,
        }

    return {
        "available": False,
        "tool": None,
        "install_instructions": _PLAYWRIGHT_MCP_INSTALL,
        "npx_available": False,
    }
