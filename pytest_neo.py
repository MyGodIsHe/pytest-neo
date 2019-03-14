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


__version__ = '0.1.3'


IS_NEO_ENABLED = False


@pytest.mark.trylast
def pytest_configure(config):
    global IS_NEO_ENABLED

    if config.option.verbose > 0:
        return

    IS_NEO_ENABLED = True

    # Get the standard terminal reporter plugin and replace it with our
    standard_reporter = config.pluginmanager.getplugin('terminalreporter')
    config.pluginmanager.unregister(standard_reporter)
    neo_reporter = NeoTerminalReporter(config, sys.stdout)
    config.pluginmanager.register(neo_reporter, 'terminalreporter')


def pytest_report_teststatus(report):
    if not IS_NEO_ENABLED:
        return
    if report.passed:
        letter = "."
    elif report.skipped:
        letter = "s"
    elif report.failed:
        letter = "F"
        if report.when != "call":
            letter = "f"
    return report.outcome, letter, report.outcome.upper()


class NeoTerminalReporter(TerminalReporter):
    def __init__(self, config, file=None):
        super().__init__(config, file)
        self.left = -2
        self.top = 0
        self.stdscr = None
        self.column_color = None
        self.COLOR_CHAIN = []
        self.previous_char = None
        self.history = {}

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
            curses.color_pair(10) ^ curses.A_BOLD,
            curses.color_pair(2),
            curses.color_pair(10),
        ])

    def teardown(self):
        if self.stdscr:
            curses.echo()
            curses.nocbreak()
            curses.endwin()
            _, max_x = self.stdscr.getmaxyx()
            self.print_history(max_x)

    def print_history(self, max_x):
        part_count = int(max_x / 2)
        history = sorted(
            (self.prepare_fspath(name), tests)
            for name, tests in self.history.items()
        )
        while history:
            history_part = history[:part_count]
            history = history[part_count:]
            columns = []
            for name, tests in history_part:
                column = name + ''.join(test for test in tests)
                columns.append(column)
            row_num = 0
            while True:
                was_entry = False
                color_chain = itertools.cycle([
                    '\033[1;38;5;10m{}\033[0m',
                    '\033[0;38;5;2m{}\033[0m',
                    '\033[0;38;5;10m{}\033[0m',
                ])
                for column in columns:
                    color = next(color_chain)
                    if len(column) > row_num:
                        letter = column[row_num]
                        self._tw.write(color.format(letter))
                        was_entry = True
                    else:
                        self._tw.write(' ')
                    self._tw.write(' ')
                self._tw.write('\n')
                if not was_entry:
                    break
                row_num += 1

    def summary_stats(self):
        self.teardown()
        super().summary_stats()

    def _write_progress_information_filling_space(self):
        pass

    @staticmethod
    def prepare_fspath(fspath):
        return pathlib.Path(fspath).stem.replace('_', '|')[5:]

    def can_write(self, top, left):
        max_y, max_x = self.stdscr.getmaxyx()
        if (max_y - 1, max_x - 1) == (top, left):
            return False
        if top >= max_y:
            return False
        if left >= max_x:
            return False
        return True

    def fix_coordinate(self):
        max_y, max_x = self.stdscr.getmaxyx()
        if (max_y - 1, max_x - 1) == (self.top, self.left):
            self.top = 0
            self.left += 1
        if self.top >= max_y:
            self.top = 0
            self.left += 1
        if self.left >= max_x:
            self.left = 0

    def addstr(self, letter, color):
        self.fix_coordinate()
        if self.previous_char:
            self.stdscr.addstr(*self.previous_char)
        self.stdscr.addstr(
            self.top, self.left,
            letter, curses.color_pair(0) ^ curses.A_BOLD
        )
        self.previous_char = self.top, self.left, letter, color

    def clear_column(self, left):
        max_y, max_x = self.stdscr.getmaxyx()
        for top in range(max_y):
            if self.can_write(top, left):
                self.stdscr.addstr(top, left, ' ')
        self.stdscr.refresh()

    def write_new_column(self):
        self.column_color = next(self.COLOR_CHAIN)
        fspath = self.prepare_fspath(self.currentfspath)

        self.clear_column(self.left)
        self.clear_column(self.left + 1)

        self.top = 0
        for letter in fspath:
            self.addstr(letter, self.column_color)
            self.stdscr.refresh()
            self.top += 1

    def write_fspath_result(self, nodeid, res):
        fspath = self.config.rootdir.join(nodeid.split("::")[0])
        if fspath != self.currentfspath:
            if self.currentfspath is not None:
                self._write_progress_information_filling_space()
            self.currentfspath = fspath
            self.left += 2
            _, max_x = self.stdscr.getmaxyx()
            if self.left >= max_x:
                self.left = 0
            self.write_new_column()
            self.history[self.currentfspath] = []

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self):
        super().pytest_collection_modifyitems()
        self.tearup()

    def pytest_keyboard_interrupt(self, excinfo):
        self.teardown()
        super().pytest_keyboard_interrupt(excinfo)

    def pytest_internalerror(self, excrepr):
        self.teardown()
        return super().pytest_internalerror(excrepr)

    def pytest_runtest_logreport(self, report):
        rep = report
        res = pytest_report_teststatus(report=rep)
        cat, letter, word = res
        if isinstance(word, tuple):
            word, markup = word
        self.stats.setdefault(cat, []).append(rep)
        self._tests_ran = True
        if not letter and not word:
            # probably passed setup/teardown
            return
        if report.when == 'setup':
            if not self.can_write(self.top, self.left):
                self.left += 1
                self.write_new_column()
        if report.when == 'teardown':
            self.top += 1
        else:
            self.addstr(letter, self.column_color)
            self.stdscr.refresh()
            if report.when == 'call' or report.skipped:
                self.history[self.currentfspath].append(letter)
