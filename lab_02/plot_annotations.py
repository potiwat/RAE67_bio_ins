"""Find physical threshold crossings and their first correct responses."""


def response_markers(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    """Pair each expected-state change with the first matching controller state."""
    if not rows:
        return []

    markers = []
    previous_expected = rows[0]["expected_state"]
    for index, row in enumerate(rows[1:], start=1):
        expected = row["expected_state"]
        if expected == previous_expected:
            continue

        response_time = None
        for candidate in rows[index:]:
            if candidate["state"] == expected:
                response_time = float(candidate["time_s"])
                break

        markers.append({
            "kind": "enter" if expected == "NEAR" else "exit",
            "physical_time_s": float(row["time_s"]),
            "response_time_s": response_time,
        })
        previous_expected = expected
    return markers
