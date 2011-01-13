#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2008
# Released under the terms of the GNU GPL v2

# Unit tests for mythnettv's syndication module


import cStringIO
import socket
import sys
import unittest
import MySQLdb

# This hackery is to get around "mythnettv" not having a .py at the end of its
# filename
import imp
mythnettv = imp.load_module('mythnettv', open('mythnettv'), 'mythnettv',
                            ('.py', 'U', 1))

import database
import gflags
import program
import proxyhandler
import mythnettvcore
import syndication
import testsetup


FLAGS = gflags.FLAGS


class SyndicationTests(unittest.TestCase):
  def Cursor(self):
    """ Return a cursor to the test database """
    db_connection = MySQLdb.connect(host = 'localhost',
                                    user = 'test',
                                    passwd = 'test',
                                    db = 'mythnettv_tests')
    return db_connection.cursor(MySQLdb.cursors.DictCursor)
  
  def setUp(self):
    testsetup.SetupTestingDatabase(self.Cursor())

  def testBadDates(self):
    """ testBadDates -- test a feed which has had date parsing problems in
        the past
    """

    db = database.MythNetTvDatabase(dbname='mythnettv_tests',
                                    dbuser='test',
                                    dbpassword='test',
                                    dbhost='localhost')
    proxy = proxyhandler.HttpHandler(db)
    xmlfile = proxy.Open('http://www.stillhq.com/mythtv/mythnettv/testdata/'
                         'baddates.xml')
    output = cStringIO.StringIO()
    syndication.Sync(db, xmlfile, 'Bad Dates', out=output)
    xmlfile.close()

class SyndicationTests(unittest.TestCase):
  """ The BoingBoing TV syndication file caused a bunch of problems, so it
      gets its own set of tests.
  """
  
  def Cursor(self):
    """ Return a cursor to the test database """
    db_connection = MySQLdb.connect(host = 'localhost',
                                    user = 'test',
                                    passwd = 'test',
                                    db = 'mythnettv_tests')
    return db_connection.cursor(MySQLdb.cursors.DictCursor)
  
  def setUp(self):
    testsetup.SetupTestingDatabase(self.Cursor())

  def testImport(self):
    """ testImport -- make sure an import gives the expected results """

    db = database.MythNetTvDatabase(dbname='mythnettv_tests',
                                    dbuser='test',
                                    dbpassword='test',
                                    dbhost='localhost')
    proxy = proxyhandler.HttpHandler(db)
    xmlfile = proxy.Open('http://www.stillhq.com/mythtv/mythnettv/testdata/'
                         'boingboing.xml')
    output = cStringIO.StringIO()
    syndication.Sync(db, xmlfile, 'Boing Boing', out=output)
    xmlfile.close()

    # 30 programs should have been created
    row = db.GetOneRow('select count(*) from mythnettv_programs where '
                       'title="Boing Boing";')
    self.assertEqual(row['count(*)'], 30,
                     'There is the right number of programs')

    # Ok, so let's try to grab one of the troublesome programs
    prog = program.MythNetTvProgram(db)
    prog.Load('http://tv.boingboing.net/2008/09/03/'
              'best-of-bbtv-david-b.html')
    self.assertEqual(prog.GetSubtitle(),
                     'Best of BBtv - David Byrne "Playing the Building."',
                     'Program has the wrong title')

    # Download it
    datadir = db.GetSettingWithDefault('datadir', '/tmp/testdata')

    # If we're running this test from Mikal's house, use the cache to speed it
    # up
    if socket.gethostname() != 'molokai':
      prog.Download(datadir)
    else:
      prog.Download(datadir, force_proxy='molokai.stillhq.com:3128',
                    force_budget=1000000000)
    prog.Import()

    # Now make sure we have it
    cursor = self.Cursor()
    cursor.execute('select * from recorded where subtitle like "%Playing%";')
    self.assertEqual(cursor.rowcount, 1, "Wrong number of shows imported")
    

if __name__ == "__main__":
  # Parse flags
  try:
    argv = FLAGS(sys.argv)
  except gflags.FlagsError, e:
    out.write('%s\n' % e)
    Usage(out)

  unittest.main() 
