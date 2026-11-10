import unittest
import test_button_look as fixture
from button_look import begin_button_look

class Tests(unittest.TestCase):
    def setup_pose(self,body,pitch,roll):
        b,c=fixture.Tests().controller();c.interested_gentle_entry=True
        for sid,value in {2:body[0],3:body[1],4:roll,5:pitch}.items():b.reg[sid][42]=value
        c.rhythm_base_reference={2:c.normal[2],3:c.normal[3]}
        return b,c
    def test_happy_head_cannot_be_paired_with_normal_arms_on_button_return(self):
        b,c=self.setup_pose((2605,3046),2164,1693)
        begin_button_look(c)
        self.assertEqual(c.pose_route.return_pose,c.normal)
    def test_existing_interested_head_is_rebased_when_returning_to_normal_body(self):
        b,c=fixture.Tests().controller()
        b,c=self.setup_pose((c.normal[2]-102,c.normal[3]+102),c.normal[5]-204,c.normal[4]-137)
        begin_button_look(c)
        self.assertEqual(c.pose_route.return_pose,c.normal)
    def test_small_cpg_body_offset_does_not_become_a_permanent_head_bias(self):
        b,c=fixture.Tests().controller()
        b,c=self.setup_pose((c.normal[2]-10,c.normal[3]+10),c.normal[5]-20,c.normal[4])
        begin_button_look(c)
        self.assertEqual(c.pose_route.return_pose[5],c.normal[5])
    def test_sleepy_saves_the_same_coordinated_awake_reference_from_happy(self):
        import test_three_state_behavior as behavior_fixture
        from three_state_behavior import handle_state_key
        m,b=behavior_fixture.Tests().motor();c=m.controller
        c.interested_gentle_entry=True;m.behavior_trial='happy'
        for sid,value in {2:2605,3:3046,4:1693,5:2164}.items():b.reg[sid][42]=value
        c.rhythm_base_reference={2:c.normal[2],3:c.normal[3]}
        handle_state_key(m,ord('s'))
        self.assertEqual(c.player_view_reference,c.normal)

if __name__=='__main__':unittest.main()
