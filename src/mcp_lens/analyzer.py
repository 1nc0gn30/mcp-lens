"""MCP Traffic Analyzer, Token Weight Auditor & Schema Minifier.

Engineered by Neal Frazier Tech (@1nc0gn30) • NullAI Platform.
100% Python Standard Library — Zero External Dependencies.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


def estimate_tokens(text: Any) -> int:
    """Accurately estimate BPE tokens for JSON schemas and code text.
    
    Standard BPE tokenizers (cl100k_base / o200k_base) average ~3.6 - 4.0 characters
    per token on English prose, and ~2.8 - 3.2 characters per token on dense punctuation
    and structured JSON syntax.
    """
    if text is None:
        return 0
    if isinstance(text, (dict, list)):
        text = json.dumps(text)
    elif not isinstance(text, str):
        text = str(text)
    if not text:
        return 0
    # Clean whitespace runs
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return 0
    # Count punctuation characters (which typically form individual single-character tokens)
    punct_count = len(re.findall(r'[{}\[\]":,._\-/\\<>!@#$%^&*()+=|;]', cleaned))
    # Count alphanumeric words
    words = re.findall(r"[a-zA-Z0-9]+", cleaned)
    word_tokens = sum(max(1, (len(w) + 2) // 4) for w in words)
    # Weighted BPE heuristic
    estimated = int(punct_count * 0.95 + word_tokens * 1.05)
    return max(1, estimated)


@dataclass
class ToolTokenWeight:
    name: str
    description: str
    total_tokens: int
    name_tokens: int
    description_tokens: int
    schema_tokens: int
    minified_tokens: int
    tokens_saved: int
    savings_percent: float
    raw_schema: Dict[str, Any]
    minified_schema: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SchemaMinifier:
    """Aggressively optimizes and strips non-essential prompt overhead from MCP tool schemas."""

    @staticmethod
    def minify_tool_schema(raw_tool: Dict[str, Any]) -> Dict[str, Any]:
        """Minify tool schema and return just the minified dictionary."""
        minified, _, _ = SchemaMinifier.minify_schema(raw_tool)
        return minified

    @staticmethod
    def minify_schema(raw_tool: Dict[str, Any]) -> Tuple[Dict[str, Any], int, int]:
        """Minify tool schema while preserving argument typing and required fields.
        
        Returns:
            Tuple of (minified_tool_dict, original_tokens, minified_tokens)
        """
        orig_json = json.dumps(raw_tool, separators=(",", ":"))
        orig_tokens = estimate_tokens(orig_json)

        minified = copy.deepcopy(raw_tool)

        # 1. Truncate / streamline tool description
        desc = minified.get("description", "")
        if desc:
            # Keep only the primary summary line (strip long multi-paragraph examples)
            first_line = desc.strip().split("\n")[0].strip()
            if len(first_line) > 120:
                first_line = first_line[:117] + "..."
            minified["description"] = first_line

        # 2. Optimize inputSchema
        schema = minified.get("inputSchema", minified.get("parameters", {}))
        if isinstance(schema, dict):
            minified_schema = SchemaMinifier._clean_json_schema(schema)
            if "inputSchema" in minified:
                minified["inputSchema"] = minified_schema
            elif "parameters" in minified:
                minified["parameters"] = minified_schema

        min_json = json.dumps(minified, separators=(",", ":"))
        min_tokens = estimate_tokens(min_json)
        return minified, orig_tokens, min_tokens

    @staticmethod
    def _clean_json_schema(schema_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively strip redundant metadata from JSON schema properties."""
        cleaned: Dict[str, Any] = {}

        # Preserve structural keys
        for key in ["type", "required", "properties", "items", "enum"]:
            if key in schema_dict:
                cleaned[key] = schema_dict[key]

        # Optimize properties
        if "properties" in cleaned and isinstance(cleaned["properties"], dict):
            new_props = {}
            for prop_name, prop_val in cleaned["properties"].items():
                if isinstance(prop_val, dict):
                    prop_clean = {}
                    for p_key, p_val in prop_val.items():
                        # Exclude verbose documentation bloat
                        if p_key in ("examples", "default", "title", "$schema", "additionalProperties"):
                            continue
                        elif p_key == "description":
                            # Strip description if it just repeats property name
                            if str(p_val).strip().lower() in (prop_name.lower(), f"the {prop_name.lower()}"):
                                continue
                            # Truncate overly verbose param descriptions
                            short_desc = str(p_val).strip().split(".")[0].strip()
                            if len(short_desc) > 80:
                                short_desc = short_desc[:77] + "..."
                            prop_clean["description"] = short_desc
                        elif p_key in ("properties", "items"):
                            prop_clean[p_key] = SchemaMinifier._clean_json_schema(p_val) if isinstance(p_val, dict) else p_val
                        else:
                            prop_clean[p_key] = p_val
                    new_props[prop_name] = prop_clean
                else:
                    new_props[prop_name] = prop_val
            cleaned["properties"] = new_props

        return cleaned


class MCPTrafficAnalyzer:
    """Parses, validates, and audits JSON-RPC 2.0 frames for Model Context Protocol."""

    estimate_tokens = staticmethod(estimate_tokens)

    @staticmethod
    def parse_frame(line: str) -> Optional[Dict[str, Any]]:
        """Parse and structure a single JSON-RPC frame line."""
        text = line.strip()
        if not text or not (text.startswith("{") and text.endswith("}")):
            return None

        try:
            data = json.loads(text)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        return data

    @staticmethod
    def categorize_frame(data: Dict[str, Any]) -> Dict[str, Any]:
        """Classify JSON-RPC frame into protocol categories and compute metadata."""
        is_rpc = data.get("jsonrpc") == "2.0"
        frame_id = data.get("id")
        method = data.get("method")
        has_result = "result" in data
        has_error = "error" in data

        if method:
            frame_type = "request" if frame_id is not None else "notification"
        elif has_result:
            frame_type = "response"
        elif has_error:
            frame_type = "error"
        else:
            frame_type = "unknown"

        # Determine method / event category
        primary_topic = method or "response"
        if has_error:
            primary_topic = "error"

        raw_str = json.dumps(data)
        tokens = estimate_tokens(raw_str)

        return {
            "is_valid_rpc": is_rpc,
            "id": frame_id,
            "frame_type": frame_type,
            "method": method,
            "primary_topic": primary_topic,
            "has_error": has_error,
            "byte_size": len(raw_str.encode("utf-8")),
            "char_count": len(raw_str),
            "estimated_tokens": tokens,
            "error_message": data.get("error", {}).get("message") if has_error else None,
        }

    @staticmethod
    def audit_tool(tool: Dict[str, Any]) -> ToolTokenWeight:
        """Calculate complete token weight breakdown and potential optimization for a tool."""
        name = str(tool.get("name", "unnamed_tool"))
        desc = str(tool.get("description", ""))
        schema = tool.get("inputSchema", tool.get("parameters", {}))

        name_tok = estimate_tokens(name)
        desc_tok = estimate_tokens(desc)
        schema_tok = estimate_tokens(json.dumps(schema))
        total_tok = estimate_tokens(json.dumps(tool))

        minified, orig_tok, min_tok = SchemaMinifier.minify_schema(tool)
        saved = max(0, orig_tok - min_tok)
        pct = round((saved / orig_tok) * 100.0, 1) if orig_tok > 0 else 0.0

        return ToolTokenWeight(
            name=name,
            description=desc,
            total_tokens=total_tok,
            name_tokens=name_tok,
            description_tokens=desc_tok,
            schema_tokens=schema_tok,
            minified_tokens=min_tok,
            tokens_saved=saved,
            savings_percent=pct,
            raw_schema=tool,
            minified_schema=minified,
        )

    @staticmethod
    def audit_tools_list(tools_result: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Audit an entire collection of discovered tools."""
        weights: List[ToolTokenWeight] = []
        total_raw = 0
        total_minified = 0

        for t in tools_result:
            if isinstance(t, dict):
                w = MCPTrafficAnalyzer.audit_tool(t)
                weights.append(w)
                total_raw += w.total_tokens
                total_minified += w.minified_tokens

        total_saved = max(0, total_raw - total_minified)
        pct = round((total_saved / total_raw) * 100.0, 1) if total_raw > 0 else 0.0

        return {
            "total_tools": len(weights),
            "tool_count": len(weights),
            "total_tokens_raw": total_raw,
            "total_tokens_minified": total_minified,
            "total_tokens_saved": total_saved,
            "overall_savings_percent": pct,
            "tools": [w.to_dict() for w in weights],
        }
