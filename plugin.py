"""
Napkollektor Vezerlo python plugin for Domoticz
Author: szelessav,
Version: 1.1.0 (september 01, 2026) - see history.txt for versions history
"""
"""
<plugin key="NkV" name="Napkollektor vezérlő / Solar collector controller" author="szelessav" version="1.0.0">
	<description>
		<h2>Napkollektor Vezérlő </h2><br/>
		Könnyen megvalósítható a Domoticzban egy napkollektor vezérlő ami tartály és a kollektor hőmérők hőfok különbségére alapul<br/>
		It is easy to implement a solar collector controller in Domoticz that is based on the temperature difference between the tank and collector thermometers.
	<br/>
	<br/>
		A hőfok differencia értékkel szabályozható a keringtetés beindítása a kollektor és a tartály között.<br/>
		The temperature difference value can be used to control the start of circulation between the collector and the tank.
	<br/>
	<br/>
		Beállítható a nappal és a fűtőpatronnal elérhető maximális tartály hőmérséklet.<br/>
		The maximum tank temperature achievable during the day and with the heating cartridge can be set.
	<br/>
	<br/>
		Ha van fűtőpatron a beállított fagyhatár alá nem engedi hűlni a tartályt<br/>
		If there is a heating cartridge, it does not allow the tank to cool below the set frost limit.

	<br/>
	<br/>
		<h3>Beállítás és konfigurálás / Setup and configuration</h3>
		Állítsd be a tartály maximális hőmérsékletét és a minimális hőfok különbséget aminél elindul a keringtető szivattyú.<br/>
		Set the maximum tank temperature and the minimum temperature difference at which the circulation pump starts.
	<br/>
	<br/>
	<strong><a href="#/Custom/NKV_Napkollektor_Vezerlo">HTML setup!</a></strong> (Csak már létező modulhoz!/Only for existing modules!)
	<br/>
	<br/>
	</description>
	<params>
		<param field="Address" label="Domoticz IP Address" width="200px" required="true" default="127.0.0.1"/>
		<param field="Port" label="Port" width="40px" required="true" default="8080"/>
		<param field="Username" label="Username" width="200px" required="false" default=""/>
		<param field="Password" label="Password" width="200px" required="false" default=""/>
		<param field="Mode1" label="Kollektor hőmérséklet szenzor / Collector temperature sensor (csv list of idx)" width="100px" required="false" default=""/>
		<param field="Mode2" label="Tartály hőmérséklet szenzor / Tank temperature sensor (csv list of idx)" width="100px" required="false" default=""/>
		<param field="Mode3" label="Keringtető szivattyú / Circulating pump (csv list of idx)" width="100px" required="false" default=""/>
		<param field="Mode4" label="Fűtőbetét kapcsoló / Heater switch (csv list of idx)" width="100px" required="false" default=""/>
		<param field="Mode5" label="Frissítés ciklus perc / Update cycle minutes" width="100px" required="false" default="5"/>
		<param field="Mode6" label="Logging Level" width="200px">
			<options>
				<option label="Normal" value="Normal"  default="true"/>
				<option label="Verbose" value="Verbose"/>
				<option label="Debug - Python Only" value="2"/>
				<option label="Debug - Basic" value="62"/>
				<option label="Debug - Basic+Messages" value="126"/>
				<option label="Debug - Connections Only" value="16"/>
				<option label="Debug - Connections+Queue" value="144"/>
				<option label="Debug - All" value="-1"/>
			</options>
		</param>
	</params>
</plugin>
"""
import Domoticz
import json
from urllib import parse, request
from datetime import datetime, timedelta
import time
import math
import base64
import itertools
import re
import os
import heapq

class deviceparam:

	def __init__(self, unit, nvalue, svalue):
		self.unit = unit
		self.nvalue = nvalue
		self.svalue = svalue

class switchparam:

	def __init__(self, idx, command):
		self.idx = idx
		self.command = command

class TranslationLoader:

	def __init__(self, language="en"):
		self.translations = self.load_translations(language)
		if not self.translations:
			Domoticz.Debug("An error occurred while loading the translations!")
			self.translations = self.load_translations("en") 

	def load_translations(self, language):
		file_path = os.path.join(Parameters["HomeFolder"], f'nkv_translate_{language}.json')
		try:
			with open(file_path, 'r', encoding='utf-8') as file:
				return json.load(file)
		except (FileNotFoundError, json.JSONDecodeError) as e:
			Domoticz.Debug(f"Error loading the file '{file_path}': {e}")
			return {} 

	def t(self, text):
		return self.translations.get(text, text)  # If there is no translation, it returns with the original text

class BasePlugin:

	def __init__(self):

		self.debug = True
		self.ActiveSensors = {}
		self.KollektorSensor = []
		self.TartalySensor = []
		self.Keringteto = []
		self.Futopatron = []
		self.TartalyAktual = []
		self.KollektorAktual = []
		self.NapMax = []
		self.PatronMax = []
		self.KapcsolasiDif = []
		self.FagyHatar = []
		self.Frissitesiciklus = []
		self.TargetTemp = 20.0
		self.KollektorSensorTemp = 20.0
		self.TartalySensorTemp = 20.0
		self.loglevel = None
		self.statussupported = True
		self.intemperror = False
		self.switchcreated = []
		self.statuscreated = []
		self.nextupdate = datetime.now()
		self.location = []
		return


	def onStart(self):

		self.location = Settings["Location"].split(";")
		
		tl = TranslationLoader(Parameters["Language"])

		# állítsa be a megfelelő naplózási szintet
		try:
			debuglevel = int(Parameters["Mode6"])
		except ValueError:
			debuglevel = 0
			self.loglevel = Parameters["Mode6"]
		if debuglevel != 0:
			self.debug = True
			Domoticz.Debugging(debuglevel)
			DumpConfigToLog()
			self.loglevel = "Verbose"
		else:
			self.debug = False
			Domoticz.Debugging(0)

		# ellenőrizze, hogy a gazdagép domoticz verziója támogatja-e a Domoticz.Status() python keretfüggvényt
		try:
			Domoticz.Status("This version of domoticz allows status logging by the plugin (in verbose mode)")
		except Exception:
			self.statussupported = False

		devicecreated = []
		if 1 not in Devices:
			Options = {"LevelActions": "||",
				"LevelNames":  tl.t("Off|Sun|+ Heating cartridge"),
				"LevelOffHidden": "false",
				"SelectorStyle": "0"}
			Domoticz.Device(Name=tl.t("Solar collector control"), Unit=1, TypeName="Selector Switch", Switchtype=18, Image=15,
				Options=Options, Used=1).Create()
			devicecreated.append(deviceparam(1, 0, "0"))
			self.addfavorite(Devices[1].ID)
		if 2 not in Devices:
			Domoticz.Device(Name=tl.t("Solar collector tank temperature"), Unit=2, Type=242, Subtype=1, Used=1).Create()
			devicecreated.append(deviceparam(2, 0, "75"))
		if 3 not in Devices:
			Domoticz.Device(Name=tl.t("Collector tank frost limit temperature"), Unit=3, Type=242, Subtype=1, Used=1).Create()
			devicecreated.append(deviceparam(3 ,0, "5"))
		if 4 not in Devices:
			Domoticz.Device(Name=tl.t("Switching differential"), Unit=4, Type=242, Subtype=1, Used=1).Create()
			devicecreated.append(deviceparam(4 ,0, "2"))
		if 5 not in Devices:
			Domoticz.Device(Name=tl.t("Tank temperature with heating cartridge"), Unit=5, Type=242, Subtype=1, Used=1).Create()
			devicecreated.append(deviceparam(5 ,0, "50"))
			self.addSchedule(Devices[5].ID)
		if 6 not in Devices:
			Domoticz.Device(Name= tl.t("Collector temperature"), Unit=6, Type=242, Subtype=1, Used=0).Create()
			devicecreated.append(deviceparam(6, 0, "20.0"))
		if 7 not in Devices:
			Domoticz.Device(Name= tl.t("Tank temperature"), Unit=7, Type=242, Subtype=1, Used=0).Create()
			devicecreated.append(deviceparam(7, 0, "20.0"))
		if 8 not in Devices:
			Domoticz.Device(Name="Circulating pump", Unit=8, Type=244, Subtype=73, Switchtype=0, Used=0).Create()
			devicecreated.append(deviceparam(8, 0, "Off"))
		if 9 not in Devices:
			Domoticz.Device(Name="Heater switch", Unit=9, Type=244, Subtype=73, Switchtype=0, Used=0).Create()
			devicecreated.append(deviceparam(9, 0, "Off"))
		if 10 not in Devices:
			Domoticz.Device(Name=tl.t("Heating element hysteresis"), Unit=10, Type=242, Subtype=1, Used=1).Create()
			devicecreated.append(deviceparam(10 ,0, "2"))

		# ha bármilyen eszközt hoztak létre az onStart()-ban, itt az ideje frissíteni az alapértelmezett beállításait
		for device in devicecreated:
			Devices[device.unit].Update(nValue=device.nvalue, sValue=device.svalue)

		# listát készít az érzékelőkről és kapcsolókról
		self.KollektorSensor = parseCSV(Parameters["Mode1"])
		self.TartalySensor = parseCSV(Parameters["Mode2"])
		self.Keringteto = parseCSV(Parameters["Mode3"])
		self.Futopatron = parseCSV(Parameters["Mode4"])
		self.Frissitesiciklus = int(Parameters["Mode5"])

		#  hőmérséklet-érzékelő állapotának felépítése
		for sensor in itertools.chain(self.KollektorSensor, self.TartalySensor):
			self.ActiveSensors[sensor] = True

		# ha mód = ki, akkor minden esetben győződjön meg arról, hogy minden ki van kapcsolva
		if Devices[1].sValue == "0":
			self.switchKeringteto(False)
			self.switchFutopatron(False)


	def onStop(self):
		Domoticz.Debugging(0)


	def onCommand(self, Unit, Command, Level, Color):

		Domoticz.Debug("onCommand called for Unit {}: Command '{}', Level: {}".format(Unit, Command, Level))

		nvalue = 1 if Level > 0 else 0
		svalue = str(Level)

		Devices[Unit].Update(nValue=nvalue, sValue=svalue)

		if Unit in (1, 2, 3, 4): # újrainditás, ha megváltozik a vezérlésimód vagy alapjel
			self.nextupdate = datetime.now()
			self.onHeartbeat()


	def onHeartbeat(self):

		self.now = datetime.now()

		if self.nextupdate <= self.now:
			self.nextupdate = self.now + timedelta(minutes=self.Frissitesiciklus)

			self.switchcreated.clear()
			self.statuscreated.clear()

			self.readTemps()

			if Devices[1].sValue == "0":  # Rendszer kikapcsolva
				Domoticz.Debug("vezerlo kikapcsolva")
				Domoticz.Debug("keringteto ki")
				Domoticz.Debug("futopatron ki")
				self.switchKeringteto(False)
				self.switchFutopatron(False)


			elif Devices[1].sValue == "10" and Devices[1].TimedOut == False :  # Nap fűtés mód
				Domoticz.Debug("napmod")
				self.TargetTemp = self.TartalyAktual + self.KapcsolasiDif
				
				if self.TargetTemp < self.KollektorAktual :
					Domoticz.Debug("tartaly + dif kisseb mint a kollektor akt")
					if self.TartalyAktual < self.NapMax :
						Domoticz.Debug("A tartaly hidegebb mint a max")
						Domoticz.Debug("keringteto be")
						self.switchKeringteto(True)
					else:
						Domoticz.Debug("A tartaly melegeb mint a max, keringteto ki")
						Domoticz.Debug("keringteto ki")
						self.switchKeringteto(False)

				else:
					Domoticz.Debug("keringteto ki")
					self.switchKeringteto(False)
					Domoticz.Debug("tartaly + dif nagyobb mint a kollektor akt, keringteto ki")

				if self.FagyHatar > self.TartalyAktual :
					Domoticz.Debug("tartaly kisseb mint a fagyhatar")
					Domoticz.Debug("futopatron be")
					self.switchFutopatron(True)

				else:
					Domoticz.Debug("tartaly nagyobb mint a fagyhatar")
					Domoticz.Debug("futopatron ki")
					self.switchFutopatron(False)


			elif Devices[1].sValue == "20" and Devices[1].TimedOut == False :  # +Fűtőpatron mód
				Domoticz.Debug("patronmod")
				self.TargetTemp = self.TartalyAktual + self.KapcsolasiDif
				
				if self.TargetTemp < self.KollektorAktual :
					Domoticz.Debug("tartaly + dif kisseb mint a kollektor akt")
					if self.TartalyAktual < self.NapMax :
						Domoticz.Debug("A tartaly hidegebb mint a max")
						Domoticz.Debug("keringteto be")
						self.switchKeringteto(True)
						self.switchFutopatron(False)
					else:
						Domoticz.Debug("A tartaly melegeb mint a max, keringteto ki")
						Domoticz.Debug("keringteto ki")
						self.switchKeringteto(False)
						self.switchFutopatron(False)

				else:
					Domoticz.Debug("keringteto ki")
					self.switchKeringteto(False)
					Domoticz.Debug("tartaly + dif nagyobb mint a kollektor akt, keringteto ki")

					if self.TartalyAktual < (self.PatronMax - float(Devices[10].sValue)):
						Domoticz.Debug("+Fűtőpatron mód tartaly kisebb mint patronmax - hiszterezis, futopatron be")
						self.switchFutopatron(True)

					elif self.TartalyAktual > (self.PatronMax + float(Devices[10].sValue)):
						Domoticz.Debug("+Fűtőpatron mód tartaly nagyobb mint patronmax + hiszterezis, futopatron ki")
						self.switchFutopatron(False)

					else:
						Domoticz.Debug("+Fűtőpatron mód hiszterezis koztes tartomany, nincs kapcsolas")


			self.switchcommand()
			self.statuscommand()

	def switchKeringteto(self, switch):

		command = "On" if switch else "Off"
		Domoticz.Debug("switch_keringteto '{}'".format(command))
		for idx in self.Keringteto:
			self.switchappend(idx,command)

		self.switchstatus(Devices[8].ID,command)

	def switchFutopatron(self, switch):

		command = "On" if switch else "Off"
		Domoticz.Debug("switch_patron '{}'".format(command))
		for idx in self.Futopatron:
			self.switchappend(idx,command)

		self.switchstatus(Devices[9].ID,command)
	
	def switchappend(self,idx,command):

		notInList = True
		for switch in self.switchcreated:
			if switch.idx == idx:
				Domoticz.Debug("Ez a kapcsoló már benne van a listában "+ format(idx) +" | "+ format(command))
				if command == "On":
					Domoticz.Debug("%s az érték felül kell írni a %s értékkel" % (switch.command, command))
					switch.command = command
				else:
					Domoticz.Debug("Marad a %s érték" % command)
				notInList = False
				break
		if notInList:
			Domoticz.Debug("Ez a kapcsoló még nincs a listában, hozzá kell adni " + format(idx) +" | "+ format(command))
			self.switchcreated.append(switchparam(idx, command))


	def switchcommand(self):

		devicesAPI = DomoticzAPI(
			"type=command&param=getdevices&filter=light&order=Name" 
			if float(Parameters["DomoticzVersion"].split()[0]) <= 2023.1 
			else "type=command&param=getdevices&filter=light&order=Name"
		)

		if devicesAPI:
			for switch in self.switchcreated:

				Domoticz.Debug("Kapcsoló {} → kényszerített parancs: {}".format(
					switch.idx,
					switch.command
				))

				DomoticzAPI(
					"type=command&param=switchlight&idx={}&switchcmd={}".format(
						switch.idx,
						switch.command
					)
				)

		

	def switchstatus(self,idx,command):
		notInList = True
		for statusflag in self.statuscreated:
			if statusflag.idx == idx:
				Domoticz.Debug("Ez a status már benne van a listában "+ format(idx) +" | "+ format(command))
				if command == "On":
					Domoticz.Debug("%s az érték felül kell írni a %s értékkel" % (statusflag.command, command))
					statusflag.command = command
				else:
					Domoticz.Debug("Marad a %s érték" % command)
				notInList = False
				break
		if notInList:
			Domoticz.Debug("Ez a status még nincs a listában, hozzá kell adni " + format(idx) +" | "+ format(command))
			self.statuscreated.append(switchparam(idx, command))

	def statuscommand(self):
		devicesAPI = DomoticzAPI(
			"type=command&param=getdevices&filter=light&order=Name" 
			if float(Parameters["DomoticzVersion"].split()[0]) <= 2023.1 
			else "type=command&param=getdevices&filter=light&order=Name"
		)
		if devicesAPI:
			for statusflag in self.statuscreated:
				# A status aktuális állapotonak megállapítása és, annak ellenőrzésére, hogy már a kívánt állapotban van-e?
				for device in devicesAPI["result"]:  # elemzi a kapcsolóeszközt
					deviceidx = int(device["idx"])
					if deviceidx == statusflag.idx:  # ez az a kapcsoló
						Domoticz.Debug("Status " + format(statusflag.idx)+" "+format(device["Status"]))
						if device["Status"] != format(statusflag.command) :
							Domoticz.Debug("Szükség van status váltásra ")
							if format(statusflag.command) == "On":
								nValue = 1
							else :
								nValue = 0

							self.UpdateDevice(device["Unit"],nValue,statusflag.command)
						else: 
							Domoticz.Debug("Nincs szükség status váltásra ")

	def UpdateDevice(self, Unit, nValue, sValue):
		Domoticz.Debug("Update Unit: "+format(Unit)+" | nValue: "+str(nValue)+" | sValue: "+str(sValue)+" ("+Devices[Unit].Name+")")
		Devices[Unit].Update(nValue=nValue, sValue=str(sValue))


	def readTemps(self):

		listKollektor = []
		listTartaly = []
		
		devicesAPI = DomoticzAPI("type=command&param=getdevices&filter=temp&used=true&order=Name")
		if devicesAPI:
			for device in devicesAPI["result"]:  # elemzi az eszközöket a hőmérséklet-érzékelőket keres
				idx = int(device["idx"])
				if idx in self.KollektorSensor:
					if "Temp" in device:
						Domoticz.Debug("device: {}-{} = {}".format(device["idx"], device["Name"], device["Temp"]))
						if not self.SensorTimedOut(idx, device["Name"], device["LastUpdate"]):
							listKollektor.append(device["Temp"])
							device["HaveTimeout"] = False
						else:
							device["HaveTimeout"] = True
				
				if idx in self.TartalySensor:
					if "Temp" in device:
						Domoticz.Debug("device: {}-{} = {}".format(device["idx"], device["Name"], device["Temp"]))
						if not self.SensorTimedOut(idx, device["Name"], device["LastUpdate"]):
							listTartaly.append(device["Temp"])
							device["HaveTimeout"] = False
						else:
							device["HaveTimeout"] = True
						
		else:
			Domoticz.Error("error deviceAPI")

		nbtemps = len(listKollektor)
		if nbtemps > 0:
			self.KollektorAktual = round(sum(listKollektor) / nbtemps, 1)

			Devices[6].Update(nValue=0, sValue=str(self.KollektorAktual), TimedOut=False)

			if self.intemperror:  # korábban érvénytelen hőmérséklet jelzés volt... visszaállítás normálra
				self.intemperror = False
				Devices[1].Update(nValue=Devices[1].nValue, sValue=Devices[1].sValue, TimedOut=False)
		else:
			Devices[1].Update(nValue=Devices[1].nValue, sValue=Devices[1].sValue, TimedOut=True)
			self.switchKeringteto(False)

		Domoticz.Debug("KollektorAktual:"+format(self.KollektorAktual))

		nbtemps = len(listTartaly)
		if nbtemps > 0:
			self.TartalyAktual = round(sum(listTartaly) / nbtemps, 1)

			Devices[7].Update(nValue=0, sValue=str(self.TartalyAktual), TimedOut=False)

			if self.intemperror:  # korábban érvénytelen hőmérséklet jelzés volt... visszaállítás normálra
				self.intemperror = False
				Devices[1].Update(nValue=Devices[1].nValue, sValue=Devices[1].sValue, TimedOut=False)

		else:
			Domoticz.Debug("Nincs tartaly homero futopatron ki")
			self.intemperror = True
			Devices[1].Update(nValue=Devices[1].nValue, sValue=Devices[1].sValue, TimedOut=True)
			self.switchFutopatron(False)
			self.switchKeringteto(False)

		Domoticz.Debug("TartalyAktual:"+format(self.TartalyAktual))

		self.NapMax = float(Devices[2].sValue)
		Domoticz.Debug("NapMax:"+format(self.NapMax))

		self.FagyHatar = float(Devices[3].sValue)
		Domoticz.Debug("FagyHatar:"+format(self.FagyHatar))

		self.KapcsolasiDif = float(Devices[4].sValue)
		Domoticz.Debug("KapcsolasiDif:"+format(self.KapcsolasiDif))

		self.PatronMax = float(Devices[5].sValue)
		Domoticz.Debug("PatronMax:"+format(self.PatronMax))


	def addSchedule(self, deviceidx):

		Domoticz.Log("Idozitok hozzaadasa")
		idx = deviceidx
		DomoticzAPI("type=command&param=addsetpointtimer&active=true&days=128&hour=0&min=0&timertype=1&tvalue=15&idx={}".format(idx))
		DomoticzAPI("type=command&param=addsetpointtimer&active=true&days=128&hour=0&min=0&timertype=4&tvalue=50&idx={}".format(idx))


	def WriteLog(self, message, level="Normal"):

		if (self.loglevel == "Verbose" and level == "Verbose") or level == "Status":
			if self.statussupported:
				Domoticz.Status(message)
			else:
				Domoticz.Log(message)
		elif level == "Normal":
			Domoticz.Log(message)


	def SensorTimedOut(self, idx, name, datestring):

		def LastUpdate(datestring):
			dateformat = "%Y-%m-%d %H:%M:%S"
			# the below try/except is meant to address an intermittent python bug in some embedded systems
			try:
				result = datetime.strptime(datestring, dateformat)
			except TypeError:
				result = datetime(*(time.strptime(datestring, dateformat)[0:6]))
			return result

		timedout = LastUpdate(datestring) + timedelta(minutes=10) < datetime.now()

		# handle logging of time outs... only log when status changes (less clutter in logs)
		if timedout:
			if self.ActiveSensors[idx]:
				Domoticz.Error("skipping timed out temperature sensor '{}'".format(name))
				self.ActiveSensors[idx] = False
		else:
			if not self.ActiveSensors[idx]:
				self.WriteLog("previously timed out temperature sensor '{}' is back online".format(name), "Status")
				self.ActiveSensors[idx] = True

		return timedout


	def addfavorite(self, deviceidx):

		idx = deviceidx
		DomoticzAPI("idx={}&isfavorite=1&param=makefavorite&type=command".format(idx))


	
global _plugin
_plugin = BasePlugin()


def onStart():
	global _plugin
	_plugin.onStart()


def onStop():
	global _plugin
	_plugin.onStop()


def onCommand(Unit, Command, Level, Color):
	global _plugin
	_plugin.onCommand(Unit, Command, Level, Color)


def onHeartbeat():
	global _plugin
	_plugin.onHeartbeat()


# Plugin utility functions ---------------------------------------------------

def parseCSV(strCSV):

	listvals = []
	for value in strCSV.split(","):
		try:
			val = int(value)
		except:
			pass
		else:
			listvals.append(val)
	return listvals


def DomoticzAPI(APICall):

	resultJson = None
	url = "http://{}:{}/json.htm?{}".format(Parameters["Address"], Parameters["Port"], parse.quote(APICall, safe="&="))
	Domoticz.Debug("Calling domoticz API: {}".format(url))
	try:
		req = request.Request(url)
		if Parameters["Username"] != "":
			Domoticz.Debug("Add authentification for user {}".format(Parameters["Username"]))
			credentials = ('%s:%s' % (Parameters["Username"], Parameters["Password"]))
			encoded_credentials = base64.b64encode(credentials.encode('ascii'))
			req.add_header('Authorization', 'Basic %s' % encoded_credentials.decode("ascii"))

		response = request.urlopen(req)
		if response.status == 200:
			resultJson = json.loads(response.read().decode('utf-8'))
			if resultJson["status"] != "OK":
				Domoticz.Error("Domoticz API returned an error: status = {}".format(resultJson["status"]))
				resultJson = None
		else:
			Domoticz.Error("Domoticz API: http error = {}".format(response.status))
	except:
		Domoticz.Error("Error calling '{}'".format(url))
	return resultJson


def CheckParam(name, value, default):
	if type(default) is int and type(value) is int:
		param = value
	elif type(default) is float and type(value) is float:
		param = value
	else:
		param = default
		Domoticz.Error("Parameter '{}' has an invalid value of '{}' ! defaut of '{}' is instead used.".format(name, value, default))
	return param


# Generic helper functions
def DumpConfigToLog():
	for x in Parameters:
		if Parameters[x] != "":
			Domoticz.Debug("'" + x + "':'" + str(Parameters[x]) + "'")
	Domoticz.Debug("Device count: " + str(len(Devices)))
	for x in Devices:
		Domoticz.Debug("Device:" + str(x) + " - " + str(Devices[x]))
		Domoticz.Debug("Device ID:'" + str(Devices[x].ID) + "'")
		Domoticz.Debug("Device Name:'" + Devices[x].Name + "'")
		Domoticz.Debug("Device nValue:" + str(Devices[x].nValue))
		Domoticz.Debug("Device sValue:'" + Devices[x].sValue + "'")
		Domoticz.Debug("Device LastLevel:" + str(Devices[x].LastLevel))
	return
