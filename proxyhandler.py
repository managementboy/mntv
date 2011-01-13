#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2008
# Released under the terms of the GNU GPL v2

# A simple wrapper around urllib2 which is used for all HTTP access. This
# provides a central place for implementing the HTTP proxy functionality.

import datetime
import re
import sys
import urllib2

import database
import utility


class DownloadBudgetExceededException(utility.LoggingException):
  """ A proxy budget error """


class HttpHandler(object):
  """ Download HTTP content, possibly using a HTTP proxy as defined in the
      database.
  """

  def __init__(self, db):
    self.db = db
    self.http_proxy = None
    self.budget = 0

  def UsedProxy(self):
    """ Return the proxy which was used for the most recent download. """
    return self.http_proxy

  def LookupProxy(self, url):
    """ Determine if a proxy should be used for a given URL. """

    # Strip off the http:// if present
    if url.startswith('http://'):
      url = url[7:]

    for row in self.db.GetRows('select * from mythnettv_proxies;'):
      url_re = re.compile(row['url'])
      m = url_re.match(url)
      if m:
        return (row['http_proxy'], row['daily_budget'])
        
    return (None, None)

  def Open(self, url, force_proxy=None, force_budget=-1, out=sys.stdout):
    """ Return a file like object for the HTTP access, possibly using a proxy
        in the process.
    """
    
    request = urllib2.Request(url)
    request.add_header('User-Agent',
                       'MythNetTV http://www.stillhq.com/mythtv/mythnettv/')

    (self.http_proxy, self.budget) = self.LookupProxy(url)
    if force_proxy:
      self.http_proxy = force_proxy
    if force_budget != -1:
      self.budget = force_budget

    opener = None
    
    if self.http_proxy:
      out.write('Using proxy %s for %s\n' %(self.http_proxy, url))
      proxy_support = urllib2.ProxyHandler({'http': 'http://%s'
                                                    % self.http_proxy})
      opener = urllib2.build_opener(proxy_support)
    else:
      opener = urllib2.build_opener()
    
    return opener.open(request)

  def LogProxyUsage(self, bytes):
    """ Log how much we transferred through the proxy. """

    # TODO(mikal): there is a potential bug here with the date rolling
    # over between these two statements, but it is very unlikely
    if self.http_proxy:
      self.db.ExecuteSql('insert ignore into mythnettv_proxy_usage '
                         '(day, http_proxy, bytes) values '
                         '(date(now()), "%s", 0);'
                         % self.http_proxy)
      self.db.ExecuteSql('update mythnettv_proxy_usage '
                         'set bytes = bytes + %d where '
                         'day = date(now()) and http_proxy="%s";'
                         %(bytes, self.http_proxy))
      self.db.ExecuteSql('commit;')

  def ReportRecentProxyUsage(self, out=sys.stdout):
    """ Report on recent proxy usage """

    for row in self.db.GetRows('select distinct(http_proxy) from '
                               'mythnettv_proxy_usage;'):
      out.write('%s:\n' % row['http_proxy'])
      for subrow in self.db.GetRows('select * from mythnettv_proxy_usage '
                                    'where http_proxy="%s" '
                                    'order by day desc limit 7;'
                                    % row['http_proxy']):
        out.write('  %s = %s\n'
                  %(subrow['day'],
                    utility.DisplayFriendlySize(subrow['bytes'])))
      out.write('\n')

  def GetBudget(self):
    """ Return the current budget """
    return self.budget

  def BudgetAllowsDownload(self, proposed_read_size):
    """ If I was to read proposed_read_size bytes, would I exceed the
        budget for this proxy?
    """

    if not self.http_proxy:
      return True

    row = self.db.GetOneRow('select * from mythnettv_proxy_usage '
                            'where http_proxy="%s" and day=date(now());'
                            % self.http_proxy)
    if self.budget > row['bytes'] + proposed_read_size:
      return True

    return False


def HTTPCopy(db, proxy, remote, local, out=sys.stdout):
  """Copy a file from a remote HTTP server to a local file."""

  total = 0
  count = 0

  # TODO(mikal): Size should be determined beforehand if possible
  while True:
    data = remote.read(1024)
    length = len(data)
    local.write(data)
    if length < 1024:
      return total

    total += length
    proxy.LogProxyUsage(length)

    if count > 3000:
      count = 0
      out.write('%s: downloaded %s\n'
                %(datetime.datetime.now(),
                  utility.DisplayFriendlySize(total)))

    count += 1

    if not proxy.BudgetAllowsDownload(1024):
      budget = utility.DisplayFriendlySize(proxy.GetBudget())
      raise DownloadBudgetExceededException(db, '%s budget of %s exceeded'
                                            %(proxy.UsedProxy(), budget))
