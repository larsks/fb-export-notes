#!/usr/bin/python

import os
import sys

HERE = os.path.dirname(__file__)
LIBDIR = 'runtime/lib/python2.5'
SITEDIR = os.path.join(HERE, LIBDIR, 'site-packages')

for line in open(os.path.join(SITEDIR, 'easy-install.pth')):
    if line.startswith("import"):
        exec line
    elif line.startswith('#'):
        pass
    else:
        sys.path.append(os.path.join(SITEDIR, line.strip()))

import facebook
import cherrypy
import wsgiref.handlers

try:
    from google.appengine.api import memcache
    sys.modules['memcache'] = memcache
except ImportError:
    pass

def fb_require_login(f):
    def _(self, *args, **kwargs):
        fb = cherrypy.request.facebook

        if 'fb_sig_session_key' in kwargs and 'fb_sig_user' in kwargs:
            fb.session_key = kwargs['fb_sig_session_key']
            fb.uid = int(kwargs['fb_sig_user'])
        elif 'auth_token' in kwargs:
            fb.auth.getSession()
            cherrypy.sessio['session_key'] = fb.session_key
            cherrypy.sessio['uid'] = fb.uid
        else:
            return fb.redirect(fb.get_login_url())

        return f(self, *args, **kwargs)

    return _

class Exporter:
    @cherrypy.expose
    @fb_require_login
    def index(self, **kwargs):
        text = ['<h1>Params</h1>']
        
        text.append('<table>')
        for k,v in kwargs.items():
            text.append('<tr><td>%s</td><td>%s</td></tr>' % (k,v))
        text.append('</table>')

        fb = cherrypy.request.facebook

        text.append('<p>api = %s</p>' % fb.api_key)
        text.append('<p>secret = %s</p>' % fb.secret_key)
        text.append('<p>fb user = %s</p>' % fb.uid)
        text.append('<p>fb session_key = %s</p>' % fb.session_key)

        try:
            user = fb.users.getLoggedInUser()
            text.append('<p>user info: %s</p>' % user)
        except facebook.FacebookError, detail:
            text.append('<p>api call failed: %s</p>' % detail)

        info = fb.users.getInfo(fb.uid)

        text.append('<h1>User info</h1>')
        for d in info:
            text.append('<h2>%s</h2>' % d['name'])
            text.append('<table>')
            for k,v in d.items():
                text.append('<tr><td>%s</td><td>%s</td></tr>' % (k,v))
            text.append('</table>')

        return '\n'.join(text)

class FacebookTool:
    def __init__ (self, api_key, secret_key):
        self.api_key = api_key
        self.secret_key = secret_key

    def __call__(self):
        cherrypy.request.facebook = facebook.Facebook(
                self.api_key,
                self.secret_key)

        cherrypy.request.facebook.redirect = self.redirect

    def redirect(self, url):
        if cherrypy.request.params.get('fb_sig_in_canvas'):
            return '<fb:redirect url="%s" />' % url
        else:
            raise cherrypy.HTTPRedirect(url)

def main():
    fb_file = open('facebook_keys.txt').readlines()
    api_key = fb_file[0].rstrip()
    secret_key = fb_file[1].rstrip()

    cherrypy.tools.facebook = cherrypy.Tool(
            'before_handler',
            FacebookTool(api_key, secret_key))

    root = Exporter()
    app = cherrypy.tree.mount(root, "/", config={
        '/' : {
            'tools.facebook.on'             : True,
            'tools.sessions.on'             : True,
            'tools.sessions.storage_type'   : "memcached",
            'tools.sessions.servers'        : ['memcached://'],
            'tools.sessions.name'           : 'fb_session',
            'tools.sessions.clean_thread'   : True,
            'tools.sessions.timeout'        : 60,
            }})
    wsgiref.handlers.CGIHandler().run(app)

if __name__ == '__main__':
    main()

