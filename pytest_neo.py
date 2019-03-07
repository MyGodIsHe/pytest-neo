# -*- coding: utf-8 -*-
"""
pytest_neo
~~~~~~~~~~~~

py.test is a plugin for py.test that changes the default look
and feel of py.test.

:copyright: see LICENSE for details
:license: BSD, see LICENSE for more details.
"""
import curses
import itertools
import pathlib
import sys

import pytest
from _pytest.terminal import TerminalReporter


__version__ = '0.1.0'


@pytest.mark.trylast
def pytest_configure(config):
    if config.option.verbose > 0:
        return
    # Get the standard terminal reporter plugin and replace it with our
    standard_reporter = config.pluginmanager.getplugin('terminalreporter')
    config.pluginmanager.unregister(standard_reporter)
    neo_reporter = NeoTerminalReporter(config, sys.stdout)
    config.pluginmanager.register(neo_reporter, 'terminalreporter')


class NeoTerminalReporter(TerminalReporter):
    def __init__(self, config, file=None):
        super().__init__(config, file)
        self.left = -1
        self.top = 1
        self.stdscr = None
        self.column_color = None
        self.COLOR_CHAIN = []

    def tearup(self):
        self.stdscr = curses.initscr()
        self.stdscr.keypad(True)
        curses.noecho()
        curses.cbreak()
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()
        for i in range(0, curses.COLORS):
            curses.init_pair(i, i, -1)

        self.COLOR_CHAIN = itertools.cycle([
            curses.color_pair(2),
            curses.color_pair(2) ^ curses.A_BOLD,
            curses.color_pair(10),
            curses.color_pair(10) ^ curses.A_BOLD,
        ])

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self):
        super().pytest_collection_modifyitems()
        self.tearup()

    def teardown(self):
        if self.stdscr:
            curses.echo()
            curses.nocbreak()
            curses.endwin()

    def pytest_keyboard_interrupt(self, excinfo):
        self.teardown()
        super().pytest_keyboard_interrupt(excinfo)

    def pytest_internalerror(self, excrepr):
        self.teardown()
        return super().pytest_internalerror(excrepr)

    def summary_stats(self):
        self.teardown()
        super().summary_stats()

    def _write_progress_information_filling_space(self):
        pass

    def write_fspath_result(self, nodeid, res):
        fspath = self.config.rootdir.join(nodeid.split("::")[0])
        if fspath != self.currentfspath:
            self.column_color = next(self.COLOR_CHAIN)
            if self.currentfspath is not None:
                self._write_progress_information_filling_space()
            self.currentfspath = fspath
            fspath = pathlib.Path(fspath).stem.replace('_', '|')[5:]
            self.left += 2
            for top, letter in enumerate(fspath):
                self.stdscr.addstr(
                    top, self.left,
                    letter,  self.column_color
                )
                self.stdscr.refresh()
            self.top = len(fspath)

    def pytest_runtest_logreport(self, report):
        rep = report
        res = pytest_report_teststatus(report=rep)
        cat, letter, word = res
        if isinstance(word, tuple):
            word, markup = word
        else:
            markup = None
        self.stats.setdefault(cat, []).append(rep)
        self._tests_ran = True
        if not letter and not word:
            # probably passed setup/teardown
            return
        try:
            self.stdscr.addstr(
                self.top, self.left,
                letter, self.column_color
            )
            self.stdscr.refresh()
        except curses.error as e:
            pass
        self.top += 1


def pytest_report_teststatus(report):
    if report.passed:
        letter = "."
    elif report.skipped:
        letter = "s"
    elif report.failed:
        letter = "F"
        if report.when != "call":
            letter = "f"
    return report.outcome, letter, report.outcome.upper()
