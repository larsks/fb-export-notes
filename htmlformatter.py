import os

import baseformatter
from google.appengine.ext.webapp import template

class HTMLFormatter (baseformatter.BaseFormatter):
    id              = 'html'
    name            = 'HTML (good for display)'
    content_type    = 'text/html'
    extension       = '.html'

    def format(self, feed):
        path = os.path.join(os.path.dirname(__file__), 'templates',
                'htmlexport.html')
        yield(template.render(path, {'feed': feed}))

