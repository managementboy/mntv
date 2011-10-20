#!/usr/bin/python

# Copyright (C) Elkin Fricke (elkin@elkin.de) 2011
# Released under the terms of the GNU GPL v2

import re
import sys
import tvrage.api
import utility
#import tvdb_api
import MythTV.ttvdb.tvdb_ui as tvdb_ui
import MythTV.ttvdb.tvdb_api as tvdb_api
from datetime import date
from datetime import datetime

def ExtractSeasonEpisode(seasonepisode, out=sys.stdout):
  """ExtractSeasonEpisode -- extract the season and episode number from a string and return these as integers"""
  
  # this list contains the regular expression that would find both the season and episode
  matchme = ["s(\d{2})e(\d{2})", "S(\d{2})E(\d{2})", "(\d{2})x(\d{2})", "(\d{1})x(\d{2})", "(\d{1})x(\d{1})"]
  
  # iterate through each regular expression to find the actual integer value
  for search in matchme:
    try:
      season = int(re.search(search, seasonepisode).group(1))
      episode = int(re.search(search, seasonepisode).group(2))
      return season, episode
    except:
      pass
  
  #similar problem with titles containing "xx of yy"
  matchme = ["(\d{2})of(\d{2})", "(\d{1})of(\d{2})", "(\d{1})of(\d{1})", "(\d{2})of (\d{2})", "(\d{1})of (\d{2})", "(\d{1})of (\d{1})", "(\d{2}) of (\d{2})", "(\d{1}) of (\d{2})", "(\d{1}) of (\d{1})", "(\d{2})/(\d{2})", "(\d{1})/(\d{2})", "(\d{1})/(\d{1})"]
  
  for search in matchme:
    try:
      # we need to assume that any such show is always the first season
      season = 1
      episode = int(re.search(search, seasonepisode).group(1))
      return season, episode
    except:
      pass
  
  # if we could not find anything...
  return 0
  
def ExtractDate(date, out=sys.stdout):
  """ExtractDate -- extract the year, month, day from a string and return these as integers"""
  
  # this list contains the regular expression that would find both the season and episode
  matchyearfirst = ["(\d{4}).(\d{2}).(\d{2})", "(\d{4}) (\d{2}) (\d{2})", "(\d{4})-(\d{2})-(\d{2})"]
  matchyearlast = ["(\d{2}).(\d{2}).(\d{4})", "(\d{2}) (\d{2}) (\d{4})", "(\d{2})-(\d{2})-(\d{4})"]
  
  # iterate through each regular expression to find the actual integer value
  for search in matchyearfirst:
    try:
      year = int(re.search(search, date).group(1))
      month = int(re.search(search, date).group(2))
      day = int(re.search(search, date).group(3))
      return year, month, day
    except:
      pass
  for search in matchyearlast:
    try:
      year = int(re.search(search, date).group(3))
      month = int(re.search(search, date).group(2))
      day = int(re.search(search, date).group(1))
      return year, month, day
    except:
      pass
  # if we could not find anything...
  return 0
  
def TVRageSeasonEpisode(title, season, episode, out=sys.stdout):
  """ TVRageSeasonEpisode -- Get and format subtitle and description from TVRage based on a season and episode"""
  try:
    #get the TVrage show information
    tvshow = tvrage.api.Show(title)
    #then get the TVrage Episode information
    tvrageepisode = tvshow.season(season).episode(episode)
    #return subtitle and description
    return tvrageepisode.title, utility.massageDescription(tvrageepisode.summary)
  except:
    return 0
    
def TVRageDate(title, year, month, day, out=sys.stdout):
  """ TVRageDate -- Get and format subtitle and description from TVRage based on a date"""
  try:
    #get the TVrage show information
    tvshow = tvrage.api.Show(title)
    #then get the TVrage Episode information
    seasoncount = int(tvshow.seasons)
    while (seasoncount > 0):
      season = tvshow.season(seasoncount)
      for episodes in season:
        if tvshow.season(seasoncount).episode(episodes).airdate == date(year, month, day):
          subtitle = date(year, month, day).strftime("%Y.%m.%d") + ' ' + tvshow.season(seasoncount).episode(episodes).title
          #return subtitle and description
          return subtitle, utility.massageDescription(tvshow.season(seasoncount).episode(episodes).summary), tvshow.season(seasoncount).episode(episodes).season, tvshow.season(seasoncount).episode(episodes).number
      seasoncount = seasoncount - 1
  except:
    return 0

def TTVDBSeasonEpisode(title, season, episode, out=sys.stdout):
  """ TTVDBSeasonEpisode -- Get and format subtitle and description from The TV Database based on a season and episode"""
  try:
    #get the TVrage show information
    tvshow = tvdb_api.Tvdb()
    #then get the TVrage Episode information
    tvrageepisode = tvshow[title][season][episode]
    #return subtitle and description
    try:
      description = utility.massageDescription(tvrageepisode['overview'].encode('latin-1','ignore'))
    except:
      description = utility.massageDescription(tvrageepisode['overview'])
    return tvrageepisode['episodename'], description, season, episode, tvrageepisode['seriesid']
  except:
    return 0

def TTVDBDate(title, year, month, day, out=sys.stdout):
  """ TTVDBDate -- Get and format subtitle and description from The TV Database based on a date"""

  try:
    #get the TTVDB show information
    ttvdb = tvdb_api.Tvdb()
    tvshow = ttvdb[title]
    #then get the TVrage Episode information

    for season in tvshow:
      for episode in tvshow[season]:
        try:
          airdate = datetime.strptime(tvshow[season][episode]['firstaired'], '%Y-%m-%d')
        except:
          airdate = datetime(1,1,1)
        if airdate == datetime(year, month, day):
          subtitle = datetime(year, month, day).strftime("%Y.%m.%d") + ' ' + tvshow[season][episode]['episodename']
          #return subtitle and description
          return subtitle, utility.massageDescription(tvshow[season][episode]['overview']), season, episode, tvshow[season][episode]['seriesid']
  except:
    return 0 

def TTVDBSubtitle(title, subtitle, out=sys.stdout):
  """ TTVDBDate -- Get and format subtitle and description from The TV Database based on a show subtitle"""

  try:
    #get the TTVDB show information
    ttvdb = tvdb_api.Tvdb()
    tvshow = ttvdb[title]
    for season in tvshow:
      for episode in tvshow[season]:
        if tvshow[season][episode]['episodename'] == subtitle:
          return subtitle, utility.massageDescription(tvshow[season][episode]['overview']), season, episode, tvshow[season][episode]['seriesid']
  except:
    return 0
