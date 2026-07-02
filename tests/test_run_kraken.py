import unittest
from unittest.mock import patch, mock_open
from types import SimpleNamespace

from run_kraken import main


class TestRunKraken(unittest.TestCase):

    @patch('run_kraken.yaml.safe_load')
    @patch('run_kraken.os.path.isfile')
    @patch('builtins.open', new_callable=mock_open)
    def test_main_without_telemetry_config(self, mock_file, mock_isfile, mock_yaml_load):
        """
        Test that main() doesn't crash when config has no telemetry section
        """
        mock_isfile.side_effect = lambda p: p == "/fake/config.yaml"
        mock_yaml_load.return_value = {
            "kraken": {"rollback_versions_directory": "/tmp/krkn-test-rollback"},
            "tunings": {},
            "performance_monitoring": {},
            "elastic": {},
        }

        options = SimpleNamespace(cfg="/fake/config.yaml")
        result = main(options, None)

        self.assertEqual(result, -1)


if __name__ == "__main__":
    unittest.main()
