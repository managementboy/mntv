#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2008
# Released under the terms of the GNU GPL v2

# Unit tests for mythnettv's primary user interface

# Tests for the utility methods


import unittest
import MySQLdb

import utility


class DisplayFriendlySizeTest(unittest.TestCase):
  def testSmallUnchanged(self):
    """ Small values should be unchanged """
    
    self.assertEqual(utility.DisplayFriendlySize(42), '42 bytes')

  def testKbWorks(self):
    """ Display values in kilobytes correctly """
    
    fourtytwo_kb = 42 * 1024
    self.assertEqual(utility.DisplayFriendlySize(fourtytwo_kb),
                     '42 kb (%d bytes)' % fourtytwo_kb)

  def testMbWorks(self):
    """ Display values in megabytes correctly """
    
    fourtytwo_mb = 42 * 1024 * 1024
    self.assertEqual(utility.DisplayFriendlySize(fourtytwo_mb),
                     '42 mb (%d bytes)' % fourtytwo_mb)

  def testGbWorks(self):
    """ Display values in gigabytes correctly """
    
    fourtytwo_gb = 42 * 1024 * 1024 * 1024
    self.assertEqual(utility.DisplayFriendlySize(fourtytwo_gb),
                     '42 gb (%d bytes)' % fourtytwo_gb)

  def testTbWorks(self):
    """ Very large values just end up in gigabytes """
    
    fourtytwo_tb = 42 * 1024 * 1024 * 1024 * 1024
    self.assertEqual(utility.DisplayFriendlySize(fourtytwo_tb),
                     '%d gb (%d bytes)' %(42 * 1024, fourtytwo_tb))

  def testBadInput(self):
    """ What happens if you hand in something which isn't a number? """

    self.assertEqual(utility.DisplayFriendlySize('banana'),
                     'NotANumber(<type \'str\'>=banana)')


class DisplayFriendlyTimeTest(unittest.TestCase):
  def testSmallUnchanged(self):
    """ Small values should be unchanged """
    self.assertEqual(utility.DisplayFriendlyTime(42), '42 seconds')

  def testMinutes(self):
    """ Minutes should work too """
    self.assertEqual(utility.DisplayFriendlyTime(70), '1 minutes, 10 seconds')

  def testHours(self):
    """ Hours as well """
    self.assertEquals(utility.DisplayFriendlyTime(3674),
                      '1 hours, 1 minutes, 14 seconds')


if __name__ == "__main__":
  unittest.main() 
