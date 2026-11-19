"""Domain packs: one per kind of code daya can generate."""

from . import intodo_view, web, webxdc

DOMAINS = {"web": web, "webxdc": webxdc, "intodo-view": intodo_view}
