import unittest

from src.infra.vkdb.join import extract_material_id_from_landscape_video


class TestVkdbMySqlJoin(unittest.TestCase):
    def test_tos_mp4(self) -> None:
        url = "tos://mindsync-lop-user/common/qianchuan/materials/2025/11/22/7549416067249274934.mp4"
        self.assertEqual(extract_material_id_from_landscape_video(url), "7549416067249274934")

    def test_https_mp4_with_query(self) -> None:
        url = "https://example.com/path/7549416067249274934.mp4?x=1&y=2"
        self.assertEqual(extract_material_id_from_landscape_video(url), "7549416067249274934")

    def test_missing_mp4(self) -> None:
        url = "tos://bucket/path/7549416067249274934"
        self.assertIsNone(extract_material_id_from_landscape_video(url))

    def test_non_digit_material_id(self) -> None:
        url = "https://example.com/path/abc123.mp4"
        self.assertIsNone(extract_material_id_from_landscape_video(url))


if __name__ == "__main__":
    unittest.main()


