import json
from pathlib import Path
from pose_route import PoseRoute
SOURCE=Path(__file__).resolve().parents[2]/'shared'/'hardware'/'button_look_observation.json'
POSE={int(k):v for k,v in json.loads(SOURCE.read_text(encoding='utf-8'))['raw_by_id'].items()}

def awake_player_reference(c,pose):
    """Rebase a coordinated head/body pose onto the ordinary awake body.

    Retain the existing empirical pitch-axis compensation signs; this is
    not Cartesian IK. Never attach a taught Happy head to unrelated arms.
    """
    player=dict(pose)
    pitch=player[5]+(c.normal[2]-player[2])-(c.normal[3]-player[3])
    low,high=c.pitch_window
    player.update({2:c.normal[2],3:c.normal[3],4:c.normal[4],5:max(low,min(high,pitch))})
    return player

def begin_button_look(controller,include_interest=True,look_at_button=True,neck_tilt=True):
    c=controller
    player=getattr(c,'player_view_reference',None)
    if player is None:
        player={i:int.from_bytes(c.bus.read(i,42,2),'little') for i in c.normal}
        if getattr(c,'interested_gentle_entry',False) is True:player=awake_player_reference(c,player)
        else:player={**player,**getattr(c,'rhythm_base_reference',{})}
    else:
        # Saved player pose is one coordinated body/head reference. In Sleepy
        # the active CPG center contains the folded elbow; overlaying that onto
        # the awake saved head recreates a downward-looking return pose.
        player=dict(player)
    steps=[];windows={}
    if include_interest:
        # One coordinated pose request; no body-only stage before head motion.
        interested={**player,2:c.normal[2]-102,3:c.normal[3]+102,
                    4:c.normal[4]-(137 if neck_tilt else 0)}
        steps=[('lean',interested)]
        # Operator-approved hold tolerance around this pose, not gaze limits.
        windows={i:(interested[i]-t,interested[i]+t) for i,t in ((2,34),(3,34),(4,22))}
        windows[5]=(getattr(c,'interest_pitch_window_request',None) or c.pitch_window) if getattr(c,'interest_head_tracking',False) else c.pitch_window
    c.pose_route=PoseRoute(c,POSE if look_at_button else player,player,steps,windows,start_post=not look_at_button,
                          button_dynamic=look_at_button and getattr(c,'button_look_dynamic_trial',False))
