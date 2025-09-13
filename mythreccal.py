#! /usr/bin/python3
# -*- coding: utf-8 -*-

import os, re, sys, select, requests, subprocess, itertools, time, pickle, logging, csv
from datetime import date, datetime, timedelta, timezone

#Get recording information (single calendar):
def get_ical_recordings(calendar):
    try:
        ical_ics = requests.get(calendar).text
    except requests.exceptions.RequestException as e:
        logging.info(e)
        sys.exit(1)
    d_time_now = datetime.utcnow() # UTC
    recordings = []
    for i in range(len(ical_ics)-13):
        if ical_ics[i : i + 13] == 'END:VCALENDAR':
            break
        if ical_ics[i : i + 8] == 'DTSTART:':
            day_str = ical_ics[i+8 : i+16]
            time_str = ical_ics[i+17 : i+21]
            s_time = datetime.strptime(day_str+time_str, '%Y%m%d%H%M') # UTC start time
            day_str = s_time.strftime("%Y%m%d")
            time_str = s_time.strftime("%H%M")
            if d_time_now > s_time:
                continue
            e_time = False
            for j in range(len(ical_ics)-i-6):
                if ical_ics[i+j : i+j+6] == 'DTEND:':
                    e_day_str = ical_ics[i+j+6 : i+j+14]
                    e_time_str = ical_ics[i+j+15 : i+j+19]
                    e_time = datetime.strptime(e_day_str+e_time_str, '%Y%m%d%H%M') # UTC end time
                    e_day_str = e_time.strftime("%Y%m%d")
                    e_time_str = e_time.strftime("%H%M")
                    break
            if not e_time:
                continue
            chan_position = False
            for j in range(len(ical_ics)-i-12):
                if ical_ics[i+j : i+j+12] == 'DESCRIPTION:':
                    for k in range(len(ical_ics)-i-j-3):
                        if ical_ics[i+j+k : i+j+k+1] == '"':
                            title = ical_ics[i+j+12 : i+j+k-1]
                            for l in range(len(ical_ics)-i-j-k-3):
                                if ical_ics[i+j+k+l+1 : i+j+k+l+2] == '"':
                                    subtitle = ical_ics[i+j+k+1 : i+j+k+l+1]
                                    subtitle = subtitle.replace('\n', '').replace('\r', '')
                                    chan_position = i+j+k+l+3
                                    break
                        else:
                            subtitle = ''
                            chan_position = i+j+k+3
                            break
                else:
                    if ical_ics[i+j : i+j+10] == 'END:VEVENT':
                        break
            if not chan_position:
                continue
            for j in range(len(ical_ics)-chan_position-1):
                if ical_ics[chan_position+j : chan_position+j+1] == ' ':
                    chan = ical_ics[chan_position : chan_position+j] #channel first part
                    for k in range(len(ical_ics)-chan_position-j-3):
                        if ical_ics[chan_position+j+k+1 : chan_position+j+k+2].isdigit():
                            for l in range(len(ical_ics)-chan_position-j-k-3):
                                if not ical_ics[chan_position+j+k+l+1 : chan_position+j+k+l+2].isdigit():
                                    chan = chan + ' ' + ical_ics[chan_position+j+k+1 : chan_position+j+k+l+1]
                                    break
                            break
                        elif ical_ics[chan_position+j+k+1 : chan_position+j+k+2] == ':':
                            break
                    break
                elif ical_ics[chan_position+j : chan_position+j+1] == ':':
                    break
            recording = []
            recording.append(day_str)
            recording.append(time_str)
            recording.append(e_day_str)
            recording.append(e_time_str)
            recording.append(title)
            recording.append(subtitle)
            recording.append(chan)
            recording.append('') #place holder for xmltvid
            recording.append('') #place holder for chanid
            recordings.append(recording)
    return recordings
    
#Get recording information (all calendars):
def get_icals_recordings(calendars):
    if len(calendars) == 0:
        logging.info(' Aborting (no calendar url provided)')
        sys.exit(0)
    recordings = []
    for i in range(len(calendars)):
        recordings = recordings + get_ical_recordings(calendars[i])
    recordings.sort()
    recordings = list(recordings for recordings,_ in itertools.groupby(recordings)) #Remove duplicates
    if recordings == []:
        recordings = [[]]
    return recordings

def removeNonAscii(s):
    s = s.replace("&", "and")
    return "".join([x if ord(x) < 128 else '_' for x in s])

class mythAPI:
    def __init__(self, host, port):
        self.baseAddr = 'http://{}:{}/'.format(host, port)
        self.headers = {'Accept':'application/json'}
    def GetUpcomingRec(self, **params):
        UpcomingRec = requests.get('{}Dvr/GetUpcomingList'.format(self.baseAddr), params = params, headers = self.headers)
        if UpcomingRec:
            return UpcomingRec.json()
    def GetChannelInfoList(self, **params):
        cInfo = requests.get('{}Channel/GetChannelInfoList'.format(self.baseAddr), params = params, headers = self.headers)
        if cInfo:
            return cInfo.json()
    def GetRecordSchedule(self, **params):
        recSchedule = requests.get('{}Dvr/GetRecordSchedule'.format(self.baseAddr), params = params, headers = self.headers)
        if recSchedule:
            return recSchedule.json()
    def AddRecordSchedule(self, params):
        return requests.post('{}Dvr/AddRecordSchedule'.format(self.baseAddr), params = params, headers = self.headers).text

def isbadipv4(s):
    pieces = s.split('.')
    if len(pieces) != 4: return True
    try: return not all(0<=int(p)<256 for p in pieces)
    except ValueError: return True

if __name__ == '__main__':
    homepath = os.path.expanduser('~')
    if os.path.isfile(homepath+'/.mythreccal/mythreccal0.log'):
        os.rename(homepath+'/.mythreccal/mythreccal0.log',homepath+'/.mythreccal/mythreccal1.log')
    if not os.path.isdir(homepath + '/.mythreccal'):
        os.mkdir(homepath + '/.mythreccal')
    try:
        logging.basicConfig(format='%(levelname)s:%(message)s', filename=homepath+'/.mythreccal/mythreccal0.log', filemode='w', level=logging.INFO)
    except IOError:
        logging.basicConfig(format='%(levelname)s:%(message)s', filename='/tmp/mythreccal0.log', filemode='w', level=logging.INFO)
    logging.info(" " + str(datetime.now()) + " Starting mythreccal.py")
    if not os.path.isfile(homepath + '/.mythreccal/mythreccal.pickle'):
        if homepath[0:6] == '/home/':
            home_folders = os.listdir('/home/')
            for i in range(len(home_folders)):
                if os.path.isfile('/home/' + home_folders[i] + '/.mythreccal/mythreccal.pickle') and not home_folders[i] in homepath:
                    try:
                        os.symlink('/home/' + home_folders[i] + '/.mythreccal/mythreccal.pickle',homepath + '/.mythreccal/mythreccal.pickle')
                    except OSError:
                        os.unlink(homepath + '/.mythreccal/mythreccal.pickle')
                        os.symlink('/home/' + home_folders[i] + '/.mythreccal/mythreccal.pickle',homepath + '/.mythreccal/mythreccal.pickle')
    if os.path.isfile(homepath + '/.mythreccal/mythreccal.pickle'):
        with open(homepath + '/.mythreccal/mythreccal.pickle', 'rb') as f:
            settings = pickle.load(f)
        mythlanip = settings[0]
        mythport = settings[1]
        mythsourceid = settings[2]
        icalurls = settings[3]
    else:
        redosettings = True
    while True:
        if os.path.isfile(homepath + '/.mythreccal/mythreccal.pickle'):
            print('Continuing in 10 seconds')
            print('s Enter:    Change settings')
            print('x Enter:    Exit')
            print('Enter:      Continue')
            i, o, e = select.select( [sys.stdin], [], [], 10 )
            if (i):
                selection = sys.stdin.readline().strip()
                if selection == 's':
                    redosettings = True
                elif selection == 'x':
                    sys.exit(0)
                else:
                    break
            else:
                break
        if redosettings:
            if os.path.isfile(homepath + '/.mythreccal/mythreccal.pickle'):
                print('Current Settings:')
                print('MythTV backend server IP address: ' + settings[0])
                print('MythTV backend web server port: ' + settings[1])
                print('MythTV channel source id: ' + settings[2])
                print('iCal address(es):')
                for i in range(len(settings[3])):
                    print(settings[3][i])
            print('Enter q to quit without saving settings')
            mythlanip = input('Enter MythTV backend server IP address (example: 192.168.1.50) --> ')
            if mythlanip == 'q':
                sys.exit(0)
            if isbadipv4(mythlanip):
                print('Aborting (invalid MythTV backend server IP address entered)')
                sys.exit(0)
            mythport = input('Enter MythTV backend web server port (default: 6544) --> ')
            if mythport == 'q':
                sys.exit(0)
            if len(mythport) == 0:
                mythport = '6544'
            elif not mythport.isdigit():
                print('Aborting (invalid MythTV backend web server port number entered)')
                sys.exit(0)
            mythsourceid = input('Enter MythTV channel source id (default: 1) --> ')
            if mythsourceid == 'q':
                sys.exit(0)
            if len(mythsourceid) == 0:
                mythsourceid = '1'
            elif not mythsourceid.isdigit():
                print('Aborting (invalid MythTV channel source id number entered)')
                sys.exit(0)
            icalurls = [input('Enter single iCal address --> ')]
            if icalurls == 'q':
                sys.exit(0)
            if len(icalurls) == 0:
                print('Aborting (iCal address is required)')
                sys.exit(0)
            while True:
                icalurl = input('Enter another iCal address or press enter if done --> ')
                if icalurl == 'q':
                    sys.exit(0)
                if len(icalurl) == 0:
                    break
                else:
                    icalurls.append(icalurl)
            settings = [mythlanip,mythport,mythsourceid,icalurls]
            with open(homepath + '/.mythreccal/mythreccal.pickle', 'wb') as f:
                pickle.dump(settings, f, pickle.HIGHEST_PROTOCOL)
    logging.info(' Opening connection to calendar')
    recordings = get_icals_recordings(icalurls)
    for i in range(len(recordings)):
        if recordings[i] != []:
            break
        if i == len(recordings)-1:
            logging.info("No future recording found on calendar(s)")
            sys.exit(0)
    mapi = mythAPI(mythlanip, mythport)
    upcomingList = []
    #Build list of upcoming myth recordings and mark new recordings to skip which overlap with upcoming
    upcoming = mapi.GetUpcomingRec()['ProgramList']['Programs']
    for i in range(len(upcoming)):
        upcomStartTm = datetime.strptime(upcoming[i]['StartTime'].replace('Z', ''), '%Y-%m-%dT%H:%M:%S')
        xid = upcoming[i]['Channel']['XMLTVID']
        upcomEndTm = datetime.strptime(upcoming[i]['EndTime'].replace('Z', ''), '%Y-%m-%dT%H:%M:%S')
        upcomingList.append([xid, upcomStartTm, upcomEndTm])
    chaninfo = mapi.GetChannelInfoList(SourceID=mythsourceid, Details='true')
    chaninfo = chaninfo['ChannelInfoList']['ChannelInfos']
    for i in range(len(recordings)):
        start = datetime.strptime(recordings[i][0] + recordings[i][1], '%Y%m%d%H%M')
        stop = datetime.strptime(recordings[i][2] + recordings[i][3], '%Y%m%d%H%M')
        chan = recordings[i][6][recordings[i][6].find(' ')+1:]
        for j in range(len(chaninfo)):
            if chan == chaninfo[j]['ChanNum']:
                overlapFound = False
                for k in range(len(upcomingList)):
                    if start <= upcomingList[k][1] and stop <= upcomingList[k][2] and stop > upcomingList[k][1]:
                        if upcomingList[k][0] == chaninfo[j]['XMLTVID']:
                            overlapFound = True
                            break
                    if start >= upcomingList[k][1] and stop >= upcomingList[k][2] and start < upcomingList[k][2]:
                        if upcomingList[k][0] == chaninfo[j]['XMLTVID']:
                            overlapFound = True
                            break
                if overlapFound:
                    recordings[i][7] = '_skip_'
                    logging.info(recordings[i][4] + " overlaps with previously set recording - skipping")
                    print(recordings[i][4] + " overlaps with previously set recording - skipping")
                    break
                else:
                    recordings[i][7] = chaninfo[j]['XMLTVID']
                    recordings[i][8] = chaninfo[j]['ChanId']
                    break
            if j == len(chaninfo)-1:
                recordings[i][7] = '_skip_'
                logging.info("No matching channel number found for " + chan + " - skipping")
                print("No matching channel number found for " + chan + " - skipping")
    #Write xml file
    if os.environ.get('USERNAME'):
        tmp_xml_file = '/tmp/xmltvmrc_' + os.environ.get('USERNAME') + '.xml'
    else:
        tmp_xml_file = '/tmp/xmltvmrc_m.xml'
    if ' ' in tmp_xml_file:
        tmp_xml_file = '/tmp/xmltvmrc.xml'
    with open(tmp_xml_file, 'w') as xml_file:
        xml_file.write('<?xml version="1.0" encoding="ISO-8859-1"?>'+'\n')
        xml_file.write('<!DOCTYPE tv SYSTEM "xmltv.dtd">'+'\n')
        xml_file.write('\n')
        xml_file.write('<tv source-info-name="user_calendar" generator-info-name="mythreccal.py">'+'\n')
        start = False #Used to check if at least one new recording
        for i in range(len(recordings)):
            if recordings[i][7] != '_skip_':
                logging.info(" New recording: " + recordings[i][4])
                print(" New recording: " + recordings[i][4])
                start = recordings[i][0] + recordings[i][1] + '00 +0000' #String UTC
                stop = recordings[i][2] + recordings[i][3]  + '00 +0000' #String UTC
                ch_id = recordings[i][7]
                xml_file.write('  <programme start="'+start+'" stop="'+stop+'" channel="'+ch_id+'">'+'\n')
                xml_file.write('    <title lang="en">'+recordings[i][4]+'</title>'+'\n')
                xml_file.write('    <sub-title lang="en">'+recordings[i][5]+'</sub-title>'+'\n')
                xml_file.write('  </programme>'+'\n')
        xml_file.write('</tv>')
    if not start:
        sys.exit(0)
    #Run mythfilldatabase:
    print('Running mythfilldatabase')
    subprocess.call('mythfilldatabase --quiet --refresh 1 --file --sourceid ' + mythsourceid + ' --xmlfile ' + tmp_xml_file, shell=True)
    #Set recording(s):
    for i in range(len(recordings)):
        if recordings[i][7] != '_skip_':
            time = recordings[i][0] + recordings[i][1] #String UTC
            time = time[0:4]+'-'+time[4:6]+'-'+time[6:8]+'T'+time[8:10]+':'+time[10:12]+':00'
            mythchid = recordings[i][8]
            recRule = mapi.GetRecordSchedule(ChanId=mythchid, StartTime=time)
            recRule = recRule['RecRule']
            recRule['Type'] = 'Single Record'
            recRule['Station'] = recRule['CallSign']
            recRule['MakeOverride'] = 'true'
            mapi.AddRecordSchedule(recRule)
