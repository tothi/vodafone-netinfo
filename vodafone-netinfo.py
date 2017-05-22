#!/usr/bin/python3
#
# vodafone-netinfo: vodafone online ügyintézés lekérdezések (pl. netinfo)
#

#from urllib.parse import urlparse, parse_qs
import requests, re, getpass, argparse, logging, io, datetime
from bs4 import BeautifulSoup
from time import sleep

from flask import Flask
from flask import Markup
from flask import render_template

import threading

class ChartAppThread(object):
    app = Flask(__name__)
    @app.route("/")
    def chart():
        global w
        return render_template('chart.html', values=w.xy, renew=w.renew)

    def __init__(self, host, port):
        self.thread = threading.Thread(target=self.run, args=(host, port))
        self.thread.deamon = True

    def run(self, host, port):
        if args.weblogfile:
            log = logging.getLogger('werkzeug')
            log.setLevel(logging.ERROR)
            handler = logging.FileHandler(args.weblogfile[0])
            handler.setLevel(logging.ERROR)
            log.addHandler(handler)
        self.app.run(host=host, port=port)

class ChartAppData(object):
    def getxylog(self, logline):
        t = logline.split(' ')
        if t[2][0] == '(':
            try:
                x0 = t[4][:-1]
                x1 = t[5][:-2]
            except:
                x0 = t[4][:-2]
                x1 = None
            return ((t[0] + ' ' + t[1].split(',')[0]),
                    t[2][1:][:-1], t[3][:-1], x0, x1)
        else:
            return None

    def calcrenew(self, now, days):
        df = "%Y-%m-%d"
        date_now = datetime.datetime.strptime(now.split(' ')[0], df)
        date_end = date_now + datetime.timedelta(days=(days+1))
        date_end = date_end.strftime(df)
        m = date_end.split("-")
        if int(m[1]) == 1:
            date_start = str(int(m[0])-1) + "-12-" + m[2]
        else:
            date_start = m[0] + "-" + str(int(m[1])-1) + "-" + m[2]
        self.renew = [date_start, date_end]
        return self.renew
        
    def readlog(self, logfile):
        self.xy = []
        with open(logfile, 'r') as f:
            for logline in f:
                t = self.getxylog(logline)
                if t:
                    self.xy.append(t)
            f.close()
        if self.xy[-1][4]:
            self.calcrenew(self.xy[-1][0], int(self.xy[-1][4]))

    def parselogline(self, logline):
        t = self.getxylog(logline)
        if t:
            self.xy.append(t)
            self.calcrenew(t[0], int(t[4]))

class NetinfoInterface(requests.Session):
    URL_BASE = "https://m.vodafone.hu"
    URL_LOGIN = 'https://sso.vodafone.hu/oam/server/authentication'
    URL_PROFILE = URL_BASE + "/online_ugyfelszolgalat/-/szolgaltatas/Profilom"
    URL_NETINFO = URL_BASE + "/netinfo"
    URL_LOGOUT = 'https://sso.vodafone.hu/oam/server/logout'

    def login(self, number, passwd):
        self.headers.update({'User-Agent': 'Mozilla/5.0'})
        self.post(self.URL_LOGIN,
                  data = {'operation': 'authentication',
                          'successurl': 'https://www.vodafone.hu/sikeres-bejelentkezes?gotoURL=http%3A%2F%2Fwww.vodafone.hu%2Fweb%2Fnetinfo',
                          'errorurl': 'https://www.vodafone.hu/belepes?p_p_id=LoginPortlet_WAR_VfhLoginPortlet&p_p_lifecycle=0&p_p_mode=view&p_p_col_id=column-1&p_p_col_count=1&_LoginPortlet_WAR_VfhLoginPortlet_render=loginError',
                          'resourceurl': 'https://www.vodafone.hu/belepes',
                          'type': 'legacy',
                          'username': number,
                          'password': passwd})
        
    def logout(self):
        self.get(self.URL_LOGOUT)
        
    inet_remain, inet_total, days, balance = None, None, None, None

    def profil(self):
        soup = BeautifulSoup(self.get(self.URL_PROFILE).text)
        #print(soup.prettify())
        t = soup.div.find_all(class_="redRow")
        self.balance = int(re.sub('[^0-9]', '', t[0]("b")[0].string))
        self.inet_remain = int(re.sub('[^0-9]', '', t[1]("b")[0].string))
        t = soup.div.find_all(class_="botRow")
        self.inet_total = int(t[0].string.split(' ')[1])
        return (self.inet_remain, self.inet_total, self.balance, self.days)

    def netinfo(self):
        soup = BeautifulSoup(self.get(self.URL_NETINFO).text)
        #print(soup.prettify())
        t = soup.find("div", class_="netinfoDetail")
        self.inet_remain = int(t['data-used'])
        self.inet_total = int(t['data-max'])
        self.days = int(t.find("p", class_="font-red").text.split(' ')[2])
        return (self.inet_remain, self.inet_total, self.balance, self.days)
        

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--interactive", help="belépési adatok megkérdezése", action="store_true")
    parser.add_argument("-c", "--credfile", nargs=1, help="belépési adatok betöltése fájlból (telszám:jelszó formátum, NEM BIZTONSÁGOS!)")
    parser.add_argument("-d", "--delay", nargs=1, help="szolgáltatás mód: lekérdezés folyamatosan, DELAY másodpercenként")
    parser.add_argument("-l", "--netlogfile", nargs=1, help="netinfo naplófájl")
    parser.add_argument("-w", "--weblogfile", nargs=1, help="webapp naplófájl")
    parser.add_argument("-p", "--port", nargs=1, help="grafikon webapp a megadott porton")
    args = parser.parse_args()

    if args.interactive:
        number = getpass.getpass("telefonszám: ")
        passwd = getpass.getpass("jelszó: ")
    elif args.credfile:
        with open(args.credfile[0], 'r') as f:
            (number, passwd) = f.read().split(':')
            f.close()
        #print("[+] hitelesítési adatok beolvasva (telefonszám: %s)" % number)
        print("[+] hitelesítési adatok beolvasva")
    else:
        print("[-] nincs autentikációs adat megadva!")
        raise SystemExit

    if args.port:
        if not args.netlogfile:
            print("[-] naplófájl megadása szükséges a grafikon rajzoláshoz")
            raise SystemExit
        else:
            print("[*] webapp indítása...", end="", flush=True)
            w = ChartAppData()
            w.readlog(args.netlogfile[0])
            wt = ChartAppThread('0.0.0.0', int(args.port[0]))
            wt.thread.start()
            print("kész.")

    if args.netlogfile:
        logger = logging.getLogger('vodefone.netlog')
        logger.setLevel(logging.INFO)
        logformatter = logging.Formatter('%(asctime)s %(message)s')
        fh = logging.FileHandler(args.netlogfile[0])
        fh.setLevel(logging.INFO)
        fh.setFormatter(logformatter)
        logger_io = io.StringIO()
        ch = logging.StreamHandler(stream=logger_io)
        ch.setLevel(logging.INFO)
        ch.setFormatter(logformatter)
        logger.addHandler(fh)
        logger.addHandler(ch)
        print("[*] naplózás a '%s' fájlba" % args.netlogfile[0])

    newInterface = True

    run = True
    while(run):
        print("[*] belépés a Vodafone Online Ügyintézés felületére...", end="", flush=True)
        if newInterface:
            v = NetinfoInterface()
            print("[*] új munkamenet létrehozva")
            newInterface = False
        v.login(number, passwd)
        print("kész.")

        print("[+] netinfo adatok lekérdezése: ", end="", flush=True)

        try:
            v.profil()
            netinfo = v.netinfo()
        except:
            netinfo = 'HIBA'
        print(netinfo)
        if args.netlogfile:
            logger.info(netinfo)
            if args.port:
                w.parselogline(logger_io.getvalue())
            logger_io.truncate(0)
            logger_io.seek(0)

        print("[*] kilépés...", end="", flush=True)
        try:
            v.logout()
            print("kész.")
        except:
            print("kommunikációs hiba. ;(")
            del v
            newInterface = True
            print("[+] új munkamenet...")

        if args.delay:
            print("[*] várakozás %d másodpercig..." % int(args.delay[0]), end="", flush=True)
            sleep(int(args.delay[0]))
            print("kész.")
        else:
            run = False
            
    del v
