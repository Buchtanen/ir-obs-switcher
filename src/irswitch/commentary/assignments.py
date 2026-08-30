"""Turn the sequence-graph structure into authoring briefs for a text model."""

from __future__ import annotations

from irswitch.commentary.graph import GraphNode, SequenceGraph, load_sequence_graph
from irswitch.overlay.i18n import CATALOGS

_FAMILY_OVERLAY_HINTS: dict[str, tuple[str, ...]] = {
    "timing": ("lap.complete", "lap.personal_best"),
    "battle": ("battle.hunting", "battle.hunted", "battle.side_by_side"),
    "position": ("position.gained", "position.lost", "position.overtake"),
    "exception": ("incident",),
    "session": ("session.final_lap", "session.finish"),
    "pit": ("pit.entry", "pit.exit", "pit.outcome"),
    "bio": ("bio.hr_pressure", "bio.hr_high"),
}

_EMOTION_HINTS: dict[str, str] = {
    "neutral": "No usable HR (BLE missing/disconnected) or calm baseline. Even pace, no fake adrenaline.",
    "calm": "HR delta in calm band. Quiet, economical line.",
    "focused": "HR in focused band. Crisp, still controlled.",
    "pushing": "HR in pushing band. Sharper rhythm, still one sentence.",
    "high": "HR in high band. Intensity in wording, not volume. No ALL-CAPS.",
}


def render_assignments(
    graph: SequenceGraph | None = None,
    *,
    locale: str | None = None,
    only_unfilled: bool = True,
) -> str:
    """Markdown briefs. Default graph is structure-only (empty variants)."""
    loaded = graph or load_sequence_graph()
    locales = (locale,) if locale else loaded.locales
    blocks: list[str] = [
        "# Commentary text assignments",
        "",
        "Fill spoken variants only. Do not change node ids, slots, edges, or TTS limits.",
        "Each line must pass `validate_utterance` (terminal punctuation, no ALL-CAPS,",
        "no stacked !!/??/..., limited SSML: break + emphasis).",
        "",
        f"Graph version: {loaded.version}. Locales: {', '.join(loaded.locales)}.",
        f"Unfilled cells: {len(loaded.unfilled_cells())}.",
        "",
    ]
    for node in sorted(loaded.nodes.values(), key=lambda item: (-item.speak_priority, item.id)):
        for loc in locales:
            emotions = _emotions_for(node, loc, only_unfilled=only_unfilled)
            if not emotions:
                continue
            blocks.append(_render_node(loaded, node, loc, emotions))
    return "\n".join(blocks).rstrip() + "\n"


def _emotions_for(node: GraphNode, locale: str, *, only_unfilled: bool) -> list[str]:
    wanted: list[str] = []
    seen: set[str] = set()
    locale_map = node.variants.get(locale) or {}
    for hr_state in node.hr_states:
        bucket = "neutral" if hr_state == "unknown" else hr_state
        if bucket in seen:
            continue
        seen.add(bucket)
        # Authored cell only — do not treat EN/neutral playback fallback as filled.
        filled = bool(locale_map.get(bucket) or locale_map.get(hr_state))
        if only_unfilled and filled:
            continue
        wanted.append(bucket)
    return wanted


def _render_node(
    graph: SequenceGraph,
    node: GraphNode,
    locale: str,
    emotions: list[str],
) -> str:
    slots = (
        "\n".join(
            f"- `{{{slot.name}}}` ({slot.type}) example: {slot.example}" for slot in node.slots
        )
        or "- (no slots)"
    )
    prev = ", ".join(edge.source for edge in graph.incoming(node.id)) or "(start)"
    nxt = ", ".join(edge.target for edge in graph.outgoing(node.id)) or "(end)"
    overlay = _overlay_hints(node.family, locale)
    emotion_lines = "\n".join(
        f"- **{emotion}**: {_EMOTION_HINTS.get(emotion, '')}" for emotion in emotions
    )
    return "\n".join(
        [
            f"## `{node.id}` — {locale} / {', '.join(emotions)}",
            "",
            f"- family: `{node.family}`",
            f"- event types: {', '.join(node.event_types)}",
            f"- phases: {', '.join(node.phases)}",
            f"- speak_priority: {node.speak_priority} (voice budget; overlay priorities stay separate)",
            f"- cooldown_s: {node.cooldown_s}",
            f"- TTS: max {node.tts.max_chars} chars, {node.tts.max_seconds}s, "
            f"SSML {', '.join(node.tts.ssml_allowed) or 'none'}",
            f"- sequence: previous {prev} → next {nxt}",
            "",
            "### Slots",
            slots,
            "",
            "### Emotion variants to write",
            emotion_lines,
            "",
            "### Overlay tokens (visual only — do not copy as speech)",
            overlay,
            "",
            "### Author notes",
            node.notes or "(none)",
            "",
            "### Deliver",
            "Viewer-facing third-person broadcast. Never address the driver in second person.",
            "Use slots verbatim (`{position}`). One breath. Terminal `.` `!` or `?`.",
            "",
        ]
    )


def _overlay_hints(family: str, locale: str) -> str:
    catalog = CATALOGS.get(locale) or CATALOGS["en"]
    tokens = _FAMILY_OVERLAY_HINTS.get(family, ())
    if not tokens:
        return "- (none)"
    lines = []
    for token in tokens:
        label = catalog.get(token) or CATALOGS["en"].get(token) or ""
        lines.append(f"- `{token}` → {label}")
    return "\n".join(lines)
