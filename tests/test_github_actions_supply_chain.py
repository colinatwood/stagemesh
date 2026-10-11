import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
REMOTE_ACTION = re.compile(r"^\s*-?\s*uses:\s*([^\s@]+)@([^\s#]+)", re.MULTILINE)
IMMUTABLE_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class GitHubActionsSupplyChainTests(unittest.TestCase):
    def test_remote_actions_are_pinned_to_full_commit_shas(self):
        workflow_paths = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
        self.assertTrue(workflow_paths, "no GitHub Actions workflows found")

        mutable = []
        actions = 0
        for path in workflow_paths:
            for action, ref in REMOTE_ACTION.findall(path.read_text(encoding="utf-8")):
                if action.startswith("./") or action.startswith("docker://"):
                    continue
                actions += 1
                if not IMMUTABLE_COMMIT.fullmatch(ref):
                    mutable.append(f"{path.relative_to(ROOT)}: {action}@{ref}")

        self.assertGreater(actions, 0, "no remote GitHub Actions references found")
        self.assertEqual([], mutable, "mutable GitHub Actions references:\n" + "\n".join(mutable))

    def test_dependabot_tracks_pinned_github_actions(self):
        config = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        self.assertRegex(config, r"(?m)^\s*- package-ecosystem:\s*github-actions\s*$")
        self.assertRegex(config, r"(?m)^\s*directory:\s*/\s*$")


if __name__ == "__main__":
    unittest.main()
