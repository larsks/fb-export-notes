import baseformatter

class CSVFormatter (baseformatter.BaseFormatter):
    id              = 'csv'
    name            = 'CSV (for Excel, etc)'
    content_type    = 'text/plain'
    extension       = '.csv'

    def format(self, user, feed):
        yield(','.join(self.fields))
        for item in feed:
            yield( ','.join(['"%s"' % str(x).replace('"', '""') for x in [
                item[y] for y in self.fields]]))

