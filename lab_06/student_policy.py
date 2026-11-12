"""Student assignment: complete an explicit transition table.

All mappings are a proposed course model. The engine already implements sensor
guards, bounded movement/RGB and output scheduling. Edit only this function.
Return a state name, or None when the event has no transition.
"""


def transition(current_state: str, event: str) -> str | None:
    if event == "fault":
        return "normal"
    if event == "near":
        return "afraid"
    if event == "clear":
        return "normal"
    if current_state == "afraid":
        return None
    if event in ("button", "approach"):
        return "interested"
    # touch enters happy from any state except afraid (afraid handled above).
    if event == "touch":
        return "happy"
    # timeout returns only interested/happy to normal.
    if event == "timeout":
        return "normal" if current_state in ("interested", "happy") else None
    # idle changes only normal to sleepy.
    if event == "idle":
        return "sleepy" if current_state == "normal" else None
    # Unrelated combinations have no transition.
    return None
