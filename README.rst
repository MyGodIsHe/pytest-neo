pytest-neo
==========

.. image:: https://img.shields.io/pypi/pyversions/pytest-neo.svg
    :target: https://pypi.org/project/pytest-neo/

.. image:: https://codecov.io/gh/MyGodIsHe/pytest-neo/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/MyGodIsHe/pytest-neo
    :alt: Code coverage Status
  
.. image:: https://img.shields.io/pypi/dm/pytest-neo.svg
    :target: https://pypi.python.org/pypi/pytest-neo


pytest-neo is a plugin for `pytest`_ that shows tests like screen of
Matrix.

.. image:: https://raw.githubusercontent.com/MyGodIsHe/pytest-neo/master/doc/readme_screen.png

Requirements
------------

You will need the following prerequisites in order to use pytest-neo:

-  Python 3.6 or newer
-  pytest 6.2.0 or newer

Installation
------------

To install pytest-neo:

::

   $ pip install pytest-neo

Then run your tests with (or verbose mode with a different visualization):

::

   $ pytest

If you would like to run tests without pytest-neo, use:

::

   $ pytest -p no:neo

.. _py.test: http://pytest.org
