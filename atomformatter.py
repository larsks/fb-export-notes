import os

from google.appengine.ext.webapp import template

class AtomFormatter (object):
    id              = 'atom'
    name            = 'Atom (XML)'
    content_type    = 'application/atom+xml'
    extension       = 'xml'

    def format(self, user, feed):
        path = os.path.join(os.path.dirname(__file__), 'templates',
                'atomexport.xml')
        return template.render(path, {'feed': feed, 'user': user})
