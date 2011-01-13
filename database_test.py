#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2009
# Released under the terms of the GNU GPL v2

# Unit tests for mythnettv's database module


import gflags
import os
import sys
import unittest
import MySQLdb

import database
import testsetup
import proxyhandler


FLAGS = gflags.FLAGS


class DatabaseTest(unittest.TestCase):
  """ Test the previously erroneous portions of database.py """
  
  def testSingleQuoteEscape(self):
    db = database.MythNetTvDatabase(dbname='mythnettv_tests',
                                    dbuser='test',
                                    dbpassword='test',
                                    dbhost='localhost')
    self.assertEquals("\"''Banana''\"",
                      db.FormatSqlValue('string', "'Banana'"))
  
  def testDoubleQuoteEscape(self):
    # Double quotes need to be escaped, and strings are returned wrapped in
    # double quotes, so we expect _three_ levels of double quotes here.

    db = database.MythNetTvDatabase(dbname='mythnettv_tests',
                                    dbuser='test',
                                    dbpassword='test',
                                    dbhost='localhost')
    self.assertEquals('"""Banana"""', db.FormatSqlValue('string', '"Banana"'))
    

if __name__ == "__main__":
  # Parse flags
  try:
    argv = FLAGS(sys.argv)
  except gflags.FlagsError, e:
    out.write('%s\n' % e)
    Usage(out)

  unittest.main()
