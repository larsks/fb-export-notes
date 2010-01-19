import os

from google.appengine.ext.webapp import template

class HTMLFormatter (object):
    id              = 'html'
    name            = 'HTML (good for display)'
    content_type    = 'text/html'
    extension       = '.html'

    def format(self, user, feed):
        path = os.path.join(os.path.dirname(__file__), 'templates',
                'htmlexport.html')
        return template.render(path, {'feed': feed, 'user': user})

