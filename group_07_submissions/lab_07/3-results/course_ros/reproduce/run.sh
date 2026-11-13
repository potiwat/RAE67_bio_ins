#!/usr/bin/env bash
set -eo pipefail
lab_src="$(cd -- "$(dirname "$0")" && pwd -P)"
if test "$#" -gt 1; then echo 'Usage: bash run.sh [new workspace directory]' >&2; exit 2; fi
if test "$#" -eq 1; then
  mkdir -- "$1"
  lab_workspace="$(cd -- "$1" && pwd -P)"
else
  lab_workspace="$(mktemp -d "$PWD/course_ros_XXXXXX")"
fi
mkdir -p "$lab_workspace/src/lamp_week07" "$lab_workspace/session" "$lab_workspace/ros_home/log"
cp -R "$lab_src/upstream/." "$lab_workspace/src/lamp_week07/"
cp "$lab_src/completed_policy.py" "$lab_workspace/completed_policy.py"
export ROS_HOME="$lab_workspace/ros_home" ROS_LOG_DIR="$lab_workspace/ros_home/log" COLCON_HOME="$lab_workspace/colcon_home"
export ROS_DOMAIN_ID=87 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
source /opt/ros/jazzy/setup.bash
cd "$lab_workspace"
/usr/bin/python3 -B "$lab_src/fix_jazzy_trace.py" "$lab_workspace/src/lamp_week07" --record "$lab_workspace/session"
colcon build --symlink-install --packages-select lamp_week07
source "$lab_workspace/install/setup.bash"
/usr/bin/python3 -B "$lab_src/verify_wire.py" "$lab_workspace"
/usr/bin/python3 -B "$lab_src/capture_session.py" "$lab_workspace"
/usr/bin/python3 -B "$lab_src/verify_recording.py" "$lab_workspace/session"
printf 'Session files: %s/session\n' "$lab_workspace"
