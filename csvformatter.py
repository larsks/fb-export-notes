fields = [ 'type', 'id', 'title', 'created', 'updated', 'url', 'summary', 'content' ]

class CSVFormatter (object):
    id              = 'csv'
    name            = 'CSV (for Excel, etc)'
    content_type    = 'text/plain'
    extension       = 'csv'

    def format(self, user, feed):
        text = [','.join(fields)]
        for item in feed:
            line = []
            for field in fields:
                line.append(unicode(item.get(field, '')).encode('utf-8'))
            text.append(','.join([
                '"%s"' % x.replace('"', '""') for x in line]))

        return '\n'.join(text)

