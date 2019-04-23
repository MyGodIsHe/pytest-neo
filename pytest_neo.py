# -*- coding: utf-8 -*-
"""
pytest_neo
~~~~~~~~~~~~

py.test is a plugin for py.test that changes the default look
and feel of py.test.

:copyright: see LICENSE for details
:license: BSD, see LICENSE for more details.
"""
import collections
import curses
import itertools
import multiprocessing
import os
import random
import sys
import time

import pytest
from _pytest.terminal import TerminalReporter


__version__ = '0.2.1'


BLOB_SIZE = (10, 20)
BLOB_SPEED = (0.1, 0.2)
IS_NEO_ENABLED = False


def pytest_addoption(parser):
    group = parser.getgroup("terminal reporting", "reporting", after="general")
    group._addoption(
        '--force-neo', action="store_true",
        dest="force_neo", default=False,
        help=(
            "Force pytest-neo output even when not in real terminal"
        )
    )


@pytest.mark.trylast
def pytest_configure(config):
    global IS_NEO_ENABLED

    if sys.stdout.isatty() or config.getvalue('force_neo'):
        IS_NEO_ENABLED = True

    if IS_NEO_ENABLED and not getattr(config, 'slaveinput', None):
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
    elif report.outcome == 'rerun':
        letter = "R"
    else:
        letter = "?"

    if hasattr(report, "wasxfail"):
        if report.skipped:
            return "xfailed", "x", "xfail"
        elif report.passed:
            return "xpassed", "X", "XPASS"

    return report.outcome, letter, report.outcome.upper()


class NeoTerminalReporter(TerminalReporter):
    def __init__(self, config, file=None):
        super(NeoTerminalReporter, self).__init__(config, file)
        self.left = -2
        self.top = 0
        self.stdscr = None
        self.column_color = None
        self.COLOR_CHAIN = []
        self.previous_char = None
        self.history = collections.defaultdict(list)
        self._show_progress_info = False
        self.verbose_reporter = None

    def tearup(self):
        self.stdscr = curses.initscr()
        self.stdscr.keypad(1)
        curses.noecho()
        try:
            curses.cbreak()
        except curses.error:  # hack for tests
            pass
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()
        try:
            for i in range(0, curses.COLORS):
                curses.init_pair(i, i, -1)
        except curses.error:  # hack for tests
            pass

        self.COLOR_CHAIN = itertools.cycle([
            curses.color_pair(10) ^ curses.A_BOLD,
            curses.color_pair(2),
            curses.color_pair(10),
        ])
        if self.verbosity > 0:
            self.verbose_reporter = VerboseReporter(self.stdscr, *BLOB_SPEED)
            self.verbose_reporter.start()

    def teardown(self):
        if self.verbose_reporter:
            self.verbose_reporter.exit.set()
            self.verbose_reporter.join()
            self.verbose_reporter = None

        if self.stdscr:
            self.stdscr.keypad(0)
            curses.echo()
            try:
                curses.nocbreak()
            except curses.error:  # hack for tests
                pass
            try:
                curses.endwin()
            except curses.error:  # hack for tests
                pass
            _, max_x = self.stdscr.getmaxyx()
            self.stdscr = None
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

    def summary_errors(self):
        self.teardown()
        return super(NeoTerminalReporter, self).summary_errors()

    def _report_keyboardinterrupt(self):
        self.teardown()
        super(NeoTerminalReporter, self)._report_keyboardinterrupt()

    @staticmethod
    def prepare_fspath(fspath):
        name = os.path.basename(str(fspath))
        parts = name.split('::', 1)
        name = parts[0]
        name = os.path.splitext(name)[0]
        if name.startswith('test_'):
            name = name[5:]
        if len(parts) == 2:
            name = '{}▒{}'.format(
                name,
                parts[1]
            )
        for pairs in [
            ('_', '|'),
            ('-', '|'),
            ('[', '▄'),
            (']', '▀')
        ]:
            name = name.replace(*pairs)
        return name

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
            if can_write(self.stdscr, top, left):
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
            self.currentfspath = fspath
            self.left += 2
            _, max_x = self.stdscr.getmaxyx()
            if self.left >= max_x:
                self.left = 0
            self.write_new_column()

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self):
        super(NeoTerminalReporter, self).pytest_collection_modifyitems()
        self.tearup()

    def pytest_internalerror(self, excrepr):
        self.teardown()
        return super(NeoTerminalReporter, self).pytest_internalerror(excrepr)

    def pytest_runtest_logstart(self, nodeid, location):
        if self.verbosity <= 0:
            fsid = nodeid.split("::")[0]
            self.write_fspath_result(fsid, "")
        else:
            self.verbose_reporter.queue.put((
                self.prepare_fspath(nodeid),
                next(self.COLOR_CHAIN)
            ))

    def pytest_runtest_logreport(self, report):
        cat, letter, word = pytest_report_teststatus(report=report)
        if isinstance(word, tuple):
            word, markup = word
        if report.when == 'call' or report.skipped:
            self.stats.setdefault(cat, []).append(report)
        elif report.failed:
            self.stats.setdefault("error", []).append(report)
        self._tests_ran = True
        if not letter and not word:
            # probably passed setup/teardown
            return

        if report.when != 'teardown':
            if report.when == 'call' or report.skipped:
                self.history[report.nodeid.split('::')[0]].append(letter)

        if self.verbosity <= 0:
            if report.when == 'setup':
                if not can_write(self.stdscr, self.top, self.left):
                    self.left += 1
                    self.write_new_column()
            if report.when == 'teardown':
                self.top += 1
            else:
                self.addstr(letter, self.column_color)
                self.stdscr.refresh()


def can_write(stdscr, top, left):
    if top < 0 or left < 0:
        return False
    max_y, max_x = stdscr.getmaxyx()
    if (max_y - 1, max_x - 1) == (top, left):
        return False
    if top >= max_y:
        return False
    if left >= max_x:
        return False
    return True


class Blob(object):

    def __init__(self, items, column, color, speed, size):
        self.size = size
        self.speed = speed
        self._items = items
        self._column = column
        self._color = color
        self._index = 0
        self._length = len(items)
        self._last_draw = time.time() - self.speed

    @property
    def column(self):
        return self._column

    @property
    def index(self):
        return self._index

    def draw(self, stdscr):
        for top, color in [
            (self._index - 1, self._color),
            (self._index, curses.color_pair(0) ^ curses.A_BOLD)
        ]:
            if top >= self._length or not can_write(stdscr, top, self._column):
                break
            letter = self._items[top]
            stdscr.addstr(
                top, self._column,
                letter, color
            )
        self._index += 1
        self._last_draw = time.time()
        return self._index - self.size >= self._length

    def can_draw(self, current_time):
        return current_time - self._last_draw > self.speed


class VerboseReporter(multiprocessing.Process):
    REFRESH_INTERVAL = 0.01

    def __init__(self, stdscr, speed_min, speed_max):
        super(VerboseReporter, self).__init__()
        self.stdscr = stdscr
        self.blobs = collections.defaultdict(list)
        assert self.REFRESH_INTERVAL <= speed_min < speed_max
        self.speed_min = speed_min
        self.speed_max = speed_max
        self._killed = False
        self.queue = multiprocessing.Queue()
        self.exit = multiprocessing.Event()

    def run(self):
        try:
            while not self.exit.is_set():
                if not self.queue.empty():
                    data = self.queue.get_nowait()
                    if data:
                        self.add_nodeid(*data)
                self.draw()
                time.sleep(self.REFRESH_INTERVAL)
        except KeyboardInterrupt:
            pass

    def get_random_column(self):
        max_y, max_x = self.stdscr.getmaxyx()
        cols = {n: max_y for n in range(max_x)}
        for column, blobs in self.blobs.items():
            for blob in blobs:
                cols[column] = min(cols[column], blob.index)
        variants = collections.defaultdict(list)
        for column, index in cols.items():
            variants[index].append(column)
        best_variant = sorted(
            variants.items(),
            key=lambda item: item[0]
        )[-1][1]
        return random.choice(best_variant)

    def draw(self):
        current_time = time.time()
        for column, blobs in self.blobs.items():
            delete_list = []
            for blob, next_blob in zip(blobs, blobs[1:] + [None]):
                top_limit = next_blob.index if next_blob else -1
                erase_top = blob.index - blob.size
                if erase_top > top_limit and can_write(
                        self.stdscr, erase_top, column):
                    self.stdscr.addstr(erase_top, column, ' ')
                if blob.can_draw(current_time):
                    need_delete = blob.draw(self.stdscr)
                    if need_delete:
                        delete_list.append(blob)
            for blob in delete_list:
                blobs.remove(blob)
        self.stdscr.refresh()

    def get_speed(self):
        delta = self.speed_max - self.speed_min
        return self.speed_min + delta * random.random()

    def add_nodeid(self, nodeid, color):
        column = self.get_random_column()
        self.blobs[column].append(
            Blob(
                nodeid,
                column,
                color,
                self.get_speed(),
                random.randint(*BLOB_SIZE)
            )
        )
