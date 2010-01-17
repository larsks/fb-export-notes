import os
import sys
import datetime
import time
import cPickle as pickle

import facebook
import PyRSS2Gen as RSS2

from xml.etree import ElementTree as ET

FB_API_KEY      = '1d35ab34c58ef4571acbef5e0f119686'
FB_SECRET_KEY   = 'ccf876e02225c98dc071f08e8fdeaf47'

CATEGORY_KIND   = 'http://schemas.google.com/g/2005#kind'
POST_KIND       = 'http://schemas.google.com/blogger/2008/kind#post'

CCACHE          = os.path.join(os.environ['HOME'], '.fbexportnotes')

class ApplicationError(Exception):
    pass

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

def main():
    fb = facebook.Facebook(FB_API_KEY, FB_SECRET_KEY)

    if os.path.exists(CCACHE):
        auth = pickle.load(open(CCACHE))
        fb.session_key = auth['session_key']
        fb.secret = auth['secret']
        fb.uid = auth['uid']
    else:
        fb.auth.createToken()
        fb.login()
        auth = fb.auth.getSession()
        pickle.dump(auth, open(CCACHE, 'w'))

    if not fb.uid:
        raise ApplicationError('Login failed.')

    notes = fb.fql.query('SELECT note_id, created_time, updated_time, title, content FROM note WHERE uid=%d' % fb.uid)
    name = fb.users.getInfo(fb.uid, 'first_name')[0]['first_name']

    feed = ET.Element('{http://www.w3.org/2005/Atom}feed')

    addSubElement(feed, '{http://www.w3.org/2005/Atom}title', attrs={'type': 'text'}, 
            text='Notes for %s' % name)
    addSubElement(addSubElement(feed, '{http://www.w3.org/2005/Atom}author'),
            '{http://www.w3.org/2005/Atom}name', text=name)
    addSubElement(feed, '{http://www.w3.org/2005/Atom}generator',
            text='Blogger')

    for note in notes:
        entry = addSubElement(feed, '{http://www.w3.org/2005/Atom}entry')
        addSubElement(entry, '{http://www.w3.org/2005/Atom}id',
                text='http://www.facebook.com/notes.php?id=%s' % note['note_id'])
        addSubElement(entry, '{http://www.w3.org/2005/Atom}title',
                attrs={'type': 'text'},
                text=note['title'])
        addSubElement(entry, '{http://www.w3.org/2005/Atom}category',
                attrs={'scheme': CATEGORY_KIND, 'term': POST_KIND})
        addSubElement(entry, '{http://www.w3.org/2005/Atom}published',
                text=fmtTime(note['created_time']))
        addSubElement(entry, '{http://www.w3.org/2005/Atom}updated',
                text=fmtTime(note['updated_time']))
        addSubElement(entry, '{http://www.w3.org/2005/Atom}author',
                text=name)
        addSubElement(entry, '{http://www.w3.org/2005/Atom}content',
                attrs={'type': 'html'},
                text=note['content'].replace('\n', '<br/>'))
    
    ET.ElementTree(feed).write(sys.stdout)

    return fb

if __name__ == '__main__':
    fb = main()

