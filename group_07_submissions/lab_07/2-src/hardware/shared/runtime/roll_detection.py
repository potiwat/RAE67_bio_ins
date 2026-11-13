"""Optional image roll compensation for the existing frontal Haar detector."""


def original_box(rect, inverse, width, height):
    x, y, w, h = rect
    corners = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
    xs = [inverse[0][0] * a + inverse[0][1] * b + inverse[0][2] for a, b in corners]
    ys = [inverse[1][0] * a + inverse[1][1] * b + inverse[1][2] for a, b in corners]
    left, right = max(0., min(xs)), min(float(width), max(xs))
    top, bottom = max(0., min(ys)), min(float(height), max(ys))
    if right <= left or bottom <= top:
        return None
    return left, top, right - left, bottom - top


def detect_faces(grey, detector, cv2, angles=()):
    rectangles = list(detector.detectMultiScale(grey, 1.1, 3))
    if rectangles or not angles:
        return rectangles
    height, width = grey.shape[:2]
    for angle in angles:
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.)
        rotated = cv2.warpAffine(grey, matrix, (width, height),
                                 flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        candidates = detector.detectMultiScale(rotated, 1.1, 3)
        inverse = cv2.invertAffineTransform(matrix)
        mapped = [original_box(rect, inverse, width, height) for rect in candidates]
        mapped = [box for box in mapped if box is not None]
        if mapped:
            # One successful orientation only: no duplicate boxes across passes.
            return mapped
    return []
