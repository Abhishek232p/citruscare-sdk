from __future__ import annotations

import unittest
from datetime import UTC, datetime

from citruscare.clinical import ClinicalObservation


class ClinicalObservationTests(unittest.TestCase):
    def test_requires_timezone_aware_timestamp(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone"):
            ClinicalObservation(
                "heart-rate",
                70,
                "bpm",
                datetime(2025, 1, 1),
                "Patient/p-1",
            )

    def test_accepts_timezone_aware_timestamp(self) -> None:
        observation = ClinicalObservation(
            "heart-rate",
            70,
            "bpm",
            datetime(2025, 1, 1, tzinfo=UTC),
            "Patient/p-1",
        )
        self.assertEqual(observation.value, 70)


if __name__ == "__main__":
    unittest.main()
