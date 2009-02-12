import os
from google.appengine.ext.webapp import template
import cgi
import twitter
from datetime import datetime, timedelta
import stockquote

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
  # And for retrieval:
  keywords = db.StringListProperty()
  
class Stock(db.Model):
  # Representing a stock price
  ticker = db.StringProperty()
  keywords = db.StringListProperty()

class StockQuote(db.Model):
  # A quote is a child of a Stock
  # So we can keep a historical account of values
  stock = db.ReferenceProperty(Stock, collection_name='quotes')
  value = db.FloatProperty()
  time = db.DateTimeProperty()

class TweetBag(db.Model):
  # Links a Stock with a set of Tweets
  stock = db.ReferenceProperty(Stock, collection_name='volume')
  sample_tweet = db.ReferenceProperty(Tweet, collection_name='bags')
  time = db.DateTimeProperty() # Start of the 5-min period
  count = db.IntegerProperty()

class MainPage(webapp.RequestHandler):
  def get(self):
    # api = twitter.Api()
    # moved api call to PopulateDatabase method
    # here we can also have (some) control on rate limits?
    # statuses = api.Search('good')
    query = "yahoo"
    stock_query = Stock.all().filter('keywords =', query).fetch(1)[0]
    
    now_quote = stockquote.get_quote(stock_query.ticker.upper())
    
    tweet_query = Tweet.all().filter('keywords = ', query).order('-created_at')
    statuses = tweet_query.fetch(20)
    count = 20 # otherwise it 'almost' re-searches
    template_values = {
      'stock' : now_quote,
      'ticker' : stock_query.ticker,
      'query' : query,
      'statuses': statuses,
      'count' : count,
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
    print "Inserted %s tweets matching %s in %s" % (inserted_count,query,time_delta)

class PopulateStock(webapp.RequestHandler):
  def get(self, ticker):
    stock_price = stockquote.get_quote(ticker.upper())
    stock = Stock.get_by_key_name(ticker)
    if stock:
      quote = StockQuote(stock = stock,
                         value = float(stock_price),
                         time  = datetime.now())
      quote.put()
      self.response.out.write("Successful")
    else:
      stockobj = Stock(ticker = ticker,
                       key_name = ticker,
                       keywords = ["yahoo","yhoo","carol bartz"])
      stockobj.put()
      self.response.out.write("Created")

class UserStatuses(webapp.RequestHandler):
  def get(self, username):
    api = twitter.Api() 
    statuses = api.GetUserTimeline(username)
    
    template_values = {
      'statuses': statuses,
      }

    path = os.path.join(os.path.dirname(__file__), 'index.html')
    self.response.out.write(template.render(path, template_values))
    
class ArchiveDeltas(webapp.RequestHandler):
  def get(self,time):
    ticker = "yhoo"
    ticker_instance = Stock.get_by_key_name(ticker)
    # time = how many hours back in the past we go
    # loop between now-time and now-time-1
    start_time = datetime.now() - timedelta(hours=int(time))
    end_time = start_time - timedelta(hours=1)
    loop_time = start_time
    
    # Check we aren't already covering this time period
    exists_query = TweetBag.all().filter("stock = ", ticker_instance).filter("time >", end_time).filter("time <", start_time).order("-time")
    if exists_query.count() > 0:
      highest = exists_query.get()
      end_time = highest.time
         
    inserts = []
    while loop_time > end_time:
      num_tweets = 0
      loop_time_5 = loop_time - timedelta(minutes=5)
      for keyword in ticker_instance.keywords:
         tweet_query = Tweet.all().filter("keywords = ", keyword).filter("created_at > ", loop_time_5).filter("created_at < ", loop_time)
         num_tweets += tweet_query.count()
      bagobj = TweetBag (
        sample_tweet = tweet_query.get(),
        stock = ticker_instance,
        count = num_tweets,
        time = loop_time_5
      )
      inserts.append(bagobj)
      loop_time = loop_time_5
    db.put(inserts)
    
class StockDisplay(webapp.RequestHandler):
  def get(self,period):
    # Default
    ticker = "yhoo"
    if period == "":
      period = "24"
      
    # Get last $period hours ticker data from database
    yesterday_now = datetime.now() - timedelta(hours=int(period))
    
    ticker_instance = Stock.get_by_key_name(ticker)
    stock_query = StockQuote.all().filter("stock = ", ticker_instance.key()).filter("time  > ", yesterday_now).order("-time")
    # Should be 288 results. Fetching 300 in case of individual non-cron queries
    stockquotes = stock_query.fetch(1000)
    
    # use our new TweetBag object
    tweet_bag_query = TweetBag.all().filter("stock = ", ticker_instance).filter("time >", yesterday_now).order("-time")
    tweet_bag = tweet_bag_query.fetch(1000)
    
    # Now find matching tweets. Need to use ticker_instance.keywords
    #for keyword in ticker_instance.keywords:
    #  tweet_matches = Tweet.all().filter("created_at > ", yesterday_now).filter("keywords =", keyword).order("-created_at")
    #  tweet_results = tweet_matches.fetch(500)
    #  tweet_bag.extend(tweet_results)
    
    template_values = {
      'tweets' : tweet_bag,
      'stockquotes' : stockquotes,
      'since' : yesterday_now,
      'ticker' : ticker.upper(),
    }
    
    path = os.path.join(os.path.dirname(__file__), 'stock.html')
    self.response.out.write(template.render(path, template_values))
    
    
application = webapp.WSGIApplication(
                                     [('/', MainPage),
                                      ('/populate/(.*)', PopulateDatabase),
                                      ('/check_stock/(.*)', PopulateStock),
                                      ('/user/(.*)', UserStatuses),
                                      ('/stock/(.*)', StockDisplay),
                                      ('/deltas/(.*)', ArchiveDeltas),],
                                     debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()