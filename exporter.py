#!/usr/bin/python

import os
import sys
import time
import datetime

# Set up virtualenv access.
import virtualenv

import facebook
import cherrypy
import wsgiref.handlers

from google.appengine.ext.webapp import template
from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.ext import db
sys.modules['memcache'] = memcache

import csvformatter
import htmlformatter
import atomformatter

# register custom django template filters.
template.register_template_library('filters')

class User (db.Model):
    session_key = db.StringProperty(required=True)
    uid = db.IntegerProperty(required=True)
    name = db.StringProperty()
    last_update = db.DateTimeProperty(required=True)
    last_export = db.DateTimeProperty()
    selected = db.StringListProperty()
    options = db.StringListProperty()

def fb_require_login(f):
    '''Decorator for functions that require a valid Facebook session to
    operate.'''

    def _(self, *args, **kwargs):
        fb = cherrypy.request.facebook

        if False:
            pass
        elif 'fb_sig_session_key' in kwargs and 'fb_sig_user' in kwargs:
            fb.session_key = kwargs['fb_sig_session_key']
            fb.uid = kwargs['fb_sig_user']
        elif 'x_sig_session_key' in kwargs and 'x_sig_user' in kwargs:
            fb.session_key = kwargs['x_sig_session_key']
            fb.uid = kwargs['x_sig_user']
        elif 'auth_token' in kwargs:
            fb.auth.getSession()
        else:
            return fb.redirect(fb.get_login_url())

        return f(self, *args, **kwargs)

    return _

class Exporter (object):
    _cp_config = {
            'tools.facebook.on'             : True,
            'tools.sessions.on'             : True,
            'tools.sessions.storage_type'   : 'memcached',
            'tools.sessions.servers	'       : [ 'memcached://' ],
            'tools.sessions.name'           : '_fb_exporter_id',
            'tools.sessions.clean_thread'   : True,
            'tools.sessions.timeout'        : 60,
            }

    def __init__ (self):
        self.formats = {}
        
        for format in [
                csvformatter.CSVFormatter(),
                htmlformatter.HTMLFormatter(),
                atomformatter.AtomFormatter(),
                ]:
            self.formats[format.id] = format

    def render (self, page, context):
        '''Render a template.'''

        base = os.path.join(os.path.dirname(__file__), 'templates', page)
        path = None

        # Allow templates to be specified with or without extension.
        for p in [base, '%s.html' % base]:
            if os.path.exists(p):
                path = p
                break

        if not path:
            raise cherrypy.HTTPError('500',
                    'Unable to find requested template (%s).' % page)

        return template.render(path, context)

    @cherrypy.expose
    @fb_require_login
    def index(self, **kwargs):
        return self.main(**kwargs)
#        return '''<p>This application is currently offline for maintenance.
#        Please check back Sunday, 2010-Feb-7, after 6:00pm EST.</p>'''

    @cherrypy.expose
    @fb_require_login
    def main(self, **kwargs):
        '''Render the main canvas page.'''

        user = User.get_by_key_name('uid=%s' %
                cherrypy.request.facebook.uid)

        return self.render('main', {
            'formats': self.formats.values(),
            'fb': cherrypy.request.facebook,
            'config': cherrypy.request.app.config['facebook'],
            'message': kwargs.get('message'),
            'user': user,
            })

    @cherrypy.expose
    def help(self, **kwargs):
        '''Render the help page.'''

        return self.render('help', {
            'fb': cherrypy.request.facebook,
            'config': cherrypy.request.app.config['facebook'],
            })

    def error(self, message):
        '''Return the user to the canvas url and display the
        given error message.'''

        canvas_url = cherrypy.request.app.config['facebook']['canvas_url']
        return cherrypy.request.facebook.redirect('%s?message=%s' % (canvas_url, message))

    @cherrypy.expose
    @fb_require_login
    def prepare(self, **kwargs):
        fb = cherrypy.request.facebook
        user = User.get_by_key_name('uid=%s' % fb.uid)

        if 'export' in kwargs:
            selected = kwargs['export']
            if not isinstance(selected, list):
                selected = [selected]
        elif user:
            selected = user.selected
        else:
            selected = []

        if not selected:
            return self.error('You have not selected anything to export.')

        options = set()
        if 'dedupe' in kwargs:
            options.add('dedupe')

        which = kwargs.get('which', 'all')

        print >>sys.stderr, 'DEBUG: options=%s, selected=%s, which=%s' % (options, selected, which)

        fbuser = fb.users.getInfo(fb.uid, 'name, first_name, last_name, profile_url, timezone')[0]
        user = User(
                key_name = 'uid=%s' % fb.uid,
                uid = int(fb.uid),
                name = fbuser['name'],
                session_key = fb.session_key,
                selected = selected,
                options = list(options),
                last_update = datetime.datetime.utcnow(),
                )

        user.put()

        return self.render('prepare', {
            'formats': self.formats.values(),
            'fb': cherrypy.request.facebook,
            'config': cherrypy.request.app.config['facebook'],
            'user': user,
            'which': which,
            })

    @cherrypy.expose
    def export(self, uid, which, format, output_file, retry=0):
        '''Generate the exported data.'''

        fb = cherrypy.request.facebook
        user = User.get_by_key_name('uid=%s' % uid)
        if user is None:
            return self.error('You have not selected anything to export.')

        if user.last_export:
            print >>sys.stderr, 'DEBUG: last visit: %s' % user.last_export
        else:
            print >>sys.stderr, 'DEBUG: this is the first visit.'

        print >>sys.stderr, 'DEBUG: which = %s' % which

        fb.uid = uid
        fb.session_key = user.session_key

        dedupe = 'dedupe' in user.options
        limits = {}

        if which == 'new' and user.last_export:
            limits['since'] = user.last_export

        format = self.formats[format]
        fbuser = fb.users.getInfo(fb.uid, 'name, first_name, last_name, profile_url')[0]

        try:
            feed = []

            # Extend feed with each object type selected by the user.
            for x in user.selected:
                f = getattr(self, 'get_%s' % x)
                feed.extend(f(dedupe=dedupe, limits=limits))

            user.last_export = datetime.datetime.utcnow()
            user.put()

        except urlfetch.DownloadError:
            url = '%s/export/%s/%s/%s/facebook_data.%s?retry=1' % (
                    cherrypy.request.app.config['facebook']['base_url'],
                    fbuser.uid,
                    format.id,
                    format.extension)
            raise HTTPRedirect(url)

        # Format the items in the feed, sorted by date created.
        cherrypy.response.headers['Content-Type'] = format.content_type
        return format.format(fbuser,
            sorted(feed, key=lambda x: x['created']))
#    export._cp_config = {'response.stream': True}

    def get_notes(self, dedupe=False, limits=None):
        fb = cherrypy.request.facebook

        fql_select = '''SELECT note_id, created_time,
                    updated_time, title, content
                    FROM note'''
        fql_where = [ 'uid = %s' % fb.uid ]
        fql_order = '''ORDER BY created_time DESC'''

        if limits and limits.get('since'):
            fql_where.append('created_time > %d'
                    % time.mktime(limits['since'].utctimetuple()))

        fql = ' '.join([fql_select, 'WHERE',
                ' AND '.join(fql_where),
                fql_order])

        print >>sys.stderr, 'DEBUG: fql = %s' % fql
        notes = fb.fql.query(fql)

        feed = []
        last_title = None

        for note in notes:
            if dedupe and note['title'] == last_title:
                continue

            last_title = note['title']

            feed.append({
                'type'      : 'note',
                'id'        : note['note_id'],
                'title'     : note['title'],
                'created'   :
                datetime.datetime.fromtimestamp(int(note['created_time'])),
                'updated'   :
                datetime.datetime.fromtimestamp(int(note['updated_time'])),
                'content'   : note['content'],
                })

        return feed

    def get_status(self, dedupe=False, limits=None):
        '''Extract status updates.'''

        fb = cherrypy.request.facebook

        fql_select = '''SELECT status_id, time, message
                    FROM status'''
        fql_where = [ 'uid = %s' % fb.uid ]
        fql_order = '''ORDER BY time DESC'''

        if limits and limits.get('since'):
            fql_where.append('time > %d'
                    % time.mktime(limits['since'].utctimetuple()))

        fql = ' '.join([fql_select, 'WHERE',
                ' AND '.join(fql_where),
                fql_order])

        print >>sys.stderr, 'DEBUG: limits = %s' % limits
        print >>sys.stderr, 'DEBUG: fql = %s' % fql
        statuses = fb.fql.query(fql)

        feed = []
        for status in statuses:
            feed.append({
                'type'      : 'status',
                'id'        : status['status_id'],
                'title'     : status['message'],
                'created'   :
                datetime.datetime.fromtimestamp(int(status['time'])),
                'content'   : status['message'],
                })

        return feed

    def get_links(self, dedupe=False, limits=None):
        fb = cherrypy.request.facebook
        links = fb.fql.query(
                '''SELECT link_id, created_time, title, summary,
                owner_comment, url
                FROM link WHERE owner=%s
                ORDER BY created_time DESC''' % fb.uid)

        feed = []
        last_title = None

        for link in links:
            if dedupe and link['title'] == last_title:
                continue

            last_title = link['title']
            content = ['<p><a href="%(url)s">%(title)s</a></p>' % link]

            if link.get('summary'):
                content.append('<blockquote>%(summary)s</blockquote>'
                        % link)

            if link.get('owner_comment'):
                content.append('<p>%(owner_comment)s</p>'
                        % link)

            feed.append({
                'type'      : 'link',
                'id'        : link['link_id'],
                'title'     : link['title'],
                'created'   :
                datetime.datetime.fromtimestamp(int(link['created_time'])),
                'summary'   : link['summary'],
                'content'   : '\n'.join(content),
                'url'       : link['url'],
                })

        return feed

class FacebookTool (object):
    '''This sets up a cherrypy.request.facebook for each incoming
    request.'''

    def __call__(self):
        cherrypy.request.facebook = facebook.Facebook(
                cherrypy.request.app.config['facebook']['api_key'],
                cherrypy.request.app.config['facebook']['secret_key'])

        cherrypy.request.facebook.redirect = self.redirect

    def redirect(self, url):
        if cherrypy.request.params.get('fb_sig_in_canvas'):
            return '<fb:redirect url="%s" />' % url
        else:
            raise cherrypy.HTTPRedirect(url)

def main():
    cherrypy.tools.facebook = cherrypy.Tool(
            'before_handler',
            FacebookTool())

    root = Exporter()
    app = cherrypy.tree.mount(root, "/", config='app.ini')
    wsgiref.handlers.CGIHandler().run(app)

if __name__ == '__main__':
    main()

