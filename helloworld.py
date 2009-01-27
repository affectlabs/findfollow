import os
from google.appengine.ext.webapp import template
import cgi
import twitter
from datetime import datetime

from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db

class Tweet(db.Model):
  # Author human readable. User is ID
  # Not sure if we need to replicate the entire User class.
  author = db.StringProperty()
  user = db.IntegerProperty()
  text = db.StringProperty(multiline=True)
  id = db.IntegerProperty()
  created_at = db.DateTimeProperty()
  now = db.DateTimeProperty()
  # And the money shot!
  keywords = db.StringListProperty()

class MainPage(webapp.RequestHandler):
  def get(self):
    # api = twitter.Api()
    # moved api call to PopulateDatabase method
    # here we can also have (some) control on rate limits?
    # statuses = api.Search('good')
    query = "good"
    tweet_query = Tweet.all().filter('keywords = ', query).order('-created_at')
    statuses = tweet_query.fetch(100)
    template_values = {
      'query' : query,
      'statuses': statuses,
      'count' : 100,
      }

    path = os.path.join(os.path.dirname(__file__), 'index.html')
    self.response.out.write(template.render(path, template_values))

class PopulateDatabase(webapp.RequestHandler):
    # Separating out database intensive updates
    # from display and processing
    # This sub-URL (eventually obfuscated) gets the latest
    # search results and adds to database.
    # Will need to be called for new results? Or just add
    # all tweets.
    # Note: Disk size might be a problem!
  def get(self, query):
    api = twitter.Api()
    the_now = datetime.now()
    statuses = api.Search(query)
    inserted_count = 0
    tweet_putlist = []
    for status in statuses:
        tweet_query = Tweet.get_by_key_name("t" + str(status.id))
        if not (tweet_query):
            # Insert into our database
            # since_id doesn't work because we need different ids for each query
            
            # +0000 static or variable?! lets see.
            # Seems to work for every tweet so I'm assuming static.
            created_datetime = datetime.strptime(status.created_at,
                                            "%a, %d %b %Y %H:%M:%S +0000")
            now_datetime = datetime.fromtimestamp(status.now)
            
            # Find the list of keywords from the tweet
            # Ignoring fancy stuff like term extraction for now
            keywords = status.text.split()
            # But do need to lowercase and strip
            keywords_lc = []
            for word in keywords:
                lastchar = word[-1:]
                if lastchar in [",", ".", "!", "?", ";"]:
                    word2 = word.rstrip(lastchar)
                else:
                    word2 = word
                keywords_lc.append(word2.lower())
    
            tweet = Tweet(
                          created_at = created_datetime,
                          author = status.user.screen_name,
                          user = status.user.id,
                          text = status.text,
                          id = status.id,
                          now = now_datetime,
                          keywords = keywords_lc,
                          key_name = "t" + str(status.id)
                          )
            tweet_putlist.append(tweet)
            inserted_count += 1
    db.put(tweet_putlist)
    time_delta = datetime.now() - the_now
    print "Inserted %s tweets matching %s" % (inserted_count,query)
    print "in %s" % (time_delta)


class UserStatuses(webapp.RequestHandler):
  def get(self, username):
    api = twitter.Api() 
    statuses = api.GetUserTimeline(username)
    
    template_values = {
      'statuses': statuses,
      }

    path = os.path.join(os.path.dirname(__file__), 'index.html')
    self.response.out.write(template.render(path, template_values))
    
application = webapp.WSGIApplication(
                                     [('/', MainPage),
                                      ('/populate/(.*)', PopulateDatabase),
                                      ('/user/(.*)', UserStatuses),],
                                     debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()