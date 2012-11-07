#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2006, 2007, 2008
# Released under the terms of the GNU GPL v2

# Unit tests for mythnettv's primary user interface

# This hackery is to get around "mythnettv" not having a .py at the end of its
# filename
import imp
mythnettv = imp.load_module('mythnettv', open('mythnettv'), 'mythnettv',
                            ('.py', 'U', 1))


import cStringIO
import gflags
import os
import sys
import unittest
import MySQLdb

import testsetup


FLAGS = gflags.FLAGS


class GetPossibleTest(unittest.TestCase):
  def testEntryPresent(self):
    self.assertEquals(mythnettv.GetPossible([1, 2, 3, 4], 1), 2)

  def testEntryMissing(self):
    self.assertEquals(mythnettv.GetPossible([], 1), None)


class UserInterfaceTests(unittest.TestCase):
  def Cursor(self):
    """ Return a cursor to the test database """
    db_connection = MySQLdb.connect(host = 'localhost',
                                    user = 'test',
                                    passwd = 'test',
                                    db = 'mythnettv_tests')
    return db_connection.cursor(MySQLdb.cursors.DictCursor)
  
  def setUp(self):
    # Make sure we have a data directory on disk
    if not os.path.isdir('/tmp/testdata'):
      os.makedirs('/tmp/testdata')

    # Make sure we have a fake MythTV recordings directory
    if not os.path.isdir('/tmp/testmyth'):
      os.makedirs('/tmp/testmyth')

    testsetup.SetupTestingDatabase(self.Cursor())

  # This magic fake command line is needed to trick mythnettv into using
  # the test database instance, and a random data directory
  REQUIRED_INVOKATION = ['mythnettv', '--db_host=localhost', '--db_user=test',
                         '--db_password=test', '--db_name=mythnettv_tests',
                         '--datadir=/tmp/testdata', 
                         '--nopromptforannounce']

  def AssertOutputContains(self, output, substring):
    """ A simple wrapper to ensure that some output contains an expected
        string.
    """

    self.assertNotEqual(output.find(substring), -1,
                        """*********
I expected to find the string "%s" in this output:

%s

*********"""
                        %(substring, output))

  def AssertOutputDoesntContain(self, output, substring):
    """ A simple wrapper to ensure that some output does not contain an
        expected string.
    """

    self.assertEqual(output.find(substring), -1,
                        """*********
I expected to not find the string "%s" in this output:

%s

*********"""
                        %(substring, output))

  def testEverything(self):
    """ This is lots of different tests, but they need to be run in this order,
        so they are all in here. I am sure there is a better way I haven't
        thought of.
    """

    # Just test if we can start up
    output = cStringIO.StringIO()
    mythnettv.main(self.REQUIRED_INVOKATION + ['list'],
                   out=output)

    # Subscribe to something
    output = cStringIO.StringIO()
    mythnettv.main(self.REQUIRED_INVOKATION +
                   ['subscribe',
                    'http://www.stillhq.com/mythtv/mythnettv/testdata/'
                    'gruen_mp4.xml', 'Gruen Transfer', '', '', ''],
                   out=output)
    self.AssertOutputContains(output.getvalue(), 'Subscribed to')

    # The update the program list
    output = cStringIO.StringIO()
    mythnettv.main(self.REQUIRED_INVOKATION + ['update'],
                   out=output)
    self.AssertOutputContains(output.getvalue(), 'Creating program for')

    # A second update should find nothing new
    output = cStringIO.StringIO()
    mythnettv.main(self.REQUIRED_INVOKATION + ['update'],
                   out=output)
    self.AssertOutputDoesntContain(output.getvalue(), 'Creating program for')

    # Can we determine what to download next?
    output = cStringIO.StringIO()
    mythnettv.main(self.REQUIRED_INVOKATION +
                   ['nextdownload', '100', 'Gruen Transfer'],
                   out=output)
    self.AssertOutputContains(output.getvalue(), '1 matches')

    # Download the program
    output = cStringIO.StringIO()
    mythnettv.main(self.REQUIRED_INVOKATION +
                   ['download', '100', 'Gruen Transfer'],
                   out=output)
    self.AssertOutputContains(output.getvalue(), 'Done')
    self.AssertOutputContains(output.getvalue(),
                              'I don\'t know if we need to '
                              'transcode videos in '
                              'DVSD format')

    # There should be nothing left to download
    output = cStringIO.StringIO()
    mythnettv.main(self.REQUIRED_INVOKATION +
                   ['nextdownload', '100', 'Gruen Transfer'],
                   out=output)
    self.AssertOutputContains(output.getvalue(), '0 matches')

    # Import a local file and make sure that works too
    output = cStringIO.StringIO()
    mythnettv.main(self.REQUIRED_INVOKATION +
                   ['importlocal', '/data/video/testdata/foo.avi',
                    'Local Import Test', '--', '--'],
                   out=output)
    self.AssertOutputContains(output.getvalue(), 'Done')

    # Try a direct fetch of a URL to a video
    output = cStringIO.StringIO()
    mythnettv.main(self.REQUIRED_INVOKATION +
                   ['importremote',
                    'http://www.stillhq.com/mythtv/mythnettv/testdata/'
                    'gruen_2008_ep10.mp4',
                    'Remote Import Test', '--', '--'],
                   out=output)
    self.AssertOutputContains(output.getvalue(), 'Done')

    # Try a direct fetch of a URL to a video
    output = cStringIO.StringIO()
    mythnettv.main(self.REQUIRED_INVOKATION +
                   ['url',
                    'http://www.stillhq.com/mythtv/mythnettv/testdata/'
                    'vimeo.rss',
                    'Sk8Columbia'],
                   out=output)

    # Try an apple feed which used to cause unicode problems
    # TODO(mikal): move this into a more generic set of feed unit
    # tests
    output = cStringIO.StringIO()
    mythnettv.main(self.REQUIRED_INVOKATION +
                   ['url',
                    'http://www.stillhq.com/mythtv/mythnettv/testdata/'
                    'apple-quick-tip-of-the-week.xml',
                    'Apple Quick Tips'],
                   out=output)
    mythnettv.main(self.REQUIRED_INVOKATION + ['update'],
                   out=output)

    # Try a feed which has had date problems in the past
    output = cStringIO.StringIO()
    mythnettv.main(self.REQUIRED_INVOKATION +
                   ['url',
                    'http://www.stillhq.com/mythtv/mythnettv/testdata/'
                    'hak5.xml',
                    'hak5'],
                   out=output)
    print output.getvalue()
    
    ################
    # Check the state of the database at the end of the tests
    ################
    cursor = self.Cursor()

    # There should be twelve tables now
    cursor.execute('show tables')
    self.assertEqual(cursor.rowcount, 12)

    # The channel table should have a MythNetTV channel
    cursor.execute('select * from channel where name="MythNetTV";')
    self.assertEqual(cursor.rowcount, 1)

    # The recordings table should have one Gruen in it
    cursor.execute('select * from recorded '
                   'where subtitle="The Gruen Transfer Episode 10";')
    self.assertEqual(cursor.rowcount, 1)

    # The recordings table should have one local transfer in it
    cursor.execute('select * from recorded '
                   'where title="Local Import Test";')
    self.assertEqual(cursor.rowcount, 1)

    # The recordings table should have one local transfer in it
    cursor.execute('select * from recorded '
                   'where title="Remote Import Test";')
    self.assertEqual(cursor.rowcount, 1)

if __name__ == "__main__":
  # Parse flags
  try:
    argv = FLAGS(sys.argv)
  except gflags.FlagsError, e:
    out.write('%s\n' % e)
    Usage(out)

  unittest.main() 
