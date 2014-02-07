#!/usr/bin/env python
from smtplib import SMTP
from smtplib import SMTPException
from email.mime.text import MIMEText
import sys
import gmailpassword
 
#Global varialbes
EMAIL_SUBJECT = "MythNetTV has something to tell you"
EMAIL_RECEIVERS = ['managementboy@gmail.com']
EMAIL_SENDER  =  'managementboy@gmail.com'
GMAIL_SMTP = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587
TEXT_SUBTYPE = "plain"
 
def listToStr(lst):
    """This method makes comma separated list item string"""
    return ','.join(lst)
 
def send_email(content):
    """This method sends an email"""    
     
    #Create the message
    msg = MIMEText(content, TEXT_SUBTYPE)
    msg["Subject"] = EMAIL_SUBJECT
    msg["From"] = EMAIL_SENDER
    msg["To"] = listToStr(EMAIL_RECEIVERS)
     
    try:
      smtpObj = SMTP(GMAIL_SMTP, GMAIL_SMTP_PORT)
      #Identify yourself to GMAIL ESMTP server.
      smtpObj.ehlo()
      #Put SMTP connection in TLS mode and call ehlo again.
      smtpObj.starttls()
      smtpObj.ehlo()
      #Login to service
      smtpObj.login(user=EMAIL_SENDER, password=gmailpassword.gmailpassword)
      #Send email
      smtpObj.sendmail(EMAIL_SENDER, EMAIL_RECEIVERS, msg.as_string())
      #close connection and session.
      smtpObj.quit();
    except SMTPException as error:
      print "Error: unable to send email :  {err}".format(err=error)
