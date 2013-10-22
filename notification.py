#!/usr/bin/python
                                                                                                                              
# Copyright (C) Elkin Fricke (managementboy@gmail.com) 2013 Released under the terms of the GNU GPL v2
                                                                                                                              
import sys 
import os 
import subprocess 
                                                                                                                              
def notify(bcastaddr, message_text, description, extra):
  """Send a notification to frontends using mythutil
                                                                                                                              
     Args:
        description: notification description text
        extra: notification extra text
        message_text: message to send
        origin: notification origin text
  """
  print 'Sending notification to frontends\n'
  
  #os.system('/usr/bin/mythutil -v none --notification --bcastaddr=%s --message_text="%s" --description="%s" --extra="%s"' %(bcastaddr, message_text, description, extra))
  return 

def progress(bcastaddr, message_text, description, progress, progress_text, extra):
  """Send a notification to frontends using mythutil
                                                                                                                              
     Args:
        description: notification description text
        extra: notification extra text
        message_text: message to send
        origin: notification origin text
        progress:progress value (must be between 0 and 1)
        progress_text: notification progress text
  """
  print 'Sending notification to frontends\n'

  #os.system('/usr/bin/mythutil -v none --notification --bcastaddr=%s --message_text="%s" --description="%s" --progress=%s --porgess_text="%s" --extra="%s"' %(bcastaddr, message_text, description, progress, progress_text, extra)) 
  return
  


