#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2008
# Released under the terms of the GNU GPL v2

# Unit tests for mythnettv's proxyhandler module


import gflags
import os
import sys
import unittest
import MySQLdb

import database
import testsetup
import proxyhandler


FLAGS = gflags.FLAGS


class ProxyHandlerTest(unittest.TestCase):
  """ Test the proxy handling functionality. Note it is assumed in these
      tests that the testing database has already been setup by the
      mythnettv_test tests.
  """
  
  def Cursor(self):
    """ Return a cursor to the test database """
    db_connection = MySQLdb.connect(host = 'localhost',
                                    user = 'test',
                                    passwd = 'test',
                                    db = 'mythnettv_tests')
    return db_connection.cursor(MySQLdb.cursors.DictCursor)
  
  def setUp(self):
    # Clear out the proxies table so we start from a clean slate
    cursor = self.Cursor()

    cursor.execute('delete from mythnettv_proxies;')
    cursor.execute('commit;')

    # Now add one proxy
    cursor.execute('insert into mythnettv_proxies(url, http_proxy) values '
                   '("proxy\.stillhq\.com", "proxyhost.stillhq.com:3128");')
    cursor.execute('commit;')

  def testNoProxy(self):
    db = database.MythNetTvDatabase(dbname='mythnettv_tests',
                                    dbuser='test',
                                    dbpassword='test',
                                    dbhost='localhost')
    proxy = proxyhandler.HttpHandler(db)
    self.assertEquals(proxy.LookupProxy('www.stillhq.com/index.html'),
                      (None, None))
    self.assertEquals(proxy.LookupProxy('http://www.stillhq.com/index.html'),
                      (None, None))
    
  def testYesProxy(self):
    db = database.MythNetTvDatabase(dbname='mythnettv_tests',
                                    dbuser='test',
                                    dbpassword='test',
                                    dbhost='localhost')
    proxy = proxyhandler.HttpHandler(db)
    self.assertEquals(proxy.LookupProxy('proxy.stillhq.com/index.html'),
                      ('proxyhost.stillhq.com:3128', None))
    self.assertEquals(proxy.LookupProxy('http://proxy.stillhq.com/'
                                        'index.html'),
                      ('proxyhost.stillhq.com:3128', None))
    

if __name__ == "__main__":
  # Parse flags
  try:
    argv = FLAGS(sys.argv)
  except gflags.FlagsError, e:
    out.write('%s\n' % e)
    Usage(out)

  unittest.main()
