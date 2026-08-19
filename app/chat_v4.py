from __future__ import annotations

# Compatibility bridge while V3.6 chat orchestration remains the stable retrieval/answer shell.
# The function object in app.chat resolves its module globals at call time, so replacing these
# two routing hooks makes the live API use V4 cognition/routing without duplicating the chat stack.
from . import chat as _legacy_chat
from .routing_guard import apply_case_route, route_query

_legacy_chat.analyze_query = route_query
_legacy_chat._apply_cognition_to_route = apply_case_route

handle_chat = _legacy_chat.handle_chat

__all__ = ["handle_chat"]
