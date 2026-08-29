"""Commentary layer: sequence graph, TTS validation, post-arbitration director.

Sits on accepted Event Engine envelopes. Does not own scene switching or overlay
pixels. Texts are authored offline into the graph; this package owns structure
and playback policy.
"""

from irswitch.commentary.assignments import render_assignments
from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.graph import SequenceGraph, load_sequence_graph
from irswitch.commentary.tts import NullTtsSink, TtsSink, build_tts_sink, speak_text
from irswitch.commentary.validator import ValidationIssue, validate_utterance

__all__ = [
    "CommentaryDirector",
    "NullTtsSink",
    "SequenceGraph",
    "TtsSink",
    "build_tts_sink",
    "speak_text",
    "ValidationIssue",
    "load_sequence_graph",
    "render_assignments",
    "validate_utterance",
]
