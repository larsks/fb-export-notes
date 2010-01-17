import os
import sys
import datetime
import time
import cPickle as pickle
import optparse
from ConfigParser import ConfigParser

import facebook
import PyRSS2Gen as RSS2

from xml.etree import ElementTree as ET

NS_ATOM         = 'http://www.w3.org/2005/Atom'
CATEGORY_KIND   = 'http://schemas.google.com/g/2005#kind'
POST_KIND       = 'http://schemas.google.com/blogger/2008/kind#post'

CCACHE          = os.path.join(os.environ['HOME'], '.fbexportnotes')

class ApplicationError(Exception):
    pass

def atomelement(e):
    return '{%s}%s' % (NS_ATOM, e)

def fmtTime(t):
    return time.strftime('%Y-%m-%dT%H:%M:%S.000-05:00', time.localtime(t))

def addSubElement(element, name, attrs=None, text=None):
    x = ET.SubElement(element, name)
    if attrs:
        for k, v in attrs.items():
            x.set(k,v)
    if text:
        x.text = text

    return x

def parse_args():
    p = optparse.OptionParser()
    p.add_option('-c', '--credentials',
            help='File from which to read Facebook application credentials.')

    return p.parse_args()

def main():
    opts, args = parse_args()
    config = ConfigParser()

    if opts.credentials:
        config.read(opts.credentials)

    FB_API_KEY = config.get('facebook', 'api key')
    FB_SECRET_KEY = config.get('facebook', 'secret key')

    print 'API KEY:', FB_API_KEY
    print 'SECRET KEY:', FB_SECRET_KEY

    fb = facebook.Facebook(FB_API_KEY, FB_SECRET_KEY)
    return fb

    if os.path.exists(CCACHE):
        auth = pickle.load(open(CCACHE))
        fb.session_key = auth['session_key']
        fb.secret = auth['secret']
        fb.uid = auth['uid']
    else:
        tok = fb.auth.createToken()
        fb.login()
        auth = fb.auth.getSession()
        pickle.dump(auth, open(CCACHE, 'w'))

    if not fb.uid:
        raise ApplicationError('Login failed.')

    notes = fb.fql.query('SELECT note_id, created_time, updated_time, title, content FROM note WHERE uid=%d' % fb.uid)
    name = fb.users.getInfo(fb.uid, 'first_name')[0]['first_name']

    feed = ET.Element(atomElement('feed'))

    addSubElement(feed, atomElement('title'),
            attrs={'type': 'text'}, 
            text='Notes for %s' % name)
    addSubElement(addSubElement(feed, atomElement('author')),
            atomElement('name'),
            text=name)
    addSubElement(feed, atomElement('generator'),
            text='Blogger')

    for note in notes:
        entry = addSubElement(feed, atomElement('entry'))
        addSubElement(entry, atomElement('id'),
                text='http://www.facebook.com/notes.php?id=%s' % note['note_id'])
        addSubElement(entry, atomElement('title'),
                attrs={'type': 'text'},
                text=note['title'])
        addSubElement(entry, atomElement('category'),
                attrs={'scheme': CATEGORY_KIND, 'term': POST_KIND})
        addSubElement(entry, atomElement('published'),
                text=fmtTime(note['created_time']))
        addSubElement(entry, atomElement('updated'),
                text=fmtTime(note['updated_time']))
        addSubElement(entry, atomElement('author'),
                text=name)
        addSubElement(entry, atomElement('content'),
                attrs={'type': 'html'},
                text=note['content'].replace('\n', '<br/>'))
    
    ET.ElementTree(feed).write(sys.stdout)

    return fb

if __name__ == '__main__':
    fb = main()

