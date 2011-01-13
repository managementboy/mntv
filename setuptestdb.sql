create database mythnettv_tests;
create user 'test'@'localhost' identified by 'test';
grant alter, create, select, insert, update, delete, drop on mythnettv_tests.* to 'test'@'localhost';
flush PRIVILEGES;

use mythnettv_tests;

CREATE TABLE `channel` (
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
  `last_record` datetime NOT NULL,
  `default_authority` varchar(32) NOT NULL default '',
  `commmethod` int(11) NOT NULL default '-1',
  PRIMARY KEY  (`chanid`),
  KEY `channel_src` (`channum`,`sourceid`),
  KEY `sourceid` (`sourceid`,`xmltvid`,`chanid`),
  KEY `visible` (`visible`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1;

