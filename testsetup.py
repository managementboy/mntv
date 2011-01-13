#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2006, 2007, 2008
# Released under the terms of the GNU GPL v2

# Helpers for unit tests


import datetime
import os
import sys
import urllib
import MySQLdb

from socket import gethostname


class TestSetupException(Exception):
  """ Test setup failed for some reason """


def SetupTestingDatabase(cursor):
  """ Create an empty database for testing """

  tables = []
  cursor.execute('show tables;')
  for row in cursor:
    tables.append(row[row.keys()[0]])

  for table in tables:
    print 'Dropping old testing table: %s' % table
    cursor.execute('drop table %s;' % table)
    cursor.execute('commit;')
    
  # Create the needed MythTV channels
  cursor.execute("""CREATE TABLE `channel` (
  `chanid` int(10) unsigned NOT NULL default '0',
  `channum` varchar(10) NOT NULL default '',
  `freqid` varchar(10) default NULL,
  `sourceid` int(10) unsigned default NULL,
  `callsign` varchar(20) NOT NULL default '',
  `name` varchar(64) NOT NULL default '',
  `icon` varchar(255) NOT NULL default 'none',
  `finetune` int(11) default NULL,
  `videofilters` varchar(255) NOT NULL default '',
  `xmltvid` varchar(64) NOT NULL default '',
  `recpriority` int(10) NOT NULL default '0',
  `contrast` int(11) default '32768',
  `brightness` int(11) default '32768',
  `colour` int(11) default '32768',
  `hue` int(11) default '32768',
  `tvformat` varchar(10) NOT NULL default 'Default',
  `commfree` tinyint(4) NOT NULL default '0',
  `visible` tinyint(1) NOT NULL default '1',
  `outputfilters` varchar(255) NOT NULL default '',
  `useonairguide` tinyint(1) default '0',
  `mplexid` smallint(6) default NULL,
  `serviceid` mediumint(8) unsigned default NULL,
  `atscsrcid` int(11) default NULL,
  `tmoffset` int(11) NOT NULL default '0',
  `atsc_major_chan` int(10) unsigned NOT NULL default '0',
  `atsc_minor_chan` int(10) unsigned NOT NULL default '0',
  PRIMARY KEY  (`chanid`),
  KEY `channel_src` (`channum`,`sourceid`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1""")
  cursor.execute('commit;')

  # Create a fake MythTV settings table
  cursor.execute("""CREATE TABLE `settings` (
  `value` varchar(128) NOT NULL default '',
  `data` text,
  `hostname` varchar(255) default NULL,
  KEY `value` (`value`,`hostname`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1""")
  cursor.execute('commit;')

  cursor.execute('insert into settings (value, data, hostname) '
                 'values("RecordFilePrefix", "/tmp/testmyth", "%s");'
                 % gethostname())
  cursor.execute('commit;')

  # Create a fake recordings table
  cursor.execute("""CREATE TABLE `recorded` (
  `chanid` int(10) unsigned NOT NULL default '0',
  `starttime` datetime NOT NULL default '0000-00-00 00:00:00',
  `endtime` datetime NOT NULL default '0000-00-00 00:00:00',
  `title` varchar(128) NOT NULL default '',
  `subtitle` varchar(128) NOT NULL default '',
  `description` text NOT NULL,
  `category` varchar(64) NOT NULL default '',
  `hostname` varchar(255) NOT NULL default '',
  `bookmark` tinyint(1) NOT NULL default '0',
  `editing` int(10) unsigned NOT NULL default '0',
  `cutlist` tinyint(1) NOT NULL default '0',
  `autoexpire` int(11) NOT NULL default '0',
  `commflagged` int(10) unsigned NOT NULL default '0',
  `recgroup` varchar(32) NOT NULL default 'Default',
  `recordid` int(11) default NULL,
  `seriesid` varchar(12) NOT NULL default '',
  `programid` varchar(20) NOT NULL default '',
  `lastmodified` timestamp NOT NULL default CURRENT_TIMESTAMP on update CURRENT_TIMESTAMP,
  `filesize` bigint(20) NOT NULL default '0',
  `stars` float NOT NULL default '0',
  `previouslyshown` tinyint(1) default '0',
  `originalairdate` date default NULL,
  `preserve` tinyint(1) NOT NULL default '0',
  `findid` int(11) NOT NULL default '0',
  `deletepending` tinyint(1) NOT NULL default '0',
  `transcoder` int(11) NOT NULL default '0',
  `timestretch` float NOT NULL default '1',
  `recpriority` int(11) NOT NULL default '0',
  `basename` varchar(128) NOT NULL default '',
  `progstart` datetime NOT NULL default '0000-00-00 00:00:00',
  `progend` datetime NOT NULL default '0000-00-00 00:00:00',
  `playgroup` varchar(32) NOT NULL default 'Default',
  `profile` varchar(32) NOT NULL default '',
  `duplicate` tinyint(1) NOT NULL default '0',
  `transcoded` tinyint(1) NOT NULL default '0',
  `watched` tinyint(4) NOT NULL default '0',
  PRIMARY KEY  (`chanid`,`starttime`),
  KEY `endtime` (`endtime`),
  KEY `seriesid` (`seriesid`),
  KEY `programid` (`programid`),
  KEY `title` (`title`),
  KEY `recordid` (`recordid`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1""")
  cursor.execute('commit;')


def DownloadTestData(filename):
  """ Download a file needed for a unit test, and store it in the testdata
      directory.
  """

  # TODO(mikal): This should probably use the proxy framework, as that
  # currently needs a database, and the only caller of this doesn't create one
  # of those.

  if not os.path.exists('/tmp/testdata'):
    os.makedirs('/tmp/testdata')

  if not os.path.isdir('/tmp/testdata'):
    raise TestSetupException('/tmp/testdata is not a directory')

  if not os.path.exists('/tmp/testdata/%s' % filename):
    sys.stderr.write('Fetching %s\n' % filename)
    remote = urllib.urlopen('http://www.stillhq.com/mythtv/mythnettv/'
                            'testdata/%s' % filename)
    local = open('/tmp/testdata/%s' % filename, 'w')

    data = remote.read(1024 * 100)
    total = len(data)
    while data:
      sys.stderr.write('  %s ... %d bytes fetched\n' %(datetime.datetime.now(),
                                                       total))
      local.write(data)
      data = remote.read(1024 * 100)
      total += len(data)

    remote.close()
    local.close()
    sys.stderr.write('  %s ... %d total bytes fetched\n\n'
                     %(datetime.datetime.now(), total))
