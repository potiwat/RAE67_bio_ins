import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from roll_detection import original_box, detect_faces


class GeometryTests(unittest.TestCase):
    def test_inverse_maps_all_four_corners_not_only_top_left(self):
        box = original_box((10, 20, 30, 40), ((0, -1, 100), (1, 0, 0)), 100, 100)
        self.assertEqual(box, (40, 10, 40, 30))

    def test_clips_to_real_image_and_discards_outside_boxes(self):
        identity = ((1, 0, 0), (0, 1, 0))
        self.assertEqual(original_box((-10, -10, 20, 20), identity, 100, 100), (0, 0, 10, 10))
        self.assertIsNone(original_box((110, 10, 10, 10), identity, 100, 100))


class Image:
    shape = (100, 100)
    def __init__(self, angle=0): self.angle = angle


class OpenCVBoundary:
    INTER_LINEAR = 1
    BORDER_REPLICATE = 1
    def getRotationMatrix2D(self, centre, angle, scale): return angle
    def warpAffine(self, image, matrix, size, **kwargs): return Image(matrix)
    def invertAffineTransform(self, matrix): return ((1, 0, 0), (0, 1, 0))


class Detector:
    def __init__(self, boxes): self.boxes, self.calls = boxes, []
    def detectMultiScale(self, image, scale, neighbours):
        self.calls.append(image.angle)
        return self.boxes.get(image.angle, [])


class FallbackTests(unittest.TestCase):
    def test_normal_detection_does_not_repeat_or_duplicate_target(self):
        detector = Detector({0: [(10, 20, 30, 40)]})
        self.assertEqual(detect_faces(Image(), detector, OpenCVBoundary(), (-15, 15)),
                         [(10, 20, 30, 40)])
        self.assertEqual(detector.calls, [0])

    def test_roll_fallback_finds_face_missing_in_upright_pass(self):
        detector = Detector({15: [(10, 20, 30, 40)]})
        self.assertEqual(detect_faces(Image(), detector, OpenCVBoundary(), (-15, 15)),
                         [(10, 20, 30, 40)])
        self.assertEqual(detector.calls, [0, -15, 15])

    def test_disabled_fallback_preserves_original_cost_and_behavior(self):
        detector = Detector({15: [(10, 20, 30, 40)]})
        self.assertEqual(detect_faces(Image(), detector, OpenCVBoundary()), [])
        self.assertEqual(detector.calls, [0])


if __name__ == '__main__':
    unittest.main()
