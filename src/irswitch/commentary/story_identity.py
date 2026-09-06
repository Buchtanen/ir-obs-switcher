"""Parent-aware edge identity shared by live selection and history composition."""

from irswitch.commentary.graph import EdgeIdentityPolicy, GraphEdge
from irswitch.events.envelope import EventEnvelope


def edge_identity_matches(edge: GraphEdge, previous: EventEnvelope, current: EventEnvelope) -> bool:
    if edge.identity is EdgeIdentityPolicy.ANY:
        return True
    left, right = previous.metrics, current.metrics
    if edge.identity is EdgeIdentityPolicy.SAME_CORRELATION:
        return bool(previous.correlation_id) and previous.correlation_id == current.correlation_id
    if (
        not previous.session_id
        or previous.session_id != current.session_id
        or previous.subject.car_id != current.subject.car_id
        or left.get("runEpoch") != right.get("runEpoch")
    ):
        return False
    parent = left.get("parentStoryId")
    if edge.identity is EdgeIdentityPolicy.SAME_PARENT_STORY:
        return bool(
            parent
            and parent == right.get("parentStoryId")
            and left.get("scenarioId")
            and left.get("scenarioId") == right.get("scenarioId")
        )
    if edge.identity is EdgeIdentityPolicy.CAUSED_BY_PARENT_STORY:
        return bool(parent and parent == right.get("causedByParentStoryId"))
    return edge.identity is EdgeIdentityPolicy.SAME_RUN
