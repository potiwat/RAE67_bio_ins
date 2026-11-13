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
    # TODO 1: touch should enter happy from any state except afraid.
    # TODO 2: timeout should return interested/happy to normal.
    # TODO 3: idle should change normal to sleepy.
    # Keep unrelated combinations as None. Test and explain every table row.
    return None
