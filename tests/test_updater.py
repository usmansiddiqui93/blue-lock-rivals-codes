import json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import update_codes as u

FIX = Path(__file__).parent / "fixtures"
CFG = {"min_confirmations": 2, "expire_votes": 2, "miss_runs_before_expire": 3}


def page(n):
    return u.extract((FIX / f"{n}.html").read_text())


class Extract(unittest.TestCase):
    def test_list_layout(self):
        r = page("pocket-tactics")
        self.assertEqual(set(r["active"]), {"NEWCODE1", "DONREVAMP", "SENDOUNEXT", "ACEEATER"})
        self.assertIn("OLDARCHIVE1", r["expired"])
        self.assertNotIn("LAUNCH", r["active"])

    def test_table_layout(self):
        r = page("dexerto")
        self.assertEqual(set(r["active"]), {"NEWCODE1", "DONREVAMP", "ACEEATER"})
        self.assertIn("SENDOUNEXT", r["expired"])
        self.assertNotIn("CODE", r["expired"])

    def test_reward_parse(self):
        self.assertEqual(u.parse_reward("five lucky style spins and five lucky flow spins"), (5, 5))
        self.assertEqual(u.parse_reward("5 Lucky Flows"), (0, 5))
        self.assertEqual(u.parse_reward("5 Lucky Spins"), (5, 0))

    def test_update_name(self):
        self.assertEqual(u.update_name_from_title("[🧟‍♂️ Don Lorenzo] Blue Lock: Rivals"), "Don Lorenzo")
        self.assertEqual(u.update_name_from_title("[🏆UPD] Blue Lock: Rivals"), None)


class Reconcile(unittest.TestCase):
    def setUp(self):
        self.codes = {"active": [{"code": "DONREVAMP"}, {"code": "SENDOUNEXT"}, {"code": "ACEEATER"}],
                      "expired": [{"code": "SNUFFYUPD"}, {"code": "WSNUFFY"}]}
        self.state = {"misses": {}}
        self.results = {n: page(n) for n in ("pocket-tactics", "dexerto", "bloxodes")}

    def test_consensus(self):
        rep = u.reconcile(self.codes, self.state, self.results, CFG, "2026-10-10")
        added = {a["code"]: a for a in rep["added"]}
        self.assertEqual(set(added), {"NEWCODE1"})           # 2 sources agree
        self.assertEqual((added["NEWCODE1"]["spins"], added["NEWCODE1"]["flows"]), (5, 5))
        self.assertEqual(rep["expired"], [])                 # SENDOUNEXT: only 1 expired vote
        self.assertEqual([a["code"] for a in rep["archived"]], ["OLDARCHIVE1"])

    def test_stale_source_cannot_add_alone(self):
        rep = u.reconcile(self.codes, self.state, self.results, CFG, "2026-10-10")
        self.assertNotIn("STALEONLYHERE", [a["code"] for a in rep["added"]])
        self.assertNotIn("SNUFFYSOON", [a["code"] for a in rep["added"]])

    def test_two_expired_votes_expire(self):
        self.results["bloxodes"]["expired"]["SENDOUNEXT"] = "SENDOUNEXT"
        self.results["bloxodes"]["active"].pop("SENDOUNEXT")
        rep = u.reconcile(self.codes, self.state, self.results, CFG, "2026-10-10")
        self.assertEqual([c["code"] for c, _ in rep["expired"]], ["SENDOUNEXT"])

    def test_missing_everywhere_expires_after_n_runs(self):
        self.codes["active"].append({"code": "GHOST"})
        for i in range(3):
            rep = u.reconcile(self.codes, self.state, self.results, CFG, "2026-10-10")
        self.assertIn("GHOST", [c["code"] for c, _ in rep["expired"]])

    def test_apply(self):
        rep = u.reconcile(self.codes, self.state, self.results, CFG, "2026-10-10")
        u.apply(self.codes, self.state, rep, "2026-10-10T10:00:00Z")
        self.assertEqual(self.codes["active"][0]["code"], "NEWCODE1")
        self.assertEqual(self.codes["updated"], "2026-10-10T10:00:00Z")


if __name__ == "__main__":
    unittest.main(verbosity=2)
