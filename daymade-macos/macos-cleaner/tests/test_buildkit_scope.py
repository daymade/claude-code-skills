"""Calibrate the exact-record exception without contacting a Docker daemon."""

import importlib.util
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location(
    'buildkit_scope_checker', Path(__file__).resolve().parents[1] / 'scripts/check_gate_plan.py')
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class BuildkitScopeTests(unittest.TestCase):
    def test_literal_record_forms_remain_destructive_and_versioned(self):
        for command in (
            'docker buildx prune --builder cache-builder --filter id=cache-record-1',
            "docker buildx prune --filter 'id=cache-record-1' --builder=cache-builder "
            "--filter until=720h --filter type=regular --force",
            'docker buildx prune --builder cache-builder --filter=id=cache-record-1 --verbose',
        ):
            with self.subTest(command=command):
                self.assertTrue(CHECKER.exact_buildkit_record(command))
                found = CHECKER.find_destructive_commands('`' + command + '`\n')
                self.assertEqual(len(found), 1)
                self.assertFalse(found[0].category_wide)
                self.assertTrue(found[0].versioned)
                self.assertEqual(found[0].tools, ('docker', 'OrbStack'))

    def test_missing_empty_widened_and_dynamic_selectors_stay_broad(self):
        suffixes = (
            '', '--builder cache-builder', '--filter id=cache-record-1',
            '--builder "" --filter id=cache-record-1',
            '--builder cache-builder --filter id=',
            '--builder cache-builder --filter id!=cache-record-1',
            '--builder cache-builder --filter id~=cache',
            '--builder cache-builder --filter "id=*"',
            '--builder cache-builder --filter id=cache-record-1,cache-record-2',
            '--builder cache-builder --filter "id=$CACHE_RECORD"',
            '--builder cache-builder --filter "id=$(lookup-record)"',
            '--builder cache-builder --filter id=cache-record-1 --all',
            '--builder cache-builder --filter id=cache-record-1 --min-free-space 20gb',
            '--builder cache-builder --filter id=cache-record-1 --filter parents=other',
            '--builder cache-builder --filter id=cache-record-1 --filter type=',
            '--builder cache-builder --filter id=cache-record-1 --filter until=',
            '--builder cache-builder --filter id=cache-record-1 --filter',
            '--builder cache-builder --builder other --filter id=cache-record-1',
            '--builder cache-builder --filter id=cache-record-1 --filter id=other',
            '--builder cache-builder --filter id=cache-record-1 && docker system prune',
            '--builder cache-builder --filter id=cache-record-1 && docker rmi old-image',
            '--builder cache-builder --filter id=cache-record-1 && uv cache clean package',
        )
        for suffix in suffixes:
            command = 'docker buildx prune ' + suffix
            with self.subTest(command=command):
                self.assertFalse(CHECKER.exact_buildkit_record(command))
                found = CHECKER.find_destructive_commands('`' + command + '`\n')
                self.assertTrue(found)
                self.assertTrue(next(item for item in found if item.tools == ('docker', 'OrbStack')).category_wide)

    def test_other_prune_families_do_not_acquire_exception(self):
        for family in ('system', 'image', 'volume', 'container', 'builder'):
            command = f'docker {family} prune --builder cache-builder --filter id=cache-record-1'
            with self.subTest(command=command):
                self.assertFalse(CHECKER.exact_buildkit_record(command))
                found = CHECKER.find_destructive_commands('`' + command + '`\n')
                self.assertTrue(found)
                self.assertTrue(all(item.category_wide for item in found))


if __name__ == '__main__':
    unittest.main()
