import os
import sys

######################################################################
#
# BEGIN VIRTUALENV IMPORT
#
# This mess of code gets us packages installed into a virtualenv
# using easy_install.
#

HERE = os.path.dirname(__file__)
LIBDIR = 'runtime/lib/python2.5'
SITEDIR = os.path.join(HERE, LIBDIR, 'site-packages')

# This was mostly extracted by site.py.
for line in open(os.path.join(SITEDIR, 'easy-install.pth')):
    if line.startswith("import"):
        exec line
    elif line.startswith('#'):
        pass
    else:
        sys.path.append(os.path.join(SITEDIR, line.strip()))

#
# END VIRTUALENV IMPORT
#
######################################################################
