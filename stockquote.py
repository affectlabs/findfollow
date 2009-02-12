import re
from google.appengine.api import urlfetch

def get_quote(symbol):
    base_url = 'http://finance.google.com/finance?q='
    content = urlfetch.fetch(base_url + symbol).content
    m = re.search('class="pr".*?>(.*?)<', content)
    if m:
        quote = m.group(1)
    else:
        quote = 'no quote available for: ' + symbol
    return quote
