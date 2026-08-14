from app.services.pose_landmarks import POSE_LANDMARK_NAMES
from app.services.pose_quality import is_plausible_person


def _payload(visibility: float = 1.0, **xy: tuple[float, float]) -> dict:
    default = (0.5, 0.5)
    points = []
    for index, name in enumerate(POSE_LANDMARK_NAMES):
        x, y = xy.get(name, default)
        points.append(
            {
                "index": index,
                "name": name,
                "x": x,
                "y": y,
                "z": 0.0,
                "visibility": visibility,
            }
        )
    return {"landmarks": points, "landmark_count": 33, "confidence": visibility}


def test_rejects_low_visibility():
    payload = _payload(
        0.1,
        nose=(0.5, 0.2),
        left_shoulder=(0.44, 0.38),
        right_shoulder=(0.56, 0.38),
        left_hip=(0.46, 0.58),
        right_hip=(0.54, 0.58),
        left_ankle=(0.46, 0.90),
        right_ankle=(0.54, 0.90),
    )
    assert is_plausible_person(payload) is False


def test_rejects_clustered_false_positive():
    payload = _payload(0.9)  # all points at 0.5, 0.5
    assert is_plausible_person(payload) is False


def test_accepts_standing_person():
    payload = _payload(
        0.9,
        nose=(0.50, 0.20),
        left_shoulder=(0.44, 0.38),
        right_shoulder=(0.56, 0.38),
        left_hip=(0.46, 0.58),
        right_hip=(0.54, 0.58),
        left_ankle=(0.46, 0.90),
        right_ankle=(0.54, 0.90),
    )
    assert is_plausible_person(payload) is True
