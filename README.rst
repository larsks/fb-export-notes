=====================
Export Facebook Notes
=====================

:Author: Lars Kellogg-Stedman

Installing
==========

You need the PyFacebook library.  It's available as a submodule of this
repository; just run the following commands::

  git submodule update --init
  ln -s pyfacebook/facebook facebook

Running
=======

The script will output your notes to stdout.  The first time you run the
script it should open a browser asking you to authenticate on Facebook.
You may need to run the script a second time for it to actually work::

  python fb-to-atom.py > mynotes.atom

