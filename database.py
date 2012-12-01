#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2006, 2007, 2008
# Released under the terms of the GNU GPL v2

import datetime
import MySQLdb
import os
import sys
import traceback
import unicodedata
import program

import gflags
FLAGS = gflags.FLAGS
gflags.DEFINE_string('db_host', '',
                     'The name of the host the MySQL database is on, '
                     'don\'t define if you want to parse mysql.txt '
                     'instead')
gflags.DEFINE_string('db_user', '',
                     'The name of the user to connect to the database with, '
                     'don\'t define if you want to parse mysql.txt '
                     'instead')
gflags.DEFINE_string('db_password', '',
                     'The password for the database user, '
                     'don\'t define if you want to parse mysql.txt '
                     'instead')
gflags.DEFINE_string('db_name', '',
                     'The name of the database which MythNetTV uses, '
                     'don\'t define if you want to parse mysql.txt '
                     'instead')

gflags.DEFINE_boolean('db_debugging', False,
                      'Output debugging messages for the database')


CURRENT_SCHEMA='23'
HAVE_WARNED_OF_DEFAULTS = False


class FormatException(Exception):
  """ FormatException -- Used for reporting failures for format DB values """


def Normalize(value):
  normalized = unicodedata.normalize('NFKD', unicode(value))
  normalized = normalized.encode('ascii', 'ignore')
  return normalized


class MythNetTvDatabase:
  """MythNetTvDatabase -- handle all MySQL details"""

  def __init__(self, dbname=None, dbuser=None, dbpassword=None,
               dbhost=None):
    self.OpenConnection(dbname=dbname, dbuser=dbuser, dbpassword=dbpassword,
                        dbhost=dbhost)
    self.CheckSchema()
    self.CleanLog()
    self.RepairMissingDates()

  def OpenConnection(self, dbname=None, dbuser=None, dbpassword=None,
                     dbhost=None):
    """OpenConnection -- parse the MythTV config file and open a connection
    to the MySQL database"""

    global HAVE_WARNED_OF_DEFAULTS

    if dbname:
      # This override makes writing unit tests simpler
      db_name = dbname
    else:
      db_name = FLAGS.db_name

    if dbuser:
      user = dbuser
    else:
      user = FLAGS.db_user

    if dbpassword:
      password = dbpassword
    else:
      password = FLAGS.db_password

    if dbhost:
      host = dbhost
    else:
      host = FLAGS.db_host

    if not host or not user or not password or not db_name:
      # Load the text configuration file
      self.config_values = {}
      home = os.environ.get('HOME')

      if os.path.exists(home + '/.mythtv/mysql.txt'):
        dbinfo = home + '/.mythtv/mysql.txt'
      elif os.path.exists('/usr/share/mythtv/mysql.txt'):
        dbinfo = '/usr/share/mythtv/mysql.txt'
      else:
        dbinfo = '/etc/mythtv/mysql.txt'

      try:
        config = open(dbinfo)
        for line in config.readlines():
          if not line.startswith('#') and len(line) > 5:
            (key, value) = line.rstrip('\n').split('=')
            self.config_values[key] = value
      except:
        if not HAVE_WARNED_OF_DEFAULTS and FLAGS.db_debugging:
          print 'Could not parse the MySQL configuration for MythTV from',
          print 'any mysql.txt in the search path. Using defaults instead.'
          HAVE_WARNED_OF_DEFAULTS = True

        self.config_values['DBName'] = 'mythconverg'
        self.config_values['DBUserName'] = 'mythtv'
        self.config_values['DBPassword'] = 'mythtv'
        self.config_values['DBHostName'] = 'localhost'

    # Fill in the blanks
    if not host:
      host = self.config_values['DBHostName']
    if not user:
      user = self.config_values['DBUserName']
    if not password:
      password = self.config_values['DBPassword']
    if not db_name:
      db_name = self.config_values['DBName']

    # Open the DB connection
    try:
      self.db_connection = MySQLdb.connect(host = host,
                                           user = user,
                                           passwd = password,
                                           db = db_name)
    except Exception, e:
      print 'Could not connect to the MySQL server: %s' % e
      sys.exit(1)

  def TableExists(self, table):
    """TableExists -- check if a table exists"""

    cursor = self.db_connection.cursor(MySQLdb.cursors.DictCursor)
    try:
      cursor.execute('describe %s;' % table)

    except MySQLdb.Error, (errno, errstr):
      if errno == 1146:
        return False
      else:
        print 'Error %d: %s' %(errno, errstr)
        sys.exit(1)

    cursor.close()
    return True

  def CheckSchema(self):
    """CheckSchema -- ensure we're running the latest schema version"""

    # Check if we even have an NetTv set of tables
    for table in ['log', 'settings', 'programs', 'subscriptions']:
      if not self.TableExists('mythnettv_%s' % table):
        if self.TableExists('mythiptv_%s' % table):
          self.Log('Renaming table %s to %s;' \
            %('mythiptv_%s' % table, 'mythnettv_%s' % table))
          self.ExecuteSql('rename table %s to %s;' \
            %('mythiptv_%s' % table, 'mythnettv_%s' % table))

        else:
          print 'Creating tables:'
          self.CreateTable(table)

    # Check the schema version
    self.version = self.GetSetting('schema')
    if int(self.version) < int(CURRENT_SCHEMA):
      print 'Updating tables'
      print 'Schema MythNetTV = %s' % CURRENT_SCHEMA
      print 'Schema Database  = %s' % self.version 
      self.UpdateTables()
    elif int(self.version) > int(CURRENT_SCHEMA):
      print 'The database schema is newer than this version of the code, '
      print 'it seems like you might need to upgrade?'
      print
      print 'Schema MythNetTV = %s' % CURRENT_SCHEMA
      print 'Schema Database  = %s' % self.version
      sys.exit(1)

    # Make sure we have a chanid
    chanid = self.GetSetting('chanid')
    if chanid == None:
      channels_row = None
      try:
        # There is none cached in the settings table
        channels_row = self.GetOneRow('select chanid from channel where '
                                      'name = "MythNetTV" or '
                                      'name = "MythIPTV";')
      except:
        print 'There was a MySQL error when trying to read the channels ',
        print 'this probably indicates an error with your MySQL installation'
        sys.exit(1)

      if channels_row:
        # There is one in the MythTV Channels table though
        chanid = self.GetSettingWithDefault('chanid', channels_row['chanid'])

      else:
        # There isn't one in the MythTV Channels table
        chanid_row = self.GetOneRow('select max(chanid) + 1 from channel')
        if chanid_row.has_key('max(chanid) + 1'):
          chanid = chanid_row['max(chanid) + 1']
        else:
          chanid = 1

        self.db_connection.query('insert into channel (chanid, callsign, '
                                 'name) values (%d, "MythNetTV", '
                                 '"MythNetTV")' % chanid)

        self.Log('Created MythNetTV channel with chanid %d' % chanid)

        # Redo the selecting to make sure it worked
        channels_row = self.GetOneRow('select chanid from channel where '
                                    'name = "MythNetTV";')
        chanid = self.GetSettingWithDefault('chanid', channels_row['chanid'])

    # Make sure that we're using the new name for the channel, and that we
    # use an @ to make it display properly in the UI
    self.db_connection.query('update channel set callsign = "MythNetTV", '
                             'name = "MythNetTV" where name = "MythIPTV";')
    self.db_connection.query('update channel set channum = "@" '
                             'where name = "MythNetTV" and channum is null;')

  def RepairMissingDates(self):
    """RepairMissingDates -- repair programs which are missing a date"""

    # At some point there was a bug which resulted in there being programs
    # in the MythNetTV TODO list which didn't have dates associated with them.
    # This doesn't have any nasty side effects, but will result in incorrect
    # ordering in the MythTV recordings interface, and downloads happening
    # out of order. We try to clean the problem up here, and report to the
    # the user if we need to.
    touched_count = 0

    # Try using parsed date
    for row in self.GetRows('select guid, parsed_date, unparsed_date from '
                            'mythnettv_programs where date is null and '
                            'parsed_date like "(%)";'):
      if row.has_key('parsed_date') and row['parsed_date'] != None:
        parsed = row['parsed_date'][1:-1].split(', ')
        parsed_ints = []
        for item in parsed:
          parsed_ints.append(int(item))
        date = datetime.datetime(*parsed_ints[0:5])
        prog = program.MythNetTvProgram(self)
        prog.Load(row['guid'])
        prog.SetDate(date)
        prog.Store()
        touched_count += 1

    # Otherwise, just set it to now and get on with our lives
    for row in self.GetRows('select guid from mythnettv_programs '
                            'where date is null;'):
      prog = program.MythNetTvProgram(self)
      prog.Load(row['guid'])
      prog.SetDate(datetime.datetime.now())
      prog.Store()
      touched_count += 1

    if touched_count > 0:
      print 'During startup, I found %d programs with invalid dates. This' \
            % touched_count
      print 'indicates a bug in MythNetTV. I think its corrected now. If'
      print 'this message keeps appearing, please email mythnettv@stillhq.com'
      print 'and us know.'
      print

  def GetSetting(self, name):
    """GetSetting -- get the current value of a setting"""

    row = self.GetOneRow('select value from mythnettv_settings where '
                         'name="%s" limit 1;' % name)
    if row == None:
      return None
    return row['value']

  def GetSettingWithDefault(self, name, default):
    """GetSettingWithDefault -- get a setting with a default value"""

    cursor = self.db_connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('select value from mythnettv_settings where '
                   'name="%s";' % name)
    if cursor.rowcount != 0:
      retval = cursor.fetchone()
      cursor.close()
      return retval['value']
    else:
      self.db_connection.query('insert into mythnettv_settings (name, value) '
                               'values("%s", "%s");' %(name, default))
      self.Log('Settings value %s defaulted to %s' %(name, default))
      return default

  def WriteSetting(self, name, value):
    """WriteSetting -- write a setting to the database"""
    self.WriteOneRow('mythnettv_settings', 'name',
                     {'name': name, 'value': value})

  def GetOneRow(self, sql):
    """GetOneRow -- get one row which matches a query"""

    try:
      cursor = self.db_connection.cursor(MySQLdb.cursors.DictCursor)
      cursor.execute(sql)
      retval = cursor.fetchone()
      cursor.close()

      if retval == None:
        if FLAGS.db_debugging:
          print 'Database: no result for %s' % sql
        return retval

      for key in retval.keys():
        if retval[key] == None:
          del retval[key]

      return retval

    except Exception, e:
      print 'Database error:'
      traceback.print_exc()
      sys.exit(1)

  def GetRows(self, sql):
    """GetRows -- return a bunch of rows as an array of dictionaries"""

    retval = []
    cursor = self.db_connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute(sql)

    for i in range(cursor.rowcount):
      row = cursor.fetchone()
      retval.append(row)

    return retval

  def GetWaitingForImport(self):
    """GetWaitingForImport -- return a list of the guids waiting for import"""

    cursor = self.db_connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('select guid from mythnettv_programs where '
                   'download_finished = "1" and imported is NULL')
    guids = []
    while True:
      program = cursor.fetchone()
      if program == None:
        break

      guids.append(program['guid'])

    return guids

  def FormatSqlValue(self, name, value):
    """FormatSqlValue -- some values get escaped for SQL use

    NOTE: This method must return strings, as some of its callers use
    string.join()
    """

    if type(value) == datetime.datetime:
      return 'STR_TO_DATE("%s", "%s")' \
             %(value.strftime('%a, %d %b %Y %H:%M:%S'),
               '''%a, %d %b %Y %H:%i:%s''')
    if name == 'date':
      return 'STR_TO_DATE("%s", "%s")' %(value, '''%a, %d %b %Y %H:%i:%s''')
    if type(value) == long or type(value) == int:
      return '%s' % value
    if value == None:
      return 'NULL'

    try:
      return '"%s"' % Normalize(value).replace('"', '""').replace("'", "''")
    except Exception, e:
      raise FormatException('Could not format string value %s = %s (%s)'
                            %(name, value, e))

  def WriteOneRow(self, table, key_col, dict):
    """WriteOneRow -- use a dictionary to write a row to the specified table"""

    cursor = self.db_connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('select %s from %s where %s = "%s"' \
                   %(key_col, table, key_col, dict[key_col]))

    if cursor.rowcount > 0:
      self.Log('Updating %s row with %s of %s' %(table, key_col,
                                                 dict[key_col]))
      vals = []
      for col in dict:
        val = '%s=%s' %(col, self.FormatSqlValue(col, dict[col]))
        vals.append(val)

      sql = 'update %s set %s where %s="%s";' %(table, ','.join(vals),
                                                key_col, dict[key_col])

    else:
      self.Log('Creating %s row with %s of %s' %(table, key_col,
                                                 dict[key_col]))
      vals = []
      for col in dict:
        vals.append(self.FormatSqlValue(col, dict[col]))

      sql = 'insert into %s (%s) values(%s);' \
             %(table, ','.join(dict.keys()), ','.join(vals))

    cursor.close()
    self.db_connection.query(sql)

  def GetNextLogSequenceNumber(self):
    """GetNextLogSequenceNumber -- ghetto lookup of the highest sequence
    number"""

    try:
      cursor = self.db_connection.cursor(MySQLdb.cursors.DictCursor)
      cursor.execute('select max(sequence) + 1 from mythnettv_log;')
      retval = cursor.fetchone()
      cursor.close()

      if retval['max(sequence) + 1'] == None:
        return 1

      return retval['max(sequence) + 1']
    except:
      return 1

  def Log(self, message):
    """Log -- write a log message to the database"""

    try:
      new_sequence = self.GetNextLogSequenceNumber()
      self.db_connection.query('insert into mythnettv_log (sequence, '
                               'timestamp, message) values(%d, NOW(), "%s");' \
                              %(new_sequence, message))

    except:
      print 'Failed to log: %s' % message

  def CleanLog(self):
    """CleanLog -- remove all but the newest xxx log messages"""

    min_sequence = self.GetNextLogSequenceNumber() - \
                   int(self.GetSettingWithDefault('loglines', '1000')) - 1
    cursor = self.db_connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('delete from mythnettv_log where sequence < %d' \
                   % min_sequence)
    if cursor.rowcount > 0:
      self.Log('Deleted %d log lines before sequence number %d' \
               %(cursor.rowcount, min_sequence))
    cursor.close()

  def CreateTable(self, tablename):
    """CreateTable -- a table has been found to be missing, create it with
    the current schema"""

    print 'Info: Creating %s table' % tablename
    if tablename == 'log':
      self.db_connection.query('create table mythnettv_log (sequence int, '
                               'timestamp datetime, message text) ENGINE = MYISAM;')
      self.db_connection.query('insert into mythnettv_log (sequence) '
                               'values(0);')

    elif tablename == 'settings':
      self.db_connection.query('create table mythnettv_settings (name text, '
                               'value text) ENGINE = MYISAM;')
      self.db_connection.query('insert into mythnettv_settings (name, value) '
                               'values("schema", "7");')

    elif tablename == 'programs':
      self.db_connection.query('create table mythnettv_programs (guid text, '
                               'url text, title text, subtitle text, '
                               'description text unicode, date datetime, '
                               'unparsed_date text, parsed_date text, '
                               'download_started int, '
                               'download_finished int, '
                               'imported int, transfered int, size int, '
                               'filename text)ENGINE = MYISAM;')

    elif tablename == 'subscriptions':
      self.db_connection.query('create table mythnettv_subscriptions ('
                               'url text, title text) ENGINE = MYISAM;')

    else:
      self.Log('Error: Don\'t know how to create %s' % tablename)
      print 'Error: Don\'t know how to create %s' % tablename
      sys.exit(1)

    self.Log('Creating %s table' % tablename)

  def UpdateTables(self):
    """UpdateTables -- handle schema upgrades"""

    if self.version == '4':
      self.Log('Upgrading schema from 4 to 5')
      self.db_connection.query('alter table mythnettv_programs '
                               'add column parsed_date text;')
      self.version = '5'

    if self.version == '5':
      # This is a deliberate noop because the new table was created during the
      # startup checks
      self.Log('Upgrading schema from 5 to 6')
      self.version = '6'

    if self.version == '6':
      # Another noop, because we're renaming tables
      self.Log('Upgrading schema from 6 to 7')
      self.version = '7'

    if self.version == '7':
      # Start tracking the MIME type of videos, this helps with bittorrent
      self.Log('Upgrading schema from 7 to 8')
      self.db_connection.query('alter table mythnettv_programs '
                               'add column mime_type text, '
                               'add column tmp_name varchar(255);')
      self.version = '8'

    if self.version == '8':
      self.Log('Upgrading schema from 8 to 10')
      self.db_connection.query('alter table mythnettv_programs '
                               'add column inactive tinyint, '
                               'add column attempts tinyint;')
      self.version = '10'

    if self.version == '10':
      self.Log('Upgrading schema from 10 to 12')
      self.db_connection.query('alter table mythnettv_subscriptions '
                               'add column inactive tinyint, '
                               'add column archive_to text;')
      self.version = '12'

    if self.version == '12':
      self.Log('Upgrading schema from 12 to 13')
      self.db_connection.query('alter table mythnettv_subscriptions '
                               'drop column archive_to;')
      self.db_connection.query('create table mythnettv_archive '
                               '(title text, path text) ENGINE = MYISAM;')
      self.version = '13'

    if self.version == '13':
      self.Log('Upgrading schema from 13 to 14')
      self.db_connection.query('alter table mythnettv_programs '
                               'add column failed tinyint;')
      self.version = '14'

    if self.version == '14':
      self.Log('Upgrading schema from 14 to 15')
      self.db_connection.query('create table mythnettv_proxies '
                               '(url text, http_proxy text) ENGINE = MYISAM;')
      self.version = '15'

    if self.version == '15':
      self.Log('Upgrading schema from 15 to 16')
      self.db_connection.query('create table mythnettv_proxy_usage '
                               '(day date, http_proxy text, bytes int) ENGINE = MYISAM;')
      self.version = '16'

    if self.version == '16':
      self.Log('Upgrading schema from 16 to 17')
      self.db_connection.query('alter table mythnettv_proxy_usage '
                               'modify column http_proxy varchar(256);')
      self.db_connection.query('alter table mythnettv_proxy_usage '
                               'add primary key(day, http_proxy);')
      self.version = '17'

    if self.version == '17':
      self.Log('Upgrading schema from 17 to 18')
      self.db_connection.query('alter table mythnettv_proxies '
                               'add column daily_budget int;')
      self.version = '18'

    if self.version == '18':
      self.Log('Upgrading schema from 18 to 19')
      self.db_connection.query('create table mythnettv_category '
                               '(title text, category varchar(64));')
      self.version = '19'

    if self.version == '19':
      self.Log('Upgrading schema from 19 to 20')
      self.db_connection.query('create table mythnettv_group '
                               '(title text, recgroup varchar(32));')
      self.version = '20'

    if self.version == '20':
      self.Log('Upgrading schema from 20 to 21')
      self.db_connection.query('alter table mythnettv_programs '
                               'add column last_attempt datetime;')
      self.version = '21'

    if self.version == '21':
      self.Log('Upgrading schema from 21 to 22')
      self.db_connection.query('alter table mythnettv_subscriptions '
                               'add column inetref text;')
      self.db_connection.query('alter table mythnettv_programs '
                               'add column inetref text;')
      self.db_connection.query('alter table mythnettv_subscriptions '
                               'add column chanid int(11);')
      self.version = '22'

    if self.version == '22':
      self.Log('Upgrading schema from 22 to 23')
      self.db_connection.query('alter table mythnettv_subscriptions '
                               'add column playgroup text;')
      self.version = '23'

    if self.version != CURRENT_SCHEMA:
      print 'Unknown schema version. This is a bug. Please report it to'
      print 'managementboy@gmail.com'
      sys.exit(1)

    self.WriteSetting('schema', self.version)

  def ExecuteSql(self, sql):
    """ ExecuteSql -- execute some SQL and return the number of rows affected
    """

    cursor = self.db_connection.cursor(MySQLdb.cursors.DictCursor)

    try:
      cursor.execute(sql)
    except Exception, e:
      print 'Database error: %s' % e
      print '  sql = %s' % sql
      raise e

    changed = cursor.rowcount
    cursor.close()

    return changed
