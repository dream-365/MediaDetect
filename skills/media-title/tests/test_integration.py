import os
import tempfile
import unittest

from helpers import SCRIPTS_DIR  # noqa: F401

from media_title_lib.apply import apply_plan
from media_title_lib.plan import build_plan
from media_title_lib.rollback import rollback_plan
from media_title_lib.scan import scan_path


MD_BIN = os.environ.get("MD_BIN")


@unittest.skipUnless(MD_BIN, "set MD_BIN to run the real-CLI integration test")
class IntegrationTests(unittest.TestCase):
    def test_tv_scan_plan_apply_rollback(self):
        with tempfile.TemporaryDirectory() as root:
            flat = os.path.join(root, "Some.Show.S01.1080p")
            os.makedirs(flat)
            for name in ("Some.Show.S01E01.mkv", "Some.Show.S01E02.mkv"):
                with open(os.path.join(flat, name), "w") as fh:
                    fh.write("x")
            scan = scan_path(flat, md_bin=MD_BIN, match="off")
            self.assertEqual(len(scan["units"]), 1)
            plan = build_plan(scan)
            self.assertEqual(len(plan["units"]), 1)
            apply_plan(plan, plan["plan_id"], "all")
            target = os.path.join(root, "Some Show", "Season 01", "Some.Show.S01E01.mkv")
            self.assertTrue(os.path.exists(target))
            rollback_plan(plan, plan["plan_id"], "all")
            self.assertTrue(os.path.exists(os.path.join(flat, "Some.Show.S01E01.mkv")))


if __name__ == "__main__":
    unittest.main()
