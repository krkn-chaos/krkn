import logging
import unittest
from unittest.mock import MagicMock

from krkn.utils.TeeLogHandler import TeeLogHandler


class TestTeeLogHandler(unittest.TestCase):
    def test_instances_do_not_share_state(self):
        handler1 = TeeLogHandler()
        handler2 = TeeLogHandler()

        fmt = logging.Formatter('%(levelname)s: %(message)s')
        handler1.setFormatter(fmt)
        handler2.setFormatter(fmt)

        record1 = logging.LogRecord('t1', logging.INFO, 'f', 1, 'm1', (), None)
        record2 = logging.LogRecord('t2', logging.INFO, 'f', 2, 'm2', (), None)

        handler1.emit(record1)
        handler2.emit(record2)

        self.assertIn('m1', handler1.get_output())
        self.assertNotIn('m2', handler1.get_output())
        self.assertIn('m2', handler2.get_output())
        self.assertNotIn('m1', handler2.get_output())

    def test_emit_accumulates_and_formats(self):
        handler = TeeLogHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))

        for i in range(3):
            handler.emit(logging.LogRecord('t', logging.INFO, 'f', i, f'M{i}', (), None))

        out = handler.get_output()
        for i in range(3):
            self.assertIn(f'M{i}', out)

    def test_works_without_formatter(self):
        handler = TeeLogHandler()
        handler.emit(logging.LogRecord('t', logging.INFO, 'f', 1, 'm', (), None))
        self.assertTrue(handler.get_output())


class TestMainFunction(unittest.TestCase):
    def test_main_returns_exit_code_on_missing_config(self):
        from run_kraken import main

        opts = MagicMock()
        opts.cfg = '/no/such/config.yaml'

        rc = main(opts, command=None)
        self.assertIsInstance(rc, int)
        self.assertEqual(rc, -1)

    def test_main_callable_multiple_times(self):
        from run_kraken import main

        opts = MagicMock()
        opts.cfg = '/no/such/config.yaml'

        for _ in range(3):
            self.assertEqual(main(opts, command=None), -1)


class TestIntegration(unittest.TestCase):
    def test_integration_with_logging(self):
        handler = TeeLogHandler()
        handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))

        logger = logging.getLogger('test_logger')
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.info('info')
        logger.warning('warn')
        logger.error('err')

        out = handler.get_output()
        self.assertIn('[INFO] info', out)
        self.assertIn('[WARNING] warn', out)
        self.assertIn('[ERROR] err', out)

        logger.removeHandler(handler)


if __name__ == '__main__':
    unittest.main()
